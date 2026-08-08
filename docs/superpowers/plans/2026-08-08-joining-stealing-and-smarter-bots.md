# Joining, Stealing, and Smarter Bots — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Revision 2 (2026-08-08), after a Fable review that verified every claim against the code.** Corrections are marked ⚠︎ where revision 1 was wrong — trust this revision, not any memory of the first.

**Goal:** Four notes from Tyler, 2026-08-08. (1) The player who just got robbed should be told what was taken, loudly. (2) A shared link should get a friend into the game with a tap, not a typed code. (3) The Discord link screen should show the code alone. (4) Bots vote as a bloc and their jury votes are a coin-flip dressed up as a heuristic — they should read the game.

**Architecture:** One genuinely new piece of plumbing — a **per-player socket room** (`gid::pid`) — carries narration to a single phone for the first time. A second, a **server-side-only ledger** under a leading underscore, gives bots a memory of the game without putting a byte on the wire. Everything else builds on machinery that already exists — with one exception discovered during review: **the web client has never received a single `game_event`**, so Part A must repair that channel before it can use it.

**Tech Stack:** Python 3 (unittest), SwiftUI iOS 17+, web `client/dist`. Tabs in `rules_engine.py`, 4-space everywhere else.

---

## Investigation results this plan rests on (verified twice — do not re-derive)

1. **There is no private channel to a player.** `on_join` (`survivor_server.py:4794`) calls `join_room(gid)` at `:4813` and nothing else; the payload is `{gameId}` only, from both clients (`SocketClient.swift:142`, `network.js:294` and `:352`). `emit_game_event` broadcasts `to=gid` (`:3619`). That is exactly why `_record_steal_alert` is documented as names-and-counts-only (`rules_engine.py:194-199`).

2. ⚠︎ **The card identity is *not* currently retained at the steal sites — it has to be captured, not merely passed along.** `steal_card` keeps only **type strings** (`rules_engine.py:2259`), plus a synthetic `"(+{type} from Camp Raid)"` string at `:2270`. `execute_take_spec`'s `random_each` kind **drops the popped card dicts entirely** (`:233-240` counts them and moves on) — and `random_each` is the kind alliances and Power Pair use. The `index`, `by_type` and `vote_card` kinds do hold the dict. Revision 1 claimed all four kinds held it; they do not.

3. **Top-level `_`-prefixed keys never reach a client.** `get_game_state` deletes them from the deep copy (`survivor_server.py:711-712`), and `tests/test_steal_alerts.py:94` already pins it. Every other read path goes through the same function: the Discord bot fetches `/api/game/{id}/state` over HTTP (`discord_bot.py:686`); `push_notify.py` never serializes game state.

4. **The web already honours `?join=CODE` and legacy `/join/CODE`** (`game.js:965-982`) — but `applyJoinLink` strips the query via `replaceState` (`:982`), and `submitAccessCode` then calls `location.reload()` (`:469`). A friend who taps a link and must enter the island code loses the game code entirely. This is the reported friction, and it is a bug.

5. **The app has no Universal Links.** `project.yml:55-57` declares only the `survivorgame://` scheme; there is no `entitlements:` block anywhere in the file. A tapped `https://` link always opens Safari, even on a phone with the app. Team `M5H3893R7A`, bundle `mctech.SurvivorGame` (`:70-71`) → appID `M5H3893R7A.mctech.SurvivorGame`. Build 14 is live (`:74`).

6. ⚠︎ **`ShareLink` builds from `gameClient.baseURL`, not a hardcoded domain** (`LobbyScreen.swift:126-129`) — a user-configurable server URL, which matters for LAN play. It does produce `…biz?join=CODE` with no slash, which is wrong for path-based AASA matching, but the fix must preserve `baseURL`.

