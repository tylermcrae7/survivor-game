#!/usr/bin/env python3
"""
Council integrity — regressions from the 2026-10-15 code review.

Each test pins a bug that was reproduced against the real server before it was
fixed: replayed council closes, double-tapped vote starts, ballots inflated by
negative counts, a Control The Vote that outlived its council, a reset that
wedged the drawer's turn, a Final Tribal whose controls went to the wrong
phone, a Hall of Fame that never recorded anything, and the rest below.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState, NULLIFIER_WINDOW_SECONDS  # noqa: E402
from rules_engine import SurvivorRulesEngine  # noqa: E402


class CouncilTestBase(unittest.TestCase):
    PLAYER_COUNT = 4
    DECK_MODE = "extended"   # nullifiers and the house advantages

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        self.gs = GameState()
        self.gid = self.gs.create_game(deckMode=self.DECK_MODE)
        colors = ["red", "blue", "green", "yellow", "orange", "purple"]
        self.pids = [self.gs.add_player(self.gid, f"P{i + 1}", colors[i])
                     for i in range(self.PLAYER_COUNT)]
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]
        for p in self.game["players"].values():
            p["hand"] = [{"type": "camp_raid"}, {"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(self.game)

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── helpers ──

    def hand_types(self, pid):
        return [c.get("type") for c in self.game["players"][pid]["hand"]]

    def open_council(self, kind="single", leader=None):
        leader = leader or self.pids[0]
        self.gs._trigger_tribal_council(self.game, kind, drawer_id=leader)
        self.game["currentVote"]["phase"] = "discussion"
        return leader

    def vote_all(self, target_of):
        for pid in self.pids:
            if self.game["players"][pid].get("isEliminated"):
                continue
            target = target_of(pid)
            r = self.gs.cast_vote(self.gid, voterId=pid,
                                  votesData=[{"targetId": target, "votes": 1}])
            self.assertTrue(r["success"], r.get("message"))

    def tally(self):
        r = self.gs.reveal_votes(self.gid)
        if r.get("idolWindowOpened"):
            r = self.gs.reveal_votes(self.gid)
        return r


class TestTheCeremonyRunsOnce(CouncilTestBase):

    def test_a_second_start_voting_keeps_the_ballots(self):
        self.open_council()
        self.assertTrue(self.gs.start_voting(self.gid)["success"])
        r = self.gs.cast_vote(self.gid, voterId=self.pids[1],
                              votesData=[{"targetId": self.pids[2], "votes": 1}])
        self.assertTrue(r["success"])

        again = self.gs.start_voting(self.gid)
        self.assertTrue(again["success"])          # idempotent, not an error
        self.assertIn(self.pids[1], self.game["currentVote"]["votes"])
        self.assertTrue(self.game["players"][self.pids[1]]["hasVoted"])

    def test_start_voting_after_the_box_is_sealed_is_refused(self):
        self.open_council()
        self.gs.start_voting(self.gid)
        self.vote_all(lambda pid: self.pids[1] if pid != self.pids[1] else self.pids[2])
        self.assertTrue(self.gs.reveal_votes(self.gid)["idolWindowOpened"])
        self.assertFalse(self.gs.start_voting(self.gid)["success"])
        self.assertEqual(self.game["currentVote"]["phase"], "immunity")

    def test_re_advancing_to_voting_does_not_clear_who_voted(self):
        self.open_council()
        self.gs.advance_tribal_phase(self.gid, "voting")
        self.gs.cast_vote(self.gid, voterId=self.pids[1],
                          votesData=[{"targetId": self.pids[2], "votes": 1}])
        self.assertTrue(self.gs.advance_tribal_phase(self.gid, "voting"))
        self.assertTrue(self.game["players"][self.pids[1]]["hasVoted"])

    def test_advancing_to_reveal_tallies_instead_of_wedging(self):
        self.open_council()
        self.gs.start_voting(self.gid)
        self.vote_all(lambda pid: self.pids[1] if pid != self.pids[1] else self.pids[2])
        self.gs.advance_tribal_phase(self.gid, "immunity")
        r = self.gs.advance_tribal_phase(self.gid, "reveal")
        self.assertTrue(r["success"], r)
        self.assertEqual(self.game["currentVote"]["eliminated"], [self.pids[1]])
        self.assertTrue(self.gs.complete_tribal(self.gid)["success"])

    def test_complete_tribal_twice_does_not_replay_the_vote_outs(self):
        self.open_council()
        self.gs.start_voting(self.gid)
        self.vote_all(lambda pid: self.pids[1] if pid != self.pids[1] else self.pids[2])
        self.tally()
        self.assertTrue(self.gs.complete_tribal(self.gid)["success"])
        cards_after_one = self.game["players"][self.pids[1]]["characterCards"]
        discard_after_one = len(self.game.get("discard", []))

        again = self.gs.complete_tribal(self.gid)
        self.assertFalse(again["success"])
        self.assertEqual(self.game["players"][self.pids[1]]["characterCards"], cards_after_one)
        self.assertEqual(len(self.game.get("discard", [])), discard_after_one)


class TestBallots(CouncilTestBase):

    def setUp(self):
        super().setUp()
        self.open_council()
        self.gs.start_voting(self.gid)

    def test_negative_counts_cannot_inflate_a_ballot(self):
        r = self.gs.cast_vote(self.gid, voterId=self.pids[0], votesData=[
            {"targetId": self.pids[1], "votes": 5},
            {"targetId": self.pids[2], "votes": -4},
        ])
        self.assertFalse(r["success"])
        self.assertNotIn(self.pids[0], self.game["currentVote"]["votes"])
        self.assertIn("vote", self.hand_types(self.pids[0]))

    def test_non_integer_counts_are_refused_not_crashed_on(self):
        for bad in ("1", 1.5, True, None):
            r = self.gs.cast_vote(self.gid, voterId=self.pids[0], votesData=[
                {"targetId": self.pids[1], "votes": bad}])
            self.assertFalse(r["success"], bad)
        r = self.gs.cast_vote(self.gid, voterId=self.pids[0], votesData=["nope"])
        self.assertFalse(r["success"])


class TestIdols(CouncilTestBase):

    def test_an_idol_outside_the_idol_window_is_refused_and_kept(self):
        self.open_council()
        self.game["players"][self.pids[0]]["hand"].append({"type": "immunity_idol"})
        r = self.gs.play_immunity(self.gid, playerId=self.pids[0])
        self.assertFalse(r["success"])
        self.assertIn("immunity_idol", self.hand_types(self.pids[0]))

    def test_played_idols_and_nullifiers_reach_the_discard(self):
        self.open_council()
        self.gs.start_voting(self.gid)
        self.vote_all(lambda pid: self.pids[1] if pid != self.pids[1] else self.pids[2])
        self.gs.reveal_votes(self.gid)   # seal → idol window
        self.game["players"][self.pids[1]]["hand"].append({"type": "immunity_idol"})
        self.game["players"][self.pids[2]]["hand"].append({"type": "idol_nullifier"})
        self.assertTrue(self.gs.play_immunity(self.gid, playerId=self.pids[1])["success"])
        self.assertTrue(self.gs.block_immunity(
            self.gid, playerId=self.pids[2], targetId=self.pids[1])["success"])
        discarded = [c.get("type") for c in self.game.get("discard", [])]
        self.assertIn("immunity_idol", discarded)
        self.assertIn("idol_nullifier", discarded)

    def test_a_fresh_idol_protects_a_nullified_player(self):
        engine = self.gs.rules_engine
        target = self.game["players"][self.pids[1]]
        target["immunityIdolProtection"] = False
        target["idolNullified"] = True
        engine._effect_immunity_idol(self.game, self.pids[2], {"type": "immunity_idol"},
                                     {"targetId": self.pids[1]})
        self.assertTrue(target["immunityIdolProtection"])
        self.assertNotIn("idolNullified", target)

    def test_a_silent_nullifier_holder_cannot_freeze_the_council(self):
        self.open_council()
        self.gs.start_voting(self.gid)
        self.vote_all(lambda pid: self.pids[1] if pid != self.pids[1] else self.pids[2])
        self.gs.reveal_votes(self.gid)
        self.game["players"][self.pids[1]]["hand"].append({"type": "immunity_idol"})
        self.game["players"][self.pids[3]]["hand"].append({"type": "idol_nullifier"})
        r = self.gs.play_immunity(self.gid, playerId=self.pids[1])
        self.assertTrue(r["nullifierWindowOpen"])
        self.assertFalse(self.gs.reveal_votes(self.gid)["success"])

        # Silence past the deadline is a decline; a state read resolves it
        self.game["pending_nullifier"]["deadline"] = time.time() - 1
        self.gs.get_game_state(self.gid)
        self.assertNotIn("pending_nullifier", self.game)
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])
        self.assertGreater(NULLIFIER_WINDOW_SECONDS, 0)


class TestRaidWindowAndTheCouncil(CouncilTestBase):

    def test_a_control_the_vote_waiting_on_sorry_for_you_holds_the_vote(self):
        self.open_council()
        a, b = self.pids[0], self.pids[1]
        self.game["players"][a]["hand"] = [{"type": "vote"}, {"type": "control_the_vote"}]
        self.game["players"][b]["hand"] = [{"type": "vote"}, {"type": "sorry_for_you"}]
        idx = self.hand_types(a).index("control_the_vote")
        r = self.gs.play_card(self.gid, a, idx, {"targetId": b})
        self.assertTrue(r["success"], r.get("message"))
        self.assertTrue(self.game["pending_theft"]["reactive_window_open"])

        refused = self.gs.start_voting(self.gid)
        self.assertFalse(refused["success"])
        self.assertIn("raid", refused["message"])
        self.assertNotEqual(self.game["currentVote"]["phase"], "voting")

    def test_a_held_vote_card_take_dies_with_its_council(self):
        a, b = self.pids[0], self.pids[1]
        self.game["pending_theft"] = {
            "reactive_window_open": True, "targetId": b, "thiefId": a,
            "_resume": {"kind": "vote_card", "thiefId": a},
        }
        self.game["players"][b]["hand"] = [{"type": "vote"}]
        self.gs.rules_engine._reset_post_tribal_flags(self.game)
        self.assertNotIn("pending_theft", self.game)
        self.assertEqual(self.hand_types(b), ["vote"])
        self.assertEqual(self.hand_types(a), ["camp_raid", "vote"])   # just their own


class TestResetTribal(CouncilTestBase):

    def test_reset_is_refused_once_ballots_are_in(self):
        self.open_council()
        self.gs.start_voting(self.gid)
        self.gs.cast_vote(self.gid, voterId=self.pids[1],
                          votesData=[{"targetId": self.pids[2], "votes": 1}])
        r = self.gs.reset_tribal_council(self.gid)
        self.assertFalse(r["success"])
        self.assertEqual(self.game["phase"], "tribal_council")

    def test_reset_before_the_vote_hands_the_torch_on(self):
        drawer = self.pids[0]
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(drawer)
        self.game["players"][drawer].update(hasStolen=True, hasDrawn=True)
        self.open_council(leader=drawer)
        discard_before = len(self.game.get("discard", []))

        r = self.gs.reset_tribal_council(self.gid)
        self.assertTrue(r["success"], r.get("message"))
        self.assertEqual(self.game["phase"], "playing")
        current = self.game["turnOrder"][self.game["currentTurnIndex"]]
        self.assertNotEqual(current, drawer)
        self.assertFalse(self.game["players"][current]["hasStolen"])
        self.assertEqual(len(self.game["discard"]), discard_before + 1)


class TestFinalTribalLeadership(CouncilTestBase):

    def test_every_leader_signal_names_the_final_leader(self):
        juror = self.pids[3]
        self.game["players"][juror]["isEliminated"] = True
        self.game["jury"] = [juror]
        self.game["currentVote"] = {"councilLeaderId": self.pids[0], "phase": "reveal"}
        self.gs._start_final_tribal_council(self.game, [self.pids[0], self.pids[1]])

        self.assertEqual(self.game["finalTribal"]["leader"], juror)
        self.assertEqual(self.game["currentVote"]["councilLeaderId"], juror)
        leaders = [pid for pid, p in self.game["players"].items() if p["isCouncilLeader"]]
        self.assertEqual(leaders, [juror])


class TestHallOfFame(CouncilTestBase):

    def winners(self):
        with open(GameState._WINNERS_FILE) as f:
            return json.load(f)

    def finish_with(self, winner):
        self.game["phase"] = "final_tribal"
        ft = self.game["finalTribal"] = {
            "phase": "voting", "finalists": [self.pids[0], self.pids[1]],
            "jury": [self.pids[2]], "leader": self.pids[2], "votes": {self.pids[2]: winner},
        }
        self.gs._determine_final_winner(self.game, ft)

    def test_a_finished_game_records_itself_once(self):
        self.finish_with(self.pids[0])
        self.assertEqual(self.game["phase"], "finished")
        self.assertEqual([w["game_id"] for w in self.winners()], [self.gid])

        # A phone that still taps "Record Winner" doesn't add a second line
        r = self.gs.record_winner(self.gid, winnerId=self.pids[0])
        self.assertTrue(r["success"])
        self.assertEqual(len(self.winners()), 1)

    def test_record_winner_refuses_a_live_game_or_the_wrong_winner(self):
        self.assertFalse(self.gs.record_winner(self.gid, winnerId=self.pids[0])["success"])
        self.assertEqual(self.game["phase"], "playing")
        self.finish_with(self.pids[0])
        self.assertFalse(self.gs.record_winner(self.gid, winnerId=self.pids[1])["success"])

    def test_an_unreadable_hall_of_fame_is_preserved_not_overwritten(self):
        with open(GameState._WINNERS_FILE, "w") as f:
            f.write('[{"winner_name": "Tyler", "da')
        self.finish_with(self.pids[0])
        preserved = [n for n in os.listdir(".") if n.startswith("winners.json.corrupt.")]
        self.assertEqual(len(preserved), 1)
        self.assertEqual(len(self.winners()), 1)


class TestResetGameStartsClean(CouncilTestBase):

    def test_reset_clears_what_the_last_game_left_behind(self):
        self.game["discard"] = [{"type": "immunity_idol"}] * 4
        self.game["pending_discards"] = {"awaiting": [self.pids[0]], "deadline": 0}
        self.game["pending_nullifier"] = {"reactive_window_open": True}
        self.game["_ledger"] = {"grudges": "everywhere"}
        self.game["phase"] = "finished"
        self.assertTrue(self.gs.reset_game(self.gid)["success"])
        for key in ("discard", "pending_discards", "pending_nullifier", "_ledger"):
            self.assertNotIn(key, self.game, key)


class TestTargetsAndTakes(CouncilTestBase):

    def setUp(self):
        super().setUp()
        self.me = self.pids[0]
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(self.me)
        for p in self.game["players"].values():
            p["hasStolen"] = True

    def play(self, card_type, **params):
        hand = self.game["players"][self.me]["hand"]
        hand.append({"type": card_type})
        return self.gs.play_card(self.gid, self.me, len(hand) - 1, params)

    def test_targeted_cards_cannot_target_yourself(self):
        r = self.play("camp_raid", targetId=self.me)
        self.assertFalse(r["success"])
        self.assertIn("camp_raid", self.hand_types(self.me))

    def test_goodwill_to_yourself_mints_no_ballot(self):
        self.open_council(leader=self.me)
        self.game["currentVote"]["phase"] = "advantage_play"
        r = self.play("goodwill_gamble", targetId=self.me)
        self.assertFalse(r["success"])
        r = self.gs.play_tribal_advantage(self.gid, self.me, "goodwill_gamble", self.me)
        self.assertFalse(r["success"])

    def test_an_alliance_needs_a_living_partner_and_victim(self):
        self.game["players"][self.pids[1]]["isEliminated"] = True
        r = self.play("lets_form_an_alliance", allyId=self.pids[1], victimId=self.pids[2])
        self.assertFalse(r["success"])
        r = self.play("lets_form_an_alliance", allyId=self.pids[2], victimId=self.pids[1])
        self.assertFalse(r["success"])

    def test_control_the_vote_by_play_card_checks_for_a_vote_card(self):
        self.open_council(leader=self.me)
        self.game["currentVote"]["phase"] = "advantage_play"
        self.game["players"][self.pids[1]]["hand"] = [{"type": "camp_raid"}]
        r = self.play("control_the_vote", targetId=self.pids[1])
        self.assertFalse(r["success"])
        self.assertIn("control_the_vote", self.hand_types(self.me))

    def test_a_penalty_never_discards_a_given_goodwill(self):
        from rules_engine import penalty_discardable_indices
        hand = [{"type": "vote"}, {"type": "goodwill_gamble", "given": True},
                {"type": "goodwill_gamble"}]
        self.assertEqual(penalty_discardable_indices(hand), [2])

    def test_unknown_advantage_types_leave_the_card_in_hand(self):
        self.open_council(leader=self.me)
        self.game["currentVote"]["phase"] = "advantage_play"
        self.game["players"][self.me]["hand"].append({"type": "immunity_idol"})
        r = self.gs.play_tribal_advantage(self.gid, self.me, "immunity_idol", None)
        self.assertFalse(r["success"])
        self.assertIn("immunity_idol", self.hand_types(self.me))


class TestCampRaidOutlivesACouncil(CouncilTestBase):

    def test_the_marker_survives_the_council(self):
        self.game["players"][self.pids[2]]["campRaidedBy"] = self.pids[0]
        self.gs.rules_engine._reset_post_tribal_flags(self.game)
        self.assertEqual(self.game["players"][self.pids[2]]["campRaidedBy"], self.pids[0])


class TestTheTribalScheduleIsShuffled(unittest.TestCase):

    def test_singles_and_doubles_come_in_varying_order(self):
        engine = SurvivorRulesEngine()
        orders = Counter()
        for _ in range(200):
            deck = engine.assemble_deck([{"type": "camp_raid"}] * 40, 5)
            orders[tuple(c["type"] for c in deck if c["type"].startswith("tribal_council"))] += 1
        self.assertGreater(len(orders), 1, orders)


class TestTheLadderForcesWhatItCan(unittest.TestCase):

    def test_the_only_non_immune_player_is_forced_not_offered(self):
        engine = SurvivorRulesEngine()
        game = {"players": {pid: {"isEliminated": False, "characterCards": 2}
                            for pid in ("x", "y", "z")}}
        # Double Elimination, every vote negated: X and Y played idols
        result = engine.resolve_tribal_eliminations(
            game, {}, protected_players={"x", "y"}, idol_players={"x", "y"},
            elimination_type="double")
        self.assertIn("z", result["eliminated"])
        self.assertNotIn("z", result["tiedPlayers"])
        self.assertEqual(sorted(result["tiedPlayers"]), ["x", "y"])


class TestTheDrawPileStaysFaceDown(CouncilTestBase):

    def test_state_carries_a_count_not_the_order(self):
        state = self.gs.get_game_state(self.gid)
        self.assertEqual(state["deckCount"], len(self.game["deck"]))
        self.assertEqual(len(state["deck"]), len(self.game["deck"]))
        self.assertTrue(all(c == {"type": "hidden"} for c in state["deck"]))
        # ...and the live pile is untouched
        self.assertTrue(any(c.get("type") != "hidden" for c in self.game["deck"]))


class TestHallOfFameNames(unittest.TestCase):

    def test_markup_cannot_be_a_name(self):
        from survivor_server import _validate_winner_fields
        bad = 'x" autofocus onfocus="alert(1)'
        self.assertIsNotNone(_validate_winner_fields({"winner_name": bad, "date": "2026-10-15"})[2])
        for good in ("Tyler", "Mary-Kate O'Neil", "José"):
            name, _, err = _validate_winner_fields({"winner_name": good, "date": "2026-10-15"})
            self.assertIsNone(err, good)
            self.assertEqual(name, good)


if __name__ == "__main__":
    unittest.main(verbosity=2)
