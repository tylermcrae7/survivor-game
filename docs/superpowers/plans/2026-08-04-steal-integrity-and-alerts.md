# Steal Integrity & Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every card steal is provably conserved (victim −N, thief +N), visibly announced on every phone, gated behind a victim-only decline with a timeout, and the tribal reveal shows the votes an immune player would have received.

**Architecture:** The rules engine records a structured alert whenever cards move; the server's three dispatch layers (HTTP `handle()`, `/api/reactive/complete_theft`, bot broadcast) flush those alerts as `game_event` narrator events, which iOS's existing `NarrationFeed`/`ToastView` pipeline toasts. The Sorry For You window gains a deadline swept on the read path (same pattern as `_sweep_expired_discards`). The reveal change is client-side only — the server already broadcasts `rawVoteResults`.

**Tech Stack:** Python 3 (Flask + Flask-SocketIO, unittest), SwiftUI iOS 17+ (Swift Testing), legacy web bundle `client/dist/ui.js`.

**Run Python tests with:** `.venv/bin/python -m unittest tests.<module>` from the repo root. Tabs for indentation in `rules_engine.py` (match the file); 4 spaces in `survivor_server.py`, `interactions.py`, tests.

**Do not touch:** `bots.py` (bot `complete_pending_theft` calls stay playerId-less on purpose), `ios/SurvivorGame.xcodeproj/project.pbxproj` (generated — new Swift files must be registered by running `xcodegen generate` from `ios/`; new files under existing source dirs are picked up automatically by the existing target globs in `ios/project.yml`).

---

## Part A — Python server (Tasks 1–8)

### Task 1: The engine records who stole what, and the prose names the thief

**Files:**
- Modify: `rules_engine.py` (`request_take` ~line 332, `execute_take_spec` ~line 160, `execute_theft` ~line 2029)
- Modify: `survivor_server.py:2570` and `survivor_server.py:3450` (thief-nameless messages)
- Modify: `interactions.py` (delete dead `_steal_random`, ~lines 66–80)
- Test: `tests/test_steal_alerts.py` (new)

Every path that moves cards between hands appends a structured entry to `game["_pending_alerts"]` (a top-level, underscore-prefixed list — Task 2 strips it from client state and flushes it as socket events). Card identities never go into an alert — names and counts only.

- [ ] **Step 1: Write the failing tests**

```python
#!/usr/bin/env python3
"""Structured steal alerts: every card movement leaves a record to announce."""
import os, sys, unittest

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m unittest tests.test_steal_alerts -v`
Expected: FAIL — no `_pending_alerts` key, `_steal_random` still exists.

- [ ] **Step 3: Implement the recording**

In `rules_engine.py`, add one module-level helper near `execute_take_spec` (~line 158), then call it from both movers. **This file uses tabs.**

```python
def _record_steal_alert(game, thief_id, victim_id, count, source=None):
	"""Leave a structured record for the server layer to announce.

	Names and counts only — an alert crosses every phone in the room, so a
	card identity here would undo the redaction the take messages keep.
	"""
	if count <= 0:
		return
	thief = game["players"].get(thief_id, {})
	victim = game["players"].get(victim_id, {})
	cards = "a card" if count == 1 else f"{count} cards"
	game.setdefault("_pending_alerts", []).append({
		"event": "steal",
		"data": {
			"thiefId": thief_id, "thief": thief.get("name", "?"),
			"victimId": victim_id, "victim": victim.get("name", "?"),
			"count": count, "source": source or "steal",
			"message": f"{thief.get('name', '?')} stole {cards} from {victim.get('name', '?')}",
		},
	})
```

Wire it in:
- `execute_take_spec` `"random_each"` branch: after the per-thief loop, for each `(pid, n)` in `taken.items()` call `_record_steal_alert(game, pid, spec["victimId"], n, spec.get("source"))`.
- `"index"` branch: after the successful `hand.pop(idx)` append, `_record_steal_alert(game, spec["thiefId"], spec["victimId"], 1, spec.get("source"))`.
- `"by_type"` branch: after a successful move, same call with count 1.
- `"vote_card"` branch: after a successful move, same call with count 1.
- `execute_theft` (~line 2076, after the camp-raid extra): `_record_steal_alert(game, thief_id, target_id, len(stolen_cards))` — count includes the camp-raid extra.
- `request_take` (~line 344): change `spec = {**spec, "victimId": victim_id}` to also carry `"source": source` so the alert can say where the raid came from.

- [ ] **Step 4: Name the thief in the turn-steal prose**

`survivor_server.py:2570` and `survivor_server.py:3450` both read `f"Stole {len(stolen_cards)} card(s) from ..."`. Change both to name the thief and pluralize honestly, e.g. at 2570:

