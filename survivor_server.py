#!/usr/bin/env python3
# Survivor Voting App – Flask & Socket.IO
# (Pythonista-friendly; persistence, extra-vote cards, leader swap, reset)

import uuid, time, os, json, socket, re, sys, threading, random, hmac, hashlib
import logging
from pathlib import Path
from functools import wraps
from rules_engine import SurvivorRulesEngine, TribalPhase
from challenges import challenge_engine, CHALLENGE_DEFINITIONS
from interactions import interaction_engine
import bots as bots_module
from bots import BotRunner

try:
    from flask import Flask, request, jsonify, send_from_directory
    from flask_socketio import SocketIO, emit, join_room
except ImportError as e:
    print(f"Critical dependency missing: {e}")
    print("Please install: pip install flask flask-socketio")
    sys.exit(1)

# ───────────────────────── Configuration ─────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "client", "dist")

# ───────────────────────── Security Configuration ─────────────────────────
# CORS: Set allowed origins for production deployment
# For local development: ["http://localhost:8080", "http://127.0.0.1:8080"]
# For Cloudflare: ["https://survivor.yourdomain.com"]
ALLOWED_ORIGINS = os.environ.get(
    'ALLOWED_ORIGINS',
    '*'  # Default to permissive for local dev; set env var for production
).split(',')

# ───────────────────────── Access Gate ─────────────────────────
# One shared "island code" gates the whole API when the app is exposed to the
# internet (Cloudflare tunnel). No accounts: friends enter the code once, a
# signed cookie remembers them, and changing the code revokes everyone.
#
#   SURVIVOR_ACCESS_CODE set   -> every /api/* call and Socket.IO connection
#                                 requires the cookie from POST /api/access
#   SURVIVOR_ACCESS_CODE unset -> gate disabled (LAN play, dev, tests)
#
# The cookie value is an HMAC derived from the code itself, so there is no
# extra secret to manage and stale cookies die the moment the code changes.
ACCESS_CODE = os.environ.get('SURVIVOR_ACCESS_CODE', '').strip()
ACCESS_COOKIE = 'survivor_access'
ACCESS_COOKIE_MAX_AGE = 90 * 24 * 3600  # one season
_ACCESS_EXEMPT_PATHS = ('/api/access', '/api/access/check', '/api/ping')

# Brute-force throttle: attempts per client IP within the window
_ACCESS_ATTEMPT_LIMIT = 10
_ACCESS_ATTEMPT_WINDOW = 60.0
_access_attempts = {}


def gate_enabled():
    return bool(ACCESS_CODE)


def _access_token():
    """The cookie value that proves knowledge of the current access code."""
    return hmac.new(ACCESS_CODE.encode(), b'survivor-access-v1', hashlib.sha256).hexdigest()


def _has_valid_access_cookie(cookies):
    if not gate_enabled():
        return True
    supplied = cookies.get(ACCESS_COOKIE, '')
    return bool(supplied) and hmac.compare_digest(supplied, _access_token())


def _client_ip():
    """Real client IP — behind the Cloudflare tunnel it's in CF-Connecting-IP."""
    return (request.headers.get('CF-Connecting-IP')
            or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or 'unknown')


def _access_rate_limited(ip):
    """True if this IP has burned its attempt budget for the current window."""
    now = time.time()
    attempts = [t for t in _access_attempts.get(ip, []) if now - t < _ACCESS_ATTEMPT_WINDOW]
    _access_attempts[ip] = attempts
    if len(attempts) >= _ACCESS_ATTEMPT_LIMIT:
        return True
    attempts.append(now)
    # Don't let the map grow unbounded under a distributed guessing attempt
    if len(_access_attempts) > 10000:
        _access_attempts.clear()
    return False

# ───────────────────────── Flask / Socket.IO ─────────────────────────
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
# Use random secret key if not provided (secure default)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(32).hex())
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB limit for iOS

try:
    socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins=ALLOWED_ORIGINS)
except:
    socketio = SocketIO(app, async_mode='threading', cors_allowed_origins=ALLOWED_ORIGINS)
    logger.warning("Using threading mode - consider installing gevent for better performance")

# Enable response compression for performance
try:
    from flask_compress import Compress
    Compress(app)
    logger.info("Response compression enabled")
except ImportError:
    logger.warning("flask-compress not available - install for better performance")

# ───────────────────────── Input Validation ─────────────────────────
def validate_player_name(name):
    """
    Validates player name for security and usability.
    Returns (is_valid, error_message).
    """
    if not name:
        return False, "Player name cannot be empty."
    if len(name) > 30:
        return False, "Player name must be 30 characters or less."
    if len(name) < 2:
        return False, "Player name must be at least 2 characters."
    # Allow letters, numbers, spaces, hyphens, underscores, and common punctuation
    if not re.match(r'^[a-zA-Z0-9_\-\. ]+$', name):
        return False, "Player name can only contain letters, numbers, spaces, hyphens, underscores, and periods."
    return True, None

