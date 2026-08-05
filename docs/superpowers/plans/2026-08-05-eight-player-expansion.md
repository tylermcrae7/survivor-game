# Eight-Player Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The game seats 7 and 8 players without losing any of the math that makes it work: the elimination ledger, the +2 flip margin, the pacing of councils through the Draw Pile, seat-bound identity, and the official tie-breaker cascade.

**Architecture:** Player count already flows through every subsystem — the work is extending the tables that are enumerated (tribal config, seats, card catalogue) and un-hard-coding the two `>= 6` caps, then pinning the N-agnostic systems (tie-breakers, ladder, jury) with 8-player tests so they stay that way. Deck depth is restored at 7–8 players with a deterministic "supply pack" of duplicated common cards, never scarce power cards.

**Tech Stack:** Python 3 (unittest, `.venv/bin/python`), SwiftUI iOS 17+ (Swift Testing), web bundle `client/dist`. Tabs in `rules_engine.py`; 4 spaces elsewhere.

---

## The invariants this plan must preserve (verified against current code)

1. **The elimination ledger.** Every player holds 2 Survivor Character Cards; the game ends at 2 alive; tribal cards must supply `2×(N−2) + 2` flips — the official table holds this at every count 3–6 with the margin of exactly **+2** (absorbs idol saves). Extension: **7 players → 6 doubles (12 flips, 10 needed); 8 players → 7 doubles (14 flips, 12 needed)** — all doubles, following the official trend (6p is already all-doubles).
2. **Pacing.** 3 cards dealt each; tribal cards spaced evenly with one at the bottom (final council guaranteed). At 6p each player gets ~6.5 turns. Restoring that at 7–8 requires a bigger action pile: target `action_total(N) = ceil(6.5×N) + 3N − tribal_count(N)` → **61 total action cards at 7p, 69 at 8p** (official base is 52). The gap is filled by the supply pack (Task A3). At 3–6 players the deck must remain **bit-for-bit the official composition** — the composition tests already pin this.
3. **Identity.** One seat per player, exact-hex matching (no heuristics — see `seats.py` module docstring for why), one Inheritance card per seat. Two new seats need two new Inheritance cards, which must NOT enter 3–6 player decks (composition pin).
4. **The tie-breaker cascade** (`resolve_tribal_eliminations`, `elimination_ladder`, `_apply_three_left_rule`, `tie_break`, final-tribal jury tie). Verified N-agnostic by reading: every branch works off `alive`/`counts`/`needed`, k-way ties are generic, the three-left rule keys on `len(alive) == 3`, `tie_break` accepts `chosenIds` for pick-2-of-k, and the jury tie has `tieBreakNeeded`/`tiedFinalists` with the Leader breaking it. **No logic changes** — but 8 players makes multi-way ties and ladder trips far more frequent, so Part B pins the cascade with an 8-player battery before anything ships.
5. **The known landmine:** `_create_tribal_council_cards` falls back to `{"single": 2, "double": 2}` for any count not in its table — an 8-player game today would silently get the 4-player set (6 flips vs 12 needed) and limp along on the emergency discard reshuffle. Task A1 removes the silent default.

---

## Part A — Server math (Python)

### Task A0: Grant Immunity leaves the island

Tyler's ruling: "That's not how we play. The other 6 can stay." The extended house set shrinks from 7 cards to 6 (`idol_nullifier` ×2, `steal_vote` ×2, `block_vote` ×2); `grant_immunity` ×1 is removed everywhere a new deck is born, and healed out of games already in flight.