7. ⚠︎ **Revision 1's "`pendingJoinCode` is dropped on the floor" was wrong about the mechanism.** At `StartScreen.swift:47-50` the view model is *guaranteed* built — `:39-46` creates it earlier in the same `.onAppear`. And while the gate is up, StartScreen isn't mounted at all (`ContentView.swift:20-29` shows `IslandAccessScreen`), so the code survives and is consumed on unlock. **The gated-link case works today.** The only real gap is the `.onChange` at `:52-57` firing in the narrow window where `viewModel` is nil. Worth a guard; not worth a paragraph.

8. **The Discord screen shows `/link CODE`** as hero text (`DiscordLinkSheet.swift:143`), so selecting it copies the slash command too. Instruction line at `:135`, a11y id at `:166`. No Discord UI exists in `client/dist` — this is iOS-only.

9. ⚠︎ **Bots vote as a bloc for one reason: every bot computes the identical target.** Votes use `_biggest_threat` (`bots.py:122`, called at `:514`) — hand size, deterministic `p` tiebreak, necklace holder excluded — so all bots converge on the same player, every council. Steals use a different function, **`_steal_target`** (`:133`, called at `:457`). Revision 2 briefly blamed the bots' unconditional every-turn steal as a second cause; **Tyler has since confirmed the rule: every turn is a mandatory steal, an optional card play, and a mandatory draw.** The mandatory steal at `:456-460` and the probabilistic play at `:467` are both correct rules behaviour and must not change.

10. **The jury vote is not an evaluation.** `_final_action` (`bots.py:611-618`) picks `sorted(finalists, key=-hand_count)[0]` — the same finalist for every jury bot, so a bot jury is always unanimous.

11. **The full ballot record exists and is then thrown away.** `current_vote["votes"]` is `{voter: {target: count}}` (`survivor_server.py:900`, `:1367`), but only the `{target: count}` tally reaches `gameHistory` (`:1785`, built from `:1373`). `currentVote` is rebuilt each council (`:1907`, `:1942`), so ballots are destroyed. Nothing anywhere records who stole from whom, or who won which challenge.

12. **NEW — the web client has never received a single `game_event`.** `narrator.js:543-559` binds `game_event` directly to `socketManager.socket` inside `bindEvents()`, which runs from `init()` at DOMContentLoaded (`:927-933`). The socket does not exist then — it is created by `connect(gameId)` when a game is joined (`game.js:697` → `network.js:297`). The `if (…socketManager?.socket)` guard fails, and **no handler is ever attached.** Only handlers registered through `socketManager.on()` are re-attached to the `forceNew: true` socket (`network.js:314-317`), and a repo-wide grep shows `socketManager.on()` is used for `state_update`, `game_reset`, `game_wiped`, `global_reset` and `error` — **never `game_event`.** Nothing in `tests/ui/test_ui_rules_checklist.py` covers the narrator, which is why it was never caught. **Consequence: every steal alert, the inheritance announcement, and the alliance modal shipped in the 2026-08-04 and 2026-08-05 plans are dead code on the web.** iOS is unaffected.

*Housekeeping:* `run_all_tests.py` currently lists **37** suites; this plan adds three (`test_private_channel.py`, `test_ledger.py`, `test_universal_links.py`) → 40.

---

## Part A — The robbery you can actually follow (Note 1)

### Task A0: Reconnect the web's narration channel ⚠︎ NEW — blocks A4

**Files:** `client/dist/narrator.js` (`bindEvents` ~543), `client/dist/network.js` (`on()` registry ~525); `tests/ui/test_ui_rules_checklist.py`.

Finding 12. Part A4 is unbuildable until this is fixed, and fixing it revives three features already believed shipped.