def validate_player_color(color):
    """
    Validates a player colour.

    Colours are written straight into inline styles on the client, so only accept a
    hex triple or a plain CSS colour name. ``None`` means "assign one for me".
    Returns (is_valid, error_message).
    """
    if color is None:
        return True, None
    if not isinstance(color, str) or not color.strip():
        return False, "Player color is required."
    color = color.strip()
    if re.match(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', color):
        return True, None
    if re.match(r'^[a-zA-Z][a-zA-Z0-9]{1,23}$', color):
        return True, None
    return False, f"'{color}' is not a valid color (use #RRGGBB or a color name)."

# ───────────────────────── Persistent Game State ────────────────────
class GameState:
    _FILE = 'games.json'
    _WINNERS_FILE = 'winners.json'

    def __init__(self):
        self.games = {}
        self._cleanup_temp_files()
        self._load()
        self.rules_engine = SurvivorRulesEngine()
        logger.info("Rules engine initialized successfully")
        self.garbage_collect()
        self._start_gc_thread()

    def _cleanup_temp_files(self):
        """Cleans up orphaned temporary files from previous runs."""
        import glob
        try:
            temp_pattern = f"{self._FILE}.tmp.*"
            for temp_file in glob.glob(temp_pattern):
                if os.path.exists(temp_file) and (time.time() - os.path.getmtime(temp_file) > 300):
                    os.remove(temp_file)
        except Exception as e:
            logger.warning(f"Error during orphaned temp file cleanup: {e}")

    def _save(self):
        """
        Atomically saves the current game state to a JSON file.

        Returns True on success, False on failure. A save failure must not abort the
        game in progress — the in-memory state is still authoritative and the next
        save may well succeed, so this logs loudly and returns False rather than
        raising into whatever request happened to trigger it.
        """
        temp_file = f"{self._FILE}.tmp.{uuid.uuid4().hex[:8]}"
        try:
            current_time = time.time()
            for game in self.games.values():
                game['lastActivity'] = current_time
            with open(temp_file, 'w') as f:
                json.dump(self.games, f, indent=2)
            os.rename(temp_file, self._FILE)
            logger.debug("Game state saved successfully")
            return True
        except Exception as e:
            logger.error(f"GameState save error: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError as cleanup_error:
                    logger.warning(f"Could not clean up temp file {temp_file}: {cleanup_error}")
            return False

    def _load(self):
        """Loads the game state from a JSON file, handling corruption."""
        if not os.path.exists(self._FILE):
            self.games = {}
            return
        try:
            with open(self._FILE, 'r') as f:
                content = f.read().strip()
            if not content:
                self.games = {}
                return
            loaded = json.loads(content)

            # Structural validation: the file must be a mapping of game-id -> game
            # object. Anything else (null, a list, a dict of non-dicts) used to load
            # happily and then crash garbage_collect on startup.
            if not isinstance(loaded, dict):
                raise ValueError(f"expected a JSON object of games, got {type(loaded).__name__}")

            bad_games = [gid for gid, game in loaded.items() if not isinstance(game, dict)]
            for gid in bad_games:
                logger.warning(f"Dropping malformed game '{gid}' from {self._FILE}")
                del loaded[gid]

            self.games = loaded
            logger.info(f"Loaded {len(self.games)} games from {self._FILE}")
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error loading {self._FILE}: {e}")
            self._backup_and_reset()

    def _backup_and_reset(self):
        """Backs up a corrupted game file and resets the game state."""
        try:
            backup_name = f"{self._FILE}.backup.{int(time.time())}"
            if os.path.exists(self._FILE):
                os.rename(self._FILE, backup_name)
        except Exception as e:
            logger.error(f"Failed to backup corrupted file: {e}")
        self.games = {}

    def garbage_collect(self):
        """Removes old and inactive games to save space."""
        current_time = time.time()
        games_to_remove = []
        LOBBY_TIMEOUT = 24 * 3600  # 24 hours
        PLAYING_TIMEOUT = 30 * 24 * 3600 # 30 days
        
        for gid, game in self.games.items():
            last_activity = game.get('lastActivity', game.get('createdAt', current_time))
            age = current_time - last_activity
            phase = game.get('phase', 'lobby')
            
            if (phase == 'lobby' and age > LOBBY_TIMEOUT) or \
               (phase in ['playing', 'tribal_council'] and age > PLAYING_TIMEOUT) or \
               (phase in ['final', 'finished']):
                games_to_remove.append(gid)
        
        for gid in games_to_remove:
            del self.games[gid]
        
        if games_to_remove:
            logger.info(f"Cleaned up {len(games_to_remove)} old games")
            self._save()
        return len(games_to_remove)

    def _start_gc_thread(self):
        """Starts a background thread for periodic garbage collection."""
        def gc_worker():
            while True:
                time.sleep(3600) # Run every hour
                self.garbage_collect()
        threading.Thread(target=gc_worker, daemon=True).start()

    def create_game(self, deckMode=None, expansion=None, **kwargs):
        """
        Creates a new game with a unique ID.

        Args:
            deckMode: "official" (the 67-card box, default) or "extended"
                      (adds the 7 house cards: Idol Nullifier, Steal A Vote,
                      Block A Vote, Grant Immunity)
            expansion: True to add the 5 Orange Challenge Cards from
                       Survivor: Let's Go To Rocks (combined mode)
        """
        gid = str(uuid.uuid4())[:8]
        deck_mode = "extended" if str(deckMode or "official").lower() == "extended" else "official"
        self.games[gid] = {
            'id': gid, 'players': {}, 'turnOrder': [], 'currentTurnIndex': 0,
            'phase': 'lobby', 'deck': [], 'createdAt': time.time(),
            'lastActivity': time.time(),
            'deckMode': deck_mode,
            'expansion': bool(expansion),
            'necklaceHolder': None,
            'challenge': None,
            'interaction': None,
            'currentVote': {
                "type": "single", "votes": {}, "phase": "waiting",
                "councilLeaderId": None, "immunityPlayed": [],
                "tieBreakNeeded": False, "tiedPlayers": [], "eliminated": []
            },
            "gameHistory": [],
            "jury": [],
            "finalTribal": {
                "phase": "waiting", "finalists": [],
                "voteCounts": {}, "tieBreakNeeded": False,
                "tieBreakerLeader": None
            }
        }
        self._save()
        logger.info(f"Created new game: {gid}")
        return gid
    
    def validate_new_player(self, gid, name, color=None):
        """
        Validate a prospective player before adding them.

        Returns {"success": bool, "message": str}. Kept separate from add_player so
        the HTTP layer can surface a specific reason without changing add_player's
        return contract (it returns the new player id, or None).
        """
        g = self.games.get(gid)
        if not g:
            return {"success": False, "message": "Game not found or has ended."}

        if not name or not str(name).strip():
            return {"success": False, "message": "Player name is required."}

        clean_name = str(name).strip()
        is_valid, error = validate_player_name(clean_name)
        if not is_valid:
            return {"success": False, "message": error}

        is_valid, error = validate_player_color(color)
        if not is_valid:
            return {"success": False, "message": error}

        if len(g["players"]) >= 6:
            return {"success": False, "message": "Game is full — maximum 6 players."}

        if g.get("phase") != "lobby":
            return {"success": False, "message": "Game has already started — no new players."}

        for player in g["players"].values():
            if player.get("name", "").strip().lower() == clean_name.lower():
                return {"success": False, "message": f"A player named '{clean_name}' already exists."}
            if color and player.get("color") == color:
                return {"success": False, "message": f"That color is already taken by {player.get('name')}."}

        return {"success": True, "message": f"{clean_name} can join."}

    def add_player(self, gid, name, color=None):
        """Adds a new player to a game. Returns the new player id, or None."""
        g = self.games.get(gid)
        if not g: return None


        if not color:
            colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#F9844A", "#90BE6D", "#F9C74F"]
            used_colors = {p.get("color") for p in g["players"].values()}
            color = next((c for c in colors if c not in used_colors), "#8B5CF6")
        
        player_id = str(uuid.uuid4())[:8]
        g['players'][player_id] = {
            'id': player_id, 'name': name, 'color': color, 'hand': [],
            'isEliminated': False, 'hasStolen': False, 'hasPlayed': False,
            'hasDrawn': False, 'hasVoted': False, 'extraVotes': 0,
            'characterCards': 2, 'isActive': True, 'isCouncilLeader': False,
            'immunityPlayed': False
        }

        # The first player to join becomes the council leader.
        if len(g['players']) == 1:
            g['players'][player_id]['isCouncilLeader'] = True
            if 'currentVote' in g:
                g['currentVote']['councilLeaderId'] = player_id

        if g.get('phase') == 'lobby':
            g['turnOrder'].append(player_id)
        
        self._save()
        return player_id
    
    def reconnect_player(self, gid, pid):
        """Reconnects a player to a game, marking them as active."""
        g = self.games.get(gid)
        if not g: 
            return False
        
        if pid not in g['players']:
            return False
        
        # Mark the player as active
        g['players'][pid]['isActive'] = True
        self._save()
        return True
    
    def start_full_game(self, gid, **kwargs):
        """
        Starts a full game, creating the deck and dealing cards.

        Official Setup (rules steps 2-3): the 6 Vote Cards are removed from the
        deck, each player is given exactly 1 Vote Card (extras put away), then
        3 Action Cards are dealt face down to each player.
        """
        g = self.games.get(gid)
        if not g or g.get("phase") != "lobby" or len(g["players"]) < 3:
            return {"success": False, "message": "Game cannot be started."}

        deck_mode = g.get("deckMode", "official")
        expansion = bool(g.get("expansion"))

        # Setup order matters: deal from the shuffled Action Cards FIRST (step 3),
        # then assemble the Tribal Council Cards into what's left (step 5). Dealing
        # from an already-assembled deck can put a Tribal Council Card in a hand.
        action_deck = self.rules_engine.create_action_deck(deck_mode=deck_mode, expansion=expansion)

        for player in g["players"].values():
            player["hand"] = []
            # 3 Action Cards from the deck...
            for _ in range(3):
                if action_deck:
                    player["hand"].append(action_deck.pop(0))
            # ...plus exactly 1 Vote Card, which never sat in the deck.
            player["hand"].append({"type": "vote"})

        g["deck"] = self.rules_engine.assemble_deck(
            action_deck, len(g["players"]), deck_mode=deck_mode, expansion=expansion
        )

        self.rules_engine.sync_vote_counters(g)
        g["phase"] = "playing"
        g["necklaceHolder"] = None
        g["challenge"] = None
        self._save()
        return {"success": True, "message": "Game started!"}

    def get_game_state(self, gid):
        """Returns the complete state of a game (hidden challenge info stripped)."""
        game = self.games.get(gid)
        if not game: return None
        import copy
        enriched_game = copy.deepcopy(game)
        # Keep derived vote-card counters honest for the client
        self.rules_engine.sync_vote_counters(enriched_game)
        # Strip hidden information (secret rock pulls, secret throws/fingers)
        # before it leaves the server — these keys reveal only at the reveal step.
        for hidden_holder in ("challenge", "interaction", "pending_theft"):
            holder = enriched_game.get(hidden_holder)
            if isinstance(holder, dict):
                for key in [k for k in holder if k.startswith("_")]:
                    del holder[key]
        return enriched_game
    
    def _get_council_leader_id(self, game):
        """Get the current council leader ID from game state."""
        # Check currentVote first
        if "currentVote" in game and game["currentVote"].get("councilLeaderId"):
            return game["currentVote"]["councilLeaderId"]
        
        # Fall back to legacy councilLeaderId field
        if game.get("councilLeaderId"):
            return game["councilLeaderId"]
        
        # Find the first player marked as council leader
        for player_id, player in game.get("players", {}).items():
            if player.get("isCouncilLeader", False):
                return player_id
        
        # Default to first non-eliminated player
        for player_id, player in game.get("players", {}).items():
            if not player.get("isEliminated", False):
                return player_id
        
        return None

    # ═══════════════════════════ Tribal Council Methods ═══════════════════════════
    def start_voting(self, gid, voteType=None, **kwargs):
        """
        Initialize the voting phase of tribal council.
        
        Args:
            gid: Game ID
            voteType: Type of vote ("elimination", "advantage", etc.)
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
            
        game = self.games[gid]
        
        # Validate game is in tribal council phase
        if game.get("phase") != "tribal_council":
            return {"success": False, "message": "Game must be in tribal council phase to start voting"}
            
        current_vote = game.get("currentVote")
        if not current_vote:
            return {"success": False, "message": "No active tribal council found"}
            
        # Initialize voting state
        current_vote["phase"] = "voting"
        current_vote["votes"] = {}
        current_vote["voteType"] = voteType or "elimination"
        
        # Reset player voting flags
        for player in game["players"].values():
            player["hasVoted"] = False
            
        # Clear any previous voting results
        current_vote["tieBreakNeeded"] = False
        current_vote["tiedPlayers"] = []
        current_vote["eliminated"] = []
        
        self._save()
        logger.info(f"Started {voteType} voting in game {gid}")
        
        return {"success": True, "message": f"Voting started for {voteType}"}

    def cast_vote(self, gid, voterId=None, votesData=None, **kwargs):
        """
        Handle player votes during tribal council.
        
        Args:
            gid: Game ID
            voterId: ID of player casting the vote
            votesData: List of vote objects with targetId and vote count
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
            
        if not voterId:
            return {"success": False, "message": "Voter ID required"}

        game = self.games[gid]
        current_vote = game.get("currentVote")

        if not current_vote or current_vote.get("phase") != "voting":
            return {"success": False, "message": "Tribal council voting has not started"}

        if votesData is None:
            return {
                "success": False,
                "message": "Invalid vote data — send a list of votes (an empty list means you have no Vote Card to cast)",
            }

        # Validate voter
        voter = game["players"].get(voterId)
        if not voter:
            return {"success": False, "message": "Invalid voter"}

        if voter.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot vote"}

        if voter.get("voteBanned", False):
            return {"success": False, "message": "Player is banned from voting this round"}

        if voter.get("hasVoted", False):
            return {"success": False, "message": "Player has already voted"}

        # Validate vote data format
        if not isinstance(votesData, list):
            return {"success": False, "message": "Vote data must be a list"}

        # ── Validate the ballot itself before counting cards ──
        necklace_holder = game.get("necklaceHolder")
        vote_targets = {}
        for vote in votesData:
            target_id = vote.get("targetId")
            vote_count = vote.get("votes", 0)

            if not target_id or target_id not in game["players"]:
                return {"success": False, "message": f"Invalid vote target: {target_id}"}

            if target_id == voterId:
                return {"success": False, "message": "Cannot vote for yourself"}

            target = game["players"][target_id]
            if target.get("isEliminated", False):
                return {"success": False, "message": f"Cannot vote for eliminated player: {target.get('name', target_id)}"}

            if necklace_holder and target_id == necklace_holder:
                return {
                    "success": False,
                    "message": f"{target.get('name', target_id)} is wearing the Immunity Idol Necklace and can't be voted for",
                }

            # Accumulate votes for same target
            vote_targets[target_id] = vote_targets.get(target_id, 0) + vote_count

        # ── Vote card economy (F2) ──
        # Vote Cards and Goodwill Gambles MUST be placed in the Voting Box at this
        # Tribal Council; Extra Vote Cards MAY be used now or saved for later.
        mandatory_votes, optional_votes = self.rules_engine.get_vote_capacity(voter)
        total_votes_available = mandatory_votes + optional_votes
        total_votes_cast = sum(vote.get("votes", 0) for vote in votesData)

        if total_votes_available == 0:
            if total_votes_cast > 0:
                return {"success": False, "message": "You have no Vote Card — you can't cast a vote at this Tribal Council"}
            # Passing the Voting Box along with no Vote Card is legal.
            current_vote["votes"][voterId] = {}
            voter["hasVoted"] = True
            self._save()
            logger.info(f"Player {voterId} had no vote cards and passed in game {gid}")
            return {"success": True, "message": "You have no Vote Card — the Voting Box passes you by"}

        if total_votes_cast > total_votes_available:
            return {"success": False, "message": f"Cannot cast {total_votes_cast} votes - only {total_votes_available} available"}

        if total_votes_cast < mandatory_votes:
            return {
                "success": False,
                "message": (
                    f"You must cast all {mandatory_votes} of your Vote/Goodwill Gamble cards "
                    f"at this Tribal Council (tried to cast {total_votes_cast})"
                ),
            }

        # Record the votes
        current_vote["votes"][voterId] = vote_targets
        voter["hasVoted"] = True

        # Physically spend the cards used to vote
        spent = self.rules_engine.spend_vote_cards(voter, total_votes_cast)
        game.setdefault("discard", []).extend(spent)
        current_vote.setdefault("cardsSpent", []).extend(c.get("type") for c in spent)
        self.rules_engine.sync_vote_counters(game)

        self._save()
        logger.info(f"Player {voterId} cast {total_votes_cast} votes in game {gid} (spent {len(spent)} cards)")

        return {"success": True, "message": f"Vote cast successfully - {total_votes_cast} votes recorded"}

    def play_immunity(self, gid, playerId=None, targetId=None, **kwargs):
        """Play immunity idol."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        if not playerId:
            return {"success": False, "message": "playerId is required"}
        
        game = self.games[gid]
        
        # Validate player exists and is not eliminated
        if playerId not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}
        
        player = game["players"][playerId]
        if player.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot play immunity"}
        
        # Validate game is in tribal council phase
        if game.get("phase") != "tribal_council":
            return {"success": False, "message": "Immunity can only be played during tribal council"}
        
        # Check if player has already played immunity this tribal
        if player.get("immunityPlayed", False):
            return {"success": False, "message": "Player has already played immunity this tribal council"}
        
        # Find immunity idol in player's hand
        hand = player.get("hand", [])
        immunity_card_idx = None
        
        for i, card in enumerate(hand):
            resolved_card = self.rules_engine.resolve_card(card)
            if resolved_card.get("type") == "immunity_idol":
                immunity_card_idx = i
                break
        
        if immunity_card_idx is None:
            return {"success": False, "message": "Player does not have an immunity idol"}
        
        # Determine target (self if not specified)
        target_id = targetId or playerId
        if target_id not in game["players"]:
            target_id = playerId  # Fallback to self
        
        target = game["players"][target_id]
        if target.get("isEliminated", False):
            return {"success": False, "message": "Cannot protect eliminated players"}
        
        # Remove immunity idol from hand
        immunity_card = hand.pop(immunity_card_idx)
        
        # Apply immunity protection using rules engine
        params = {"targetId": target_id}
        effect_result = self.rules_engine._effect_immunity_idol(game, playerId, immunity_card, params)
        
        # Mark player as having played immunity
        player["immunityPlayed"] = True
        
        # Track immunity play in currentVote
        current_vote = game.get("currentVote", {})
        if "immunityPlayed" not in current_vote:
            current_vote["immunityPlayed"] = []
        current_vote["immunityPlayed"].append({
            "playerId": playerId,
            "targetId": target_id,
            "timestamp": time.time()
        })
        
        self._save()
        logger.info(f"Player {playerId} played immunity idol for {target_id} in game {gid}")
        
        return {
            "success": True,
            "message": effect_result.get("message", f"Immunity idol played for {target.get('name', 'player')}"),
            "targetId": target_id,
            "protectedPlayer": target.get("name", "player")
        }

    def block_immunity(self, gid, playerId=None, targetId=None, **kwargs):
        """Block immunity with nullifier."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        if not playerId:
            return {"success": False, "message": "playerId is required"}
        
        if not targetId:
            return {"success": False, "message": "targetId is required"}
        
        game = self.games[gid]
        
        # Validate player exists and is not eliminated
        if playerId not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}
        
        player = game["players"][playerId]
        if player.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot block immunity"}
        
        # Validate target exists and is not eliminated
        if targetId not in game["players"]:
            return {"success": False, "message": "Invalid target ID"}
        
        target = game["players"][targetId]
        if target.get("isEliminated", False):
            return {"success": False, "message": "Cannot target eliminated players"}
        
        # Validate game is in tribal council phase
        if game.get("phase") != "tribal_council":
            return {"success": False, "message": "Immunity can only be blocked during tribal council"}
        
        # Check if target has immunity protection
        if not target.get("immunityIdolProtection", False):
            return {"success": False, "message": "Target does not have immunity protection to block"}
        
        # Check if target's immunity has already been nullified
        if target.get("idolNullified", False):
            return {"success": False, "message": "Target's immunity has already been nullified"}
        
        # Find idol nullifier in player's hand
        hand = player.get("hand", [])
        nullifier_card_idx = None
        
        for i, card in enumerate(hand):
            resolved_card = self.rules_engine.resolve_card(card)
            if resolved_card.get("type") == "idol_nullifier":
                nullifier_card_idx = i
                break
        
        if nullifier_card_idx is None:
            return {"success": False, "message": "Player does not have an idol nullifier"}
        
        # Remove nullifier from hand
        nullifier_card = hand.pop(nullifier_card_idx)
        
        # Apply nullifier effect using rules engine
        params = {"targetId": targetId}
        effect_result = self.rules_engine._effect_idol_nullifier(game, playerId, nullifier_card, params)
        
        # Track nullifier play in currentVote
        current_vote = game.get("currentVote", {})
        if "nullifierPlayed" not in current_vote:
            current_vote["nullifierPlayed"] = []
        current_vote["nullifierPlayed"].append({
            "playerId": playerId,
            "targetId": targetId,
            "timestamp": time.time()
        })
        
        self._save()
        logger.info(f"Player {playerId} nullified {targetId}'s immunity in game {gid}")
        
        return {
            "success": True,
            "message": effect_result.get("message", f"Nullified {target.get('name', 'player')}'s immunity"),
            "targetId": targetId,
            "nullifiedPlayer": target.get("name", "player")
        }

    def reveal_votes(self, gid, **kwargs):
        """
        Process and reveal voting results, determining eliminations.
        
        Args:
            gid: Game ID
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
            
        game = self.games[gid]
        current_vote = game.get("currentVote")
        
        if not current_vote:
            return {"success": False, "message": "No active tribal council found"}
            
        # Votes are revealed from the voting phase, or from the immunity phase —
        # the official order is: everyone votes, THEN idols are played, THEN the
        # Council Leader opens the box and tallies.
        if current_vote.get("phase") not in ("voting", "immunity"):
            return {"success": False, "message": "Voting must be in progress to reveal votes"}

        # Advance to reveal phase
        current_vote["phase"] = "reveal"

        # Tally all votes
        vote_counts = {}
        for voter_id, vote_targets in current_vote["votes"].items():
            for target_id, vote_count in vote_targets.items():
                vote_counts[target_id] = vote_counts.get(target_id, 0) + vote_count

        raw_vote_counts = dict(vote_counts)

        # Apply immunity idol protection
        protected_players = set()
        idol_players = set()
        for player_id, player in game["players"].items():
            if player.get("immunityIdolProtection", False):
                # Check if idol was nullified
                if not player.get("idolNullified", False):
                    protected_players.add(player_id)
                    idol_players.add(player_id)
                    if player_id in vote_counts:
                        logger.info(f"Player {player_id} protected by immunity idol - {vote_counts[player_id]} votes negated")
                        del vote_counts[player_id]

        # Apply temporary immunity (from cards like grant_immunity)
        for player_id, player in game["players"].items():
            if player.get("temporaryImmunity", False):
                protected_players.add(player_id)
                if player_id in vote_counts:
                    logger.info(f"Player {player_id} protected by temporary immunity - {vote_counts[player_id]} votes negated")
                    del vote_counts[player_id]

        # The Immunity Idol Necklace makes its wearer un-votable; treat them like an
        # idol player so the Council Leader can only pick them as a last resort.
        necklace_holder = game.get("necklaceHolder")
        if necklace_holder and necklace_holder in game["players"]:
            protected_players.add(necklace_holder)
            idol_players.add(necklace_holder)
            vote_counts.pop(necklace_holder, None)

        # Determine eliminations using the official tie / double-elimination cascade
        elimination_type = current_vote.get("type", "single")
        outcome = self.rules_engine.resolve_tribal_eliminations(
            game,
            vote_counts,
            protected_players=protected_players,
            idol_players=idol_players,
            elimination_type=elimination_type,
        )

        current_vote["eliminated"] = outcome["eliminated"]
        current_vote["tieBreakNeeded"] = outcome["tieBreakNeeded"]
        current_vote["tiedPlayers"] = outcome["tiedPlayers"]
        current_vote["eliminationsNeeded"] = outcome["eliminationsNeeded"]
        current_vote["finalTribalAfter"] = outcome["finalTribalAfter"]
        current_vote["resolution"] = outcome["reason"]

        # Store vote results for display
        current_vote["voteResults"] = vote_counts
        current_vote["rawVoteResults"] = raw_vote_counts
        current_vote["protectedPlayers"] = list(protected_players)

        self._save()
        logger.info(
            f"Vote reveal completed in game {gid} - {len(current_vote['eliminated'])} voted out, "
            f"tie-break needed: {current_vote['tieBreakNeeded']} ({outcome['reason']})"
        )

        if current_vote["tieBreakNeeded"]:
            picks_left = outcome["eliminationsNeeded"] - len(outcome["eliminated"])
            return {
                "success": True,
                "message": (
                    f"Votes revealed - Council Leader must choose {picks_left} of "
                    f"{len(current_vote['tiedPlayers'])} players. {outcome['reason']}"
                ),
                "resolution": outcome["reason"],
            }
        else:
            return {
                "success": True,
                "message": f"Votes revealed - {len(current_vote['eliminated'])} players voted out. {outcome['reason']}",
                "resolution": outcome["reason"],
            }

    def tie_break(self, gid, leaderId=None, chosenId=None, chosenIds=None, **kwargs):
        """
        Handle tie-break scenarios during tribal council.

        The Council Leader may need to pick 1 or 2 players depending on the
        elimination type and how the votes landed (see the official cascade in
        SurvivorRulesEngine.resolve_tribal_eliminations). Picks may be submitted
        one at a time or as a list.

        Args:
            gid: Game ID
            leaderId: ID of tribal council leader making the decision
            chosenId: ID of a single player chosen to be voted out
            chosenIds: list of player IDs chosen to be voted out
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        if not leaderId:
            return {"success": False, "message": "Leader ID required for tie-break"}

        picks = [p for p in (list(chosenIds) if chosenIds else []) if p]
        if chosenId and chosenId not in picks:
            picks.insert(0, chosenId)

        if not picks:
            return {"success": False, "message": "Chosen player ID required for tie-break"}

        game = self.games[gid]
        current_vote = game.get("currentVote")

        if not current_vote:
            return {"success": False, "message": "No active tribal council found"}

        if not current_vote.get("tieBreakNeeded", False):
            return {"success": False, "message": "No tie-break is needed"}

        # Validate tribal council leader
        council_leader_id = current_vote.get("councilLeaderId")
        if not council_leader_id:
            # Fallback: find leader by isCouncilLeader flag
            for pid, player in game["players"].items():
                if player.get("isCouncilLeader", False):
                    council_leader_id = pid
                    current_vote["councilLeaderId"] = pid
                    break

        if leaderId != council_leader_id:
            return {"success": False, "message": "Only the tribal council leader can break ties"}

        tied_players = list(current_vote.get("tiedPlayers", []))
        eliminated = list(current_vote.get("eliminated", []))
        eliminations_needed = current_vote.get(
            "eliminationsNeeded",
            2 if current_vote.get("type") == "double" else 1,
        )

        for chosen_id in picks:
            if len(eliminated) >= eliminations_needed:
                break

            if chosen_id not in tied_players:
                return {"success": False, "message": f"Chosen player must be one of the tied players: {tied_players}"}

            chosen_player = game["players"].get(chosen_id)
            if not chosen_player:
                return {"success": False, "message": "Invalid chosen player"}

            if chosen_player.get("isEliminated", False):
                return {"success": False, "message": "Cannot eliminate already eliminated player"}

            eliminated.append(chosen_id)
            tied_players.remove(chosen_id)

        current_vote["eliminated"] = eliminated
        current_vote["tiedPlayers"] = tied_players
        current_vote["tieBreakResolvedBy"] = leaderId

        picks_left = eliminations_needed - len(eliminated)
        if picks_left > 0 and tied_players:
            current_vote["tieBreakNeeded"] = True
            self._save()
            return {
                "success": True,
                "message": f"Tie-break in progress - Council Leader must choose {picks_left} more player(s)",
                "picksRemaining": picks_left,
            }

        current_vote["tieBreakNeeded"] = False
        self._save()
        logger.info(f"Tie-break resolved by {leaderId} in game {gid} - voted out: {eliminated}")

        return {"success": True, "message": f"Tie-break resolved - {len(eliminated)} players voted out"}

    def complete_tribal(self, gid, **kwargs):
        """
        Complete tribal council and eliminate players.
        
        Args:
            gid: Game ID
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
            
        game = self.games[gid]
        current_vote = game.get("currentVote")
        
        if not current_vote:
            return {"success": False, "message": "No active tribal council found"}
            
        if current_vote.get("tieBreakNeeded", False):
            return {"success": False, "message": "Cannot complete tribal council - tie-break needed"}
            
        voted_out_players = current_vote.get("eliminated", [])

        if not voted_out_players:
            return {"success": False, "message": "No players marked for elimination"}

        # ── Process vote-outs against Survivor Character Cards (F1) ──
        # Official rules: "As long as you have at least one Survivor Character Card,
        # you're still in the game." A vote-out turns over ONE card; you are only
        # eliminated (and join the Jury) when both have been turned over.
        inheritance_messages = []
        jury_members = []
        eliminated_players = []
        survived_players = []

        for player_id in voted_out_players:
            player = game["players"].get(player_id)
            if not player:
                continue

            # Rulebook: Final Tribal starts "the moment there are only 2 players
            # left ... This could happen at a Double Elimination Tribal Council
            # after just the first player is voted out." Once the table is down
            # to 2, remaining flips are spared.
            alive_now = sum(1 for p in game["players"].values()
                            if not p.get("isEliminated", False))
            if alive_now <= 2 and (eliminated_players or survived_players):
                logger.info(f"Double elimination stopped early in {gid} — down to 2 players")
                break

            remaining = max(0, player.get("characterCards", 2) - 1)
            player["characterCards"] = remaining
            player_name = player.get("name", player_id)

            if remaining > 0:
                # Still in the game — one torch left burning.
                survived_players.append(player_name)
                logger.info(
                    f"Player {player_id} turned over a Survivor Character Card "
                    f"({remaining} left) in game {gid}"
                )
                continue

            # Both Survivor Character Cards are gone — truly eliminated.
            player["isEliminated"] = True
            player["isActive"] = False
            eliminated_players.append(player_id)

            # Add to jury (eliminated players become jury members for final tribal)
            if "jury" not in game:
                game["jury"] = []
            if player_id not in game["jury"]:
                game["jury"].append(player_id)
            jury_members.append(player_name)

            # Process inheritance effects — only fires on TRUE elimination
            inheritance_results = self.rules_engine.process_elimination_inheritance(game, player_id)
            inheritance_messages.extend(inheritance_results)

            # "put your cards face up on top of the Discard Pile" — whatever an
            # Inheritance didn't claim leaves the game via the discard
            leftover = game["players"][player_id].get("hand") or []
            if leftover:
                game.setdefault("discard", []).extend(leftover)
                game["players"][player_id]["hand"] = []

            logger.info(f"Player {player_id} eliminated and added to jury in game {gid}")

        # The Tribal Council Card itself goes face up on the Discard Pile
        game.setdefault("discard", []).append(
            {"type": f"tribal_council_{current_vote.get('type', 'single')}"})

        # ── Return 1 Vote Card to every player still in the game ──
        # "After voting has ended, return 1 Vote Card to every player who still has
        #  at least one Survivor Character Card left in the game."
        vote_cards_returned = []
        for player_id, player in game["players"].items():
            if player.get("isEliminated", False):
                continue
            player.setdefault("hand", []).append({"type": "vote"})
            vote_cards_returned.append(player_id)

        # Reset per-tribal flags using rules engine
        self.rules_engine._reset_post_tribal_flags(game)

        # The Immunity Idol Necklace returns to the middle of the table when the
        # Tribal Council ends (Let's Go To Rocks combined mode).
        necklace_released = game.get("necklaceHolder")
        game["necklaceHolder"] = None

        self.rules_engine.sync_vote_counters(game)

        # Check if final tribal should trigger (2 players remaining, regardless of
        # how many Survivor Character Cards they have left)
        active_players = [pid for pid, p in game["players"].items() if not p.get("isEliminated", False)]

        if len(active_players) == 1:
            # Degenerate case the tie cascade tries to avoid; the last player standing wins.
            winner_id = active_players[0]
            game["phase"] = "finished"
            game["winner"] = {
                "playerId": winner_id,
                "playerName": game["players"][winner_id].get("name", winner_id),
            }
            if "currentVote" in game:
                del game["currentVote"]
            message = (
                f"Tribal council completed - {game['players'][winner_id].get('name', winner_id)} "
                "is the last player left in the game and wins!"
            )
        elif len(active_players) == 2:
            # Trigger final tribal council
            self._start_final_tribal_council(game, active_players)
            message = (
                f"Tribal council completed - {len(voted_out_players)} voted out. "
                "Final Tribal Council begins!"
            )
        else:
            # Return to normal game play
            game["phase"] = "playing"

            # Clear tribal council state
            if "currentVote" in game:
                del game["currentVote"]

            # Rotate tribal council leader to next active player
            self._rotate_tribal_leader(game)

            # Advance turn to next player if needed
            if "turnOrder" in game and game["turnOrder"]:
                turn_order = game["turnOrder"]

                # "I'm The Leader Now" gives its player the next turn once tribal ends
                pending = game.pop("pendingTurnPlayerId", None)
                if pending and pending in turn_order and not game["players"][pending].get("isEliminated", False):
                    game["currentTurnIndex"] = turn_order.index(pending)
                else:
                    # Find next active player
                    current_index = game.get("currentTurnIndex", 0)
                    attempts = 0
                    while attempts < len(turn_order):
                        current_index = (current_index + 1) % len(turn_order)
                        next_player_id = turn_order[current_index]
                        if not game["players"][next_player_id].get("isEliminated", False):
                            break
                        attempts += 1

                    game["currentTurnIndex"] = current_index

            # Fresh turn — the new current player still owes a Steal before drawing
            for player in game["players"].values():
                player["hasStolen"] = False
                player["hasPlayed"] = False
                player["hasDrawn"] = False

            message = (
                f"Tribal council completed - {len(voted_out_players)} voted out "
                f"({len(eliminated_players)} eliminated). Game continues with "
                f"{len(active_players)} players."
            )

        game.pop("pendingTurnPlayerId", None)

        # Record elimination in game history
        if "gameHistory" not in game:
            game["gameHistory"] = []

        elimination_record = {
            "type": "tribal_council_elimination",
            "voted_out": voted_out_players,
            "eliminated": eliminated_players,
            "survived_with_one_card": survived_players,
            "elimination_type": current_vote.get("type", "single"),
            "vote_results": current_vote.get("voteResults", {}),
            "jury_members": jury_members,
            "vote_cards_returned": len(vote_cards_returned),
            "timestamp": time.time()
        }
        if necklace_released:
            elimination_record["necklace_released_from"] = necklace_released

        if inheritance_messages:
            elimination_record["inheritance"] = inheritance_messages

        game["gameHistory"].append(elimination_record)

        self._save()
        logger.info(
            f"Tribal council completed in game {gid} - {len(voted_out_players)} voted out, "
            f"{len(eliminated_players)} eliminated, {len(active_players)} remaining"
        )

        result = {
            "success": True,
            "message": message,
            "votedOut": voted_out_players,
            "eliminated": eliminated_players,
            "survivedWithOneCard": survived_players,
        }
        if inheritance_messages:
            result["inheritance_messages"] = inheritance_messages

        return result

    def _rotate_tribal_leader(self, game):
        """
        Rotate the tribal council leader to the next active player in turn order.

        Per rules, the player who draws the Tribal Council card becomes the leader.
        After tribal ends, leadership rotates for the next tribal.
        """
        turn_order = game.get("turnOrder", [])
        if not turn_order:
            return

        # Find current leader
        current_leader_id = None
        for pid, player in game["players"].items():
            if player.get("isCouncilLeader", False):
                current_leader_id = pid
                break

        if not current_leader_id:
            # No current leader, assign first active player
            for pid in turn_order:
                player = game["players"].get(pid)
                if player and not player.get("isEliminated", False):
                    player["isCouncilLeader"] = True
                    logger.info(f"Assigned {pid} as initial council leader")
                    return

        # Find current leader's position in turn order
        try:
            current_index = turn_order.index(current_leader_id)
        except ValueError:
            current_index = 0

        # Clear old leader status
        for player in game["players"].values():
            player["isCouncilLeader"] = False

        # Find next active player
        attempts = 0
        while attempts < len(turn_order):
            current_index = (current_index + 1) % len(turn_order)
            next_leader_id = turn_order[current_index]
            next_leader = game["players"].get(next_leader_id)
            if next_leader and not next_leader.get("isEliminated", False):
                next_leader["isCouncilLeader"] = True
                logger.info(f"Rotated council leader to {next_leader_id}")
                return
            attempts += 1

    def _trigger_tribal_council(self, game, elimination_type="single", drawer_id=None):
        """
        Trigger a tribal council when a tribal council card is drawn.

        Args:
            game: Game state dictionary
            elimination_type: Type of elimination ("single" or "double")
            drawer_id: Player who drew the card — they become the Council Leader
        """
        # Transition game from "playing" to "tribal_council" phase
        game["phase"] = "tribal_council"

        if drawer_id and drawer_id in game.get("players", {}):
            for pid, player in game["players"].items():
                player["isCouncilLeader"] = (pid == drawer_id)
            leader_id = drawer_id
        else:
            leader_id = self._get_council_leader_id(game)

        # Initialize the currentVote structure for tribal council
        game["currentVote"] = {
            "type": elimination_type,
            "phase": "announcement",  # Start with announcement phase
            "votes": {},
            "councilLeaderId": leader_id,
            "immunityPlayed": [],
            "advantageCardsPlayed": [],
            "tieBreakNeeded": False,
            "tiedPlayers": [],
            "eliminated": [],
            "eliminationsNeeded": 2 if elimination_type == "double" else 1,
            "voteResults": {}
        }

        # Clear previous tribal council state flags
        for player in game["players"].values():
            player["hasVoted"] = False
            player["immunityPlayed"] = False

        logger.info(f"Triggered tribal council with {elimination_type} elimination (leader={leader_id})")

    def _initialize_tribal_council(self, game, elimination_type="single", drawer_id=None):
        """Alias for _trigger_tribal_council (older call sites use this name)."""
        return self._trigger_tribal_council(game, elimination_type, drawer_id)

    def reset_tribal_council(self, gid, **kwargs):
        """Reset current tribal council."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        
        # Validate game is in tribal council phase
        if game.get("phase") != "tribal_council":
            return {"success": False, "message": "Game is not in tribal council phase"}
        
        # Return to playing phase
        game["phase"] = "playing"

        # Reset tribal council state back to the idle shape a new game starts with
        # (rather than deleting it) so start_voting and the client can read it.
        game["currentVote"] = {
            "type": "single", "votes": {}, "phase": "waiting",
            "councilLeaderId": self._get_council_leader_id(game),
            "immunityPlayed": [], "advantageCardsPlayed": [],
            "tieBreakNeeded": False, "tiedPlayers": [], "eliminated": [],
            "voteResults": {}
        }

        # Reset per-tribal flags using rules engine
        self.rules_engine._reset_post_tribal_flags(game)

        # Reset player voting states
        for player in game["players"].values():
            player["hasVoted"] = False
            player["immunityPlayed"] = False

        self._save()
        logger.info(f"Reset tribal council in game {gid}")
        
        return {
            "success": True, 
            "message": "Tribal council reset - game returned to playing phase"
        }

    def advance_tribal_phase(self, gid, target_phase=None, **kwargs):
        """
        Advance tribal council to a specific phase with validation.

        Args:
            gid: Game ID
            target_phase: Phase to advance to (positional or keyword)
            **kwargs: Additional keyword arguments (supports 'phase' from API handler)

        Returns:
            Boolean indicating success
        """
        # Support both direct calls (positional) and API handler calls (kwarg 'phase')
        if target_phase is None:
            target_phase = kwargs.get('phase')
        if not target_phase:
            return False

        if gid not in self.games:
            return False

        game = self.games[gid]

        # Use rules engine to advance tribal phase with validation
        success, message = self.rules_engine.advance_tribal_phase(game, target_phase)
        
        if success:
            self._save()
            logger.info(f"Advanced tribal phase to {target_phase} in game {gid}")
            
        return success

    def play_tribal_advantage(self, gid, playerId=None, advantageType=None, targetId=None, **kwargs):
        """
        Play a tribal advantage card during tribal council.

        Args:
            gid: Game ID
            playerId: ID of the player playing the advantage
            advantageType: Type of advantage card (e.g., 'steal_vote', 'block_vote', 'extra_vote', 'grant_immunity')
            targetId: Optional target player ID for targeted advantages
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        if not playerId:
            return {"success": False, "message": "playerId is required"}

        if not advantageType:
            return {"success": False, "message": "advantageType is required"}

        game = self.games[gid]

        # Validate player exists
        if playerId not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}

        # Delegate to rules engine
        result = self.rules_engine.play_tribal_advantage(game, playerId, advantageType, targetId)

        if result.get("success"):
            self._save()
            logger.info(f"Tribal advantage {advantageType} played by {playerId} in game {gid}")

        return result

    def enhanced_tie_break(self, gid, leaderId=None, chosenIds=None, chosenId=None, **kwargs):
        """
        Handle a multi-pick tie break (double elimination where the Council Leader
        chooses 2 players). Thin wrapper over tie_break, which accepts a list.
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        return self.tie_break(gid, leaderId=leaderId, chosenId=chosenId, chosenIds=chosenIds)

    def _start_final_tribal_council(self, game, finalists):
        """
        Initialize final tribal council with 2 remaining players.
        
        Args:
            game: Game state dictionary
            finalists: List of 2 finalist player IDs
        """
        if len(finalists) != 2:
            logger.warning(f"Final tribal requires exactly 2 finalists, got {len(finalists)}")
            return
            
        # Initialize final tribal state
        game["phase"] = "final_tribal"
        
        # Get jury members (all eliminated players)
        jury_members = game.get("jury", [])
        
        # Determine tribal council leader (most recent elimination)
        leader_id = jury_members[-1] if jury_members else finalists[0]
        
        game["finalTribal"] = {
            "phase": "questions",
            "finalists": finalists,
            "jury": jury_members,
            "leader": leader_id,
            "votes": {},
            "juryReady": [],
            # The official three Final Tribal Council questions (F10)
            "questions": [
                "What was your strategy coming into the game?",
                "What was your best move in the game?",
                "How did you outplay your opponent?"
            ],
            "voteCounts": {},
            "tieBreakNeeded": False
        }
        
        logger.info(f"Final tribal council started with finalists: {finalists}, jury: {jury_members}, leader: {leader_id}")

    def _determine_final_winner(self, game, final_tribal):
        """
        Tally final tribal votes and determine the winner or if a tie-break is needed.

        Per rules: The player with the most votes is declared the Sole Survivor.
        If tied, the Final Tribal Council Leader breaks the tie.
        """
        votes = final_tribal.get("votes", {})
        finalists = final_tribal.get("finalists", [])

        # Tally votes for each finalist
        vote_counts = {finalist: 0 for finalist in finalists}
        for jury_member_id, voted_for in votes.items():
            if voted_for in vote_counts:
                vote_counts[voted_for] += 1

        final_tribal["voteCounts"] = vote_counts

        # Find the winner(s)
        max_votes = max(vote_counts.values()) if vote_counts else 0
        winners = [fid for fid, count in vote_counts.items() if count == max_votes]

        if len(winners) == 1:
            # Clear winner
            winner_id = winners[0]
            final_tribal["winner"] = winner_id
            final_tribal["tieBreakNeeded"] = False
            game["phase"] = "finished"
            game["winner"] = winner_id
            logger.info(f"Final tribal winner determined: {winner_id} with {max_votes} votes")
        else:
            # Tie - leader must break
            final_tribal["tieBreakNeeded"] = True
            final_tribal["tiedFinalists"] = winners
            logger.info(f"Final tribal tie between {winners}, leader must break tie")

    # ═══════════════════════════ Final Tribal Methods ═══════════════════════════
    def advance_final_phase(self, gid, target_phase=None, **kwargs):
        """
        Advance final tribal council to a specific phase.

        Args:
            gid: Game ID
            target_phase: Phase to advance to ("deliberation", "voting", "reveal").
                          The HTTP layer sends this as the keyword 'phase', which this
                          signature must accept — it previously raised TypeError, so
                          POST /api/final/advance never worked from the client.

        Returns:
            Boolean indicating success
        """
        if target_phase is None:
            target_phase = kwargs.get('phase')
        if not target_phase:
            return False

        if gid not in self.games:
            return False


        game = self.games[gid]
        
        # Validate game is in final phase
        if game.get("phase") not in ["final", "final_tribal"]:
            return False
            
        # Get final tribal state
        final_tribal = game.get("finalTribal", {})
        current_phase = final_tribal.get("phase", "questions")
        
        # Valid phase transitions for final tribal
        # Allow skipping deliberation (go directly to voting from questions)
        valid_transitions = {
            "questions": ["deliberation", "voting"],
            "deliberation": ["voting"],
            "voting": ["reveal"],
            "reveal": []
        }
        
        # Check if transition is valid
        if target_phase not in valid_transitions.get(current_phase, []) and current_phase != target_phase:
            return False
            
        # Execute the phase transition
        final_tribal["phase"] = target_phase
        
        # Phase-specific initialization
        if target_phase == "deliberation":
            final_tribal["juryReady"] = []
        elif target_phase == "voting":
            final_tribal["votes"] = {}
            final_tribal["juryReady"] = []
        elif target_phase == "reveal":
            # Tally votes and determine winner
            self._determine_final_winner(game, final_tribal)

        self._save()
        logger.info(f"Advanced final tribal phase to {target_phase} in game {gid}")
        return True

    def cast_final_vote(self, gid, juryMemberId=None, finalistId=None, **kwargs):
        """
        Cast final tribal vote from a jury member for a finalist.

        In Survivor, the jury votes for who they think should WIN (not who should be eliminated).
        All jury members point simultaneously at their chosen finalist.

        Args:
            gid: Game ID
            juryMemberId: ID of the jury member casting the vote
            finalistId: ID of the finalist they're voting FOR (to win)

        Returns:
            Boolean indicating success
        """
        if gid not in self.games:
            return False

        if not juryMemberId or not finalistId:
            return False

        game = self.games[gid]

        # Validate game is in final tribal phase
        if game.get("phase") not in ["final", "final_tribal"]:
            return False

        final_tribal = game.get("finalTribal", {})

        # Validate we're in voting phase
        if final_tribal.get("phase") != "voting":
            return False

        # Validate jury member is actually a jury member
        jury = final_tribal.get("jury", [])
        if juryMemberId not in jury:
            return False

        # Validate finalist is actually a finalist
        finalists = final_tribal.get("finalists", [])
        if finalistId not in finalists:
            return False

        # Record the vote
        if "votes" not in final_tribal:
            final_tribal["votes"] = {}

        final_tribal["votes"][juryMemberId] = finalistId

        # Track that this jury member is ready (has voted)
        if "juryReady" not in final_tribal:
            final_tribal["juryReady"] = []
        if juryMemberId not in final_tribal["juryReady"]:
            final_tribal["juryReady"].append(juryMemberId)

        logger.info(f"Final vote cast in game {gid}: jury member {juryMemberId} voted for {finalistId}")

        # Check if all jury members have voted - auto-advance to reveal
        all_voted = len(final_tribal["votes"]) >= len(jury)
        if all_voted:
            final_tribal["phase"] = "reveal"
            self._determine_final_winner(game, final_tribal)

        self._save()
        return True

    def break_final_tie(self, gid, leaderId=None, winnerId=None, chosenWinner=None, **kwargs):
        """
        Break a tie in the final tribal council.

        Per rules: If both players get the same number of votes,
        the Final Tribal Council Leader breaks the tie by choosing the winner.
        They DON'T have to pick the player they originally voted for.

        Args:
            gid: Game ID
            leaderId: ID of the Final Tribal Council Leader (must be the tie-breaker)
            winnerId: ID of the finalist chosen to win. The iOS client sends this as
                      'chosenWinner' (which the route also requires), so both spellings
                      are accepted — previously the chosen winner was dropped and the
                      tie-break always failed.

        Returns:
            Boolean indicating success
        """
        if gid not in self.games:
            return False

        winnerId = winnerId or chosenWinner
        if not leaderId or not winnerId:
            return False

        game = self.games[gid]

        # Validate game is in final tribal phase
        if game.get("phase") not in ["final", "final_tribal"]:
            return False

        final_tribal = game.get("finalTribal", {})

        # Validate we're in reveal phase and tie-break is needed
        if final_tribal.get("phase") != "reveal":
            return False

        if not final_tribal.get("tieBreakNeeded", False):
            return False

        # Validate leader is the Final Tribal Council Leader
        if leaderId != final_tribal.get("leader"):
            return False

        # Validate winner is a finalist
        finalists = final_tribal.get("finalists", [])
        if winnerId not in finalists:
            return False

        # Record the winner
        final_tribal["winner"] = winnerId
        final_tribal["tieBreakNeeded"] = False
        final_tribal["tieBreakBy"] = leaderId

        # Mark game as finished
        game["phase"] = "finished"
        game["winner"] = winnerId

        self._save()
        logger.info(f"Final tie broken in game {gid}: leader {leaderId} chose {winnerId} as winner")
        return True

    def signal_jury_ready(self, gid, juryMemberId=None, **kwargs):
        """
        Signal that a jury member is ready to vote (finger raised).

        Per rules: When each member of the Jury is ready to vote, they raise a finger.
        When every member has a finger raised, voting proceeds.

        Args:
            gid: Game ID
            juryMemberId: ID of the jury member signaling readiness

        Returns:
            Boolean indicating success
        """
        if gid not in self.games:
            return False

        if not juryMemberId:
            return False

        game = self.games[gid]

        # Validate game is in final tribal phase
        if game.get("phase") not in ["final", "final_tribal"]:
            return False

        final_tribal = game.get("finalTribal", {})

        # Fingers go up during deliberation, once the statements are done
        if final_tribal.get("phase") != "deliberation":
            return False

        # Validate player is a jury member
        jury = final_tribal.get("jury", [])
        if juryMemberId not in jury:
            return False

        # Track readiness
        if "juryReady" not in final_tribal:
            final_tribal["juryReady"] = []

        if juryMemberId not in final_tribal["juryReady"]:
            final_tribal["juryReady"].append(juryMemberId)

        logger.info(f"Jury member {juryMemberId} signaled ready in game {gid}")

        # Check if all jury members are ready - auto-advance to voting.
        # juryReady is deliberately NOT cleared: it records who raised a finger, and
        # clearing it here made a jury member's own signal vanish from the state they
        # get back.
        all_ready = jury and len(final_tribal["juryReady"]) >= len(jury)
        if all_ready:
            final_tribal["phase"] = "voting"
            final_tribal["votes"] = {}

        self._save()
        return True

    # ═══════════════════════════ Game Management Methods ═══════════════════════════
    def change_leader(self, gid, newLeaderId=None, **kwargs):
        """Change tribal council leader."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        if not newLeaderId:
            return {"success": False, "message": "newLeaderId is required"}
        
        game = self.games[gid]
        
        # Validate new leader exists and is not eliminated
        if newLeaderId not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}
        
        new_leader = game["players"][newLeaderId]
        if new_leader.get("isEliminated", False):
            return {"success": False, "message": "Cannot make eliminated player the leader"}
        
        # Clear old leader status
        for player in game["players"].values():
            player["isCouncilLeader"] = False
        
        # Set new leader
        new_leader["isCouncilLeader"] = True
        
        # Update currentVote state if exists
        if "currentVote" in game:
            game["currentVote"]["councilLeaderId"] = newLeaderId
        
        # Update legacy councilLeaderId field if exists
        if "councilLeaderId" in game:
            game["councilLeaderId"] = newLeaderId
        
        self._save()
        logger.info(f"Changed leader to {newLeaderId} in game {gid}")
        
        return {
            "success": True, 
            "message": f"{new_leader.get('name', 'Player')} is now the tribal council leader",
            "newLeaderId": newLeaderId
        }

    def add_bot(self, gid, **kwargs):
        """Add a computer player to a lobby. The server picks name and color."""
        g = self.games.get(gid)
        if not g:
            return {"success": False, "message": "Game not found"}
        if g.get("phase") != "lobby":
            return {"success": False, "message": "Computer players can only join in the lobby"}
        if len(g["players"]) >= 6:
            return {"success": False, "message": "Game is full — maximum 6 players."}

        taken_names = {p.get("name", "").lower() for p in g["players"].values()}
        name = next((n for n in bots_module.BOT_NAMES
                     if n.lower() not in taken_names), None)
        if name is None:
            return {"success": False, "message": "The island is out of computer players"}

        taken_colors = {p.get("color") for p in g["players"].values()}
        color = next((c for c in bots_module.BOT_COLORS
                      if c not in taken_colors), None)

        validation = self.validate_new_player(gid, name, color)
        if not validation.get("success"):
            return validation
        pid = self.add_player(gid, name, color)
        if not pid:
            return {"success": False, "message": "Could not add the computer player"}
        g["players"][pid]["isBot"] = True
        self._save()
        logger.info(f"Bot {name} ({pid}) added to game {gid}")
        return {"success": True, "message": f"{name} wanders into camp",
                "playerId": pid, "name": name}

    def remove_bot(self, gid, playerId=None, **kwargs):
        """Remove a computer player — lobby only, bots only."""
        g = self.games.get(gid)
        if not g:
            return {"success": False, "message": "Game not found"}
        if g.get("phase") != "lobby":
            return {"success": False, "message": "The game has started — the tribe is set."}
        player = g["players"].get(playerId)
        if not player:
            return {"success": False, "message": "Invalid player ID"}
        if not player.get("isBot"):
            return {"success": False, "message": "Only computer players can be removed"}

        name = player.get("name", "?")
        was_leader = player.get("isCouncilLeader")
        del g["players"][playerId]
        if playerId in g.get("turnOrder", []):
            g["turnOrder"].remove(playerId)
        # A departing leader hands the torch to the first remaining player
        if was_leader and g["players"]:
            first = next(iter(g["players"]))
            g["players"][first]["isCouncilLeader"] = True
            if "currentVote" in g:
                g["currentVote"]["councilLeaderId"] = first
        self._save()
        logger.info(f"Bot {name} ({playerId}) removed from game {gid}")
        return {"success": True, "message": f"{name} walks back into the jungle"}

    def rename_player(self, gid, playerId=None, newName=None, **kwargs):
        """Rename a player. Only allowed in the lobby — once the game starts,
        you are who the tribe knows you as."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]
        if game.get("phase") != "lobby":
            return {"success": False, "message": "The game has started — names are set."}

        if not playerId or playerId not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}

        clean_name = str(newName or "").strip()
        if not clean_name:
            return {"success": False, "message": "Player name is required."}

        is_valid, error = validate_player_name(clean_name)
        if not is_valid:
            return {"success": False, "message": error}

        for pid, player in game["players"].items():
            if pid != playerId and player.get("name", "").strip().lower() == clean_name.lower():
                return {"success": False, "message": f"A player named '{clean_name}' already exists."}

        old_name = game["players"][playerId].get("name", "?")
        game["players"][playerId]["name"] = clean_name
        self._save()
        logger.info(f"Player {playerId} renamed '{old_name}' -> '{clean_name}' in game {gid}")
        return {"success": True, "message": f"{old_name} is now {clean_name}", "newName": clean_name}

    def steal_card(self, gid, thiefId=None, targetId=None, **kwargs):
        """
        Steal card from another player.

        Accepts ``steal_card(gid, thiefId=..., targetId=...)`` or the positional
        form ``steal_card(gid, thief_id, target_id)``.
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]
        thief_id = thiefId or kwargs.get('thiefId') or kwargs.get('playerId')
        target_id = targetId or kwargs.get('targetId')


        if not thief_id or not target_id:
            return {"success": False, "message": "Both thiefId and targetId are required"}

        if game.get("phase") != "playing":
            return {
                "success": False,
                "message": f"Game is not in playing phase (currently '{game.get('phase')}') — stealing is a turn action",
            }

        if thief_id not in game["players"]:
            return {"success": False, "message": "Thief player not found in this game"}

        if target_id not in game["players"]:
            return {"success": False, "message": "Target player not found in this game"}

        # Validate it's the thief's turn
        turn_order = game.get("turnOrder", [])
        current_index = game.get("currentTurnIndex", 0)
        if turn_order and turn_order[current_index] != thief_id:
            return {"success": False, "message": "It's not your turn to steal"}

        # Prevent stealing from yourself
        if thief_id == target_id:
            return {"success": False, "message": "You cannot steal from yourself"}

        blocked = self._challenge_block_reason(game)
        if blocked:
            return {"success": False, "message": blocked}

        thief = game["players"][thief_id]
        target = game["players"][target_id]
        
        # Validate thief can steal
        if thief.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot steal"}
        
        if thief.get("hasStolen", False):
            return {"success": False, "message": "Player has already stolen this turn"}
        
        # Validate target
        if target.get("isEliminated", False):
            return {"success": False, "message": "Cannot steal from eliminated players"}
        
        if not target.get("hand"):
            thief["hasStolen"] = True  # Mark as stolen even if no cards
            return {"success": True, "message": f"{target.get('name', 'Player')} has no cards to steal"}
        
        # Check if target has reactive cards (Sorry For You)
        reactive_cards = []
        for i, card in enumerate(target.get("hand", [])):
            resolved_card = self.rules_engine.resolve_card(card)
            if resolved_card.get("reactive_only", False) and resolved_card.get("type") == "sorry_for_you":
                reactive_cards.append((i, resolved_card))
        
        if reactive_cards:
            # Set up pending theft state for reactive interrupt window
            game["pending_theft"] = {
                "thiefId": thief_id,
                "thiefIds": [thief_id],
                "targetId": target_id,
                "source": "steal",
                "reactive_window_open": True
            }
            self._save()
            return {
                "success": True, 
                "message": "Theft initiated - target can play reactive cards",
                "reactive_window": True,
                "reactive_cards": [card[1] for card in reactive_cards]
            }
        
        # No reactive cards, execute theft immediately
        theft_result = self.rules_engine.execute_theft(game, thief_id, target_id)
        if theft_result.get("success"):
            stolen_cards = theft_result.get("stolen_cards", [])
            self._save()
            return {
                "success": True, 
                "message": f"Stole {len(stolen_cards)} card(s) from {target.get('name', 'player')}",
                "stolen_cards": stolen_cards
            }
        else:
            return {"success": False, "message": theft_result.get("message", "Theft failed")}

    def get_complete_card(self, card_type):
        """Resolve a card type name into a full card dict (None if unknown)."""
        return self.rules_engine.get_complete_card(card_type)

    def play_card(self, gid, playerId=None, cardIdx=None, params=None, **kwargs):
        """
        Play a card.

        Accepts either the keyword form used by the HTTP layer
        (``playerId``/``cardIdx`` plus card params as top-level kwargs) or the
        positional form ``play_card(gid, player_id, card_idx, {"targetId": ...})``.
        ``cardIdx`` may be a hand index or a card type name.
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]
        player_id = playerId or kwargs.get('playerId')
        card_idx = cardIdx if cardIdx is not None else kwargs.get('cardIdx')
        if isinstance(params, dict):
            kwargs = {**params, **kwargs}

        if not player_id or card_idx is None:
            return {"success": False, "message": "Both playerId and cardIdx are required"}

        if player_id not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}

        # Allow addressing a card by type name as well as by hand index
        if isinstance(card_idx, str) and not card_idx.lstrip('-').isdigit():
            hand = game["players"][player_id].get("hand", [])
            match = next((i for i, c in enumerate(hand) if c.get("type") == card_idx), None)
            if match is None:
                return {"success": False, "message": f"Player does not have a {card_idx} card"}
            card_idx = match
        else:
            try:
                card_idx = int(card_idx)
            except (TypeError, ValueError):
                return {"success": False, "message": "Invalid card index"}


        player = game["players"][player_id]

        if player.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot play cards"}

        blocked = self._challenge_block_reason(game)
        if blocked:
            return {"success": False, "message": blocked}

        hand = player.get("hand", [])
        if card_idx < 0 or card_idx >= len(hand):
            return {"success": False, "message": "Invalid card index"}

        compact_card = hand[card_idx]
        card = self.rules_engine.resolve_card(compact_card)
        
        # Get current phase for validation
        current_phase = self.rules_engine.get_current_turn_phase(game, player_id)
        
        # Validate card play
        is_valid, reason = self.rules_engine.validate_play(game, player_id, card, current_phase, kwargs)
        if not is_valid:
            return {"success": False, "message": reason}
        
        # Remove card from hand before executing effect
        played_card = hand.pop(card_idx)
        
        # Execute card effect
        effect_result = self.rules_engine.execute_effect(game, player_id, card, kwargs)
        
        if not effect_result.get("success", False):
            # If effect failed, put card back in hand
            hand.insert(card_idx, played_card)
            return {"success": False, "message": effect_result.get("message", "Card effect failed")}
        
        # Official rule: "Play 1 card from your hand if you'd like to." The one
        # turn-play is spent now; tribal/reactive plays don't touch the flag.
        if current_phase == "turn_play":
            player["hasPlayed"] = True

        # "place it face up on the Discard Pile"
        if card.get("category") != "tribal_council" and card.get("type") != "goodwill_gamble":
            game.setdefault("discard", []).append({"type": card.get("type")})

        # Handle tribal council card triggers
        if card.get("category") == "tribal_council":
            self._trigger_tribal_council(
                game,
                card.get("elimination_type", "single"),
                drawer_id=player_id,
            )

        # Handle Let's Go To Rocks Challenge Card triggers
        challenge_message = None
        challenge_started = False
        if effect_result.get("start_challenge"):
            start_result = challenge_engine.start(game, player_id, effect_result["start_challenge"])
            challenge_message = start_result.get("message")
            challenge_started = bool(start_result.get("success")) and not start_result.get("unavailable")
            if not start_result.get("success"):
                # The challenge couldn't run — the card is still discarded, but say why.
                challenge_message = start_result.get("message")

        # Handle Reward Challenge interactions (Do Or Die / Power Pair / Numbers Game)
        interaction_message = None
        if effect_result.get("start_interaction"):
            start_result = interaction_engine.start(
                game, player_id,
                effect_result["start_interaction"],
                effect_result.get("interaction_params") or {},
            )
            interaction_message = start_result.get("message")

        self.rules_engine.sync_vote_counters(game)
        self._save()
        response = {
            "success": True,
            "message": interaction_message or challenge_message
                       or effect_result.get("message", f"Played {card.get('name', 'card')}"),
            "card_effect": effect_result,
            "tribal_triggered": card.get("category") == "tribal_council"
        }
        if effect_result.get("start_challenge"):
            response["challenge_started"] = challenge_started
        if effect_result.get("start_interaction"):
            response["interaction_started"] = bool(game.get("interaction"))
        return response

    # ═══════════════════════════ Reward Challenge Interactions ═══════════════════════════
    def interaction_action(self, gid, playerId=None, action=None, value=None, **kwargs):
        """
        Take an action in the active Reward Challenge interaction.

        Args:
            gid: Game ID
            playerId: player acting
            action: 'pick' (secret throw/fingers) | 'give' (own-hand card index for
                    a tie swap or all-match discard) | 'steal_from' (Numbers Game
                    winner's victim) | 'dismiss'
            value: the pick / index / target depending on the action
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]

        if not playerId:
            return {"success": False, "message": "playerId is required"}
        if not action:
            return {"success": False, "message": "action is required"}

        result = interaction_engine.act(game, playerId, action, value)

        if result.get("success"):
            self.rules_engine.sync_vote_counters(game)
            self._save()

        return result

    # ═══════════════════════════ Rocks Expansion Challenges ═══════════════════════════
    def _challenge_block_reason(self, game):
        """
        Return an error message if an unfinished Challenge or Reward Challenge
        interaction blocks other turn actions.
        """
        theft = game.get("pending_theft")
        if theft and theft.get("reactive_window_open"):
            victim = game["players"].get(theft.get("targetId"), {}).get("name", "someone")
            return f"Waiting on {victim} - they may play Sorry For You"
        challenge = game.get("challenge")
        if challenge and challenge.get("phase") not in (None, "complete"):
            return f"Resolve the active Challenge ({challenge.get('name')}) before continuing your turn"
        interaction = game.get("interaction")
        if interaction and interaction.get("phase") not in (None, "complete"):
            return f"Resolve the {interaction.get('name', 'Reward Challenge')} before continuing your turn"
        return None

    def _award_challenge_win(self, game, winner_id):
        """
        Apply the reward for winning a Challenge.

        "When you win a Challenge from Survivor: Let's Go To Rocks, put on the
        Immunity Idol Necklace. While wearing it, players can't vote for you in the
        next Tribal Council. ... If someone is already wearing the Immunity Idol
        Necklace when you win a Challenge, you instead get to take 3 random cards
        from anywhere in the Draw Pile. You CAN'T take Tribal Council cards."
        """
        winner = game["players"].get(winner_id)
        if not winner:
            return "Challenge winner is no longer in the game"

        name = winner.get("name", winner_id)

        if not game.get("necklaceHolder"):
            game["necklaceHolder"] = winner_id
            return f"{name} wears the Immunity Idol Necklace — nobody can vote for them at the next Tribal Council!"

        # Someone already wears the Necklace → take 3 random non-tribal cards
        deck = game.get("deck", [])
        eligible = [
            i for i, card in enumerate(deck)
            if not str(card.get("type", "")).startswith("tribal_council")
        ]
        picked = sorted(random.sample(eligible, min(3, len(eligible))), reverse=True)
        taken = []
        for idx in picked:
            taken.append(deck.pop(idx))
        winner.setdefault("hand", []).extend(taken)
        self.rules_engine.sync_vote_counters(game)

        holder_name = game["players"].get(game["necklaceHolder"], {}).get("name", "another player")
        return (
            f"{name} won the Challenge, but {holder_name} already wears the Immunity Idol Necklace — "
            f"{name} takes {len(taken)} random cards from the Draw Pile instead."
        )

    def challenge_action(self, gid, playerId=None, action=None, value=None, **kwargs):
        """
        Take an action in the active Rocks Challenge.

        Args:
            gid: Game ID
            playerId: player acting
            action: 'bid' | 'pass' | 'pull' | 'steal' | 'dismiss'
            value: bid amount, rock count, or steal target depending on the action
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]

        if not playerId:
            return {"success": False, "message": "playerId is required"}
        if not action:
            return {"success": False, "message": "action is required"}

        challenge = game.get("challenge")
        if not challenge:
            return {"success": False, "message": "No Challenge is in progress"}

        if action == "dismiss":
            if challenge.get("phase") != "complete":
                return {"success": False, "message": "The Challenge is still in progress"}
            game["challenge"] = None
            self._save()
            return {"success": True, "message": "Challenge cleared"}

        result = challenge_engine.action(game, playerId, action, value)

        if result.get("success") and result.get("challengeWon"):
            reward_message = self._award_challenge_win(game, result["challengeWon"])
            result["message"] = f"{result.get('message', '')} {reward_message}".strip()
            result["reward"] = reward_message
            challenge_engine._log(game["challenge"], reward_message)

        if result.get("success"):
            self._save()

        return result

    def draw_card(self, gid, playerId=None, **kwargs):
        """
        Draw a card.

        Accepts ``draw_card(gid, playerId=...)`` or ``draw_card(gid, player_id)``.
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]
        player_id = playerId or kwargs.get('playerId')

        if not player_id:
            return {"success": False, "message": "playerId is required"}
        
        if player_id not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}
        
        player = game["players"][player_id]
        
        if player.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot draw cards"}

        if game.get("phase") != "playing":
            if game.get("phase") == "tribal_council":
                return {
                    "success": False,
                    "message": "You can't draw during a tribal council — the Tribe must speak first",
                }
            return {
                "success": False,
                "message": f"Cannot draw during the '{game.get('phase')}' phase",
            }

        # Validate it's this player's turn
        turn_order = game.get("turnOrder", [])
        current_index = game.get("currentTurnIndex", 0)
        if turn_order and turn_order[current_index] != player_id:
            return {"success": False, "message": "It's not your turn to draw"}

        blocked = self._challenge_block_reason(game)
        if blocked:
            return {"success": False, "message": blocked}

        # ── Enforce the official turn order: Steal → Play (optional) → Draw (F5) ──
        turn_phase = self.rules_engine.get_current_turn_phase(game, player_id)
        if turn_phase == "turn_steal":
            return {
                "success": False,
                "message": "You must steal a card first — your turn is Steal, then Play (optional), then Draw.",
            }
        # "End your turn by taking the top card from the Draw Pile." One draw,
        # and the turn is over.
        if player.get("hasDrawn"):
            return {
                "success": False,
                "message": "You already drew — drawing ends your turn. Tap End Turn.",
            }

        if game.get("pending_theft", {}).get("reactive_window_open"):
            return {
                "success": False,
                "message": "Your steal is still being resolved — wait for the reactive card window to close.",
            }

        deck = game.get("deck", [])
        if not deck:
            discard = game.get("discard") or []
            if discard:
                # The table would do exactly this: shuffle the Discard Pile into
                # a fresh Draw Pile (used Tribal Council Cards return with it,
                # which is what keeps the game finishable).
                random.shuffle(discard)
                game["deck"] = discard
                game["discard"] = []
                deck = game["deck"]
                # The official deck math guarantees Final Tribal before the pile
                # empties (the bottom card is always a Tribal Council Card). If
                # this fires, an elimination-count invariant broke somewhere —
                # keep the game alive, but shout about it.
                logger.error(f"INVARIANT: Draw Pile emptied mid-game in {gid} — "
                             f"reshuffled {len(deck)} discards to keep the game alive")
            else:
                # Nothing anywhere to draw — the draw step still ends the turn
                player["hasDrawn"] = True
                self._save()
                return {"success": True,
                        "message": "The Draw Pile is empty — your turn ends"}

        # Get number of cards to draw (including draw bonuses)
        draw_count = self.rules_engine.get_card_draw_count(player)
        
        drawn_cards = []      # resolved cards, for the response
        hand_cards = []       # the exact (compact) objects added to the hand
        tribal_triggered = False


        for _ in range(min(draw_count, len(deck))):
            if not deck:
                break
                
            drawn_card = deck.pop(0)
            resolved_card = self.rules_engine.resolve_card(drawn_card)
            
            # Check for tribal council card
            if resolved_card.get("category") == "tribal_council":
                tribal_triggered = True
                # Tribal cards trigger immediately when drawn, and per the rules the
                # player who drew the card becomes the Tribal Council Leader.
                self._trigger_tribal_council(
                    game,
                    resolved_card.get("elimination_type", "single"),
                    drawer_id=player_id,
                )
                drawn_cards.append(resolved_card)
                # Tribal cards are not added to hand - they trigger immediately
                break
            else:
                player["hand"].append(drawn_card)
                hand_cards.append(drawn_card)
                drawn_cards.append(resolved_card)

        # The one draw of the turn is spent — whether it was an Action Card or
        # the Tribal Council card that ends everything.
        player["hasDrawn"] = True

        # Process card draw effects (Camp Raid, etc.). This must be handed the exact
        # objects that went into the hand — passing the resolved copies meant the
        # "is this card still in their hand?" check never matched and Camp Raid
        # silently took nothing.
        if not tribal_triggered:
            self.rules_engine.process_card_draw_effects(game, player_id, hand_cards)

        self.rules_engine.sync_vote_counters(game)


        self._save()
        
        if tribal_triggered:
            return {
                "success": True,
                "message": f"Drew {resolved_card.get('name', 'Tribal Council')} - Tribal Council triggered!",
                "drawn_cards": drawn_cards,
                "tribal_triggered": True
            }
        else:
            card_names = [card.get("name", card.get("type", "unknown")) for card in drawn_cards]
            return {
                "success": True,
                "message": f"Drew {len(drawn_cards)} card(s): {', '.join(card_names)}",
                "drawn_cards": drawn_cards,
                "tribal_triggered": False
            }

    def advance_turn(self, gid, **kwargs):
        """Advance to next turn."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        
        if game.get("phase") != "playing":
            return {"success": False, "message": "Can only advance turns during playing phase"}

        blocked = self._challenge_block_reason(game)
        if blocked:
            return {"success": False, "message": blocked}

        turn_order = game.get("turnOrder", [])
        if not turn_order:
            return {"success": False, "message": "No turn order established"}

        current_index = game.get("currentTurnIndex", 0)

        # Finished Challenges / Reward Challenges are cleared at the end of the turn
        game["challenge"] = None
        game["interaction"] = None

        # Fresh turn for the next player: steal, one play, one draw
        for player in game["players"].values():
            player["hasStolen"] = False
            player["hasPlayed"] = False
            player["hasDrawn"] = False
        
        # Find next non-eliminated player
        original_index = current_index
        while True:
            current_index = (current_index + 1) % len(turn_order)
            next_player_id = turn_order[current_index]
            
            # Check if we've cycled through all players
            if current_index == original_index:
                # All players are eliminated - end game
                return {"success": False, "message": "All players eliminated"}
            
            # Check if this player is still active
            if next_player_id in game["players"] and not game["players"][next_player_id].get("isEliminated", False):
                break
        
        # Update game state
        game["currentTurnIndex"] = current_index
        current_player = game["players"][turn_order[current_index]]
        
        # Check for end game condition (2 or fewer players remaining)
        active_players = [p for p in game["players"].values() if not p.get("isEliminated", False)]
        if len(active_players) <= 2:
            # Trigger final tribal council
            game["phase"] = "final"
            game["finalTribal"] = {
                "phase": "waiting",
                "finalists": [p["id"] for p in active_players],
                "voteCounts": {},
                "tieBreakNeeded": False,
                "tieBreakerLeader": None
            }
            self._save()
            return {
                "success": True,
                "message": "Final Tribal Council triggered!",
                "final_tribal": True,
                "finalists": [p.get("name", p["id"]) for p in active_players]
            }
        
        self._save()
        return {
            "success": True,
            "message": f"Turn advanced to {current_player.get('name', 'player')}",
            "current_player": current_player.get("name", turn_order[current_index]),
            "current_player_id": turn_order[current_index]
        }

    def record_winner(self, gid, winnerId=None, **kwargs):
        """Record game winner."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        if not winnerId:
            return {"success": False, "message": "winnerId is required"}
        
        game = self.games[gid]

        # House rule: a game with a computer player in it is practice, not
        # history — it never writes to the Hall of Fame.
        if any(p.get("isBot") for p in game["players"].values()):
            return {"success": False,
                    "message": "Games with computer players aren't recorded in the Hall of Fame"}

        # Validate winner exists
        if winnerId not in game["players"]:
            return {"success": False, "message": "Invalid winner ID"}
        
        winner = game["players"][winnerId]
        winner_name = winner.get("name", "Unknown Player")
        
        # Load existing winners
        winners = []
        if os.path.exists(self._WINNERS_FILE):
            try:
                with open(self._WINNERS_FILE, 'r') as f:
                    content = f.read().strip()
                    if content:
                        winners = json.loads(content)
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.error(f"Failed to load winners file: {e}")
                # Continue anyway - will create new file
        
        # Add new winner
        import datetime
        current_date = datetime.datetime.now().strftime('%Y-%m-%d')
        winner_entry = {
            "winner_name": winner_name,
            "date": current_date,
            "game_id": gid,
            "timestamp": time.time(),
            "id": uuid.uuid4().hex[:12]
        }
        winners.append(winner_entry)
        
        # Save winners file atomically
        temp_file = f"{self._WINNERS_FILE}.tmp.{uuid.uuid4().hex[:8]}"
        try:
            with open(temp_file, 'w') as f:
                json.dump(winners, f, indent=2)
            os.rename(temp_file, self._WINNERS_FILE)
            logger.info(f"Recorded winner: {winner_name} for game {gid}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to save winner: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            return {"success": False, "message": "Failed to save winner"}
        
        # Mark game as finished
        game["phase"] = "finished"
        game["winner"] = {
            "playerId": winnerId,
            "playerName": winner_name,
            "date": current_date
        }
        
        self._save()
        
        return {
            "success": True, 
            "message": f"Congratulations {winner_name}! Game completed and winner recorded.",
            "winner": winner_name,
            "winnerId": winnerId
        }

    def delete_game(self, gid, **kwargs):
        """
        Wipe a game out of existence and send everyone back to shore.

        Unlike reset_game (which keeps the tribe and returns them to the lobby),
        this removes the game entirely so a brand new one can be started. The
        socket broadcast in handle() tells every connected phone to clear its
        local state and go home.
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}

        game = self.games[gid]
        player_count = len(game.get("players", {}))
        names = [p.get("name", "?") for p in game.get("players", {}).values()]

        del self.games[gid]
        self._save()
        logger.info(f"Game {gid} wiped ({player_count} players: {', '.join(names)})")

        return {
            "success": True,
            "message": "The camp is struck — this game is gone.",
            "wiped": True,
            "gameId": gid,
            "playerCount": player_count,
        }

    def reset_game(self, gid, **kwargs):
        """Reset game to lobby state."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        
        # Reset game phase
        game["phase"] = "lobby"

        # Clear game-specific state
        game["deck"] = []
        game["currentTurnIndex"] = 0
        game["necklaceHolder"] = None
        game["challenge"] = None
        game["interaction"] = None
        game.pop("winner", None)
        game.pop("pendingTurnPlayerId", None)

        # Reset all player states
        for player in game["players"].values():
            player["hand"] = []
            player["isEliminated"] = False
            player["hasStolen"] = False
            player["hasPlayed"] = False
            player["hasDrawn"] = False
            player["hasVoted"] = False
            player["extraVotes"] = 0
            player["characterCards"] = 2
            player["immunityPlayed"] = False
            player.pop("inheritanceTarget", None)
            player.pop("campRaidedBy", None)
            player.pop("mustUseExtraVotes", None)
            
            # Clear all temporary flags and effects
            player.pop("immunityIdolProtection", None)
            player.pop("idolNullified", None)
            player.pop("immunityNullified", None)
            player.pop("temporaryImmunity", None)
            player.pop("voteStolen", None)
            player.pop("voteBanned", None)
        
        # Clear tribal council state
        if "currentVote" in game:
            del game["currentVote"]
        
        # Clear game history and jury
        game["gameHistory"] = []
        game["jury"] = []
        
        # Reset final tribal state
        game["finalTribal"] = {
            "phase": "waiting", "finalists": [],
            "voteCounts": {}, "tieBreakNeeded": False,
            "tieBreakerLeader": None
        }
        
        # Clear any pending operations
        if "pending_theft" in game:
            del game["pending_theft"]
        
        # Preserve turn order but reset to first player
        if game.get("turnOrder"):
            game["currentTurnIndex"] = 0
        
        # Keep the first player as council leader
        if game["turnOrder"]:
            first_player_id = game["turnOrder"][0]
            for player_id, player in game["players"].items():
                player["isCouncilLeader"] = (player_id == first_player_id)
        
        self._save()
        logger.info(f"Reset game {gid} to lobby state")
        
        active_players = [p.get("name", "Player") for p in game["players"].values() if p.get("isActive", True)]
        
        return {
            "success": True, 
            "message": f"Game reset to lobby state with {len(active_players)} players",
            "active_players": active_players
        }

    # ═══════════════════════════ Reactive Card Methods ═══════════════════════════
    def handle_reactive_card_play(self, gid, player_id, card_idx, theft_context):
        """Handle reactive card play during theft attempts."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        pending_theft = game.get("pending_theft")
        
        if not pending_theft or not pending_theft.get("reactive_window_open"):
            return {"success": False, "message": "No active theft to react to"}
        
        if player_id != pending_theft.get("targetId"):
            return {"success": False, "message": "Only the theft target can play reactive cards"}
        
        player = game["players"].get(player_id)
        if not player or player.get("isEliminated", False):
            return {"success": False, "message": "Invalid or eliminated player"}
        
        hand = player.get("hand", [])
        if card_idx < 0 or card_idx >= len(hand):
            return {"success": False, "message": "Invalid card index"}
        
        compact_card = hand[card_idx]
        card = self.rules_engine.resolve_card(compact_card)
        
        # Validate this is a reactive card
        if not card.get("reactive_only", False):
            return {"success": False, "message": "This is not a reactive card"}
        
        # Remove card from hand — it goes to the discard once the block lands
        played_card = hand.pop(card_idx)

        # Execute reactive interrupt
        thief_id = pending_theft.get("thiefId")
        interrupt_result = self.rules_engine.execute_reactive_interrupt(
            game, player_id, thief_id, card
        )
        
        if interrupt_result.get("success"):
            # The played Sorry For You goes face up on the Discard Pile
            game.setdefault("discard", []).append({"type": "sorry_for_you"})
            # Close reactive window (execute_reactive_interrupt may already have)
            game.pop("pending_theft", None)
            self._save()
            return {
                "success": True,
                "message": interrupt_result.get("message", "Theft blocked by reactive card"),
                "reactive_interrupt": True
            }
        else:
            # Put card back if interrupt failed
            hand.insert(card_idx, played_card)
            return {"success": False, "message": interrupt_result.get("message", "Reactive interrupt failed")}

    def complete_pending_theft(self, gid):
        """Complete a pending theft when target chooses not to play reactive cards."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        pending_theft = game.get("pending_theft")
        
        if not pending_theft or not pending_theft.get("reactive_window_open"):
            return {"success": False, "message": "No pending theft to complete"}
        
        thief_id = pending_theft.get("thiefId")
        target_id = pending_theft.get("targetId")
        resume = pending_theft.get("_resume")

        if resume:
            # A card-effect taking (Spy Shack, Alliance, Camp Raid, a Reward
            # Challenge...) — the victim declined, so the held take executes now.
            from rules_engine import execute_take_spec
            take_result = execute_take_spec(game, resume)
            game.pop("pending_theft", None)
            self.rules_engine.sync_vote_counters(game)
            self._save()
            return {"success": True,
                    "message": take_result.get("message", "The cards change hands")}

        # Legacy path: the turn-steal
        theft_result = self.rules_engine.execute_theft(game, thief_id, target_id)

        # Close reactive window (execute_theft may already have)
        game.pop("pending_theft", None)


        if theft_result.get("success"):
            stolen_cards = theft_result.get("stolen_cards", [])
            target_name = game["players"][target_id].get("name", "player")
            self._save()
            return {
                "success": True,
                "message": f"Stole {len(stolen_cards)} card(s) from {target_name}",
                "stolen_cards": stolen_cards
            }
        else:
            self._save()
            return {"success": False, "message": theft_result.get("message", "Theft failed")}

# ──────────────── route helper ────────────────
def safe_api_call(func):
    """Decorator for robust API error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API operation={func.__name__} error: {e}")
            return jsonify(success=False, message="Internal server error"), 500
    return wrapper

