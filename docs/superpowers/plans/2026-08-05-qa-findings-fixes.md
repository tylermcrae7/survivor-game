# QA Findings Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every finding from the 2026-08-05 three-surface e2e QA pass is fixed: the silent history gaps, the frozen-table exposure, the web client's create/overflow/console defects, the lobby-exit gap, and the iOS/web cosmetic issues.

**Architecture:** Server-side, the two hand-rolled reactive routes gain the same eventLog append every `handle()` action already gets, plus the missing alert flush; a lobby-only self-leave endpoint fills the API gap. Client fixes are local to each surface. Nothing touches the tie-break cascade, the deck builder, or the steal engine.

**Tech Stack:** Python 3 (unittest, `.venv/bin/python`), SwiftUI iOS 17+ (Swift Testing), web bundle `client/dist`. Tabs in `rules_engine.py` (untouched here); 4 spaces elsewhere.

**Evidence sources:** the three QA reports (API/iOS/web agents, 2026-08-05). File:line anchors below come from those reports — treat as approximate anchors, grep before editing.

---

## Part S — Server (Python)

### Task S1: The reactive routes write history and flush alerts

**Finding #1 (real, top priority):** `/api/reactive/complete_theft` (~`survivor_server.py:4689`) and `/api/reactive/play_card` (~`:4665`) bypass `handle()`, so their outcomes never reach `game["eventLog"]` — the web "Story So Far" freezes on "Theft initiated…" forever, and iOS history misses the same lines. The play_card route also never calls `_flush_steal_alerts`, so a HUMAN victim playing Sorry For You gets the `raid_blocked` toast late (only when the bot broadcast happens to flush).

**Files:**
- Modify: `survivor_server.py` (both routes + one new helper)
- Test: `tests/test_steal_alerts.py` (extend)

- [ ] **Step 1: Failing tests** (append to `tests/test_steal_alerts.py`, reusing its `_game`/GameState fixtures):

```python
class ReactiveRoutesWriteHistoryTest(unittest.TestCase):
    """The two hand-rolled routes must log outcomes like every handled action."""

    def setUp(self):
        import survivor_server
        self.server = survivor_server
        self.client = survivor_server.app.test_client()
        # Build a game with an open Sorry For You window via the real
        # GameState — mirror OnlyTheTargetClosesTheWindowTest's fixture in
        # tests/test_theft_window.py (import or copy its helper).

    def test_declining_lands_the_outcome_in_the_event_log(self):
        # POST /api/reactive/complete_theft as the victim
        # -> eventLog's last entry mentions "stole"
        ...

    def test_blocking_lands_sorry_for_you_in_the_event_log(self):
        # victim holds sorry_for_you; POST /api/reactive/play_card with its idx
        # -> eventLog gains the "Sorry for you! The raid fails" line
        # -> AND game["_pending_alerts"] is EMPTY afterwards (flushed), not
        #    sitting there waiting for a bot broadcast
        ...
```

(Write them fully — the `...` above is scaffolding for THIS plan only; the real tests must assert on real fixtures. `test_theft_window.py`'s `_game_with_window` builder is importable or copyable.)

- [ ] **Step 2: Implement.** Extract the eventLog append that lives inside `handle()` (~`:3711-3722` — log_message preferred over message, `[:200]` cap, `del log_list[:-120]`) into a module-level helper:

```python
def _append_event_log(gid, result):
    """The Story So Far entry every successful action leaves behind.

    handle() does this for every routed action; the hand-rolled reactive
    routes must do it too or a raid that met a Sorry For You vanishes
    from history (found live: the web drawer froze on "Theft initiated").
    """
    if not isinstance(result, dict) or not result.get("message") \
            or not result.get("success", True):
        return
    log_list = game_state.games.get(gid, {}).setdefault("eventLog", [])
    log_msg = result.get("log_message") or result["message"]
    log_list.append({"t": time.time(), "msg": str(log_msg)[:200]})
    del log_list[:-120]
```

Replace `handle()`'s inline block with a call to it (identical behavior — keep the same skip-list condition for `add_bot`/`remove_bot`/`rename_player`/`move_place` at the `handle()` call site, NOT inside the helper). Then in `api_complete_theft` and the play_card route: on success, call `_append_event_log(game_id, result)` and `_flush_steal_alerts(game_id)` before returning (complete_theft already flushes — verify, don't double).

- [ ] **Step 3: Run + commit**

