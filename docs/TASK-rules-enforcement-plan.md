# Rules-Enforcement Plan — 2026-07-30

Source of truth: the official Survival Guide (`docs/SURV-CORE_SurvivalGuide_07AUG024_Web.pdf`)
and the base rulebook (`docs/survivor_rules.md`). Every finding below was verified against
the current code, not assumed.

## Confirmed violations (Tyler's reports)

### V1 — Multiple card plays per turn
Rulebook: *"Play **1 card** from your hand if you'd like to."* One optional play.
Code: `play_card` has **no played-this-turn flag**. `get_current_turn_phase` returns
`turn_play` from the moment you steal until the turn advances, so the client keeps
showing cards as playable and the server keeps accepting plays.

### V2 — Unlimited draws per turn
Rulebook: *"**End your turn** by taking the top card from the Draw Pile."* One draw,
and it ends the turn. Code: `draw_card` enforces steal-first but has **no drawn-this-turn
flag** — draw as many as you like. Also, because `turn_play` persists after drawing,
you can **play a card after drawing**, violating "Steal, Play, THEN Draw."

### V3 — Vote-card discipline (Control The Vote)
Guide: *"You MUST use that Vote Card **in addition to your Vote Card**."* Taking a vote
only makes sense while you still hold your own. Code: `_effect_control_the_vote` takes a
Vote Card with **no check that the player still holds their own Vote Card**.
(The stolen card does correctly become mandatory via `sync_vote_counters`.)

## Discovered while reviewing (not reported, but real)

### V4 — Camp Raid has the wrong effect entirely
Guide: *"Place this card **face up in front of any player**. You take the **next card they
draw** at the end of their turn… You can't play this card on a player who already has a
Camp Raid in front of them."* It's a visible trap on future draws.
Code: `_effect_camp_raid` does an **immediate steal of 2 random cards** — a different,
stronger card. Irony: the correct delayed machinery already exists (`campRaidedBy` marker,
consumed in `process_card_draw_effects`, wired into `draw_card`) — but **nothing ever sets
the marker**. The wrong effect shipped; the right one sits orphaned.

### V5 — Sorry For You's reach is too narrow
Guide: *"Play ANY time someone tries to take cards from you… **or any cards they would
steal from you as an effect of another card** (like the Do Or Die Card)."* And the
multi-taker clause: one Sorry For You blocks **all** takers and **each** discards 1.
Code: the reactive window only opens for the **turn-steal**. Spy Shack takes, Knowledge
Is Power demands, Alliance steals, all three Reward Challenge steals, and (future) Camp
Raid consumption all bypass it via direct hand manipulation. No multi-taker support.

### V6 — Housekeeping
- `drawBonus` is a phantom mechanic: consumed in `get_card_draw_count`, set by nothing.
  Remove it — it's a latent multi-draw path.
- README card table describes Control The Vote with the old wrong text ("choose the next
  Council Leader"); the registry/effect are already correct. Fix the docs.
- Inheritance: implementation is "proactively mark any player" vs official "color-bound
  card played at the moment of elimination." **Recommendation: keep the digital
  adaptation** (it plays better async and shipped tested), but document it as a house
  adaptation in the README.

## Verified correct (no action; add pinning tests where noted)
- Tribal Council Leader = the player who drew the card ✓
- Immunity Idol: only after all votes, before tally; playable on another player ✓ (pin test)
- Advantage cards locked once voting starts ✓ (pin test)
- I'm The Leader Now: leader swap + takes the next turn after tribal ✓
- Post-tribal turn order: next after drawer, honoring `pendingTurnPlayerId` ✓
- Goodwill Gamble / Vote mandatory casting; Extra Vote optional ✓
- Reveal refuses until every living player has voted ✓

## Workstreams

### W1 — Turn discipline (V1 + V2) — the core fix
Server: add `hasPlayed` / `hasDrawn` per player, reset wherever `hasStolen` resets
(advance_turn, complete_tribal, reset paths). `play_card` refuses a second play AND any
play after drawing. `draw_card` refuses a second draw. `get_current_turn_phase` grows a
`turn_done` state (stolen + drawn): nothing left but End Turn.
Client: mirror the phase logic (`game.js` getCurrentTurnPhase), so the hand grid locks
after a play is spent, the Draw button disables after drawing, and the guidance strip
says "You drew — end your turn." Keep the explicit End Turn button (a beat to read the
drawn card is good UX).
Bots: simplify `_turn_action` to read the new flags instead of runner memory.
Tests: unit (second play refused, play-after-draw refused, second draw refused, flags
reset on advance/tribal) + e2e checks + the bot soak still finishing.

### W2 — Vote-card discipline (V3)
`_validate_action_card_play` / advantage-play path: Control The Vote requires the player
to still hold their own Vote Card ("in addition to yours"). Test: play it with and
without a Vote Card in hand; verify the stolen card becomes mandatory and both get cast.

### W3 — Camp Raid, the official trap (V4)
Rewrite `_effect_camp_raid`: set `campRaidedBy` on the target (refuse if already marked —
"can't stack"), no cards move at play time. Registry description + card sheet text
change. UI: a face-up "Camp Raid" chip on the marked player's row (it's public
information by rule). Bots: raid becomes trap placement (target the card leader);
consumption already works via the existing draw hook. Tests: marker set, no-stack rule,
consumption on next draw (after they look at it — the drawn card enters their hand then
transfers), marker cleared, works when raider was eliminated first (guide is silent —
rule: dead raiders' traps fizzle; document).

### W4 — Sorry For You everywhere (V5) — biggest
Generalize `pending_theft` into a single reactive "taking gate": every path that takes
cards from a hand goes through it — turn steal (today), Spy Shack, Knowledge Is Power,
Alliance (both takers → multi-thief list), Do Or Die loss, Power Pair (two takers),
Numbers Game, Camp Raid consumption, Control The Vote's vote take.
Multi-taker: one Sorry For You cancels every taker in the gate; each discards 1.
The existing raid dialog is reused — it names the source card ("Do Or Die!" etc.).
Bots already answer the window. Interactions/challenge engines route their steals
through the gate (pause interaction → resolve window → resume/finish).
Tests: one per source path, plus the multi-taker discard case from the guide.

### W5 — Cleanups (V6)
Remove `drawBonus`. Fix README card table (Camp Raid, Control The Vote). Registry
description audit against the guide (one pass, all 26). Note the Inheritance adaptation.

## Order & risk
W1 → W2 → W5 (small, immediate, fixes everything Tyler saw) → W3 (self-contained) →
W4 (largest; touches interactions + challenges — do last, behind the full suite + e2e +
a fresh bot soak, since the soak exercises every take-path automatically).
Version bump to 3.9.0 with W1; ship W1+W2+W5 together, then W3, then W4.