def emit_game_event(gid, event_type, data=None):
    """Emit a game event for the narrator system"""
    try:
        event_data = {
            'type': event_type,
            'timestamp': time.time()
        }
        if data:
            event_data.update(data)
        socketio.emit('game_event', event_data, to=gid)
    except Exception as e:
        logger.warning(f"Failed to emit game event: {e}")

def _emit_narrator_events(gid, action, request_data, game_before, game_after, result):
    """Emit rich game events for the narrator based on action type"""
    try:
        players = game_after.get('players', {})

        # Helper to get player name by ID
        def get_player_name(player_id):
            player = players.get(player_id)
            return player.get('name', 'Unknown') if player else 'Unknown'

        # Steal action
        if action == 'steal_card':
            thief_id = request_data.get('playerId')
            target_id = request_data.get('targetId')
            emit_game_event(gid, 'steal', {
                'thief': get_player_name(thief_id),
                'victim': get_player_name(target_id)
            })

        # Card play
        elif action == 'play_card':
            player_id = request_data.get('playerId')
            card_index = request_data.get('cardIndex')
            # Try to get card name from result or player's hand
            card_name = 'a card'
            if isinstance(result, dict) and result.get('cardName'):
                card_name = result.get('cardName')
            emit_game_event(gid, 'card_played', {
                'player': get_player_name(player_id),
                'card': card_name,
                'target': get_player_name(request_data.get('targetId')) if request_data.get('targetId') else None
            })

        # Vote cast
        elif action == 'cast_vote':
            voter_id = request_data.get('voterId')
            emit_game_event(gid, 'vote_cast', {
                'player': get_player_name(voter_id)
            })

        # Tribal council start (phase change to tribal)
        elif action == 'advance_tribal_phase':
            new_phase = request_data.get('phase')
            emit_game_event(gid, 'tribal_phase_change', {
                'phase': new_phase
            })

        # Play immunity idol
        elif action == 'play_immunity':
            player_id = request_data.get('playerId')
            emit_game_event(gid, 'immunity_played', {
                'player': get_player_name(player_id)
            })

        # Block immunity (nullifier)
        elif action == 'block_immunity':
            target_id = request_data.get('targetId')
            emit_game_event(gid, 'immunity_nullified', {
                'target': get_player_name(target_id)
            })

        # Vote reveal - check for elimination
        elif action == 'reveal_votes' or action == 'complete_tribal':
            # Check if someone was eliminated
            eliminated_before = {pid for pid, p in game_before.get('players', {}).items() if p.get('isEliminated')}
            eliminated_after = {pid for pid, p in players.items() if p.get('isEliminated')}
            newly_eliminated = eliminated_after - eliminated_before
            for pid in newly_eliminated:
                emit_game_event(gid, 'elimination', {
                    'player': get_player_name(pid),
                    'playerId': pid
                })

        # Game start
        elif action == 'start_game':
            player_count = len([p for p in players.values() if not p.get('isEliminated')])
            emit_game_event(gid, 'game_start', {
                'count': player_count
            })

        # Winner recorded
        elif action == 'record_winner':
            winner_id = request_data.get('winnerId')
            emit_game_event(gid, 'winner', {
                'player': get_player_name(winner_id),
                'playerId': winner_id
            })

        # Check for phase changes
        old_phase = game_before.get('phase')
        new_phase = game_after.get('phase')
        if old_phase != new_phase and new_phase:
            if new_phase.startswith('tribal') and not old_phase.startswith('tribal'):
                emit_game_event(gid, 'tribal_start', {})

    except Exception as e:
        logger.warning(f"Error emitting narrator event for {action}: {e}")