- [ ] `bindEvents()` registers through `socketManager.on('game_event', …)` (and `state_update`, `game_updated`) instead of touching `.socket` directly, so the handlers land in the `eventListeners` registry and survive both first connect and every `forceNew` reconnect. Drop the `if (…socket)` guard — it is the bug.
- [ ] Verify by hand in a browser: join a game, trigger a steal, watch a toast appear. Then force a reconnect and confirm it still appears.
- [ ] Add narrator coverage to the UI checklist — at minimum, one assertion that a `game_event`-driven toast reaches the DOM. Its absence is why this survived two plans.
- [ ] Commit: `"The web starts hearing the narrator again"`
- [ ] **Tell Tyler:** the web-side alliance modal, inheritance announcement, and steal toasts have never fired for anyone on a browser.

### Task A1: A private room per player

**Files:** `survivor_server.py` (`on_join` ~4794, new `emit_private_event`), `ios/.../SocketClient.swift` (`joinGame` :141), `ios/.../GameClient.swift` (**three** call sites: :172 join, :193 rejoin, :699 reconnect), `client/dist/network.js` (:294, :352); new `tests/test_private_channel.py`.

- [ ] `on_join` accepts an optional `playerId`; when present **and** that id is a player in that game, also `join_room(f"{gid}::{pid}")`. An absent or unknown id is not an error — an older app must keep working and simply gets no private events.
- [ ] `emit_private_event(gid, pid, event_type, data)` mirrors `emit_game_event` but targets `f"{gid}::{pid}"`, with the same `type`/`timestamp` envelope so no client needs a new decoder shape.
- [ ] Both clients pass `playerId` on join. ⚠︎ **The iOS reconnect re-join already exists** (`GameClient.swift:695-701`) — it needs the id added, not inventing. Same for `network.js:352`.
- [ ] **State plainly in the code comment that this room is a UX channel, not a security boundary.** playerIds are public in the broadcast state and the socket carries no identity, so any tablemate could join another player's room. This adds no *new* leak — every hand is already broadcast — but nobody should later build real secrets on it. (`gid`/`pid` are `uuid4[:8]` hex, `survivor_server.py:418`/`:510`, so `::` cannot be forged into the separator.)
- [ ] Tests: a private event reaches only the addressed room; an unknown or missing `playerId` still joins the game room and never raises; a `pid` from a different game is refused. Two devices on one playerId both join and both receive — that is correct. Emitting to a bot's room is a harmless no-op.
- [ ] Commit: `"A phone can be spoken to alone"`

### Task A2: The alert learns what was taken

**Files:** `rules_engine.py` (`_record_steal_alert` ~194 and its **five** call sites — `execute_take_spec` at :246, :271, :290, :304 and `steal_card` at :2272), `survivor_server.py` (`_flush_steal_alerts` ~3623); `tests/test_steal_alerts.py`.

⚠︎ Revision 1 said six call sites and pointed at `rules_engine.py:2458` as the alliance. **Wrong on both counts:** there are five, `:2458` is the *inheritance* alert, `:2113` is the alliance alert, and an alliance's actual steals already flow through `random_each` → `:246`. Do not edit `:2458` for this task.

- [ ] `_record_steal_alert` grows an optional `cards` argument — a list of `{name, type}` pairs. It records **two** alerts: the existing public one (wording unchanged, still identity-free) and a new `{"private_to": victim_id, "event": "robbed", "data": {…}}` naming thief and cards.
- [ ] ⚠︎ **`random_each` must be changed to collect the popped dicts per thief** (`:233-240`) — today it only increments a counter, so there is nothing to name. `steal_card` must keep the popped dicts rather than `card.get("type")` strings, and the Camp Raid extra card belongs in the same alert as a real card, not a synthetic string.
- [ ] `_flush_steal_alerts` routes on `private_to`: present → `emit_private_event`, absent → `emit_game_event` as today. Skip minting a private alert when the victim is a bot — a dead emit and needless `games.json` noise.
- [ ] ⚠︎ **`stolen_cards` is returned in the thief's HTTP response** (`survivor_server.py:2689-2697`). No client reads it (grepped web, iOS, tests) — keep the response shape as-is and change only the internal collection, or change it deliberately and say so.
- [ ] ⚠︎ **Existing assertions break beyond the redaction one.** `tests/test_steal_alerts.py:28` asserts `len(alerts) == 1` and `:56-57` count over *all* alerts; every steal now records two. Split every count/shape assertion into public and private. The redaction test is **strengthened, not relaxed**: the public alert still leaks nothing, and a new twin asserts the private one names the card and carries `private_to == victim`. `tests/test_inheritance.py` filters by event type (`:459`, `:547`) and survives untouched.
- [ ] Commit: `"The robbed are told what was taken"`

