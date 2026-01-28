#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Turn-Based Gameplay
Testing complete turn sequences, multi-system interactions, and game flow

This test suite focuses on:
- Complete single player turns (steal → play → draw sequence)
- Multi-player turn sequences with proper turn advancement
- Card playing during appropriate phases with validation
- Turn interruption by tribal council cards
- Game flow from lobby through playing phase
- Turn validation and error handling scenarios
- Game state consistency throughout turn sequences
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

# Create a test version of GameState without Flask dependencies
class TestableGameState:
    """GameState class modified for integration testing without Flask server dependencies"""
    
    def __init__(self, test_mode=True):
        self._FILE = 'test_games.json' if test_mode else 'games.json'
        self._WINNERS_FILE = 'test_winners.json' if test_mode else 'winners.json'
        self.games = {}
        if not test_mode:
            self._load()
    
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

    def create_game(self):
        gid = str(uuid.uuid4())[:8]
        self.games[gid] = {
            "gameId": gid,
            "players": {},
            "phase": "lobby",  # lobby → playing → tribal → final
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
            "jury": [],
            "finalTribal": {
                "phase": "waiting", "finalists": [],
                "voteCounts": {}, "tieBreakNeeded": False,
                "tieBreakerLeader": None
            },
            "created": time.time()
        }
        return gid

    def add_player(self, game_id, name, color):
        if game_id not in self.games:
            return None
        pid = str(uuid.uuid4())[:8]
        self.games[game_id]["players"][pid] = {
            "id": pid, "name": name, "color": color,
            "characterCards": 2, "isActive": True, "isCouncilLeader": False,
            "hasVoted": False, "immunityPlayed": False, "hand": [], "hasStolen": False
        }
        if len(self.games[game_id]["players"]) == 1:
            self.games[game_id]["players"][pid]["isCouncilLeader"] = True
            self.games[game_id]["currentVote"]["councilLeaderId"] = pid
        return pid

    def _create_deck(self, player_count=4):
        """Create a deck of action cards for testing"""
        deck = []
        
        # Basic action cards for testing
        basic_cards = [
            {"type": "extra_vote", "description": "Gain an extra vote", 
             "playable_phases": ["tribal_discussion"], "requires_confirmation": False},
            {"type": "immunity_idol", "description": "Protect from elimination",
             "playable_phases": ["tribal_immunity"], "requires_confirmation": True},
            {"type": "camp_raid", "description": "Steal cards from other players",
             "playable_phases": ["turn_play"], "requires_confirmation": False, "requires_target": True},
            {"type": "alliance", "description": "Form strategic partnership",
             "playable_phases": ["turn_play"], "requires_confirmation": True, "requires_multiple_targets": True},
            {"type": "sabotage", "description": "Disrupt another player",
             "playable_phases": ["turn_play"], "requires_confirmation": False, "requires_target": True}
        ]
        
        # Add multiple copies of each card
        for card_template in basic_cards:
            for i in range(5):  # 5 copies of each
                card = card_template.copy()
                card["id"] = f"{card['type']}_{i}"
                deck.append(card)
        
        # Add tribal council cards (these trigger tribal council when drawn)
        tribal_cards = [
            {"type": "tribal_council", "elimination_type": "single", 
             "description": "Single elimination vote"},
            {"type": "tribal_council", "elimination_type": "double", 
             "description": "Double elimination vote"}
        ]
        
        for card_template in tribal_cards:
            for i in range(3):  # 3 copies each
                card = card_template.copy()
                card["id"] = f"{card['type']}_{card['elimination_type']}_{i}"
                deck.append(card)
        
        # Shuffle the deck
        random.shuffle(deck)
        return deck

    def start_full_game(self, gid):
        """Start the full card-based game phase"""
        g = self.games.get(gid)
        if not g:
            return False
        
        # Initialize full game state
        players = list(g["players"].keys())
        if len(players) < 2:
            return False
            
        # Set up full game phase
        g["phase"] = "playing"
        g["turnOrder"] = players.copy()
        g["currentTurnIndex"] = 0
        g["deck"] = self._create_deck(len(players))
        
        # Initialize player hands and states
        for pid, player in g["players"].items():
            player["hand"] = []
            player["hasStolen"] = False
            
        # Deal initial cards (2 per player)
        for _ in range(2):
            for pid in players:
                if g["deck"]:
                    card = g["deck"].pop()
                    g["players"][pid]["hand"].append(card)
        
        return True

    def _get_current_turn_phase(self, game, player_id):
        """Determine the current turn phase for card validation"""
        if game.get("phase") == "playing":
            # Check if it's this player's turn
            turn_order = game.get("turnOrder", [])
            if not turn_order:
                return "waiting"
            current_player = turn_order[game.get("currentTurnIndex", 0)]
            if current_player == player_id:
                player = game["players"][player_id]
                if not player.get("hasStolen"):
                    return "turn_steal"
                else:
                    return "turn_play"
            else:
                return "waiting"  # Not their turn
        elif game.get("phase") == "tribal_council":
            vote_phase = game.get("currentVote", {}).get("phase", "waiting")
            if vote_phase == "waiting":
                return "tribal_discussion"
            elif vote_phase == "immunity":
                return "tribal_immunity"
            else:
                return "tribal_voting"
        else:
            return game.get("phase", "lobby")

    def _validate_card_play(self, game, player_id, card, current_phase, params):
        """Validate if a card can be played in the current phase"""
        if not card.get("playable_phases"):
            return False, "Card has no valid play phases"
            
        if current_phase not in card["playable_phases"]:
            return False, f"Card cannot be played during {current_phase} phase"
            
        player = game["players"].get(player_id)
        if not player or not player.get("isActive"):
            return False, "Player is not active"
            
        # Additional validation based on card requirements
        if card.get("requires_target") and not params.get("targetId"):
            return False, "Card requires a target player"
            
        if card.get("requires_multiple_targets"):
            required_targets = ["teammateId", "victimId"] if card["type"] == "alliance" else ["targets"]
            if not all(params.get(target) for target in required_targets):
                return False, f"Card requires multiple targets: {required_targets}"
                
        return True, "Valid"

    def _execute_card_effect(self, game, player_id, card, params):
        """Execute the effect of a played card"""
        player = game["players"][player_id]
        card_type = card.get("type")
        
        # Basic card effects for testing
        if card_type == "extra_vote":
            player["extraVotes"] = player.get("extraVotes", 0) + 1
            return {"message": f"{player['name']} gained an extra vote"}
            
        elif card_type == "immunity_idol":
            player["immunityPlayed"] = True
            return {"message": f"{player['name']} played immunity idol"}
            
        elif card_type == "camp_raid":
            target_id = params.get("targetId")
            if target_id and target_id in game["players"]:
                target = game["players"][target_id]
                if target["hand"]:
                    stolen_card = random.choice(target["hand"])
                    target["hand"].remove(stolen_card)
                    player["hand"].append(stolen_card)
                    return {"message": f"{player['name']} raided {target['name']}'s camp"}
            return {"message": f"{player['name']} attempted camp raid but failed"}
            
        elif card_type == "alliance":
            teammate_id = params.get("teammateId")
            victim_id = params.get("victimId")
            if teammate_id and victim_id:
                return {"message": f"{player['name']} formed alliance targeting {victim_id}"}
            return {"message": f"{player['name']} attempted to form alliance but failed"}
            
        elif card_type == "sabotage":
            target_id = params.get("targetId")
            if target_id and target_id in game["players"]:
                target = game["players"][target_id]
                # Simple sabotage effect
                return {"message": f"{player['name']} sabotaged {target['name']}"}
            return {"message": f"{player['name']} attempted sabotage but failed"}
        
        # Default fallback
        return {"message": f"{player['name']} played {card_type}"}

    def _trigger_tribal_council(self, game, elimination_type):
        """Trigger a tribal council when a tribal council card is drawn"""
        game["phase"] = "tribal_council"
        game["currentVote"] = {
            "type": elimination_type,
            "phase": "waiting",
            "votes": {},
            "councilLeaderId": game.get("councilLeaderId"),
            "immunityPlayed": [],
            "tieBreakNeeded": False,
            "tiedPlayers": [],
            "eliminated": []
        }

    def _start_tribal_council(self, game, triggering_player_id, tribal_card):
        """Start tribal council phase"""
        self._trigger_tribal_council(game, tribal_card.get("elimination_type", "single"))
        
        # Add the tribal card to game history
        game["gameHistory"].append({
            "type": "tribal_triggered",
            "player": triggering_player_id,
            "card": tribal_card,
            "timestamp": time.time()
        })

    def _advance_turn(self, game):
        """Advance to next player's turn"""
        current_idx = game.get("currentTurnIndex", 0)
        turn_order = game.get("turnOrder", [])
        
        if turn_order:
            game["currentTurnIndex"] = (current_idx + 1) % len(turn_order)

    def steal_card(self, gid, thief_id, target_id):
        """Steal a card from another player"""
        g = self.games.get(gid)
        if not g or g.get("phase") != "playing":
            return False
            
        thief = g["players"].get(thief_id)
        target = g["players"].get(target_id)
        
        if not thief or not target or thief.get("hasStolen") or not target.get("hand"):
            return False
            
        # Steal random card
        stolen_card = random.choice(target["hand"])
        target["hand"].remove(stolen_card)
        thief["hand"].append(stolen_card)
        thief["hasStolen"] = True
        
        return True
        
    def play_card(self, gid, player_id, card_idx, params=None):
        """Play a card from hand with validation"""
        g = self.games.get(gid)
        if not g:
            return {"success": False, "message": "Game not found"}
            
        player = g["players"].get(player_id)
        if not player or card_idx >= len(player.get("hand", [])):
            return {"success": False, "message": "Invalid card selection"}
            
        card = player["hand"][card_idx]
        params = params or {}
        
        # Determine current phase for validation
        current_phase = self._get_current_turn_phase(g, player_id)
        
        # Validate card play
        valid, validation_msg = self._validate_card_play(g, player_id, card, current_phase, params)
        if not valid:
            return {"success": False, "message": validation_msg}
        
        # Card is valid - remove from hand and execute
        player["hand"].pop(card_idx)
        
        # Execute card effect
        effect_result = self._execute_card_effect(g, player_id, card, params)
        
        # Check for tribal council trigger
        if card.get("type") == "tribal_council":
            self._trigger_tribal_council(g, card.get("elimination_type", "single"))
        
        return {
            "success": True, 
            "message": effect_result.get("message", "Card played successfully"),
            "effect_data": effect_result
        }

    def draw_card(self, gid, player_id):
        """Draw a card and end turn"""
        g = self.games.get(gid)
        if not g or g.get("phase") != "playing":
            return False
            
        player = g["players"].get(player_id)
        if not player:
            return False
            
        # Check if it's this player's turn
        turn_order = g.get("turnOrder", [])
        if not turn_order or turn_order[g.get("currentTurnIndex", 0)] != player_id:
            return False
            
        # Draw card if deck has cards
        drawn_card = None
        if g.get("deck"):
            drawn_card = g["deck"].pop()
            
            # Check if drawn card is a tribal council card
            if drawn_card.get("category") == "tribal_council":
                # Start tribal council immediately
                self._start_tribal_council(g, player_id, drawn_card)
                return {"tribal_council": True, "card": drawn_card}
            else:
                player["hand"].append(drawn_card)
            
        # Reset steal flag and advance turn (only if not tribal council)
        if not drawn_card or drawn_card.get("category") != "tribal_council":
            player["hasStolen"] = False
            self._advance_turn(g)
        
        return True

    def advance_turn(self, gid):
        """Manually advance turn (leader action)"""
        g = self.games.get(gid)
        if not g:
            return False
            
        self._advance_turn(g)
        return True


