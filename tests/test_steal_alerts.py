#!/usr/bin/env python3
"""Structured steal alerts: every card movement leaves a record to announce."""
import os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules_engine import execute_take_spec, request_take, new_card, SurvivorRulesEngine


def _game(hands):
    """hands: {pid: [card_type, ...]} -> minimal game dict."""
    return {
        "players": {
            pid: {"name": pid.capitalize(), "hand": [new_card(t) for t in types],
                  "isEliminated": False}
            for pid, types in hands.items()
        },
        "deck": [], "discard": [],
    }


class TakeSpecRecordsAlertsTest(unittest.TestCase):
    def test_random_each_records_thief_victim_and_count(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid", "the_spy_shack"]})
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        alerts = game.get("_pending_alerts") or []
        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["event"], "steal")
        self.assertEqual(alert["data"]["thiefId"], "a")
        self.assertEqual(alert["data"]["victimId"], "b")
        self.assertEqual(alert["data"]["count"], 2)
        self.assertIn("stole 2 cards", alert["data"]["message"])

    def test_alert_message_never_names_the_card(self):
        game = _game({"a": [], "b": ["immunity_idol"]})
        execute_take_spec(game, {"victimId": "b", "kind": "index",
                                 "thiefId": "a", "index": 0, "force": True})
        message = game["_pending_alerts"][0]["data"]["message"]
        self.assertNotIn("Idol", message)
        self.assertNotIn("idol", message)

    def test_a_take_that_moves_nothing_records_nothing(self):
        game = _game({"a": [], "b": []})
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        self.assertFalse(game.get("_pending_alerts"))

    def test_each_thief_in_a_pair_gets_their_own_alert(self):
        game = _game({"a": [], "b": [], "c": ["extra_vote", "camp_raid"]})
        execute_take_spec(game, {"victimId": "c", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 1},
                                           {"thiefId": "b", "count": 1}]})
        alerts = game["_pending_alerts"]
        self.assertEqual({a["data"]["thiefId"] for a in alerts}, {"a", "b"})
        self.assertTrue(all(a["data"]["count"] == 1 for a in alerts))
        self.assertIn("stole a card", alerts[0]["data"]["message"])


class TurnStealRecordsAlertsTest(unittest.TestCase):
    def test_execute_theft_records_and_names_the_thief(self):
        engine = SurvivorRulesEngine()
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        engine.execute_theft(game, "a", "b")
        alert = game["_pending_alerts"][0]
        self.assertEqual(alert["event"], "steal")
        self.assertTrue(alert["data"]["message"].startswith("A stole"),
                        alert["data"]["message"])


class DeadCodeGoneTest(unittest.TestCase):
    def test_steal_random_helper_is_gone(self):
        import interactions
        self.assertFalse(hasattr(interactions.InteractionEngine, "_steal_random"))


class AlertsNeverLeakToClientsTest(unittest.TestCase):
    """_pending_alerts is server plumbing — it must not ride the state payload."""
    def setUp(self):
        import survivor_server
        self.gs = survivor_server.GameState.__new__(survivor_server.GameState)
        # Minimal instance: reuse the real engine + games dict without file IO
        from rules_engine import SurvivorRulesEngine
        self.gs.rules_engine = SurvivorRulesEngine()
        self.gs.games = {"g1": _game({"a": [], "b": ["extra_vote"]})}
        self.gs.games["g1"].update({"phase": "playing", "turnOrder": ["a", "b"],
                                    "currentTurnIndex": 0})
        self.gs._save = lambda gid: None

    def test_state_payload_carries_no_underscore_keys(self):
        self.gs.games["g1"]["_pending_alerts"] = [{"event": "steal", "data": {}}]
        state = self.gs.get_game_state("g1")
        self.assertFalse([k for k in state if k.startswith("_")],
                         "top-level underscore keys are server-side only")


