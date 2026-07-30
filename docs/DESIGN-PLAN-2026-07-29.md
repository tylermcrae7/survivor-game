# Survivor Web Client — Frontend Design Plan

**Date:** 2026-07-29 · **Reviewed by:** frontend-design pass over the live app at 414×896 (iPhone)
**Scope:** `client/dist/` only. No server or API changes. No build step — vanilla HTML/CSS/JS stays.

---

## 1. Review findings

### What the app is
A phones-around-the-table companion for a physical party game, played at game night over
LAN/Tailscale/Cloudflare tunnel. Primary viewport is a phone held in one hand in a dim living
room. One shared game; each phone shows *that player's* view. Moments matter more than density:
"it's your turn", "tribal council", "the tribe has spoken".

### Current aesthetic (screenshots in scratchpad `design-review/`)
Dark glassmorphism over an OKLCH jungle/torch palette — competent tokens, but the execution is
generic AI-dark-dashboard: system font stack (`-apple-system`), emoji as the entire iconography
(🏝️🔥🗳️📿💀🃏), identical rounded glass cards for every screen, no compositional hierarchy, and
huge dead space below the single centered column. Nothing about it says *Survivor* except the
words.

### Broken visuals found (must fix regardless of aesthetics)
1. **Header is visually broken.** The SURVIVOR badge renders invisible (dark-on-dark) at phone
   widths; the torch decorations render as a lone orange rectangle; `Game:` / `Player:` info is
   unreadable. The whole header reads as a rendering glitch.
2. **Avatars render as full-width color bars.** `.player-avatar` / `.vote-target-avatar` stretch
   into horizontal stripes with a letter at the left edge (see lobby + voting screenshots) —
   `border-radius: 50%` on an unconstrained flex child. Every screen with players is affected.
3. **Screens render stale/empty on navigation.** `showScreen()` switches visibility but never
   re-renders content; content only appears when the *next* socket update arrives. Reproduced:
   lives tracker empty on the playing screen until a poke. Fix: `showScreen` (or `setupScreen`)
   must call `updateCurrentScreen(fullGameState)` after switching.
4. **The playing screen has no steal UI — a flow break, not a style issue.** The only Steal
   buttons live in the *lobby* player list. During play (when stealing is mandatory!) there is no
   player list at all, so the first turn action has no affordance. The lobby, meanwhile, shows
   Steal buttons when stealing is impossible.
5. **Native form controls unstyled** on the start screen (`<select>`, checkbox) — jarring against
   the glass cards.
6. **Voting screen shows "Votes cast: 0/4"** but gives no indication of *my* remaining votes
   (mandatoryVotes/maxVotes are in the state and unused by the UI).

### Structure (what the executor inherits)
- `index-optimized.html` (607 lines) — 11 screens by id: `startScreen, lobbyScreen, playingScreen,
  tribalAnnouncementScreen, tribalAdvantageScreen, tribalDiscussionScreen, votingScreen,
  immunityScreen, resultsScreen, finalTribalScreen, gameOverScreen` + narrator bar, toasts, modal
  `<dialog>`, card tooltip popover.
- `styles.css` (2126 lines) — cascade layers `reset, tokens, base, layout, components, states,
  utilities`; OKLCH tokens; many keyframes already defined (`torchFlicker`, `torchSnuff`,
  `voteSlam`, `turnPulse`, `confettiFall`).
- `ui.js` (2058 lines) — all rendering is template literals keyed by element IDs.
- `sw.js` — cache-first for static assets; **cache names must be bumped on any client change.**

---

## 2. Design direction — "TORCHLIT"

Commit to one idea: **night on the island, and fire is the only light.**

Everything on screen is lit the way tribal council is lit — warm light against deep darkness.
Not glassmorphism: **firelight**. Surfaces are matte near-black with a barely-there grain;
warmth comes from a single torch-amber accent that behaves like light (glows, flickers, casts);
the ceremonial moments (tribal council, elimination, crowning) get full-screen atmosphere shifts.
Between councils the app is calm and quiet; at council it turns ritual.

- **Typography** — the voice of the design:
  - **Display: `Fraunces`** (Google Fonts, variable: `wght` 400–900 + `SOFT`/`WONK` axes).
    Big, editorial, slightly feral at 900 italic — used for screen titles, the game code,
    ceremony lines ("The Tribe Has Spoken"), and count numerals.
  - **Body/UI: `Alegreya Sans`** (400/500/700/800) — warm humanist sans, highly legible at
    phone sizes. `Alegreya Sans SC` (small caps) for eyebrow labels, phase names, and button
    text — this is the "expedition signage" register: letterspaced small caps everywhere a
    generic app would use 12px uppercase Inter.
  - Load via Google Fonts with `display=swap` and system-serif/sans fallback stacks so the
    offline PWA degrades gracefully. Keep the existing preconnects.
