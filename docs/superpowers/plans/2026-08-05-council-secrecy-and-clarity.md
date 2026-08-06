# Council Secrecy & Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five findings from the 2026-08-05 live 8-player playtest: the jury-ready error, a private Discord room for the jury, idol labels that survive nullification, secret tribal advantages that stay secret, and an alliance that announces itself like the event it is.

**Architecture:** The server stops narrating what should be secret (an effect-level `secret` flag the dispatch layers respect), starts saying why a jury signal was refused, and opens a Jury Hut place during Final Tribal. Clients decode two flags they already receive-and-drop (`idolNullified`, `voteBanned`) and add one prominent overlay (alliance). Nothing touches the tie-break cascade or the deck.

**Tech Stack:** Python 3 (unittest), SwiftUI iOS 17+, web `client/dist`. Tabs in `rules_engine.py`.

---

## Investigation results this plan rests on (verified, do not re-derive)

1. **The jury error:** `signal_jury_ready` (`survivor_server.py:2343`) returns bare `False` from every guard — no game / no id / wrong phase / not deliberation — so the client gets a reasonless failure. Live log: `Action 'signal_jury_ready' returned False for game c2acaf7a` ×2 at 20:59; the game later completed fine. iOS renders "Ready to Vote" in two spots (`FinalTribalScreen.swift:184-186` and `:215-216`) and at least one shows before deliberation opens.
2. **No jury room exists:** `places.py` `_PHASE_POLICY` forces every player — jury and finalists alike — into `tribal_council` during `final_tribal` (line 67). The jury has nowhere to talk without the finalists hearing.
3. **Idol labels never change on nullification:** the server tracks `player["idolNullified"]` and correctly excludes nullified idols from `protectedPlayers` at reveal, and a transient `immunityNullified` toast exists — but **no iOS view or State file decodes `idolNullified` at all** (repo-wide grep: zero hits outside the model-free toast), so every persistent "idol played / protected" label stays lit after a nullifier lands.
4. **Secret advantages are announced:** every `play_card` fires a `card_played` narrator event naming player, card, and target (`survivor_server.py:3665`) AND lands the effect's message in the eventLog via `handle()`. Playing Steal A Vote or Block A Vote tells the whole table who did what to whom — end-game information the card's whole point is to hide.
5. **Alliance is a toast and a mystery card:** the ally's phone gets a normal-priority steal toast and a card silently appears in hand. Nothing durable marks the moment for the two partners.

---

## Part S — Server

### Task S1: The jury signal says why

**Files:** `survivor_server.py` (`signal_jury_ready`, ~2343); test beside the final-tribal tests (grep `signal_jury_ready` in tests/).

- [ ] Every `return False` becomes a `{"success": False, "message": ...}` with a reason: game not found; "Only jury members raise a finger"; "The Final Tribal hasn't started"; **"The finalists are still making their cases — deliberation opens the vote"** (the one Tyler hit); "You already raised your finger" if re-signaled. Success returns `{"success": True, "message": f"{name} is ready to vote"}` so the eventLog/broadcast pipeline picks it up like every other action. Confirm `bots.py`'s caller tolerates dicts (it does — `result.get("success", True)` — verify, don't assume).
- [ ] Tests: each refusal reason, the success message, and that a pre-deliberation signal is refused with the finalists-still-talking message.
- [ ] Commit: `"The jury's raised finger gets an answer instead of a shrug"`

### Task S2: Steal A Vote and Block A Vote go dark

**Files:** `rules_engine.py` (`_effect_steal_vote` ~1978, `_effect_block_vote` below it — tabs), `survivor_server.py` (`handle()`'s eventLog call site, `_emit_narrator_events`'s `play_card` branch ~3658); tests in `tests/test_steal_alerts.py` or a new `tests/test_secret_advantages.py`.

Contract: a card effect may return `"secret": True`. A secret result: (a) never lands in the eventLog, (b) never emits the `card_played` narrator event, (c) still returns its full message to the ACTOR's own HTTP response, (d) still mutates state normally (the target's `voteBanned`/stolen vote flags ride the ordinary state push — the target's own phone can see WHAT happened to them without being told WHO).