**Files:**
- Modify: `survivor_cards.json` (delete the `grant_immunity` definition; fix the `validation` totals AND the prose comment at ~line 11 that says "7 cards total")
- Modify: `rules_engine.py` (`NON_OFFICIAL_CARD_TYPES` set and its "These 7" comment; the `grant_immunity` entry in the effects registry and any validation branch; new heal)
- Modify: `survivor_server.py` (call the heal where the other heals run — find `ensure_card_uids` / `ensure_seat_bound_inheritance` call sites in the load path, ~line 342)
- Modify: `bots.py` ONLY if it names `grant_immunity` (grep; remove dead references — value tables, advantage-play picks)
- Test: `tests/test_deck_composition.py`, a heal test beside the other heal tests (grep `ensure_seat_bound_inheritance` in tests/ for the pattern's home)

- [ ] **Step 1: Write the failing tests**

```python
    def test_grant_immunity_is_gone_from_every_new_deck(self):
        for mode in ("official", "extended"):
            deck = self.engine.create_action_deck(deck_mode=mode)
            self.assertNotIn("grant_immunity", [c["type"] for c in deck])

    def test_extended_mode_adds_exactly_six_house_cards(self):
        official = len(self.engine.create_action_deck(deck_mode="official"))
        extended = len(self.engine.create_action_deck(deck_mode="extended"))
        self.assertEqual(extended - official, 6)
```

And the heal (mirroring the `ensure_seat_bound_inheritance` test file's fixtures):

```python
class GrantImmunityHealsAwayTest(unittest.TestCase):
    def test_saved_games_lose_the_card_on_load(self):
        """A game saved under the old rules holds the card in a hand, the
        deck and the discard; the heal removes all three, idempotently."""
        game = ...  # hands: one grant_immunity among others; deck+discard seeded too
        removed = ensure_no_grant_immunity(game)
        self.assertEqual(removed, 3)
        self.assertEqual(ensure_no_grant_immunity(game), 0)   # idempotent
        # and nothing else was touched
```

- [ ] **Step 2: Run to verify failure** (`.venv/bin/python tests/test_deck_composition.py`)

- [ ] **Step 3: Implement**

1. Delete the `grant_immunity` block from `survivor_cards.json`; reduce the validation totals by 1 (read the `validation` section and the loader check at `rules_engine.py:429-450` — a mismatch makes every boot fall back to the empty card set, which is the failure mode to fear here); fix the ~line 11 comment to name the 3 remaining house types, "6 cards total."
2. `rules_engine.py`: drop `"grant_immunity"` from `NON_OFFICIAL_CARD_TYPES` (comment: "These 6"); remove its effects-registry line and its `_effect_grant_immunity` handler; grep `grant_immunity` across `rules_engine.py`/`survivor_server.py` for validation branches that name it and remove them. **Keep the `temporaryImmunity` player-flag checks in `reveal_votes`** — the flag machinery stays (it is generic protection plumbing and history contains games that used it); only the card that set it goes.
3. New heal, following `ensure_card_uids`'s shape exactly (module-level in `rules_engine.py`, walks `_iter_game_cards`... note: that iterator YIELDS cards but the heal must REMOVE them, so filter each container in place instead — hands, `deck`, `discard` — return the count removed, idempotent). Call it in the server load path beside `ensure_seat_bound_inheritance`.
4. `bots.py`: remove dead references if the grep finds any.
5. `grep -rn "grant_immunity" tests/` — every test that plays or stages the card gets updated or removed WITH its reason recorded in the report (a test of the card's effect dies with the card; a test that merely used it as a prop gets a different prop).

**Clients:** deliberately untouched. Both clients tolerate unknown/absent card types, and their catalogue entries for `grant_immunity` become vestigial rather than harmful — removing them is cosmetic and can ride any later build.

- [ ] **Step 4: Run deck + heal + full suite, commit**

```bash
git add survivor_cards.json rules_engine.py survivor_server.py bots.py tests/
git commit -m "Grant Immunity leaves the island — the house plays 6 extra cards, not 7"
```

### Task A1: The tribal table learns 7 and 8, and stops guessing

**Files:**
- Modify: `rules_engine.py` — `_create_tribal_council_cards` (the `tribal_config` dict and its `.get(..., default)`)
- Test: `tests/test_deck_composition.py` (`test_comprehensive_player_count_matrix` ~line 233, the per-count tests ~58-72, `test_invalid_player_counts` ~189)

- [ ] **Step 1: Extend the matrix test first**

In `test_comprehensive_player_count_matrix`, extend `expectations`:

```python
        expectations = [
            (3, 4, 0, 4),  # 3 players: 4 single, 0 double, 4 total
            (4, 2, 2, 4),
            (5, 2, 3, 5),
            (6, 0, 5, 5),
            (7, 0, 6, 6),  # extension: all doubles, 12 flips = 2(7-2)+2
            (8, 0, 7, 7),  # extension: all doubles, 14 flips = 2(8-2)+2
        ]
```

Add the ledger invariant as its own test in the same class:

```python
    def test_flip_supply_always_exceeds_need_by_exactly_two(self):
        """2 lives × (N-2) players out, +2 spare flips for idol saves —
        the margin the official table keeps at every count."""
        for n in range(3, 9):
            with self.subTest(players=n):
                cards = self.engine._create_tribal_council_cards(n)
                flips = sum(2 if c["elimination_type"] == "double" else 1
                            for c in cards)
                self.assertEqual(flips, 2 * (n - 2) + 2)
```

Add per-count tests `test_deck_composition_7_players` / `_8_players` mirroring the existing four (they call `_test_player_count_deck_composition(n)` — that helper asserts totals; it will need the Task A3 numbers, so write these two AFTER reading the helper and wire in the 7/8 expected totals from Task A3's table).

Update `test_invalid_player_counts`: counts outside 3–8 must now raise or be refused loudly — assert the new behavior from Step 3, not the old silent default.

- [ ] **Step 2: Run to see the new rows fail**

Run: `.venv/bin/python tests/test_deck_composition.py 2>&1 | tail -5`

- [ ] **Step 3: Implement** (tabs)

```python
		tribal_config = {
		3: {"single": 4, "double": 0},
		4: {"single": 2, "double": 2},
		5: {"single": 2, "double": 3},
		6: {"single": 0, "double": 5},
		7: {"single": 0, "double": 6},
		8: {"single": 0, "double": 7},
		}

		config = tribal_config.get(player_count)
		if config is None:
			# The old fallback quietly dealt the 4-player set — an 8-player
			# game got 6 flips against the 12 it needed and survived only on
			# the emergency reshuffle. Out-of-range is a caller bug: say so.
			raise ValueError(
				f"No tribal council configuration for {player_count} players "
				f"(supported: 3-8)")
```

Check every caller of `_create_tribal_council_cards`/`assemble_deck` handles the raise (game creation validates count first — Task A4 puts the cap there, so the raise is a backstop, not a user-facing path).

- [ ] **Step 4: Run deck tests + full suite, commit**

```bash
git add rules_engine.py tests/test_deck_composition.py
git commit -m "Tribal cards for 7 and 8 players, and no more silent 4-player default"
```

### Task A2: Two new seats at the fire

**Files:**
- Modify: `seats.py` (SEATS tuple)
- Modify: `survivor_cards.json` (two new Inheritance definitions + validation totals)
- Test: `tests/test_seats.py`, `tests/test_inheritance.py`

- [ ] **Step 1: Choose the hexes so nothing collides.** New seats:

```python
    {"key": "purple", "label": "Purple", "hex": "#9B5DE5"},
    {"key": "pink",   "label": "Pink",   "hex": "#F06595"},
```

Constraints checked here, assert them in tests: neither hex equals any existing seat hex NOR any key in `_ALIASES` (`#DDA0DD` plum already aliases to **red** — the new purple must not be `#DDA0DD`, and the alias must keep winning for old clients that send it). Append to `SEATS` only — order is identity for nothing, but append anyway; `SEAT_KEYS`/`SEAT_HEX`/`SEAT_LABELS`/`_BY_HEX` derive automatically.

- [ ] **Step 2: New Inheritance cards** — in `survivor_cards.json`, add `inheritance_purple` and `inheritance_pink` mirroring `inheritance_red` word-for-word (colour substituted, `"seat"` key, `"count": 1`, `"playable_phases": []`). Then fix the validation block: `total_expected_cards` and `extended_deck_cards` each grow by 2 (read the validation section and the loader's count check at `rules_engine.py:429-450` first — the totals must match or every server boot falls back to the empty card set).

**CRITICAL COMPOSITION RULE:** these two cards must NOT appear in 3–6 player decks (the official 67-card box is pinned by tests and by the physical game). Task A3's deck builder gains the filter; this task just defines the cards. Until A3 lands, the composition tests will catch the leak — implement A2 and A3 in the same session, A3 immediately after.

- [ ] **Step 3: Tests** — `tests/test_seats.py`: roster has 8 seats, keys unique, hexes unique, no new hex appears in `_ALIASES`, `seat_of` round-trips a purple/pink player. `tests/test_inheritance.py`: an 8-player game where the purple player is eliminated and the pink player holds `inheritance_purple` → estate transfers, card spent (mirror the existing red test).

- [ ] **Step 4: Commit**

```bash
git add seats.py survivor_cards.json tests/test_seats.py tests/test_inheritance.py
git commit -m "Purple and Pink join the fire, each with an Inheritance of their own"
```

### Task A3: The deck grows with the table

**Files:**
- Modify: `rules_engine.py` — `create_action_deck` (player-count awareness + supply pack + inheritance filter)
- Test: `tests/test_deck_composition.py`

The pile must give 7–8 player games the same ~6.5 turns per player that 6 gets, without touching the 3–6 composition and without duplicating scarce power.

- [ ] **Step 1: The numbers.** Base action deck (official, no expansion): 52 cards. Targets: `action_total(7) = 61`, `action_total(8) = 69` — derived from `ceil(6.5×N) + 3N − tribal_count(N)`; the 6-player instance of the same formula reproduces exactly 52, which is the sanity check that the formula captures the official pacing. The supply pack fills the gap between the assembled base (52 official; +6 extended after Task A0; +4 digital expansion; +2 new-seat Inheritance at 7–8p) and the target — the pack is computed as `target − base`, so it self-adjusts to whatever mode the game chose.

- [ ] **Step 2: Write the failing tests**

```python
    def test_seven_and_eight_player_decks_hit_the_pacing_target(self):
        for n, target in ((7, 61), (8, 69)):
            with self.subTest(players=n):
                deck = self.engine.create_action_deck(player_count=n)
                self.assertEqual(len(deck), target)

    def test_three_to_six_player_decks_are_untouched(self):
        """The official 52-card pile, bit for bit — no new-seat Inheritance,
        no supply pack, exactly what the box prints."""
        for n in range(3, 7):
            with self.subTest(players=n):
                deck = self.engine.create_action_deck(player_count=n)
                types = [c["type"] for c in deck]
                self.assertEqual(len(deck), 52)
                self.assertNotIn("inheritance_purple", types)
                self.assertNotIn("inheritance_pink", types)

    def test_the_supply_pack_never_duplicates_power(self):
        deck = self.engine.create_action_deck(player_count=8)
        from collections import Counter
        counts = Counter(c["type"] for c in deck)
        base = {t: d.get("count", 0)
                for t, d in self.engine.card_definitions["cards"].items()}
        for scarce in ("immunity_idol", "inheritance_red", "inheritance_purple",
                       "sorry_for_you"):
            self.assertLessEqual(counts.get(scarce, 0), base.get(scarce, 1),
                                 f"{scarce} must stay as scarce as the box made it")

    def test_the_supply_pack_is_deterministic(self):
        a = sorted(c["type"] for c in self.engine.create_action_deck(player_count=8))
        b = sorted(c["type"] for c in self.engine.create_action_deck(player_count=8))
        self.assertEqual(a, b, "same table, same composition — only the shuffle varies")
```

(Adapt the `create_action_deck` signature call to Step 3's design; existing callers pass no `player_count`, so it must default to preserving today's behavior.)

- [ ] **Step 3: Implement** (tabs). `create_action_deck(self, deck_mode="official", expansion=False, player_count=None)`:

1. Build the base exactly as today, with one new filter: `inheritance_purple`/`inheritance_pink` are skipped unless `player_count and player_count >= 7`.
2. After the base, if `player_count and player_count >= 7`, compute the target from the formula above (`tribal_count` from the Task A1 table) and top up with the **supply pack**: candidate types are every action card in the current mode EXCEPT a scarce-list (`immunity_idol`, every `inheritance_*`, `sorry_for_you`, plus `idol_nullifier` in extended — one-and-two-copy power stays at box count); add one extra copy per candidate in descending box-count order (commonest first), cycling until the target is met. Deterministic: sort by `(-count, type)` — no RNG before the final shuffle.
3. Thread `player_count` through `create_game_deck`/`assemble_deck` callers (read `survivor_server.py:590-610` `start_full` — it knows the player count; pass it).

- [ ] **Step 4: Run the full deck + composition suites, commit**

```bash
git add rules_engine.py survivor_server.py tests/test_deck_composition.py
git commit -m "The deck grows with the table: 7 and 8 players keep the official pacing"
```

### Task A4: The caps move to 8

**Files:**
- Modify: `survivor_server.py:456-459` and `survivor_server.py:2425-2426` (the two `>= 6` guards)
- Test: `tests/test_gamestate_units.py` (or wherever join caps are pinned — grep `"Game is full"` in tests/)

- [ ] **Step 1:** Extract one constant near the top of `survivor_server.py`: `MAX_PLAYERS = 8`, use it at both sites, message: `f"Game is full — maximum {MAX_PLAYERS} players."` Grep for any other literal 6 that means the cap: `grep -n "maximum 6\|>= 6\|> 5" survivor_server.py bots.py` and audit each hit (most 6s are unrelated).
- [ ] **Step 2:** Tests: a 7th and 8th join succeed, a 9th is refused. Bots: `add_bot` fills to 8.
- [ ] **Step 3:** Commit

```bash
git add survivor_server.py tests/
git commit -m "Eight seats at the fire"
```

### Task A5: The rocks scale where the Guide says they scale

**Files:**
- Modify: `challenges.py` (only if Step 1 finds gaps)
- Test: `tests/test_rocks_expansion.py`

- [ ] **Step 1:** Audit each challenge's setup at 7–8 players: Pull-or-Steal already generalizes (`(players-1) grey + 1 purple` — `_pull_or_steal_grey`). Read the other three setups (`Highest Bidder` 10+1, `1 Now or 2 Later` 5+1, `Lowest Score Loses` — read its bag/scoring for any per-player table). Fixed bags stay fixed — the odds shift is acceptable house behavior and the Guide gives no bigger table — UNLESS a setup literally cannot seat 7–8 (e.g., a hard-coded per-player rock array of length 6). Fix only real breakage, minimally.
- [ ] **Step 2:** Add an 8-player smoke test per challenge: starts, every player can act, completes. Commit:

```bash
git add challenges.py tests/test_rocks_expansion.py
git commit -m "The Rocks challenges seat eight"
```

---

## Part B — The tie-breaker battery (Python, tests only)

The cascade logic is verified N-agnostic and must NOT be modified. These tests pin the behaviors 8 players will actually hit, so a future refactor can't quietly break the official rules. All in a new `tests/test_tie_break_eight_players.py`, built on the fixture idioms of `tests/test_tie_break_cascade.py` (read it first; mirror its game-construction helpers).

- [ ] **B1 — Four-way tie at a double:** 8 alive, votes 2/2/2/2 → `tieBreakNeeded`, `tiedPlayers` has all four, `eliminationsNeeded == 2`; `tie_break` with `chosenIds` of two of them eliminates exactly those two.
- [ ] **B2 — Clear first, three-way second tie:** votes 3/1/1/1 → first is eliminated outright, Leader chooses 1 of the 3 (per rules line 151); `tie_break` with a single `chosenId` completes it.
- [ ] **B3 — Ties exactly matching the need:** votes 3/3 at a double → both out, **no** Leader choice (rules line 150) — with six other players at the table getting 0 votes.
- [ ] **B4 — The ladder under idol pressure:** 8 alive, double; 3 players played idols (all votes landed on them and were negated), nobody else got votes → unclear path: ladder tier 2 (non-immune, no votes) must supply the candidates; the 3 idol players appear only after all 5 non-immune players (assert `tiedPlayers` ordering).
- [ ] **B5 — Ladder exhaustion:** 8 alive, everyone but 2 played idols or wears the Necklace → tier 3 is reached; idol players are choosable last (assert order), per rules lines 157-159.
- [ ] **B6 — The three-left rule still keys on 3 alive, not table size:** an 8-player game reduced to 3 alive, double, both vote-getters on their last card → `eliminationsNeeded` drops to 1, `finalTribalAfter` set (rules line 152).
- [ ] **B7 — Even jury splits:** 8-player game reaching final 2 has a 6-member jury; stage a 3–3 final vote → `finalTribal.tieBreakNeeded` with the most-recently-eliminated juror as Leader breaking it (rules line 188). Read `survivor_server.py:2090-2122` for the tally method and the Leader identity before writing.
- [ ] **B8 — Second-place tie where second place is zero:** votes 3/0/0/... at a double (one player got all votes) → first out, then the *unclear* ladder (not a "second-place tie") supplies candidates from the no-votes tier (rules line 161's "after just the first player is voted out" case).

Run each against the CURRENT engine — every one must pass with no production change. Any that fails is a real pre-existing bug: stop, report it verbatim, and do not "fix the test to match."

```bash
git add tests/test_tie_break_eight_players.py
git commit -m "Pin the official tie-breaker cascade at an eight-player table"
```

---

## Part C — Clients

### Task C1: iOS seats and capacity

**Files:**
- Modify: colour/seat picker (find it: `grep -rn "seats\|/api/seats\|roster" ios/SurvivorGame --include="*.swift"` — the server serves `/api/seats` from `roster()`; if the picker reads the server roster, purple/pink appear with zero code; if any Swift hard-codes the six hexes, extend it)
- Modify: any player-count copy ("maximum 6", lobby capacity hints): `grep -rn "6 players\|maximum 6" ios/SurvivorGame`
- Test: extend `ios/SurvivorGameUITests/VisualAuditUITests.swift`

- [ ] **Step 1:** Audit + fix picker and copy per the greps above. Old-server tolerance: an 8-seat client joining a 6-max server just gets "Game is full" from the server — no client-side gating to add.
- [ ] **Step 2:** Layout audit at 8: camp strip (horizontal scroll — verify), ballot list, reveal list, Numbers Game reveal rows, jury row. Fix only what overflows.
- [ ] **Step 3:** Visual test: `testEightCastawaysFitTheFire` — stage a game with 7 API allies (extend the `stage()` helper with an ally-count parameter, default 3, backward compatible), assert the camp strip renders all 8, `shot("18-eight-player-camp")`. A second shot at the ballot: everyone votes via API, screenshot the 8-row reveal.
- [ ] **Step 4:** Commit

```bash
git add ios/SurvivorGame ios/SurvivorGameUITests
git commit -m "iOS: eight castaways fit the fire"
```

### Task C2: Web seats and capacity

**Files:**
- Modify: `client/dist/ui.js` / `index-optimized.html` — same audit: colour picker source (server roster vs hard-coded array: `grep -n "FF6B6B\|4ECDC4" client/dist/*.js` — if the hexes are literal, add the two new ones), "6 players" copy, any layout assumptions in the camp strip / reveal list.
- [ ] Commit:

```bash
git add client/dist
git commit -m "Web: eight castaways fit the fire"
```

---

## Part D — Verification & rollout (dispatcher)

- [ ] **D1:** Full Python suite (`run_all_tests.py`, now including `test_tie_break_eight_players.py` — register it in the runner's list) + full iOS unit tests.
- [ ] **D2:** A scripted 8-player bot game to completion: create an 8-player game (1 human slot + 7 bots via API against the scratch server), let bots run, assert it reaches `finished` — this exercises the whole ledger: 7 double councils, ~14 flips, inheritance, final tribal with a 6-jury. `tests/e2e/scripted_full_games.py` already does this shape for 3–6; extend it to 7 and 8 (seeded, deterministic).
- [ ] **D3:** Visual verification against the scratch server (`SURVIVOR_TEST_HOOKS=1`, port 8099): the two new UI shots, plus the existing suite for regressions.
- [ ] **D4:** Deploy (`bash deploy/redeploy.sh`), health check, push. Server-side 8-player games work immediately for web; iOS needs the next TestFlight build for the picker/layout work — flag it.
- [ ] **D5:** Report: the tie-break battery results (especially any pre-existing bug B1–B8 surfaces), the deck composition tables as shipped, and the one-line summary for the group: "the island now seats eight."

## Coordination notes

- Order matters in Part A: **A0 first** (it rewrites the same `survivor_cards.json` validation totals A2 touches — one agent, sequential, so the arithmetic is done twice in order rather than merged). Then A1, then **A2 and A3 together** (A2's new cards leak into 3–6 decks until A3's filter exists — do not commit A2 alone across a suite run), then A4, A5.
- Part B is independent of Part A (tests against current logic) and can run in parallel with A. Parts C1/C2 parallel to everything, file-disjoint.
- The plan deliberately does NOT touch: `resolve_tribal_eliminations`, `elimination_ladder`, `_apply_three_left_rule`, `tie_break`, the jury tally, bots' strategy, or the Sorry For You gate — all verified N-agnostic. If an implementation agent believes one of these needs a change, that is a stop-and-report, not an edit.
- 10 players is the documented single-tribe ceiling (colour distinguishability, vote scatter, council wait time); this plan intentionally builds only 7–8. A 9–10 extension would repeat A1–A3 with new rows (9p: 8 doubles; 10p: 9 doubles) plus two more seats. Twenty players means tribes-and-merge — a separate design.