def handle(action, required):
    """Enhanced request handler with better error handling"""
    try:
        d = request.get_json(silent=True)
        if d is None:
            logger.warning("Invalid JSON in request")
            return jsonify(success=False, message="Invalid JSON data"), 400

        gid = d.get('gameId')
        if not gid:
            logger.warning("Missing gameId in request")
            return jsonify(success=False, message="gameId missing"), 400

        if not isinstance(gid, str) or len(gid) > 20:
            logger.warning(f"Invalid gameId format: {gid}")
            return jsonify(success=False, message="Invalid gameId format"), 400

        if gid not in game_state.games:
            logger.warning(f"Game {gid} not found")
            return jsonify(success=False, message="Game not found"), 404

        missing_fields = [k for k in required if k not in d]
        if missing_fields:
            logger.warning(f"Missing required fields: {missing_fields}")
            return jsonify(success=False, message=f"Missing fields: {', '.join(missing_fields)}"), 400

        kwargs = {k: v for k, v in d.items() if k != 'gameId'}

        # Get game state before action for comparison
        game_before = game_state.games.get(gid, {}).copy() if gid in game_state.games else {}

        try:
            if not hasattr(game_state, action):
                logger.error(f"Unknown action: {action}")
                return jsonify(success=False, message="Invalid action"), 400

            result = getattr(game_state, action)(gid, **kwargs)
            
        except Exception as e:
            gid = d.get('gameId', 'unknown')
            logger.error(f"API operation={action} gameId={gid} error: {e}")
            error_msg = f"Operation {action} failed: {str(e)}"
            return jsonify(success=False, message=error_msg), 500
    
        if isinstance(result, dict):
            if "success" in result:
                if not result.get("success", False):
                    logger.warning(f"Action '{action}' failed: {result.get('message', 'Operation completed')}")
                    return jsonify(success=False, message=result.get('message', 'Operation completed')), 400
            
        elif result is False:
            logger.warning(f"Action '{action}' returned False for game {gid}")
            return jsonify(success=False, message=f"Action '{action}' could not be completed."), 400
        elif result is None:
            logger.warning(f"Action '{action}' returned None for game {gid}")
            return jsonify(success=False, message=f"Action '{action}' failed - invalid request"), 400

        try:
            if action == 'delete_game':
                # The game no longer exists — tell every phone in the room to
                # clear local state and return to the start screen.
                socketio.emit('game_wiped', {'gameId': gid}, to=gid)
            elif action in ['reset_game', 'record_winner']:
                socketio.emit('game_reset', {'gameId': gid}, to=gid)
                socketio.emit('global_reset', {'gameId': gid})
            else:
                game_data = game_state.get_game_state(gid) or {}
                socketio.emit('state_update', game_data, to=gid)

                # Emit specific game events for narrator
                game_after = game_state.games.get(gid, {})
                _emit_narrator_events(gid, action, d, game_before, game_after, result)

        except Exception as e:
            logger.error(f"Socket operation=state_update gameId={gid} error: {e}")

        # A state change may put a bot on the clock
        if bot_runner:
            try:
                bot_runner.poke(gid)
            except Exception as e:
                logger.error(f"Bot poke failed for {gid}: {e}")

        response_data = {"success": True}
        if isinstance(result, dict):
            response_data.update(result)
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error in handle(): {e}")
        return jsonify(success=False, message="Internal server error"), 500