```python
        n = len(stolen_cards)
        cards_word = "a card" if n == 1 else f"{n} cards"
        return {
            "success": True,
            "message": f"{thief.get('name', 'Someone')} stole {cards_word} from {target.get('name', 'player')}",
            "stolen_cards": stolen_cards,
        }
```

Mirror at 3450 (`target_name` variable is already in scope there; the thief is `game["players"].get(thief_id, {})`). Keep the `stolen_cards` key — the acting client reads it.

**Check for stale tests:** `grep -rn "Stole " tests/` — any test asserting the old prose must be updated to the new wording, not deleted.

- [ ] **Step 5: Delete dead `_steal_random`**

`interactions.py` ~lines 66–80. First confirm: `grep -n "_steal_random" -r .` must show only the definition. Delete the method. Its import line `from rules_engine import request_take, takeable_indices` stays (both still used).

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_steal_alerts tests.test_reward_interactions tests.test_card_effects tests.test_rules_enforcement -v 2>&1 | tail -5`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add rules_engine.py survivor_server.py interactions.py tests/test_steal_alerts.py
git commit -m "Every steal leaves a record, and the prose names the thief"
```

### Task 2: The server announces steals (and blocked raids) to every phone

**Files:**
- Modify: `survivor_server.py` — `get_game_state` (~line 657), `handle()` (~line 3700), `_emit_narrator_events` (~line 3493), `api_complete_theft` (~line 4599), `_bot_broadcast` (~line 4758)
- Modify: `rules_engine.py` — `_effect_sorry_for_you` (~line 1755)
- Test: extend `tests/test_steal_alerts.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_steal_alerts.py`)

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m unittest tests.test_steal_alerts -v`
Expected: the two new tests FAIL (underscore key leaks; no raid_blocked alert).

- [ ] **Step 3: Strip top-level underscore keys from the client state**

In `get_game_state`, right after the existing hidden-holder stripping loop (~line 678), add:

```python
        # Top-level underscore keys are server plumbing (pending alert
        # flushes) — same rule as the hidden holders: never on the wire.
        for key in [k for k in enriched_game if k.startswith("_")]:
            del enriched_game[key]
```

- [ ] **Step 4: The Sorry For You block records an alert**

In `rules_engine.py` `_effect_sorry_for_you`, just before the `return` (~line 1803), append (tabs):

```python
		defender = game["players"][player_id]
		game.setdefault("_pending_alerts", []).append({
			"event": "raid_blocked",
			"data": {
				"defenderId": player_id, "defender": defender.get("name", "?"),
				"thiefIds": list(thief_ids),
				"message": f"{defender.get('name', '?')} played Sorry For You — the raid fails",
			},
		})
```

- [ ] **Step 5: One flush helper, four call sites**

In `survivor_server.py`, add a module-level function next to `_emit_narrator_events` (~line 3490):

```python
def _flush_steal_alerts(gid):
    """Announce any takes the engine recorded since the last flush.

    Reads the LIVE game (not the client copy) and emits one narrator event
    per alert; every phone's toast pipeline picks these up. Safe to call
    when there is nothing to say.
    """
    game = game_state.games.get(gid)
    if not game:
        return
    for alert in game.pop("_pending_alerts", []) or []:
        try:
            emit_game_event(gid, alert["event"], alert["data"])
        except Exception as e:
            logger.error(f"Steal alert emit failed for {gid}: {e}")
```

Call it from:
1. `handle()` — immediately after the action result comes back, before the `state_update` emit (~line 3700): `_flush_steal_alerts(gid)`.
2. `api_complete_theft` — after a successful `complete_pending_theft`, before returning (~line 4613).
3. `_bot_broadcast` — first line, before `get_game_state` (~line 4759).
4. Task 4's expiry sweep will add the fourth call.

Then in `_emit_narrator_events` **delete the old `'steal'` special-case block** (~3493–3513) — it fired only for the turn-steal action and is now redundant with the flush (double toast otherwise). Keep the payload contract: the new alert `data` carries `thief`/`victim`/`thiefId`/`victimId` exactly as the old event did, plus `count`, `source`, `message`.

**Check for stale tests:** `grep -rn "narrator\|game_event\|'steal'" tests/test_narrator_events.py` — update any assertion that expected the old steal event shape or emission site to expect the flush-emitted event instead (same event name `steal`, same core keys, new extras). Do not delete coverage; move it.

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_steal_alerts tests.test_narrator_events -v 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add survivor_server.py rules_engine.py tests/test_steal_alerts.py tests/test_narrator_events.py
git commit -m "Steals and blocked raids announce themselves on every phone"
```