### Task A3: The victim's phone says so plainly

**Files:** `ios/.../Models/NarrationEvent.swift`, `ios/.../Networking/GameClient.swift` (`handleEvent`), new `ios/.../Views/Components/RobberyBanner.swift`; `ios/SurvivorGameTests/NetworkingTests.swift`.

Design note, and hold this line: **a steal happens on nearly every turn.** The alliance overlay blocks because an alliance is rare; a blocking modal per theft would be intolerable. The victim gets a *banner* — bigger and longer-lived than the narration ticker (which is `lineLimit(1)` and structurally cannot carry this), auto-dismissing, tap-to-dismiss, never blocking.

- [ ] `case robbed(thief:, thiefId:, cards: [String], message:)`, `.critical` priority, `.steal` cue, decoded by allowlist like every other case — that preserves the allowlist-by-construction property, and `init?` already returns nil for unknown types (`:119-120`), so build 14 ignores it safely.
- [ ] `GameClient.handleEvent` sets `robberyAlert` and does **not** also enqueue a narration toast — the victim already gets the public line, and two notices for one event is the double-toast mistake `_emit_narrator_events` documents.
- [ ] **Gate the banner on `victimId == own playerId`.** Private and public events arrive on the same `'game_event'` name; this is the only defense if a routing bug ever leaks `robbed` to the room.
- [ ] `RobberyBanner`: thief's seat colour, "**Coconut took your Hidden Immunity Idol**", plural for two cards, ~5s auto-dismiss, warning haptic. Reuse `AllianceOverlay`'s composition; not its blocking scrim.
- [ ] `.reset` and `leaveGame()` clear `robberyAlert` — the stale-overlay bug the alliance work already had to fix once.
- [ ] Tests: victim gets banner and no toast; a `robbed` naming someone else is ignored; reset clears it; two cards read "took 2 of your cards" naming both.
- [ ] Commit: `"iOS: being robbed is a moment, not a mystery"`

### Task A4: The same, on the web — depends on A0

**Files:** ⚠︎ `client/dist/narrator.js` (`handleGameEvent` ~563 — **not** `network.js`, which revision 1 named), `client/dist/ui.js`, `client/dist/styles.css`; `tests/ui/test_ui_rules_checklist.py`.

- [ ] Handle `robbed` in `handleGameEvent`; render a prominent banner (not the ordinary toast) naming thief and cards, gated on the viewer being the victim. Match the iOS copy word for word so a table on mixed devices hears one voice.
- [ ] UI checklist gains a check for the banner.
- [ ] Commit: `"Web: being robbed is a moment, not a mystery"`

**Deferred, stated not silently dropped:** a robbed victim whose app is backgrounded still learns nothing until they look. The repo has a push stack (`push_notify.py`); wiring a robbery push is out of scope here.

---

## Part B — Tap a link, land in the game (Note 2)

### Task B1: The gate stops eating the game code

**Files:** `client/dist/game.js` (`applyJoinLink` ~965, `submitAccessCode` ~452).

Fix this **first and alone** — it is the whole feature for anyone on the web. Review confirmed nothing else clears the code across the reload: `replaceState` plus the reload's DOM reset are the entire failure, and same-tab `sessionStorage` survives `location.reload()`.

