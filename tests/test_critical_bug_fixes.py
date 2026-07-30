#!/usr/bin/env python3
"""
Critical Bug Fixes Test Suite for Survivor App

Comprehensive tests for recently identified and fixed critical bugs:
1. Tribal draw trigger tests
2. Phase mapping tests  
3. Card timing tests
4. Idol/Nullifier interaction tests
5. Tribal composition tests
6. Numbers Game range tests

This test suite validates proper rule compliance and edge case handling.
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import shutil
import random
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from survivor_server import GameState
from rules_engine import SurvivorRulesEngine

class TestCriticalBugFixes(unittest.TestCase):
    """Test critical bug fixes for proper rule compliance"""

    def setUp(self):
        """Set up test environment with clean temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        self.gs = GameState()
        self.rules_engine = SurvivorRulesEngine()
        
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

    # Test 1: Tribal Draw Trigger Tests
    
    def test_tribal_council_single_draw_triggers_correct_phase(self):
        """Test that drawing tribal_council_single properly triggers tribal council phase"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        # draw_card enforces Steal -> Play -> Draw
        game["players"][current_player]["hasStolen"] = True
        
        # Create and add tribal_council_single card to deck
        tribal_card = {
            "type": "tribal_council_single",
            "category": "tribal_council",
            "name": "Tribal Council - Single Elimination",
            "description": "Tribal Council - Single Elimination",
            "elimination_type": "single"
        }
        
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, tribal_card)  # draw_card takes from the top (index 0)
        
        # Verify initial state
        self.assertEqual(game["phase"], "playing")
        self.assertEqual(game["currentVote"]["phase"], "waiting")
        
        # Draw the tribal council card
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Verify tribal council was properly triggered (draw_card returns different format)
        self.assertIsInstance(result, dict, "Draw should return a dictionary")
        self.assertTrue(result.get("tribal_triggered", False), f"Draw should trigger tribal council: {result}")
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], "tribal_council", 
                        "Phase should change to tribal_council")
        self.assertIn("currentVote", updated_game, 
                     "currentVote should be initialized")
        
        # Verify currentVote.type is set correctly for single elimination
        vote_data = updated_game["currentVote"]
        self.assertEqual(vote_data.get("type"), "single",
                        "currentVote.type should be 'single' for tribal_council_single")

    def test_tribal_council_double_draw_triggers_correct_phase(self):
        """Test that drawing tribal_council_double properly triggers tribal council phase"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        # draw_card enforces Steal -> Play -> Draw
        game["players"][current_player]["hasStolen"] = True
        
        # Create and add tribal_council_double card to deck
        tribal_card = {
            "type": "tribal_council_double",
            "category": "tribal_council",
            "name": "Tribal Council - Double Elimination",
            "description": "Tribal Council - Double Elimination",
            "elimination_type": "double"
        }
        
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, tribal_card)  # draw_card takes from the top (index 0)
        
        # Verify initial state
        self.assertEqual(game["phase"], "playing")
        
        # Draw the tribal council card
        result = self.gs.draw_card(self.game_id, current_player)
        
        # Verify tribal council was properly triggered
        self.assertTrue(result.get("tribal_triggered", False))
        updated_game = self.gs.games[self.game_id]
        
        self.assertEqual(updated_game["phase"], "tribal_council")
        self.assertIn("currentVote", updated_game)
        
        # Verify currentVote.type is set correctly for double elimination
        vote_data = updated_game["currentVote"]
        self.assertEqual(vote_data.get("type"), "double",
                        "currentVote.type should be 'double' for tribal_council_double")

    # Test 2: Phase Mapping Tests

    def test_phase_mapping_announcement_returns_tribal_discussion(self):
        """Test that tribal announcement phase maps to tribal_discussion"""
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "announcement"}
        
        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        self.assertEqual(phase, "tribal_discussion",
                        "Announcement phase should map to tribal_discussion")

    def test_phase_mapping_advantage_play_returns_tribal_discussion(self):
        """Test that tribal advantage_play phase maps to tribal_discussion"""
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "advantage_play"}
        
        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        self.assertEqual(phase, "tribal_discussion",
                        "Advantage_play phase should map to tribal_discussion")

    def test_phase_mapping_discussion_returns_tribal_discussion(self):
        """Test that tribal discussion phase maps to tribal_discussion"""
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "discussion"}
        
        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        self.assertEqual(phase, "tribal_discussion",
                        "Discussion phase should map to tribal_discussion")

    def test_phase_mapping_unknown_phase_falls_back_to_discussion(self):
        """
        An unrecognised tribal sub-phase must not crash card validation — it falls
        back to tribal_discussion. ("voting_start" is not a real phase; the real
        sequence is announcement, advantage_play, discussion, voting, immunity, reveal.)
        """
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "voting_start"}

        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        self.assertEqual(phase, "tribal_discussion",
                        "Unknown tribal sub-phases should fall back to tribal_discussion")

    def test_phase_mapping_voting_returns_tribal_voting(self):
        """Test that tribal voting phase maps to tribal_voting"""
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "voting"}
        
        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        self.assertEqual(phase, "tribal_voting",
                        "Voting phase should map to tribal_voting")

    def test_phase_mapping_immunity_returns_tribal_immunity(self):
        """Test that tribal immunity phase maps to tribal_immunity"""
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "immunity"}
        
        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        self.assertEqual(phase, "tribal_immunity",
                        "Immunity phase should map to tribal_immunity")

    # Test 3: Card Timing Tests

    def test_control_the_vote_fails_during_turn_play(self):
        """Test that control_the_vote fails during turn_play phase"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Set up turn_play phase
        game["phase"] = "playing"
        # draw_card enforces Steal -> Play -> Draw
        game["players"][player_id]["hasStolen"] = True
        game["players"][player_id]["hasStolen"] = True  # This makes it turn_play
        
        control_vote_card = self.rules_engine.get_card_definition("control_the_vote")
        self.assertIsNotNone(control_vote_card, "control_the_vote card should exist")
        
        # Test that card is not playable during turn_play
        can_play, reason = self.rules_engine.is_card_playable(game, player_id, control_vote_card)
        self.assertFalse(can_play, "control_the_vote should not be playable during turn_play")
        self.assertIn("turn_play", reason, "Error reason should mention turn_play phase")

    def test_control_the_vote_succeeds_during_tribal_discussion(self):
        """Test that control_the_vote succeeds during tribal_discussion phase"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Set up tribal_discussion phase
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "discussion"}
        
        control_vote_card = self.rules_engine.get_card_definition("control_the_vote")
        
        # Test that card is playable during tribal_discussion
        can_play, reason = self.rules_engine.is_card_playable(game, player_id, control_vote_card)
        self.assertTrue(can_play, f"control_the_vote should be playable during tribal_discussion: {reason}")

    def test_im_the_leader_now_fails_during_turn_play(self):
        """Test that im_the_leader_now fails during turn_play phase"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Set up turn_play phase
        game["phase"] = "playing"
        # draw_card enforces Steal -> Play -> Draw
        game["players"][player_id]["hasStolen"] = True
        game["players"][player_id]["hasStolen"] = True
        
        leader_card = self.rules_engine.get_card_definition("im_the_leader_now")
        self.assertIsNotNone(leader_card, "im_the_leader_now card should exist")
        
        # Test that card is not playable during turn_play
        can_play, reason = self.rules_engine.is_card_playable(game, player_id, leader_card)
        self.assertFalse(can_play, "im_the_leader_now should not be playable during turn_play")
        self.assertIn("turn_play", reason, "Error reason should mention turn_play phase")

    def test_im_the_leader_now_succeeds_during_tribal_discussion(self):
        """Test that im_the_leader_now succeeds during tribal_discussion phase"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Set up tribal_discussion phase
        game["phase"] = "tribal_council"
        game["currentVote"] = {"phase": "discussion"}
        
        leader_card = self.rules_engine.get_card_definition("im_the_leader_now")
        
        # Test that card is playable during tribal_discussion
        can_play, reason = self.rules_engine.is_card_playable(game, player_id, leader_card)
        self.assertTrue(can_play, f"im_the_leader_now should be playable during tribal_discussion: {reason}")

    # Test 4: Idol/Nullifier Interaction Test

    def test_idol_nullifier_removes_immunity_protection(self):
        """Test that idol_nullifier removes immunity idol protection"""
        game = self.gs.games[self.game_id]
        idol_player = self.player_ids[0]
        nullifier_player = self.player_ids[1]
        target_player = self.player_ids[2]
        
        # Set up tribal council phase
        game["phase"] = "tribal_council"
        game["currentVote"] = {
            "phase": "immunity",
            "votes": {idol_player: target_player},  # Cast vote first
            "hasVoted": {idol_player: True}
        }
        
        # Initialize player protection status
        for player_id in self.player_ids:
            game["players"][player_id]["immunityIdolProtection"] = False
            game["players"][player_id]["idolNullified"] = False
        
        # Step 1: Cast votes (already done above)
        
        # Step 2: Play immunity idol to protect target
        idol_card = self.rules_engine.get_card_definition("immunity_idol")
        params = {"targetId": target_player}
        
        result = self.rules_engine.execute_card_effect(game, idol_player, idol_card, params)
        self.assertTrue(result["success"], "Immunity idol should play successfully")
        
        # Verify target is protected
        self.assertTrue(game["players"][target_player]["immunityIdolProtection"],
                       "Target should have immunity idol protection")
        
        # Step 3: Play idol nullifier against target
        nullifier_card = self.rules_engine.get_card_definition("idol_nullifier")
        params = {"targetId": target_player}
        
        result = self.rules_engine.execute_card_effect(game, nullifier_player, nullifier_card, params)
        self.assertTrue(result["success"], "Idol nullifier should play successfully")
        
        # Step 4: Verify target is NOT protected after nullifier
        self.assertFalse(game["players"][target_player]["immunityIdolProtection"],
                        "Target should NOT have immunity idol protection after nullifier")
        self.assertTrue(game["players"][target_player]["idolNullified"],
                       "Target should have idolNullified flag set")

    # Test 5: Tribal Composition Tests

    def test_tribal_composition_3_players(self):
        """Test that 3-player games get correct tribal card distribution"""
        tribal_cards = self.rules_engine._create_tribal_council_cards(3)
        
        single_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_single")
        double_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_double")
        
        self.assertEqual(single_count, 4, "3-player game should have 4 single elimination cards")
        self.assertEqual(double_count, 0, "3-player game should have 0 double elimination cards")

    def test_tribal_composition_4_players(self):
        """Test that 4-player games get correct tribal card distribution"""
        tribal_cards = self.rules_engine._create_tribal_council_cards(4)
        
        single_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_single")
        double_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_double")
        
        self.assertEqual(single_count, 2, "4-player game should have 2 single elimination cards")
        self.assertEqual(double_count, 2, "4-player game should have 2 double elimination cards")

    def test_tribal_composition_5_players(self):
        """Test that 5-player games get correct tribal card distribution"""
        tribal_cards = self.rules_engine._create_tribal_council_cards(5)
        
        single_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_single")
        double_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_double")
        
        self.assertEqual(single_count, 2, "5-player game should have 2 single elimination cards")
        self.assertEqual(double_count, 3, "5-player game should have 3 double elimination cards")

    def test_tribal_composition_6_players(self):
        """Test that 6-player games get correct tribal card distribution"""
        tribal_cards = self.rules_engine._create_tribal_council_cards(6)
        
        single_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_single")
        double_count = sum(1 for card in tribal_cards if card["type"] == "tribal_council_double")
        
        self.assertEqual(single_count, 0, "6-player game should have 0 single elimination cards")
        self.assertEqual(double_count, 5, "6-player game should have 5 double elimination cards")

    def test_tribal_composition_total_cards_correct(self):
        """Test that total tribal cards match expected count for each player count"""
        # Official rules table: 3p=4+0, 4p=2+2, 5p=2+3, 6p=0+5
        expected_totals = {3: 4, 4: 4, 5: 5, 6: 5}
        
        for player_count in [3, 4, 5, 6]:
            with self.subTest(player_count=player_count):
                tribal_cards = self.rules_engine._create_tribal_council_cards(player_count)
                expected_total = expected_totals[player_count]
                
                self.assertEqual(len(tribal_cards), expected_total,
                               f"{player_count}-player game should have {expected_total} tribal cards")

    # Test 6: Numbers Game — official rules

    def test_numbers_game_uses_the_official_one_to_five_range(self):
        """
        Official: "all players (including you) will show 1-5 fingers." The old
        implementation rolled 1-3 on the server; now every pick is a real player
        input validated to the 1-5 range.
        """
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        game["phase"] = "playing"
        game["players"][player_id]["hasStolen"] = True

        numbers_game_card = self.rules_engine.get_card_definition("reward_challenge_its_a_numbers_game")
        self.assertIsNotNone(numbers_game_card, "Numbers game card should exist")

        # Playing the card starts a real interaction rather than rolling dice
        result = self.rules_engine.execute_card_effect(game, player_id, numbers_game_card, {})
        self.assertTrue(result["success"])
        self.assertEqual(result["start_interaction"], "numbers_game")

        from interactions import interaction_engine
        interaction_engine.start(game, player_id, "numbers_game", {})

        # 1-5 accepted, everything else rejected
        for bad in (0, 6, -1, "banana", None):
            reply = interaction_engine.act(game, player_id, "pick", bad)
            self.assertFalse(reply["success"], f"{bad!r} should be rejected")
        reply = interaction_engine.act(game, player_id, "pick", 5)
        self.assertTrue(reply["success"], reply.get("message"))
        game["interaction"] = None

    def test_numbers_game_lowest_unique_wins(self):
        """Official: "The player who shows the lowest UNIQUE number" wins."""
        game = self.gs.games[self.game_id]
        from interactions import interaction_engine
        interaction_engine.start(game, self.player_ids[0], "numbers_game", {})

        picks = {self.player_ids[0]: 1, self.player_ids[1]: 1,
                 self.player_ids[2]: 4, self.player_ids[3]: 2}
        for pid, n in picks.items():
            interaction_engine.act(game, pid, "pick", n)

        interaction = game["interaction"]
        # 1 is duplicated, so 2 is the lowest unique — not 1
        self.assertEqual(interaction["winnerId"], self.player_ids[3])
        self.assertEqual(interaction["phase"], "choose_victim")
        game["interaction"] = None

    def test_tribal_council_initialization_all_required_fields(self):
        """Test that tribal council initialization includes all required fields"""
        game = self.gs.games[self.game_id]
        current_player = self.player_ids[0]
        # draw_card enforces Steal -> Play -> Draw
        game["players"][current_player]["hasStolen"] = True
        
        # Add tribal council card
        tribal_card = {
            "type": "tribal_council_single",
            "category": "tribal_council",
            "name": "Tribal Council - Single Elimination",
            "description": "Tribal Council - Single Elimination",
            "elimination_type": "single"
        }
        
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, tribal_card)  # draw_card takes from the top (index 0)
        
        # Draw the card to trigger tribal council
        result = self.gs.draw_card(self.game_id, current_player)
        self.assertTrue(result.get("tribal_triggered", False), "Should trigger tribal council")
        
        updated_game = self.gs.games[self.game_id]
        self.assertIn("currentVote", updated_game, "currentVote should be created")
        vote_data = updated_game["currentVote"]
        
        # Verify all required fields are present based on _start_tribal_council method
        required_fields = [
            "type", "phase", "councilLeaderId", "votes", "immunityPlayed",
            "advantageCardsPlayed", "tieBreakNeeded", "tiedPlayers", "eliminated",
            "eliminationsNeeded", "voteResults",
        ]
        
        for field in required_fields:
            self.assertIn(field, vote_data, 
                         f"currentVote should have required field '{field}'")

    def test_phase_mapping_with_missing_current_vote(self):
        """Test phase mapping handles missing currentVote gracefully"""
        game = self.gs.games[self.game_id]
        game["phase"] = "tribal_council"
        # Intentionally do not set currentVote
        
        phase = self.rules_engine.get_current_turn_phase(game, self.player_ids[0])
        
        # Should default to a reasonable phase
        self.assertIn(phase, ["tribal_discussion", "waiting", "tribal_announcement"],
                     "Should handle missing currentVote gracefully")

    def test_card_timing_with_invalid_phases(self):
        """Test that cards properly reject invalid phases"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Set up an invalid/unexpected phase
        game["phase"] = "finished"
        
        control_vote_card = self.rules_engine.get_card_definition("control_the_vote")
        
        # Should not be playable in finished phase
        can_play, reason = self.rules_engine.is_card_playable(game, player_id, control_vote_card)
        self.assertFalse(can_play, "Cards should not be playable in finished phase")

if __name__ == '__main__':
    print("Running Critical Bug Fixes Test Suite...")
    unittest.main(verbosity=2)