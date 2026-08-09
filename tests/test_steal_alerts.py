#!/usr/bin/env python3
"""Structured steal alerts: every card movement leaves a record to announce."""
import os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules_engine import execute_take_spec, request_take, new_card, SurvivorRulesEngine


def _game(hands, bots=()):
    """hands: {pid: [card_type, ...]} -> minimal game dict. `bots` marks
    which pids are isBot — Task A2's private "robbed" alert skips them."""
    return {
        "players": {
            pid: {"name": pid.capitalize(), "hand": [new_card(t) for t in types],
                  "isEliminated": False, "isBot": pid in bots}
            for pid, types in hands.items()
        },
        "deck": [], "discard": [],
    }


def _public(alerts):
    return [a for a in alerts if a["event"] == "steal"]


def _private(alerts):
    return [a for a in alerts if a["event"] == "robbed"]


class TakeSpecRecordsAlertsTest(unittest.TestCase):
    def test_random_each_records_thief_victim_and_count(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid", "the_spy_shack"]})
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        alerts = game.get("_pending_alerts") or []
        public, private = _public(alerts), _private(alerts)
        # Task A2: a successful steal against a real player now leaves TWO
        # records — the table-wide one and the victim's own.
        self.assertEqual(len(public), 1)
        self.assertEqual(len(private), 1)

        alert = public[0]
        self.assertEqual(alert["data"]["thiefId"], "a")
        self.assertEqual(alert["data"]["victimId"], "b")
        self.assertEqual(alert["data"]["count"], 2)
        self.assertIn("stole 2 cards", alert["data"]["message"])

        priv = private[0]
        self.assertEqual(priv["private_to"], "b")
        self.assertEqual(priv["data"]["thiefId"], "a")
        self.assertEqual(priv["data"]["victimId"], "b")
        self.assertEqual(priv["data"]["count"], 2)
        self.assertEqual(len(priv["data"]["cards"]), 2)

    def test_alert_message_never_names_the_card(self):
        """Redaction, strengthened not relaxed: the PUBLIC alert still never
        names a card. Its private twin does — that's the whole point of A2."""
        game = _game({"a": [], "b": ["immunity_idol"]})
        execute_take_spec(game, {"victimId": "b", "kind": "index",
                                 "thiefId": "a", "index": 0, "force": True})
        alerts = game["_pending_alerts"]
        public_message = _public(alerts)[0]["data"]["message"]
        self.assertNotIn("Idol", public_message)
        self.assertNotIn("idol", public_message)

        priv = _private(alerts)[0]
        self.assertEqual(priv["private_to"], "b")
        self.assertEqual(priv["data"]["thiefId"], "a")
        self.assertEqual(priv["data"]["victimId"], "b")
        self.assertEqual(priv["data"]["cards"],
                         [{"name": "Hidden Immunity Idol", "type": "immunity_idol"}])
        self.assertIn("Hidden Immunity Idol", priv["data"]["message"])
        self.assertIn("took your", priv["data"]["message"])

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
        public, private = _public(alerts), _private(alerts)

        self.assertEqual({a["data"]["thiefId"] for a in public}, {"a", "b"})
        self.assertTrue(all(a["data"]["count"] == 1 for a in public))
        self.assertIn("stole a card", public[0]["data"]["message"])

        # c is robbed by both — one private alert per thief, both addressed
        # to c, each naming exactly the one card that thief took.
        self.assertEqual(len(private), 2)
        self.assertTrue(all(a["private_to"] == "c" for a in private))
        self.assertTrue(all(len(a["data"]["cards"]) == 1 for a in private))

    def test_a_bot_victim_gets_no_private_alert(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]}, bots=("b",))
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        alerts = game["_pending_alerts"]
        self.assertEqual(len(_public(alerts)), 1, "the table still hears it")
        self.assertEqual(_private(alerts), [],
                         "nobody is holding a bot's phone")

    def test_two_cards_read_an_oxford_free_and_join(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        priv = _private(game["_pending_alerts"])[0]
        names = [c["name"] for c in priv["data"]["cards"]]
        self.assertEqual(len(names), 2)
        self.assertEqual(priv["data"]["message"],
                         f"A took 2 of your cards — {names[0]} and {names[1]}")
        self.assertNotIn(", and", priv["data"]["message"])


class TurnStealRecordsAlertsTest(unittest.TestCase):
    def test_execute_theft_records_and_names_the_thief(self):
        engine = SurvivorRulesEngine()
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        engine.execute_theft(game, "a", "b")
        alert = _public(game["_pending_alerts"])[0]
        self.assertTrue(alert["data"]["message"].startswith("A stole"),
                        alert["data"]["message"])

    def test_execute_theft_private_alert_names_the_card(self):
        engine = SurvivorRulesEngine()
        game = _game({"a": [], "b": ["immunity_idol"]})
        engine.execute_theft(game, "a", "b")
        priv = _private(game["_pending_alerts"])[0]
        self.assertEqual(priv["private_to"], "b")
        self.assertEqual(priv["data"]["cards"],
                         [{"name": "Hidden Immunity Idol", "type": "immunity_idol"}])
        self.assertIn("Hidden Immunity Idol", priv["data"]["message"])

    def test_camp_raid_extra_card_joins_the_same_private_alert(self):
        """The public HTTP response keeps its synthetic '(+type from Camp
        Raid)' string unchanged (see execute_theft); the private alert
        names the same card for real, like any other."""
        engine = SurvivorRulesEngine()
        game = _game({"a": [], "b": ["extra_vote", "camp_raid", "the_spy_shack"]})
        game["players"]["b"]["campRaidedBy"] = "a"
        result = engine.execute_theft(game, "a", "b")

        self.assertTrue(any("Camp Raid" in c for c in result["stolen_cards"]),
                        "the public HTTP shape is untouched")

        priv = _private(game["_pending_alerts"])[0]
        self.assertEqual(priv["data"]["count"], 2)
        self.assertEqual(len(priv["data"]["cards"]), 2)
        for card in priv["data"]["cards"]:
            # A real {name, type} pair, not the synthetic "(+type from Camp
            # Raid)" suffix the public HTTP shape uses — "Camp Raid" itself
            # is also a legitimate card name here, so check for the suffix.
            self.assertNotIn("from Camp Raid)", card["name"])

    def test_a_bot_victim_gets_no_private_alert(self):
        engine = SurvivorRulesEngine()
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]}, bots=("b",))
        engine.execute_theft(game, "a", "b")
        self.assertEqual(_private(game["_pending_alerts"]), [])


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
        # (d) state mutates normally — ONE ballot physically moves (the
        # voteBanned full-silence belongs to Block A Vote alone now), the
        # thief votes twice, and the victim's own screen can say why.
        self.assertFalse(self.game["players"][victim].get("voteBanned"))
        self.assertEqual(self.game["players"][victim]["mandatoryVotes"], 0)
        self.assertEqual(self.game["players"][victim].get("votesStolenFrom"), 1)
        self.assertEqual(self.game["players"][actor]["mandatoryVotes"], 2)
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
        self.assertEqual(self.game["players"][victim]["mandatoryVotes"], 0)
        self.assertEqual(self.game["players"][actor]["mandatoryVotes"], 2)
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

    # ── the Voting Box skips a BLOCKED voter; a stolen-from voter still
    #    has to answer it (casting whatever remains, or passing it by) ────

    def test_the_box_skips_the_blocked_but_waits_on_the_stolen_from(self):
        actor, blocked, robbed = self.ids[1], self.ids[2], self.ids[0]
        self.give(actor, "block_vote")
        self.post('/api/tribal/advantage',
                  {"gameId": self.gid, "playerId": actor,
                   "advantageType": "block_vote", "targetId": blocked})
        self.assertTrue(self.game["players"][blocked]["voteBanned"])
        missing = self.gs._ballot_box_missing(self.game)
        self.assertNotIn(self.game["players"][blocked]["name"], missing)

        self.give(actor, "steal_vote")
        self.post('/api/tribal/advantage',
                  {"gameId": self.gid, "playerId": actor,
                   "advantageType": "steal_vote", "targetId": robbed})
        self.assertFalse(self.game["players"][robbed].get("voteBanned"))
        missing = self.gs._ballot_box_missing(self.game)
        self.assertIn(self.game["players"][robbed]["name"], missing,
                      "a stolen-from voter still answers the box")


if __name__ == "__main__":
    unittest.main(verbosity=2)
