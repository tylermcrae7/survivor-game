# Playtest Fixes — Tyler's notes, 2026-07-30

Each note vetted against the code before planning. Verdicts: CONFIRMED (real, fixing),
BY-DESIGN (rulebook says so — explained, not changed), ALREADY-FIXED (today's earlier work).

| # | Note | Verdict | Fix |
|---|------|---------|-----|
| 1 | Show card counts during the steal step | **CONFIRMED** — `renderLivesTracker` swaps the count out for the "steal" hint on your steal step, exactly when you need the counts | Show count AND steal hint together |
| 2a | Drawing should end the turn automatically | **CONFIRMED** (and rulebook-faithful: "End your turn by taking the top card") | `draw_card` auto-advances (except tribal triggers); End Turn button removed; bots/harnesses updated |
| 2b | Play-again check is slow | **ALREADY-FIXED** by the turn-discipline phase machine — the card sheet now knows client-side and shows no Play button instantly, no server round-trip | Verified only |
| 3 | Normal steals can take Vote Cards | **BY-DESIGN** — the rulebook builds around it: Sorry For You says "regardless of how many cards you owe them", Vote Cards return after every tribal, and pass-the-box exists precisely because a stolen Vote Card is possible. Control The Vote is the *targeted* version | No change; documented here |
| 4 | History sidebar (reconnect-proof) | **CONFIRMED** — narrator history is client-only and dies with the page | Server-side `eventLog` (capped 120) fed from every successful action incl. bot actions; slide-over "The Story So Far" panel from the camp menu + header |
| 5a | Tribal advantage cards unplayable during discussion | **CONFIRMED — root cause found**: the client's `getCurrentTurnPhase` never mapped tribal phases (server maps announcement/advantage/discussion → `tribal_discussion`; client returned `waiting`, locking every card) | Mirror the server's tribal phase mapping client-side |
| 5b | Couldn't play Extra Vote | **CONFIRMED** — the voting UI casts `mandatoryVotes` only; extra votes are never sent | When you hold Extra Votes, tapping a ballot target asks how many to add (0–N) |
| 5c | Don't show votes in the box (leaks extras) | **SAFE BUT UNCLEAR** — the counter counts *voters*, not votes, so extras never leak; the label "ballots in the box" reads like votes | Label becomes "X of Y players have voted" |
| 6 | Disable physical-only cards | **CONFIRMED** — Hide 'n' Seek is undigitizable sleight-of-hand; today it sits in the deck as a dead card | Removed from the expansion deck build (Rocks now adds 4 playable Challenge Cards); definition kept for old games |
| 7 | iPad: action bar covers the hand grid | **CONFIRMED** (screenshot shows a playable card glowing under the Draw button) | Clearance padding under the hand zone; bar shrinks with End Turn gone |
| 8 | Toasts vanish too fast | **CONFIRMED** — 3s default | 5s default, 6.5s for errors |
| 9 | Does the leader break ties? | **YES in the engine** (full official cascade, tested) — **but the results screen only *announces* the deadlock; the leader has no picker in the UI** | Leader-only tied-player picker on the results screen wired to `/vote/tiebreak` |
| 10 | Anyone can spam End Turn | **CONFIRMED** — `advance_turn` has no caller check. Same class: `draw_card` doesn't verify it's your turn either (an out-of-turn draw was possible) | API-level gates: advance/draw require the current player; End Turn button retired anyway by 2a |
| 11 | Share URL with the code baked in | **CONFIRMED** missing | Share/copy produce `?join=CODE`; the app opens the join form prefilled from the parameter |

## Execution order
Server (auto-advance, turn gates, eventLog, deck change) → client (tribal phase map,
extra-vote chooser, steal-step counts, tie-break picker, history panel, join links,
toasts, iPad clearance, End Turn removal) → bots + both e2e harnesses + UI suite updated
for auto-advance → full battery (23 suites, e2e, scripted) → deploy → live check → push.
Assets/SW → 3.10.0.

## Status: SHIPPED (3.10.0, 2026-07-30)
All confirmed items implemented and tested. One extra bug found on the way: a draw that
springs a Camp Raid trap opens the Sorry-For-You window, which blocked the auto-advance and
wedged the game — the turn end now defers until the window closes (caught by the bot soak).
Battery: 22/22 suites ×3, bot soak ×4, e2e 102/102, scripted full games all-pass, UI 39/39.