```bash
.venv/bin/python -m unittest tests.test_steal_alerts -v 2>&1 | tail -3
git add survivor_server.py tests/test_steal_alerts.py
git commit -m "A raid that meets a Sorry For You still makes the history books"
```

### Task S2: The blocked-raid toast names who owes the penalty

**Finding #2 (the 45-second freeze).** The deadline stays 45s — that is deliberate grace, and the iOS overlay is blocking for the ower. What's missing is the TABLE knowing why nothing moves. The `raid_blocked` alert message currently reads "X played Sorry For You — the raid fails"; when raiders owe a chosen discard, extend it.

**Files:**
- Modify: `rules_engine.py` — `_effect_sorry_for_you`'s alert append (tabs)
- Test: `tests/test_steal_alerts.py` (`SorryForYouRecordsABlockedRaidTest` — extend)

- [ ] Implement: when the effect's `awaiting` list is non-empty, the alert's `message` gains `" — {names} must choose a card to give up"` (names joined with " and "). Test asserts the suffix appears when the thief has a real choice and is absent when the discard was automatic.
- [ ] Commit: `git commit -m "The blocked-raid toast says who the table is waiting on"`

### Task S3: The e2e harness answers the discard window

**Finding #2's test half:** `tests/e2e/e2e_api_live_test.py`'s `_wait_for_human_turn`/`_answer_the_island` (~line 810) auto-answers theft windows, interactions and challenges but not `pending_discards`, losing a 45s-vs-45s race intermittently.

- [ ] Implement: in the same polling helper, when `state["pending_discards"]` has the human in `awaiting`, pick their first takeable card index and POST `/api/reactive/choose_discard` (`{gameId, playerId, cardIdx}` — grep the route for exact params). Mirror how the helper already answers the theft window.
- [ ] Verify: run `SURVIVOR_TEST_BASE=... tests/e2e/e2e_api_live_test.py` against a scratch server **5 times**; all must pass (the failure was a ~1-in-3 coin flip, 5 clean runs is meaningful).
- [ ] Commit: `git commit -m "The e2e human pays the Sorry For You penalty instead of freezing"`

### Task S4: Leaving a lobby, and start_full says why not

**Findings #5 and #9.**

**Files:**
- Modify: `survivor_server.py`
- Test: `tests/test_gamestate_units.py` or the join/cap test home (grep `"Game is full"` in tests/)

- [ ] **Leave API**: new method `leave_game(self, gid, playerId=None, **kwargs)` + route `POST /api/player/leave` — lobby-phase ONLY (`game["phase"] == "lobby"`, else refuse "The game has started — a torch can't just walk away"), removes the player dict entirely (their seat frees automatically since seats derive from live players), removes them from `turnOrder` if present, `_save`, returns a message naming who left. The route requires `playerId` (self-leave — the trust model everywhere is claimed playerId, this is consistent). Emit the state update the way other lobby mutations do (route through `handle()` if the action map allows — check how `add_bot` routes; prefer `handle('leave_game', ['playerId'])` so eventLog and broadcasts come free).
- [ ] **start_full reasons**: find the flat `"Game cannot be started."` and split it: not found / already started (name the phase) / fewer than 3 players (name the count). Tests for each refusal.
- [ ] Tests: leave in lobby succeeds and frees the seat for a new join; leave after start refused; leave of unknown player refused.
- [ ] Commit: `git commit -m "A castaway can leave an unlit lobby, and starting says why it can't"`

---

## Part I — iOS (files under `ios/` only)

### Task I1: The toast clears the FIRE pill

**Finding #6:** the narration toast overlaps the FIRE/day counter (4 screenshots, reproducible). Read `ToastView.swift`'s `NarrationHost` placement and the top-bar layout it floats over (find the FIRE pill's view — grep "FIRE"). Give the toast the inset or alignment that clears the top-bar row entirely (below it, or leading-aligned after it) — whatever reads most naturally with the file's existing layout idiom. Verify by re-running `VisualAuditUITests/testNarrationToastClearsTheNavigationBar` against a scratch server AND reading the PNG — the assertion alone provably misses this.

### Task I2: Monograms stop colliding

**Finding #7:** Coconut and Cornelius both render "CO". Find the monogram derivation (grep `prefix(2)` / monogram in the player chip/strip views). New rule, derived deterministically from the alive roster so every phone agrees: default = first 2 characters; if another player's name shares them (case-insensitive), use first character + first differing character (Coconut→"CC", Cornelius→"CR"); a full-prefix name ("Co" vs "Cor") keeps default. Unit-test the derivation with the QA ally names (Christopher/Coconut/Cleo/Cornelius/Cassidy/Clementine/Casper — note Christopher/Cleo/Clementine also collide on "C" variants; assert every alive player's monogram is unique for that roster, or document which pairs legitimately can't be).

