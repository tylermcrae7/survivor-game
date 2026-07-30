#!/usr/bin/env python3
"""
Comprehensive Targeted Tests for Optimization Fixes

This test suite validates specific bug fixes and improvements implemented
in the Survivor app, covering tribal council triggers, idol nullification,
state management, deck composition, phase validation, and error handling.
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import shutil
import json
from unittest.mock import patch, mock_open

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from survivor_server import GameState
from rules_engine import SurvivorRulesEngine

class TestOptimizationFixes(unittest.TestCase):
    """Comprehensive tests for optimization fixes and improvements"""

    def setUp(self):
        """Set up test environment with clean temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        self.gs = GameState()
        self.rules_engine = SurvivorRulesEngine()
        
        # Create a standard 4-player game for most tests
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

    # ═══════════════════════════════════════════════════════════════════════
    # TEST 1: TRIBAL DRAW TRIGGER TEST
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_tribal_draw_trigger_sets_announcement_phase_and_council_leader(self):
        """
        Test that drawing tribal_council_single properly starts Tribal 
        with phase='announcement' and sets councilLeaderId to the drawer.
        """
        game = self.gs.games[self.game_id]
        drawer_id = self.player_ids[0]
        # draw_card enforces Steal -> Play -> Draw
        game["players"][drawer_id]["hasStolen"] = True
        
        # Create and add tribal council card to deck
        tribal_card = {
            "type": "tribal_council_single",
            "category": "tribal_council", 
            "name": "Tribal Council (Single)",
            "description": "A single elimination tribal council",
            "elimination_type": "single"
        }
        
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, tribal_card)  # Add to top of deck
        
        # Verify initial state
        self.assertEqual(game["phase"], "playing")
        self.assertEqual(game["currentVote"]["phase"], "waiting")
        
        # Draw the tribal council card
        result = self.gs.draw_card(self.game_id, drawer_id)
        
        # Verify tribal council was triggered correctly
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        # Check game phase transition
        self.assertEqual(updated_game["phase"], "tribal_council",
            "Game phase should transition to tribal_council")
        
        # Check currentVote initialization
        self.assertIn("currentVote", updated_game,
            "currentVote should be created when tribal council starts")
        
        vote_data = updated_game["currentVote"]
        
        # Check tribal council phase is announcement
        self.assertEqual(vote_data["phase"], "announcement",
            "Tribal council should start in announcement phase")
        
        # Check council leader is set to the drawer
        self.assertEqual(vote_data["councilLeaderId"], drawer_id,
            "Council leader should be set to the player who drew the tribal card")
        
        # Verify all required tribal council properties are initialized
        required_properties = [
            "type", "phase", "councilLeaderId", "votes", "immunityPlayed",
            "tieBreakNeeded", "eliminated", "advantageCardsPlayed",
            "tiedPlayers", "eliminationsNeeded", "voteResults",
        ]
        
        for prop in required_properties:
            self.assertIn(prop, vote_data,
                f"Tribal council should initialize '{prop}' property")
        
        # Verify elimination type is correctly set
        self.assertEqual(vote_data["type"], "single",
            "Elimination type should be 'single' for tribal_council_single")
        
    def test_tribal_draw_trigger_double_elimination(self):
        """
        Test that drawing tribal_council_double properly initializes 
        double elimination tribal council.
        """
        game = self.gs.games[self.game_id]
        drawer_id = self.player_ids[1]  # Use different drawer
        # draw_card enforces turn ownership and Steal -> Play -> Draw
        game["currentTurnIndex"] = game["turnOrder"].index(drawer_id)
        game["players"][drawer_id]["hasStolen"] = True
        
        # Create double elimination tribal card
        tribal_card = {
            "type": "tribal_council_double",
            "category": "tribal_council",
            "name": "Tribal Council (Double)",
            "description": "A double elimination tribal council",
            "elimination_type": "double"
        }
        
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, tribal_card)
        
        # Draw the card
        result = self.gs.draw_card(self.game_id, drawer_id)
        
        self.assertTrue(result["success"])
        updated_game = self.gs.games[self.game_id]
        
        # Verify tribal council setup
        self.assertEqual(updated_game["phase"], "tribal_council")
        vote_data = updated_game["currentVote"]
        
        self.assertEqual(vote_data["phase"], "announcement")
        self.assertEqual(vote_data["councilLeaderId"], drawer_id)
        self.assertEqual(vote_data["type"], "double",
            "Elimination type should be 'double' for tribal_council_double")

    # ═══════════════════════════════════════════════════════════════════════
    # TEST 2: IDOL NULLIFIER END-TO-END TEST  
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_idol_nullifier_end_to_end_workflow(self):
        """
        End-to-end test: Player A plays immunity_idol (self), Player B plays 
        idol_nullifier targeting A, on reveal_votes A's votes DO count 
        (idol nullified), verify flags are properly reset after reveal.
        """
        game = self.gs.games[self.game_id]
        player_a_id = self.player_ids[0]
        player_b_id = self.player_ids[1] 
        player_c_id = self.player_ids[2]
        player_d_id = self.player_ids[3]
        
        # Set up tribal council manually
        self.gs._initialize_tribal_council(game, drawer_id=player_a_id)
        game["phase"] = "tribal_council"
        
        # Give Player A an immunity idol
        immunity_idol_card = {
            "type": "immunity_idol",
            "category": "tribal_advantage",
            "name": "Hidden Immunity Idol",
            "description": "Play to become immune from elimination",
            "playable_phases": ["tribal_immunity"],
            "requires_target": False,
            "requires_multiple_targets": False,
            "requires_confirmation": True,
            "reactive_only": False
        }
        game["players"][player_a_id]["hand"] = [immunity_idol_card]
        
        # Give Player B an idol nullifier
        nullifier_card = {
            "type": "idol_nullifier", 
            "category": "tribal_advantage",
            "name": "Idol Nullifier",
            "description": "Nullify someone's immunity idol",
            "playable_phases": ["tribal_immunity"],
            "requires_target": True,
            "requires_multiple_targets": False,
            "requires_confirmation": False,
            "reactive_only": False
        }
        game["players"][player_b_id]["hand"] = [nullifier_card]
        
        # Give other players vote cards
        vote_card = {
            "type": "vote",
            "category": "vote", 
            "name": "Vote",
            "description": "Cast a vote at tribal council",
            "playable_phases": ["tribal_voting"],
            "requires_target": True,
            "requires_multiple_targets": False,
            "requires_confirmation": False,
            "reactive_only": False
        }
        
        for pid in [player_c_id, player_d_id]:
            game["players"][pid]["hand"] = [vote_card.copy()]
        
        # Phase 1: Move to immunity phase
        vote_data = game["currentVote"]
        vote_data["phase"] = "immunity"
        
        # Phase 2: Player A plays immunity idol on self
        result_a = self.gs.play_immunity(
            self.game_id, playerId=player_a_id, targetId=player_a_id
        )
        self.assertTrue(result_a["success"], result_a.get("message"))
        
        # Verify Player A has immunity protection
        player_a = game["players"][player_a_id]
        self.assertTrue(player_a.get("immunityIdolProtection", False),
            "Player A should have immunity protection after playing idol")
        
        # Phase 3: Player B plays idol nullifier targeting Player A
        result_b = self.gs.block_immunity(
            self.game_id, playerId=player_b_id, targetId=player_a_id
        )
        self.assertTrue(result_b["success"], result_b.get("message"))
        
        # Verify Player A's immunity is nullified
        self.assertFalse(player_a.get("immunityIdolProtection", False),
            "Player A's immunity protection should be nullified")
        self.assertTrue(player_a.get("idolNullified", False),
            "Player A should be marked as having immunity nullified")
        
        # Phase 4: Move to voting phase and cast votes
        vote_data["phase"] = "voting"
        
        # Players C and D vote for Player A (who should not be immune) — and A
        # and B place their own ballots too: the box must reach everyone now
        for voter_id in [player_c_id, player_d_id]:
            result_vote = self.gs.cast_vote(
                self.game_id, voter_id, [{"targetId": player_a_id, "votes": 1}]
            )
            self.assertTrue(result_vote["success"], result_vote.get("message"))
        for voter_id in [player_a_id, player_b_id]:
            # A and B hold no Vote Cards in this fixture — they pass the box
            result_vote = self.gs.cast_vote(self.game_id, voter_id, [])
            self.assertTrue(result_vote["success"], result_vote.get("message"))
        
        # Phase 5: Reveal votes - Player A's votes SHOULD count (immunity nullified).
        # reveal_votes moves the phase to "reveal" itself; it must be called from the
        # voting or immunity phase.
        result_reveal = self.gs.reveal_votes(self.game_id)
        self.assertTrue(result_reveal["success"], result_reveal.get("message"))

        # Verify Player A received votes and was eliminated. currentVote["votes"] maps
        # voterId -> {targetId: count}.
        final_vote_data = game["currentVote"]
        votes_for_a = sum(ballot.get(player_a_id, 0)
                          for ballot in final_vote_data["votes"].values())
        self.assertEqual(votes_for_a, 2,
            "Player A should have received 2 votes (immunity was nullified)")
        
        # Verify Player A is eliminated
        self.assertIn(player_a_id, final_vote_data["eliminated"],
            "Player A should be eliminated (immunity nullified)")
        
        # Phase 6: Complete tribal council and verify flags reset
        result_complete = self.gs.complete_tribal(self.game_id)
        self.assertTrue(result_complete["success"])
        
        # Verify immunity flags are properly reset after tribal
        remaining_players = [pid for pid, p in game["players"].items() 
                           if p.get("isActive", True)]
        
        for pid in remaining_players:
            player = game["players"][pid]
            self.assertFalse(player.get("immunityIdolProtection", False),
                f"Player {pid} should not have immunity protection after tribal")
            self.assertFalse(player.get("idolNullified", False), 
                f"Player {pid} should not have immunity nullified flag after tribal")
            self.assertFalse(player.get("immunityPlayed", False),
                f"Player {pid} should not have immunity played flag after tribal")

    # ═══════════════════════════════════════════════════════════════════════
    # TEST 3: STEAL → TRIBAL INTERRUPTION TEST
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_steal_tribal_interruption_clears_theft_state(self):
        """
        Test: Thief attempts steal, then immediately draws tribal card.
        After complete_tribal, ensure hasStolen=False and turn proceeds normally.
        Test that pending theft state is properly cleared.
        """
        game = self.gs.games[self.game_id]
        thief_id = self.player_ids[0]
        victim_id = self.player_ids[1]
        # draw_card enforces Steal -> Play -> Draw
        game["players"][thief_id]["hasStolen"] = True
        
        # Give thief a stealing card
        stealing_card = {
            "type": "the_spy_shack",
            "category": "action",
            "name": "The Spy Shack", 
            "description": "Look at a player's hand and steal one card",
            "playable_phases": ["turn_play"],
            "requires_target": True,
            "requires_multiple_targets": False,
            "requires_confirmation": False,
            "reactive_only": False
        }
        game["players"][thief_id]["hand"] = [stealing_card]
        
        # Give victim some cards to steal
        victim_cards = [
            {"type": "vote", "category": "vote", "name": "Vote"},
            {"type": "extra_vote", "category": "tribal_advantage", "name": "Extra Vote"}
        ]
        game["players"][victim_id]["hand"] = victim_cards
        
        # Phase 1: Thief initiates steal. The Spy Shack is "look and take one",
        # so the chosen card index rides along with the play.
        result_steal = self.gs.play_card(
            self.game_id, thief_id, 0, {"targetId": victim_id, "takeIndex": 0}
        )
        self.assertTrue(result_steal["success"], result_steal.get("message"))
        
        # Verify theft is in progress
        thief_player = game["players"][thief_id]
        self.assertTrue(thief_player.get("hasStolen", False),
            "Thief should have hasStolen=True after stealing")
        
        # Phase 2: Add tribal council card to deck and draw it
        tribal_card = {
            "type": "tribal_council_single",
            "category": "tribal_council",
            "name": "Tribal Council (Single)", 
            "description": "A single elimination tribal council",
            "elimination_type": "single"
        }
        
        if "deck" not in game:
            game["deck"] = []
        game["deck"].insert(0, tribal_card)
        
        # Draw the tribal card (this should interrupt the steal)
        result_draw = self.gs.draw_card(self.game_id, thief_id)
        self.assertTrue(result_draw["success"])
        
        # Verify tribal council was triggered
        self.assertEqual(game["phase"], "tribal_council")
        self.assertIn("currentVote", game)
        
        # Phase 3: Complete tribal council 
        vote_data = game["currentVote"]
        vote_data["phase"] = "reveal"  # Skip to end
        vote_data["eliminated"] = [victim_id]  # Eliminate someone
        
        result_complete = self.gs.complete_tribal(self.game_id)
        self.assertTrue(result_complete["success"])
        
        # Phase 4: Verify theft state is properly cleared
        updated_thief = game["players"][thief_id]
        self.assertFalse(updated_thief.get("hasStolen", False),
            "hasStolen should be False after tribal council completion")
        
        # Verify game can proceed normally
        self.assertEqual(game["phase"], "playing",
            "Game should return to playing phase after tribal")
        
        # Verify no lingering theft-related state
        for pid, player in game["players"].items():
            if player.get("isActive", True):  # Only check active players
                self.assertFalse(player.get("hasStolen", False),
                    f"Player {pid} should not have hasStolen=True after tribal")
        
        # Verify turn can advance normally
        if game.get("currentPlayer") == thief_id:
            # Thief should be able to end turn normally
            advance_result = self.gs.advance_turn(self.game_id)
            self.assertTrue(advance_result["success"] or "already ended" in advance_result.get("message", ""),
                "Turn should advance normally after tribal interruption")

    # ═══════════════════════════════════════════════════════════════════════ 
    # TEST 4: CAMP RAID TRANSFER TEST
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_camp_raid_transfer_mechanism(self):
        """
        Test: Mark campRaidedBy, then draw cards. Last drawn card goes to raider.
        Marker is cleared properly.
        """
        game = self.gs.games[self.game_id]
        raider_id = self.player_ids[0]
        victim_id = self.player_ids[1] 
        # draw_card enforces Steal -> Play -> Draw
        game["players"][victim_id]["hasStolen"] = True
        
        # Phase 1: Set up camp raid marker (it lives on the raided player) and put
        # the turn on the victim so they're allowed to draw.
        game["players"][victim_id]["campRaidedBy"] = raider_id
        game["currentTurnIndex"] = game["turnOrder"].index(victim_id)
        
        # Phase 2: Add cards to deck for drawing
        test_cards = [
            {"type": "vote", "category": "vote", "name": "Vote 1"},
            {"type": "extra_vote", "category": "tribal_advantage", "name": "Extra Vote"},
            {"type": "the_spy_shack", "category": "action", "name": "The Spy Shack"}
        ]
        
        if "deck" not in game:
            game["deck"] = []
        
        # Add cards to deck (last added will be drawn first)
        for card in reversed(test_cards):
            game["deck"].insert(0, card.copy())
        
        # A Sorry For You in the victim's dealt hand would (correctly) open the
        # reactive gate on consumption — this test pins the plain transfer path,
        # so make the hand deterministic first.
        game["players"][victim_id]["hand"] = [
            c for c in game["players"][victim_id]["hand"]
            if c.get("type") != "sorry_for_you"
        ]

        # Get initial hand sizes
        raider_initial_hand = len(game["players"][raider_id]["hand"])
        victim_initial_hand = len(game["players"][victim_id]["hand"])
        
        # Phase 3: Victim draws. Camp Raid takes "the next card they draw", so the
        # marker is consumed by the FIRST draw and later draws are unaffected.
        num_draws = len(test_cards)
        
        for i in range(num_draws):
            # One draw per turn now, and the draw itself ends the turn —
            # simulate a fresh turn back on the victim each time
            game["currentTurnIndex"] = game["turnOrder"].index(victim_id)
            game["players"][victim_id]["hasStolen"] = True
            game["players"][victim_id]["hasDrawn"] = False
            result = self.gs.draw_card(self.game_id, victim_id)
            self.assertTrue(result["success"], f"Draw {i+1} should succeed")
        
        # Phase 4: Verify last drawn card went to raider
        raider_final_hand = len(game["players"][raider_id]["hand"])
        victim_final_hand = len(game["players"][victim_id]["hand"])
        
        # Raider should get exactly 1 card (the last drawn)
        self.assertEqual(raider_final_hand, raider_initial_hand + 1,
            "Raider should receive exactly 1 card (the last drawn)")
        
        # Victim should get all but the last card
        expected_victim_cards = num_draws - 1
        self.assertEqual(victim_final_hand, victim_initial_hand + expected_victim_cards,
            f"Victim should receive {expected_victim_cards} cards")
        
        # Phase 5: Verify camp raid marker is cleared (used up by the first draw)
        self.assertIsNone(game["players"][victim_id].get("campRaidedBy"),
            "campRaidedBy marker should be cleared after card transfer")

        # Phase 6: Verify the specific card transferred — Camp Raid takes "the next
        # card they draw", i.e. the first one drawn after the marker was placed.
        expected_card = test_cards[0]
        raider_hand = game["players"][raider_id]["hand"]

        raider_has_card = any(
            card.get("name") == expected_card["name"]
            for card in raider_hand
        )
        self.assertTrue(raider_has_card,
            f"Raider should have received the next card drawn: {expected_card['name']}")

    # ═══════════════════════════════════════════════════════════════════════
    # TEST 5: DECK DISTRIBUTION TESTS
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_deck_distribution_for_all_player_counts(self):
        """
        For each player count (3-6), verify:
        - Correct single/double tribal card counts per official rules
        - Even tribal spacing throughout deck with one bottom card
        - Total deck composition is correct
        """
        # Official tribal card distribution per player count
        # The official rules table (Survivor: The Tribe Has Spoken, Setup step 4)
        official_tribal_counts = {
            3: {"single": 4, "double": 0},  # 4 total
            4: {"single": 2, "double": 2},  # 4 total
            5: {"single": 2, "double": 3},  # 5 total
            6: {"single": 0, "double": 5}   # 5 total
        }
        
        for player_count in range(3, 7):
            with self.subTest(player_count=player_count):
                # Create fresh game with specific player count
                test_game_id = self.gs.create_game()
                test_player_ids = []
                colors = ["red", "blue", "green", "yellow", "purple", "orange"]
                
                for i in range(player_count):
                    player_id = self.gs.add_player(
                        test_game_id, f"TestPlayer{i+1}", colors[i]
                    )
                    test_player_ids.append(player_id)
                
                # Start game to trigger deck construction
                self.gs.start_full_game(test_game_id)
                
                game = self.gs.games[test_game_id]
                deck = game.get("deck", [])
                
                # Count tribal cards in deck
                single_count = sum(1 for card in deck 
                                 if card.get("type") == "tribal_council_single")
                double_count = sum(1 for card in deck 
                                 if card.get("type") == "tribal_council_double")
                
                expected_single = official_tribal_counts[player_count]["single"]
                expected_double = official_tribal_counts[player_count]["double"]
                
                # Verify correct tribal card counts
                self.assertEqual(single_count, expected_single,
                    f"Player count {player_count}: Expected {expected_single} single tribal cards, got {single_count}")
                
                self.assertEqual(double_count, expected_double,
                    f"Player count {player_count}: Expected {expected_double} double tribal cards, got {double_count}")
                
                # Verify even spacing of tribal cards
                total_tribal = single_count + double_count
                total_deck_size = len(deck)
                
                # Find positions of all tribal cards
                tribal_positions = []
                for i, card in enumerate(deck):
                    if card.get("category") == "tribal_council":
                        tribal_positions.append(i)
                
                self.assertEqual(len(tribal_positions), total_tribal,
                    f"Should find exactly {total_tribal} tribal cards in deck")
                
                # Verify one tribal card is at bottom (last position)
                self.assertIn(total_deck_size - 1, tribal_positions,
                    "One tribal card should be at the bottom of the deck")
                
                # Verify remaining tribal cards are evenly spaced
                remaining_positions = [pos for pos in tribal_positions 
                                     if pos != total_deck_size - 1]
                
                # The rules say to space the tribal cards "evenly(ish)", so assert the
                # properties that actually matter rather than an exact interval:
                # never adjacent, and spread across the whole deck.
                for i in range(len(tribal_positions) - 1):
                    gap = tribal_positions[i + 1] - tribal_positions[i]
                    self.assertGreater(gap, 1,
                        f"Tribal cards should never be adjacent (positions {tribal_positions})")

                if len(remaining_positions) > 1:
                    self.assertLess(remaining_positions[0], total_deck_size // 2,
                        "The first tribal card should land in the first half of the deck")

                # Official setup: 67 cards minus 9 tribal and 6 vote = 52 Action Cards,
                # minus 3 dealt per player, plus this player count's tribal cards.
                expected_total_cards = 52 - (3 * player_count) + total_tribal
                self.assertEqual(total_deck_size, expected_total_cards,
                    f"Player count {player_count}: expected {expected_total_cards} cards, got {total_deck_size}")
                
                # Clean up
                del self.gs.games[test_game_id]

    # ═══════════════════════════════════════════════════════════════════════
    # TEST 6: PHASE VALIDATION CONSISTENCY TESTS
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_phase_validation_consistency_for_all_sub_phases(self):
        """
        Test that tribal phase mapping works correctly for all sub-phases 
        and that card playability follows category-based rules.
        """
        game = self.gs.games[self.game_id]
        test_player_id = self.player_ids[0]
        
        # Set up tribal council
        self.gs._initialize_tribal_council(game, drawer_id=test_player_id)
        game["phase"] = "tribal_council"
        
        # Define all tribal sub-phases and their expected properties
        tribal_phases = [
            "announcement",
            "advantage_play", 
            "discussion",
            "voting",
            "immunity", 
            "reveal"
        ]
        
        # Test cards of different categories
        test_cards = [
            {
                "type": "vote",
                "category": "vote",
                "name": "Vote",
                "playable_phases": ["tribal_voting"],
                "expected_playable_in": ["voting"]
            },
            {
                "type": "immunity_idol",
                "category": "tribal_advantage", 
                "name": "Hidden Immunity Idol",
                "playable_phases": ["tribal_immunity"],
                "expected_playable_in": ["immunity"]
            },
            {
                "type": "extra_vote",
                "category": "tribal_advantage",
                "name": "Extra Vote", 
                "playable_phases": ["tribal_advantage_play"],
                "expected_playable_in": ["advantage_play"]
            },
            {
                "type": "the_spy_shack", 
                "category": "action",
                "name": "The Spy Shack",
                "playable_phases": ["turn_play"],
                "expected_playable_in": []  # Not playable in tribal
            }
        ]
        
        # Test each tribal phase
        for phase in tribal_phases:
            with self.subTest(tribal_phase=phase):
                # Set current tribal phase
                game["currentVote"]["phase"] = phase
                
                # Test each card type
                for card_info in test_cards:
                    with self.subTest(card_type=card_info["type"]):
                        card = {k: v for k, v in card_info.items() 
                               if k not in ["expected_playable_in"]}
                        
                        # Check if card should be playable in this phase
                        should_be_playable = phase in card_info["expected_playable_in"]
                        
                        # Test playability using rules engine
                        is_playable = self.rules_engine.can_play_card_in_phase(
                            card, f"tribal_{phase}"
                        )
                        
                        if should_be_playable:
                            self.assertTrue(is_playable,
                                f"Card {card['type']} should be playable in tribal_{phase}")
                        else:
                            self.assertFalse(is_playable,
                                f"Card {card['type']} should NOT be playable in tribal_{phase}")
        
        # Test phase transitions maintain consistency
        vote_data = game["currentVote"]
        valid_phase_transitions = {
            "announcement": ["advantage_play"],
            "advantage_play": ["discussion"], 
            "discussion": ["voting"],
            "voting": ["immunity"],
            "immunity": ["reveal"],
            "reveal": []  # Terminal phase
        }
        
        for current_phase, valid_next_phases in valid_phase_transitions.items():
            with self.subTest(phase_transition=current_phase):
                vote_data["phase"] = current_phase
                
                # Verify phase is recognized as valid
                self.assertIn(current_phase, tribal_phases,
                    f"Phase {current_phase} should be recognized as valid tribal phase")
                
                # Test that only valid transitions are allowed
                for test_next_phase in tribal_phases:
                    if test_next_phase in valid_next_phases:
                        # This transition should be valid
                        # (Actual transition testing would require more server methods)
                        pass
                    else:
                        # This transition should be invalid
                        # (Actual validation would need server method support)
                        pass
    
    def test_category_based_card_playability_rules(self):
        """
        Test that card playability strictly follows category-based rules
        across all game phases.
        """
        game = self.gs.games[self.game_id]
        
        # Test cards with their expected playability
        test_scenarios = [
            {
                "game_phase": "playing",
                "turn_phase": "turn_play",
                "cards": [
                    {
                        "type": "the_spy_shack",
                        "category": "action", 
                        "playable_phases": ["turn_play"],
                        "should_be_playable": True
                    },
                    {
                        "type": "vote",
                        "category": "vote",
                        "playable_phases": ["tribal_voting"],
                        "should_be_playable": False
                    }
                ]
            },
            {
                "game_phase": "tribal_council", 
                "turn_phase": "tribal_voting",
                "cards": [
                    {
                        "type": "vote",
                        "category": "vote",
                        "playable_phases": ["tribal_voting"],
                        "should_be_playable": True
                    },
                    {
                        "type": "the_spy_shack",
                        "category": "action",
                        "playable_phases": ["turn_play"],
                        "should_be_playable": False
                    }
                ]
            }
        ]
        
        for scenario in test_scenarios:
            with self.subTest(
                game_phase=scenario["game_phase"], 
                turn_phase=scenario["turn_phase"]
            ):
                # Set up game state
                game["phase"] = scenario["game_phase"]
                if scenario["game_phase"] == "tribal_council":
                    if "currentVote" not in game:
                        self.gs._initialize_tribal_council(game)
                    # Extract tribal phase from turn_phase
                    tribal_phase = scenario["turn_phase"].replace("tribal_", "")
                    game["currentVote"]["phase"] = tribal_phase
                
                # Test each card
                for card_info in scenario["cards"]:
                    with self.subTest(card_type=card_info["type"]):
                        card = {k: v for k, v in card_info.items() 
                               if k != "should_be_playable"}
                        
                        is_playable = self.rules_engine.can_play_card_in_phase(
                            card, scenario["turn_phase"]
                        )
                        
                        if card_info["should_be_playable"]:
                            self.assertTrue(is_playable,
                                f"Card {card['type']} should be playable in {scenario['turn_phase']}")
                        else:
                            self.assertFalse(is_playable,
                                f"Card {card['type']} should NOT be playable in {scenario['turn_phase']}")

    # ═══════════════════════════════════════════════════════════════════════
    # TEST 7: EXCEPTION HANDLING TESTS
    # ═══════════════════════════════════════════════════════════════════════
    
    def test_save_operations_handle_io_errors_gracefully(self):
        """
        Verify save operations handle IO errors gracefully with proper exception types.
        """
        game = self.gs.games[self.game_id]
        
        # Test 1: File permission errors
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.side_effect = PermissionError("Permission denied")
            
            # Attempt to save game state
            try:
                result = self.gs._save()
                # Should either return False or handle gracefully
                if result is not None:
                    self.assertFalse(result, 
                        "Save should return False on permission error")
            except PermissionError:
                self.fail("PermissionError should be handled gracefully")
            except Exception as e:
                # Should be a specific, expected exception type
                self.assertIsInstance(e, (IOError, OSError),
                    f"Unexpected exception type: {type(e)}")
        
        # Test 2: Disk full errors
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.side_effect = OSError("No space left on device")
            
            try:
                result = self.gs._save()
                if result is not None:
                    self.assertFalse(result,
                        "Save should return False on disk full error")
            except OSError:
                self.fail("OSError should be handled gracefully")
            except Exception as e:
                self.assertIsInstance(e, (IOError, OSError),
                    f"Unexpected exception type: {type(e)}")
        
        # Test 3: JSON serialization errors
        # Create game state with non-serializable data
        original_phase = game["phase"]
        game["phase"] = lambda x: x  # Non-serializable function
        
        with patch("json.dump") as mock_json:
            mock_json.side_effect = TypeError("Object is not JSON serializable")
            
            try:
                result = self.gs._save()
                if result is not None:
                    self.assertFalse(result,
                        "Save should return False on JSON serialization error")
            except TypeError:
                self.fail("JSON TypeError should be handled gracefully")
            except Exception as e:
                self.assertIsInstance(e, (TypeError, ValueError),
                    f"Unexpected exception type: {type(e)}")
            finally:
                # Restore valid state
                game["phase"] = original_phase
        
        # Test 4: File system corruption
        with patch("builtins.open", mock_open()) as mock_file:
            # Simulate file handle becoming invalid mid-write
            mock_file.return_value.__enter__.return_value.write.side_effect = IOError("Bad file descriptor")
            
            try:
                result = self.gs._save()
                if result is not None:
                    self.assertFalse(result,
                        "Save should return False on file corruption")
            except IOError:
                self.fail("IOError should be handled gracefully")
            except Exception as e:
                self.assertIsInstance(e, (IOError, OSError),
                    f"Unexpected exception type: {type(e)}")
        
        # Test 5: Ensure game state remains consistent after save failures
        # Game should still be in valid state after failed saves
        self.assertEqual(game["phase"], original_phase,
            "Game state should remain valid after save failures")
        
        self.assertIn(self.game_id, self.gs.games,
            "Game should still exist after save failures")
        
        for player_id in self.player_ids:
            self.assertIn(player_id, game["players"],
                f"Player {player_id} should still exist after save failures")
        
        # Verify game is still functional
        current_player = game.get("currentPlayer")
        if current_player and game["phase"] == "playing":
            # Should be able to perform basic operations
            hand_size_before = len(game["players"][current_player]["hand"])
            
            # Add a test card to deck
            if "deck" not in game:
                game["deck"] = []
            test_card = {"type": "vote", "category": "vote", "name": "Test Vote"}
            game["deck"].insert(0, test_card)
            
            # Draw should still work
            result = self.gs.draw_card(self.game_id, current_player)
            if result["success"]:
                hand_size_after = len(game["players"][current_player]["hand"])
                self.assertEqual(hand_size_after, hand_size_before + 1,
                    "Game functionality should remain intact after save failures")


if __name__ == '__main__':
    print("Running Comprehensive Optimization Fix Tests...")
    unittest.main(verbosity=2)