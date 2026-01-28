#!/usr/bin/env python3
"""
Tribal Council Trigger Tests for Survivor App

Tests the automatic triggering of tribal council when tribal council cards are drawn.
Validates proper game phase transitions and tribal council initialization.
"""

import unittest
import tempfile
import os
import sys
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState

class TestTribalCouncilTriggers(unittest.TestCase):
    """Test automatic tribal council triggering when tribal council cards are drawn"""

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
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def _create_tribal_council_card(self, card_type="tribal_council_single"):
        """Helper to create a tribal council card"""
        elimination_type = "single" if "single" in card_type else "double"
        return {
            "type": card_type,
            "category": "tribal_council",
            "name": f"Tribal Council ({elimination_type.title()})",
            "description": f"A {elimination_type} elimination tribal council",
            "elimination_type": elimination_type
        }
    
    def _add_card_to_deck_top(self, card):
        """Helper to add a card to the top of the deck"""
        game = self.gs.games[self.game_id] 
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, card)  # Add to front (top) of deck
    
    def test_drawing_tribal_council_single_triggers_tribal_council(self):
        """Test that drawing a tribal_council_single card triggers tribal council"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Add tribal council card to top of deck
        tribal_card = self._create_tribal_council_card("tribal_council_single")
        self._add_card_to_deck_top(tribal_card)
        
        # Verify game is in playing phase before drawing
        self.assertEqual(game["phase"], "playing")
        self.assertNotIn("currentVote", game)
        
        # Draw the card (this should trigger tribal council)
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Verify tribal council was triggered
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], "tribal_council", 
            "Game phase should change to tribal_council when tribal card is drawn")
        
        self.assertIn("currentVote", updated_game, 
            "currentVote should be initialized when tribal council starts")
        
        # Verify tribal council is properly initialized
        vote_data = updated_game["currentVote"]
        self.assertEqual(vote_data["phase"], "tribal_announcement", 
            "Tribal council should start in announcement phase")
        self.assertIn("votes", vote_data)
        self.assertIn("hasVoted", vote_data)
        self.assertIn("eliminatedPlayers", vote_data)
        
    def test_drawing_tribal_council_double_triggers_tribal_council(self):
        """Test that drawing a tribal_council_double card triggers tribal council"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Add double elimination tribal council card to deck
        tribal_card = self._create_tribal_council_card("tribal_council_double")
        self._add_card_to_deck_top(tribal_card)
        
        # Verify game is in playing phase
        self.assertEqual(game["phase"], "playing")
        
        # Draw the card
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Verify tribal council was triggered
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], "tribal_council")
        self.assertIn("currentVote", updated_game)
        
        # Verify double elimination is set correctly
        vote_data = updated_game["currentVote"]
        self.assertTrue(vote_data.get("doubleElimination", False),
            "Double elimination should be set for tribal_council_double")
    
    def test_drawing_non_tribal_cards_does_not_trigger_tribal_council(self):
        """Test that drawing non-tribal cards does not trigger tribal council"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Add a regular action card to deck
        action_card = {
            "type": "the_spy_shack",
            "category": "action",
            "name": "The Spy Shack", 
            "description": "Look at a player's hand and steal one card",
            "playable_phases": ["turn_play"],
            "requires_target": True,
            "requires_multiple_targets": False,
            "requires_confirmation": False,
            "reactive_only": False,
            "count": 3
        }
        self._add_card_to_deck_top(action_card)
        
        # Verify game is in playing phase
        original_phase = game["phase"]
        self.assertEqual(original_phase, "playing")
        
        # Draw the card
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Verify game is still in playing phase (no tribal council triggered)
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], original_phase,
            "Game phase should not change when drawing non-tribal cards")
        
        self.assertNotIn("currentVote", updated_game,
            "currentVote should not be initialized for non-tribal cards")
        
        # Verify card was added to player's hand
        player = updated_game["players"][current_player]
        self.assertIn(action_card, player["hand"], 
            "Action card should be added to player's hand")
    
    def test_tribal_advantage_cards_do_not_trigger_tribal_council(self):
        """Test that tribal advantage cards don't trigger tribal council when drawn"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Add tribal advantage card (not tribal_council category)
        advantage_card = {
            "type": "immunity_idol",
            "category": "tribal_advantage",  # This is NOT tribal_council category
            "name": "Immunity Idol",
            "description": "Play during tribal council to become immune",
            "playable_phases": ["tribal_immunity"],
            "requires_target": False,
            "requires_multiple_targets": False,
            "requires_confirmation": True,
            "reactive_only": False,
            "count": 4
        }
        self._add_card_to_deck_top(advantage_card)
        
        # Draw the card
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Should not trigger tribal council
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], "playing",
            "Tribal advantage cards should not trigger tribal council")
        self.assertNotIn("currentVote", updated_game,
            "currentVote should not be created for tribal advantage cards")
    
    def test_vote_cards_do_not_trigger_tribal_council(self):
        """Test that vote cards don't trigger tribal council when drawn"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Add vote card
        vote_card = {
            "type": "vote",
            "category": "vote",
            "name": "Vote",
            "description": "Cast a vote at tribal council",
            "playable_phases": ["tribal_voting"],
            "requires_target": True,
            "requires_multiple_targets": False,
            "requires_confirmation": False,
            "reactive_only": False,
            "count": 6
        }
        self._add_card_to_deck_top(vote_card)
        
        # Draw the card
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Should not trigger tribal council
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], "playing")
        self.assertNotIn("currentVote", updated_game)
    
    def test_tribal_council_initialization_properties(self):
        """Test that tribal council is initialized with correct properties"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Test both single and double elimination
        for elimination_type in ["single", "double"]:
            with self.subTest(elimination_type=elimination_type):
                # Reset game state
                game["phase"] = "playing"
                if "currentVote" in game:
                    del game["currentVote"]
                
                # Add appropriate tribal council card
                card_type = f"tribal_council_{elimination_type}"
                tribal_card = self._create_tribal_council_card(card_type)
                self._add_card_to_deck_top(tribal_card)
                
                # Draw the card to trigger tribal council
                result = self.gs.draw_card(self.game_id, current_player)
                self.assertTrue(result["success"])
                
                updated_game = self.gs.games[self.game_id]
                vote_data = updated_game["currentVote"]
                
                # Verify all required properties are initialized
                required_properties = [
                    "phase", "votes", "hasVoted", "eliminatedPlayers", 
                    "tribalAdvantages", "immunityPlayers"
                ]
                
                for prop in required_properties:
                    self.assertIn(prop, vote_data, 
                        f"Tribal council should have '{prop}' property")
                
                # Verify elimination type is set correctly
                if elimination_type == "double":
                    self.assertTrue(vote_data.get("doubleElimination", False),
                        "Double elimination should be true for double tribal council")
                else:
                    self.assertFalse(vote_data.get("doubleElimination", False),
                        "Double elimination should be false for single tribal council")
    
    def test_multiple_tribal_cards_in_sequence(self):
        """Test behavior when multiple tribal council cards are drawn in sequence"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        # Add multiple tribal cards to deck
        tribal_card1 = self._create_tribal_council_card("tribal_council_single")
        tribal_card2 = self._create_tribal_council_card("tribal_council_double")
        
        self._add_card_to_deck_top(tribal_card2)  # This will be drawn second
        self._add_card_to_deck_top(tribal_card1)  # This will be drawn first
        
        # Draw first tribal card
        result1 = self.gs.draw_card(self.game_id, current_player)
        self.assertTrue(result1["success"])
        
        updated_game = self.gs.games[self.game_id]
        self.assertEqual(updated_game["phase"], "tribal_council")
        
        # Should not be able to draw another card while in tribal council
        result2 = self.gs.draw_card(self.game_id, current_player)
        
        # This should either fail or not trigger another tribal council
        # (depends on implementation - some systems prevent drawing during tribal)
        if result2["success"]:
            # If it succeeds, should still be in same tribal council
            final_game = self.gs.games[self.game_id]
            self.assertEqual(final_game["phase"], "tribal_council")
        else:
            # Should provide reasonable error message about phase
            self.assertIn("tribal", result2["message"].lower())
    
    def test_tribal_council_card_drawn_message_content(self):
        """Test that drawing tribal council cards provides appropriate feedback"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        game["currentPlayer"] = current_player
        
        tribal_card = self._create_tribal_council_card("tribal_council_single")
        self._add_card_to_deck_top(tribal_card)
        
        result = self.gs.draw_card(self.game_id, current_player)
        
        self.assertTrue(result["success"])
        
        # Message should indicate tribal council was triggered
        message = result["message"].lower()
        tribal_keywords = ["tribal", "council", "elimination", "vote"]
        
        has_tribal_keyword = any(keyword in message for keyword in tribal_keywords)
        self.assertTrue(has_tribal_keyword,
            f"Draw message should mention tribal council: {result['message']}")

if __name__ == '__main__':
    print("Running Tribal Council Trigger Tests...")
    unittest.main(verbosity=2)