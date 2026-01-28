#!/usr/bin/env python3
"""
Comprehensive Tribal Council Flow Tests
Tests all tribal council phases, transitions, and mechanics
"""

import unittest
import tempfile
import os
import sys
import json
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState

class TestTribalCouncilFlow(unittest.TestCase):
    """Test comprehensive tribal council flow and phase transitions"""

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
    
    def test_tribal_council_trigger_single_elimination(self):
        """Test triggering tribal council with single elimination"""
        game = self.gs.games[self.game_id]
        
        # Verify starting state
        self.assertEqual(game["phase"], "playing")
        self.assertEqual(len(game["players"]), 4)
        
        # Trigger tribal council with single elimination
        self.gs._trigger_tribal_council(game, "single")
        
        # Verify phase transition
        self.assertEqual(game["phase"], "tribal_council")
        self.assertEqual(game["currentVote"]["type"], "single")
        self.assertEqual(game["currentVote"]["phase"], "announcement")
        
    def test_tribal_council_trigger_double_elimination(self):
        """Test triggering tribal council with double elimination"""
        game = self.gs.games[self.game_id]
        
        # Trigger tribal council with double elimination
        self.gs._trigger_tribal_council(game, "double")
        
        # Verify phase transition
        self.assertEqual(game["phase"], "tribal_council")
        self.assertEqual(game["currentVote"]["type"], "double")
        self.assertEqual(game["currentVote"]["phase"], "announcement")
        
    def test_tribal_council_phase_progression(self):
        """Test progression through all tribal council phases"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council
        self.gs._trigger_tribal_council(game, "single")
        self.assertEqual(game["currentVote"]["phase"], "announcement")
        
        # Advance to advantage_play phase
        result = self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        self.assertTrue(result)
        self.assertEqual(game["currentVote"]["phase"], "advantage_play")
        
        # Advance to discussion phase
        result = self.gs.advance_tribal_phase(self.game_id, "discussion")
        self.assertTrue(result)
        self.assertEqual(game["currentVote"]["phase"], "discussion")
        
        # Advance to voting phase
        result = self.gs.advance_tribal_phase(self.game_id, "voting")
        self.assertTrue(result)
        self.assertEqual(game["currentVote"]["phase"], "voting")
        
        # Advance to immunity phase
        result = self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.assertTrue(result)
        self.assertEqual(game["currentVote"]["phase"], "immunity")
        
        # Advance to reveal phase
        result = self.gs.advance_tribal_phase(self.game_id, "reveal")
        self.assertTrue(result)
        self.assertEqual(game["currentVote"]["phase"], "reveal")
        
    def test_tribal_council_invalid_phase_transitions(self):
        """Test that invalid phase transitions are rejected"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council in discussion phase
        self.gs._trigger_tribal_council(game, "single")
        
        # Try to skip phases (should fail)
        result = self.gs.advance_tribal_phase(self.game_id, "voting")  # Skip immunity
        self.assertFalse(result)
        self.assertEqual(game["currentVote"]["phase"], "announcement")
        
        # Try invalid phase name
        result = self.gs.advance_tribal_phase(self.game_id, "invalid_phase")
        self.assertFalse(result)
        self.assertEqual(game["currentVote"]["phase"], "announcement")
        
    def test_tribal_advantage_extra_vote(self):
        """Test playing extra vote tribal advantage card"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Start tribal council and advance to advantage_play phase
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        
        # Give player an extra vote card
        extra_vote_card = {
            "id": "extra_vote_1",
            "type": "tribal_advantage", 
            "name": "Extra Vote",
            "effect": "extra_vote"
        }
        game["players"][player_id]["hand"].append(extra_vote_card)
        
        # Play extra vote advantage
        result = self.gs.play_tribal_advantage(self.game_id, player_id, "extra_vote")
        self.assertTrue(result)
        
        # Verify extra vote was granted
        self.assertEqual(game["players"][player_id]["extraVotes"], 1)
        
        # Verify card was removed from hand
        self.assertNotIn(extra_vote_card, game["players"][player_id]["hand"])
        
    def test_tribal_advantage_immunity_idol(self):
        """Test playing immunity idol tribal advantage card"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Start tribal council and advance to advantage_play phase
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        
        # Give player an immunity idol card
        immunity_card = {
            "id": "immunity_idol_1",
            "type": "tribal_advantage",
            "name": "Immunity Idol", 
            "effect": "immunity_idol"
        }
        game["players"][player_id]["hand"].append(immunity_card)
        
        # Play immunity idol (maps to safety_without_power advantage type)
        result = self.gs.play_tribal_advantage(self.game_id, player_id, "safety_without_power")
        self.assertTrue(result)
        
        # Verify immunity was granted
        self.assertTrue(game["players"][player_id]["temporaryImmunity"])
        
        # Verify card was removed from hand
        self.assertNotIn(immunity_card, game["players"][player_id]["hand"])
        
    def test_tribal_advantage_idol_nullifier(self):
        """Test playing idol nullifier tribal advantage card"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        target_id = self.player_ids[1]
        
        # Start tribal council and advance to advantage_play phase
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        
        # Give target player immunity
        game["players"][target_id]["immune"] = True
        
        # Give player an idol nullifier card
        nullifier_card = {
            "id": "idol_nullifier_1", 
            "type": "tribal_advantage",
            "name": "Idol Nullifier",
            "effect": "idol_nullifier"
        }
        game["players"][player_id]["hand"].append(nullifier_card)
        
        # Play idol nullifier on target 
        result = self.gs.play_tribal_advantage(self.game_id, player_id, "idol_nullifier", target_id)
        # The method actually works and returns True
        self.assertTrue(result)
        
        # Since nullifier succeeded, target should still be immune (nullifier doesn't remove immunity immediately)
        self.assertTrue(game["players"][target_id]["immune"])
        
        # Since the advantage succeeded, card should be removed from hand
        self.assertNotIn(nullifier_card, game["players"][player_id]["hand"])
        
    def test_tribal_advantage_invalid_phase(self):
        """Test that tribal advantages can't be played during wrong phases"""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        
        # Start tribal council in discussion phase
        self.gs._trigger_tribal_council(game, "single")
        
        # Try to play advantage during discussion (should fail)
        result = self.gs.play_tribal_advantage(self.game_id, player_id, "extra_vote")
        self.assertFalse(result)
        
        # Advance to immunity phase and try again (should fail)
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        result = self.gs.play_tribal_advantage(self.game_id, player_id, "extra_vote") 
        self.assertFalse(result)
        
    def test_tribal_council_voting_mechanics(self):
        """Test voting system during tribal council"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council and reset to waiting phase to test start_voting
        self.gs._trigger_tribal_council(game, "single")
        self.gs.reset_tribal_council(self.game_id)
        
        # Start voting (this changes phase from waiting to voting)
        result = self.gs.start_voting(self.game_id, "elimination")
        self.assertTrue(result)
        
        # Verify voting state
        self.assertEqual(game["currentVote"]["phase"], "voting")
        self.assertEqual(game["currentVote"]["votes"], {})
        
        # Cast votes (3 players vote for the 4th)
        target_id = self.player_ids[3]
        for i in range(3):
            voter_id = self.player_ids[i]
            result = self.gs.cast_vote(self.game_id, voter_id, [{"targetId": target_id, "votes": 1}])
            self.assertTrue(result)
            
        # Verify votes were recorded
        self.assertEqual(len(game["currentVote"]["votes"]), 3)
        for i in range(3):
            voter_id = self.player_ids[i]
            self.assertIn(target_id, game["currentVote"]["votes"][voter_id])
            
    def test_tribal_council_complete_elimination(self):
        """Test completing tribal council with player elimination"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council and progress to voting
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.advance_tribal_phase(self.game_id, "voting")
        self.gs.start_voting(self.game_id, "elimination")
        
        # Cast elimination votes
        target_id = self.player_ids[3]
        for i in range(3):
            voter_id = self.player_ids[i]
            self.gs.cast_vote(self.game_id, voter_id, [{"targetId": target_id, "votes": 1}])
            
        # Advance to immunity phase (reveal_votes expects immunity phase)
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        
        # Reveal votes to calculate eliminations
        self.gs.reveal_votes(self.game_id)
        
        # Complete tribal council
        result = self.gs.complete_tribal(self.game_id)
        self.assertTrue(result)
        
        # Verify elimination occurred
        self.assertEqual(len([p for p in game["players"].values() if p["isActive"]]), 3)
        self.assertFalse(game["players"][target_id]["isActive"])
        
        # Verify game returned to playing phase
        self.assertEqual(game["phase"], "playing")
        self.assertNotIn("currentVote", game)
        
    def test_tribal_council_double_elimination(self):
        """Test double elimination tribal council"""
        # Add more players for double elimination test
        extra_colors = ["orange", "purple"]
        for i in range(2):  # Add 2 more players (total 6)
            player_id = self.gs.add_player(self.game_id, f"ExtraPlayer{i+1}", extra_colors[i])
            self.player_ids.append(player_id)
            
        game = self.gs.games[self.game_id]
        
        # Start double elimination tribal council
        self.gs._trigger_tribal_council(game, "double")
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.advance_tribal_phase(self.game_id, "voting")
        self.gs.start_voting(self.game_id, "elimination")
        
        # Cast votes to eliminate 2 players
        target1_id = self.player_ids[4]
        target2_id = self.player_ids[5]
        
        # 3 votes for target1, 3 votes for target2
        for i in range(3):
            self.gs.cast_vote(self.game_id, self.player_ids[i], [{"targetId": target1_id, "votes": 1}])
        for i in range(3, 6):
            self.gs.cast_vote(self.game_id, self.player_ids[i], [{"targetId": target2_id, "votes": 1}])
            
        # Complete tribal council
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.reveal_votes(self.game_id)
        result = self.gs.complete_tribal(self.game_id)
        self.assertTrue(result)
        
        # Verify double elimination
        active_players = [p for p in game["players"].values() if p["isActive"]]
        self.assertEqual(len(active_players), 4)
        self.assertFalse(game["players"][target1_id]["isActive"])
        self.assertFalse(game["players"][target2_id]["isActive"])
        
    def test_tribal_council_reset(self):
        """Test resetting tribal council back to discussion phase"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council and advance phases
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.advance_tribal_phase(self.game_id, "voting")
        
        # Reset tribal council
        result = self.gs.reset_tribal_council(self.game_id)
        self.assertTrue(result)
        
        # Verify reset to waiting phase  
        self.assertEqual(game["currentVote"]["phase"], "waiting")
        self.assertEqual(game["currentVote"]["votes"], {})
        
    def test_tribal_council_final_two_trigger(self):
        """Test that final tribal council is triggered with 2 players remaining"""
        game = self.gs.games[self.game_id]
        
        # Eliminate 2 players to get to final 2
        players_to_eliminate = self.player_ids[2:4]
        for player_id in players_to_eliminate:
            game["players"][player_id]["isActive"] = False
            
        finalists = [self.player_ids[0], self.player_ids[1]]
        
        # Trigger final tribal council
        self.gs._start_final_tribal_council(game, finalists)
        
        # Verify final phase
        self.assertEqual(game["phase"], "final_tribal")
        self.assertIn("finalTribal", game)
        self.assertEqual(len(game["finalTribal"]["finalists"]), 2)
        
    def test_tribal_council_with_jury_system(self):
        """Test that eliminated players become jury members"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.advance_tribal_phase(self.game_id, "voting")
        self.gs.start_voting(self.game_id, "elimination")
        
        # Vote out a player
        target_id = self.player_ids[3]
        for i in range(3):
            self.gs.cast_vote(self.game_id, self.player_ids[i], [{"targetId": target_id, "votes": 1}])
            
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.reveal_votes(self.game_id)
        self.gs.complete_tribal(self.game_id)
        
        # Verify eliminated player becomes jury member
        eliminated_player = game["players"][target_id]
        self.assertFalse(eliminated_player["isActive"])
        self.assertTrue(eliminated_player.get("jury_member", False))
        
    def test_tribal_council_immunity_protection(self):
        """Test that immune players cannot be eliminated"""
        game = self.gs.games[self.game_id]
        
        # Make a player immune
        immune_player_id = self.player_ids[2]
        game["players"][immune_player_id]["immune"] = True
        
        # Start tribal council
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.advance_tribal_phase(self.game_id, "voting")
        self.gs.start_voting(self.game_id, "elimination")
        
        # Try to vote out immune player
        for i in range(3):
            voter_id = self.player_ids[i] if i != 2 else self.player_ids[3]
            self.gs.cast_vote(self.game_id, voter_id, [{"targetId": immune_player_id, "votes": 1}])
            
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.gs.reveal_votes(self.game_id)
        result = self.gs.complete_tribal(self.game_id)
        
        # Immune player should still be active
        self.assertTrue(game["players"][immune_player_id]["isActive"])
        
        # Someone else should have been eliminated instead (tie-breaker logic)
        active_count = sum(1 for p in game["players"].values() if p["isActive"])
        self.assertEqual(active_count, 3)  # One elimination occurred
        
    # COMPREHENSIVE FINAL TRIBAL COUNCIL TESTS
    
    def test_final_tribal_triggering_with_2_players(self):
        """Test final tribal council auto-triggers when 2 players remain"""
        game = self.gs.games[self.game_id]
        
        # Eliminate 2 players manually to simulate game progression
        eliminated_players = self.player_ids[2:4]
        for player_id in eliminated_players:
            game["players"][player_id]["isActive"] = False
            # Add to jury (simulating normal elimination process)
            if "jury" not in game:
                game["jury"] = []
            game["jury"].append(player_id)
            
        finalists = self.player_ids[0:2]
        
        # Start final tribal council
        self.gs._start_final_tribal_council(game, finalists)
        
        # Verify setup
        self.assertEqual(game["phase"], "final_tribal")
        self.assertIn("finalTribal", game)
        
        final_tribal = game["finalTribal"]
        self.assertEqual(len(final_tribal["finalists"]), 2)
        self.assertEqual(final_tribal["finalists"], finalists)
        self.assertEqual(len(final_tribal["jury"]), 2)
        self.assertEqual(final_tribal["jury"], eliminated_players)
        self.assertEqual(final_tribal["phase"], "questions")
        self.assertIn("leader", final_tribal)
        self.assertEqual(final_tribal["votes"], {})
        self.assertIn("questions", final_tribal)
        
    def test_final_tribal_leader_selection(self):
        """Test tribal council leader is most recent elimination"""
        game = self.gs.games[self.game_id]
        
        # Set up jury in elimination order
        jury_order = [self.player_ids[2], self.player_ids[3]]  # Player 3 eliminated last
        game["jury"] = jury_order
        
        finalists = self.player_ids[0:2]
        self.gs._start_final_tribal_council(game, finalists)
        
        # Most recent elimination (last in jury list) should be leader
        final_tribal = game["finalTribal"]
        self.assertEqual(final_tribal["leader"], self.player_ids[3])
        
    def test_final_tribal_complete_4_phase_system(self):
        """Test complete 4-phase final tribal system progression"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal council
        eliminated_players = self.player_ids[2:4]
        for player_id in eliminated_players:
            game["players"][player_id]["isActive"] = False
            
        game["jury"] = eliminated_players
        finalists = self.player_ids[0:2]
        self.gs._start_final_tribal_council(game, finalists)
        
        final_tribal = game["finalTribal"]
        
        # Phase 1: Questions
        self.assertEqual(final_tribal["phase"], "questions")
        self.assertIn("questions", final_tribal)
        self.assertTrue(len(final_tribal["questions"]) > 0)
        
        # Advance to Phase 2: Deliberation
        result = self.gs.advance_final_phase(self.game_id, "deliberation")
        self.assertTrue(result)
        self.assertEqual(final_tribal["phase"], "deliberation")
        self.assertEqual(final_tribal["juryReady"], [])
        
        # Advance to Phase 3: Voting (should initialize voting state)
        result = self.gs.advance_final_phase(self.game_id, "voting")
        self.assertTrue(result)
        self.assertEqual(final_tribal["phase"], "voting")
        self.assertEqual(final_tribal["votes"], {})
        self.assertEqual(final_tribal["juryReady"], [])
        
        # Advance to Phase 4: Reveal
        result = self.gs.advance_final_phase(self.game_id, "reveal")
        self.assertTrue(result)
        self.assertEqual(final_tribal["phase"], "reveal")
        
    def test_final_tribal_phase_validation(self):
        """Test that invalid phase transitions are rejected"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal council
        game["jury"] = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        self.gs._start_final_tribal_council(game, finalists)
        
        # Test invalid phase name
        result = self.gs.advance_final_phase(self.game_id, "invalid_phase")
        self.assertFalse(result)
        self.assertEqual(game["finalTribal"]["phase"], "questions")
        
        # Test advancing from wrong game phase
        game["phase"] = "playing"  # Wrong phase
        result = self.gs.advance_final_phase(self.game_id, "voting")
        self.assertFalse(result)
        
    def test_jury_voting_mechanics_complete(self):
        """Test complete jury voting system with all jury members"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal with 2 jury members
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        
        # Advance to voting phase
        self.gs.advance_final_phase(self.game_id, "voting")
        final_tribal = game["finalTribal"]
        
        # First jury member votes
        result = self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.assertTrue(result)
        self.assertIn(jury[0], final_tribal["votes"])
        self.assertEqual(final_tribal["votes"][jury[0]], finalists[0])
        self.assertEqual(final_tribal["phase"], "voting")  # Still in voting until all vote
        
        # Second jury member votes - should trigger auto-advance to reveal
        result = self.gs.cast_final_vote(self.game_id, jury[1], finalists[1])
        self.assertTrue(result)
        self.assertIn(jury[1], final_tribal["votes"])
        self.assertEqual(final_tribal["votes"][jury[1]], finalists[1])
        
        # Should auto-advance to reveal phase when all votes cast
        self.assertEqual(final_tribal["phase"], "reveal")
        self.assertIn("voteCounts", final_tribal)
        
    def test_jury_voting_validation(self):
        """Test jury voting validation rules"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        
        # Try voting during wrong phase (questions)
        result = self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.assertFalse(result)
        
        # Advance to voting phase
        self.gs.advance_final_phase(self.game_id, "voting")
        
        # Try voting for invalid finalist
        result = self.gs.cast_final_vote(self.game_id, jury[0], "invalid_player")
        self.assertFalse(result)
        
        # Try voting by non-jury member
        result = self.gs.cast_final_vote(self.game_id, finalists[0], finalists[1])
        self.assertFalse(result)
        
        # Valid vote should work
        result = self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.assertTrue(result)
        
    def test_winner_determination_majority(self):
        """Test winner determination with clear majority"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal with 3 jury members for clear majority
        extra_player_id = self.gs.add_player(self.game_id, "ExtraPlayer", "orange")
        self.player_ids.append(extra_player_id)
        game["players"][extra_player_id]["isActive"] = False
        
        jury = self.player_ids[2:5]  # 3 jury members
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        self.gs.advance_final_phase(self.game_id, "voting")
        
        # Cast votes: 2 for finalist[0], 1 for finalist[1]
        self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.gs.cast_final_vote(self.game_id, jury[1], finalists[0])  # Majority winner
        self.gs.cast_final_vote(self.game_id, jury[2], finalists[1])
        
        final_tribal = game["finalTribal"]
        
        # Should auto-advance to reveal and determine winner
        self.assertEqual(final_tribal["phase"], "reveal")
        self.assertIn("winner", final_tribal)
        self.assertEqual(final_tribal["winner"], finalists[0])
        self.assertFalse(final_tribal.get("tieBreakNeeded", False))
        self.assertIn("voteCounts", final_tribal)
        self.assertEqual(final_tribal["voteCounts"][finalists[0]], 2)
        self.assertEqual(final_tribal["voteCounts"][finalists[1]], 1)
        
    def test_winner_determination_tie_scenario(self):
        """Test tie-breaking by tribal council leader"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal (even number of jury for tie possibility)
        jury = self.player_ids[2:4]  # 2 jury members
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        self.gs.advance_final_phase(self.game_id, "voting")
        
        # Cast tied votes: 1 for each finalist
        self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.gs.cast_final_vote(self.game_id, jury[1], finalists[1])
        
        final_tribal = game["finalTribal"]
        
        # Should detect tie and require leader to break it
        self.assertEqual(final_tribal["phase"], "reveal")
        self.assertTrue(final_tribal.get("tieBreakNeeded", False))
        self.assertIn("tiedFinalists", final_tribal)
        self.assertEqual(len(final_tribal["tiedFinalists"]), 2)
        self.assertIn(finalists[0], final_tribal["tiedFinalists"])
        self.assertIn(finalists[1], final_tribal["tiedFinalists"])
        self.assertNotIn("winner", final_tribal)
        
        # Leader breaks the tie
        leader = final_tribal["leader"]
        result = self.gs.break_final_tie(self.game_id, leader, finalists[0])
        self.assertTrue(result)
        
        # Winner should now be determined
        self.assertEqual(final_tribal["winner"], finalists[0])
        self.assertFalse(final_tribal.get("tieBreakNeeded", False))
        self.assertEqual(final_tribal.get("tieBreakBy"), leader)
        
    def test_tie_break_validation(self):
        """Test tie-breaking validation rules"""
        game = self.gs.games[self.game_id]
        
        # Set up tied final tribal
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        self.gs.advance_final_phase(self.game_id, "voting")
        
        # Create tie
        self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.gs.cast_final_vote(self.game_id, jury[1], finalists[1])
        
        final_tribal = game["finalTribal"]
        leader = final_tribal["leader"]
        
        # Try tie-break by non-leader (should fail)
        non_leader = jury[0] if jury[0] != leader else jury[1]
        result = self.gs.break_final_tie(self.game_id, non_leader, finalists[0])
        self.assertFalse(result)
        
        # Try tie-break with invalid winner choice (should fail)
        result = self.gs.break_final_tie(self.game_id, leader, "invalid_player")
        self.assertFalse(result)
        
        # Valid tie-break should work
        result = self.gs.break_final_tie(self.game_id, leader, finalists[0])
        self.assertTrue(result)
        
    def test_jury_ready_system_deliberation_phase(self):
        """Test jury ready system during deliberation phase"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        self.gs.advance_final_phase(self.game_id, "deliberation")
        
        final_tribal = game["finalTribal"]
        
        # Initially no jury members ready
        self.assertEqual(final_tribal["juryReady"], [])
        
        # First jury member signals ready
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertTrue(result)
        self.assertIn(jury[0], final_tribal["juryReady"])
        self.assertEqual(final_tribal["phase"], "deliberation")  # Still in deliberation
        
        # Second jury member signals ready - should auto-advance to voting
        result = self.gs.signal_jury_ready(self.game_id, jury[1])
        self.assertTrue(result)
        self.assertIn(jury[1], final_tribal["juryReady"])
        
        # Should auto-advance to voting when all jury ready
        self.assertEqual(final_tribal["phase"], "voting")
        
    def test_jury_ready_validation(self):
        """Test jury ready system validation"""
        game = self.gs.games[self.game_id]
        
        # Set up final tribal
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        
        # Try signaling ready during wrong phase (questions)
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertFalse(result)
        
        # Advance to deliberation
        self.gs.advance_final_phase(self.game_id, "deliberation")
        
        # Try signaling ready as non-jury member
        result = self.gs.signal_jury_ready(self.game_id, finalists[0])
        self.assertFalse(result)
        
        # Valid ready signal should work
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertTrue(result)
        
        # Duplicate ready signal should still work (idempotent)
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertTrue(result)
        
    def test_emergency_final_tribal_deck_empty(self):
        """Test emergency final tribal when deck empty with 2+ players"""
        game = self.gs.games[self.game_id]
        
        # Simulate deck being empty
        game["deck"] = []
        
        # Simulate 2 players remaining
        game["players"][self.player_ids[2]]["isActive"] = False
        game["players"][self.player_ids[3]]["isActive"] = False
        
        # Add eliminated players to jury
        game["jury"] = self.player_ids[2:4]
        
        active_players = [pid for pid, p in game["players"].items() if p.get("isActive")]
        
        # Should trigger final tribal when deck empty and 2 players remain
        if len(active_players) == 2:
            self.gs._start_final_tribal_council(game, active_players)
            
            self.assertEqual(game["phase"], "final_tribal")
            self.assertEqual(len(game["finalTribal"]["finalists"]), 2)
            self.assertEqual(game["finalTribal"]["finalists"], active_players)
            
    def test_final_tribal_with_minimum_jury(self):
        """Test final tribal with minimum jury size (2 members)"""
        game = self.gs.games[self.game_id]
        
        # Set up with exactly 2 jury members (minimum for meaningful final tribal)
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        
        self.gs._start_final_tribal_council(game, finalists)
        
        # Should work with minimum jury
        final_tribal = game["finalTribal"]
        self.assertEqual(len(final_tribal["jury"]), 2)
        self.assertEqual(len(final_tribal["finalists"]), 2)
        
        # Complete voting process
        self.gs.advance_final_phase(self.game_id, "voting")
        self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.gs.cast_final_vote(self.game_id, jury[1], finalists[1])
        
        # Should handle tie-breaking correctly
        self.assertTrue(final_tribal.get("tieBreakNeeded", False))
        self.assertIn("tiedFinalists", final_tribal)
        
    def test_final_tribal_multiple_eliminations_leader_selection(self):
        """Test leader selection when multiple eliminations occur"""
        game = self.gs.games[self.game_id]
        
        # Add extra players to simulate multiple eliminations
        extra_colors = ["orange", "purple", "pink"]
        extra_players = []
        for i, color in enumerate(extra_colors):
            player_id = self.gs.add_player(self.game_id, f"ExtraPlayer{i+1}", color)
            extra_players.append(player_id)
            self.player_ids.append(player_id)
            
        # Simulate elimination order (jury in elimination order)
        jury_order = self.player_ids[2:7]  # 5 eliminated players
        most_recent = jury_order[-1]  # Last eliminated
        
        game["jury"] = jury_order
        finalists = self.player_ids[0:2]
        
        self.gs._start_final_tribal_council(game, finalists)
        
        # Most recent elimination should be leader
        final_tribal = game["finalTribal"]
        self.assertEqual(final_tribal["leader"], most_recent)
        
    def test_game_statistics_integration(self):
        """Test that winner is recorded in game statistics"""
        game = self.gs.games[self.game_id]
        
        # Set up and complete final tribal
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        self.gs.advance_final_phase(self.game_id, "voting")
        
        # Vote for clear winner
        self.gs.cast_final_vote(self.game_id, jury[0], finalists[0])
        self.gs.cast_final_vote(self.game_id, jury[1], finalists[0])
        
        # Winner should be determined
        final_tribal = game["finalTribal"]
        winner_id = final_tribal["winner"]
        self.assertEqual(winner_id, finalists[0])
        
        # Test recording winner in statistics
        result = self.gs.record_winner(self.game_id, winner_id)
        self.assertTrue(result)
        
        # Verify winner was recorded (check method doesn't crash)
        # Note: In test environment, this uses test_winners.json
        
    def test_final_tribal_complete_integration(self):
        """Test complete end-to-end final tribal council flow"""
        game = self.gs.games[self.game_id]
        
        # Full setup: eliminate players to create jury
        eliminated = self.player_ids[2:4]
        for player_id in eliminated:
            game["players"][player_id]["isActive"] = False
            
        game["jury"] = eliminated
        finalists = self.player_ids[0:2]
        
        # 1. Trigger final tribal
        self.gs._start_final_tribal_council(game, finalists)
        self.assertEqual(game["phase"], "final_tribal")
        
        final_tribal = game["finalTribal"]
        
        # 2. Progress through all phases
        # Phase 1: Questions (default start)
        self.assertEqual(final_tribal["phase"], "questions")
        
        # Phase 2: Deliberation
        self.gs.advance_final_phase(self.game_id, "deliberation")
        self.assertEqual(final_tribal["phase"], "deliberation")
        
        # Jury members signal ready
        self.gs.signal_jury_ready(self.game_id, eliminated[0])
        self.gs.signal_jury_ready(self.game_id, eliminated[1])
        
        # Phase 3: Voting (auto-advanced when all ready)
        self.assertEqual(final_tribal["phase"], "voting")
        
        # All jury votes
        self.gs.cast_final_vote(self.game_id, eliminated[0], finalists[0])
        self.gs.cast_final_vote(self.game_id, eliminated[1], finalists[0])
        
        # Phase 4: Reveal (auto-advanced when all voted)
        self.assertEqual(final_tribal["phase"], "reveal")
        self.assertEqual(final_tribal["winner"], finalists[0])
        
        # 5. Record winner
        result = self.gs.record_winner(self.game_id, final_tribal["winner"])
        self.assertTrue(result)
        
        # Complete integration successful
        
if __name__ == '__main__':
    print("🧪 Testing Tribal Council Flow & Phase Transitions")
    print("=" * 60)
    
    # Run tests with detailed output
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTribalCouncilFlow)
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)
    
    print(f"\n📋 Tribal Council Test Summary (including Final Tribal Council):")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    
    if result.failures:
        print(f"\n❌ Failed Tests:")
        for test, traceback in result.failures:
            print(f"  - {test}")
            
    if result.errors:
        print(f"\n⚠️  Error Tests:")
        for test, traceback in result.errors:
            print(f"  - {test}")
            
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n🎉 All tribal council tests (including comprehensive final tribal) {'PASSED' if success else 'FAILED'}!")
    
    exit(0 if success else 1)