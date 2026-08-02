#!/usr/bin/env python3
"""
The Sorry For You penalty: the raider chooses what they give up.

  "Play ANY time someone tries to take cards from you. Instead, they get
   nothing from you and must discard 1 card (regardless of how many cards you
   owe them)... If you play a Sorry For You after a card that would allow more
   than 1 player to take cards from you, each of those players gets nothing,
   and must EACH discard 1 card instead."

A discard is chosen by the player making it. The engine used to take the last
takeable card in the raider's hand, silently — which made the Guide's own
Inheritance advice impossible to follow: "It can be useful to have the
Inheritance for a player that isn't in the game. You can discard it if someone
plays a Sorry For You against you!" You cannot feed a dead card to a penalty
that picks for you.

The tests that matter most are the ones proving the table cannot freeze: this
is a blocking window, and an unresolvable blocking window is how the web app
once wedged a game forever.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import survivor_server
from rules_engine import request_take
from survivor_server import GameState


def hand_types(game, pid):
    return [c.get("type") for c in game["players"][pid]["hand"]]


class PenaltyDiscardTest(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        self.gs = GameState()
        self.gid = self.gs.create_game()
        self.ids = [self.gs.add_player(self.gid, n, c) for n, c in
                    [("Ana", "#FF6B6B"), ("Ben", "#4ECDC4"),
                     ("Cam", "#45B7D1"), ("Dee", "#F9844A")]]
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]
        self.thief = self.game["turnOrder"][0]
        self.victim = next(p for p in self.game["turnOrder"] if p != self.thief)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── helpers ───────────────────────────────────────────────────────────

    def _raid_blocked(self, thief_hand):
        """Thief raids, victim answers with Sorry For You."""
        self.game["players"][self.thief]["hand"] = list(thief_hand)
        self.game["players"][self.victim]["hand"] = [
            {"type": "sorry_for_you"}, {"type": "camp_raid"}]
        self.gs.rules_engine.sync_vote_counters(self.game)

        steal = self.gs.steal_card(self.gid, thiefId=self.thief, targetId=self.victim)
        self.assertTrue(steal["success"], steal.get("message"))
        self.assertTrue(self.game.get("pending_theft"))

        hand = self.game["players"][self.victim]["hand"]
        idx = next(i for i, c in enumerate(hand) if c["type"] == "sorry_for_you")
        return self.gs.handle_reactive_card_play(self.gid, self.victim, idx, {})

    @property
    def window(self):
        return self.game.get("pending_discards")

    # ── the choice ────────────────────────────────────────────────────────

    def test_a_raider_with_a_choice_is_asked(self):
        result = self._raid_blocked([{"type": "camp_raid"},
                                     {"type": "inheritance"},
                                     {"type": "vote"}])
        self.assertTrue(result["success"])
        self.assertEqual(result["awaitingDiscards"], [self.thief])
        self.assertEqual(self.window["awaiting"], [self.thief])
        # Nothing has left their hand yet.
        self.assertEqual(len(hand_types(self.game, self.thief)), 3)

    def test_the_raider_gives_up_the_card_they_picked(self):
        """The Guide's own Inheritance advice, finally executable."""
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        # Feed it the dead Inheritance, not the useful Camp Raid.
        idx = hand_types(self.game, self.thief).index("inheritance")
        result = self.gs.choose_penalty_discard(self.gid, playerId=self.thief, cardIdx=idx)

        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["windowClosed"])
        self.assertIsNone(self.window)
        self.assertEqual(sorted(hand_types(self.game, self.thief)), ["camp_raid", "vote"])
        self.assertIn("inheritance", [c["type"] for c in self.game["discard"]])

    def test_one_discardable_card_is_not_a_decision(self):
        """No prompt when there is only one legal answer."""
        result = self._raid_blocked([{"type": "camp_raid"}, {"type": "vote"}])
        self.assertTrue(result["success"])
        self.assertFalse(result.get("awaitingDiscards"))
        self.assertIsNone(self.window)
        self.assertEqual(hand_types(self.game, self.thief), ["vote"])

    def test_a_vote_only_hand_pays_nothing(self):
        result = self._raid_blocked([{"type": "vote"}])
        self.assertTrue(result["success"])
        self.assertIsNone(self.window)
        self.assertEqual(hand_types(self.game, self.thief), ["vote"])

    def test_the_vote_card_can_never_be_the_penalty(self):
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        vote_idx = hand_types(self.game, self.thief).index("vote")
        refused = self.gs.choose_penalty_discard(self.gid, playerId=self.thief, cardIdx=vote_idx)
        self.assertFalse(refused["success"])
        self.assertIn("vote", hand_types(self.game, self.thief))

    def test_an_out_of_range_pick_is_refused_not_clamped(self):
        """Clamping would discard a card the player never chose."""
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        for bad in (-1, 99, "two", 1.5, None):
            refused = self.gs.choose_penalty_discard(self.gid, playerId=self.thief, cardIdx=bad)
            self.assertFalse(refused["success"], f"cardIdx={bad!r} must be refused")
        self.assertEqual(len(hand_types(self.game, self.thief)), 3)

    def test_only_the_raider_may_pay(self):
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        refused = self.gs.choose_penalty_discard(self.gid, playerId=self.victim, cardIdx=0)
        self.assertFalse(refused["success"])
        self.assertIsNotNone(self.window)

    def test_a_raider_cannot_pay_twice(self):
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        self.gs.choose_penalty_discard(self.gid, playerId=self.thief, cardIdx=0)
        again = self.gs.choose_penalty_discard(self.gid, playerId=self.thief, cardIdx=0)
        self.assertFalse(again["success"])

    # ── the table is frozen while it is owed ──────────────────────────────

    def test_the_table_is_frozen_until_the_penalty_is_paid(self):
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        drew = self.gs.draw_card(self.gid, playerId=self.thief)
        self.assertFalse(drew["success"])
        played = self.gs.play_card(self.gid, playerId=self.thief, cardIdx=0)
        self.assertFalse(played["success"])

    def test_the_refusal_does_not_describe_anybodys_hand(self):
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        message = self.gs.draw_card(self.gid, playerId=self.thief)["message"]
        for leak in ("Camp Raid", "camp_raid", "Inheritance", "inheritance"):
            self.assertNotIn(leak, message)

    # ── it can never wedge ────────────────────────────────────────────────

    def test_a_raider_who_never_answers_forfeits_on_the_clock(self):
        """The wedge this window would otherwise be.

        There is no ticker for a human-only table, so the sweep runs on the
        read path: any state fetch, from any player, resolves an expired
        window. Somebody is always looking.
        """
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        self.window["deadline"] = time.time() - 1     # they walked away

        state = self.gs.get_game_state(self.gid)      # anyone's phone polling
        self.assertIsNone(self.game.get("pending_discards"))
        self.assertNotIn("pending_discards", state)
        # Forfeit falls back to exactly the old automatic behaviour.
        self.assertEqual(len(hand_types(self.game, self.thief)), 2)
        self.assertIn("vote", hand_types(self.game, self.thief))
        # ...and the table moves again.
        self.assertIsNone(self.gs._challenge_block_reason(self.game))

    def test_the_sweep_leaves_a_live_window_alone(self):
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        self.gs.get_game_state(self.gid)
        self.assertIsNotNone(self.window, "an unexpired window must survive a poll")

    def test_the_raid_is_cancelled_even_if_nobody_ever_pays(self):
        """The block must not depend on the penalty being answered."""
        self._raid_blocked([{"type": "camp_raid"},
                            {"type": "inheritance"},
                            {"type": "vote"}])
        # Victim keeps everything; the thief took nothing.
        self.assertNotIn("pending_theft", self.game)
        self.assertTrue(self.game["players"][self.thief].get("hasStolen"))
        self.assertEqual(hand_types(self.game, self.victim), ["camp_raid"])

    # ── the multi-raider fan-out ──────────────────────────────────────────

    def test_every_raider_owes_their_own_choice(self):
        """"...each of those players ... must EACH discard 1 card instead." """
        ana, ben, cam = self.ids[0], self.ids[1], self.ids[2]
        for pid in (ana, ben):
            self.game["players"][pid]["hand"] = [
                {"type": "camp_raid"}, {"type": "inheritance"}, {"type": "vote"}]
        self.game["players"][cam]["hand"] = [
            {"type": "sorry_for_you"}, {"type": "knowledge_is_power"}]
        self.gs.rules_engine.sync_vote_counters(self.game)

        # Let's Form An Alliance: Ana and Ben both raid Cam.
        pending, _ = request_take(
            self.game, [ana, ben], cam, "lets_form_an_alliance",
            {"kind": "random_each",
             "victimId": cam,
             "takes": [{"thiefId": ana, "count": 1}, {"thiefId": ben, "count": 1}]})
        self.assertTrue(pending, "Cam holds Sorry For You, so the gate must open")

        hand = self.game["players"][cam]["hand"]
        idx = next(i for i, c in enumerate(hand) if c["type"] == "sorry_for_you")
        result = self.gs.handle_reactive_card_play(self.gid, cam, idx, {})
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(sorted(result["awaitingDiscards"]), sorted([ana, ben]))

        # Ana pays; Ben still owes.
        self.gs.choose_penalty_discard(
            self.gid, playerId=ana, cardIdx=hand_types(self.game, ana).index("inheritance"))
        self.assertEqual(self.window["awaiting"], [ben])
        self.assertEqual(len(hand_types(self.game, ben)), 3, "Ben's hand is untouched")

        # Ben pays something different — each chose for themselves.
        self.gs.choose_penalty_discard(
            self.gid, playerId=ben, cardIdx=hand_types(self.game, ben).index("camp_raid"))
        self.assertIsNone(self.window)
        self.assertEqual(sorted(hand_types(self.game, ana)), ["camp_raid", "vote"])
        self.assertEqual(sorted(hand_types(self.game, ben)), ["inheritance", "vote"])
        # Cam kept everything.
        self.assertEqual(hand_types(self.game, cam), ["knowledge_is_power"])

    def test_a_mixed_fan_out_resolves_partly_by_choice_partly_on_the_clock(self):
        ana, ben, cam = self.ids[0], self.ids[1], self.ids[2]
        for pid in (ana, ben):
            self.game["players"][pid]["hand"] = [
                {"type": "camp_raid"}, {"type": "inheritance"}, {"type": "vote"}]
        self.game["players"][cam]["hand"] = [
            {"type": "sorry_for_you"}, {"type": "knowledge_is_power"}]
        self.gs.rules_engine.sync_vote_counters(self.game)
        request_take(
            self.game, [ana, ben], cam, "lets_form_an_alliance",
            {"kind": "random_each", "victimId": cam,
             "takes": [{"thiefId": ana, "count": 1}, {"thiefId": ben, "count": 1}]})
        hand = self.game["players"][cam]["hand"]
        idx = next(i for i, c in enumerate(hand) if c["type"] == "sorry_for_you")
        self.gs.handle_reactive_card_play(self.gid, cam, idx, {})

        self.gs.choose_penalty_discard(
            self.gid, playerId=ana, cardIdx=hand_types(self.game, ana).index("inheritance"))
        self.window["deadline"] = time.time() - 1
        self.gs.get_game_state(self.gid)

        self.assertIsNone(self.game.get("pending_discards"))
        self.assertEqual(sorted(hand_types(self.game, ana)), ["camp_raid", "vote"])
        self.assertEqual(len(hand_types(self.game, ben)), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