### Task 3: Only the raid's target can wave the raid through

**Files:**
- Modify: `survivor_server.py` — `complete_pending_theft` (~line 3402), `api_complete_theft` (~line 4599)
- Test: `tests/test_theft_window.py` (new)

Today `/api/reactive/complete_theft` takes only a `gameId`: any client — including the thief — can force-decline the victim's Sorry For You window. The method gains an optional `playerId`; the HTTP route makes it mandatory and victim-only. Internal callers (bots driver, Task 4's sweep) pass none and stay trusted.

- [ ] **Step 1: Write the failing tests**

```python
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
```

Note: if the access gate blocks the route test (401), follow the pattern other HTTP tests in `tests/` use to disable/satisfy the gate (grep `gate_enabled\|SURVIVOR_ACCESS_CODE` in `tests/`) and copy that idiom into `setUp`.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m unittest tests.test_theft_window -v`
Expected: FAIL — `complete_pending_theft` accepts the thief today; route accepts bare gameId.

- [ ] **Step 3: Implement**

Method signature: `def complete_pending_theft(self, gid, playerId=None, **kwargs):` and right after the `reactive_window_open` check add:

```python
        # Only the raid's target may let it through. None = the server
        # itself: the bot driver answering for a bot victim, or the
        # expiry sweep declaring silence a decline.
        if playerId is not None and playerId != pending_theft.get("targetId"):
            return {"success": False,
                    "message": "Only the raid's target can let it through"}
```

Route: after the `game_id` check add:

```python
    player_id = data.get('playerId')
    if not player_id:
        return {"success": False,
                "message": "playerId required — only the raid's target can let a raid through"}, 400
```

and pass it: `game_state.complete_pending_theft(game_id, playerId=player_id)`.

**Compatibility note (record in the final report, not code):** TestFlight builds in the field don't send `playerId`; their "let them take it" button will start refusing after deploy. Task 4's 60-second sweep resolves those windows anyway, and the new iOS build (Task 9) sends it. `bots.py` needs no change — the driver calls the method with no playerId.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_theft_window tests.test_card_effects -v 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add survivor_server.py tests/test_theft_window.py
git commit -m "Only the raid's target can wave the raid through"
```

### Task 4: The Sorry For You window closes on its own

**Files:**
- Modify: `survivor_server.py` — constant near `PENALTY_DISCARD_SECONDS` (~line 69), `get_game_state` (~line 659), new `_sweep_expired_theft`, legacy window creation (~line 2548)
- Modify: `rules_engine.py` — `request_take` (~line 355)
- Test: extend `tests/test_theft_window.py`

A human victim who backgrounds the app currently freezes the table forever. Mirror `_sweep_expired_discards`: stamp a deadline when the window opens, sweep it on the read path, silence = decline (the held take executes).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_theft_window.py`)

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m unittest tests.test_theft_window -v`
Expected: the four new tests FAIL.

- [ ] **Step 3: Implement**

Constant next to `PENALTY_DISCARD_SECONDS` in `survivor_server.py`:

```python
# How long a Sorry For You window stays open before silence means "take it".
# Long enough to find the card and think; short enough that a backgrounded
# phone can't freeze the table. Bots answer in seconds and never see it.
THEFT_WINDOW_SECONDS = 60.0
```

New method after `_sweep_expired_discards` (~line 1168):

```python
    def _sweep_expired_theft(self, gid):
        """Silence is a decline: an expired Sorry For You window executes.

        Same shape as _sweep_expired_discards, and for the same reason — a
        blocking window with no way out once wedged a game forever. Runs on
        the read path; somebody is always looking.
        """
        game = self.games.get(gid)
        window = (game or {}).get("pending_theft")
        if not window or not window.get("reactive_window_open"):
            return False
        deadline = window.get("deadline")
        if deadline is None:
            # Opened before deadlines existed (a deploy mid-game): heal on
            # read rather than fire on sight.
            window["deadline"] = time.time() + THEFT_WINDOW_SECONDS
            return False
        if time.time() < deadline:
            return False
        logger.info(f"Sorry For You window expired in {gid} — the take executes")
        self.complete_pending_theft(gid)
        _flush_steal_alerts(gid)
        return True
```

Call it in `get_game_state` right after `self._sweep_expired_discards(gid)` (~line 659): `self._sweep_expired_theft(gid)`.

