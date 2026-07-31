# Playtest Fixes — Tyler's notes, 2026-07-30

Each note vetted against the code before planning. Verdicts: CONFIRMED (real, fixing),
BY-DESIGN (rulebook says so — explained, not changed), ALREADY-FIXED (today's earlier work).

| # | Note | Verdict | Fix |
|---|------|---------|-----|
| 1 | Show card counts during the steal step | **CONFIRMED** — `renderLivesTracker` swaps the count out for the "steal" hint on your steal step, exactly when you need the counts | Show count AND steal hint together |
| 2a | Drawing should end the turn automatically | **CONFIRMED** (and rulebook-faithful: "End your turn by taking the top card") | `draw_card` auto-advances (except tribal triggers); End Turn button removed; bots/harnesses updated |
| 2b | Play-again check is slow | **ALREADY-FIXED** by the turn-discipline phase machine — the card sheet now knows client-side and shows no Play button instantly, no server round-trip | Verified only |
| 3 | Normal steals can take Vote Cards | ~~**BY-DESIGN**~~ → **OVERTURNED 2026-07-30, see below** — this verdict was wrong | Fixed in 3.10.1 |
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

---

# Follow-up — 3.10.1, 2026-07-30

## Note 3 revisited: the Vote Card is NOT stealable (the earlier verdict was wrong)

Tyler pushed back on the BY-DESIGN call above, and he is right. The Guide's setup
removes all 6 Vote Cards from the 67 *before* dealing — "remove the 9 Tribal Council
and 6 Vote Cards. Give each player 1 Vote Card, and put the extras away" — so the
Vote Card never sits in the shuffled Action Card pile you steal from. **Control The
Vote** exists solely to "take any player's Vote Card... If the player you pick has
more than 1 Vote Card, you only take 1", which would be a near-pointless card if any
random steal already took votes. Pass-the-box exists because *Control The Vote* can
leave you without a ballot, not because ordinary steals can.

Measured before the fix: 200/200 trials, a plain turn steal took a Vote Card out of a
vote-only hand. Every taking path could strip one — turn steal, Do Or Die, Power Pair,
It's A Numbers Game, Let's Form An Alliance, The Spy Shack, and Knowledge Is Power.

**Fixed** — `UNTAKEABLE_CARD_TYPES` / `takeable_indices()` in `rules_engine.py`, applied to
`execute_theft` and take-spec kinds `random_each` / `index` / `by_type`; to
`interactions.py` (`_steal_random`, plus the tie-swap and all-match-discard choices);
and mirrored in the client (Knowledge Is Power can't name "Vote"; the swap/discard picker
hides it; The Spy Shack still *shows* it — looking is that card's whole point — but renders
it disabled). Camp Raid's draw-spring passes `force: True`: it claims the card they just
drew "no matter what it is", and Vote Cards never reach the Draw Pile.

**Extra Vote is deliberately still stealable** — it rides in the Draw Pile and lives in
your hand like any other card. Only `type == "vote"` is protected.

## Empty rock bag froze the game (Tyler's reported repro)

Reported as "too many rocks were drawn and the bag was empty, the bot didn't know what to
do so it froze the game". Reproduced in a 200-game soak.

In Lowest Score Loses the bag holds 5 grey + 3 purple and the first player may legally take
all 8, so later seats meet an empty bag. The Rocks Guide covers it: *"When you get the bag it
might be empty – that's fine, just pretend to take some Rocks and pass the bag to the next
player."* The server and the human UI both handled that (0 is accepted; the input is `min="0"`).
`bots.py` was `rng.randint(1, 2)` and never considered 0 — so the bot asked for rocks that
weren't there, the server correctly refused, and the bot re-asked forever.

**Fixed** — the bot clamps its pull to the bag; `challenges.py` additionally resolves *any*
pull against an empty bag as a pull of nothing rather than erroring. A too-large pull from a
non-empty bag is still refused (a genuine client error worth surfacing).

## Also fixed
- **Double toast on every card play** — `network.js` `apiCall` already toasts each successful
  response, and `ui.js` toasted `result.message` a second time. Same duplication in `castVote`
  and the tie-break. Verified in-browser: 2 toasts before, 1 after.
- **"Camp Raid!" was the modal title for an ordinary steal** — the Sorry-For-You prompt fell
  back to the name of a real card, so a plain turn-opening steal looked like the Camp Raid card
  had been played on you. Now "A Raid On Your Camp".
- **Garbled multi-card take message** — "Sam took a card; Sam took a card from Driftwood" now
  reads "Sam took 2 cards from Driftwood" (and "X took 1 card and Y took 1 card from Z" for
  Power Pair).
- **Do Or Die tie could deadlock** — the give phase waits indefinitely for a valid card with no
  escape hatch. The trigger is gone (bot, UI and test harness all skip the Vote Card), but the
  phase still has no timeout — worth hardening if it ever recurs.

Assets/SW → 3.10.1 (required: the static cache is cache-first, so installed PWAs keep the old
JS until the cache name changes).

Battery: 22/22 suites, e2e 102/102, scripted full games all-pass, UI 39/39, and a **200-game
bot soak** across 5 configurations (official/extended, Rocks on/off, 3–6 players, 1–2 humans)
completing cleanly. Note: the Playwright UI suite is flaky *in batch* under heavy CPU load
(passes in ~29s, fails at ~195s when contended); it passed standalone every time and in 5 of
7 batch runs.