class SorryForYouRecordsABlockedRaidTest(unittest.TestCase):
    def test_blocking_the_raid_leaves_a_raid_blocked_alert(self):
        from rules_engine import SurvivorRulesEngine
        engine = SurvivorRulesEngine()
        # Thief holds two discardable cards — a real choice, so the table
        # is left waiting on them.
        game = _game({"thief": ["extra_vote", "camp_raid"], "victim": ["sorry_for_you"]})
        game["pending_theft"] = {"thiefId": "thief", "thiefIds": ["thief"],
                                 "targetId": "victim", "source": "steal",
                                 "reactive_window_open": True}
        card = engine.resolve_card({"type": "sorry_for_you"})
        engine.execute_reactive_interrupt(game, "victim", "thief", card)
        alerts = [a for a in game.get("_pending_alerts", [])
                  if a["event"] == "raid_blocked"]
        self.assertEqual(len(alerts), 1)
        data = alerts[0]["data"]
        self.assertIn("Sorry For You", data["message"])
        self.assertIn("Victim", data["message"])
        self.assertIn("Thief must choose a card to give up", data["message"])

    def test_an_automatic_discard_gets_no_suffix(self):
        """One discardable card is not a decision — nobody is left waiting."""
        from rules_engine import SurvivorRulesEngine
        engine = SurvivorRulesEngine()
        game = _game({"thief": ["extra_vote"], "victim": ["sorry_for_you"]})
        game["pending_theft"] = {"thiefId": "thief", "thiefIds": ["thief"],
                                 "targetId": "victim", "source": "steal",
                                 "reactive_window_open": True}
        card = engine.resolve_card({"type": "sorry_for_you"})
        engine.execute_reactive_interrupt(game, "victim", "thief", card)
        alerts = [a for a in game.get("_pending_alerts", [])
                  if a["event"] == "raid_blocked"]
        self.assertEqual(len(alerts), 1)
        data = alerts[0]["data"]
        self.assertIn("Sorry For You", data["message"])
        self.assertNotIn("must choose a card to give up", data["message"])