Stamp deadlines at both creation sites:
- `rules_engine.py` `request_take` (~line 355): add to the `game["pending_theft"]` dict: `"openedAt": time.time(), "deadline": time.time() + 60.0,` — `rules_engine` must not import from `survivor_server` (circular); use the literal with a comment `# keep in step with THEFT_WINDOW_SECONDS`, and add `import time` at the top of `rules_engine.py` if missing.
- `survivor_server.py:2548` legacy turn-steal window: add `"openedAt": time.time(), "deadline": time.time() + THEFT_WINDOW_SECONDS,`.

Note `_flush_steal_alerts` is module-level and `game_state` may not exist in bare-unittest contexts — guard the sweep's call: `if 'game_state' in globals() and game_state is not None:` is ugly; instead make `_flush_steal_alerts` tolerate a missing global: wrap its body in `try/except NameError: return`. Keep it simple and covered by the tests.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_theft_window tests.test_reward_interactions -v 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add survivor_server.py rules_engine.py tests/test_theft_window.py
git commit -m "A Sorry For You window nobody answers closes on its own"
```

### Task 5: A council no longer eats a hanging steal

**Files:**
- Modify: `rules_engine.py` — post-tribal flag reset (~line 1636)
- Test: extend `tests/test_theft_window.py`

The post-tribal reset pops `pending_theft` silently — the winner's held take vanishes. Resume it instead.

- [ ] **Step 1: Write the failing test** (append to `tests/test_theft_window.py`)

```python
class TheCouncilDoesNotEatAWonStealTest(unittest.TestCase):
    def test_post_tribal_reset_resumes_the_held_take(self):
        gs = _fresh_gamestate()
        gs.games["g1"] = _game_with_window(deadline=time.time() + 60)
        game = gs.games["g1"]
        # Find the reset by behavior: it is the method that pops
        # pending_theft after a council (reset_post_tribal_flags or the
        # engine method the server calls — locate via
        # `grep -n "pending_theft" rules_engine.py` around line 1636).
        gs.rules_engine.reset_post_tribal_flags(game)
        self.assertIsNone(game.get("pending_theft"))
        self.assertEqual(len(game["players"]["thief"]["hand"]), 2,
                        "the held take must execute, not evaporate")
```

Adjust the method name to whatever the function at `rules_engine.py:1636` actually belongs to (read the enclosing `def` — the grep in the comment finds it; update the test to call it the way the server does).

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m unittest tests.test_theft_window -v`
Expected: new test FAILS (hand still 0 — the take evaporated).

- [ ] **Step 3: Implement** (tabs — this is `rules_engine.py`)

Replace `game.pop("pending_theft", None)` at ~line 1636 with:

```python
		theft = game.pop("pending_theft", None)
		if theft and theft.get("_resume"):
			# The council ended while a Sorry For You window hung open.
			# The take was already won — resume it rather than letting
			# the reward die with the phase.
			result = execute_take_spec(game, theft["_resume"])
			logger.warning("Resumed a theft the council interrupted: "
			               f"{result.get('message')}")
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_theft_window tests.test_tribal_council -v 2>&1 | tail -5`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rules_engine.py tests/test_theft_window.py
git commit -m "A council no longer eats a steal the window was holding"
```

### Task 6: Do Or Die needs an opponent

**Files:**
- Modify: `rules_engine.py` — `_validate_action_card_play` do_or_die branch (~line 1210)
- Test: extend `tests/test_reward_interactions.py`

- [ ] **Step 1: Write the failing test** — add to the Do Or Die test class in `tests/test_reward_interactions.py` (match its existing setup idiom — read the neighboring tests first):

```python
    def test_you_cannot_challenge_yourself(self):
        result = self.play_do_or_die(target=self.initiator_id, choice="rock")
        self.assertFalse(result["success"])
        self.assertIn("yourself", result["message"])
```

(Adapt `self.play_do_or_die`/`self.initiator_id` to the helper names that file actually uses — read `test_play_without_a_throw_keeps_the_card` at line 85 and mirror it.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m unittest tests.test_reward_interactions -v 2>&1 | tail -5`
Expected: new test FAILS (self-target currently validates).

- [ ] **Step 3: Implement** (tabs) — in the `reward_challenge_do_or_die` branch:

```python
		elif card_type == "reward_challenge_do_or_die":
			if params.get("targetId") == player_id:
				return False, "Do Or Die needs an opponent — you can't challenge yourself"
			if params.get("choice") not in ("rock", "paper", "scissors"):
				return False, "Do Or Die requires your secret throw: rock, paper or scissors"
			if game.get("interaction"):
				return False, "Another Reward Challenge is already in progress"
```

- [ ] **Step 4: Run, expect PASS, commit**

```bash
git add rules_engine.py tests/test_reward_interactions.py
git commit -m "Do Or Die needs an opponent"
```