- [ ] `applyJoinLink` stashes the code in `sessionStorage` before cleaning the address bar, and reads from the stash when the URL has none. Clear it once the code has actually been used to join, not merely displayed.
- [ ] Verify by hand: gated browser, fresh session, tap `/join/ABC123` → island code → reload → the code is still in the field.
- [ ] Test in `tests/ui/test_ui_rules_checklist.py` (it drives real browsers): the code survives a gate unlock.
- [ ] Commit: `"A shared link survives the island gate"`

### Task B2: Universal Links — the tap opens the app

**Files:** `ios/project.yml`, `ios/.../App/ContentView.swift`, `survivor_server.py` (new AASA route), new `client/dist/.well-known/apple-app-site-association`; new `tests/test_universal_links.py`.

- [ ] Serve AASA from an **explicit Flask route** returning `Content-Type: application/json`, HTTP 200, no redirect, at **both** `/.well-known/apple-app-site-association` and `/apple-app-site-association`:
  ```json
  {"applinks":{"details":[{"appIDs":["M5H3893R7A.mctech.SurvivorGame"],
    "components":[{"/":"/join/*"},{"/":"/","?":{"join":"*"}}]}]}}
  ```
  (Route placement was checked: Werkzeug ranks the static rule above `/<path:path>` regardless of registration order, the gate only guards `/api/` at `:3947`, and `rsync -a` copies `.well-known` — `deploy/redeploy.sh:19-30`. The explicit route is still right, for the mimetype.)
- [ ] Test that pins it: correct status, correct content type, and **that the access gate exempts it** — a future gate change that swallows this file breaks link-opening silently and is found months later.
- [ ] ⚠︎ `com.apple.developer.associated-domains` is **not an Info.plist property**. `project.yml` needs a target-level `entitlements: {path: …, properties: {…}}` block — none exists today, so this creates the file. Then `xcodegen generate`. **Never hand-edit `project.pbxproj`.**
- [ ] `ContentView` accepts `/join/CODE` and `?join=CODE` over https as well as `survivorgame://`. `.onOpenURL` alone is sufficient in a SwiftUI-lifecycle app; add `.onContinueUserActivity` as belt-and-braces only.
- [ ] Guard the `.onChange` at `StartScreen.swift:52-57` so it only nils `pendingJoinCode` when something consumed it (finding 7 — a small real gap, not the large one revision 1 described).
- [ ] Commit: `"A tapped link opens the island in the app"`

**Three things to tell Tyler rather than discover on a device:** Apple fetches AASA through its own CDN, so propagation can take ~24h — `applinks:survivor.mctech.biz?mode=developer` bypasses the cache for testing. Automatic signing must be able to add the Associated Domains capability to the App ID. And Cloudflare bot-fight rules can block Apple's fetcher; if links don't open, check that first.

### Task B3: The share sheet sends a link worth tapping

**Files:** `ios/.../Views/Lobby/LobbyScreen.swift` (~126), `client/dist/ui.js` (`copyGameCode` ~4163, `shareGame` ~4206).

- [ ] ⚠︎ Mint `<baseURL>/join/CODE` — **keep building from `gameClient.baseURL`**, do not hardcode the production domain, or LAN players get links pointing at a server they aren't on. (A LAN link simply won't be a universal link; that's fine.) This also fixes the missing slash in finding 6.
- [ ] The message stops leading with the raw code and reads like an invitation, keeping the code as a fallback: `"Join my Survivor game — tap to come ashore. (Fire code: ABC123)"`.
- [ ] Commit: `"The invitation is a link, not a chore"`

---

## Part C — The Discord code, alone (Note 3)

### Task C1

**Files:** `ios/.../Views/Settings/DiscordLinkSheet.swift` (~133-166).

- [ ] The hero text becomes `code` alone. The instruction line above it (`:135`) extends to "in discord, run **/link** and paste:" — the command stated once, in the small type, where it belongs.
- [ ] Tap-to-copy on the code (`UIPasteboard`, bare code) with a brief "Copied" confirmation. Selecting the text must also yield the bare code — that is the actual regression.
- [ ] `accessibilityIdentifier("discord-link-code-\(code)")` stays exactly as-is (`:166`); the spoken label drops the "slash link" prefix.
- [ ] Commit: `"The link code is just the code"`

