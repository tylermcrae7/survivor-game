#!/usr/bin/env python3
"""
Playing a tribal advantage from the council screen.

Two faults, found from one screenshot of a live game: "Server Error — Missing
fields: targetId" over the Advantage Play Phase, with I'm The Leader Now and
Steal A Vote sitting in the hand behind it.

  1. The door required a `targetId` key on every advantage. I'm The Leader Now
     has no target, the phone omits a nil rather than sending one, and so that
     card could never be played from a phone at all.

  2. Dropping that requirement on its own would have been worse than the bug.
     The effects report a missing target by returning a bare `{"message": ...}`
     with no `success` key, and `play_tribal_advantage` returns success
     regardless — so a Steal A Vote played at nobody was discarded, did
     nothing, and said it had worked. The card has to be checked while it is
     still in the hand.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import survivor_server
from survivor_server import GameState


def hand_types(game, pid):
    return [c.get("type") for c in game["players"][pid]["hand"]]


class TribalAdvantagePlayTest(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        self.gs = GameState()
        self.gid = self.gs.create_game()
        self.ids = [self.gs.add_player(self.gid, n) for n in ("Ana", "Ben", "Cam", "Dee")]
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]
        for pid in self.ids:
            self.game["players"][pid]["hand"] = [{"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(self.game)
        self.gs._trigger_tribal_council(self.game, "single")
        self.game["currentVote"]["phase"] = "advantage_play"

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def give(self, pid, card_type):
        self.game["players"][pid]["hand"].append({"type": card_type})

    # ── the card with no target ───────────────────────────────────────────

    def test_an_untargeted_advantage_plays_without_a_target(self):
        actor = self.ids[1]
        self.give(actor, "im_the_leader_now")

        result = self.gs.play_tribal_advantage(
            self.gid, playerId=actor, advantageType="im_the_leader_now")

        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.game["currentVote"]["councilLeaderId"], actor)
        self.assertNotIn("im_the_leader_now", hand_types(self.game, actor))

    def test_the_http_door_no_longer_demands_a_target_key(self):
        """The exact request the phone sends for a targetless advantage."""
        actor = self.ids[1]
        self.give(actor, "im_the_leader_now")
        survivor_server.game_state = self.gs
        client = survivor_server.app.test_client()

        res = client.post('/api/tribal/advantage',
                          json={"gameId": self.gid, "playerId": actor,
                                "advantageType": "im_the_leader_now"})

        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertTrue(res.get_json()["success"], res.get_json().get("message"))

    # ── the card that needs one ───────────────────────────────────────────

    def test_a_targeted_advantage_is_refused_rather_than_eaten(self):
        actor = self.ids[1]
        self.give(actor, "steal_vote")

        result = self.gs.play_tribal_advantage(
            self.gid, playerId=actor, advantageType="steal_vote")

        self.assertFalse(result["success"])
        self.assertIn("steal_vote", hand_types(self.game, actor),
                      "a refused advantage stays in the hand")
        self.assertNotIn("steal_vote",
                         [c.get("type") for c in (self.game.get("discard") or [])])
        self.assertFalse(self.game["currentVote"].get("advantageCardsPlayed"),
                         "and nothing is announced")

    def test_a_targeted_advantage_still_works_when_aimed(self):
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "steal_vote")

        result = self.gs.play_tribal_advantage(
            self.gid, playerId=actor, advantageType="steal_vote", targetId=victim)

        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(self.game["players"][victim].get("voteBanned"))
        self.assertEqual(self.game["players"][actor].get("extraVotes"), 1)
        self.assertNotIn("steal_vote", hand_types(self.game, actor))

    def test_an_eliminated_target_is_refused_and_the_card_survives(self):
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "block_vote")
        self.game["players"][victim]["isEliminated"] = True

        result = self.gs.play_tribal_advantage(
            self.gid, playerId=actor, advantageType="block_vote", targetId=victim)

        self.assertFalse(result["success"])
        self.assertIn("block_vote", hand_types(self.game, actor))
        self.assertFalse(self.game["players"][victim].get("voteBanned"))

    def test_a_target_who_is_not_at_this_table_is_refused(self):
        actor = self.ids[1]
        self.give(actor, "control_the_vote")

        result = self.gs.play_tribal_advantage(
            self.gid, playerId=actor, advantageType="control_the_vote",
            targetId="not-a-player")

        self.assertFalse(result["success"])
        self.assertIn("control_the_vote", hand_types(self.game, actor))

    def test_every_targeted_advantage_refuses_an_empty_target(self):
        """Whatever the catalogue marks, the door must honour."""
        defs = self.gs.rules_engine.get_all_card_definitions()
        targeted = [t for t, c in defs.items()
                    if c.get("category") == "tribal_advantage"
                    and c.get("requires_target")
                    and "tribal_discussion" in (c.get("playable_phases") or [])]
        self.assertTrue(targeted, "the catalogue should mark some as targeted")

        for card_type in targeted:
            with self.subTest(card=card_type):
                actor = self.ids[1]
                self.game["players"][actor]["hand"] = [{"type": "vote"},
                                                       {"type": card_type}]
                result = self.gs.play_tribal_advantage(
                    self.gid, playerId=actor, advantageType=card_type)
                self.assertFalse(result["success"], f"{card_type} fired at nobody")
                self.assertIn(card_type, hand_types(self.game, actor))


if __name__ == '__main__':
    unittest.main(verbosity=2)