### Task 7: Conservation — every steal moves exactly what it says

**Files:**
- Test: `tests/test_card_conservation.py` (new — pure tests, no production change expected; any failure found is a bug to fix in the smallest way and note in the report)

Tyler's ask, verbatim: "Confirm in code that if 2 cards must be taken that the hand count goes down by two and up by two respectively. This should be for any stealing of cards."

- [ ] **Step 1: Write the suite**

```python
#!/usr/bin/env python3
"""Card conservation: a steal moves exactly N cards, and mints none.

For every path that takes cards, assert three things: the victim's hand
shrank by N, the thief's grew by N, and the total number of cards in the
game (hands + deck + discard) did not change.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules_engine import (execute_take_spec, new_card, SurvivorRulesEngine)
from interactions import interaction_engine


def _game(hands, deck=0, discard=0):
    return {
        "players": {
            pid: {"name": pid.capitalize(), "hand": [new_card(t) for t in types],
                  "isEliminated": False}
            for pid, types in hands.items()
        },
        "deck": [new_card("extra_vote") for _ in range(deck)],
        "discard": [new_card("camp_raid") for _ in range(discard)],
        "turnOrder": list(hands.keys()), "currentTurnIndex": 0,
        "phase": "playing",
    }


def _census(game):
    return (sum(len(p.get("hand") or []) for p in game["players"].values())
            + len(game.get("deck") or []) + len(game.get("discard") or []))


def _hand(game, pid):
    return len(game["players"][pid].get("hand") or [])


class ConservationCase(unittest.TestCase):
    def assertMoved(self, game, action, thief, victim, n):
        """Run action(), then assert thief +n, victim -n, census equal."""
        before_thief, before_victim = _hand(game, thief), _hand(game, victim)
        census = _census(game)
        action()
        self.assertEqual(_hand(game, thief), before_thief + n, "thief's gain")
        self.assertEqual(_hand(game, victim), before_victim - n, "victim's loss")
        self.assertEqual(_census(game), census, "cards minted or destroyed")


class TakeSpecConservationTest(ConservationCase):
    def test_random_each_two_cards(self):
        game = _game({"a": ["vote"], "b": ["vote", "extra_vote", "camp_raid", "the_spy_shack"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                             "takes": [{"thiefId": "a", "count": 2}]}),
            thief="a", victim="b", n=2)

    def test_random_each_never_takes_the_vote_card(self):
        game = _game({"a": [], "b": ["vote", "extra_vote"]})
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        self.assertEqual([c["type"] for c in game["players"]["b"]["hand"]], ["vote"])
        self.assertEqual(_hand(game, "a"), 1)

    def test_pair_takes_one_each(self):
        game = _game({"a": [], "b": [], "c": ["extra_vote", "camp_raid", "vote"]})
        before = _census(game)
        execute_take_spec(game, {"victimId": "c", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 1},
                                           {"thiefId": "b", "count": 1}]})
        self.assertEqual((_hand(game, "a"), _hand(game, "b"), _hand(game, "c")),
                         (1, 1, 1))
        self.assertEqual(_census(game), before)

    def test_index_take(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "index",
                                             "thiefId": "a", "index": 1}),
            thief="a", victim="b", n=1)

    def test_by_type_take(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "by_type",
                                             "thiefId": "a", "cardType": "camp_raid"}),
            thief="a", victim="b", n=1)

    def test_vote_card_take(self):
        game = _game({"a": [], "b": ["vote", "extra_vote"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "vote_card",
                                             "thiefId": "a"}),
            thief="a", victim="b", n=1)

    def test_short_hand_takes_what_exists(self):
        """Asked for 2, victim has 1 takeable: exactly 1 moves, none invented."""
        game = _game({"a": [], "b": ["vote", "extra_vote"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                             "takes": [{"thiefId": "a", "count": 2}]}),
            thief="a", victim="b", n=1)


class TurnStealConservationTest(ConservationCase):
    def test_plain_steal_moves_one(self):
        engine = SurvivorRulesEngine()
        game = _game({"a": ["vote"], "b": ["vote", "extra_vote", "camp_raid"]})
        self.assertMoved(game, lambda: engine.execute_theft(game, "a", "b"),
                         thief="a", victim="b", n=1)


class DoOrDieEndToEndConservationTest(ConservationCase):
    """The reported bug, end to end: win RPS, get exactly 2 of the loser's cards."""
    def test_winner_gets_two_loser_loses_two(self):
        game = _game({"a": ["vote"], "b": ["vote", "extra_vote", "camp_raid", "the_spy_shack"]})
        interaction_engine.start(game, "a", "do_or_die",
                                 {"targetId": "b", "choice": "rock"})
        self.assertMoved(
            game,
            lambda: interaction_engine.act(game, "b", "pick", "scissors"),
            thief="a", victim="b", n=2)

    def test_tie_swap_conserves_hand_sizes(self):
        game = _game({"a": ["vote", "extra_vote"], "b": ["vote", "camp_raid"]})
        interaction_engine.start(game, "a", "do_or_die",
                                 {"targetId": "b", "choice": "rock"})
        interaction_engine.act(game, "b", "pick", "rock")   # tie -> give phase
        before = _census(game)
        interaction_engine.act(game, "a", "give", 1)
        interaction_engine.act(game, "b", "give", 1)
        self.assertEqual(_hand(game, "a"), 2)
        self.assertEqual(_hand(game, "b"), 2)
        self.assertEqual(_census(game), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run**

Run: `.venv/bin/python -m unittest tests.test_card_conservation -v`
Expected: PASS on first run (Tasks 1–6 landed first). Any failure is a real conservation bug: fix it minimally in the engine and note it in the final report.

- [ ] **Step 3: Commit**

```bash
git add tests/test_card_conservation.py
git commit -m "Prove every steal moves exactly the cards it claims"
```

### Task 8: The history remembers the votes immunity erased

**Files:**
- Modify: `survivor_server.py` — `elimination_record` (~line 1718)
- Test: extend `tests/test_tribal_council.py` (`test_tribal_council_immunity_protection`, line ~657)

The reveal payload already carries `rawVoteResults` (pre-nullification) and `protectedPlayers` — clients just ignore them (fixed in Tasks 10–12). Two server gaps: the post-council history record drops the raw counts, and nothing tests the field.

- [ ] **Step 1: Extend the test** — in `test_tribal_council_immunity_protection` (read it first; it stages an immune player receiving votes), after the existing `protectedPlayers` assertion (~line 695) add:

```python
        raw = current_vote.get("rawVoteResults") or {}
        self.assertGreater(raw.get(immune_player_id, 0), 0,
                           "the reveal must remember the votes immunity erased")