---

## Part D — Bots that read the game (Note 4)

### Task D1: A ledger the table can't see

**Files:** new `ledger.py`; `rules_engine.py` (steal alert sites), `survivor_server.py` (`reveal_votes` ~1425, `play_card`/`play_immunity`, `_award_challenge_win` ~2905, elimination recording ~1778); `tests/test_ledger.py`.

⚠︎ Revision 1's schema could not feed D2/D3 — it had no record of cards or idols *played by* a player, no write site for card plays at all, and no way to identify the council that eliminated a given juror. Corrected:

- [ ] `game["_ledger"]`, keyed per player: `votesAgainst` (who voted for me, per council index), `votesCast` (who I voted for, per council), `stolenFrom` (thief → count), `stolenBy` (victim → count), `challengeWins`, `cardsPlayed`, `idolsPlayed`, `cardsPlayedOn` (played *on* me, by whom), and `eliminatedAtCouncil` (the council index that ended me).
- [ ] `eliminatedAtCouncil` is explicit and **not** inferred from `votesAgainst`: the rock-draw cascade in `resolve_tribal_eliminations` can eliminate a juror who received zero votes that council, and D3's central question — "did you vote for me at the council that ended me?" — would silently mis-answer.
- [ ] Written by: the steal alert sites; `reveal_votes`, which holds the full `{voter: {target: count}}` map before it is aggregated away; `_award_challenge_win`; the card-play path; and the elimination record.
- [ ] **Heals on load, per `CLAUDE.md`.** `ensure_ledger(game)` is idempotent, mutates in place, creates an empty ledger for in-flight games. An empty ledger must produce sane behaviour — never a crash, never a divide-by-zero — and bots must fall back to the card-count read.
- [ ] ⚠︎ **The ledger persists to `games.json` by design, and that is required, not a leak.** `_save` dumps `self.games` verbatim (`survivor_server.py:283`); jury votes happen hours and restarts after the councils they remember. It is stripped from `get_game_state` (`:711`) and never reaches a client. Say this in the module docstring so nobody later "fixes" the persistence.
- [ ] Tests: the ledger records what happened; `get_game_state` never contains it; a game with no ledger heals silently; a rock-draw elimination still sets `eliminatedAtCouncil`.
- [ ] Commit: `"The island keeps a private ledger"`

### Task D2: Tribal votes stop clumping

**Files:** `bots.py` (`_biggest_threat` ~122, vote site ~514); `tests/test_bots.py`.

> **Rule constraint from Tyler (2026-08-08): every turn is steal (mandatory) → play a card (optional, skippable at will) → draw (mandatory). The bots' unconditional turn steal at `:456-460` is the rules working as written — do not gate it, do not touch it, and do not "fix" `test_decision_basics` (`tests/test_bots.py:142-149`), which correctly pins it. The bots' probabilistic card play (`:467`, `play_chance`) is likewise correct — playing is the optional step and stays optional.**