### Task I3: The reveal's bars tell the truth

**Finding #8:** an immune player's uncounted 3-vote bar draws longer than the eliminated player's real 1-vote bar. In `VoteRevealView`/`VoteResultRow`: scale every row's bar against the maximum count across ALL displayed rows (counted and immune together), keeping the immune row's dimmed styling. The eliminated player's bar may still be shorter when they truly got fewer votes — the fix is honest proportionality, not "eliminated always longest". Unit-test the scaling math if it lives in the view model; otherwise re-shoot `testTheRevealShowsAnImmunePlayersUncountedVotes` and eyeball.

### Task I4: Leave the lobby from the phone

**Finding #5's iOS half.** In the lobby screen: a "Leave game" affordance (secondary/destructive styling per Torch idiom, confirmation dialog — leaving is semi-destructive) calling the new `POST /api/player/leave` via APIClient/GameClient (add the method following `completeTheft`'s shape), then returning to the start screen. Old-server tolerance: a 404/refusal surfaces through the existing error-alert path.

Run the full unit suite + affected visual tests. One commit per task, plan-style messages, trailers as usual.

---

## Part W — Web (files under `client/dist` only)

### Task W1: Light the Fire lights one fire

**Finding #3:** every click created a game; first click showed no form. Read the button's handler in `ui.js`/`game.js` — separate "reveal the create form" from "create the game": the first interaction reveals/toggles the form only; creation happens on an explicit submit; an in-flight guard (`disabled` + flag) prevents double-creates; failure re-enables. Verify by reading the flow end-to-end after the change — count `/api/game/create` calls per UI path.

### Task W2: The phone can't scroll into the void

**Finding #4:** the closed Story drawer (`position:fixed; transform:translateX(350px)`) still widens the document. Fix with the smallest correct CSS: `overflow-x: clip` on the drawer's containing scope (html/body) OR toggle `visibility: hidden` when closed (transition-safe — keep the slide animation working). `client/dist/styles.css` is in scope for this. Verify via the same measurement the QA agent used: `document.documentElement.scrollWidth === window.innerWidth` at 390px, drawer closed AND open.

### Task W3: Console quiet before the gate, and honest controls

**Findings #10, #11, #12:**
- Pre-auth: `loadCardDefinitions` (game.js:53) 401s loudly on every gated visit. Gate it: check `/api/access/check` first (or catch the 401 silently and retry after unlock) — no console.error for the expected-gated case; real failures still log.
- Reconnect toast: dedupe — one "Reconnected to game!" per reconnect cycle (guard flag cleared on disconnect).
- Add-bot button: disable (with the same visual treatment other disabled buttons get) when the lobby holds `MAX_PLAYERS` (read the player count from state; the server's refusal stays the backstop).

### Task W4: Web reveal bars + leave the lobby

- **Finding #8's web half:** in `renderVoteResults`, scale all bars (counted + immune) against the max count across displayed rows — replaces the `Math.min(100, ...)` clamp band-aid for immune rows with honest proportions.
- **Finding #5's web half:** a "Leave game" control in the lobby calling `POST /api/player/leave` (add to `network.js` beside `completeTheft`), returning to the start screen on success.

`node --check` every touched JS file. One commit per task or one for all four — agent's judgment, plan-style messages, trailers.

---

## Part D — Integration (dispatcher)

- [ ] Full Python suite (36 suites) + 5× e2e_api_live_test runs (the S3 flake-fix proof) + scripted games once.
- [ ] Full iOS unit + UI suites against a scratch server; READ the re-shot toast/reveal/camp PNGs — three of these fixes are pixel-level and only eyes verify them.
- [ ] Browser spot-check of W1/W2 (create-once, no sideways scroll) via Playwright.
- [ ] Deploy, health check, push. iOS changes ride the next TestFlight build — flag it.

## Coordination

- Three parallel agents: S (Python: S1→S4 sequential), I (iOS), W (web) — file-disjoint, one worktree, `git add` by explicit path only.
- S1's eventLog helper extraction must not change `handle()`'s observable behavior — the narrator/history tests pin it; run `tests.test_narrator_events` after S1.
- Off limits, as always: the tie-break cascade, deck builder, steal engine internals. `PENALTY_DISCARD_SECONDS` stays 45.0 — the fix is visibility and the harness, not the grace period.
