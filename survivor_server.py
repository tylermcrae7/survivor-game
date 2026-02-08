#!/usr/bin/env python3
# Survivor Voting App – Flask & Socket.IO
# (Pythonista-friendly; persistence, extra-vote cards, leader swap, reset)

import uuid, time, os, json, socket, re, sys, threading
import logging
from pathlib import Path
from functools import wraps
from rules_engine import SurvivorRulesEngine, TribalPhase

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
        """Atomically saves the current game state to a JSON file."""
        temp_file = f"{self._FILE}.tmp.{uuid.uuid4().hex[:8]}"
        try:
            current_time = time.time()
            for game in self.games.values():
                game['lastActivity'] = current_time
            with open(temp_file, 'w') as f:
                json.dump(self.games, f, indent=2)
            os.rename(temp_file, self._FILE)
            logger.debug("Game state saved successfully")
        except Exception as e:
            logger.error(f"GameState save error: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError as cleanup_error:
                    logger.warning(f"Could not clean up temp file {temp_file}: {cleanup_error}")
            raise

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
            self.games = json.loads(content)
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

    def create_game(self):
        """Creates a new game with a unique ID."""
        gid = str(uuid.uuid4())[:8]
        self.games[gid] = {
            'id': gid, 'players': {}, 'turnOrder': [], 'currentTurnIndex': 0,
            'phase': 'lobby', 'deck': [], 'createdAt': time.time(),
            'lastActivity': time.time(),
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
    
    def add_player(self, gid, name, color=None):
        """Adds a new player to a game."""
        g = self.games.get(gid)
        if not g: return None
        
        if color is None:
            colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#F9844A", "#90BE6D", "#F9C74F"]
            used_colors = {p.get("color") for p in g["players"].values()}
            color = next((c for c in colors if c not in used_colors), "#8B5CF6")
        
        player_id = str(uuid.uuid4())[:8]
        g['players'][player_id] = {
            'id': player_id, 'name': name, 'color': color, 'hand': [],
            'isEliminated': False, 'hasStolen': False, 'hasVoted': False, 'extraVotes': 0,
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
    
    def start_full_game(self, gid):
        """Starts a full game, creating the deck and dealing cards."""
        g = self.games.get(gid)
        if not g or g.get("phase") != "lobby" or len(g["players"]) < 3:
            return {"success": False, "message": "Game cannot be started."}
        
        g["deck"] = self.rules_engine.create_deck(len(g["players"]))
        for player in g["players"].values():
            for _ in range(5):
                if g["deck"]: player["hand"].append(g["deck"].pop(0))
        
        g["phase"] = "playing"
        self._save()
        return {"success": True, "message": "Game started!"}
    
    def get_game_state(self, gid):
        """Returns the complete state of a game."""
        game = self.games.get(gid)
        if not game: return None
        import copy
        enriched_game = copy.deepcopy(game)
        # Add any derived state for the client here
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
            
        if not votesData:
            return {"success": False, "message": "Vote data required"}
            
        game = self.games[gid]
        current_vote = game.get("currentVote")
        
        if not current_vote or current_vote.get("phase") != "voting":
            return {"success": False, "message": "Voting is not currently active"}
            
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
            
        # Calculate total votes this player can cast
        base_votes = 1
        extra_votes = voter.get("extraVotes", 0)
        total_votes_available = base_votes + extra_votes
        
        # Validate vote data format
        if not isinstance(votesData, list):
            return {"success": False, "message": "Vote data must be a list"}
            
        total_votes_cast = sum(vote.get("votes", 0) for vote in votesData)
        if total_votes_cast > total_votes_available:
            return {"success": False, "message": f"Cannot cast {total_votes_cast} votes - only {total_votes_available} available"}
            
        # Validate all targets are valid and not immune
        vote_targets = {}
        for vote in votesData:
            target_id = vote.get("targetId")
            vote_count = vote.get("votes", 0)
            
            if not target_id or target_id not in game["players"]:
                return {"success": False, "message": f"Invalid vote target: {target_id}"}
                
            target = game["players"][target_id]
            if target.get("isEliminated", False):
                return {"success": False, "message": f"Cannot vote for eliminated player: {target.get('name', target_id)}"}
                
            # Accumulate votes for same target
            vote_targets[target_id] = vote_targets.get(target_id, 0) + vote_count
            
        # Record the votes
        current_vote["votes"][voterId] = vote_targets
        voter["hasVoted"] = True
        
        # Use up extra votes
        if extra_votes > 0:
            voter["extraVotes"] = max(0, voter["extraVotes"] - (total_votes_cast - base_votes))
            
        self._save()
        logger.info(f"Player {voterId} cast {total_votes_cast} votes in game {gid}")
        
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
            
        if current_vote.get("phase") != "voting":
            return {"success": False, "message": "Voting must be in progress to reveal votes"}
            
        # Advance to reveal phase
        current_vote["phase"] = "reveal"
        
        # Tally all votes
        vote_counts = {}
        for voter_id, vote_targets in current_vote["votes"].items():
            for target_id, vote_count in vote_targets.items():
                vote_counts[target_id] = vote_counts.get(target_id, 0) + vote_count
                
        # Apply immunity idol protection
        protected_players = set()
        for player_id, player in game["players"].items():
            if player.get("immunityIdolProtection", False):
                # Check if idol was nullified
                if not player.get("idolNullified", False):
                    protected_players.add(player_id)
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
                    
        # Determine elimination type
        elimination_type = current_vote.get("type", "single")
        eliminations_needed = 1 if elimination_type == "single" else 2
        
        # Sort players by vote count (highest first)
        sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Find players to eliminate
        if not sorted_votes:
            # No valid votes - need tie-breaker among all eligible players
            eligible_players = [pid for pid, p in game["players"].items() 
                             if not p.get("isEliminated", False) and pid not in protected_players]
            current_vote["tieBreakNeeded"] = True
            current_vote["tiedPlayers"] = eligible_players
            current_vote["eliminated"] = []
        else:
            # Check for ties at elimination threshold
            if len(sorted_votes) > eliminations_needed:
                elimination_threshold = sorted_votes[eliminations_needed - 1][1]
                tied_at_threshold = [pid for pid, votes in sorted_votes if votes == elimination_threshold]
                
                if len(tied_at_threshold) > 1:
                    # Tie detected - need council leader to break
                    current_vote["tieBreakNeeded"] = True
                    current_vote["tiedPlayers"] = tied_at_threshold
                    current_vote["eliminated"] = []
                else:
                    # No tie - clear eliminations
                    current_vote["tieBreakNeeded"] = False
                    current_vote["eliminated"] = [pid for pid, _ in sorted_votes[:eliminations_needed]]
            else:
                # Not enough players with votes - eliminate all with votes
                current_vote["tieBreakNeeded"] = False
                current_vote["eliminated"] = [pid for pid, _ in sorted_votes[:eliminations_needed]]
                
        # Store vote results for display
        current_vote["voteResults"] = vote_counts
        current_vote["protectedPlayers"] = list(protected_players)
        
        self._save()
        logger.info(f"Vote reveal completed in game {gid} - {len(current_vote['eliminated'])} eliminated, tie-break needed: {current_vote['tieBreakNeeded']}")
        
        if current_vote["tieBreakNeeded"]:
            return {"success": True, "message": f"Votes revealed - tie-break needed between {len(current_vote['tiedPlayers'])} players"}
        else:
            return {"success": True, "message": f"Votes revealed - {len(current_vote['eliminated'])} players eliminated"}

    def tie_break(self, gid, leaderId=None, chosenId=None, **kwargs):
        """
        Handle tie-break scenarios during tribal council.
        
        Args:
            gid: Game ID
            leaderId: ID of tribal council leader making the decision
            chosenId: ID of player chosen for elimination
        """
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
            
        if not leaderId:
            return {"success": False, "message": "Leader ID required for tie-break"}
            
        if not chosenId:
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
            
        # Validate chosen player is in tied players list
        tied_players = current_vote.get("tiedPlayers", [])
        if chosenId not in tied_players:
            return {"success": False, "message": f"Chosen player must be one of the tied players: {tied_players}"}
            
        # Validate chosen player exists and is not eliminated
        chosen_player = game["players"].get(chosenId)
        if not chosen_player:
            return {"success": False, "message": "Invalid chosen player"}
            
        if chosen_player.get("isEliminated", False):
            return {"success": False, "message": "Cannot eliminate already eliminated player"}
            
        # Resolve tie-break
        elimination_type = current_vote.get("type", "single")
        eliminations_needed = 1 if elimination_type == "single" else 2
        
        # For single elimination, just choose the one player
        if elimination_type == "single":
            current_vote["eliminated"] = [chosenId]
        else:
            # For double elimination, need to handle differently
            # If there are enough tied players, eliminate up to the limit
            if len(tied_players) >= eliminations_needed:
                # Leader chooses first, then need additional logic for second elimination
                current_vote["eliminated"] = [chosenId]
                # For simplicity, if double elimination needed and tie, eliminate all tied players up to limit
                remaining_spots = eliminations_needed - 1
                remaining_tied = [pid for pid in tied_players if pid != chosenId]
                current_vote["eliminated"].extend(remaining_tied[:remaining_spots])
            else:
                current_vote["eliminated"] = [chosenId]
                
        # Clear tie-break state
        current_vote["tieBreakNeeded"] = False
        current_vote["tieBreakResolvedBy"] = leaderId
        
        self._save()
        logger.info(f"Tie-break resolved by {leaderId} in game {gid} - eliminated: {current_vote['eliminated']}")
        
        return {"success": True, "message": f"Tie-break resolved - {len(current_vote['eliminated'])} players eliminated"}

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
            
        eliminated_players = current_vote.get("eliminated", [])
        
        if not eliminated_players:
            return {"success": False, "message": "No players marked for elimination"}
            
        # Process eliminations
        inheritance_messages = []
        jury_members = []
        
        for player_id in eliminated_players:
            player = game["players"].get(player_id)
            if not player:
                continue
                
            # Mark player as eliminated
            player["isEliminated"] = True
            player["isActive"] = False
            
            # Add to jury (eliminated players become jury members for final tribal)
            if "jury" not in game:
                game["jury"] = []
            game["jury"].append(player_id)
            jury_members.append(player.get("name", player_id))
            
            # Process inheritance effects
            inheritance_results = self.rules_engine.process_elimination_inheritance(game, player_id)
            inheritance_messages.extend(inheritance_results)
            
            logger.info(f"Player {player_id} eliminated and added to jury in game {gid}")
            
        # Reset per-tribal flags using rules engine
        self.rules_engine._reset_post_tribal_flags(game)
        
        # Check if final tribal should trigger (2 players remaining)
        active_players = [pid for pid, p in game["players"].items() if not p.get("isEliminated", False)]
        
        if len(active_players) == 2:
            # Trigger final tribal council
            self._start_final_tribal_council(game, active_players)
            message = f"Tribal council completed - {len(eliminated_players)} eliminated. Final Tribal Council begins!"
        else:
            # Return to normal game play
            game["phase"] = "playing"
            
            # Clear tribal council state
            if "currentVote" in game:
                del game["currentVote"]
                
            # Advance turn to next player if needed
            if "turnOrder" in game and game["turnOrder"]:
                # Find next active player
                current_index = game.get("currentTurnIndex", 0)
                turn_order = game["turnOrder"]
                
                # Find next active player
                attempts = 0
                while attempts < len(turn_order):
                    current_index = (current_index + 1) % len(turn_order)
                    next_player_id = turn_order[current_index]
                    if not game["players"][next_player_id].get("isEliminated", False):
                        break
                    attempts += 1
                    
                game["currentTurnIndex"] = current_index
                
            message = f"Tribal council completed - {len(eliminated_players)} eliminated. Game continues with {len(active_players)} players."
            
        # Record elimination in game history
        if "gameHistory" not in game:
            game["gameHistory"] = []
            
        elimination_record = {
            "type": "tribal_council_elimination",
            "eliminated": eliminated_players,
            "elimination_type": current_vote.get("type", "single"),
            "vote_results": current_vote.get("voteResults", {}),
            "jury_members": jury_members,
            "timestamp": time.time()
        }
        
        if inheritance_messages:
            elimination_record["inheritance"] = inheritance_messages
            
        game["gameHistory"].append(elimination_record)
        
        self._save()
        logger.info(f"Tribal council completed in game {gid} - {len(eliminated_players)} eliminated, {len(active_players)} remaining")
        
        result = {"success": True, "message": message}
        if inheritance_messages:
            result["inheritance_messages"] = inheritance_messages
            
        return result

    def _trigger_tribal_council(self, game, elimination_type):
        """
        Trigger a tribal council when a tribal council card is drawn.
        
        Args:
            game: Game state dictionary
            elimination_type: Type of elimination ("single" or "double")
        """
        # Transition game from "playing" to "tribal_council" phase
        game["phase"] = "tribal_council"
        
        # Initialize the currentVote structure for tribal council
        game["currentVote"] = {
            "type": elimination_type,
            "phase": "announcement",  # Start with announcement phase
            "votes": {},
            "councilLeaderId": game.get("councilLeaderId"),
            "immunityPlayed": [],
            "advantageCardsPlayed": [],
            "tieBreakNeeded": False,
            "tiedPlayers": [],
            "eliminated": [],
            "voteResults": {}
        }
        
        # Clear previous tribal council state flags
        for player in game["players"].values():
            player["hasVoted"] = False
            player["immunityPlayed"] = False
            
        logger.info(f"Triggered tribal council with {elimination_type} elimination")

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
        
        # Clear tribal council state
        if "currentVote" in game:
            del game["currentVote"]
        
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

    def advance_tribal_phase(self, gid, target_phase):
        """
        Advance tribal council to a specific phase with validation.
        
        Args:
            gid: Game ID
            target_phase: Phase to advance to
            
        Returns:
            Boolean indicating success
        """
        if gid not in self.games:
            return False
            
        game = self.games[gid]
        
        # Use rules engine to advance tribal phase with validation
        success, message = self.rules_engine.advance_tribal_phase(game, target_phase)
        
        if success:
            self._save()
            logger.info(f"Advanced tribal phase to {target_phase} in game {gid}")
            
        return success

    def play_tribal_advantage(self, gid, **kwargs):
        """Play tribal advantage card."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        return {"success": True, "message": "Feature not yet implemented"}

    def enhanced_tie_break(self, gid, **kwargs):
        """Handle enhanced tie break."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        return {"success": True, "message": "Feature not yet implemented"}

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
            "questions": [
                "What was your biggest strategic move?",
                "Why do you deserve to win?",
                "How did you adapt your strategy throughout the game?"
            ],
            "voteCounts": {},
            "tieBreakNeeded": False
        }
        
        logger.info(f"Final tribal council started with finalists: {finalists}, jury: {jury_members}, leader: {leader_id}")

    # ═══════════════════════════ Final Tribal Methods ═══════════════════════════
    def advance_final_phase(self, gid, target_phase):
        """
        Advance final tribal council to a specific phase.
        
        Args:
            gid: Game ID
            target_phase: Phase to advance to ("deliberation", "voting", "reveal")
            
        Returns:
            Boolean indicating success
        """
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
        valid_transitions = {
            "questions": ["deliberation"],
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
            # No additional setup needed for reveal
            pass
            
        self._save()
        logger.info(f"Advanced final tribal phase to {target_phase} in game {gid}")
        return True

    def cast_final_vote(self, gid, **kwargs):
        """Cast final tribal vote."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        return {"success": True, "message": "Feature not yet implemented"}

    def break_final_tie(self, gid, **kwargs):
        """Break final tribal tie."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        return {"success": True, "message": "Feature not yet implemented"}

    def signal_jury_ready(self, gid, **kwargs):
        """Signal jury member ready."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        return {"success": True, "message": "Feature not yet implemented"}

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

    def steal_card(self, gid, **kwargs):
        """Steal card from another player."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        thief_id = kwargs.get('thiefId')
        target_id = kwargs.get('targetId')
        
        if not thief_id or not target_id:
            return {"success": False, "message": "Both thiefId and targetId are required"}
        
        if thief_id not in game["players"] or target_id not in game["players"]:
            return {"success": False, "message": "Invalid player IDs"}
        
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
                "targetId": target_id,
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

    def play_card(self, gid, **kwargs):
        """Play a card."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        player_id = kwargs.get('playerId')
        card_idx = kwargs.get('cardIdx')
        
        if not player_id or card_idx is None:
            return {"success": False, "message": "Both playerId and cardIdx are required"}
        
        if player_id not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}
        
        player = game["players"][player_id]
        
        if player.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot play cards"}
        
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
        
        # Handle tribal council card triggers
        if card.get("category") == "tribal_council":
            game["phase"] = "tribal_council"
            game["currentVote"] = {
                "type": card.get("elimination_type", "single"),
                "votes": {},
                "phase": "announcement",
                "councilLeaderId": self._get_council_leader_id(game),
                "immunityPlayed": [],
                "tieBreakNeeded": False,
                "tiedPlayers": [],
                "eliminated": []
            }
            
        self._save()
        return {
            "success": True, 
            "message": effect_result.get("message", f"Played {card.get('name', 'card')}"),
            "card_effect": effect_result,
            "tribal_triggered": card.get("category") == "tribal_council"
        }

    def draw_card(self, gid, **kwargs):
        """Draw a card."""
        if gid not in self.games:
            return {"success": False, "message": "Game not found"}
        
        game = self.games[gid]
        player_id = kwargs.get('playerId')
        
        if not player_id:
            return {"success": False, "message": "playerId is required"}
        
        if player_id not in game["players"]:
            return {"success": False, "message": "Invalid player ID"}
        
        player = game["players"][player_id]
        
        if player.get("isEliminated", False):
            return {"success": False, "message": "Eliminated players cannot draw cards"}
        
        deck = game.get("deck", [])
        if not deck:
            return {"success": True, "message": "Deck is empty - no cards to draw"}
        
        # Get number of cards to draw (including draw bonuses)
        draw_count = self.rules_engine.get_card_draw_count(player)
        
        drawn_cards = []
        tribal_triggered = False
        
        for _ in range(min(draw_count, len(deck))):
            if not deck:
                break
                
            drawn_card = deck.pop(0)
            resolved_card = self.rules_engine.resolve_card(drawn_card)
            
            # Check for tribal council card
            if resolved_card.get("category") == "tribal_council":
                tribal_triggered = True
                # Tribal cards trigger immediately when drawn
                game["phase"] = "tribal_council"
                game["currentVote"] = {
                    "type": resolved_card.get("elimination_type", "single"),
                    "votes": {},
                    "phase": "announcement",
                    "councilLeaderId": self._get_council_leader_id(game),
                    "immunityPlayed": [],
                    "tieBreakNeeded": False,
                    "tiedPlayers": [],
                    "eliminated": []
                }
                drawn_cards.append(resolved_card)
                # Tribal cards are not added to hand - they trigger immediately
                break
            else:
                player["hand"].append(drawn_card)
                drawn_cards.append(resolved_card)
        
        # Process card draw effects (Camp Raid, etc.)
        if not tribal_triggered:
            self.rules_engine.process_card_draw_effects(game, player_id, drawn_cards)
        
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
        
        turn_order = game.get("turnOrder", [])
        if not turn_order:
            return {"success": False, "message": "No turn order established"}
        
        current_index = game.get("currentTurnIndex", 0)
        
        # Reset hasStolen for all players at end of turn
        for player in game["players"].values():
            player["hasStolen"] = False
        
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
            "timestamp": time.time()
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
        
        # Reset all player states
        for player in game["players"].values():
            player["hand"] = []
            player["isEliminated"] = False
            player["hasStolen"] = False
            player["hasVoted"] = False
            player["extraVotes"] = 0
            player["characterCards"] = 2
            player["immunityPlayed"] = False
            
            # Clear all temporary flags and effects
            player.pop("immunityIdolProtection", None)
            player.pop("idolNullified", None)
            player.pop("immunityNullified", None)
            player.pop("temporaryImmunity", None)
            player.pop("voteStolen", None)
            player.pop("voteBanned", None)
            player.pop("drawBonus", None)
        
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
        
        # Remove card from hand
        played_card = hand.pop(card_idx)
        
        # Execute reactive interrupt
        thief_id = pending_theft.get("thiefId")
        interrupt_result = self.rules_engine.execute_reactive_interrupt(
            game, player_id, thief_id, card
        )
        
        if interrupt_result.get("success"):
            # Close reactive window
            del game["pending_theft"]
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
        
        # Execute the theft
        theft_result = self.rules_engine.execute_theft(game, thief_id, target_id)
        
        # Close reactive window
        del game["pending_theft"]
        
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
            if action in ['reset_game', 'record_winner']:
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
    
    # Add cache headers for frequent polling
    response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    response.headers['ETag'] = f'state-{game_id}-{int(time.time())}'
    
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
        "game_id": "manual_entry"
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

@app.route('/api/game/create',methods=['POST'])
@safe_api_call
def api_create():
    """Create new game with error handling"""
    try:
        game_id = game_state.create_game()
        if not game_id:
            return jsonify(success=False, message="Failed to create game"), 500
        logger.info(f"Created new game: {game_id}")
        return jsonify(gameId=game_id, success=True)
    except Exception as e:
        logger.error(f"Failed to create game: {e}")
        return jsonify(success=False, message="Game creation failed"), 500

@app.route('/api/player/join',methods=['POST'])
def api_join():
    d=request.get_json(silent=True) or {}
    gid = d.get('gameId')
    if not gid or gid not in game_state.games:
        return jsonify(success=False, message="Game not found or has ended."), 404

    g = game_state.games[gid]
    if len(g['players']) >= 6:
        return jsonify(success=False, message="Game is full."), 400

    name = d.get('name', '').strip()
    is_valid, error_msg = validate_player_name(name)
    if not is_valid:
        return jsonify(success=False, message=error_msg), 400

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
def api_enhanced_tie_break(): return handle('enhanced_tie_break',['leaderId','eliminationType','tiedPlayers','chosenIds'])

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
def on_disconnect():
    """Handle client disconnect with logging"""
    logger.debug(f"Client disconnected: {request.sid}")

@socketio.on('connect')
def on_connect():
    """Handle client connect with logging"""
    logger.debug(f"Client connected: {request.sid}")

@socketio.on('heartbeat')
def on_heartbeat():
    """Handle heartbeat to keep WebSocket connection alive through Cloudflare"""
    return {'status': 'ok', 'timestamp': time.time()}

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
    """Global handler for unhandled exceptions to prevent 500 errors."""
    logger.error(f"Unhandled Exception: {e}", exc_info=True)
    return jsonify(success=False, message=f"An internal server error occurred: {str(e)}"), 500


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
        IP = get_local_ip()
        port = find_available_port()
        
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