- [ ] New `_vote_target(game, bot_id, rng)` scoring every living opponent — **humans included, with no path that can exclude them**: hand size normalised (the current signal, now one of several); **grudge** (cards they stole from me, votes they cast against me); **threat** (challenge wins, necklace, an idol they've played); **loyalty** (councils where we voted alike — a mild negative).
- [ ] ⚠︎ **There is no per-bot rng.** `BotRunner` has one shared, unseeded rng (`bots.py:737`), and drawing from it makes output depend on bot evaluation order — which would contradict this plan's own determinism test. The tiebreak jitter must be a **deterministic hash of `(gid, council_index, bot_id, candidate_id)`**, decisive only among near-equal scores: enough to break the bloc, not enough to make bots play badly.
- [ ] Weight by the existing `botStyle` dial: cutthroat leans threat, chill leans grudge.
- [ ] `_biggest_threat` stays for card targeting and `_steal_target` for steals — steals *should* chase the biggest hand, and per the rule constraint above the mandatory turn steal is untouchable. The bloc fix lives entirely in the vote scoring.
- [ ] Tests: over N seeded councils with a human holding the most cards, the human is voted for; bot votes are not unanimous; a bot never votes for itself, the necklace holder, or anyone eliminated; identical inputs give identical output.
- [ ] Commit: `"Bots vote the table, not the leaderboard"`

### Task D3: A jury with a memory

**Files:** `bots.py` (`_final_action` ~611); `tests/test_bots.py`.

The show's own logic: a jury rewards the player who played the best game *at them*.

- [ ] `_jury_vote(game, juror_id, finalists)`:
  - **Betrayal** — did they vote for me at `eliminatedAtCouncil`? Heavy negative. At any earlier council? Milder.
  - **Loyalty** — councils where we voted together. Positive.
  - **Robbery** — cards they took from me. Negative for a chill juror; **positive for a cutthroat one** — respect for a strong game. The asymmetry is the point, not an inconsistency.
  - **Résumé** — challenge wins, idols played, councils survived. Positive for everyone.
  - **Carried** — a finalist who never stole, never played a card, never won anything takes a penalty. "You did nothing" is a real jury argument.
  - Ties break on the same deterministic hash as D2, never on a sorted player id.
- [ ] Tests: a finalist who blindsided the juror loses that juror's vote; a loyal finalist wins it; a three-bot jury can split; an empty ledger falls back to the hand-size read without raising.
- [ ] Commit: `"The jury remembers"`

**Wedge safety, for both tasks:** a bot must never propose an action the server refuses forever. The seeded full-bot games in `tests/test_bots.py` assert completion-without-wedge and stall out at `> 50` (`:490-500`) — a forever-refused ballot is caught there, and the refusal breaker will not save a synchronous test loop. The scripted e2e games are all-human over HTTP (`scripted_full_games.py:21-25`) and cannot be affected by D2/D3.

---

## Verification

- [ ] `python3 run_all_tests.py` — 37 suites today, 40 after; register the three new files in the runner list.
- [ ] `tests/e2e/e2e_api_live_test.py` and `scripted_full_games.py` against a **scratch server on a spare port** via `SURVIVOR_TEST_BASE` (`scripted_full_games.py:73-74`) — never port 8080, never `~/srv`.
- [ ] iOS unit tests and the full UI bundle.
- [ ] A full bot game to completion with one human seat, confirming the jury actually splits.
- [ ] `bash deploy/redeploy.sh`, then `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/`.
- [ ] `curl -sI https://survivor.mctech.biz/.well-known/apple-app-site-association` — 200, `application/json`.

## Ordering and packaging

A0 → A1 → A2 → A3/A4. B1 alone and first in its part. D1 strictly before D2/D3. Cross-version compatibility holds in both directions: an old `on_join` ignores an extra `playerId`, old apps never join private rooms, unknown events decode to nil.

**The server halves (A0, A1, A2, B1, B2's AASA route, D1–D3) must be deployed with `bash deploy/redeploy.sh` before the iOS build ships.** The iOS halves — A1's join id, A3, B2, B3, C1 — must ride **one** TestFlight build.

## What this plan does not do

- **The redaction leak stays open.** Every client still receives every hand and the deck order. A1 builds the first per-player channel, which is the foundation for closing it; closing it is a larger job, not attempted here.
- **No robbery push notification** to a backgrounded victim.
- **The Jury Hut** remains deferred from the 2026-08-05 plan, waiting on a Discord channel id from Tyler.
- **`on_join` still never `leave_room`s a previous game** — private rooms inherit that existing stale-room behaviour on a game switch.