class ReactiveRoutesWriteHistoryTest(unittest.TestCase):
    """The two hand-rolled routes must log outcomes like every handled action."""

    def setUp(self):
        import survivor_server
        from tests.test_theft_window import _fresh_gamestate, _game_with_window
        self.server = survivor_server
        self.gs = _fresh_gamestate()
        self.gs.games["g1"] = _game_with_window()
        self.server.game_state = self.gs
        self.client = self.server.app.test_client()

    def test_declining_lands_the_outcome_in_the_event_log(self):
        response = self.client.post('/api/reactive/complete_theft',
                                     json={"gameId": "g1", "playerId": "victim"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

        log = self.gs.games["g1"].get("eventLog") or []
        self.assertTrue(log, "the decline must leave a Story So Far entry")
        self.assertIn("Thief", log[-1]["msg"])
        self.assertIn("Victim", log[-1]["msg"])
        self.assertIn("took 2 cards", log[-1]["msg"])

    def test_blocking_lands_sorry_for_you_in_the_event_log(self):
        # victim's hand[0] is sorry_for_you (see _game_with_window)
        response = self.client.post('/api/reactive/play_card',
                                     json={"gameId": "g1", "playerId": "victim",
                                           "cardIdx": 0})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

        log = self.gs.games["g1"].get("eventLog") or []
        self.assertTrue(log, "a blocked raid must leave a Story So Far entry")
        self.assertIn("Sorry for you! The raid fails", log[-1]["msg"])

        # The raid_blocked alert must be flushed here, not left for a bot
        # broadcast to pick up later.
        self.assertFalse(self.gs.games["g1"].get("_pending_alerts"))


class SecretTribalAdvantagesTest(unittest.TestCase):
    """Steal A Vote and Block A Vote work in the dark, as end-game secrets should.

    Task S2 contract: a secret card effect (a) never lands in the eventLog,
    (b) never emits the `card_played` narrator event, (c) still returns its
    full message to the ACTOR's own HTTP response, (d) still mutates state
    normally — the target's own phone sees WHAT happened without being told
    WHO. Control The Vote is deliberately excluded: the Guide's own card is
    public by design.
    """

    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        import survivor_server
        self.server = survivor_server
        self.gs = survivor_server.GameState()
        survivor_server.game_state = self.gs
        self.client = survivor_server.app.test_client()

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

    def post(self, path, payload):
        return self.client.post(path, json=payload)

    # ── the effects mark themselves secret ──────────────────────────────

    def test_effects_mark_themselves_secret(self):
        actor, victim = self.ids[1], self.ids[2]
        engine = self.gs.rules_engine
        self.assertTrue(
            engine._effect_steal_vote(self.game, actor, {}, {"targetId": victim}).get("secret"))
        self.assertTrue(
            engine._effect_block_vote(self.game, actor, {}, {"targetId": victim}).get("secret"))

    # ── played through the tribal advantage door ────────────────────────

    def test_steal_vote_leaves_no_trace_in_the_room(self):
        from tests.test_narrator_events import captured_events, of_type
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "steal_vote")
        before_log = len(self.game.get("eventLog") or [])

        with captured_events() as events:
            res = self.post('/api/tribal/advantage',
                             {"gameId": self.gid, "playerId": actor,
                              "advantageType": "steal_vote", "targetId": victim})

        body = res.get_json()
        self.assertTrue(body["success"], body.get("message"))
        # (c) the actor's own HTTP response still carries the full message
        self.assertIn(self.game["players"][victim]["name"], body["message"])
        # (d) state mutates normally — the target really loses their vote
        self.assertTrue(self.game["players"][victim]["voteBanned"])
        self.assertEqual(self.game["players"][actor].get("extraVotes"), 1)
        # (a) never lands in the eventLog
        self.assertEqual(len(self.game.get("eventLog") or []), before_log)
        # (b) never emits card_played — nor anything else naming the actor
        self.assertEqual(of_type(events, 'card_played'), [])
        # Not recorded in the room-facing "Advantages Played" history either
        self.assertFalse(self.game["currentVote"].get("advantageCardsPlayed"))

    def test_block_vote_leaves_no_trace_in_the_room(self):
        from tests.test_narrator_events import captured_events, of_type
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "block_vote")
        before_log = len(self.game.get("eventLog") or [])

        with captured_events() as events:
            res = self.post('/api/tribal/advantage',
                             {"gameId": self.gid, "playerId": actor,
                              "advantageType": "block_vote", "targetId": victim})

        body = res.get_json()
        self.assertTrue(body["success"], body.get("message"))
        self.assertIn(self.game["players"][victim]["name"], body["message"])
        self.assertTrue(self.game["players"][victim]["voteBanned"])
        self.assertEqual(len(self.game.get("eventLog") or []), before_log)
        self.assertEqual(of_type(events, 'card_played'), [])
        self.assertFalse(self.game["currentVote"].get("advantageCardsPlayed"))

    # ── the same secrecy holds through the ordinary turn route ──────────

    def test_steal_vote_via_the_generic_play_card_route_stays_dark_too(self):
        """Tribal advantage cards are also playable through the ordinary turn
        route while a council is in session — the same secrecy must hold."""
        from tests.test_narrator_events import captured_events, of_type
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "steal_vote")
        idx = len(self.game["players"][actor]["hand"]) - 1
        before_log = len(self.game.get("eventLog") or [])

        with captured_events() as events:
            res = self.post('/api/turn/play_card',
                             {"gameId": self.gid, "playerId": actor, "cardIdx": idx,
                              "params": {"targetId": victim}})

        body = res.get_json()
        self.assertTrue(body["success"], body.get("message"))
        self.assertTrue(self.game["players"][victim]["voteBanned"])
        self.assertEqual(len(self.game.get("eventLog") or []), before_log)
        self.assertEqual(of_type(events, 'card_played'), [])

    # ── Control The Vote is unaffected — it stays loud by design ────────

    def test_control_the_vote_stays_loud(self):
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "control_the_vote")
        before_log = len(self.game.get("eventLog") or [])

        res = self.post('/api/tribal/advantage',
                         {"gameId": self.gid, "playerId": actor,
                          "advantageType": "control_the_vote", "targetId": victim})

        body = res.get_json()
        self.assertTrue(body["success"], body.get("message"))
        self.assertGreater(len(self.game.get("eventLog") or []), before_log)
        self.assertTrue(self.game["currentVote"].get("advantageCardsPlayed"))

    # ── the Voting Box already skips a banned voter — pinned here ───────

    def test_a_banned_voter_never_appears_in_the_waiting_on_refusal(self):
        actor, victim = self.ids[1], self.ids[2]
        self.give(actor, "steal_vote")
        self.post('/api/tribal/advantage',
                  {"gameId": self.gid, "playerId": actor,
                   "advantageType": "steal_vote", "targetId": victim})
        self.assertTrue(self.game["players"][victim]["voteBanned"])

        missing = self.gs._ballot_box_missing(self.game)
        self.assertNotIn(self.game["players"][victim]["name"], missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)
