#!/usr/bin/env python3
"""
Turn notifications over Web Push.

Keys and subscriptions are runtime files beside the server (like games.json)
— never inside game state, which every client receives. Sends fire on turn
start and tribal start, and must never break a turn when the push service is
down or the dependency is missing.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SURVIVOR_BOT_DELAY"] = "0"

import push_notify
from survivor_server import GameState


FAKE_SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x", "auth": "y"}}


class PushTestBase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        self.sent = []
        self._orig_webpush = push_notify._webpush
        self._orig_thread = push_notify._send_async
        push_notify._webpush = lambda sub, payload, keys: self.sent.append(
            (sub, json.loads(payload)))
        push_notify._send_async = lambda fn: fn()   # synchronous for tests

    def tearDown(self):
        push_notify._webpush = self._orig_webpush
        push_notify._send_async = self._orig_thread
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)


class TestKeysAndSubscriptions(PushTestBase):
    def test_keys_generate_once_and_persist(self):
        if not push_notify.AVAILABLE:
            self.skipTest("pywebpush not installed")
        first = push_notify.get_keys()
        self.assertTrue(first["public"] and first["private"])
        self.assertTrue(os.path.exists(push_notify.KEYS_FILE))
        second = push_notify.get_keys()
        self.assertEqual(first, second)

    def test_subscribe_roundtrip_stays_out_of_game_state(self):
        gs = GameState()
        gid = gs.create_game()
        pid = gs.add_player(gid, "Tyler", "red")
        push_notify.subscribe(gid, pid, FAKE_SUB)

        stored = json.load(open(push_notify.SUBS_FILE))
        self.assertIn(f"{gid}:{pid}", stored)
        # The capability URL must never ride the state every phone receives
        state_json = json.dumps(gs.get_game_state(gid))
        self.assertNotIn("push.example", state_json)

        push_notify.unsubscribe(gid, pid)
        stored = json.load(open(push_notify.SUBS_FILE))
        self.assertNotIn(f"{gid}:{pid}", stored)

    def test_notify_without_subscription_is_a_quiet_noop(self):
        push_notify.notify_player("nope", "nobody", "t", "b")
        self.assertEqual(self.sent, [])


class TestSendTriggers(PushTestBase):
    def _game(self):
        gs = GameState()
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")
        for _ in range(2):
            gs.add_bot(gid)
        gs.start_full_game(gid)
        return gs, gid, human

    def test_turn_start_notifies_the_subscribed_human(self):
        if not push_notify.AVAILABLE:
            self.skipTest("pywebpush not installed")
        gs, gid, human = self._game()
        push_notify.subscribe(gid, human, FAKE_SUB)
        game = gs.games[gid]

        # Put the turn on the player before the human, then advance into them
        order = game["turnOrder"]
        game["currentTurnIndex"] = (order.index(human) - 1) % len(order)
        current = order[game["currentTurnIndex"]]
        game["players"][current]["hasStolen"] = True
        game["players"][current]["hasDrawn"] = True
        self.sent.clear()
        gs.advance_turn(gid)

        self.assertEqual(len(self.sent), 1, self.sent)
        self.assertIn("turn", self.sent[0][1]["body"].lower())

    def test_tribal_start_notifies_every_subscribed_human(self):
        if not push_notify.AVAILABLE:
            self.skipTest("pywebpush not installed")
        gs, gid, human = self._game()
        push_notify.subscribe(gid, human, FAKE_SUB)
        game = gs.games[gid]
        self.sent.clear()

        game["deck"].insert(0, {"type": "tribal_council_single"})
        drawer = game["turnOrder"][game["currentTurnIndex"]]
        game["players"][drawer]["hasStolen"] = True
        gs.draw_card(gid, drawer)

        tribal_pings = [p for _, p in self.sent if "tribal" in p["title"].lower()]
        self.assertEqual(len(tribal_pings), 1, self.sent)

    def test_a_dead_endpoint_unsubscribes_itself(self):
        if not push_notify.AVAILABLE:
            self.skipTest("pywebpush not installed")
        gs = GameState()
        gid = gs.create_game()
        pid = gs.add_player(gid, "Tyler", "red")
        push_notify.subscribe(gid, pid, FAKE_SUB)

        class Dead(push_notify.WebPushException):
            def __init__(self):
                super().__init__("gone")
                # set after super() — the real WebPushException assigns
                # self.response in its own __init__
                self.response = type("R", (), {"status_code": 410})()

        def gone(sub, payload, keys):
            raise Dead()
        push_notify._webpush = gone

        push_notify.notify_player(gid, pid, "t", "b")
        stored = json.load(open(push_notify.SUBS_FILE))
        self.assertNotIn(f"{gid}:{pid}", stored)

    def test_send_failure_never_breaks_the_turn(self):
        gs, gid, human = self._game()
        push_notify.subscribe(gid, human, FAKE_SUB)

        def boom(sub, payload, keys):
            raise RuntimeError("push service down")
        push_notify._webpush = boom

        game = gs.games[gid]
        order = game["turnOrder"]
        game["currentTurnIndex"] = (order.index(human) - 1) % len(order)
        current = order[game["currentTurnIndex"]]
        game["players"][current]["hasStolen"] = True
        game["players"][current]["hasDrawn"] = True
        result = gs.advance_turn(gid)
        self.assertTrue(result is None or result.get("success", True) is not False)


if __name__ == '__main__':
    print("🔔 Testing turn notifications (Web Push)")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print(f"\n✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    success = not result.failures and not result.errors
    print(f"\n🎉 Push notification tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
