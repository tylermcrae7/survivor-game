# TASK: Survivor Game — Correction Plan Execution

You are working in `~/Documents/GitHub/survivor-game` on Tyler's Mac mini. Work autonomously to completion. **ultrathink**

## Context
A rules-compliance review was completed 2026-07-29. Read these FIRST:
1. `docs/REVIEW-2026-07-29.md` — full findings (F1-F12) and the 4-phase correction plan. This is your spec.
2. `docs/survivor_rules.md` — the official game rules (ground truth).
3. `docs/SURV-CORE_SurvivalGuide_07AUG024_Web.pdf` — official card-by-card rulings.
4. `docs/expansion/rocks-instructions.pdf` + `docs/expansion/rocks-challenge-guide.pdf` — the Let's Go To Rocks expansion (2025), incl. "Playing with Survivor: The Tribe Has Spoken" combined-mode rules.

Architecture: Flask+Socket.IO server (`survivor_server.py`) → rules engine (`rules_engine.py`, card defs in `survivor_cards.json`) → vanilla-JS web client (`client/dist/`). There is also an iOS SwiftUI client in `ios/` — do NOT build it, but keep its API contract in mind (it mirrors the web client's REST+socket calls); note any breaking API changes in the progress log.

## Environment — IMPORTANT
- Homebrew python3 is 3.14 and has NO flask. Use `.venv/bin/python` for EVERYTHING (server, tests). It exists with requirements installed.
- Run the server for testing: `.venv/bin/python survivor_server.py` (port 8080; it is free).
- The git repo has a CORRUPTED packfile (`.git/objects/pack/pack-bd27a5bb… far too short`). Remote: https://github.com/tylermcrae7/survivor-game.git, branch main, 1 unpushed commit that may be unrecoverable. **Step 0 = repair:** fresh-clone to a temp dir, verify the clone's fsck is clean, copy the fresh `.git` in place of the corrupt one (preserve the CURRENT working tree exactly — it is ahead of origin and is the source of truth), re-check `git fsck`, then commit the working tree as a baseline commit before touching anything. Do not lose working-tree files. `games*.json`, `.venv/`, `ios/SourcePackages/` should be gitignored, not committed.

## What to do
Execute the correction plan phases 1→4 from the review, in order, committing after each coherent unit of work with clear messages.

### Phase 1 — Correctness (P0)
1. **F1 — Character-card lives.** Vote-out decrements `characterCards` (2→1→0). Player is only `isEliminated` (and jury) at 0. First flip: player stays fully in the game. Handle: single + double eliminations, tie-break eliminations, Inheritance (only fires on TRUE elimination), final-tribal trigger (2 players with ≥1 card left), client UI showing lives (e.g. 🔥🔥 / 🔥) in player lists and playing screen.
2. **F2 — Vote-card economy.** Setup: deal 3 action cards + exactly 1 Vote Card per player; remaining Vote Cards OUT of the deck (official: 6 vote cards, extras removed; deck contains no vote cards after setup). Voting consumes a Vote Card (or Extra Vote / Goodwill Gamble card) from hand. After each tribal: every player with ≥1 character card gets 1 Vote Card back. Control The Vote takes a physical Vote Card from the target's hand. Keep `extraVotes` counters consistent with actual cards.
3. **F3 — State resync 405.** `client/dist/state-manager.js` line ~436 calls `apiCall('/game/${gameId}/state')` which defaults to POST; server route is GET-only. Fix the client to GET. Verify the resync path works (poll it live).

### Phase 2 — Robustness (P1)
4. **F4 — HTTPS redirect wedge.** Remove or fix the inline force-HTTPS redirect in `client/dist/index-optimized.html` (it black-screens any non-LAN/non-localhost hostname, e.g. Tailscale IPs). Keep PWA function intact.
5. **F5 — Enforce Steal→Play→Draw.** `draw_card()` must reject if the player hasn't stolen this turn (rules engine already computes phase — use it). Return a clear error message the client surfaces.
6. **F6 — Heartbeat crash.** `on_heartbeat()` takes 0 args; client emits `('heartbeat', {t}, ack)`. Fix signature + send the ack so client RTT measurement works.
7. **F7 — Deck contents toggle.** Official deck = 67 cards (no Idol Nullifier, Steal A Vote, Block A Vote, Grant Immunity). Add a game-creation option `deckMode: "official" | "extended"` (default official). Extended keeps the current 74. Update `survivor_cards.json` metadata to stop claiming the extended deck is official. Expose the toggle in the web client create-game UI.
8. **F8 — Test suite repair.** Fix drifted tests to match the OFFICIAL rules table and current state shapes (the review confirmed the ENGINE is right where tests disagree on the tribal table: 3p=4S/0D, 4p=2S/2D, 5p=2S/3D, 6p=0S/5D). Update tests for the new lives + vote-economy behavior. `tests/e2e/e2e_api_live_test.py` is a 23-check live API test (needs server on :8080) — update its 3 expected-failure checks (lives) to now PASS, and extend it to cover vote-card economy + steal-enforcement. Goal: `run_all_tests.py` green under `.venv/bin/python`.

### Phase 3 — Fidelity (P2)
9. **F9 — Tie-break cascade.** Implement official double-elim rules: 3+ way tie → leader picks 2; 2-way tie → both out; clear 1st + tie for 2nd → 1st out, leader picks among 2nd; 3-players-left double-elim → leader picks 1 then final tribal. Plus the "unclear who is voted out" priority ladder (non-immune with votes → non-immune without votes → idol players).
10. **F10 — Official final-tribal questions:** "What was your strategy coming into the game?" / "What was your best move in the game?" / "How did you outplay your opponent?"
11. **F12 — Housekeeping:** delete `games 2.json`…`games 7.json`; gitignore `games.json`, `ios/SourcePackages/`, `.venv/`, `*.log`; keep `winners.json`.

### Phase 4 — Expansion: Let's Go To Rocks (combined mode)
Read the two expansion PDFs carefully first. Implement combined-mode per the official guide:
12. New card category `challenge` with the 5 Orange Challenge Cards added to the deck ONLY when game is created with `expansion: true` (new create-game toggle, works with either deckMode). Drawn like action cards, played on your turn.
13. **Immunity Idol Necklace:** challenge winner wears it; players CANNOT vote for the wearer at the next tribal council; necklace returns to the table when that tribal ends. If a winner is already wearing it → they instead draw 3 random non-tribal-council cards from the draw pile.
14. Implement challenges in this order (server logic + minimal functional web UI for each):
    a. **Highest Bidder** — bid/pass auction, winner pulls N rocks from a virtual bag (5-8 grey per player-count table + 1 purple), purple = knocked out, survive your bid = win.
    b. **1 Now or 2 Later** — pass-or-pull with forced-2 penalty, 5 grey + 1 purple, purple knocked out, last standing wins.
    c. **Lowest Score Loses** — simultaneous secret pulls from 5 grey (+1) / 3 purple (−2), lowest total knocked out per round, redo if all remaining knocked out, last standing wins.
    d. **Pull or Steal** — sequential pull-from-bag or steal-from-lower-numbered-player (10 grey + 1 purple), simultaneous reveal, purple holder wins.
    e. **Hide 'n' Seek — SKIP.** It is physical sleight-of-hand. Add a stub that explains it's not available digitally; document the design question in the progress log.
    Eliminated players still participate in challenges (per official rules) but can't win the game.
15. Add engine tests for necklace behavior + each challenge; extend the e2e test with one expansion game.

## Final retest (required)
- `run_all_tests.py` — all suites green.
- Start the server, run `tests/e2e/e2e_api_live_test.py` — all checks pass.
- Play one full scripted 3-player OFFICIAL game to a winner via the API (verify: lives 2→1→0, vote cards consumed/returned, final tribal fires at 2 players, jury vote, winner recorded).
- One scripted EXPANSION game exercising at least 2 challenges + the necklace immunity at a tribal.
- Summarize results in the progress log.

## Progress reporting (do this THROUGHOUT, not at the end)
- Append a timestamped line to `docs/PROGRESS-2026-07-29.md` after EVERY completed item (e.g. `- [x] 19:45 F1 lives system — engine+server done, 14 tests updated, commit abc1234`). Tyler will read this file to track you.
- Also log milestones to the task tracker: `~/.local/bin/mtask log 3978 "message"` (task id 3978 already exists).
- Commit early and often. NEVER force-push. Do not push to GitHub at all — local commits only (the remote branch situation is tangled; Tyler will push).
- If you hit something genuinely blocking, write it to the progress file, log it via mtask, and continue with the next non-blocked item.
