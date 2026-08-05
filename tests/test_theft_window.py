#!/usr/bin/env python3
"""The Sorry For You window: who may close it, and when it closes itself."""
import os, sys, time, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import survivor_server
from survivor_server import GameState
from rules_engine import new_card


def _fresh_gamestate():
    gs = GameState.__new__(GameState)
    from rules_engine import SurvivorRulesEngine
    gs.rules_engine = SurvivorRulesEngine()
    gs.games = {}
    gs._save = lambda gid: None
    return gs


def _game_with_window(**window_extra):
    game = {
        "players": {
            "thief": {"name": "Thief", "hand": [], "isEliminated": False},
            "victim": {"name": "Victim",
                       "hand": [new_card("sorry_for_you"), new_card("extra_vote"),
                                new_card("camp_raid")],
                       "isEliminated": False},
        },
        "phase": "playing", "turnOrder": ["thief", "victim"],
        "currentTurnIndex": 0, "deck": [], "discard": [],
        "pending_theft": {
            "thiefId": "thief", "thiefIds": ["thief"], "targetId": "victim",
            "source": "Do Or Die", "reactive_window_open": True,
            "_resume": {"victimId": "victim", "kind": "random_each",
                        "takes": [{"thiefId": "thief", "count": 2}]},
            **window_extra,
        },
    }
    return game


class OnlyTheTargetClosesTheWindowTest(unittest.TestCase):
    def setUp(self):
        self.gs = _fresh_gamestate()
        self.gs.games["g1"] = _game_with_window()

    def test_the_thief_cannot_wave_their_own_raid_through(self):
        result = self.gs.complete_pending_theft("g1", playerId="thief")
        self.assertFalse(result["success"])
        self.assertTrue(self.gs.games["g1"].get("pending_theft"),
                        "the window must still be open")
        self.assertEqual(len(self.gs.games["g1"]["players"]["victim"]["hand"]), 3)

    def test_the_target_can(self):
        result = self.gs.complete_pending_theft("g1", playerId="victim")
        self.assertTrue(result["success"])
        self.assertEqual(len(self.gs.games["g1"]["players"]["thief"]["hand"]), 2)

    def test_the_server_itself_still_can(self):
        """No playerId = internal caller (bot driver, expiry sweep)."""
        result = self.gs.complete_pending_theft("g1")
        self.assertTrue(result["success"])


class TheRouteRequiresThePlayerTest(unittest.TestCase):
    """HTTP layer: gameId alone is no longer enough."""
    def setUp(self):
        self.client = survivor_server.app.test_client()

    def test_no_player_id_is_refused(self):
        response = self.client.post('/api/reactive/complete_theft',
                                    json={"gameId": "anything"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("playerId", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
