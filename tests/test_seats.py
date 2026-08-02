#!/usr/bin/env python3
"""
Seats — the six colours a castaway can be.

"Each player chooses a colour and the 2 Survivor Character Cards of that
colour" (docs/survivor_rules.md:20), and the Survival Guide's Inheritance entry
reads "6 CARDS, 1 OF EACH COLOR". So colour stops being decoration the moment
Inheritance binds to it: it becomes a fixed, enumerable identity, and two
players can never hold the same one.

The tests that matter most here are the migration ones. There are 117 saved
games with free-form colours, and the obvious move — snapping each to the
nearest seat — was measured against the real store and puts two players on one
seat in 13 of them. Deriving by exact match cannot do that, because colours
were already unique within a game.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seats
from survivor_server import GameState


class SeatRosterTest(unittest.TestCase):
    def test_there_are_exactly_six_seats(self):
        """Six colours in the box, six Inheritance cards, six seats."""
        self.assertEqual(len(seats.SEATS), 6)
        self.assertEqual(len(set(seats.SEAT_KEYS)), 6)
        self.assertEqual(len(set(seats.SEAT_HEX.values())), 6,
                         "no two seats may share a colour")

    def test_a_stored_seat_is_believed(self):
        self.assertEqual(seats.seat_of({"seat": "blue", "color": "#FF6B6B"}), "blue")

    def test_a_legacy_player_is_seated_by_their_colour(self):
        """Games saved before seats existed carry only a hex."""
        self.assertEqual(seats.seat_of({"color": "#45B7D1"}), "blue")
        self.assertEqual(seats.seat_of({"color": "#ff6b6b"}), "red", "case-insensitive")

    def test_an_unplaceable_colour_stays_honestly_seatless(self):
        """Never guess. A wrong seat is worse than no seat."""
        self.assertIsNone(seats.seat_of({"color": "#96CEB4"}))
        self.assertIsNone(seats.seat_of({"color": "chartreuse"}))
        self.assertIsNone(seats.seat_of({}))
        self.assertIsNone(seats.seat_of(None))

    # ── the join door ─────────────────────────────────────────────────────

    def test_a_seat_key_or_its_hex_are_both_understood(self):
        self.assertEqual(seats.resolve_request("blue"), ("blue", True))
        self.assertEqual(seats.resolve_request("#45B7D1"), ("blue", True))
        self.assertEqual(seats.resolve_request("#45b7d1"), ("blue", True))

    def test_a_colour_we_used_to_offer_still_means_something(self):
        """An installed phone keeps sending last version's palette."""
        self.assertEqual(seats.resolve_request("#96CEB4"), ("green", True))
        self.assertEqual(seats.resolve_request("#FFEAA7"), ("yellow", True))

    def test_nonsense_is_not_a_request(self):
        for value in ("chartreuse", "", "   ", None, 42):
            key, explicit = seats.resolve_request(value)
            self.assertIsNone(key)
            self.assertFalse(explicit)

    def test_asking_for_a_taken_seat_is_told_so(self):
        """Two people both reaching for Red should be told, not re-seated."""
        game = {"players": {"p1": {"name": "Ana", "seat": "red", "color": "#FF6B6B"}}}
        key, error = seats.assign(game, "red")
        self.assertIsNone(key)
        self.assertIn("already taken by Ana", error)

    def test_an_unplaceable_request_quietly_takes_a_free_seat(self):
        """Losing your place at the fire over a colour is out of proportion."""
        game = {"players": {}}
        key, error = seats.assign(game, "chartreuse")
        self.assertIsNone(error)
        self.assertIn(key, seats.SEAT_KEYS)

    def test_seats_are_handed_out_in_table_order(self):
        game = {"players": {}}
        handed = []
        for i in range(6):
            key, error = seats.assign(game, None)
            self.assertIsNone(error)
            game["players"][f"p{i}"] = {"seat": key, "color": seats.seat_hex(key)}
            handed.append(key)
        self.assertEqual(handed, list(seats.SEAT_KEYS))
        self.assertEqual(seats.free_seats(game), [])

    def test_a_seventh_player_finds_no_seat(self):
        game = {"players": {f"p{i}": {"seat": k, "color": seats.seat_hex(k)}
                            for i, k in enumerate(seats.SEAT_KEYS)}}
        key, error = seats.assign(game, None)
        self.assertIsNone(key)
        self.assertIn("taken", error)


