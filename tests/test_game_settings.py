#!/usr/bin/env python3
"""
Per-game settings: botPace, tribalPace, botStyle.

The device sends its defaults at creation; the Leader can adjust mid-game via
update_game_settings. Bots read the game's settings instead of module-level
constants, and the ceremony windows keep a human floor so a bot Council Leader
can't race past the advantage window when a person is at the table.
"""

import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SURVIVOR_BOT_DELAY"] = "0"   # windows collapse to zero for tests

from survivor_server import GameState, GAME_SETTINGS_DEFAULTS, sanitize_game_settings
import bots
from bots import BotRunner


class SettingsTestBase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.game_id = self.gs.create_game()
        self.leader = self.gs.add_player(self.game_id, "Tyler", "red")
        for _ in range(3):
            self.assertTrue(self.gs.add_bot(self.game_id)["success"])
        self.gs.start_full_game(self.game_id)
        self.game = self.gs.games[self.game_id]

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)


class TestGameSettings(SettingsTestBase):
    def test_create_accepts_and_sanitizes_settings(self):
        gid = self.gs.create_game(settings={"botPace": "fast", "tribalPace": "junk",
                                            "extra": 1})
        self.assertEqual(self.gs.games[gid]["settings"],
                         {"botPace": "fast", "tribalPace": "normal",
                          "botStyle": "normal"})

    def test_create_without_settings_gets_defaults(self):
        self.assertEqual(self.game["settings"], dict(GAME_SETTINGS_DEFAULTS))

    def test_sanitize_never_mutates_its_base(self):
        base = {"botPace": "chill", "tribalPace": "tv", "botStyle": "normal"}
        out = sanitize_game_settings({"botPace": "fast"}, base=base)
        self.assertEqual(base["botPace"], "chill")
        self.assertEqual(out["botPace"], "fast")
        self.assertEqual(out["tribalPace"], "tv")

    def test_update_game_settings_validates_and_merges(self):
        result = self.gs.update_game_settings(
            self.game_id, playerId=self.leader,
            settings={"tribalPace": "relaxed"})
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.game["settings"]["tribalPace"], "relaxed")
        # untouched keys survive the merge
        self.assertEqual(self.game["settings"]["botPace"], "normal")

    def test_update_refuses_junk_values(self):
        result = self.gs.update_game_settings(
            self.game_id, playerId=self.leader,
            settings={"botPace": "ludicrous"})
        self.assertFalse(result["success"])
        self.assertEqual(self.game["settings"]["botPace"], "normal")

    def test_update_refuses_junk_keys(self):
        result = self.gs.update_game_settings(
            self.game_id, playerId=self.leader,
            settings={"maxPlayers": 40})
        self.assertFalse(result["success"])


class TestBotPacing(SettingsTestBase):
    def test_pace_multipliers(self):
        self.game["settings"] = {"botPace": "chill", "tribalPace": "relaxed",
                                 "botStyle": "normal"}
        self.assertAlmostEqual(bots.delay_mult(self.game), 1.8)
        self.assertAlmostEqual(bots.window_mult(self.game), 2.0)

    def test_missing_settings_mean_normal(self):
        self.game.pop("settings", None)
        self.assertAlmostEqual(bots.delay_mult(self.game), 1.0)
        self.assertAlmostEqual(bots.window_mult(self.game), 1.0)
        self.assertAlmostEqual(bots.play_chance(self.game), bots.PLAY_CHANCE)

    def test_style_scales_play_and_steal(self):
        self.game["settings"]["botStyle"] = "cutthroat"
        self.assertAlmostEqual(bots.play_chance(self.game), 0.95)
        self.assertAlmostEqual(bots.steal_chance(self.game), 0.8)
        self.game["settings"]["botStyle"] = "chill"
        self.assertAlmostEqual(bots.play_chance(self.game), bots.PLAY_CHANCE * 0.5)
        self.assertAlmostEqual(bots.steal_chance(self.game), 0.25)

    def test_windows_scale_and_floor_with_humans(self):
        """With a live human, the advantage window keeps a real floor even
        though the test env collapses the base windows to zero — a bot Council
        Leader must never race past the one moment a human can play
        I'm The Leader Now or an idol."""
        base_delay = bots.BASE_DELAY
        base_windows = dict(bots.WINDOWS)
        try:
            bots.BASE_DELAY = 1.6                     # a realistic live pace
            bots.WINDOWS = bots._windows(bots.BASE_DELAY)
            self.game["settings"]["tribalPace"] = "normal"
            w = bots.windows_for(self.game)
            self.assertGreaterEqual(w["advantage"], 12.0)
            self.assertGreaterEqual(w["discussion"], 10.0)

            self.game["settings"]["tribalPace"] = "relaxed"
            w = bots.windows_for(self.game)
            self.assertGreaterEqual(w["advantage"], 24.0)

            # Bot-only games keep their quick ceremonies — no floor
            for p in self.game["players"].values():
                p["isBot"] = True
            w = bots.windows_for(self.game)
            self.assertAlmostEqual(w["advantage"], bots.WINDOWS["advantage"] * 2.0)
        finally:
            bots.BASE_DELAY = base_delay
            bots.WINDOWS = base_windows

    def test_zero_delay_env_stays_zero(self):
        """SURVIVOR_BOT_DELAY=0 (the test env) must keep every window at zero,
        floors included, or the soak suites would crawl."""
        self.game["settings"]["tribalPace"] = "tv"
        w = bots.windows_for(self.game)
        self.assertEqual(w, dict(bots.WINDOWS))


class TestStyleSoak(unittest.TestCase):
    def test_extreme_styles_still_finish(self):
        """Style/pace multipliers must never break termination. Bots only play
        alongside a human (house rule), so this rides test_bots' scripted-human
        full-game runner with settings threaded through."""
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
        from test_bots import _play_full_bot_game

        for settings, seed in (
            ({"botStyle": "cutthroat", "botPace": "fast"}, 11),
            ({"botStyle": "chill", "tribalPace": "tv"}, 12),
        ):
            name, steps = _play_full_bot_game("official", False, seed,
                                              settings=settings)
            self.assertTrue(name, f"{settings} game did not finish")


if __name__ == '__main__':
    print("⚙️  Testing per-game settings (pace, style, windows)")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print(f"\n✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    success = not result.failures and not result.errors
    print(f"\n🎉 Per-game settings tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