```

(Use the actual variable names in that test — read lines 657–700 first.) Run: expect PASS already for the reveal half (the server sets the field) — this pins the contract. Then add the history half:

```python
        # complete the council the way the test file's other cases do, then:
        record = game["gameHistory"][-1]
        self.assertEqual(record.get("raw_vote_results"), raw,
                         "the recap must keep the pre-immunity tally")
```

If the existing test doesn't run `complete_tribal`, mirror the completion idiom used by the nearest test in the same file that does.

- [ ] **Step 2: Run to see the history half fail**

Run: `.venv/bin/python -m unittest tests.test_tribal_council -v 2>&1 | tail -5`
Expected: FAIL on `raw_vote_results`.

- [ ] **Step 3: Implement** — in `complete_tribal`'s `elimination_record` (~line 1718) add:

```python
            "raw_vote_results": current_vote.get("rawVoteResults", {}),
```

- [ ] **Step 4: Run, expect PASS, commit**

```bash
git add survivor_server.py tests/test_tribal_council.py
git commit -m "The recap keeps the votes immunity erased"
```

---

## Part B — iOS (Tasks 9–11) — all files under `ios/SurvivorGame`

### Task 9: The decline button says who is declining

**Files:**
- Modify: `ios/SurvivorGame/Networking/APIClient.swift:202-204`, `ios/SurvivorGame/Networking/GameClient.swift:290-297`

- [ ] **Step 1: Implement** — `APIClient.completeTheft` gains a `playerId`:

```swift
    func completeTheft(gameId: String, playerId: String) async throws {
        try await post("/api/reactive/complete_theft",
                       body: ["gameId": gameId, "playerId": playerId])
    }
