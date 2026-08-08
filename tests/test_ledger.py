#!/usr/bin/env python3
"""
The island's private ledger (Task D1).

Covers ``ledger.py`` itself (healing, idempotence, the write helpers) and
the real write sites this plan wires it into: a steal (via
``rules_engine._record_steal_alert``), a tribal council's vote reveal, a
Challenge win, a card play (including an Immunity Idol), an elimination —
and the two guarantees that make the whole thing safe to keep in
``games.json``: it never reaches ``get_game_state``, and it heals silently
on a game that has never seen one.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ledger
from survivor_server import GameState
from rules_engine import SurvivorRulesEngine, execute_take_spec, new_card


def _fresh_state():
    tmp = tempfile.mkdtemp()
    original = os.getcwd()
    os.chdir(tmp)
    return GameState(), original, tmp


# ─────────────────────────── ensure_ledger / healing ───────────────────────────

class EnsureLedgerHealsTest(unittest.TestCase):
    def test_heals_a_ledger_less_game_silently(self):
        game = {"players": {"a": {"name": "A"}, "b": {"name": "B"}}}
        healed = ledger.ensure_ledger(game)

        self.assertIn("_ledger", game)
        self.assertIs(game["_ledger"], healed)
        self.assertEqual(healed["councilIndex"], 0)
        self.assertIn("a", healed["players"])
        self.assertIn("b", healed["players"])

        entry = healed["players"]["a"]
        self.assertEqual(entry["challengeWins"], 0)
        self.assertEqual(entry["cardsPlayed"], 0)
        self.assertEqual(entry["idolsPlayed"], 0)
        self.assertEqual(entry["stolenFrom"], {})
        self.assertEqual(entry["stolenBy"], {})
        self.assertEqual(entry["cardsPlayedOn"], {})
        self.assertEqual(entry["votesAgainst"], [])
        self.assertEqual(entry["votesCast"], [])
        self.assertIsNone(entry["eliminatedAtCouncil"])

    def test_idempotent_second_call_does_not_duplicate_or_reset(self):
        game = {"players": {"a": {}, "b": {}}}
        ledger.record_steal(game, "a", "b", 3)
        ledger.ensure_ledger(game)
        ledger.ensure_ledger(game)
        self.assertEqual(ledger.get_player_ledger(game, "b")["stolenFrom"]["a"], 3)
        self.assertEqual(len(game["_ledger"]["players"]), 2)

    def test_heals_a_partial_or_corrupt_ledger_without_raising(self):
        game = {
            "players": {"a": {}, "b": {}},
            "_ledger": {"councilIndex": "not a number",
                        "players": {"a": "garbage", "b": {"challengeWins": "nope"}}},
        }
        healed = ledger.ensure_ledger(game)
        self.assertEqual(healed["councilIndex"], 0)
        self.assertEqual(healed["players"]["a"]["challengeWins"], 0)
        self.assertEqual(healed["players"]["b"]["challengeWins"], 0)

    def test_missing_or_non_dict_game_never_raises(self):
        self.assertEqual(ledger.ensure_ledger(None), {"councilIndex": 0, "players": {}})
        self.assertEqual(ledger.ensure_ledger("not a game"), {"councilIndex": 0, "players": {}})
        self.assertEqual(ledger.get_player_ledger({}, "ghost")["challengeWins"], 0)

    def test_new_players_get_healed_entries_on_a_later_call(self):
        game = {"players": {"a": {}}}
        ledger.ensure_ledger(game)
        game["players"]["b"] = {"name": "B"}
        ledger.ensure_ledger(game)
        self.assertIn("b", game["_ledger"]["players"])


# ────────────────────────────── record_steal ──────────────────────────────

class RecordStealTest(unittest.TestCase):
    def test_records_both_sides_of_a_steal(self):
        game = {"players": {"a": {}, "b": {}}}
        ledger.record_steal(game, "a", "b", 2)
        self.assertEqual(ledger.get_player_ledger(game, "a")["stolenBy"]["b"], 2)
        self.assertEqual(ledger.get_player_ledger(game, "b")["stolenFrom"]["a"], 2)

    def test_accumulates_across_multiple_steals(self):
        game = {"players": {"a": {}, "b": {}}}
        ledger.record_steal(game, "a", "b", 1)
        ledger.record_steal(game, "a", "b", 3)
        self.assertEqual(ledger.get_player_ledger(game, "b")["stolenFrom"]["a"], 4)

    def test_zero_or_negative_count_records_nothing(self):
        game = {"players": {"a": {}, "b": {}}}
        ledger.record_steal(game, "a", "b", 0)
        ledger.record_steal(game, "a", "b", -1)
        self.assertEqual(ledger.get_player_ledger(game, "b")["stolenFrom"], {})
        self.assertEqual(ledger.get_player_ledger(game, "a")["stolenBy"], {})


class StealAlertWritesLedgerTest(unittest.TestCase):
    """The real write site: rules_engine._record_steal_alert."""

    def test_random_each_take_spec_updates_the_ledger(self):
        game = {
            "players": {
                "a": {"name": "A", "hand": []},
                "b": {"name": "B", "hand": [new_card("extra_vote"), new_card("camp_raid")]},
            },
            "deck": [], "discard": [],
        }
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        self.assertEqual(ledger.get_player_ledger(game, "a")["stolenBy"]["b"], 2)
        self.assertEqual(ledger.get_player_ledger(game, "b")["stolenFrom"]["a"], 2)

    def test_engine_execute_theft_updates_the_ledger(self):
        engine = SurvivorRulesEngine()
        game = {
            "players": {
                "a": {"name": "A", "hand": []},
                "b": {"name": "B", "hand": [new_card("extra_vote"), new_card("vote")]},
            },
            "deck": [], "discard": [],
        }
        engine.execute_theft(game, "a", "b")
        self.assertGreaterEqual(ledger.get_player_ledger(game, "b")["stolenFrom"].get("a", 0), 1)

    def test_a_bot_victim_still_updates_the_ledger(self):
        """The private alert skips a bot victim (nobody's phone to tell) —
        the ledger must NOT skip them; bots need this to remember grudges."""
        game = {
            "players": {
                "a": {"name": "A", "hand": []},
                "b": {"name": "B", "hand": [new_card("extra_vote")], "isBot": True},
            },
            "deck": [], "discard": [],
        }
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 1}]})
        self.assertEqual(ledger.get_player_ledger(game, "b")["stolenFrom"]["a"], 1)


# ─────────────────────────── never reaches a client ────────────────────────────

class LedgerNeverLeaksToClientsTest(unittest.TestCase):
    def setUp(self):
        self.gs, self.original_cwd, self.tmp = _fresh_state()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_game_state_never_contains_the_ledger(self):
        gid = self.gs.create_game()
        a = self.gs.add_player(gid, "Ana", "red")
        b = self.gs.add_player(gid, "Ben", "blue")
        self.gs.add_player(gid, "Cam", "green")
        self.gs.start_full_game(gid)
        game = self.gs.games[gid]

        ledger.record_steal(game, a, b, 2)
        ledger.record_challenge_win(game, a)
        ledger.record_elimination(game, b, 0)
        self.assertIn("_ledger", game)  # sanity: it really is there server-side

        state = self.gs.get_game_state(gid)
        self.assertNotIn("_ledger", state)
        self.assertFalse([k for k in state if k.startswith("_")],
                         "no top-level underscore key belongs on the wire")


# ────────────────────────────── reveal_votes ──────────────────────────────

class VoteRevealWritesLedgerTest(unittest.TestCase):
    def setUp(self):
        self.gs, self.original_cwd, self.tmp = _fresh_state()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _council(self, gid, leader):
        game = self.gs.games[gid]
        self.gs._trigger_tribal_council(game, "single", drawer_id=leader)
        self.gs.start_voting(gid, "elimination")
        for pid in game["turnOrder"]:
            game["players"][pid]["hand"] = [{"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(game)
        return game

    def test_reveal_records_ballots_and_bumps_the_council_counter(self):
        gid = self.gs.create_game()
        a = self.gs.add_player(gid, "Ana", "red")
        b = self.gs.add_player(gid, "Ben", "blue")
        c = self.gs.add_player(gid, "Cam", "green")
        self.gs.start_full_game(gid)
        game = self._council(gid, a)

        self.gs.cast_vote(gid, voterId=a, votesData=[{"targetId": c, "votes": 1}])
        self.gs.cast_vote(gid, voterId=b, votesData=[{"targetId": c, "votes": 1}])
        self.gs.cast_vote(gid, voterId=c, votesData=[{"targetId": a, "votes": 1}])

        # First tap only seals the box and opens the idol window — it must
        # not have filed anything in the ledger yet.
        first = self.gs.reveal_votes(gid)
        self.assertTrue(first.get("idolWindowOpened"))
        self.assertEqual(game.get("_ledger", {}).get("councilIndex", 0), 0)

        second = self.gs.reveal_votes(gid)
        self.assertTrue(second["success"], second.get("message"))
        self.assertEqual(game["_ledger"]["councilIndex"], 1)

        c_entry = ledger.get_player_ledger(game, c)
        self.assertEqual(len(c_entry["votesAgainst"]), 1)
        self.assertEqual(c_entry["votesAgainst"][0]["council"], 0)
        self.assertEqual(c_entry["votesAgainst"][0]["voters"], {a: 1, b: 1})

        a_entry = ledger.get_player_ledger(game, a)
        self.assertEqual(a_entry["votesCast"], [{"council": 0, "votes": {c: 1}}])
        a_against = ledger.get_player_ledger(game, a)["votesAgainst"]
        self.assertEqual(a_against[0]["voters"], {c: 1})

class RecordCouncilVotesDirectTest(unittest.TestCase):
    """Direct coverage of the counter's bump-once-per-call contract, without
    the overhead of staging a second real Tribal Council end to end."""

    def test_each_call_gets_the_next_index(self):
        game = {"players": {"a": {}, "b": {}}}
        idx1 = ledger.record_council_votes(game, {"a": {"b": 1}})
        idx2 = ledger.record_council_votes(game, {"b": {"a": 1}})
        self.assertEqual(idx1, 0)
        self.assertEqual(idx2, 1)
        self.assertEqual(game["_ledger"]["councilIndex"], 2)

        a_entry = ledger.get_player_ledger(game, "a")
        self.assertEqual([v["council"] for v in a_entry["votesCast"]], [0])
        b_entry = ledger.get_player_ledger(game, "b")
        self.assertEqual([v["council"] for v in b_entry["votesCast"]], [1])

    def test_next_and_last_council_index_helpers(self):
        game = {"players": {}}
        self.assertEqual(ledger.next_council_index(game), 0)
        self.assertEqual(ledger.last_council_index(game), 0)  # never negative
        ledger.record_council_votes(game, {})
        self.assertEqual(ledger.next_council_index(game), 1)
        self.assertEqual(ledger.last_council_index(game), 0)


# ──────────────────────────── challenge wins ────────────────────────────

class ChallengeWinWritesLedgerTest(unittest.TestCase):
    def test_award_challenge_win_increments_challenge_wins(self):
        gs, original_cwd, tmp = _fresh_state()
        try:
            gid = gs.create_game()
            a = gs.add_player(gid, "Ana", "red")
            gs.add_player(gid, "Ben", "blue")
            gs.start_full_game(gid)
            game = gs.games[gid]

            gs._award_challenge_win(game, a)
            self.assertEqual(ledger.get_player_ledger(game, a)["challengeWins"], 1)
            gs._award_challenge_win(game, a)
            self.assertEqual(ledger.get_player_ledger(game, a)["challengeWins"], 2)
        finally:
            os.chdir(original_cwd)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_winner_no_longer_in_the_game_records_nothing(self):
        gs, original_cwd, tmp = _fresh_state()
        try:
            gid = gs.create_game()
            gs.add_player(gid, "Ana", "red")
            gs.start_full_game(gid)
            game = gs.games[gid]
            result = gs._award_challenge_win(game, "ghost-id")
            self.assertIn("no longer", result)
            self.assertEqual(ledger.get_player_ledger(game, "ghost-id")["challengeWins"], 0)
        finally:
            os.chdir(original_cwd)
            shutil.rmtree(tmp, ignore_errors=True)


# ──────────────────────────────── card plays ────────────────────────────────

class CardPlayWritesLedgerTest(unittest.TestCase):
    def setUp(self):
        self.gs, self.original_cwd, self.tmp = _fresh_state()
        self.gid = self.gs.create_game()
        self.a = self.gs.add_player(self.gid, "Ana", "red")
        self.b = self.gs.add_player(self.gid, "Ben", "blue")
        self.gs.add_player(self.gid, "Cam", "green")
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(self.a)
        for p in self.game["players"].values():
            p["hasStolen"] = True  # past the mandatory steal

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_targeted_card_play_increments_cards_played_and_played_on(self):
        self.game["players"][self.a]["hand"] = [{"type": "camp_raid"}]
        result = self.gs.play_card(self.gid, self.a, 0, {"targetId": self.b})
        self.assertTrue(result["success"], result.get("message"))

        a_entry = ledger.get_player_ledger(self.game, self.a)
        self.assertEqual(a_entry["cardsPlayed"], 1)
        self.assertEqual(a_entry["idolsPlayed"], 0)

        b_entry = ledger.get_player_ledger(self.game, self.b)
        self.assertEqual(b_entry["cardsPlayedOn"][self.a], 1)

    def test_a_failed_play_records_nothing(self):
        self.game["players"][self.a]["hand"] = [{"type": "camp_raid"}]
        # An invalid target refuses the play — the card even goes back to hand.
        result = self.gs.play_card(self.gid, self.a, 0, {"targetId": "not-a-real-player"})
        self.assertFalse(result["success"])
        self.assertEqual(ledger.get_player_ledger(self.game, self.a)["cardsPlayed"], 0)

    def test_play_immunity_increments_idols_played(self):
        self.gs._trigger_tribal_council(self.game, "single", drawer_id=self.a)
        self.game["players"][self.a]["hand"] = [{"type": "immunity_idol"}]

        result = self.gs.play_immunity(self.gid, playerId=self.a, targetId=self.a)
        self.assertTrue(result["success"], result.get("message"))

        entry = ledger.get_player_ledger(self.game, self.a)
        self.assertEqual(entry["idolsPlayed"], 1)
        self.assertEqual(entry["cardsPlayed"], 1)
        # A self-target names nobody in cardsPlayedOn.
        self.assertEqual(entry["cardsPlayedOn"], {})

    def test_play_immunity_on_someone_else_marks_cards_played_on(self):
        self.gs._trigger_tribal_council(self.game, "single", drawer_id=self.a)
        self.game["players"][self.a]["hand"] = [{"type": "immunity_idol"}]

        result = self.gs.play_immunity(self.gid, playerId=self.a, targetId=self.b)
        self.assertTrue(result["success"], result.get("message"))

        b_entry = ledger.get_player_ledger(self.game, self.b)
        self.assertEqual(b_entry["cardsPlayedOn"][self.a], 1)


# ──────────────────────────────── elimination ────────────────────────────────

class EliminationWritesLedgerTest(unittest.TestCase):
    def test_eliminated_at_council_is_explicit_not_derived(self):
        """The rock-draw / tie-break cascade can eliminate a player who took
        ZERO votes that council — eliminatedAtCouncil must still be set,
        which is exactly why it cannot be read back out of votesAgainst."""
        game = {"players": {"a": {}, "b": {}}}
        # "a" never received a single vote — no votesAgainst entries at all —
        # yet the elimination path still stamps the council explicitly.
        ledger.record_elimination(game, "a", 2)
        entry = ledger.get_player_ledger(game, "a")
        self.assertEqual(entry["eliminatedAtCouncil"], 2)
        self.assertEqual(entry["votesAgainst"], [])

    def test_complete_tribal_stamps_the_council_that_just_revealed(self):
        gs, original_cwd, tmp = _fresh_state()
        try:
            gid = gs.create_game()
            a = gs.add_player(gid, "Ana", "red")
            b = gs.add_player(gid, "Ben", "blue")
            c = gs.add_player(gid, "Cam", "green")
            gs.add_player(gid, "Deb", "yellow")
            gs.start_full_game(gid)
            game = gs.games[gid]

            gs._trigger_tribal_council(game, "single", drawer_id=a)
            gs.start_voting(gid, "elimination")
            for pid in game["turnOrder"]:
                game["players"][pid]["hand"] = [{"type": "vote"}]
            gs.rules_engine.sync_vote_counters(game)
            # One Survivor Character Card left — this vote-out is a TRUE
            # elimination, not a first flip that leaves them still in.
            game["players"][c]["characterCards"] = 1

            deb = game["turnOrder"][3]
            for pid in (a, b, deb):
                res = gs.cast_vote(gid, voterId=pid, votesData=[{"targetId": c, "votes": 1}])
                self.assertTrue(res["success"], res.get("message"))
            res = gs.cast_vote(gid, voterId=c, votesData=[{"targetId": a, "votes": 1}])
            self.assertTrue(res["success"], res.get("message"))

            gs.reveal_votes(gid)  # opens the idol window
            gs.reveal_votes(gid)  # tallies
            self.assertIn(c, game["currentVote"]["eliminated"])

            result = gs.complete_tribal(gid)
            self.assertTrue(result["success"], result.get("message"))
            self.assertTrue(game["players"][c]["isEliminated"])

            entry = ledger.get_player_ledger(game, c)
            self.assertEqual(entry["eliminatedAtCouncil"], 0)
        finally:
            os.chdir(original_cwd)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