- [ ] Mark both effects' returns `"secret": True`. Their message text stays for the actor ("You stole Mango's vote — you cast two ballots tonight").
- [ ] `handle()`: skip `_append_event_log` when `result.get("secret")`. `_emit_narrator_events`: skip the `card_played` emission when `result.get("secret")`.
- [ ] Sweep for other leaks: grep both card types through `survivor_server.py`/`rules_engine.py` for any other message that names the actor to the room (the tribal-advantage window's own responses, `log_message` twins). The plan deliberately scopes secrecy to these two house cards — Control The Vote stays loud (the Guide's card is public by design: the stolen Vote Card must be cast openly).
- [ ] Tests: playing each secretly leaves the eventLog without a new entry, emits no `card_played`, bans/steals the vote for real, and returns the actor a full message. Also: the existing "Voting Box waits on everyone" logic already skips banned players (`is_vote_blocked`) — pin with a test that a banned player never appears in the reveal's "waiting on" refusal.
- [ ] Commit: `"Steal A Vote and Block A Vote work in the dark, as end-game secrets should"`

### Task S3: The Jury Hut — DEFERRED (Tyler, 2026-08-05: "Forget about number 2 for now.") Do not implement.

**Files:** `places.py`, `discord_bot.py`, `tests/test_places.py`; env var on the bot's LaunchAgent (dispatcher wires it when Tyler supplies the channel id).

During `final_tribal` (and legacy `final`), the jury may slip out to talk without the finalists hearing; the finalists stay at the council. Mirrors the Exile Island pattern commit-for-commit (`e79d272`/`f4921a6`).

- [ ] `places.py`: new place key `jury_hut` (label/emoji per Tyler's channel name — dispatcher confirms; placeholder "⚖️ The Jury Hut"). Policy: in `final_tribal`/`final`, an ELIMINATED player (the jury) gets `open = (tribal_council, jury_hut)`, forced None — their choice; a finalist stays `forced = tribal_council`. All other phases: jury_hut closed (exile rules unchanged — Exile Island remains the eliminated's home in `playing`/`tribal_council`; the hut exists only while the Final Tribal sits).
- [ ] `voice_plan`: jury members carry the same `eliminated` marking they do today.
- [ ] `discord_bot.py`: `DISCORD_JURY_HUT_CHANNEL_ID` env, optional exactly like Exile Island — when unset, the place still exists in-app (text/place UI) and the bot simply has no channel to move anyone to, barring nobody.
- [ ] Tests mirroring `TestExileIsland`: jury may enter the hut during final tribal, finalists are refused, the hut is closed during `playing`, and a missing channel bars nobody.
- [ ] Commit: `"The jury gets a hut of their own while the finalists plead"`

### Task S4: Pin that `idolNullified` reaches the wire

**Files:** test only (`tests/test_nullifier_window.py` or the tribal tests).

The player dict already carries `idolNullified` and `get_game_state` deep-copies players whole — verify with a test that a nullified player's state payload shows `idolNullified: true` alongside their (now moot) `immunityIdolProtection`. No production change expected; if one IS needed, it's a bug — report it.

- [ ] Commit: `"The wire is pinned: a nullified idol says so in the state"`

---

## Part I — iOS

### Task I1: The ready finger waits for deliberation

**Files:** `ios/SurvivorGame/Views/FinalTribal/FinalTribalScreen.swift` (both Ready buttons, ~184 and ~215 — read the surrounding phase cases first), `FinalTribalViewModel.swift`.

- [ ] The "Ready to Vote" button renders only when `finalTribal.phase == "deliberation"` (or is shown disabled with the hint "The finalists are still making their cases" during questions — pick whichever matches the screen's existing disabled-state idiom). Server refusals (S1's new messages) surface through the normal error path either way.
- [ ] Commit: `"iOS: the ready finger waits for deliberation"`

### Task I2: A nullified idol says so

**Files:** `ios/SurvivorGame/State/PlayerState.swift` (decode `idolNullified`, mirroring a neighboring optional Bool), every view rendering idol-played state — `ImmunityView.swift` (the played-idol banner naming protector/protected, ~84), and any chip/label found by `grep -rn "immunityIdolProtection" ios/SurvivorGame/Views`.