- **Palette** — keep the OKLCH tokens as the base but re-grade them:
  - Base: deepen `--bg` to near-black jungle (`oklch(0.11 0.015 170)`); kill the blue-ish
    radial washes; replace with a subtle SVG-noise grain overlay (inline data-URI, ~2% white)
    plus one warm radial "torchlight" gradient anchored to the top of the active card.
  - Accent: `--torch` stays the hero; introduce `--flame-hot` (`oklch(0.78 0.17 70)`) for the
    hottest highlights. Everything interactive is torch-warm; everything informational is
    parchment-neutral. Cool colors reserved exclusively for player identity dots.
  - Ceremony modes via `body[data-mode]`: `data-mode="council"` (ember red-black, deeper
    shadows), `data-mode="final"` (jury gold), `data-mode="victory"` (dawn — the one time the
    background lightens). Set/removed in `updateCurrentScreen` from the game phase.
- **Iconography** — delete the emoji system. One inline SVG sprite (`<svg><symbol>` block at the
  top of `<body>`) with hand-drawn-feel icons: torch (lit), torch-snuffed (smoke wisp), voting
  parchment, immunity idol, necklace, rock, skull, crown, eye (spy). Lives render as *drawn
  torches*, not 🔥: lit = amber flame with a 3s CSS flicker; spent = grey smoke curl. Emoji may
  survive only inside the narrator's text stream.
- **Composition** — break the single-centered-card monotony:
  - The header becomes a slim one-line ritual bar: small torch mark, `SURVIVOR` in Fraunces,
    game code as a wide-tracked SC label, connection dot. No fake badge, no decorative rectangles.
  - Screens get an editorial layout: oversized Fraunces screen title overlapping the content
    card by ~0.5em (grid-breaking), eyebrow label above it, generous bottom padding instead of
    a void (the torchlight gradient fades to black, so emptiness reads as *night*, not bug).
  - Action cards in hand become **cards** — 3:4-ish tiles in a horizontal snap-scroll rail,
    category-colored top rule, SC category label, Fraunces card name, playable ones lifted with
    a torch-glow edge; locked ones recede to 40% and desaturate.
- **Motion** — few, high-impact, CSS-only:
  - One staggered reveal per screen change (existing View Transitions hook + `animation-delay`
    on children; respect `prefers-reduced-motion`).
  - Torch flicker on lit torches (reuse `torchFlicker`), smoke drift on snuffed ones.
  - "YOUR TURN" moment: when it becomes your turn, the turn banner slides in with a single
    strong pulse (reuse `turnPulse`), never loops forever.
  - Vote reveal: ballots flip in one-by-one (`animation-delay` staggered), then the eliminated
    player's torch runs `torchSnuff`. The pieces exist in CSS already — compose them.

## 3. Work plan (execute in order)

### Phase A — Foundation (blocks everything)
1. **Fonts + tokens.** Add Google Fonts `<link>` for Fraunces + Alegreya Sans (+SC). Re-grade
   the `tokens` layer: new bg/graining, `--font-display`, `--font-body`, `--font-label` vars,
   type scale for Fraunces display sizes, `data-mode` palettes. Kill the radial blue washes.
2. **SVG sprite + icon helper.** Inline `<symbol>` sprite in `index-optimized.html`; add a tiny
   `icon(name, cls)` helper in `ui.js` returning `<svg class="icon ${cls}"><use href="#i-${name}"></use></svg>`.
   Replace every emoji in `ui.js` template literals and static HTML (player status, lives,
   phase guidance icons, buttons, screen headings). Grep for the emoji list to be sure:
   🏝️🏕️🔥🗳️🛡️📊👑🎉📿💀🃏⚖️🎯💭🕯️🪨📋📤✓.
3. **Fix the broken bones** (independent of look): header rebuild (finding 1), avatar shape
   (finding 2 — fixed size, `flex: 0 0 auto`, circle), render-on-show (finding 3), styled
   `<select>`/checkbox replacements (finding 5).

### Phase B — Screens (in play order; each must look done before moving on)
4. **Start screen.** Full-bleed night backdrop, torch glow from below, huge Fraunces
   wordmark, tagline in SC. Deck mode becomes a two-option segmented control (keep a hidden
   `<select id="deckModeSelect">` in sync — tests query it); expansion checkbox becomes a
   toggle row with rock icon (keep `id="expansionToggle"` on the real input). Join flow: the
   game-code input gets wide tracking + auto-uppercase; color picker becomes a ring-select
   swatch grid with pressed states.