# ───────────────────────────── Flask Routes ─────────────────────────────
@app.route("/")
def index():
    # Serve optimized version if available, fallback to original
    optimized_path = os.path.join(app.static_folder, "index-optimized.html")
    if os.path.exists(optimized_path):
        logger.info("Serving optimized version")
        return send_from_directory(app.static_folder, "index-optimized.html")
    else:
        logger.info("Serving original version (optimized version not found)")
        return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def spa_fallback(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    # Return optimized version for SPA fallback
    optimized_path = os.path.join(app.static_folder, "index-optimized.html")
    if os.path.exists(optimized_path):
        return send_from_directory(app.static_folder, "index-optimized.html")
    return send_from_directory(app.static_folder, "index.html")

# ───────────────────────────── Access Gate ─────────────────────────────
@app.before_request
def enforce_access_gate():
    """
    When SURVIVOR_ACCESS_CODE is set, every API call needs the access cookie.

    Pages and static assets stay fetchable (they hold no game data — the client
    shows its own gate screen), and the gate endpoints themselves are exempt so
    the code can actually be entered.
    """
    if not gate_enabled():
        return None
    path = request.path
    if not path.startswith('/api/') or path in _ACCESS_EXEMPT_PATHS:
        return None
    if _has_valid_access_cookie(request.cookies):
        return None
    return jsonify(success=False, gated=True,
                   message="This island is code-locked — enter the access code first"), 401


@app.route('/api/access/check', methods=['GET'])
@safe_api_call
def api_access_check():
    """Is the gate up, and does this browser already hold a valid cookie?"""
    return jsonify(
        success=True,
        gated=gate_enabled(),
        ok=_has_valid_access_cookie(request.cookies),
    )


@app.route('/api/access', methods=['POST'])
@safe_api_call
def api_access():
    """Trade the shared access code for the signed access cookie."""
    if not gate_enabled():
        return jsonify(success=True, message="No access code is required")

    ip = _client_ip()
    if _access_rate_limited(ip):
        logger.warning(f"Access gate rate limit hit from {ip}")
        return jsonify(success=False,
                       message="Too many attempts — wait a minute and try again"), 429

    data = request.get_json(silent=True) or {}
    supplied = str(data.get('code', '')).strip()

    if not supplied or not hmac.compare_digest(supplied.lower(), ACCESS_CODE.lower()):
        logger.warning(f"Access gate: wrong code from {ip}")
        return jsonify(success=False, message="That's not the code. The island stays hidden."), 403

    response = jsonify(success=True, message="Welcome ashore")
    forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
    response.set_cookie(
        ACCESS_COOKIE, _access_token(),
        max_age=ACCESS_COOKIE_MAX_AGE,
        httponly=True,
        samesite='Lax',
        secure=(forwarded_proto == 'https'),
    )
    logger.info(f"Access gate: code accepted for {ip}")
    return response


# ───────────────────────────── REST API ─────────────────────────────
@app.route('/api/ping', methods=['GET'])
@safe_api_call
def api_ping():
    """Health check endpoint"""
    return jsonify(
        success=True, 
        timestamp=time.time(),
        server_info={
            'games_active': len(game_state.games),
            'uptime': time.time() - start_time if 'start_time' in globals() else 0
        }
    )

@app.route('/api/cards', methods=['GET'])
@safe_api_call
def get_card_definitions():
    """Get card definitions from rules engine"""
    response = jsonify(game_state.rules_engine.card_definitions)
    # Set cache headers for static card definitions
    response.headers['Cache-Control'] = 'public, max-age=3600'
    response.headers['ETag'] = 'cards-v1.0.0'
    return response

@app.route('/api/game/<game_id>/state', methods=['GET'])
@safe_api_call
def api_game_state(game_id):
    """Get current game state (for state synchronization)"""
    if game_id not in game_state.games:
        return jsonify(success=False, message="Game not found"), 404
    
    current_state = game_state.get_game_state(game_id)
    response = jsonify(current_state)

    # Live game state must never be reused from any cache — not the browser's, not
    # the service worker's, and not Cloudflare's. The previous headers advertised
    # `no-cache` alongside a per-second ETag, which let clients serve a stale board
    # to a reconnecting phone (exactly the resync path this route exists for).
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers.pop('ETag', None)

    return response

@app.route('/api/batch', methods=['POST'])
@safe_api_call
def api_batch():
    """Handle batched API requests for performance optimization"""
    try:
        data = request.get_json()
        operations = data.get('operations', [])
        results = []
        
        for operation in operations:
            try:
                # Execute each operation (simplified implementation)
                endpoint = operation.get('endpoint', '')
                method = operation.get('method', 'POST')
                op_data = operation.get('data', {})
                
                # Route to appropriate handler based on endpoint
                # This is a simplified implementation - in production you'd
                # want more sophisticated routing
                if endpoint == '/turn/advance':
                    result = game_state.advance_turn(op_data.get('gameId'))
                elif endpoint == '/turn/draw':
                    result = game_state.draw_card(op_data.get('gameId'), op_data.get('playerId'))
                else:
                    result = {"success": False, "message": "Unsupported batch operation"}
                
                results.append({
                    "operation": operation,
                    "result": result
                })
                
            except Exception as e:
                results.append({
                    "operation": operation,
                    "result": {"success": False, "message": str(e)}
                })
        
        return jsonify({"success": True, "results": results})
        
    except Exception as e:
        logger.error(f"Batch API error: {e}")
        return jsonify({"success": False, "message": "Batch processing failed"}), 500

@app.route('/api/winners', methods=['GET'])
@safe_api_call
def get_winners():
    """Get winners list with robust error handling"""
    winners_list = []
    
    if os.path.exists(GameState._WINNERS_FILE):
        try:
            with open(GameState._WINNERS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    winners_list = json.loads(content)
                else:
                    logger.info("Empty winners file")
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Failed to load winners file: {e}")
            return jsonify([])

    try:
        aggregated = {}
        for win in winners_list:
            if not isinstance(win, dict):
                logger.warning(f"Invalid winner entry: {win}")
                continue
                
            name = win.get("winner_name")
            if not name or not isinstance(name, str):
                logger.warning(f"Invalid winner name in entry: {win}")
                continue
                
            if name not in aggregated:
                aggregated[name] = {"winner_name": name, "victories": 0, "dates": []}
            aggregated[name]["victories"] += 1
            
            date = win.get("date")
            if date:
                aggregated[name]["dates"].append(date)
        
        for name in aggregated:
            aggregated[name]["dates"].sort(reverse=True)
            
        return jsonify(list(aggregated.values()))
        
    except Exception as e:
        logger.error(f"Error processing winners data: {e}")
        return jsonify([])

@app.route('/api/winners/add', methods=['POST'])
@safe_api_call
def add_winner():
    """Add winner with comprehensive validation and error handling"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify(success=False, message="Invalid JSON data"), 400
        
    winner_name = data.get('winner_name', '').strip()
    date = data.get('date', '').strip()

    if not winner_name:
        return jsonify(success=False, message="Winner name is required"), 400
    if len(winner_name) > 50:
        return jsonify(success=False, message="Winner name too long"), 400
        
    if not date:
        return jsonify(success=False, message="Date is required"), 400
        
    try:
        time.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify(success=False, message="Invalid date format (use YYYY-MM-DD)"), 400

    winners = []
    if os.path.exists(GameState._WINNERS_FILE):
        try:
            with open(GameState._WINNERS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    winners = json.loads(content)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Failed to load winners file: {e}")
            return jsonify(success=False, message="Failed to load existing winners"), 500
    
    winners.append({
        "winner_name": winner_name,
        "date": date,
        "game_id": "manual_entry",
        "id": uuid.uuid4().hex[:12]
    })
    
    temp_file = f"{GameState._WINNERS_FILE}.tmp"
    try:
        with open(temp_file, 'w') as f:
            json.dump(winners, f, indent=2)
        
        if os.path.exists(GameState._WINNERS_FILE):
            os.remove(GameState._WINNERS_FILE)
        os.rename(temp_file, GameState._WINNERS_FILE)
        
        logger.info(f"Added winner: {winner_name} on {date}")
        return jsonify(success=True)
        
    except (IOError, OSError, TypeError, ValueError) as e:
        logger.error(f"Failed to save winner: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass
        return jsonify(success=False, message="Failed to save winner"), 500


def _read_winner_records():
    """Load the raw win records, giving any legacy record a stable id.

    Older records (and ones written by record_winner) have no id; editing
    needs one, so ids are minted on first read and persisted immediately.
    """
    records = []
    if os.path.exists(GameState._WINNERS_FILE):
        try:
            with open(GameState._WINNERS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    records = json.loads(content)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Failed to load winners file: {e}")
            return None
    if not isinstance(records, list):
        return None

    changed = False
    for rec in records:
        if isinstance(rec, dict) and not rec.get("id"):
            rec["id"] = uuid.uuid4().hex[:12]
            changed = True
    if changed:
        _write_winner_records(records)
    return records


def _write_winner_records(records):
    """Atomically replace the winners file."""
    temp_file = f"{GameState._WINNERS_FILE}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(temp_file, 'w') as f:
            json.dump(records, f, indent=2)
        os.rename(temp_file, GameState._WINNERS_FILE)
        return True
    except (IOError, OSError) as e:
        logger.error(f"Failed to write winners file: {e}")
        try:
            os.remove(temp_file)
        except OSError:
            pass
        return False


def _validate_winner_fields(data):
    """Shared validation for editing win records. Returns (name, date, error)."""
    name = str(data.get('winner_name', '')).strip()
    date = str(data.get('date', '')).strip()
    if not name:
        return None, None, "Winner name is required"
    if len(name) > 50:
        return None, None, "Winner name too long"
    if not date:
        return None, None, "Date is required"
    try:
        time.strptime(date, '%Y-%m-%d')
    except ValueError:
        return None, None, "Invalid date format (use YYYY-MM-DD)"
    return name, date, None


@app.route('/api/winners/records', methods=['GET'])
@safe_api_call
def get_winner_records():
    """The raw, editable win records — one entry per victory."""
    records = _read_winner_records()
    if records is None:
        return jsonify(success=False, message="Failed to load winners"), 500
    return jsonify(records)


@app.route('/api/winners/update', methods=['POST'])
@safe_api_call
def update_winner():
    """Edit one win record (name and/or date) by id."""
    data = request.get_json(silent=True)
    if not data or not data.get('id'):
        return jsonify(success=False, message="Record id is required"), 400
    name, date, error = _validate_winner_fields(data)
    if error:
        return jsonify(success=False, message=error), 400

    records = _read_winner_records()
    if records is None:
        return jsonify(success=False, message="Failed to load winners"), 500

    for rec in records:
        if isinstance(rec, dict) and rec.get("id") == data['id']:
            rec["winner_name"] = name
            rec["date"] = date
            if not _write_winner_records(records):
                return jsonify(success=False, message="Failed to save winners"), 500
            logger.info(f"Winner record {data['id']} updated: {name} on {date}")
            return jsonify(success=True, message=f"Updated — {name}, {date}")

    return jsonify(success=False, message="Record not found"), 404


@app.route('/api/winners/delete', methods=['POST'])
@safe_api_call
def delete_winner():
    """Remove one win record by id."""
    data = request.get_json(silent=True)
    if not data or not data.get('id'):
        return jsonify(success=False, message="Record id is required"), 400

    records = _read_winner_records()
    if records is None:
        return jsonify(success=False, message="Failed to load winners"), 500

    kept = [r for r in records if not (isinstance(r, dict) and r.get("id") == data['id'])]
    if len(kept) == len(records):
        return jsonify(success=False, message="Record not found"), 404
    if not _write_winner_records(kept):
        return jsonify(success=False, message="Failed to save winners"), 500
    logger.info(f"Winner record {data['id']} deleted")
    return jsonify(success=True, message="The record is struck from the island's history")


@app.route('/api/game/create',methods=['POST'])
@safe_api_call
def api_create():
    """
    Create new game with error handling.

    Optional JSON body:
        deckMode:  "official" (default, the 67-card box) | "extended" (+7 house cards)
        expansion: true to add the 5 Orange Challenge Cards from Let's Go To Rocks
    """
    try:
        d = request.get_json(silent=True) or {}
        game_id = game_state.create_game(
            deckMode=d.get('deckMode'),
            expansion=d.get('expansion'),
        )
        if not game_id:
            return jsonify(success=False, message="Failed to create game"), 500
        game = game_state.games[game_id]
        logger.info(
            f"Created new game: {game_id} (deckMode={game['deckMode']}, expansion={game['expansion']})"
        )
        return jsonify(
            gameId=game_id,
            success=True,
            deckMode=game['deckMode'],
            expansion=game['expansion'],
        )
    except Exception as e:
        logger.error(f"Failed to create game: {e}")
        return jsonify(success=False, message="Game creation failed"), 500

@app.route('/api/player/join',methods=['POST'])
def api_join():
    d=request.get_json(silent=True) or {}
    gid = d.get('gameId')
    if not gid or gid not in game_state.games:
        return jsonify(success=False, message="Game not found or has ended."), 404

    name = d.get('name', '').strip()
    check = game_state.validate_new_player(gid, name, d.get('color'))
    if not check["success"]:
        return jsonify(success=False, message=check["message"]), 400

    pid=game_state.add_player(gid, name, d.get('color'))
    if not pid: return jsonify(success=False,message="Failed to add player."),400

    # Emit narrator event for player joining
    g = game_state.games[gid]
    emit_game_event(gid, 'player_joined', {
        'player': name,
        'count': len(g['players'])
    })

    socketio.emit('state_update',game_state.get_game_state(gid),to=gid)
    return jsonify(success=True,playerId=pid,gameState=game_state.get_game_state(gid))

@app.route('/api/player/rejoin',methods=['POST'])
def api_rejoin():
    d=request.get_json(silent=True) or {}
    gid = d.get('gameId')
    pid = d.get('playerId')
    if not game_state.reconnect_player(gid, pid):
        return jsonify(success=False,message="Could not reconnect. Invalid game or player ID."),400
    g=game_state.games[gid]
    return jsonify(success=True,gameState=g,playerName=g["players"][pid]["name"])

@app.route('/api/vote/start',methods=['POST'])
def api_start():   return handle('start_voting',['voteType'])
@app.route('/api/vote/cast',methods=['POST'])
def api_cast():    return handle('cast_vote',['voterId','votesData'])
@app.route('/api/immunity/play',methods=['POST'])
def api_imm():     return handle('play_immunity',['playerId'])
@app.route('/api/immunity/block',methods=['POST'])
def api_block():   return handle('block_immunity',['targetId'])
@app.route('/api/vote/reveal',methods=['POST'])
def api_reveal():  return handle('reveal_votes',[])
@app.route('/api/vote/tiebreak',methods=['POST'])
def api_tb():      return handle('tie_break',['leaderId','chosenId'])
@app.route('/api/tribal/complete',methods=['POST'])
def api_done():    return handle('complete_tribal',[])
@app.route('/api/game/reset',methods=['POST'])
def api_reset():   return handle('reset_game',[])
@app.route('/api/game/delete',methods=['POST'])
def api_delete():  return handle('delete_game',[])
@app.route('/api/player/rename',methods=['POST'])
def api_rename():  return handle('rename_player',['playerId','newName'])
@app.route('/api/player/add_bot',methods=['POST'])
def api_add_bot():    return handle('add_bot',[])
@app.route('/api/player/remove_bot',methods=['POST'])
def api_remove_bot(): return handle('remove_bot',['playerId'])
@app.route('/api/game/finish',methods=['POST'])
def api_finish():  return handle('record_winner',['winnerId'])
@app.route('/api/tribal/reset',methods=['POST'])
def api_tribal_reset(): return handle('reset_tribal_council',[])

# New Tribal Council API endpoints
@app.route('/api/tribal/advance',methods=['POST'])
def api_advance_tribal(): return handle('advance_tribal_phase',['phase'])
@app.route('/api/tribal/advantage',methods=['POST'])  
def api_tribal_advantage(): return handle('play_tribal_advantage',['playerId','advantageType','targetId'])
@app.route('/api/tribal/tie_enhanced',methods=['POST'])
def api_enhanced_tie_break(): return handle('enhanced_tie_break',['leaderId','chosenIds'])

# Let's Go To Rocks expansion — Challenge actions
@app.route('/api/challenge/action',methods=['POST'])
def api_challenge_action(): return handle('challenge_action',['playerId','action'])

# Reward Challenge interactions (Do Or Die / Power Pair / Numbers Game)
@app.route('/api/interaction/act',methods=['POST'])
def api_interaction_act(): return handle('interaction_action',['playerId','action'])

# Final Tribal Council API endpoints
@app.route('/api/final/advance',methods=['POST'])
def api_advance_final(): return handle('advance_final_phase',['phase'])
@app.route('/api/final/vote',methods=['POST'])
def api_final_vote(): return handle('cast_final_vote',['juryMemberId','finalistId'])
@app.route('/api/final/tie_break',methods=['POST']) 
def api_final_tie_break(): return handle('break_final_tie',['leaderId','chosenWinner'])
@app.route('/api/final/ready',methods=['POST'])
def api_jury_ready(): return handle('signal_jury_ready',['juryMemberId'])

@app.route('/api/leader/change',methods=['POST'])
def api_leader():  return handle('change_leader',['newLeaderId'])

@app.route('/api/game/start_full',methods=['POST'])
def api_start_full():  return handle('start_full_game',[])

@app.route('/api/turn/steal',methods=['POST'])
def api_steal():  return handle('steal_card',['thiefId','targetId'])

@app.route('/api/turn/play_card',methods=['POST'])
def api_play_card():  return handle('play_card',['playerId','cardIdx'])

@app.route('/api/turn/draw',methods=['POST'])
def api_draw():  return handle('draw_card',['playerId'])

@app.route('/api/turn/advance',methods=['POST'])
def api_advance():  return handle('advance_turn',[])

@app.route('/api/reactive/play_card',methods=['POST'])
def api_reactive_play():
    """Handle reactive card plays during theft attempts"""
    data = request.get_json()
    if not data:
        return {"success": False, "message": "No data provided"}, 400
    
    game_id = data.get('gameId')
    player_id = data.get('playerId')
    card_idx = data.get('cardIdx')
    theft_context = data.get('theftContext', {})
    
    if not all([game_id, player_id, isinstance(card_idx, int)]):
        return {"success": False, "message": "Missing required parameters"}, 400
    
    try:
        result = game_state.handle_reactive_card_play(game_id, player_id, card_idx, theft_context)
        if result.get("success"):
            socketio.emit('game_updated', game_state.get_game_state(game_id), room=game_id)
        return result
    except Exception as e:
        logger.error(f"Reactive card play error: {e}")
        return {"success": False, "message": "Reactive card play failed"}, 500

@app.route('/api/reactive/complete_theft',methods=['POST'])
def api_complete_theft():
    """Complete a pending theft when target chooses not to play reactive cards"""
    data = request.get_json()
    if not data:
        return {"success": False, "message": "No data provided"}, 400
    
    game_id = data.get('gameId')
    if not game_id:
        return {"success": False, "message": "Game ID required"}, 400
    
    try:
        result = game_state.complete_pending_theft(game_id)
        if result.get("success"):
            socketio.emit('game_updated', game_state.get_game_state(game_id), room=game_id)
        return result
    except Exception as e:
        logger.error(f"Complete theft error: {e}")
        return {"success": False, "message": "Complete theft failed"}, 500

# ────────────────────────── Socket.IO events ───────────────────────
@socketio.on('join')
def on_join(data):
    """Handle client join with error handling"""
    try:
        if not data or not isinstance(data, dict):
            logger.warning(f"Invalid join data from {request.sid}")
            emit('error', {'message': 'Invalid join data'})
            return
            
        gid = data.get('gameId')
        if not gid:
            logger.warning(f"Missing gameId in join from {request.sid}")
            emit('error', {'message': 'Game ID required'})
            return
            
        if gid not in game_state.games:
            logger.warning(f"Join attempt for non-existent game {gid} from {request.sid}")
            emit('error', {'message': 'Game not found'})
            return
        
        join_room(gid)
        game_data = game_state.get_game_state(gid) or {}
        emit('state_update', game_data)
        logger.debug(f"Client {request.sid} joined game {gid}")
        
    except Exception as e:
        gid = data.get('gameId', 'unknown')
        logger.error(f"Socket operation=join gameId={gid} error: {e}")
        emit('error', {'message': 'Join failed'})

@socketio.on('disconnect')
def on_disconnect(reason=None):
    """Handle client disconnect with logging. python-socketio passes a reason."""
    logger.debug(f"Client disconnected: {request.sid} ({reason or 'no reason given'})")

@socketio.on('connect')
def on_connect():
    """
    Handle client connect. When the access gate is up, the websocket handshake
    must carry the access cookie — refusing here keeps ungated clients from
    receiving state_update broadcasts.
    """
    if gate_enabled() and not _has_valid_access_cookie(request.cookies):
        logger.warning(f"Socket connection refused by access gate: {request.sid}")
        return False
    logger.debug(f"Client connected: {request.sid}")

@socketio.on('heartbeat')
def on_heartbeat(data=None):
    """
    Handle heartbeat to keep WebSocket connection alive through Cloudflare.

    The client emits ('heartbeat', {t: <perf.now()>}, ack). Returning a value from
    the handler sends it back as the ack, which is what the client's RTT
    measurement waits on — so the signature must accept the payload (F6).
    """
    echo = data.get('t') if isinstance(data, dict) else None
    return {'status': 'ok', 'timestamp': time.time(), 't': echo}

@socketio.on_error_default
def default_error_handler(e):
    """Handle socket errors"""
    logger.error(f"Socket.IO error from {request.sid}: {e}")
    emit('error', {'message': 'Connection error occurred'})

# ─────────────────────────────── Main ──────────────────────────────
def get_local_ip():
    """Get local IP with robust error handling for iOS"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            logger.info(f"Detected local IP: {ip}")
            return ip
    except Exception as e:
        logger.warning(f"Failed to detect IP via socket: {e}")
    
    try:
        import subprocess
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            ip = result.stdout.strip().split()[0]
            logger.info(f"Detected IP via hostname: {ip}")
            return ip
    except Exception as e:
        logger.warning(f"Failed to detect IP via hostname: {e}")
    
    logger.warning("Using fallback IP 127.0.0.1")
    return '127.0.0.1'

def find_available_port(start_port=8080, max_attempts=10):
    """Find an available port starting from start_port"""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                logger.info(f"Found available port: {port}")
                return port
        except OSError:
            continue
    
    logger.error(f"No available ports found in range {start_port}-{start_port + max_attempts}")
    return None

def cleanup_handler(signum, frame):
    """Graceful shutdown handler"""
    logger.info("Shutting down gracefully...")
    try:
        game_state._save()
        logger.info("Game state saved before shutdown")
    except Exception as e:
        logger.error(f"Failed to save state during shutdown: {e}")
    sys.exit(0)
    
@app.errorhandler(Exception)
def handle_unhandled_exception(e):
    """
    Global handler for unhandled exceptions to prevent bare 500 errors.

    HTTP errors (404 Not Found, 405 Method Not Allowed, ...) are passed through
    with their real status code — swallowing them into 500s made every client-side
    routing mistake look like a server crash.
    """
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        logger.warning(f"HTTP {e.code} on {request.method} {request.path}: {e.name}")
        return jsonify(success=False, message=f"{e.code} {e.name}"), e.code

    logger.error(f"Unhandled Exception: {e}", exc_info=True)
    return jsonify(success=False, message=f"An internal server error occurred: {str(e)}"), 500


# ── Computer players ─────────────────────────────────────────────────────────
# The runner is created at server startup (game_state doesn't exist on import);
# everything here tolerates bot_runner being None so test imports are unaffected.
bot_runner = None

def _bot_broadcast(gid, action):
    """Bots act outside any request context — push fresh state to the room."""
    game_data = game_state.get_game_state(gid) or {}
    socketio.emit('state_update', game_data, to=gid)

def _bot_spawn_later(delay, fn, *args):
    def _run():
        socketio.sleep(delay)
        fn(*args)
    socketio.start_background_task(_run)

def _bot_heartbeat_loop():
    """Backstop: every couple of seconds the bots look at their games. The
    poke-after-action path makes them responsive; this makes them unstoppable."""
    while True:
        socketio.sleep(2)
        try:
            bot_runner.heartbeat()
        except Exception as e:
            logger.error(f"Bot heartbeat error: {e}")


if __name__=='__main__':
    import signal
    signal.signal(signal.SIGTERM, cleanup_handler)
    signal.signal(signal.SIGINT, cleanup_handler)
    
    if '--clean' in sys.argv:
        try:
            if os.path.exists(GameState._FILE):
                os.remove(GameState._FILE)
                print(f"'{GameState._FILE}' deleted. Starting with a fresh game state.")
        except OSError as e:
            print(f"Warning: Could not delete {GameState._FILE}: {e}")
    
    import gc
    gc.collect()
    
    try:
        start_time = time.time()
        game_state = GameState()
        bot_runner = BotRunner(game_state, broadcast=_bot_broadcast)
        bot_runner.attach(_bot_spawn_later)
        socketio.start_background_task(_bot_heartbeat_loop)
        IP = get_local_ip()
        port = int(os.environ.get('PORT', 0)) or find_available_port()
        
        if not port:
            print("Error: Could not find an available port. Please check network settings.")
            sys.exit(1)

        app.config['RUNNING_PORT'] = port
        
        print("="*50)
        print("🏝️  Survivor Voting Server")
        print("="*50)
        print(f"🌐 Server starting on: http://{IP}:{port}")
        print(f"📱 Find your device's Wi-Fi IP in Settings to connect.")
        print(f"🔧 Debug mode: {app.debug}")
        print("="*50)
        
        print("🚀 Starting server... (Press Ctrl+C to stop)\n")
        
        socketio.run(
            app,
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
            log_output=True
        )
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error starting server: {e}")
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)
    finally:
        try:
            game_state._save()
            logger.info("Final game state saved")
        except Exception as e:
            logger.error(f"Failed to save final state: {e}")