class SeatedGameTest(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        self.gs = GameState()
        self.gid = self.gs.create_game()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_player_gets_a_distinct_seat(self):
        for name in ("Ana", "Ben", "Cam", "Dee", "Eve", "Fin"):
            self.gs.add_player(self.gid, name)
        game = self.gs.games[self.gid]
        keys = [seats.seat_of(p) for p in game["players"].values()]
        self.assertTrue(all(keys), "nobody joins without a seat")
        self.assertEqual(len(set(keys)), 6)

    def test_a_joined_player_stores_the_seats_canonical_colour(self):
        """`color` stays on the wire forever — every render path reads it, and
        an installed build decodes it as a required field."""
        pid = self.gs.add_player(self.gid, "Ana", "blue")
        player = self.gs.games[self.gid]["players"][pid]
        self.assertEqual(player["seat"], "blue")
        self.assertEqual(player["color"], seats.seat_hex("blue"))

    def test_an_old_palette_colour_still_gets_you_in(self):
        pid = self.gs.add_player(self.gid, "Ana", "#96CEB4")   # the clients' sage
        player = self.gs.games[self.gid]["players"][pid]
        self.assertEqual(player["seat"], "green")

    def test_bots_take_seats_like_anyone_else(self):
        self.gs.add_player(self.gid, "Ana")
        for _ in range(3):
            self.assertTrue(self.gs.add_bot(self.gid)["success"])
        game = self.gs.games[self.gid]
        keys = [seats.seat_of(p) for p in game["players"].values()]
        self.assertTrue(all(keys), "a seatless bot could never be inherited from")
        self.assertEqual(len(set(keys)), 4)

    def test_the_state_carries_the_seat_and_the_roster(self):
        """Clients stop hard-coding a palette — which is how the server's six
        and the clients' eight drifted apart in the first place."""
        pid = self.gs.add_player(self.gid, "Ana", "red")
        state = self.gs.get_game_state(self.gid)
        self.assertEqual(state["players"][pid]["seat"], "red")
        self.assertEqual(state["players"][pid]["seatLabel"], "Red")
        self.assertEqual(len(state["seatRoster"]), 6)
        self.assertEqual({s["key"] for s in state["seatRoster"]}, set(seats.SEAT_KEYS))

    def test_a_legacy_game_is_seated_without_being_rewritten(self):
        """No migration: derive on read, leave the saved bytes alone."""
        pid = self.gs.add_player(self.gid, "Ana", "red")
        game = self.gs.games[self.gid]
        del game["players"][pid]["seat"]              # as an old save would be

        state = self.gs.get_game_state(self.gid)
        self.assertEqual(state["players"][pid]["seat"], "red")
        self.assertNotIn("seat", game["players"][pid],
                         "the stored record must not be rewritten behind us")

    def test_an_unplaceable_legacy_colour_reports_null_rather_than_a_guess(self):
        pid = self.gs.add_player(self.gid, "Ana", "red")
        game = self.gs.games[self.gid]
        del game["players"][pid]["seat"]
        game["players"][pid]["color"] = "#96CEB4"     # sage: never a seat hex

        state = self.gs.get_game_state(self.gid)
        self.assertIsNone(state["players"][pid]["seat"])
        self.assertIsNone(state["players"][pid]["seatLabel"])
        self.assertEqual(state["players"][pid]["color"], "#96CEB4",
                         "their colour is left exactly as they chose it")


if __name__ == '__main__':
    unittest.main(verbosity=2)