```

(Match the file's actual request idiom at line 202 — read it first; the body today is `["gameId": gameId]`.) In `GameClient.completeTheft()` pass the stored player id the same way neighboring methods do (see `steal`'s `thiefId` at `APIClient.swift:155-158` and how `GameClient` supplies `playerId` elsewhere). Both call sites (`PlayingViewModel.swift:137-142`, `ReactiveTheftOverlay.swift:168`) go through `GameClient` and need no change if `GameClient` injects its own `playerId`.

- [ ] **Step 2: Build + unit tests**

Run: `cd ios && xcodebuild test -scheme SurvivorGame -destination 'platform=iOS Simulator,name=iPhone 16' 2>&1 | tail -5` (use the scheme/destination the repo's CI or previous sessions used — check `ios/project.yml` scheme name).
Expected: build succeeds, tests pass.

- [ ] **Step 3: Commit**

```bash
git add ios/SurvivorGame/Networking/APIClient.swift ios/SurvivorGame/Networking/GameClient.swift
git commit -m "iOS: declining a raid says who is declining"
```

### Task 10: Toasts for steals with counts, and for blocked raids

**Files:**
- Modify: `ios/SurvivorGame/Models/NarrationEvent.swift` (`.steal` case ~lines 17, 41-45, 89-90)
- Test: the narration unit test file if one exists (`grep -rn "NarrationEvent" ios/SurvivorGameTests/`) — extend it; otherwise add cases to the nearest model-decoding test file.

The server now sends `count` and `message` in the `steal` event data, and a new `raid_blocked` event. `NarrationFeed`/`ToastView` need no changes — only the event parsing.

- [ ] **Step 1: Read `NarrationEvent.swift` fully.** Understand how `.custom(type, data)` becomes a `NarrationEvent` (init at ~lines 35-77) and what unknown types do today.

- [ ] **Step 2: Extend**
- `steal` parsing: read `count` (Int, default 1) from data; message becomes `"\(thief) stole a card from \(victim)"` / `"\(thief) stole \(count) cards from \(victim)"`. Prefer the server's `message` string when present (`data["message"] as? String`) so wording stays server-authoritative; fall back to the constructed one. Keep the existing `.steal` sound cue.
- New `raid_blocked` handling: use the server's `message` ("X played Sorry For You — the raid fails"); pick the sound/priority idiom the file uses for negative events (read what exists — if there's no obvious cue, reuse the steal cue). If the init switches on a string type, add a `case "raid_blocked":` arm.

- [ ] **Step 3: Unit test** — mirror the file's existing test idiom (if `NarrationEvent` has tests, extend; else create `ios/SurvivorGameTests/NarrationEventTests.swift` using Swift Testing `@Test`/`#expect`):

```swift
import Testing
@testable import SurvivorGame

struct StealNarrationTests {
    @Test func stealWithCountReadsCards() {
        let event = NarrationEvent(type: "steal", data: [
            "thief": "TDawg", "victim": "Mango", "count": 2,
            "message": "TDawg stole 2 cards from Mango",
        ])
        #expect(event?.message == "TDawg stole 2 cards from Mango")
    }

    @Test func raidBlockedUsesTheServersWords() {
        let event = NarrationEvent(type: "raid_blocked", data: [
            "defender": "Mango",
            "message": "Mango played Sorry For You — the raid fails",
        ])
        #expect(event?.message == "Mango played Sorry For You — the raid fails")
    }

    @Test func stealWithoutCountStillReads() {
        let event = NarrationEvent(type: "steal",
                                   data: ["thief": "A", "victim": "B"])
        #expect(event?.message.contains("A") == true)
    }
}
```

(Adapt the initializer signature to the real one — read the file first; if `NarrationEvent(type:data:)` is failable or takes `[String: Any]`, mirror it.)

- [ ] **Step 4: Build + tests, commit**

```bash
git add ios/SurvivorGame/Models/NarrationEvent.swift ios/SurvivorGameTests/
git commit -m "iOS: steals toast with their count, blocked raids toast their block"
```

### Task 11: The reveal shows the votes that didn't count

**Files:**
- Modify: `ios/SurvivorGame/State/TribalVoteState.swift` (add `rawVoteResults` — mirror `voteResults` at lines 9/49-50/64-65)
- Modify: `ios/SurvivorGame/ViewModels/TribalViewModel.swift` (`voteResults` computed property, lines 76-84)
- Modify: `ios/SurvivorGame/Views/Tribal/VoteRevealView.swift` (`VoteResultRow`, ~line 63)
- Test: the fixtures/decoding test for `TribalVoteState` (`grep -rn "TribalVoteState\|voteResults" ios/SurvivorGameTests/`) — extend with `rawVoteResults`.

- [ ] **Step 1: Decode the field** — in `TribalVoteState`: `var rawVoteResults: [String: Int]?` + CodingKeys case + decode line, exactly mirroring `voteResults` one line above. Older servers omit it — it must stay optional.

- [ ] **Step 2: Merge immune players into the reveal rows** — in `TribalViewModel`, the computed `voteResults` (~line 76) currently maps only `voteState?.voteResults`. Change it to produce rows from: every entry of `voteResults`, PLUS every player in `protectedPlayers` who has a nonzero count in `rawVoteResults` but is absent from `voteResults`. Each row needs an `isImmune` flag (false for normal rows). Keep the property name and ordering (sorted by votes descending, matching current behavior) so `EliminationView.swift:13`'s delay math stays consistent automatically. The immune row's vote number comes from `rawVoteResults`.

