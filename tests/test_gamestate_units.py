#!/usr/bin/env python3
"""
Comprehensive Unit Tests for GameState Class
Testing all methods in the Survivor iOS App GameState class without Flask dependencies

This test suite covers:
- Game creation and player management
- Card deck creation and management  
- Phase transitions and turn management
- Card playing and effect execution
- Data persistence (save/load methods)
- Validation methods
- Edge cases and error handling
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import uuid
import time
import os
import json
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
import sys
import random

from rules_engine import SurvivorRulesEngine

# Single shared engine — the tests exercise the REAL deck/card rules, not a copy.
RULES = SurvivorRulesEngine()

# Mock Flask dependencies for testing
class MockFlask:
    def __init__(self):
        self.config = {}

class MockSocketIO:
    def emit(self, *args, **kwargs):
        pass

# Create a test version of GameState without Flask dependencies
class TestableGameState:
    """GameState class modified for unit testing without Flask server dependencies"""
    
    def __init__(self, test_mode=True):
        self._FILE = 'test_games.json' if test_mode else 'games.json'
        self._WINNERS_FILE = 'test_winners.json' if test_mode else 'winners.json'
        self.games = {}
        if not test_mode:
            self._load()
    
    # Core GameState methods (copied from survivor_server.py for testing)
    def _save(self):
        """Save game state with error handling and atomic writes"""
        temp_file = f"{self._FILE}.tmp"
        try:
            # Use atomic write to prevent corruption
            with open(temp_file, 'w') as f:
                json.dump(self.games, f, indent=2)
            
            # Atomic rename
            if os.path.exists(self._FILE):
                os.remove(self._FILE)
            os.rename(temp_file, self._FILE)
            
        except (IOError, OSError, ValueError) as e:
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            raise

    def _load(self):
        """Load game state with comprehensive error handling"""
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
                
        except (ValueError, IOError, OSError) as e:
            self.games = {}
            
            # Try to backup corrupted file
            try:
                backup_file = f"{self._FILE}.backup.{int(time.time())}"
                os.rename(self._FILE, backup_file)
            except OSError:
                pass

    def create_game(self):
        gid = str(uuid.uuid4())[:8]
        self.games[gid] = {
            "gameId": gid,
            "players": {},
            "phase": "lobby",  # lobby → playing → tribal_council → final
            "turnPhase": "waiting",  # steal → play → draw
            "turnOrder": [],
            "currentTurnIndex": 0,
            "deck": [],
            "currentVote": {
                "type": "single", "votes": {}, "phase": "waiting",
                "councilLeaderId": None, "immunityPlayed": [],
                "tieBreakNeeded": False, "tiedPlayers": [], "eliminated": []
            },
            "gameHistory": [],
            "jury": [],  # List of eliminated players who become jury members
            "finalTribal": {
                "phase": "waiting",  # waiting → voting → reveal
                "finalists": [],
                "voteCounts": {},
                "tieBreakNeeded": False,
                "tieBreakerLeader": None
            },
            "created": time.time()
        }
        self._save()
        return gid

    def add_player(self, game_id, name, color):
        if game_id not in self.games:
            return None
        pid = str(uuid.uuid4())[:8]
        self.games[game_id]["players"][pid] = {
            "id": pid, "name": name, "color": color,
            "characterCards": 2, "isActive": True, "isCouncilLeader": False,
            "hasVoted": False, "immunityPlayed": False, "hand": []
        }
        if len(self.games[game_id]["players"]) == 1:
            self.games[game_id]["players"][pid]["isCouncilLeader"] = True
            self.games[game_id]["currentVote"]["councilLeaderId"] = pid
        self._save()
        return pid

    def reconnect_player(self, gid, pid):
        return pid in self.games.get(gid, {}).get("players", {})

    def change_leader(self, gid, new_leader_id):
        g = self.games.get(gid)
        if not g or new_leader_id not in g["players"]:
            return False
        for p in g["players"].values():
            p["isCouncilLeader"] = False
        g["players"][new_leader_id]["isCouncilLeader"] = True
        g["currentVote"]["councilLeaderId"] = new_leader_id
        self._save()
        return True

    def start_voting(self, gid, vote_type):
        g = self.games.get(gid)
        if not g or g["currentVote"]["phase"] != "waiting":
            return False
        for p in g["players"].values():
            p["hasVoted"] = False
        g["currentVote"].update({"phase": "voting", "type": vote_type,
                                 "votes": {}, "immunityPlayed": [],
                                 "tieBreakNeeded": False, "tiedPlayers": [],
                                 "eliminated": []})
        self._save()
        return True

    def reset_game(self, gid):
        if gid not in self.games:
            return False
        # Reset to lobby state but keep players
        g = self.games[gid]
        g["phase"] = "lobby"
        g["turnPhase"] = "waiting"
        g["currentTurnIndex"] = 0
        g["deck"] = []
        for player in g["players"].values():
            player["characterCards"] = 2
            player["hasVoted"] = False
            player["immunityPlayed"] = False
            player["hand"] = []
        self._save()
        return True

    def _get_card_database(self):
        """Card database, sourced from the real rules engine (survivor_cards.json)."""
        return {
            card_type: {
                "name": card["name"],
                "description": card["description"],
                "category": card["category"],
                "playable_phases": card["playable_phases"] or ["turn_play"],
                "requires_target": card.get("requires_target", False),
                "requires_confirmation": card.get("requires_confirmation", False),
            }
            for card_type, card in RULES.get_all_card_definitions().items()
        }

    def _create_deck(self, player_count=4, deck_mode="official", expansion=False):
        """Create a complete deck via the real rules engine."""
        return RULES.create_deck(player_count, deck_mode=deck_mode, expansion=expansion)

    def _create_tribal_council_cards(self, player_count):
        """Tribal Council Cards for this player count, per the official rules table."""
        return RULES._create_tribal_council_cards(player_count)

    def _insert_tribal_cards(self, deck, tribal_cards):
        """Assemble tribal cards into a deck: 1 on the bottom, rest spaced evenly."""
        return RULES._insert_tribal_cards(deck, tribal_cards)

    def start_full_game(self, gid, deck_mode="official", expansion=False):
        """
        Start the full card-based game, following official setup order:
        deal 3 Action Cards + 1 Vote Card each, THEN assemble the Tribal Council
        Cards into what remains of the Draw Pile.
        """
        g = self.games.get(gid)
        if not g or g["phase"] != "lobby":
            return False

        player_count = len([p for p in g["players"].values() if p["isActive"]])
        if player_count < 3:
            return False

        action_deck = RULES.create_action_deck(deck_mode=deck_mode, expansion=expansion)

        g["turnOrder"] = list(g["players"].keys())
        random.shuffle(g["turnOrder"])
        g["currentTurnIndex"] = 0
        g["phase"] = "playing"
        g["turnPhase"] = "steal"

        for pid in g["players"]:
            g["players"][pid]["hand"] = []
            for _ in range(3):
                if action_deck:
                    g["players"][pid]["hand"].append(action_deck.pop(0))
            g["players"][pid]["hand"].append({"type": "vote"})

        g["deck"] = RULES.assemble_deck(action_deck, player_count,
                                        deck_mode=deck_mode, expansion=expansion)

        self._save()
        return True

    def record_winner(self, gid, winner_id):
        """Record a game winner"""
        g = self.games.get(gid)
        if not g or winner_id not in g["players"]:
            return False
            
        winner_data = {
            "gameId": gid,
            "winnerId": winner_id,
            "winnerName": g["players"][winner_id]["name"],
            "timestamp": time.time(),
            "playerCount": len(g["players"])
        }
        
        # Save to winners file
        winners = []
        if os.path.exists(self._WINNERS_FILE):
            try:
                with open(self._WINNERS_FILE, 'r') as f:
                    winners = json.load(f)
            except (ValueError, IOError):
                winners = []
        
        winners.append(winner_data)
        
        try:
            with open(self._WINNERS_FILE, 'w') as f:
                json.dump(winners, f, indent=2)
        except (IOError, OSError):
            return False
            
        return True


class TestGameStateUnits(unittest.TestCase):
    """Comprehensive unit tests for GameState class methods"""

    def setUp(self):
        """Set up test environment with temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        
        # Create fresh GameState instance for each test
        self.gs = TestableGameState(test_mode=True)

    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_init(self):
        """Test GameState initialization"""
        gs = TestableGameState(test_mode=True)
        self.assertIsInstance(gs.games, dict)
        self.assertEqual(len(gs.games), 0)
        self.assertEqual(gs._FILE, 'test_games.json')
        self.assertEqual(gs._WINNERS_FILE, 'test_winners.json')

    def test_create_game_success(self):
        """Test successful game creation"""
        gid = self.gs.create_game()
        
        # Verify game ID format
        self.assertIsInstance(gid, str)
        self.assertEqual(len(gid), 8)
        
        # Verify game structure
        self.assertIn(gid, self.gs.games)
        game = self.gs.games[gid]
        
        expected_keys = [
            "gameId", "players", "phase", "turnPhase", "turnOrder",
            "currentTurnIndex", "deck", "currentVote",
            "gameHistory", "jury", "finalTribal", "created"
        ]
        
        for key in expected_keys:
            self.assertIn(key, game)
        
        # Verify initial values
        self.assertEqual(game["gameId"], gid)
        self.assertEqual(game["phase"], "lobby")
        self.assertEqual(game["turnPhase"], "waiting")
        self.assertEqual(game["currentTurnIndex"], 0)
        self.assertIsInstance(game["created"], float)

    def test_create_multiple_games(self):
        """Test creating multiple games produces unique IDs"""
        gid1 = self.gs.create_game()
        gid2 = self.gs.create_game()
        gid3 = self.gs.create_game()
        
        self.assertNotEqual(gid1, gid2)
        self.assertNotEqual(gid1, gid3)
        self.assertNotEqual(gid2, gid3)
        
        self.assertEqual(len(self.gs.games), 3)

    def test_add_player_success(self):
        """Test successful player addition"""
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "TestPlayer", "red")
        
        self.assertIsNotNone(pid)
        self.assertIsInstance(pid, str)
        self.assertEqual(len(pid), 8)
        
        # Verify player structure
        game = self.gs.games[gid]
        self.assertIn(pid, game["players"])
        
        player = game["players"][pid]
        expected_keys = [
            "id", "name", "color", "characterCards", "isActive",
            "isCouncilLeader", "hasVoted", "immunityPlayed", "hand"
        ]
        
        for key in expected_keys:
            self.assertIn(key, player)
        
        # Verify player values
        self.assertEqual(player["name"], "TestPlayer")
        self.assertEqual(player["color"], "red")
        self.assertEqual(player["characterCards"], 2)
        self.assertTrue(player["isActive"])
        self.assertTrue(player["isCouncilLeader"])  # First player becomes leader
        self.assertFalse(player["hasVoted"])

    def test_add_player_first_becomes_leader(self):
        """Test that first player automatically becomes council leader"""
        gid = self.gs.create_game()
        pid1 = self.gs.add_player(gid, "Player1", "red")
        pid2 = self.gs.add_player(gid, "Player2", "blue")
        
        game = self.gs.games[gid]
        self.assertTrue(game["players"][pid1]["isCouncilLeader"])
        self.assertFalse(game["players"][pid2]["isCouncilLeader"])
        self.assertEqual(game["currentVote"]["councilLeaderId"], pid1)

    def test_add_player_invalid_game(self):
        """Test adding player to non-existent game"""
        result = self.gs.add_player("invalid_gid", "Player", "red")
        self.assertIsNone(result)

    def test_reconnect_player_valid(self):
        """Test player reconnection with valid IDs"""
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "Player", "red")
        
        result = self.gs.reconnect_player(gid, pid)
        self.assertTrue(result)

    def test_reconnect_player_invalid(self):
        """Test player reconnection with invalid IDs"""
        gid = self.gs.create_game()
        
        # Invalid player ID
        result = self.gs.reconnect_player(gid, "invalid_pid")
        self.assertFalse(result)
        
        # Invalid game ID
        result = self.gs.reconnect_player("invalid_gid", "invalid_pid")
        self.assertFalse(result)

    def test_change_leader_success(self):
        """Test successful leader change"""
        gid = self.gs.create_game()
        pid1 = self.gs.add_player(gid, "Player1", "red")
        pid2 = self.gs.add_player(gid, "Player2", "blue")
        
        result = self.gs.change_leader(gid, pid2)
        self.assertTrue(result)
        
        game = self.gs.games[gid]
        self.assertFalse(game["players"][pid1]["isCouncilLeader"])
        self.assertTrue(game["players"][pid2]["isCouncilLeader"])
        self.assertEqual(game["currentVote"]["councilLeaderId"], pid2)

    def test_change_leader_invalid(self):
        """Test leader change with invalid parameters"""
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "Player", "red")
        
        # Invalid game ID
        result = self.gs.change_leader("invalid_gid", pid)
        self.assertFalse(result)
        
        # Invalid player ID
        result = self.gs.change_leader(gid, "invalid_pid")
        self.assertFalse(result)

    def test_start_voting_success(self):
        """Test successful voting initiation"""
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "Player", "red")
        
        result = self.gs.start_voting(gid, "single")
        self.assertTrue(result)
        
        game = self.gs.games[gid]
        vote_state = game["currentVote"]
        
        self.assertEqual(vote_state["phase"], "voting")
        self.assertEqual(vote_state["type"], "single")
        self.assertFalse(game["players"][pid]["hasVoted"])

    def test_start_voting_invalid(self):
        """Test voting initiation with invalid parameters"""
        # Invalid game ID
        result = self.gs.start_voting("invalid_gid", "single")
        self.assertFalse(result)
        
        # Voting already in progress
        gid = self.gs.create_game()
        self.gs.add_player(gid, "Player", "red")
        self.gs.start_voting(gid, "single")
        
        result = self.gs.start_voting(gid, "double")
        self.assertFalse(result)

    def test_reset_game_success(self):
        """Test successful game reset"""
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "Player", "red")
        
        # Modify game state
        game = self.gs.games[gid]
        game["phase"] = "playing"
        game["turnPhase"] = "steal"
        game["deck"] = ["card1", "card2"]
        
        result = self.gs.reset_game(gid)
        self.assertTrue(result)
        
        # Verify reset state
        game = self.gs.games[gid]
        self.assertEqual(game["phase"], "lobby")
        self.assertEqual(game["turnPhase"], "waiting")
        self.assertEqual(game["currentTurnIndex"], 0)
        self.assertEqual(len(game["deck"]), 0)

    def test_reset_game_invalid(self):
        """Test game reset with invalid game ID"""
        result = self.gs.reset_game("invalid_gid")
        self.assertFalse(result)

    def test_get_card_database(self):
        """Test card database retrieval"""
        card_db = self.gs._get_card_database()
        
        self.assertIsInstance(card_db, dict)
        self.assertGreater(len(card_db), 0)
        
        # Check required cards exist
        required_cards = ["extra_vote", "immunity_idol", "camp_raid", "the_spy_shack"]
        for card_type in required_cards:
            self.assertIn(card_type, card_db)
            
            card_info = card_db[card_type]
            self.assertIn("name", card_info)
            self.assertIn("description", card_info)
            self.assertIn("category", card_info)
            self.assertIn("playable_phases", card_info)

    def test_create_deck_structure(self):
        """Test deck creation produces valid structure"""
        deck = self.gs._create_deck(4)

        self.assertIsInstance(deck, list)

        def is_tribal(card):
            return str(card.get("type", "")).startswith("tribal_council")

        action_cards = [c for c in deck if not is_tribal(c)]
        tribal_cards = [c for c in deck if is_tribal(c)]

        # Official deck: 67 cards minus the 9 Tribal Council and 6 Vote Cards that
        # setup removes = 52 Action Cards in the Draw Pile.
        self.assertEqual(len(action_cards), 52)
        self.assertEqual(len(tribal_cards), 4)  # 4 players = 2 single + 2 double
        self.assertEqual(len(deck), 56)

    def test_create_deck_different_player_counts(self):
        """Test deck creation with different player counts"""
        for player_count in [3, 4, 5, 6]:
            deck = self.gs._create_deck(player_count)

            tribal_cards = [c for c in deck
                            if str(c.get("type", "")).startswith("tribal_council")]

            # Official rules table: 3p=4S/0D, 4p=2S/2D, 5p=2S/3D, 6p=0S/5D
            expected_tribal_counts = {3: 4, 4: 4, 5: 5, 6: 5}
            self.assertEqual(len(tribal_cards), expected_tribal_counts[player_count],
                             f"player_count={player_count}")

    def test_create_tribal_council_cards(self):
        """Test tribal council card creation"""
        # Test 4 players (2 single, 2 double)
        tribal_cards = self.gs._create_tribal_council_cards(4)
        
        self.assertEqual(len(tribal_cards), 4)
        
        single_count = len([c for c in tribal_cards if c["elimination_type"] == "single"])
        double_count = len([c for c in tribal_cards if c["elimination_type"] == "double"])
        
        self.assertEqual(single_count, 2)
        self.assertEqual(double_count, 2)

    def test_create_tribal_council_cards_all_player_counts(self):
        """Test tribal council cards for all valid player counts"""
        # The official rules table (Survivor: The Tribe Has Spoken, Setup step 4)
        expected_configs = {
            3: {"single": 4, "double": 0},
            4: {"single": 2, "double": 2},
            5: {"single": 2, "double": 3},
            6: {"single": 0, "double": 5}
        }
        
        for player_count, expected in expected_configs.items():
            tribal_cards = self.gs._create_tribal_council_cards(player_count)
            
            single_count = len([c for c in tribal_cards if c["elimination_type"] == "single"])
            double_count = len([c for c in tribal_cards if c["elimination_type"] == "double"])
            
            self.assertEqual(single_count, expected["single"], f"Player count {player_count}")
            self.assertEqual(double_count, expected["double"], f"Player count {player_count}")

    def test_insert_tribal_cards(self):
        """Test tribal card insertion into deck"""
        # Create a simple deck
        deck = [{"type": "action"} for _ in range(10)]
        tribal_cards = [
            {"type": "tribal_council", "elimination_type": "single"},
            {"type": "tribal_council", "elimination_type": "double"}
        ]
        
        result = self.gs._insert_tribal_cards(deck, tribal_cards)
        
        # Should have all original cards plus tribal cards
        self.assertEqual(len(result), 12)
        
        # Last card should be tribal (per rules)
        self.assertEqual(result[-1]["type"], "tribal_council")
        
        # Should have tribal cards distributed through deck
        tribal_positions = [i for i, card in enumerate(result) if card["type"] == "tribal_council"]
        self.assertEqual(len(tribal_positions), 2)

    def test_insert_tribal_cards_empty(self):
        """Test tribal card insertion with empty tribal cards list"""
        deck = [{"type": "action"} for _ in range(5)]
        result = self.gs._insert_tribal_cards(deck, [])
        
        self.assertEqual(result, deck)

    def test_start_full_game_success(self):
        """Test successful full game start"""
        gid = self.gs.create_game()
        # Add minimum 3 players
        for i in range(3):
            self.gs.add_player(gid, f"Player{i+1}", ["red", "blue", "green"][i])
        
        result = self.gs.start_full_game(gid)
        self.assertTrue(result)
        
        game = self.gs.games[gid]
        self.assertEqual(game["phase"], "playing")
        self.assertEqual(game["turnPhase"], "steal")
        self.assertGreater(len(game["deck"]), 0)
        self.assertEqual(len(game["turnOrder"]), 3)
        
        # Official setup deals 3 Action Cards + exactly 1 Vote Card to each player
        for player in game["players"].values():
            self.assertEqual(len(player["hand"]), 4)
            vote_cards = [c for c in player["hand"] if c.get("type") == "vote"]
            self.assertEqual(len(vote_cards), 1)

        # No Vote Cards and no Tribal Council Cards may be dealt into hands
        self.assertEqual([c for c in game["deck"] if c.get("type") == "vote"], [])
        for player in game["players"].values():
            for card in player["hand"]:
                self.assertFalse(str(card.get("type", "")).startswith("tribal_council"))

    def test_start_full_game_invalid_conditions(self):
        """Test full game start with invalid conditions"""
        gid = self.gs.create_game()
        
        # Not enough players
        self.gs.add_player(gid, "Player1", "red")
        result = self.gs.start_full_game(gid)
        self.assertFalse(result)
        
        # Invalid game ID
        result = self.gs.start_full_game("invalid_gid")
        self.assertFalse(result)
        
        # Game not in lobby phase
        self.gs.add_player(gid, "Player2", "blue")
        self.gs.add_player(gid, "Player3", "green")
        self.gs.start_full_game(gid)  # Start successfully
        
        result = self.gs.start_full_game(gid)  # Try again
        self.assertFalse(result)

    def test_record_winner_success(self):
        """Test successful winner recording"""
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "Winner", "gold")
        
        result = self.gs.record_winner(gid, pid)
        self.assertTrue(result)
        
        # Verify winner file was created
        self.assertTrue(os.path.exists(self.gs._WINNERS_FILE))
        
        with open(self.gs._WINNERS_FILE, 'r') as f:
            winners = json.load(f)
        
        self.assertEqual(len(winners), 1)
        winner = winners[0]
        
        self.assertEqual(winner["gameId"], gid)
        self.assertEqual(winner["winnerId"], pid)
        self.assertEqual(winner["winnerName"], "Winner")
        self.assertIsInstance(winner["timestamp"], float)

    def test_record_winner_invalid(self):
        """Test winner recording with invalid parameters"""
        gid = self.gs.create_game()
        
        # Invalid player ID
        result = self.gs.record_winner(gid, "invalid_pid")
        self.assertFalse(result)
        
        # Invalid game ID
        result = self.gs.record_winner("invalid_gid", "invalid_pid")
        self.assertFalse(result)

    def test_save_and_load_persistence(self):
        """Test data persistence through save and load operations"""
        # Create game state
        gid = self.gs.create_game()
        pid = self.gs.add_player(gid, "PersistentPlayer", "purple")
        
        # Create new GameState instance and explicitly load the same file
        gs2 = TestableGameState(test_mode=True)
        gs2._FILE = self.gs._FILE  # Use same file
        gs2._load()  # Explicitly load
        
        # Verify data persisted
        self.assertIn(gid, gs2.games)
        self.assertIn(pid, gs2.games[gid]["players"])
        self.assertEqual(gs2.games[gid]["players"][pid]["name"], "PersistentPlayer")

    def test_save_error_handling(self):
        """Test save error handling with invalid file path"""
        # Create GameState with invalid file path
        gs_invalid = TestableGameState(test_mode=True)
        gs_invalid._FILE = "/invalid/path/that/does/not/exist/test_games.json"
        
        # This should raise an exception when trying to save
        with self.assertRaises((IOError, OSError, FileNotFoundError)):
            gs_invalid.create_game()

    def test_load_corrupted_file(self):
        """Test loading corrupted JSON file"""
        # Create corrupted file
        corrupted_file = "test_corrupted_games.json"
        with open(corrupted_file, 'w') as f:
            f.write("{ corrupted json content")
        
        # Create GameState that will try to load corrupted file
        gs_corrupted = TestableGameState(test_mode=True)
        gs_corrupted._FILE = corrupted_file
        gs_corrupted._load()
        
        # Should handle corruption gracefully
        self.assertEqual(len(gs_corrupted.games), 0)
        
        # Should create backup file
        backup_files = [f for f in os.listdir('.') if f.startswith(f"{corrupted_file}.backup")]
        self.assertGreater(len(backup_files), 0)

    def test_load_empty_file(self):
        """Test loading empty file"""
        # Create empty file
        with open(self.gs._FILE, 'w') as f:
            f.write("")
        
        gs_empty = TestableGameState(test_mode=False)
        self.assertEqual(len(gs_empty.games), 0)

    def test_card_database_completeness(self):
        """Test that card database contains all required fields"""
        card_db = self.gs._get_card_database()
        
        required_fields = ["name", "description", "category", "playable_phases"]
        
        for card_type, card_info in card_db.items():
            for field in required_fields:
                self.assertIn(field, card_info, f"Card {card_type} missing field {field}")
            
            # Validate playable_phases is a list
            self.assertIsInstance(card_info["playable_phases"], list)
            self.assertGreater(len(card_info["playable_phases"]), 0)

    def test_edge_case_zero_players(self):
        """Test edge case with zero players"""
        gid = self.gs.create_game()
        
        # Try to start game with no players
        result = self.gs.start_full_game(gid)
        self.assertFalse(result)

    def test_edge_case_many_players(self):
        """Test edge case with maximum players"""
        gid = self.gs.create_game()
        
        # Add 6 players (maximum)
        pids = []
        colors = ["red", "blue", "green", "yellow", "purple", "orange"]
        for i in range(6):
            pid = self.gs.add_player(gid, f"Player{i+1}", colors[i])
            pids.append(pid)
        
        result = self.gs.start_full_game(gid)
        self.assertTrue(result)
        
        # Should create appropriate tribal cards for 6 players
        game = self.gs.games[gid]
        tribal_cards = [c for c in game["deck"]
                        if str(c.get("type", "")).startswith("tribal_council")]
        self.assertEqual(len(tribal_cards), 5)  # 6 players = 0 single + 5 double

    def test_concurrent_operations(self):
        """Test that operations maintain consistency under concurrent-like conditions"""
        gid = self.gs.create_game()
        
        # Simulate rapid player additions
        pids = []
        for i in range(5):
            pid = self.gs.add_player(gid, f"Player{i+1}", f"color{i}")
            pids.append(pid)
        
        # All players should be properly registered
        game = self.gs.games[gid]
        self.assertEqual(len(game["players"]), 5)
        
        # Only first player should be leader
        leader_count = sum(1 for p in game["players"].values() if p["isCouncilLeader"])
        self.assertEqual(leader_count, 1)

    def test_memory_efficiency(self):
        """Test memory efficiency with large game states"""
        # Create multiple games with players
        for game_num in range(10):
            gid = self.gs.create_game()
            for player_num in range(4):
                self.gs.add_player(gid, f"G{game_num}P{player_num}", "color")
        
        # Should handle multiple games without issues
        self.assertEqual(len(self.gs.games), 10)
        
        # Each game should have 4 players
        for game in self.gs.games.values():
            self.assertEqual(len(game["players"]), 4)


