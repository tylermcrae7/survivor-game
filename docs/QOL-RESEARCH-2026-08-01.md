# Quality-of-life research — 1 August 2026

Nine items, researched against the code, the rulebook PDF, and the live
production server. No code changed. Every claim below cites a file and line so
whoever implements this can start from evidence rather than from my summary.

**Headline:** six of the nine are straightforwardly right and mostly small. One
(#7, idols) is a real bug with a specific cause. One (#3, choosing which card to
steal) contradicts the printed rules under its obvious reading — but there is a
second reading that is *more* faithful than what we have now, and I think it's
what you meant. One (#8, slow buttons) is **not** the production server; I
measured it.

---

## Codex's Discord work — reviewed, untouched

`discord_bot.py` (828 lines) matches the handoff spec and improves on it. It
moves before locking, unlocks with `connect=None` rather than `True` so an
administrator's explicit allow isn't erased (`_set_channel_lock`,
discord_bot.py:687), paces moves sequentially with a gap rather than
`asyncio.gather`, and re-checks voice state *after* the REST member fetch to
catch someone leaving mid-move (discord_bot.py:661) — a race I never called out.

It also added something not in the spec: server-muting linked players during the
voting phase (`_set_vote_mute`, discord_bot.py:732). Worth knowing it's there,
because it's the one behaviour that acts on people rather than channels.

Nothing below touches this file, the plist, or `places.py`.

---

## The prerequisite behind #3 and #6: cards have no identity

Before the item list, the one architectural fact that governs two of your asks.

A card in a hand is this, on the server:

```json
{ "type": "vote" }
```

That's the whole record (verified against a live hand in `games.json`). Two Vote
cards in the same hand are *identical dictionaries* — indistinguishable, not
merely similar. iOS inherits the problem twice over: `CardInstance.id` is
`type + (name ?? "")` (State/PlayerState.swift:151), so duplicates collide, and
the hand grid keys off array position anyway —
`ForEach(Array(viewModel.hand.enumerated()), id: \.offset)`
(Views/Cards/CardHandView.swift:51).

Position-as-identity means every card below a removed one changes identity. You
cannot drag-reorder a hand whose items are named by their position (#3), and you
cannot run a `matchedGeometryEffect` from one player's hand to another's when
the source view's identity dissolves the instant the card moves (#6).

**Both need the same foundation:** mint a UUID per card when it's dealt, carry
it through every `hand.pop`/`append`, and key the client off it. It's a small
change in absolute terms — the deal site, the card dicts, and the Swift decoder
— but it touches the persistence format, so old saved games in `games.json` need
a lazy backfill on load. Do this once and #3 and #6 both become ordinary
feature work. Skip it and both become unstable hacks.

---

## 1. "A card just magically disappears" — turn clarity

**You're right, and it's worse than a missing animation.**

The server broadcasts nine narration events — `steal`, `card_played`,
`vote_cast`, `immunity_played`, `immunity_nullified`, `elimination`,
`tribal_start`, `tribal_phase_change`, `winner` (survivor_server.py:3123–3202).

The iOS app handles **one**:

```swift
case .custom(let type, _):
    if type == "player_joined" {
        Task { await syncState() }
    }
```
— Networking/GameClient.swift:656

Every other event arrives over the socket and is dropped on the floor. The web
app narrates all of them (`client/dist/narrator.js:555`). That asymmetry *is*
the "magic" — the server is already telling the phone what happened, and the
phone isn't listening.

Fix: a narration consumer feeding the existing `ToastView` / `StorySoFarDrawer`.
No server work. **Effort: S**, and it's the highest value-per-line item on the
list — it improves every phase at once, not just steals.

> **Adjacent bug, free to fix while you're there:** the server emits steals as
> `{thief, victim}` (survivor_server.py:3123) but the web narrator destructures
> `{player, target}` and passes those into `narrateSteal(thief, victim)`
> (narrator.js:557). Both are `undefined`. Every steal narration in the *web*
> app has been broken.

### "Should I get to choose which card I discard? I don't think it should be random"

It isn't random — it's worse, it's arbitrary but deterministic:

```python
discarded = hand.pop(discardable[-1])   # "the last one they hold"
```
— rules_engine.py:1667

**The rulebook settles this in your favour**, and not on taste. The Survival
Guide's own strategy tip for Inheritance reads:

> *"It can be useful to have the Inheritance for a player that isn't in the
> game. You can discard it if someone plays a Sorry For You against you!"*

That advice is only executable if the discarding player picks the card. Today,
holding a dead Inheritance card as Sorry-For-You chaff does nothing unless it
happens to be last in your hand. So #1 and #2 reinforce each other: choosing
your own discard isn't a house rule, it's what makes the printed Inheritance
strategy work at all.

Fix: a discard-picker window for each penalised raider. **Effort: M** — the
reactive-window machinery already exists (`game["pending_theft"]`,
rules_engine.py:263); this is a second, simpler instance of the same pattern.

---

## 2. Inheritance — the current card is not the printed card

You remembered it exactly. From the Survival Guide:

> **INHERITANCE (6 CARDS, 1 OF EACH COLOR)**
> Each Inheritance Card targets a different color player. When that player is
> eliminated from the game (by having **both** of their Survivor Character Cards
> turned over), you can **IMMEDIATELY** play this card. You get all of the cards
> in their hand instead of their cards going in the Discard Pile.

What we ship instead: you play it on your turn to *mark* anyone
(`_effect_inheritance`, rules_engine.py:1764), and it fires automatically when
they die (`process_elimination_inheritance`, rules_engine.py:2059). The README
is candid about this — "digital adaptation of the color-bound original"
(README.md:124) — so it was a deliberate simplification, not an oversight. Three
differences from the printed card:

| | Printed | Shipped |
|---|---|---|
| Binding | one fixed colour per card | any player you choose |
| When played | reactively, at the moment of elimination | proactively, on your turn |
| Agency | you choose to play it | fires automatically |

The elimination trigger is already correct: `process_elimination_inheritance` is
called only on true elimination, after both character cards are gone
(survivor_server.py:1272), and it correctly withholds the dead player's Vote
Card from the heir (rules_engine.py:2075) — that detail is well done and should
survive any rewrite.

**The obstacle is colour.** Binding a card to a colour requires colours to be a
fixed six-slot roster. We're close: `add_player` picks from exactly six defaults
(survivor_server.py:420) and refuses duplicates (survivor_server.py:403) — but
`validate_player_color` also accepts any `#RRGGBB` or CSS colour name
(survivor_server.py:142), so a player who picks their own colour has no
Inheritance card bound to them.

So this item is really two decisions:

1. **Lock colours to six seats.** Custom colours either go away or snap to the
   nearest slot. This is a product decision, not a technical one — it's the only
   part I can't make for you.
2. Then: rebind the six cards to the six seats, move the play to a reactive
   window at elimination, and rewrite the bot heuristic
   (bots.py:190 currently *chooses* a target — with colour binding there's no
   choice left, only whether to play).

Also worth keeping: the Guide's note that an Inheritance for an absent colour is
deliberately dead weight — chaff for a Sorry For You. Don't "fix" that by
reshuffling unbound cards out of the deck; it's intentional design.

**Effort: L.** The largest item on the list, and the only one where I'd want a
decision from you before anyone writes code.

---

## 3. Reorder your hand + see hand order when stealing

Two halves of one feature, and I think you're describing the physical game
rather than a house rule — but the obvious reading of it *is* a house rule, so
let me separate them.

**The rulebook says the turn-start steal is blind:**

> **1. Steal a Card** — Pick a player and steal a *random* card from them.
> (docs/survivor_rules.md:51)

If "select a card to steal" means *choose the card you want, knowing what it
is*, that removes the randomness the whole card economy is balanced on — the
best card would leave every hand every turn. I'd push back on that one.

**But the physical ritual isn't random-by-shuffle, it's random-by-ignorance.**
The victim fans their hand face-down; the thief picks a *position*. Which is
exactly what "shows the order the cards are in their hand… to select a card"
describes — and it explains why you asked for hand-reordering in the same
breath. The two are one mechanic: the victim arranges, the thief points.

That version is **more** faithful than what we ship now, not less. It keeps the
outcome unknowable, gives the thief agency, and makes hand order *strategic* —
you bury your idol behind two Vote cards and hope they pick left. The paranoia
is real and the maths are unchanged.

The plumbing already exists: `execute_take_spec` handles `kind == "index"`
(rules_engine.py:1191) for The Spy Shack, which is the same shape with the cards
face-up. A face-down variant is a small addition on top.

Blocked on card identity (see above). **Effort: M** once IDs exist — plus a
`POST /api/hand/reorder` for the permutation, since the hand lives server-side.

*Which reading did you mean? Face-down position-pick is my recommendation; I'll
build the face-up version if you want it, but say so explicitly, because it
changes the game's balance rather than its interface.*

---

## 4. Show lives during tie-break decisions

**Right, and it's nearly free.** `TieBreakView` renders avatar + name + a red X
per tied player (Views/Tribal/TieBreakView.swift:31–39) — no lives. Which is
exactly the number the leader needs: eliminating someone on 2 lives costs them a
character card, eliminating someone on 1 ends their game. Same tap, very
different act.

Everything needed is already in hand: `PlayerState.characterCards` is decoded
(State/PlayerState.swift:17), `viewModel.tiedPlayers` returns full
`PlayerState`s, and `TorchLivesView(lives:)` already exists and is already used
in the camp status strip (Views/Components/SurvivorTheme.swift:61).

Fix: one line per row. **Effort: S.** Worth doing the same in `VoteRevealView`.

---

## 5. Idol nullifiers playable right after an idol

**Right, and today the window can vanish under you.** The nullifier
(`idol_nullifier`, `"official": false` — our house card, survivor_cards.json:102)
can only be played during the `.immunity` phase, and that phase ends whenever the
council leader says so. Someone plays an idol; the leader taps *Reveal Votes*;
the nullifier holder never got a beat.

Correct fix is a reactive window, and we already have the pattern: Sorry For You
pauses a theft on `game["pending_theft"]` until the defender answers
(rules_engine.py:263). An idol should open the same kind of pause for anyone
holding a nullifier. That also fixes the ordering problem — right now the
nullifier button is offered *alongside* the idol button, before you know whether
anyone will play an idol at all (Views/Tribal/ImmunityView.swift:48).

**Effort: M.** Same shape as the existing gate; the risk is that a second
reactive window means two can now be open at once, so the resume-spec handling
needs care.

---

## 6. Animate the stolen card travelling

**Reasonable, and nothing exists today.** `Views/Cards/CardAnimations.swift`
defines `CardPlayEffect`, `CardDrawEffect` and `StealEffect` — and **all three
are dead code**. Nothing in the app calls any of them (verified: zero references
outside the file itself). They wouldn't do the job anyway; `StealEffect` is a
local wiggle, not a card moving between two players.

The real thing — a card lifting off one player's hand and flying to another's —
is `matchedGeometryEffect` across a shared `Namespace`, which needs stable card
identity (see prerequisite). It also needs the narration events from #1 to know
*when* to fire.

So the honest ordering is: **#1 first** (the app learns what happened), **card
IDs second**, then this. Done in that order it's **Effort: M**. Done first, it's
guesswork.

---

## 7. "I had immunity idols and it wouldn't let me play them"

**Found it. This is a real bug, and the cause is specific.**

The idol window is skippable, and it's one tap away from the thing you actually
want to tap. In the voting phase the council leader sees two buttons of
*identical* visual weight, side by side:

```swift
case .voting:
    Button("Open Idol Window") { … }.buttonStyle(.torchGlow)
    Button("Reveal Votes")     { … }.buttonStyle(.torchGlow)
```
— Views/Tribal/TribalScreen.swift:266–278

`VOTING → REVEAL` is a legal transition (rules_engine.py:34), so tapping *Reveal
Votes* is accepted and jumps straight past immunity. And because the iOS idol
button only renders inside `case .immunity:`
(Views/Tribal/TribalScreen.swift:158), every idol holder is now locked out —
**even though the server would still have accepted the play.** `play_immunity`
checks the game phase but never the tribal sub-phase (survivor_server.py:806).
The card was legal. The screen just wasn't there any more.

Three compounding factors:

1. **The leader has no idea anyone holds an idol.** In the physical game the
   leader *asks the table* ("If anyone has an Immunity Idol…", rules:120). In the
   app, nothing signals it.
2. **Equal button weight.** Nothing marks *Reveal Votes* as the door that closes
   the window behind it.
3. **`DISCUSSION → IMMUNITY` is also legal** (rules_engine.py:32), which opens
   the idol window *before* anyone has voted — contradicting "AFTER all players
   have voted, but BEFORE votes are tallied" (Survival Guide). The guard that
   enforces a full ballot box only fires on transitions *from* `voting`
   (survivor_server.py:1618), so the discussion route slips past it.

Recommended fix, cheapest first:
- Make the idol window **mandatory** — remove `REVEAL` from `VOTING`'s legal
  transitions, and drop `IMMUNITY` from `DISCUSSION`'s. The ceremony then always
  runs Vote → Idols → Reveal, which is what the rulebook describes.
- Badge the leader's screen when any live player holds an idol or nullifier.
- Demote *Reveal Votes* to a secondary style wherever it can close a window.

**Effort: S–M.** Highest-priority bug on the list — it silently voids the single
most valuable card in the game.

---

## 8. Rocks-bag Draw/Pass buttons feel slow and need multiple taps

**Not the production server. I measured it** — five requests to
`survivor.mctech.biz`, through Cloudflare and the tunnel:

```
total=0.094s  connect=0.034s  ttfb=0.093s
total=0.069s  connect=0.012s  ttfb=0.069s
total=0.070s  connect=0.011s  ttfb=0.069s
total=0.064s  connect=0.012s  ttfb=0.064s
total=0.063s  connect=0.011s  ttfb=0.063s
```

62–94 ms round trip. The action path applies the response's state directly
rather than waiting for a socket echo (`applyState(response.gameState)`,
Networking/GameClient.swift:529), so that's the whole latency. I also benchmarked
the write-on-every-action (`_save` re-serialises **all** games —
survivor_server.py:207): 2.7 ms for the current 884 KB / 117 games. Real, and it
grows with retained games, but not what you're feeling.

So it's client-side. Ranked by how well each explains *"needs multiple taps"*:

1. **The panel is inside a `ScrollView`** (Views/Challenge/ChallengeScreen.swift:34).
   If you scrolled to reach the button, the first tap is eaten stopping the
   scroll. This is the classic cause of exactly this complaint, and it's the one
   I'd bet on.
2. **The panel unmounts under your finger.** It's conditionally mounted on
   `isMyMove` (ChallengeScreen.swift:71). When the turn passes, the entire panel
   is torn out and replaced by a bare `ProgressView()`. A button removed and
   re-inserted mid-touch never fires.
3. **No feedback where you tapped.** `.disabled(isActing)` dims the whole panel
   (ChallengeScreen.swift:275) while the only spinner sits at the *bottom* of the
   stack, below the steal list (line 273) — often off-screen. So a tap that
   worked looks identical to a tap that didn't, and you tap again.
4. **The waiting spinner is the same spinner.** "I'm sending your move" and
   "it's someone else's turn" render identically.

Fixes: give the button its own in-place pressed/spinner state, keep the panel
mounted and disable it rather than swapping it for a `ProgressView`, and add
`.buttonStyle` press feedback so a tap is visibly received before the network
answers.

**Effort: S.** *Caveat: I diagnosed this by reading, not by reproducing it live
in a staged rocks challenge — so treat the ranking as ranked hypotheses. If you
want certainty before anyone spends time on it, I can stage one and film it.*

---

## 9. Two-letter monograms, tap an icon for the name

**Right on both counts, though narrower than it looks.** The avatar renders
`player.name.prefix(1)` (Views/Lobby/PlayerAvatarView.swift:16) — one letter. Two
players named Tyler and Tim are both a "T" in similar circles.

I checked all thirteen usages. Twelve pair the avatar with a name label beside
it, so the initial is rarely the *only* cue. The exception is the one that
matters most: `PlayerStatusBar`, the always-on camp strip, where the name sits in
a 60-point column at `.caption2` with `lineLimit(1)`
(Views/Playing/PlayerStatusBar.swift:45,61) — so longer names truncate and the
circle is doing the identifying.

And you're right that **no avatar is tappable anywhere** — there's no gesture on
`PlayerAvatarView` in any of the thirteen sites.

Fix: two-letter monogram (initials where there's a surname, first two letters
otherwise), and make the avatar a button opening a small player popover — name,
lives, hand count, place, necklace. That popover is also the natural home for
the lives-in-tie-break ask (#4) and would pay for itself several times over.

**Effort: S** for the monogram, **M** for the popover.

---

## Suggested order

| | Item | Why here | Effort |
|---|---|---|---|
| 1 | **#7 idols** | Live bug voiding the game's best card | S–M |
| 2 | **#1 narration** | One consumer fixes every phase; unblocks #6 | S |
| 3 | **#4 lives in tie-break** | One line, real decision quality | S |
| 4 | **#9 monogram** | Cheap, visible | S |
| 5 | **Card instance IDs** | Prerequisite for #3 and #6 | S–M |
| 6 | **#1b chosen discard** | Makes the printed Inheritance strategy work | M |
| 7 | **#5 nullifier window** | Known pattern, some concurrency care | M |
| 8 | **#9b player popover** | Absorbs several other asks | M |
| 9 | **#3 reorder + position-pick** | Needs your ruling first | M |
| 10 | **#6 steal animation** | Wants #1 and card IDs done | M |
| 11 | **#2 inheritance** | Needs the colour decision first | L |
| — | **#8 rocks buttons** | Do after a live repro confirms the cause | S |

## Two things I need from you

1. **#3 — face-down position-pick, or genuinely choose the card?** I recommend
   face-down. The other version changes the game's balance, and I don't want to
   ship that by assumption.
2. **#2 — lock player colours to six fixed seats?** Colour-bound Inheritance is
   impossible without it, and it means dropping custom colours.

Everything else I can act on as described.