- [ ] **Step 3: Render the badge** — `VoteResultRow` gains `isImmune: Bool` (default false, next to `isTied`). When immune: the vote count renders in a dimmed style (`Torch.Color.textFaint` — check the file's palette usage) and a small capsule badge reading `IMMUNE` in the file's label style; accessibility label: `"\(name) would have received \(votes) votes — immune, they don't count"`. Follow the existing `isTied` badge's implementation (~lines 100-103) as the template.

- [ ] **Step 4: Unit test** — extend the decoding/fixture test found in Step 0 grep:

```swift
@Test func rawVoteResultsDecodes() throws {
    let json = #"{"phase":"reveal","voteResults":{},"rawVoteResults":{"p1":3},"protectedPlayers":["p1"]}"#
    let state = try JSONDecoder().decode(TribalVoteState.self, from: Data(json.utf8))
    #expect(state.rawVoteResults?["p1"] == 3)
}
```

(Adapt to the struct's real decoding — it has a manual `init(from:)` at lines 64-65, so the JSON key names must match the CodingKeys; read them.) Add a `TribalViewModel` test asserting an immune player with 3 raw votes and no counted votes appears as a row with `isImmune == true` and `votes == 3` — construct the view model the way its existing tests do (find them via `grep -rn "TribalViewModel" ios/SurvivorGameTests/`).

- [ ] **Step 5: Build + tests, commit**

```bash
git add ios/SurvivorGame/State/TribalVoteState.swift ios/SurvivorGame/ViewModels/TribalViewModel.swift ios/SurvivorGame/Views/Tribal/VoteRevealView.swift ios/SurvivorGameTests/
git commit -m "iOS: the reveal shows the votes immunity erased"
```

---

## Part C — Web client (Task 12) — files under `client/dist` only

### Task 12: Web parity — decline identifies itself; reveal shows erased votes

**Files:**
- Modify: `client/dist/network.js:748-750` (`completeTheft`)
- Modify: `client/dist/ui.js:3047` (allowBtn handler), `client/dist/ui.js:434-503` (`renderVoteResults`)

- [ ] **Step 1: `completeTheft` sends the player** —

```js
async completeTheft(gameId, playerId) {
    return apiCall('/reactive/complete_theft', { gameId, playerId });
},
```

At `ui.js:3047` pass the local player's id — find the variable the surrounding raid-prompt code uses for "me" (the same identity the `handle_reactive_card_play` call nearby sends) and pass it through.

- [ ] **Step 2: Immunity in `renderVoteResults`** (`ui.js:434-503`) — after `sortedResults` is built from `voteCounts`, append entries for every player in `currentVote.protectedPlayers || []` whose `currentVote.rawVoteResults?.[pid] > 0` and who is not already in the list; carry an `isImmune` flag. Render immune rows with their raw count, visually dimmed, plus a badge span (reuse the styling pattern of `vote-result-eliminated-badge` at ~line 486) reading `IMMUNE — votes don't count`. Do not change the eliminated badge or sort order for counted rows; immune rows sort by their raw count among themselves and render after counted rows (simplest stable choice).
- Note (pre-existing quirk, do not "fix" silently): the `voteCounts` fallback at `ui.js:446-454` re-sums raw ballots when `voteResults` is empty, which would already include immune players — leave that logic alone and only ADD the immune rows when they're not present.

- [ ] **Step 3: Manual check + commit** — no JS test harness exists for `client/dist`; sanity-check by loading the page (`python3 -m http.server` is not enough — it needs the live server; the reviewer will verify against the deployed server).

```bash
git add client/dist/network.js client/dist/ui.js
git commit -m "Web: decline identifies itself; the reveal shows erased votes"
```

---

## Coordination notes for the dispatcher

- Part A (Tasks 1–8), Part B (9–11), Part C (12) touch disjoint files and may run as three parallel subagents in ONE worktree (do not create git worktrees — see memory note on worktree failures under load). Each agent commits only its own files; **no agent runs `git commit -a` or stages files outside its part.**
- Part A's agent must run the FULL Python suite at the end (`.venv/bin/python run_all_tests.py` or `for f in tests/test_*.py; do ...` — match how previous sessions ran it) and report any failure it did not introduce verbatim.
- Parts B and C depend on Part A only at runtime (event names/payloads are fixed by this plan), so they can build and test independently.
- The dispatcher (main session) owns: final review, full test runs, simulator screenshot verification, `bash deploy/redeploy.sh`, and the report. Server deploy delivers Tasks 1–8 and 12; Tasks 9–11 ride the next TestFlight build.
