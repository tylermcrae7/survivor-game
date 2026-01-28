#!/usr/bin/env python3
"""
Negative Phase Enforcement Tests for Survivor App

Tests that cards CANNOT be played in wrong phases, validating proper rule enforcement.
Focuses on phase validation and rejection scenarios with specific error messages.
"""

import unittest
import tempfile
import os
import sys
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState

class TestPhaseEnforcement(unittest.TestCase):
    """Test that cards are properly rejected when played in wrong phases"""

    def setUp(self):
        """Set up test environment with clean temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        self.gs = GameState()
        
        # Create a standard 4-player game for testing
        self.game_id = self.gs.create_game()
        self.player_ids = []
        colors = ["red", "blue", "green", "yellow"]
        for i in range(4):
            player_id = self.gs.add_player(self.game_id, f"Player{i+1}", colors[i])
            self.player_ids.append(player_id)
        
        # Start the game to get to playing phase
        self.gs.start_full_game(self.game_id)
        
        # Set all players to have completed their steal phase for card testing
        game = self.gs.games[self.game_id]
        for player_id in self.player_ids:
            game["players"][player_id]["hasStolen"] = True
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def _add_card_to_player_hand(self, player_id, card_type):
        """Helper to add a specific card to a player's hand"""
        game = self.gs.games[self.game_id]
        card_def = self.gs.rules_engine.get_card_definition(card_type)
        
        if not card_def:
            # Create a basic card for testing if definition not found
            card = {
                "type": card_type,
                "category": "tribal_advantage",
                "name": card_type.title().replace('_', ' '),
                "description": f"Test card: {card_type}",
                "playable_phases": ["tribal_discussion"],
                "requires_target": False,
                "requires_multiple_targets": False,
                "requires_confirmation": True,
                "reactive_only": False,
                "count": 1
            }
        else:
            card = {
                "type": card_type,
                "category": card_def["category"],
                "name": card_def["name"], 
                "description": card_def["description"],
                "playable_phases": card_def["playable_phases"],
                "requires_target": card_def["requires_target"],
                "requires_multiple_targets": card_def["requires_multiple_targets"],
                "requires_confirmation": card_def["requires_confirmation"],
                "reactive_only": card_def["reactive_only"],
                "count": card_def["count"]
            }
        
        game["players"][player_id]["hand"].append(card)
        return len(game["players"][player_id]["hand"]) - 1  # Return card index

    def test_control_the_vote_cannot_be_played_during_turn_play(self):
        """Test control_the_vote CANNOT be played during turn_play phase"""
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "control_the_vote")
        
        # Should fail during turn_play phase
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
        
    def test_im_the_leader_now_cannot_be_played_during_turn_play(self):
        """Test im_the_leader_now CANNOT be played during turn_play phase"""
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "im_the_leader_now")
        
        # Should fail during turn_play phase
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_sorry_for_you_cannot_be_played_outside_reactive_theft(self):
        """Test sorry_for_you CANNOT be played outside reactive_theft context"""
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "sorry_for_you")
        
        # Should fail during turn_play phase (not reactive context)
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_immunity_idol_cannot_be_played_during_turn_phases(self):
        """Test immunity_idol CANNOT be played during regular turn phases"""
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "immunity_idol")
        
        # Should fail during turn_play phase
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_idol_nullifier_cannot_be_played_during_turn_phases(self):
        """Test idol_nullifier CANNOT be played during regular turn phases"""  
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "idol_nullifier")
        
        # Should fail during turn_play phase
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_extra_vote_cannot_be_played_during_turn_phases(self):
        """Test extra_vote CANNOT be played during regular turn phases"""
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "extra_vote")
        
        # Should fail during turn_play phase
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_vote_cards_cannot_be_played_during_turn_phases(self):
        """Test vote cards CANNOT be played outside tribal council"""
        player_id = self.player_ids[0]
        card_idx = self._add_card_to_player_hand(player_id, "vote")
        
        # Should fail during turn_play phase
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_action_cards_cannot_be_played_during_tribal_phases(self):
        """Test action cards CANNOT be played during tribal council phases"""
        player_id = self.player_ids[0]
        
        # Manually set game to tribal council phase
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {
            "phase": "tribal_discussion",
            "votes": {},
            "hasVoted": {},
            "eliminatedPlayers": [],
            "tribalAdvantages": {},
            "immunityPlayers": set()
        }
        
        # Try to play an action card (should fail)
        card_idx = self._add_card_to_player_hand(player_id, "the_spy_shack")
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        self.assertFalse(result["success"])
        self.assertIn("cannot be played during", result["message"].lower())
    
    def test_phase_validation_provides_specific_error_messages(self):
        """Test that phase validation provides specific, helpful error messages"""
        player_id = self.player_ids[0]
        
        # Set the current player to the test player to avoid "not active" errors
        game = self.gs.games[self.game_id]
        game["currentPlayer"] = player_id
        
        # Test different types of cards with expected error patterns
        test_cases = [
            ("control_the_vote", "tribal_discussion"),  # Should only work in tribal
            ("sorry_for_you", "reactive_theft"),       # Should only work reactively
            ("immunity_idol", "tribal_immunity"),      # Should only work in immunity phase
            ("the_spy_shack", "turn_play")            # Should only work in turn_play when it's their play phase
        ]
        
        for card_type, expected_phase in test_cases:
            with self.subTest(card_type=card_type):
                card_idx = self._add_card_to_player_hand(player_id, card_type)
                result = self.gs.play_card(self.game_id, player_id, card_idx)
                
                self.assertFalse(result["success"], 
                    f"{card_type} should not be playable in current phase")
                
                # Check for phase-related error messages (various forms)
                error_msg = result["message"].lower()
                phase_error_indicators = [
                    "cannot be played during", 
                    "phase",
                    "waiting",
                    "turn",
                    "tribal"
                ]
                
                has_phase_error = any(indicator in error_msg for indicator in phase_error_indicators)
                self.assertTrue(has_phase_error,
                    f"{card_type} should provide phase validation error message: {result['message']}")
    
    def test_wrong_player_turn_rejection(self):
        """Test that cards cannot be played when it's not the player's turn"""
        # Set current player to player 0
        game = self.gs.games[self.game_id]
        game["currentPlayer"] = self.player_ids[0]
        
        # Try to play card as different player (should fail)
        wrong_player = self.player_ids[1]
        card_idx = self._add_card_to_player_hand(wrong_player, "the_spy_shack")
        result = self.gs.play_card(self.game_id, wrong_player, card_idx)
        
        # Should fail because it's not their turn
        self.assertFalse(result["success"])
        # Error should mention turn, player, phase, or waiting validation
        error_msg = result["message"].lower()
        turn_related_error = any(term in error_msg for term in ["turn", "player", "active", "phase", "waiting", "cannot"])
        self.assertTrue(turn_related_error, 
            f"Error should mention turn/phase validation: {result['message']}")
    
    def test_eliminated_player_cannot_play_cards(self):
        """Test that eliminated players cannot play cards"""
        player_id = self.player_ids[0]
        
        # Eliminate player
        game = self.gs.games[self.game_id]
        game["players"][player_id]["isActive"] = False
        
        # Try to play card as eliminated player
        card_idx = self._add_card_to_player_hand(player_id, "the_spy_shack")
        result = self.gs.play_card(self.game_id, player_id, card_idx)
        
        # Should fail
        self.assertFalse(result["success"])
        self.assertIn("not active", result["message"].lower())

if __name__ == '__main__':
    print("Running Negative Phase Enforcement Tests...")
    unittest.main(verbosity=2)