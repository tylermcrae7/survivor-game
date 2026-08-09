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


def _tally(gs, gid):
    """Run the council to the tally, through the mandatory idol window.

    "Immunity Idol ... can only be played AFTER all players have voted, but
    BEFORE votes are tallied." So the Leader's first reveal seals the Voting
    Box and calls for idols; a second one opens it. Tests that tallied in a
    single call were encoding a window that could be skipped — which is
    precisely the bug that made idols unplayable.
    """
    result = gs.reveal_votes(gid)
    if isinstance(result, dict) and result.get("idolWindowOpened"):
        result = gs.reveal_votes(gid)
    return result



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

        # Opening hands are randomly dealt, which makes vote-economy assertions
        # flaky (a random Goodwill Gamble adds a mandatory vote). Give everyone a
        # known hand: 3 plain action cards + the 1 Vote Card setup deals.
        self._deal_known_hands()

    def _deal_known_hands(self):
        """Replace random opening hands with a deterministic 3 actions + 1 Vote Card."""
        game = self.gs.games[self.game_id]
        for player in game["players"].values():
            player["hand"] = [
                {"type": "sorry_for_you"},
                {"type": "the_spy_shack"},
                {"type": "camp_raid"},
                {"type": "vote"},
            ]
        self.gs.rules_engine.sync_vote_counters(game)
        
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

        # The idol window and the reveal require a full Voting Box now —
        # every living player votes (or passes) before the phase can advance
        for voter_id in self.player_ids:
            target = next(p for p in self.player_ids if p != voter_id)
            self.gs.cast_vote(self.game_id, voter_id, [{"targetId": target, "votes": 1}])

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
        
    def test_tribal_advantage_control_the_vote(self):
        """
        Control The Vote takes a physical Vote Card from a target.

        Survival Guide: "Play this card during a Tribal Council before voting begins
        to take any player's Vote Card. You MUST use that Vote Card in addition to
        your Vote Card during the Tribal Council at which this card is played."
        """
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        target_id = self.player_ids[1]

        # Start tribal council and advance to advantage_play phase
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")

        control_card = {"type": "control_the_vote"}
        # Deterministic hands: both hold their Vote Card, no Sorry For You in the
        # target's hand (that case is covered below)
        game["players"][player_id]["hand"] = [{"type": "vote"}, control_card]
        game["players"][target_id]["hand"] = [{"type": "vote"}, {"type": "camp_raid"}]
        self.gs.rules_engine.sync_vote_counters(game)
        self.assertEqual(game["players"][player_id]["mandatoryVotes"], 1)
        self.assertEqual(game["players"][target_id]["mandatoryVotes"], 1)

        result = self.gs.play_tribal_advantage(self.game_id, player_id, "control_the_vote", target_id)
        self.assertTrue(result["success"], result.get("message"))

        # The thief must now cast 2 votes; the target has none to cast
        self.assertEqual(game["players"][player_id]["mandatoryVotes"], 2)
        self.assertEqual(game["players"][target_id]["mandatoryVotes"], 0)

        # Verify card was removed from hand
        self.assertNotIn(control_card, game["players"][player_id]["hand"])

        # W2: without your own Vote Card, Control The Vote is refused —
        # "You MUST use that Vote Card in addition to YOUR Vote Card"
        third_id = self.player_ids[2]
        game["players"][third_id]["hand"] = [{"type": "control_the_vote"}]
        game["players"][player_id]["hand"] = [{"type": "vote"}, {"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(game)
        result = self.gs.play_tribal_advantage(self.game_id, third_id, "control_the_vote", player_id)
        self.assertFalse(result["success"])
        self.assertIn("your own Vote Card", result.get("message", ""))
        # The card was NOT consumed by the refusal
        self.assertIn("control_the_vote",
                      [c.get("type") for c in game["players"][third_id]["hand"]])

        # W4: a target holding Sorry For You gets the reactive window
        game["players"][third_id]["hand"] = [{"type": "vote"}, {"type": "control_the_vote"}]
        game["players"][player_id]["hand"] = [{"type": "vote"}, {"type": "sorry_for_you"}]
        self.gs.rules_engine.sync_vote_counters(game)
        result = self.gs.play_tribal_advantage(self.game_id, third_id, "control_the_vote", player_id)
        self.assertTrue(result["success"], result.get("message"))
        pending = game.get("pending_theft") or {}
        self.assertTrue(pending.get("reactive_window_open"))
        self.assertEqual(pending.get("source"), "Control The Vote")
        # Declining hands the Vote Card over
        done = self.gs.complete_pending_theft(self.game_id)
        self.assertTrue(done["success"], done.get("message"))
        self.assertIn("vote", [c.get("type") for c in game["players"][third_id]["hand"]])
        self.assertNotIn("vote", [c.get("type") for c in game["players"][player_id]["hand"]])

    def test_tribal_advantage_goodwill_gamble(self):
        """Goodwill Gamble moves to the recipient and counts as 1 mandatory vote."""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]
        target_id = self.player_ids[1]

        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")

        game["players"][player_id]["hand"].append({"type": "goodwill_gamble"})
        before = game["players"][target_id]["mandatoryVotes"]

        result = self.gs.play_tribal_advantage(self.game_id, player_id, "goodwill_gamble", target_id)
        self.assertTrue(result["success"], result.get("message"))

        # Recipient gains 1 mandatory vote — the Goodwill Gamble must be used here
        self.assertEqual(game["players"][target_id]["mandatoryVotes"], before + 1)
        self.assertIn("goodwill_gamble",
                      [c["type"] for c in game["players"][target_id]["hand"]])

    def test_a_drawn_goodwill_gamble_is_not_its_holders_ballot(self):
        """The card: "GIVE this card to another player… it counts as 1 vote."
        Un-given, it's an Action Card waiting to be played — not a ballot.
        Counting it for the drawer made it a strictly-better Extra Vote nobody
        would ever give away, and handed two bots doubled ballots at a live
        double elimination (game b11498a9, 10 votes tallied where 8 were
        legitimate)."""
        game = self.gs.games[self.game_id]
        holder = self.player_ids[0]
        game["players"][holder]["hand"] = [{"type": "vote"},
                                           {"type": "goodwill_gamble"}]
        self.gs.rules_engine.sync_vote_counters(game)
        self.assertEqual(game["players"][holder]["mandatoryVotes"], 1)
        self.assertEqual(game["players"][holder]["goodwillVotes"], 0)

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        result = self.gs.cast_vote(self.game_id, holder,
                                   [{"targetId": self.player_ids[1], "votes": 2}])
        self.assertFalse(result["success"], "the drawn goodwill must not be castable")

        # And a legal 1-vote ballot leaves the drawn goodwill in hand,
        # unspent — it's a card, not a parchment.
        result = self.gs.cast_vote(self.game_id, holder,
                                   [{"targetId": self.player_ids[1], "votes": 1}])
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn("goodwill_gamble",
                      [c["type"] for c in game["players"][holder]["hand"]])

    def test_a_given_goodwill_gamble_cannot_be_regifted(self):
        """Once given, the card is its recipient's BALLOT — "they can use it
        to vote for any player they want" — never a re-giftable advantage."""
        game = self.gs.games[self.game_id]
        giver, recipient, third = self.player_ids[:3]

        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        game["players"][giver]["hand"].append({"type": "goodwill_gamble"})
        result = self.gs.play_tribal_advantage(
            self.game_id, giver, "goodwill_gamble", recipient)
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(game["players"][recipient]["mandatoryVotes"], 2)

        regift = self.gs.play_tribal_advantage(
            self.game_id, recipient, "goodwill_gamble", third)
        self.assertFalse(regift["success"], "a given goodwill is a ballot, not a gift")
        self.assertEqual(game["players"][third]["mandatoryVotes"], 1)

    def test_steal_a_vote_takes_one_ballot_not_the_whole_box(self):
        """Tyler's council 1, game def05d15: he held two Vote Cards via
        Control The Vote, someone played Steal A Vote, and voteBanned
        silenced BOTH. The card says "steal another player's vote" —
        singular. One ballot moves to the thief; the victim casts what
        remains."""
        game = self.gs.games[self.game_id]
        victim, thief, other = self.player_ids[:3]
        game["players"][victim]["hand"] = [{"type": "vote"}, {"type": "vote"}]
        game["players"][thief]["hand"] = [{"type": "vote"}, {"type": "steal_vote"}]
        self.gs.rules_engine.sync_vote_counters(game)

        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        result = self.gs.play_tribal_advantage(
            self.game_id, thief, "steal_vote", victim)
        self.assertTrue(result["success"], result.get("message"))

        self.assertFalse(game["players"][victim].get("voteBanned"))
        self.assertEqual(game["players"][victim]["mandatoryVotes"], 1)
        self.assertEqual(game["players"][victim]["votesStolenFrom"], 1)
        self.assertEqual(game["players"][thief]["mandatoryVotes"], 2)

        # The victim still votes — the whole point of the fix.
        self.gs.start_voting(self.game_id, "elimination")
        cast = self.gs.cast_vote(self.game_id, victim,
                                 [{"targetId": other, "votes": 1}])
        self.assertTrue(cast["success"], cast.get("message"))
        # And the thief must cast both, like Control The Vote.
        short = self.gs.cast_vote(self.game_id, thief,
                                  [{"targetId": other, "votes": 1}])
        self.assertFalse(short["success"], "the stolen vote is mandatory too")

    def test_steal_a_vote_with_nothing_to_steal_is_refused(self):
        game = self.gs.games[self.game_id]
        victim, thief = self.player_ids[0], self.player_ids[1]
        game["players"][victim]["hand"] = [{"type": "camp_raid"}]
        game["players"][thief]["hand"] = [{"type": "steal_vote"}]

        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        result = self.gs.play_tribal_advantage(
            self.game_id, thief, "steal_vote", victim)
        self.assertFalse(result["success"])
        self.assertIn("steal_vote",
                      [c["type"] for c in game["players"][thief]["hand"]],
                      "a refused steal keeps the card")

    def test_post_council_reset_holds_every_hand_to_exactly_one_vote(self):
        """The other half of Tyler's def05d15 report: vote-banned at council
        1 holding two Vote Cards, he opened the next turn holding THREE (the
        reset appended without collecting) and cast three phantom votes at
        council 2. The reset now sweeps every ballot and deals exactly one:
        unspent votes don't stack, a taken Vote Card implicitly goes home,
        an uncast GIVEN goodwill dies with its council — while Extra Votes
        and a drawn goodwill (an Action Card) survive untouched."""
        game = self.gs.games[self.game_id]
        banned = self.player_ids[0]
        game["players"][banned]["hand"] = [
            {"type": "vote"}, {"type": "vote"},              # own + taken
            {"type": "goodwill_gamble", "given": True},      # uncast ballot
            {"type": "goodwill_gamble"},                     # drawn — a card
            {"type": "extra_vote"},                          # saved — keeps
        ]
        game["players"][banned]["voteBanned"] = True
        self.gs.rules_engine.sync_vote_counters(game)
        self._vote_out(self.player_ids[2],
                       votes_from=[p for p in self.player_ids if p != banned])

        hand = [c["type"] for c in game["players"][banned]["hand"]]
        self.assertEqual(hand.count("vote"), 1,
                         "exactly one Vote Card after every council, always")
        self.assertEqual(hand.count("extra_vote"), 1)
        self.assertEqual(hand.count("goodwill_gamble"), 1)
        self.assertFalse(any(c.get("given")
                             for c in game["players"][banned]["hand"]
                             if c["type"] == "goodwill_gamble"),
                         "the drawn goodwill survives; the given one died")

    def test_a_given_goodwill_cannot_be_regifted_through_play_card_either(self):
        """The door the first guard missed: goodwill is also playable through
        the ordinary play_card route during a council, and a live game
        ping-ponged one three gives deep (Tyler↔Maddie, def05d15)."""
        game = self.gs.games[self.game_id]
        recipient, third = self.player_ids[1], self.player_ids[2]
        game["players"][recipient]["hand"] = [
            {"type": "goodwill_gamble", "given": True}]

        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        result = self.gs.play_card(self.game_id, recipient, 0,
                                   params={"targetId": third})
        self.assertFalse(result["success"])
        self.assertIn("ballot", result.get("message", ""))
        self.assertEqual(len(game["players"][recipient]["hand"]), 1,
                         "the refused regift never leaves the hand")

    def test_vote_cards_cannot_be_played_from_hand(self):
        """Vote and Extra Vote cards are spent by voting, never played as cards."""
        game = self.gs.games[self.game_id]
        player_id = game["turnOrder"][game["currentTurnIndex"]]
        game["players"][player_id]["hasStolen"] = True
        game["players"][player_id]["hand"].append({"type": "extra_vote"})

        idx = len(game["players"][player_id]["hand"]) - 1
        result = self.gs.play_card(self.game_id, player_id, idx)
        self.assertFalse(result["success"])
        self.assertIn("spent when you vote", result["message"])

        
    def test_tribal_advantage_immunity_idol(self):
        """Hidden Immunity Idol is played through play_immunity and negates votes."""
        game = self.gs.games[self.game_id]
        player_id = self.player_ids[0]

        self.gs._trigger_tribal_council(game, "single")

        immunity_card = {"type": "immunity_idol"}
        game["players"][player_id]["hand"].append(immunity_card)

        result = self.gs.play_immunity(self.game_id, playerId=player_id)
        self.assertTrue(result["success"], result.get("message"))

        # Verify immunity was granted
        self.assertTrue(game["players"][player_id]["immunityIdolProtection"])
        self.assertTrue(game["players"][player_id]["immunityPlayed"])

        # Verify card was removed from hand
        self.assertNotIn(immunity_card, game["players"][player_id]["hand"])

        # An idol can only be played once per tribal council
        game["players"][player_id]["hand"].append({"type": "immunity_idol"})
        again = self.gs.play_immunity(self.game_id, playerId=player_id)
        self.assertFalse(again["success"])
        
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
        
        game["players"][player_id]["hand"].append({"type": "control_the_vote"})

        # announcement phase is before advantage_play/discussion (should fail)
        result = self.gs.play_tribal_advantage(
            self.game_id, player_id, "control_the_vote", self.player_ids[1])
        self.assertFalse(result["success"])

        # Advance to immunity phase and try again (should fail — voting has started)
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        result = self.gs.play_tribal_advantage(
            self.game_id, player_id, "control_the_vote", self.player_ids[1])
        self.assertFalse(result["success"])
        
    def test_tribal_council_voting_mechanics(self):
        """Test voting system during tribal council"""
        game = self.gs.games[self.game_id]
        
        # Start tribal council, then open voting
        self.gs._trigger_tribal_council(game, "single")
        result = self.gs.start_voting(self.game_id, "elimination")
        self.assertTrue(result["success"], result.get("message"))
        
        # Verify voting state
        self.assertEqual(game["currentVote"]["phase"], "voting")
        self.assertEqual(game["currentVote"]["votes"], {})
        
        # Cast votes (3 players vote for the 4th)
        target_id = self.player_ids[3]
        for i in range(3):
            voter_id = self.player_ids[i]
            result = self.gs.cast_vote(self.game_id, voter_id, [{"targetId": target_id, "votes": 1}])
            self.assertTrue(result["success"], result.get("message"))

        # Verify votes were recorded
        self.assertEqual(len(game["currentVote"]["votes"]), 3)
        for i in range(3):
            voter_id = self.player_ids[i]
            self.assertIn(target_id, game["currentVote"]["votes"][voter_id])
            
    def test_two_mandatory_vote_cards_split_across_two_targets(self):
        """Control The Vote leaves a player holding TWO Vote Cards — two
        parchments, and like the physical game they may carry two different
        names. The server has always accepted the split (validation only
        checks totals); this pins it against a future 'helpful' one-target
        rule, because both clients now offer the split UI for exactly this
        hand (found live: Tyler, council b11498a9, wanted to split and the
        phone never offered)."""
        game = self.gs.games[self.game_id]
        voter = self.player_ids[0]
        target_a, target_b = self.player_ids[1], self.player_ids[2]
        # The hand Control The Vote produces: own Vote Card plus the taken one.
        game["players"][voter]["hand"] = [{"type": "vote"}, {"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(game)
        self.assertEqual(game["players"][voter]["mandatoryVotes"], 2)

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")

        # Splitting 1 + 1 across two names is a legal ballot...
        result = self.gs.cast_vote(self.game_id, voter, [
            {"targetId": target_a, "votes": 1},
            {"targetId": target_b, "votes": 1},
        ])
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(game["currentVote"]["votes"][voter],
                         {target_a: 1, target_b: 1})

    def test_two_mandatory_vote_cards_cannot_be_held_back(self):
        """The other half of the same rule: both Vote Cards MUST be cast —
        splitting is allowed, withholding is not."""
        game = self.gs.games[self.game_id]
        voter = self.player_ids[0]
        game["players"][voter]["hand"] = [{"type": "vote"}, {"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(game)

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")

        result = self.gs.cast_vote(self.game_id, voter,
                                   [{"targetId": self.player_ids[1], "votes": 1}])
        self.assertFalse(result["success"])
        self.assertIn("must cast all 2", result.get("message", ""))

    def _vote_out(self, target_id, elimination_type="single", votes_from=None):
        """Run one full tribal council that votes `target_id` out."""
        game = self.gs.games[self.game_id]
        self.gs._trigger_tribal_council(game, elimination_type)
        self.gs.start_voting(self.game_id, "elimination")

        # "Everyone must vote" — the player being voted out casts a vote too.
        alive = [p for p in self.player_ids if not game["players"][p].get("isEliminated")]
        voters = votes_from if votes_from is not None else alive
        for voter_id in voters:
            # The target can't vote for themselves, so they vote for the next player along
            vote_for = target_id if voter_id != target_id else next(
                p for p in alive if p != target_id)
            # Every Vote Card / Goodwill Gamble in hand must be cast at this tribal
            votes = max(1, game["players"][voter_id]["mandatoryVotes"])
            result = self.gs.cast_vote(self.game_id, voter_id,
                                       [{"targetId": vote_for, "votes": votes}])
            self.assertTrue(result["success"], result.get("message"))

        # Idols are played after the votes are in, before the tally
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        return self.gs.complete_tribal(self.game_id)

    def test_tribal_council_first_vote_out_flips_one_character_card(self):
        """
        Official rules: "As long as you have at least one Survivor Character Card,
        you're still in the game." The first vote-out turns over ONE card.
        """
        game = self.gs.games[self.game_id]
        target_id = self.player_ids[3]

        result = self._vote_out(target_id)
        self.assertTrue(result["success"], result.get("message"))

        target = game["players"][target_id]
        self.assertEqual(target["characterCards"], 1)
        self.assertFalse(target["isEliminated"])
        self.assertTrue(target["isActive"])
        self.assertNotIn(target_id, game["jury"])

        # Everyone still in the game gets a Vote Card back
        for player in game["players"].values():
            if not player["isEliminated"]:
                self.assertEqual(player["voteCards"], 1)

        # Verify game returned to playing phase
        self.assertEqual(game["phase"], "playing")
        self.assertNotIn("currentVote", game)

    def test_tribal_council_second_vote_out_eliminates_and_juries(self):
        """Both Survivor Character Cards gone = eliminated, and you join the Jury."""
        game = self.gs.games[self.game_id]
        target_id = self.player_ids[3]

        self._vote_out(target_id)
        self.assertEqual(game["players"][target_id]["characterCards"], 1)

        result = self._vote_out(target_id)
        self.assertTrue(result["success"], result.get("message"))

        target = game["players"][target_id]
        self.assertEqual(target["characterCards"], 0)
        self.assertTrue(target["isEliminated"])
        self.assertFalse(target["isActive"])
        self.assertIn(target_id, game["jury"])

        self.assertEqual(len([p for p in game["players"].values() if not p["isEliminated"]]), 3)
        
    def test_tribal_council_double_elimination(self):
        """Test double elimination tribal council with 6 players"""
        # A separate 6-player game — players must be added before the game starts so
        # they get a turn order seat and their Vote Card.
        self.game_id = self.gs.create_game()
        self.player_ids = [
            self.gs.add_player(self.game_id, f"Player{i+1}", c)
            for i, c in enumerate(["red", "blue", "green", "yellow", "orange", "purple"])
        ]
        self.gs.start_full_game(self.game_id)
        self._deal_known_hands()
        game = self.gs.games[self.game_id]

        # Start double elimination tribal council
        self.gs._trigger_tribal_council(game, "double")
        self.gs.start_voting(self.game_id, "elimination")

        # Cast votes to vote out 2 players: 2 votes each, tied for most
        target1_id = self.player_ids[4]
        target2_id = self.player_ids[5]

        for i in range(2):
            self.gs.cast_vote(self.game_id, self.player_ids[i], [{"targetId": target1_id, "votes": 1}])
        for i in range(2, 4):
            self.gs.cast_vote(self.game_id, self.player_ids[i], [{"targetId": target2_id, "votes": 1}])
        # The two targets vote for each other, keeping them tied at 3 apiece
        self.gs.cast_vote(self.game_id, target1_id, [{"targetId": target2_id, "votes": 1}])
        self.gs.cast_vote(self.game_id, target2_id, [{"targetId": target1_id, "votes": 1}])
        
        # Complete tribal council
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))

        # Official rule: "If 2 players are tied with the most votes, both are voted out."
        self.assertFalse(game["currentVote"]["tieBreakNeeded"], game["currentVote"]["resolution"])
        self.assertCountEqual(game["currentVote"]["eliminated"], [target1_id, target2_id])

        result = self.gs.complete_tribal(self.game_id)
        self.assertTrue(result["success"], result.get("message"))

        # Both were voted out, so both turned over ONE Survivor Character Card —
        # neither is eliminated yet, so all 6 are still in the game.
        self.assertEqual(game["players"][target1_id]["characterCards"], 1)
        self.assertEqual(game["players"][target2_id]["characterCards"], 1)
        self.assertFalse(game["players"][target1_id]["isEliminated"])
        self.assertFalse(game["players"][target2_id]["isEliminated"])
        self.assertEqual(len([p for p in game["players"].values() if not p["isEliminated"]]), 6)
        
    def test_block_a_vote_council_still_reaches_reveal_and_completes(self):
        """
        Block A Vote takes its target out of the Voting Box. The server refuses
        their ballot — even an empty one — so the council must not wait on it.
        Counting a blocked player as "still to vote" wedged Tribal forever:
        neither the idol window nor the reveal could ever open.
        """
        game = self.gs.games[self.game_id]
        blocker, blocked = self.player_ids[0], self.player_ids[3]

        self.gs._trigger_tribal_council(game, "single", drawer_id=blocker)
        game["players"][blocker]["hand"].append({"type": "block_vote"})
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        played = self.gs.play_tribal_advantage(
            self.game_id, playerId=blocker, advantageType="block_vote",
            targetId=blocked)
        self.assertTrue(played["success"], played.get("message"))
        self.assertTrue(game["players"][blocked]["voteBanned"])

        self.gs.advance_tribal_phase(self.game_id, "discussion")
        self.gs.start_voting(self.game_id, "elimination")

        # The banned player is refused even with an empty ballot...
        refused = self.gs.cast_vote(self.game_id, blocked, [])
        self.assertFalse(refused["success"])
        self.assertIn("banned from voting", refused["message"])

        # ...and the box is full without them
        for voter_id in self.player_ids[:3]:
            res = self.gs.cast_vote(self.game_id, voter_id,
                                    [{"targetId": blocked, "votes": 1}])
            self.assertTrue(res["success"], res.get("message"))
        self.assertEqual(self.gs._ballot_box_missing(game), "")

        # The idol window opens, and so does the box
        self.assertTrue(self.gs.advance_tribal_phase(self.game_id, "immunity"))
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        self.assertEqual(game["currentVote"]["eliminated"], [blocked])
        self.assertEqual(game["currentVote"]["voteResults"], {blocked: 3})
        # ...and the reveal says why a ballot is missing
        self.assertEqual(reveal["blockedVoters"], [blocked])
        self.assertIn("was blocked from voting", reveal["message"])

        done = self.gs.complete_tribal(self.game_id)
        self.assertTrue(done["success"], done.get("message"))
        self.assertEqual(game["players"][blocked]["characterCards"], 1)
        # The ban lifts with the council
        self.assertFalse(game["players"][blocked].get("voteBanned", False))

    def test_a_blocked_ballot_never_reaches_the_tally(self):
        """A ban landing after a ballot was cast still counts as nothing."""
        game = self.gs.games[self.game_id]
        banned, target = self.player_ids[0], self.player_ids[3]

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        for voter_id in self.player_ids:
            vote_for = target if voter_id != target else self.player_ids[1]
            self.gs.cast_vote(self.game_id, voter_id,
                              [{"targetId": vote_for, "votes": 1}])

        game["players"][banned]["voteBanned"] = True
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        # 3 ballots named the target; the banned one is not among them
        self.assertEqual(game["currentVote"]["voteResults"].get(target), 2)

    def test_the_idol_window_cannot_be_skipped(self):
        """A reveal from `voting` seals the box — it must never tally.

        The reported bug: "I had immunity idols and it wouldn't let me play
        them." The card was legal the whole time (play_immunity checks the game
        phase, never the tribal sub-phase) — but the only screen that offers it
        lives in the immunity phase, so a Leader who went straight to the
        reveal silently voided every idol at the table.
        """
        game = self.gs.games[self.game_id]
        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        for voter_id in self.player_ids:
            target = self.player_ids[3] if voter_id != self.player_ids[3] else self.player_ids[1]
            self.gs.cast_vote(self.game_id, voter_id, [{"targetId": target, "votes": 1}])

        first = self.gs.reveal_votes(self.game_id)
        self.assertTrue(first["success"], first.get("message"))
        self.assertTrue(first.get("idolWindowOpened"))
        self.assertEqual(game["currentVote"]["phase"], "immunity")
        # Nothing tallied: the votes are still sealed in the box.
        self.assertFalse(game["currentVote"].get("voteResults"))

        second = self.gs.reveal_votes(self.game_id)
        self.assertTrue(second["success"], second.get("message"))
        self.assertEqual(game["currentVote"]["phase"], "reveal")
        self.assertTrue(game["currentVote"].get("voteResults"))

    def test_the_idol_window_cannot_open_before_the_box_is_full(self):
        """"...AFTER all players have voted" — the other half of the rule."""
        game = self.gs.games[self.game_id]
        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        # Exactly one ballot placed, out of four.
        self.gs.cast_vote(self.game_id, self.player_ids[0],
                          [{"targetId": self.player_ids[3], "votes": 1}])

        early = self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.assertFalse(early.get("success") if isinstance(early, dict) else early)
        self.assertEqual(game["currentVote"]["phase"], "voting")

    def test_discussion_cannot_jump_straight_to_the_idol_window(self):
        """The old table let a Leader open the idols with an empty box."""
        game = self.gs.games[self.game_id]
        self.gs._trigger_tribal_council(game, "single")
        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        self.gs.advance_tribal_phase(self.game_id, "discussion")

        jumped = self.gs.advance_tribal_phase(self.game_id, "immunity")
        self.assertFalse(jumped.get("success") if isinstance(jumped, dict) else jumped)
        self.assertEqual(game["currentVote"]["phase"], "discussion")

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
        self.assertEqual(game["phase"], "playing")
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
        target_id = self.player_ids[3]

        # Takes two vote-outs to lose both Survivor Character Cards
        self._vote_out(target_id)
        self.assertEqual(game["jury"], [])

        self._vote_out(target_id)

        eliminated_player = game["players"][target_id]
        self.assertFalse(eliminated_player["isActive"])
        self.assertTrue(eliminated_player["isEliminated"])
        self.assertIn(target_id, game["jury"])
        
    def test_tribal_council_immunity_protection(self):
        """
        Votes for a player who plays an Immunity Idol do not count. With nobody
        else holding votes, the Council Leader must choose from the priority ladder.
        """
        game = self.gs.games[self.game_id]
        immune_player_id = self.player_ids[2]

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.game_id, "elimination")

        # Everyone else votes for the soon-to-be-immune player; the immune
        # player's Vote Card was stolen earlier, so they legally pass the box
        # (it must still reach everyone before the idol window or the tally)
        game["players"][immune_player_id]["hand"] = [
            c for c in game["players"][immune_player_id]["hand"]
            if c.get("type") not in ("vote", "goodwill_gamble", "extra_vote")
        ]
        self.gs.rules_engine.sync_vote_counters(game)
        for voter_id in self.player_ids:
            if voter_id != immune_player_id:
                self.gs.cast_vote(self.game_id, voter_id,
                                  [{"targetId": immune_player_id, "votes": 1}])
            else:
                self.gs.cast_vote(self.game_id, voter_id, [])

        # Idol is played after the votes are in, before the tally
        self.gs.advance_tribal_phase(self.game_id, "immunity")
        game["players"][immune_player_id]["hand"].append({"type": "immunity_idol"})
        played = self.gs.play_immunity(self.game_id, playerId=immune_player_id)
        self.assertTrue(played["success"], played.get("message"))

        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))

        current_vote = game["currentVote"]
        # All 3 votes negated, so no one has votes -> unclear, Leader must choose
        self.assertEqual(current_vote["voteResults"], {})
        self.assertIn(immune_player_id, current_vote["protectedPlayers"])
        self.assertTrue(current_vote["tieBreakNeeded"])

        # The idol player is only choosable as a last resort, after everyone else
        self.assertNotIn(immune_player_id, current_vote["tiedPlayers"][:3])
        self.assertEqual(sorted(current_vote["tiedPlayers"][:3]),
                         sorted([p for p in self.player_ids if p != immune_player_id]))

        raw = current_vote.get("rawVoteResults") or {}
        self.assertGreater(raw.get(immune_player_id, 0), 0,
                           "the reveal must remember the votes immunity erased")

        # Break the tie the Leader now faces, then complete the council, and
        # confirm the recap keeps the pre-immunity tally.
        leader_id = current_vote["councilLeaderId"]
        tie_broken = self.gs.tie_break(self.game_id, leaderId=leader_id,
                                       chosenId=current_vote["tiedPlayers"][0])
        self.assertTrue(tie_broken["success"], tie_broken.get("message"))

        completed = self.gs.complete_tribal(self.game_id)
        self.assertTrue(completed["success"], completed.get("message"))

        record = game["gameHistory"][-1]
        self.assertEqual(record.get("raw_vote_results"), raw,
                         "the recap must keep the pre-immunity tally")

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

        # Deliberation carries the jury's ready signals and cannot be skipped.
        result = self.gs.advance_final_phase(self.game_id, "voting")
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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn(jury[0], final_tribal["juryReady"])
        self.assertEqual(final_tribal["phase"], "deliberation")  # Still in deliberation

        # Second jury member signals ready - should auto-advance to voting
        result = self.gs.signal_jury_ready(self.game_id, jury[1])
        self.assertTrue(result["success"], result.get("message"))
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

        # Try signaling ready during wrong phase (questions) — this is the
        # refusal Tyler hit live: a reasoned refusal, not a bare False.
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertFalse(result["success"])
        self.assertIn("deliberation opens the vote", result["message"])

        # Advance to deliberation
        self.gs.advance_final_phase(self.game_id, "deliberation")

        # Try signaling ready as non-jury member
        result = self.gs.signal_jury_ready(self.game_id, finalists[0])
        self.assertFalse(result["success"])
        self.assertIn("Only jury members raise a finger", result["message"])

        # Valid ready signal should work
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn("is ready to vote", result["message"])

        # Duplicate ready signal is refused — you can't raise the same finger twice
        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertFalse(result["success"])
        self.assertIn("already raised your finger", result["message"])

    # ── S1: the jury signal says why (every refusal, and the success line) ──

    def test_jury_ready_refuses_with_a_message_when_game_is_missing(self):
        result = self.gs.signal_jury_ready("no-such-game", "someone")
        self.assertFalse(result["success"])
        self.assertTrue(result.get("message"))

    def test_jury_ready_refuses_with_a_message_when_no_member_given(self):
        result = self.gs.signal_jury_ready(self.game_id, None)
        self.assertFalse(result["success"])
        self.assertTrue(result.get("message"))

    def test_jury_ready_refuses_outside_final_tribal_phase(self):
        """Game hasn't even reached final tribal yet."""
        result = self.gs.signal_jury_ready(self.game_id, self.player_ids[0])
        self.assertFalse(result["success"])
        self.assertIn("Final Tribal hasn't started", result["message"])

    def test_jury_ready_success_message_names_the_signaler(self):
        game = self.gs.games[self.game_id]
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        self.gs.advance_final_phase(self.game_id, "deliberation")

        result = self.gs.signal_jury_ready(self.game_id, jury[0])
        self.assertTrue(result["success"], result.get("message"))
        name = game["players"][jury[0]]["name"]
        self.assertEqual(result["message"], f"{name} is ready to vote")

    def test_jury_ready_http_route_surfaces_the_reason(self):
        """The exact live-log failure: a phone that gets nothing but False."""
        import survivor_server
        game = self.gs.games[self.game_id]
        jury = self.player_ids[2:4]
        finalists = self.player_ids[0:2]
        game["jury"] = jury
        self.gs._start_final_tribal_council(game, finalists)
        # Still in "questions" — the door Tyler hit live.
        survivor_server.game_state = self.gs
        client = survivor_server.app.test_client()

        res = client.post('/api/final/ready',
                          json={"gameId": self.game_id, "juryMemberId": jury[0]})

        self.assertEqual(res.status_code, 400)
        body = res.get_json()
        self.assertFalse(body["success"])
        self.assertIn("deliberation opens the vote", body["message"])

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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
        self.gs.advance_final_phase(self.game_id, "deliberation")
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