5. **Lobby.** The game code is the hero: Fraunces, huge, centered, tap-to-copy with a "copied"
   ember flash. Players appear as a vertical roster of torch rows (identity dot, name, host
   crown, "ready by firelight" flicker on join). **Remove the Steal buttons from the lobby
   roster** (stealing is impossible in lobby). Leader controls pinned to a bottom action bar.
6. **Playing screen — the core redesign.**
   - Top: compact turn ribbon — whose turn + turn phase as a 3-step tracker (STEAL → PLAY →
     DRAW, SC labels, current step torch-lit). Data: `getCurrentTurnPhase` already exists.
   - **New tribe panel** (fixes finding 4): every living player as a row — identity dot, name,
     torch marks (lives), card count, necklace icon when `necklaceHolder`. On *my* turn during
     `turn_steal`, rows become steal targets: torch-glow border, "tap to steal" SC hint; tapping
     calls the existing `GameAPI.stealCard`. Reuse `data-player-id` + existing handler wiring.
     Keep `id="livesTracker"` on the container (tests + updateFromDiff hook look for it).
   - Hand as the snap-scroll card rail (Phase A card design). Draw/End Turn in a fixed bottom
     action bar, Draw disabled with SC hint "steal first" until `hasStolen`.
   - Challenge panel (`id="challengePanel"` must remain): restyle as an "orange card" — rock
     icon, Fraunces challenge name, bag meter showing grey/purple rocks as dots, log as a
     campfire ticker. Keep every `data-challenge-action` hook and input id untouched.
7. **Tribal council screens** (`tribalAnnouncement/Advantage/Discussion/voting/immunity/results`).
   Enter `data-mode="council"`: ember palette, vignette darkens, header torch dims. Announcement
   is a full-screen ceremony card (Fraunces XL: "TRIBAL COUNCIL"). Voting: ballot-styled targets
   (parchment cards, tap to mark an X), my remaining votes shown as parchment chips
   (`mandatoryVotes`/`maxVotes` from state — finding 6), leader's Reveal in the bottom bar.
   Results: staggered ballot flips → vote bars in ember → eliminated player's torch `torchSnuff`
   → "The Tribe Has Spoken" in Fraunces italic. Keep all existing element IDs
   (`voteTargets`, `voteResults`, `eliminationResults`, `leaderVotingControls`, …).
8. **Final tribal + game over.** `data-mode="final"`: jury gold. Jury vote UI styled as pointing
   fingers/ballots; winner screen `data-mode="victory"`: dawn gradient (the only light screen),
   crown icon, Fraunces name huge, existing confetti keyframe recolored to embers + gold.

### Phase C — Coherence & ship
9. **Sweep every remaining surface** for the old look: toasts (restyle as parchment slips),
   modal dialog, card tooltip popover, narrator bar (matte, SC label, keep all behavior),
   network status pill, loading overlay (torch flicker loader), PWA `manifest.json`
   `theme_color`/`background_color` to match new bg.
10. **`sw.js`: bump all three cache names** (e.g. `survivor-v3.0.0`) or installed PWAs keep the
    old skin.
11. **Verify:** all 11 screens screenshot-clean at 375/414/768px; `run_all_tests.py` green;
    live e2e green (it asserts `deckModeSelect`, `expansionToggle`, `challengePanel`,
    `livesTracker` exist in served HTML); no console errors; `prefers-reduced-motion` honored.

## 4. Hard constraints for the executor

- **Do not touch** server files, `survivor_cards.json`, tests, or the API. UI contract only.
- **Every existing element ID and `data-action`/`data-challenge-action` attribute keeps
  working** — `ui.js` renders into them and `index-optimized.html`'s delegation map calls them.
  You may add IDs, never remove or rename without updating every reference AND checking
  `tests/e2e/e2e_api_live_test.py` greps (`deckModeSelect`, `expansionToggle`, `challengePanel`,
  `livesTracker`, absence of `location.replace('https`).
- No frameworks, no build step, no external JS. Google Fonts CSS is the only new external
  resource (graceful fallback required).
- Touch targets ≥ 48px; WCAG AA contrast on all text (amber-on-black passes at 4.5:1 for the
  chosen values — verify); `prefers-reduced-motion: reduce` disables flicker/stagger/confetti.
- Commit per phase (A, B-by-screen-group, C) with clear messages. Never push.
