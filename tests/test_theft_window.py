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


class TheWindowClosesOnItsOwnTest(unittest.TestCase):
    def setUp(self):
        self.gs = _fresh_gamestate()

    def test_an_expired_window_executes_the_take(self):
        self.gs.games["g1"] = _game_with_window(deadline=time.time() - 1)
        self.gs.get_game_state("g1")
        game = self.gs.games["g1"]
        self.assertIsNone(game.get("pending_theft"))
        self.assertEqual(len(game["players"]["thief"]["hand"]), 2)
        self.assertEqual(len(game["players"]["victim"]["hand"]), 1)

    def test_a_live_window_is_left_alone(self):
        self.gs.games["g1"] = _game_with_window(deadline=time.time() + 60)
        self.gs.get_game_state("g1")
        self.assertTrue(self.gs.games["g1"].get("pending_theft"))

    def test_a_window_from_before_deadlines_is_stamped_not_executed(self):
        """A deploy lands mid-game: heal on read, don't fire instantly."""
        self.gs.games["g1"] = _game_with_window()   # no deadline key
        self.gs.get_game_state("g1")
        window = self.gs.games["g1"]["pending_theft"]
        self.assertIsNotNone(window, "healed, not swept")
        self.assertGreater(window.get("deadline", 0), time.time())

    def test_new_windows_are_born_with_a_deadline(self):
        from rules_engine import request_take
        game = _game_with_window()
        game.pop("pending_theft")
        pending, _ = request_take(
            game, ["thief"], "victim", "Do Or Die",
            {"kind": "random_each", "takes": [{"thiefId": "thief", "count": 2}]})
        self.assertTrue(pending)
        self.assertGreater(game["pending_theft"].get("deadline", 0), time.time())


class TheCouncilDoesNotEatAWonStealTest(unittest.TestCase):
    def test_post_tribal_reset_resumes_the_held_take(self):
        gs = _fresh_gamestate()
        gs.games["g1"] = _game_with_window(deadline=time.time() + 60)
        game = gs.games["g1"]
        # The reset is rules_engine.SurvivorRulesEngine._reset_post_tribal_flags
        # (found via `grep -n "pending_theft" rules_engine.py` around line
        # 1636) — it is what survivor_server.py's complete_tribal calls.
        gs.rules_engine._reset_post_tribal_flags(game)
        self.assertIsNone(game.get("pending_theft"))
        self.assertEqual(len(game["players"]["thief"]["hand"]), 2,
                        "the held take must execute, not evaporate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
