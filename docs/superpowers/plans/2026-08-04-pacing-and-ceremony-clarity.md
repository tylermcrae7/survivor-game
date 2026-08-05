# Pacing & Ceremony Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The game slows down enough to follow (bots and toasts), the council says out loud whether one torch or two go out tonight, and an Inheritance firing is announced instead of happening silently.

**Architecture:** Server-side, one constant (bot base delay) sets the whole tempo — ceremonies scale from it automatically — and `process_elimination_inheritance` records a `_pending_alerts` entry the existing flush pipeline toasts. Client-side, `NarrationFeed` gains a length-aware dwell, and the tribal screens read the `currentVote.type` field both clients already decode (or receive) and ignore.

**Tech Stack:** Python 3 (unittest, `.venv/bin/python`), SwiftUI iOS 17+ (Swift Testing), legacy web bundle `client/dist`.

**Payload contracts (fixed by this plan):**
- New narrator event `inheritance`, data: `{heirId, heir, deadId, dead, count, seatLabel, message}` — message like `"Mango inherits Coconut's 2 cards — Inheritance (Red) is spent"`.
- `currentVote.type` is `"single" | "double"` (already on the wire from `survivor_server.py:1865`); `currentVote.eliminationsNeeded` is 1 or 2.

**Investigation results this plan rests on (do not re-derive):** bots were NOT over-stealing (a finished game's log shows every steal moved exactly one card); Inheritance already auto-fires correctly on elimination (`rules_engine.py:2231-2305`, tests in `tests/test_inheritance.py`) — it is merely silent.

---

## Part A — Python server

### Task A1: The island breathes slower

**Files:**
- Modify: `bots.py:629` (BASE_DELAY default)
- Test: `tests/test_bots.py` (only if an assertion pins the old default — check first)

- [ ] **Step 1: Check what the tests assume**

Run: `grep -rn "SURVIVOR_BOT_DELAY\|BASE_DELAY\|1\.6" tests/ bots.py | head -20`
Tests that set `SURVIVOR_BOT_DELAY=0` (the zero-collapse test env) are unaffected. If any test asserts a literal window value derived from the 1.6 default, update it to derive from `bots.BASE_DELAY` instead of the literal.

- [ ] **Step 2: Implement**

`bots.py:629`: change the fallback `"1.6"` to `"2.4"`, and extend the comment: the default gap between bot actions becomes ~1.7–3.1s (jitter 0.7–1.3), and every ceremony window in `_windows` scales by `base/1.6` — so one number slows the whole show together. The `SURVIVOR_BOT_DELAY` env override and the per-game `botPace` dial (chill/normal/fast) keep working unchanged on top of it.

- [ ] **Step 3: Run the bot suite**

Run: `.venv/bin/python tests/test_bots.py 2>&1 | tail -3`
Expected: exits clean.

- [ ] **Step 4: Commit**

```bash
git add bots.py tests/test_bots.py
git commit -m "The island breathes slower: bots act every 2.4s, ceremonies stretch with them"
```

### Task A2: An Inheritance announces itself

**Files:**
- Modify: `rules_engine.py` — `process_elimination_inheritance` (~line 2284, where the card fires)
- Modify: `survivor_server.py` — `complete_tribal` (~line 1630, where `inheritance_results` returns)
- Test: extend `tests/test_inheritance.py`

The transfer already works; nobody is told. Two mouths: a `_pending_alerts` entry (toast on every phone via the existing flush pipeline — `complete_tribal` runs through `handle()`/the bot runner, both of which flush) and the council-completed message carrying the inheritance line into the eventLog.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_inheritance.py`, matching its existing fixtures — read the neighboring tests first)

```python
class InheritanceAnnouncesItselfTest(unittest.TestCase):
    """The transfer was silent; the table deserves to hear the will read."""

    def test_a_firing_inheritance_records_an_alert(self):
        # Build the same fixture InheritanceEstateTest uses: an eliminated
        # red-seat player with a two-card estate, and a living heir holding
        # inheritance_red. Then:
        engine.process_elimination_inheritance(game, dead_id)
        alerts = [a for a in game.get("_pending_alerts", [])
                  if a["event"] == "inheritance"]
        self.assertEqual(len(alerts), 1)
        data = alerts[0]["data"]
        self.assertEqual(data["count"], 2)
        self.assertIn("inherits", data["message"])
        self.assertIn("Inheritance (Red) is spent", data["message"])

    def test_an_inheritance_that_does_not_fire_stays_quiet(self):
        # Nobody holds the matching colour: no alert.
        engine.process_elimination_inheritance(game, dead_id)
        self.assertFalse([a for a in game.get("_pending_alerts", [])
                          if a["event"] == "inheritance"])

    def test_the_council_summary_reads_the_will(self):
        # End-to-end через complete_tribal (mirror the existing end-to-end
        # test at ~line 216): the returned message/log_message must contain
        # the "inherited" line so the eventLog keeps it.
        self.assertIn("inherit", result.get("message", "").lower())
```

(These are shapes — bind them to the file's real fixture helpers; the existing `InheritanceEstateTest` setUp builds exactly the players needed.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python tests/test_inheritance.py 2>&1 | tail -3`
Expected: new tests FAIL (no alerts recorded, summary lacks the line).

- [ ] **Step 3: Implement** (tabs in `rules_engine.py`)

In `process_elimination_inheritance`, at the point the card fires (after the estate moves and the card is discarded, ~line 2300), append — using `seats` (already imported there) for the label:

```python
			seat_label = next((label for key, label, _ in seats.SEATS if key == seat), seat)
			heir_name = holder.get("name", "?")
			dead_name = eliminated_player.get("name", "?")
			cards = "1 card" if count == 1 else f"{count} cards"
			game.setdefault("_pending_alerts", []).append({
				"event": "inheritance",
				"data": {
					"heirId": holder_id, "heir": heir_name,
					"deadId": eliminated_id, "dead": dead_name,
					"count": count, "seatLabel": seat_label,
					"message": f"{heir_name} inherits {dead_name}'s {cards} — "
					           f"Inheritance ({seat_label}) is spent",
				},
			})
```

(Adapt variable names to the function's real locals — the count is the estate size it just moved; check how `seats.SEATS` tuples are shaped at `seats.py:25-32` and use the label accessor the module actually provides.)

In `survivor_server.py` `complete_tribal`: the summary message built after the elimination loop (the "Tribal council completed - N voted out..." string) gains the inheritance lines when `inheritance_results` is non-empty — append `"; " + "; ".join(inheritance_results)` to both the message and any `log_message` twin, so the eventLog and every history panel keep the will-reading. (Read how `inheritance_results` is accumulated at ~1630 — it already collects human-readable strings like "Mango inherited 2 cards from Coconut".)

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python tests/test_inheritance.py 2>&1 | tail -3` then `.venv/bin/python run_all_tests.py 2>&1 | grep -E "^Passed|^Failed"`
Expected: inheritance file green; full run `Failed: 0`.

- [ ] **Step 5: Commit**

```bash
git add rules_engine.py survivor_server.py tests/test_inheritance.py
git commit -m "An Inheritance reads the will aloud instead of firing in silence"
```

---

## Part B — iOS (all files under `ios/SurvivorGame`)

### Task B1: Toasts stay up long enough to read

**Files:**
- Modify: `ios/SurvivorGame/State/NarrationFeed.swift` (dwell/gap at ~line 29, drain at ~74-88)
- Test: the feed's existing test file (`grep -rn "NarrationFeed" ios/SurvivorGameTests/`) — extend

- [ ] **Step 1: Implement a length-aware dwell**

Replace the fixed `dwell` with a floor: rename the init param to `minDwell` defaulting to `.milliseconds(2400)`, `gap` to `.milliseconds(350)`, and compute per-event:

```swift
    /// Long enough to actually read: a floor for short lines, ~60ms per
    /// character for longer ones, capped so a wordy event can't dam the queue.
    private func dwell(for event: NarrationEvent) -> Duration {
        let byLength = Duration.milliseconds(event.message.count * 60)
        return max(minDwell, min(byLength, .milliseconds(4200)))
    }
```

Use it in `drain()` in place of the constant. Keep the initializer's parameters injectable so the existing tests (which likely pass tiny dwells to run fast) keep working — read the test file first and preserve its construction pattern.

- [ ] **Step 2: Unit tests** — extend the feed's tests: a 10-character message dwells `minDwell`; a 60-character message dwells 3600ms; a 200-character message caps at 4200ms. Test the `dwell(for:)` math directly if it needs to be made internal for testability (match the file's existing access-control idiom).

- [ ] **Step 3: Build + tests, commit**

```bash
git add ios/SurvivorGame/State/NarrationFeed.swift ios/SurvivorGameTests/
git commit -m "iOS: a toast stays up long enough to be read"
```

### Task B2: The council says how many torches go out

**Files:**
- Modify: `ios/SurvivorGame/Views/Tribal/TribalScreen.swift` (header block ~108-120, AnnouncementPhase ~195-228)
- Test: extend `ios/SurvivorGameUITests/VisualAuditUITests.swift` (one staged visual test)

`TribalVoteState.type` is already decoded (`TribalVoteState.swift:4`) and never read. Two mouths:

- [ ] **Step 1: Announcement line** — in `AnnouncementPhase`, after `CeremonyTitle(text: "Tribal Council")` (~line 207), replace/augment the static flavor line with one that answers the question: `"One torch goes out tonight."` for single, `"TWO torches go out tonight."` for double (double styled in `Torch.Color.ember` or the file's warning tone; match the existing flavor-line typography).

- [ ] **Step 2: Persistent badge** — near the `PhaseProgressView` header block (~117-120), when `voteState?.type == "double"`, render a compact capsule chip reading `DOUBLE ELIMINATION` (mirror an existing chip pattern — the IMMUNE capsule from `VoteRevealView` or `CampChip`) so the fact stays visible through Advantage/Talk/Vote/Idols/Reveal, not just the announcement. Singles get no chip — the announcement line already said it, and single is the norm.

- [ ] **Step 3: Visual UI test** — append to `VisualAuditUITests` (mirror `testBallotShowsTorchesIncludingTheLastOne`'s staging exactly — including `playerId` on any Leader-only call): stack `["tribal_council_double"]`, steal+draw to open the council, assert `"TWO torches go out tonight."` exists and the `DOUBLE ELIMINATION` chip exists, `shot("17-double-elimination-banner")`. Requires the scratch server on :8099 with `SURVIVOR_TEST_HOOKS=1` — if it is not running, the test self-skips; note that in your report rather than fighting it.

- [ ] **Step 4: Build + unit tests, commit**

```bash
git add ios/SurvivorGame/Views/Tribal/TribalScreen.swift ios/SurvivorGameUITests/VisualAuditUITests.swift
git commit -m "iOS: the council says whether one torch or two go out tonight"
```

### Task B3: The inheritance toast

**Files:**
- Modify: `ios/SurvivorGame/Models/NarrationEvent.swift`
- Test: extend `ios/SurvivorGameTests/NarrationEventTests.swift`

- [ ] **Step 1: Implement** — add an `inheritance` case following exactly the pattern `raidBlocked` used (associated values from the payload contract above; message required, event dropped without it). Priority: critical (it belongs to the elimination moment and must not be evicted by chatter); cue: reuse the most fitting existing cue (read what elimination uses).

- [ ] **Step 2: Tests** — mirror the `raidBlocked` tests: happy path uses the server's message verbatim; missing message drops the event; priority is critical.

- [ ] **Step 3: Build + tests, commit**

```bash
git add ios/SurvivorGame/Models/NarrationEvent.swift ios/SurvivorGameTests/NarrationEventTests.swift
git commit -m "iOS: the will is read aloud — inheritance toasts as part of the elimination"
```

---

## Part C — Web client (`client/dist` only)

### Task C1: The ceremony says it on the web too

**Files:**
- Modify: `client/dist/ui.js` (`renderTribalCeremony` ~2617-2675), `client/dist/index-optimized.html` (announcement ceremony block ~459-463)

- [ ] **Step 1:** In the announcement screen's `.ceremony` block, add an element `#ceremonyEliminationLine`; `renderTribalCeremony` sets its text from `currentVote.type`: `"One torch goes out tonight."` / `"TWO torches go out tonight."` (style it like the existing `.ceremony-line`; for double add a class or inline color matching the site's warning/ember tone already used elsewhere in ui.js — grep for how existing warning text is colored, stay inline-or-existing-class per the constraint).
- [ ] **Step 2:** For double only, append `" · Double Elimination"` to the `.eyebrow` text of the advantage/discussion/voting screens inside `renderTribalCeremony` so the fact survives past the announcement.
- [ ] **Step 3:** `node --check client/dist/ui.js`, eyeball `git diff`, commit:

```bash
git add client/dist/ui.js client/dist/index-optimized.html
git commit -m "Web: the ceremony says whether one torch or two go out tonight"
```

---

## Coordination notes for the dispatcher

- Parts A, B, C are file-disjoint; run as three parallel subagents in ONE worktree. Each commits only its own files; no `git commit -a`.
- Part A must run `run_all_tests.py` at the end (35 suites; the known `test_edge_cases` internal 23/24 is pre-existing).
- The dispatcher owns: review, full suites, the double-elimination visual test against the scratch server (`SURVIVOR_ACCESS_CODE=torchtest2468 SURVIVOR_TEST_HOOKS=1 PORT=8099`, run from a scratch dir), inheritance-toast live verification, deploy, push, report.
- No change addresses "bots steal more than one card" — investigated and disproven; the report explains it as a pacing perception.