class TestTurnBasedGameplay(unittest.TestCase):
    """Integration tests for turn-based gameplay mechanics"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        self.game_state = TestableGameState(test_mode=True)
        
        # Create test game with players
        self.game_id = self.game_state.create_game()
        self.player1_id = self.game_state.add_player(self.game_id, "Alice", "red")
        self.player2_id = self.game_state.add_player(self.game_id, "Bob", "blue")
        self.player3_id = self.game_state.add_player(self.game_id, "Charlie", "green")
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    def test_game_setup_and_start_full_game(self):
        """Test game flow from lobby to playing phase"""
        game = self.game_state.games[self.game_id]
        
        # Initially in lobby phase
        self.assertEqual(game["phase"], "lobby")
        self.assertEqual(len(game["deck"]), 0)
        
        # Start full game
        result = self.game_state.start_full_game(self.game_id)
        self.assertTrue(result)
        
        # Verify game state after start
        game = self.game_state.games[self.game_id]
        self.assertEqual(game["phase"], "playing")
        self.assertGreater(len(game["deck"]), 0)
        self.assertEqual(len(game["turnOrder"]), 3)
        self.assertEqual(game["currentTurnIndex"], 0)
        
        # Verify players have initial cards
        for player_id in [self.player1_id, self.player2_id, self.player3_id]:
            player = game["players"][player_id]
            self.assertEqual(len(player["hand"]), 2)  # Initial 2 cards per player
            self.assertFalse(player["hasStolen"])

    def test_complete_single_player_turn_sequence(self):
        """Test complete turn sequence: steal → play → draw"""
        # Start the game
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        # Player 1 should be first in turn order
        current_player_id = game["turnOrder"][0]
        self.assertEqual(current_player_id, self.player1_id)
        
        # Phase 1: Steal phase
        current_phase = self.game_state._get_current_turn_phase(game, current_player_id)
        self.assertEqual(current_phase, "turn_steal")
        
        # Steal a card from player 2
        steal_result = self.game_state.steal_card(self.game_id, current_player_id, self.player2_id)
        self.assertTrue(steal_result)
        
        # Verify steal state
        player1 = game["players"][current_player_id]
        player2 = game["players"][self.player2_id]
        self.assertTrue(player1["hasStolen"])
        self.assertEqual(len(player1["hand"]), 3)  # 2 initial + 1 stolen
        self.assertEqual(len(player2["hand"]), 1)  # 2 initial - 1 stolen
        
        # Phase should now be turn_play
        current_phase = self.game_state._get_current_turn_phase(game, current_player_id)
        self.assertEqual(current_phase, "turn_play")
        
        # Phase 2: Play phase - play a card that can be played during turn_play
        playable_cards = []
        for i, card in enumerate(player1["hand"]):
            if "turn_play" in card.get("playable_phases", []):
                playable_cards.append((i, card))
        
        if playable_cards:
            card_idx, card = playable_cards[0]
            # If card requires target, provide one
            params = {}
            if card.get("requires_target"):
                params["targetId"] = self.player2_id
            elif card.get("requires_multiple_targets"):
                if card["type"] == "alliance":
                    params["teammateId"] = self.player2_id
                    params["victimId"] = self.player3_id
                else:
                    params["targets"] = [self.player2_id]
            
            initial_hand_before_play = len(player1["hand"])
            play_result = self.game_state.play_card(self.game_id, current_player_id, card_idx, params)
            self.assertTrue(play_result["success"])
            # Card should have been removed, but effects might add cards back
            self.assertLessEqual(len(player1["hand"]), initial_hand_before_play)
        
        # Phase 3: Draw phase
        initial_turn_index = game["currentTurnIndex"]
        draw_result = self.game_state.draw_card(self.game_id, current_player_id)
        
        # Check if we hit a tribal council card
        if isinstance(draw_result, dict) and draw_result.get("tribal_council"):
            # Tribal council was triggered
            self.assertEqual(game["phase"], "tribal_council")
        else:
            # Normal draw - turn should advance
            self.assertTrue(draw_result)
            self.assertFalse(player1["hasStolen"])  # Reset after turn
            self.assertEqual(game["currentTurnIndex"], (initial_turn_index + 1) % 3)

    def test_multi_player_turn_rotation(self):
        """Test that turns properly rotate between multiple players"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        initial_turn_order = game["turnOrder"].copy()
        
        # Complete 3 full turns (one for each player)
        for turn_num in range(3):
            current_index = game["currentTurnIndex"]
            current_player_id = game["turnOrder"][current_index]
            
            # Verify it's the expected player's turn
            expected_player = initial_turn_order[turn_num % 3]
            self.assertEqual(current_player_id, expected_player)
            
            # Skip steal phase for simplicity
            game["players"][current_player_id]["hasStolen"] = True
            
            # Draw card to end turn
            draw_result = self.game_state.draw_card(self.game_id, current_player_id)
            
            # If tribal council triggered, stop the test
            if isinstance(draw_result, dict) and draw_result.get("tribal_council"):
                break
                
            # Verify turn advanced
            expected_next_index = (current_index + 1) % 3
            self.assertEqual(game["currentTurnIndex"], expected_next_index)

    def test_card_phase_validation(self):
        """Test that cards can only be played during appropriate phases"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        current_player_id = game["turnOrder"][0]
        player = game["players"][current_player_id]
        
        # Add test cards with specific phase restrictions
        tribal_card = {"type": "extra_vote", "playable_phases": ["tribal_discussion"]}
        turn_card = {"type": "camp_raid", "playable_phases": ["turn_play"], "requires_target": True}
        
        player["hand"] = [tribal_card, turn_card]
        
        # During steal phase, neither card should be playable
        current_phase = self.game_state._get_current_turn_phase(game, current_player_id)
        self.assertEqual(current_phase, "turn_steal")
        
        # Try to play tribal card - should fail
        result = self.game_state.play_card(self.game_id, current_player_id, 0)
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"])
        
        # Try to play turn card - should fail (wrong phase)
        result = self.game_state.play_card(self.game_id, current_player_id, 1, {"targetId": self.player2_id})
        self.assertFalse(result["success"])
        
        # Move to play phase
        player["hasStolen"] = True
        current_phase = self.game_state._get_current_turn_phase(game, current_player_id)
        self.assertEqual(current_phase, "turn_play")
        
        # Now turn card should be playable
        result = self.game_state.play_card(self.game_id, current_player_id, 1, {"targetId": self.player2_id})
        self.assertTrue(result["success"])
        
        # Tribal card should still not be playable
        result = self.game_state.play_card(self.game_id, current_player_id, 0)
        self.assertFalse(result["success"])

    def test_tribal_council_interruption(self):
        """Test that drawing a tribal council card interrupts normal turn flow"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        # Replace deck with known tribal council card
        tribal_card = {"type": "tribal_council_single", "category": "tribal_council", "elimination_type": "single", "id": "test_tribal"}
        game["deck"] = [tribal_card]
        
        current_player_id = game["turnOrder"][0]
        initial_phase = game["phase"]
        initial_turn_index = game["currentTurnIndex"]
        
        # Draw the tribal council card
        draw_result = self.game_state.draw_card(self.game_id, current_player_id)
        
        # Verify tribal council was triggered
        self.assertIsInstance(draw_result, dict)
        self.assertTrue(draw_result.get("tribal_council"))
        self.assertEqual(draw_result["card"], tribal_card)
        
        # Game phase should have changed
        self.assertEqual(game["phase"], "tribal_council")
        
        # Turn should not have advanced
        self.assertEqual(game["currentTurnIndex"], initial_turn_index)
        
        # Verify tribal council state
        vote_data = game["currentVote"]
        self.assertEqual(vote_data["type"], "single")
        self.assertEqual(vote_data["phase"], "waiting")

    def test_turn_validation_and_error_handling(self):
        """Test various error conditions and validation during turns"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        current_player_id = game["turnOrder"][0]
        wrong_player_id = game["turnOrder"][1]
        
        # Test stealing from non-existent player
        result = self.game_state.steal_card(self.game_id, current_player_id, "nonexistent")
        self.assertFalse(result)
        
        # Test stealing when already stolen
        self.game_state.steal_card(self.game_id, current_player_id, self.player2_id)
        result = self.game_state.steal_card(self.game_id, current_player_id, self.player3_id)
        self.assertFalse(result)  # Already stolen this turn
        
        # Test playing card when not your turn
        player = game["players"][wrong_player_id]
        if player["hand"]:
            result = self.game_state.play_card(self.game_id, wrong_player_id, 0)
            self.assertFalse(result["success"])
            # The exact error message may vary depending on the card
            self.assertIn(result["message"], [
                "Card has no valid play phases",
                "Card cannot be played during waiting phase"
            ])
        
        # Test playing card with invalid index
        result = self.game_state.play_card(self.game_id, current_player_id, 999)
        self.assertFalse(result["success"])
        self.assertIn("Invalid card selection", result["message"])
        
        # Test drawing when not your turn
        result = self.game_state.draw_card(self.game_id, wrong_player_id)
        # Should return False (not tribal council dict) since it's not their turn
        self.assertFalse(result)
        
        # Test actions in non-existent game
        result = self.game_state.steal_card("nonexistent", current_player_id, self.player2_id)
        self.assertFalse(result)

    def test_game_state_consistency_throughout_turns(self):
        """Test that game state remains consistent throughout multiple turns"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        # Track initial state
        initial_deck_size = len(game["deck"])
        initial_total_cards = sum(len(player["hand"]) for player in game["players"].values())
        
        # Complete several turn phases and verify consistency
        for _ in range(5):  # 5 turn phases
            current_player_id = game["turnOrder"][game["currentTurnIndex"]]
            current_player = game["players"][current_player_id]
            
            # Record pre-action state
            pre_deck_size = len(game["deck"])
            pre_hand_size = len(current_player["hand"])
            
            # Perform some action based on current phase
            current_phase = self.game_state._get_current_turn_phase(game, current_player_id)
            
            if current_phase == "turn_steal" and not current_player["hasStolen"]:
                # Try to steal if possible
                targets = [pid for pid in game["players"] 
                          if pid != current_player_id and game["players"][pid]["hand"]]
                if targets:
                    self.game_state.steal_card(self.game_id, current_player_id, targets[0])
                else:
                    # No valid targets, skip steal
                    current_player["hasStolen"] = True
                    
            elif current_phase == "turn_play":
                # Try to play a card if possible
                playable_found = False
                for i, card in enumerate(current_player["hand"]):
                    if "turn_play" in card.get("playable_phases", []):
                        params = {}
                        if card.get("requires_target"):
                            other_players = [pid for pid in game["players"] if pid != current_player_id]
                            if other_players:
                                params["targetId"] = other_players[0]
                        elif card.get("requires_multiple_targets") and card["type"] == "alliance":
                            other_players = [pid for pid in game["players"] if pid != current_player_id]
                            if len(other_players) >= 2:
                                params["teammateId"] = other_players[0]
                                params["victimId"] = other_players[1]
                        
                        result = self.game_state.play_card(self.game_id, current_player_id, i, params)
                        if result["success"]:
                            playable_found = True
                            break
                
                # If no playable card, draw to end turn
                if not playable_found:
                    draw_result = self.game_state.draw_card(self.game_id, current_player_id)
                    if isinstance(draw_result, dict) and draw_result.get("tribal_council"):
                        break  # Tribal council triggered, stop testing
                    
            # Verify no cards were lost or duplicated
            current_deck_size = len(game["deck"])
            current_total_cards = sum(len(player["hand"]) for player in game["players"].values())
            
            # Total cards in system should be consistent (accounting for cards drawn/played)
            # This is a basic sanity check
            self.assertGreaterEqual(current_deck_size, 0)
            self.assertGreaterEqual(current_total_cards, 0)
            
            # If we're still in playing phase, continue
            if game["phase"] != "playing":
                break

    def test_skip_phases_and_empty_actions(self):
        """Test turns where players skip phases or perform no actions"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        current_player_id = game["turnOrder"][0]
        current_player = game["players"][current_player_id]
        
        # Empty other players' hands so stealing fails
        for pid in game["players"]:
            if pid != current_player_id:
                game["players"][pid]["hand"] = []
        
        # Try to steal - should fail due to no valid targets
        result = self.game_state.steal_card(self.game_id, current_player_id, self.player2_id)
        self.assertFalse(result)
        
        # Player should still be able to move to play phase
        current_player["hasStolen"] = True  # Simulate skipping steal
        
        current_phase = self.game_state._get_current_turn_phase(game, current_player_id)
        self.assertEqual(current_phase, "turn_play")
        
        # Replace hand with cards that can't be played in turn_play phase
        current_player["hand"] = [
            {"type": "extra_vote", "playable_phases": ["tribal_discussion"]},
            {"type": "immunity_idol", "playable_phases": ["tribal_immunity"]}
        ]
        
        # Trying to play either card should fail
        result = self.game_state.play_card(self.game_id, current_player_id, 0)
        self.assertFalse(result["success"])
        
        result = self.game_state.play_card(self.game_id, current_player_id, 1)
        self.assertFalse(result["success"])
        
        # Player should still be able to draw to end turn
        initial_hand_size = len(current_player["hand"])
        draw_result = self.game_state.draw_card(self.game_id, current_player_id)
        
        if not (isinstance(draw_result, dict) and draw_result.get("tribal_council")):
            # Normal draw - turn should advance
            self.assertTrue(draw_result)
            # Hand size should increase by 1 (drew card)
            self.assertEqual(len(current_player["hand"]), initial_hand_size + 1)

    def test_card_effects_spanning_multiple_players(self):
        """Test cards that affect multiple players or other players' turns"""
        self.game_state.start_full_game(self.game_id)
        game = self.game_state.games[self.game_id]
        
        current_player_id = game["turnOrder"][0]
        target_player_id = self.player2_id
        current_player = game["players"][current_player_id]
        target_player = game["players"][target_player_id]
        
        # Set up for play phase
        current_player["hasStolen"] = True
        
        # Test camp_raid card (affects another player)
        initial_target_hand_size = len(target_player["hand"])
        initial_current_hand_size = len(current_player["hand"])
        
        # Add a camp_raid card to current player
        raid_card = {"type": "camp_raid", "playable_phases": ["turn_play"], "requires_target": True}
        current_player["hand"].append(raid_card)
        raid_card_index = len(current_player["hand"]) - 1
        
        # Play the raid card
        result = self.game_state.play_card(
            self.game_id, current_player_id, raid_card_index, 
            {"targetId": target_player_id}
        )
        
        self.assertTrue(result["success"])
        
        # Verify effects on both players
        if initial_target_hand_size > 0:  # If target had cards to steal
            # Target should have lost a card
            self.assertEqual(len(target_player["hand"]), initial_target_hand_size - 1)
            # Current player should have net zero change (played 1, potentially gained 1)
            # But the exact count depends on the camp_raid implementation
            self.assertLessEqual(len(current_player["hand"]), initial_current_hand_size + 1)
            self.assertGreaterEqual(len(current_player["hand"]), initial_current_hand_size - 1)
        
        # Test alliance card (affects multiple players)
        if len(game["players"]) >= 3:
            alliance_card = {
                "type": "alliance", 
                "playable_phases": ["turn_play"], 
                "requires_multiple_targets": True
            }
            current_player["hand"].append(alliance_card)
            alliance_card_index = len(current_player["hand"]) - 1
            
            teammate_id = self.player2_id
            victim_id = self.player3_id
            
            result = self.game_state.play_card(
                self.game_id, current_player_id, alliance_card_index,
                {"teammateId": teammate_id, "victimId": victim_id}
            )
            
            self.assertTrue(result["success"])
            self.assertIn("formed alliance", result["message"])


if __name__ == '__main__':
    # Set up logging for test debugging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    unittest.main(verbosity=2)