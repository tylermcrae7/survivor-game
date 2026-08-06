#!/usr/bin/env python3
"""
The Idol Nullifier's reactive window.

An Idol Nullifier answers an Immunity Idol, and it can only be played once a
target actually holds protection — so it cannot be played early. Before this
window existed, the only thing standing between a holder and their card was how
fast the Council Leader tapped: the tally could land at any moment, and often
did, so the card frequently could not be played at all.

Unlike the Sorry For You gate, this window does NOT hold the idol back. The
protection applies immediately and the nullifier undoes it, because a holder
has to *see* the protection in order to target it.

The tests that matter most here are the ones that prove a council cannot get
stuck: a window nobody can close freezes the endgame for everyone.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState


class NullifierWindowTest(unittest.TestCase):
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

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── helpers ───────────────────────────────────────────────────────────

    def _to_immunity(self, *, idol_holder=None, nullifier_holders=()):
        """Run a council to the open idol window, with hands staged."""
        for pid in self.ids:
            hand = [{"type": "vote"}]
            if pid == idol_holder:
                hand.append({"type": "immunity_idol"})
            if pid in nullifier_holders:
                hand.append({"type": "idol_nullifier"})
            self.game["players"][pid]["hand"] = hand
        self.gs.rules_engine.sync_vote_counters(self.game)

        self.gs._trigger_tribal_council(self.game, "single")
        self.gs.start_voting(self.gid, "elimination")
        for voter in self.ids:
            target = self.ids[3] if voter != self.ids[3] else self.ids[0]
            votes = max(1, self.game["players"][voter].get("mandatoryVotes", 1))
            self.gs.cast_vote(self.gid, voter, [{"targetId": target, "votes": votes}])
        sealed = self.gs.reveal_votes(self.gid)
        self.assertTrue(sealed.get("idolWindowOpened"), sealed.get("message"))

    @property
    def window(self):
        return self.game.get("pending_nullifier")

    # ── the window opens only when it can be used ─────────────────────────

    def test_no_nullifier_at_the_table_means_no_pause(self):
        """A dead pause on every idol would be its own tell."""
        self._to_immunity(idol_holder=self.ids[0])
        result = self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        self.assertTrue(result["success"])
        self.assertFalse(result.get("nullifierWindowOpen"))
        self.assertIsNone(self.window)
        # ...and the tally is immediately available.
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])

    def test_an_idol_opens_a_window_for_the_holder(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        result = self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        self.assertTrue(result.get("nullifierWindowOpen"))
        self.assertEqual(self.window["_responderIds"], [self.ids[1]])
        self.assertEqual(self.window["targetId"], self.ids[0])

    # ── the window actually holds the ceremony ────────────────────────────

    def test_the_leader_cannot_tally_through_an_open_window(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        refused = self.gs.reveal_votes(self.gid)
        self.assertFalse(refused["success"])
        self.assertFalse(self.game["currentVote"].get("voteResults"))

        advanced = self.gs.advance_tribal_phase(self.gid, "reveal")
        self.assertFalse(advanced.get("success") if isinstance(advanced, dict) else advanced)

    def test_the_refusal_does_not_name_who_is_holding_it_up(self):
        """Naming the holder would leak the very card the window protects."""
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        message = self.gs.reveal_votes(self.gid)["message"]
        self.assertNotIn("Ben", message)
        self.assertNotIn(self.ids[1], message)

    # ── both answers close it ─────────────────────────────────────────────

    def test_playing_the_nullifier_closes_the_window(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        blocked = self.gs.block_immunity(self.gid, playerId=self.ids[1], targetId=self.ids[0])
        self.assertTrue(blocked["success"], blocked.get("message"))
        self.assertIsNone(self.window)
        self.assertTrue(self.game["players"][self.ids[0]].get("idolNullified"))
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])

    def test_declining_closes_the_window_and_the_idol_stands(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        declined = self.gs.decline_nullifier(self.gid, playerId=self.ids[1])
        self.assertTrue(declined["success"])
        self.assertTrue(declined["windowClosed"])
        self.assertIsNone(self.window)
        self.assertFalse(self.game["players"][self.ids[0]].get("idolNullified"))
        # The idol still does its job.
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])
        self.assertTrue(self.game["players"][self.ids[0]].get("immunityIdolProtection"))

    def test_every_holder_must_answer_before_the_window_closes(self):
        self._to_immunity(idol_holder=self.ids[0],
                          nullifier_holders=(self.ids[1], self.ids[2]))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        self.assertEqual(len(self.window["_responderIds"]), 2)

        first = self.gs.decline_nullifier(self.gid, playerId=self.ids[1])
        self.assertFalse(first["windowClosed"], "one of two answers is not enough")
        self.assertIsNotNone(self.window)

        second = self.gs.decline_nullifier(self.gid, playerId=self.ids[2])
        self.assertTrue(second["windowClosed"])
        self.assertIsNone(self.window)

    def test_the_first_nullifier_wins_and_closes_it_for_the_rest(self):
        self._to_immunity(idol_holder=self.ids[0],
                          nullifier_holders=(self.ids[1], self.ids[2]))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        self.gs.block_immunity(self.gid, playerId=self.ids[1], targetId=self.ids[0])
        self.assertIsNone(self.window)
        # The second holder's card is refused cleanly, not silently swallowed.
        late = self.gs.block_immunity(self.gid, playerId=self.ids[2], targetId=self.ids[0])
        self.assertFalse(late["success"])

    # ── nobody outside the window may touch it ────────────────────────────

    def test_a_player_without_a_nullifier_cannot_close_the_window(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        refused = self.gs.decline_nullifier(self.gid, playerId=self.ids[3])
        self.assertFalse(refused["success"])
        self.assertIsNotNone(self.window)

    def test_a_second_idol_cannot_be_played_while_one_is_being_answered(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.game["players"][self.ids[2]]["hand"].append({"type": "immunity_idol"})
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        second = self.gs.play_immunity(self.gid, playerId=self.ids[2], targetId=self.ids[2])
        self.assertFalse(second["success"])

    # ── nobody can freeze the ceremony ────────────────────────────────────

    def test_the_leader_can_call_time_on_a_silent_holder(self):
        """The wedge this window would otherwise create.

        There is no server-side ticker for a human-only game, so a holder who
        puts their phone down would freeze the endgame for everyone. The
        Council Leader can always close it — the digital "going once, going
        twice".
        """
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        self.assertIsNotNone(self.window)

        leader = self.game["currentVote"]["councilLeaderId"]
        # The leader here must not be the holder, or this proves nothing.
        self.assertNotEqual(leader, self.ids[1])

        called = self.gs.decline_nullifier(self.gid, playerId=leader)
        self.assertTrue(called["success"], called.get("message"))
        self.assertTrue(called["windowClosed"])
        self.assertIsNone(self.window)
        # The ceremony can finish.
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])
        # ...and the idol did its job, because nobody answered it.
        self.assertTrue(self.game["players"][self.ids[0]].get("immunityIdolProtection"))

    def test_calling_time_is_the_leaders_privilege_alone(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        leader = self.game["currentVote"]["councilLeaderId"]
        bystander = next(p for p in self.ids if p not in (leader, self.ids[1]))

        refused = self.gs.decline_nullifier(self.gid, playerId=bystander)
        self.assertFalse(refused["success"])
        self.assertIsNotNone(self.window)

    # ── the leak that would undo the whole point ──────────────────────────

    def test_the_window_never_names_its_holders_to_a_client(self):
        """_responderIds lists every nullifier holder at the table."""
        self._to_immunity(idol_holder=self.ids[0],
                          nullifier_holders=(self.ids[1], self.ids[2]))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        state = self.gs.get_game_state(self.gid)
        window = state.get("pending_nullifier") or {}
        self.assertNotIn("_responderIds", window)
        self.assertNotIn("_answered", window)
        # And no stray copy anywhere else in the payload.
        import json
        blob = json.dumps(state)
        self.assertNotIn("_responderIds", blob)
        # The public half survives — clients need to know a window is open.
        self.assertTrue(window.get("reactive_window_open"))

    # ── it must not survive the council ───────────────────────────────────

    def test_a_window_cannot_leak_into_the_next_council(self):
        """The old cleanup popped 'pendingTheft'; the real key is snake_case."""
        self.game["pending_theft"] = {"reactive_window_open": True}
        self.game["pending_nullifier"] = {"reactive_window_open": True}
        self.gs.rules_engine._reset_post_tribal_flags(self.game)
        self.assertNotIn("pending_theft", self.game)
        self.assertNotIn("pending_nullifier", self.game)


class NullifiedIdolReachesTheStatePayloadTest(NullifierWindowTest):
    """Task S4: pin that `idolNullified` reaches the wire.

    The player dict already carries `idolNullified`, and `get_game_state`
    deep-copies `players` whole with no per-player redaction of that key
    (only underscore-prefixed keys on a handful of hidden-info holders are
    stripped). This is a verification test only, per the plan: if it ever
    fails, that is a production bug to report, not quietly fix here.
    """

    def test_a_nullified_players_state_payload_says_so(self):
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[1],))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        blocked = self.gs.block_immunity(self.gid, playerId=self.ids[1], targetId=self.ids[0])
        self.assertTrue(blocked["success"], blocked.get("message"))
        # Confirmed in memory first (mirrors test_playing_the_nullifier_closes_the_window).
        self.assertTrue(self.game["players"][self.ids[0]].get("idolNullified"))

        state = self.gs.get_game_state(self.gid)
        wire_player = state["players"][self.ids[0]]
        self.assertTrue(
            wire_player.get("idolNullified"),
            "idolNullified must reach the wire — a client can never decode a "
            "flag the server never sends. This would be a bug to report.")
        # The (now moot) protection flag rides along too, unredacted —
        # `_effect_idol_nullifier` revokes it the moment it nullifies, so a
        # client can tell "never protected" and "nullified" apart only by
        # also reading idolNullified.
        self.assertFalse(wire_player.get("immunityIdolProtection"))

    def test_an_unnullified_idol_holder_carries_no_stray_flag(self):
        """The flag must not appear at all for a protection that stands."""
        self._to_immunity(idol_holder=self.ids[0])
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        state = self.gs.get_game_state(self.gid)
        wire_player = state["players"][self.ids[0]]
        self.assertFalse(wire_player.get("idolNullified"))
        self.assertTrue(wire_player.get("immunityIdolProtection"))




class NullifierCannotFreezeTheCouncilTest(NullifierWindowTest):
    """The two locks that shut a real council down.

    Reported from a live game: an idol on the table, the phone showing "Your
    idol is on the table — waiting to see if it stands…", and nothing anybody
    could do about it. The player who laid the idol was also the only person
    at the table holding a nullifier, so they were the sole responder to a
    window their own screen never offers them — it tells them to wait.
    """

    def test_the_idol_player_is_not_asked_to_answer_their_own_idol(self):
        """It is not a move. You would simply not play the idol."""
        self._to_immunity(idol_holder=self.ids[0], nullifier_holders=(self.ids[0],))
        result = self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        self.assertTrue(result["success"])
        self.assertFalse(result.get("nullifierWindowOpen"),
                         "the only holder was the idol's own player")
        self.assertIsNone(self.window)
        # ...and the ceremony moves on rather than waiting for nobody.
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])

    def test_holding_both_cards_still_lets_others_answer(self):
        """Excluding yourself must not excuse everybody else."""
        self._to_immunity(idol_holder=self.ids[0],
                          nullifier_holders=(self.ids[0], self.ids[1]))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])

        self.assertEqual(self.window["_responderIds"], [self.ids[1]],
                         "the other holder is still asked")
        self.assertFalse(self.gs.reveal_votes(self.gid)["success"])

    def test_an_idol_played_for_someone_else_still_excludes_only_the_player(self):
        """Protection can be granted; the exclusion follows who played it."""
        self._to_immunity(idol_holder=self.ids[0],
                          nullifier_holders=(self.ids[0], self.ids[2]))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[1])

        self.assertEqual(self.window["_responderIds"], [self.ids[2]])

    def test_a_leader_holding_a_nullifier_can_still_call_time(self):
        """The second lock.

        The Leader's power to end the wait used to be refused whenever the
        Leader happened to hold a nullifier — which handed the one player who
        could end it the one reason they could not.
        """
        leader = self.game["turnOrder"][0]
        others = [p for p in self.ids if p != leader]
        self._to_immunity(idol_holder=others[0],
                          nullifier_holders=(leader, others[1]))
        self.gs.play_immunity(self.gid, playerId=others[0], targetId=others[0])

        actual_leader = self.game["currentVote"]["councilLeaderId"]
        self.assertIn(actual_leader, self.window["_responderIds"],
                      "this test is only meaningful if the Leader holds one")

        called = self.gs.decline_nullifier(self.gid, playerId=actual_leader)
        self.assertTrue(called["success"], called.get("message"))
        self.assertTrue(called["windowClosed"], "the Leader ends the wait")
        self.assertIsNone(self.window)
        self.assertTrue(self.gs.reveal_votes(self.gid)["success"])

    def test_the_leaders_own_decline_still_counts_as_an_answer(self):
        """Calling time IS declining — it must not also nullify anything."""
        self._to_immunity(idol_holder=self.ids[3],
                          nullifier_holders=(self.ids[0], self.ids[1], self.ids[2]))
        self.gs.play_immunity(self.gid, playerId=self.ids[3], targetId=self.ids[3])
        actual_leader = self.game["currentVote"]["councilLeaderId"]

        self.gs.decline_nullifier(self.gid, playerId=actual_leader)

        self.assertIsNone(self.window)
        self.assertFalse(self.game["players"][self.ids[3]].get("idolNullified"),
                         "the idol stands; calling time is not a nullification")
        self.assertTrue(self.game["players"][self.ids[3]].get("immunityIdolProtection"))

    def test_the_last_ordinary_decline_still_closes_it_without_a_leader(self):
        """The normal path must survive the reordering."""
        self._to_immunity(idol_holder=self.ids[0],
                          nullifier_holders=(self.ids[1], self.ids[2]))
        self.gs.play_immunity(self.gid, playerId=self.ids[0], targetId=self.ids[0])
        leader = self.game["currentVote"]["councilLeaderId"]
        responders = list(self.window["_responderIds"])
        non_leaders = [p for p in responders if p != leader]
        if len(non_leaders) < 2:
            self.skipTest("the Leader holds one this deal; covered elsewhere")

        self.assertFalse(self.gs.decline_nullifier(
            self.gid, playerId=non_leaders[0])["windowClosed"])
        self.assertTrue(self.gs.decline_nullifier(
            self.gid, playerId=non_leaders[1])["windowClosed"])


if __name__ == '__main__':
    unittest.main(verbosity=2)