# ── Task S4: leaving a lobby, and start_full_game naming its refusal ──────
#
# These exercise the REAL survivor_server.GameState (not the TestableGameState
# mock above) — leave_game and start_full_game's refusal text are the actual
# production methods, so a mock copy would prove nothing.

class LobbyLeaveTest(unittest.TestCase):
    """A castaway can leave an unlit lobby, and only an unlit lobby."""

    def setUp(self):
        from survivor_server import GameState
        self.original_cwd = os.getcwd()
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)
        self.gs = GameState()
        self.gid = self.gs.create_game()
        self.alice = self.gs.add_player(self.gid, "Alice", "red")
        self.bob = self.gs.add_player(self.gid, "Bob", "blue")
        self.cara = self.gs.add_player(self.gid, "Cara", "green")

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_leaving_in_the_lobby_succeeds_and_frees_the_seat(self):
        result = self.gs.leave_game(self.gid, playerId=self.bob)
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn("Bob", result["message"])

        game = self.gs.games[self.gid]
        self.assertNotIn(self.bob, game["players"])
        self.assertNotIn(self.bob, game.get("turnOrder", []))

        # The freed name and colour are available to a new join
        check = self.gs.validate_new_player(self.gid, "Dee", "blue")
        self.assertTrue(check["success"], check.get("message"))

    def test_leaving_after_the_game_has_started_is_refused(self):
        self.gs.start_full_game(self.gid)
        result = self.gs.leave_game(self.gid, playerId=self.bob)
        self.assertFalse(result["success"])
        self.assertIn("started", result["message"])
        self.assertIn(self.bob, self.gs.games[self.gid]["players"],
                       "a refused leave must not remove the player")

    def test_leaving_as_an_unknown_player_is_refused(self):
        result = self.gs.leave_game(self.gid, playerId="not-a-real-player-id")
        self.assertFalse(result["success"])
        self.assertEqual(len(self.gs.games[self.gid]["players"]), 3)


class StartFullGameReasonsTest(unittest.TestCase):
    """start_full_game's refusal names why, instead of one flat message."""

    def setUp(self):
        from survivor_server import GameState
        self.original_cwd = os.getcwd()
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)
        self.gs = GameState()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_unknown_game_says_not_found(self):
        result = self.gs.start_full_game("no-such-game")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"].lower())

    def test_already_started_names_the_phase(self):
        gid = self.gs.create_game()
        for name in ("Alice", "Bob", "Cara"):
            self.gs.add_player(gid, name)
        self.gs.start_full_game(gid)
        result = self.gs.start_full_game(gid)
        self.assertFalse(result["success"])
        self.assertIn("started", result["message"])
        self.assertIn("playing", result["message"])

    def test_too_few_players_names_the_count(self):
        gid = self.gs.create_game()
        self.gs.add_player(gid, "Alice")
        self.gs.add_player(gid, "Bob")
        result = self.gs.start_full_game(gid)
        self.assertFalse(result["success"])
        self.assertIn("3", result["message"])
        self.assertIn("2", result["message"])


if __name__ == '__main__':
    # Configure test runner
    unittest.main(verbosity=2, buffer=True)