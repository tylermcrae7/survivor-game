#!/usr/bin/env python3
"""The archive the garbage collector leaves behind.

A finished game used to be swept within the hour — no grace, no record —
which made "review last night's game against the rules" structurally
impossible: the first post-game audit (2026-08-08, game b11498a9) lost its
entire endgame to a restart's sweep. Now a finished game lingers a day in
the live store, and everything the collector removes is written to
archive/<gid>.json first.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState


class GameArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.gs = GameState()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _finished_game(self, age_seconds):
        gid = self.gs.create_game()
        game = self.gs.games[gid]
        game["phase"] = "finished"
        game["winner"] = "somebody"
        game["lastActivity"] = time.time() - age_seconds
        return gid

    def test_a_fresh_win_survives_the_sweep(self):
        """A day to savour (and audit) the win — no more vanishing within
        the hour."""
        gid = self._finished_game(age_seconds=3600)  # one hour old
        removed = self.gs.garbage_collect()
        self.assertEqual(removed, 0)
        self.assertIn(gid, self.gs.games)
        self.assertFalse(os.path.exists(os.path.join("archive", f"{gid}.json")))

    def test_an_old_win_is_archived_not_erased(self):
        gid = self._finished_game(age_seconds=25 * 3600)  # past the day
        winner = self.gs.games[gid]["winner"]
        removed = self.gs.garbage_collect()
        self.assertEqual(removed, 1)
        self.assertNotIn(gid, self.gs.games)

        path = os.path.join("archive", f"{gid}.json")
        self.assertTrue(os.path.exists(path), "the removed game must be archived")
        with open(path) as f:
            archived = json.load(f)
        self.assertEqual(archived["winner"], winner)
        self.assertEqual(archived["phase"], "finished")

    def test_a_stale_lobby_is_archived_too(self):
        gid = self.gs.create_game()
        self.gs.games[gid]["lastActivity"] = time.time() - 25 * 3600
        removed = self.gs.garbage_collect()
        self.assertEqual(removed, 1)
        self.assertTrue(os.path.exists(os.path.join("archive", f"{gid}.json")))

    def test_a_live_final_tribal_is_never_swept(self):
        """The old sweep matched phase 'final' with NO age check. The live
        phase string is 'final_tribal' so the entry was dead — but had any
        code path ever set 'final', the hourly collector would have deleted
        a live ceremony. Pin both spellings as safe."""
        for phase in ("final", "final_tribal"):
            gid = self.gs.create_game()
            game = self.gs.games[gid]
            game["phase"] = phase
            game["lastActivity"] = time.time() - 2 * 3600
            removed = self.gs.garbage_collect()
            self.assertEqual(removed, 0, f"a {phase} game must never be swept")
            self.assertIn(gid, self.gs.games)
            del self.gs.games[gid]

    def test_an_archive_failure_never_kills_the_collector(self):
        gid = self._finished_game(age_seconds=25 * 3600)
        # A FILE named 'archive' makes makedirs fail — the collector must
        # log, skip the archive, and still collect.
        with open("archive", "w") as f:
            f.write("in the way")
        removed = self.gs.garbage_collect()
        self.assertEqual(removed, 1)
        self.assertNotIn(gid, self.gs.games)


if __name__ == '__main__':
    unittest.main(verbosity=2)