- [ ] Decode the flag (optional, default false — old servers).
- [ ] Everywhere a label says the idol protects, `idolNullified` flips it: "IDOL NULLIFIED" / "the idol is nullified — votes count" in the ember/danger tone (mirror the IMMUNE pill's construction, inverted palette). The reveal needs nothing — the server already excludes nullified players from `protectedPlayers`.
- [ ] Unit test: decoding; a view-model-level test if the label logic lands in one.
- [ ] Commit: `"iOS: a nullified idol stops advertising protection"`

### Task I3: The target learns their vote was taken — quietly

**Files:** `ios/SurvivorGame/Views/Tribal/VotingView.swift` (the ballot), `PlayerState.swift` if `voteBanned` isn't decoded yet (grep first).

- [ ] On the target's OWN ballot screen, when `voteBanned` is true: a quiet line in place of the ballot — "Your vote was taken tonight. Who took it stays in the shadows." No toast, no event, nothing on other phones (S2 keeps the table dark; the waiting list already skips them).
- [ ] Commit: `"iOS: the ballot tells its owner their vote is gone, and no one else"`

### Task I4: The alliance gets its moment

**Files:** `ios/SurvivorGame/Models/NarrationEvent.swift`, a new small overlay under `Views/Components/` (follow `ReactiveTheftOverlay`'s presentation pattern), `ContentView.swift` (mount point).

- [ ] Server (REASSIGNED to Part S as Task S5, for file disjointness): `_effect_lets_form_an_alliance`'s success path appends a `_pending_alerts` entry `{"event": "alliance", "data": {"initiatorId", "initiator", "allyId", "ally", "victimId", "victim", "message": "X forms an alliance with Y — they raid Z's camp together"}}` (the flush pipeline already delivers it; redaction rule: names only, never cards). Test beside the inheritance-alert tests. The iOS agent builds against this contract without reading Python.
- [ ] iOS: `NarrationEvent` gains the `alliance` case (critical priority — it must not be evicted). The two PARTNERS (my id == initiatorId or allyId) get a **blocking overlay**, not just the toast: alliance title, the partner's name, the victim's name, and "the spoils are in your hand" — dismissed by tap, mirroring the interaction reveal's Continue idiom. Everyone else gets the ordinary toast only.
- [ ] Tests: NarrationEvent decode trio (mirroring `raidBlocked`'s tests); overlay presentation logic unit-tested if it lands in a view model.
- [ ] Commit: `"iOS: an alliance is a moment, not a mystery card in your hand"`

---

## Part W — Web (`client/dist` only)

### Task W1: Parity where the web has the same organs

- [ ] Jury ready button gated on deliberation (find the final-tribal screen's ready control; same rule as I1).
- [ ] Idol labels honor `idolNullified` wherever the web shows played-idol state (grep `immunityIdolProtection` in `ui.js`).
- [ ] Ballot-owner "your vote was taken tonight" line off `voteBanned`.
- [ ] Alliance: a modal for the two partners on the `alliance` event (the web listens to `game_event` — check how it handles narrator events today; if it only reads the eventLog drawer, present the modal off the event the socket already delivers).
- [ ] Commit: `"Web: deliberation gates the finger, nullified idols say so, alliances announce"`

---

## Part D — Integration (dispatcher)

- [ ] Full Python suite + iOS unit tests + affected UI/visual tests (stage: a nullified idol council; an alliance overlay; a jury-hut move during final tribal via API).
- [ ] Answer for Tyler's Discord question, wired: he creates the Jury Hut voice channel and supplies its ID; the dispatcher adds `DISCORD_JURY_HUT_CHANNEL_ID` to the bot's LaunchAgent plist and bounces it (redeploy.sh already restarts both agents).
- [ ] Deploy, health check, push. iOS pieces ride the next build — flag which of the five findings are server-side-live vs build-gated.

## Coordination

- Three parallel agents (S, I, W), file-disjoint, one worktree, explicit-path staging only. S first is NOT required — I and W depend only on the payload contracts above (`secret` flag behavior, `alliance` event shape, `idolNullified`/`voteBanned` flags), all fixed by this plan. EXCEPTION: I4/W1's alliance event needs S's emission to test live — agents verify via unit tests; the dispatcher stages the live overlay.
- Off limits: tie-break cascade, deck builder, steal engine, `PENALTY_DISCARD_SECONDS`.
- Secrecy rule of thumb for every message an agent writes: the ACTOR may read everything, the TARGET may read what happened to them, the TABLE reads only what a table watching real players would see.
