# Torchlit iOS Research

> Assembled 2026-07-31 from two research passes: the web app's design language (extracted from `client/dist`) and its mapping to iOS-17 SwiftUI techniques. Workstream C of docs/superpowers/plans/2026-07-31-ios-fixes-and-torchlit-design.md implements from this document.

# Part 1 — The Web Design Language

# Survivor "TORCHLIT" — Web Design Language Extraction

Sources: `client/dist/styles.css` (primary, v `torchlit-3.11.2`), `client/dist/ui.js`, `client/dist/game.js`, `client/dist/narrator.js`, `client/dist/index-optimized.html`.

Design concept (from the stylesheet's own header comment): *"Night on the island. Fire is the only light."* Near-black jungle ground with faint SVG grain, one warm torchlight radial anchored at top-center, and a single torch-amber accent that behaves like light (glows, flickers, casts). Type is Fraunces (display/ceremony) + Alegreya Sans / Alegreya Sans SC (body/signage). The whole app re-palettes via `body[data-mode="council" | "final" | "victory"]`.

All CSS colors are authored in `oklch()`. Hex values below are exact sRGB conversions (standard OKLab math, clamped to sRGB gamut) — use the hex for SwiftUI `Color(hex:)`, but note alpha-modified variants are listed as base-color + opacity.

---

## §Palette

### Fire (accent) tokens

| Token | oklch | Hex | Role |
|---|---|---|---|
| `--torch` | `oklch(0.70 0.165 60)` | `#E68100` | THE accent. Primary/CTA color, icon tint, focus rings, caret color, glows, links-equivalent. Aliased as `--primary`. `accent-color` for native controls. |
| `--flame-hot` | `oklch(0.80 0.16 75)` | `#F9AD26` | Hotter top of flame. Top stop of CTA gradient, "your turn" name color, big game-code text, vote-count numbers, toggle thumb when on, focus-visible outline. |
| `--ember` | `oklch(0.55 0.17 40)` | `#BF4306` | Darker fire. Left stop of vote-result progress bar gradient. |
| `--ember-deep` | `oklch(0.38 0.14 32)` | `#7C1403` | Deepest fire. Track fill of the checked toggle switch. |

### Night (ground/surface) tokens

| Token | oklch | Hex | Role |
|---|---|---|---|
| `--bg` | `oklch(0.115 0.015 170)` | `#020604` | Page background (near-black with a faint green-teal jungle cast). Top of body gradient. |
| `--bg-deep` | `oklch(0.09 0.012 175)` | `#010302` | Deeper night. Bottom of body gradient, narrator panel bg, action-bar fade target, loading overlay, story drawer bg, tooltip bg. |
| `--surface` | `oklch(0.155 0.018 165)` | `#050F0A` | Card/panel base surface. Aliased as `--glass-bg`. |
| `--surface-raised` | `oklch(0.19 0.022 160)` | `#0B1710` | Lifted surface (top stop of panel/card gradients, hover states). Aliased `--glass-bg-light`. |
| `--surface-sunken` | `oklch(0.13 0.016 168)` | `#030906` | Recessed wells: inputs, chips, list rows, segmented-control track. |

### Parchment & ink

| Token | oklch | Hex | Role |
|---|---|---|---|
| `--parchment` | `oklch(0.91 0.04 85)` | `#EEE0C4` | Warm off-white. Headings, player names, ballot/toast paper background. |
| `--parchment-dim` | `oklch(0.84 0.045 82)` | `#D9C8AA` | Dimmer parchment: narrator text, quote text, ballot gradient bottom stop. |
| `--ink` | `oklch(0.24 0.03 60)` | `#2A1C10` | Dark warm brown "ink" — text ON parchment/amber (CTA button label, toast text, ballot text). Aliased `--text-dark`. |
| `--ink-soft` | `oklch(0.36 0.035 55)` | `#4C382B` | Softer ink for secondary text on parchment (vote count on ballots, info-toast icon). |

### Text

| Token | oklch | Hex | Role |
|---|---|---|---|
| `--text` | `oklch(0.93 0.02 85)` | `#EEE7D9` | Default body text on dark. |
| `--text-secondary` | `oklch(0.67 0.03 80)` | `#9F9481` | Secondary text, labels, meta rows. |
| `--text-faint` | `oklch(0.50 0.025 80)` | `#6B6253` | Hints, placeholders, timestamps, spent torches, disabled category rule fallback. |

### Lines & hairlines

| Token | Value | Role |
|---|---|---|
| `--line` | `oklch(1 0 0 / 0.09)` = white @ 9% | Standard 1px hairline border everywhere (panels, chips, rows, header bottom border). Aliased `--glass-border`. |
| `--line-strong` | `oklch(1 0 0 / 0.16)` = white @ 16% | Stronger border: inputs, cards, modal, secondary buttons, spinner ring. |

### Semantic

| Token | oklch | Hex | Role |
|---|---|---|---|
| `--danger` | `oklch(0.58 0.19 28)` | `#D33C33` | Destructive actions, offline dot, camp-menu danger items, Camp Raid mark. |
| `--success` | `oklch(0.62 0.13 150)` | `#429C5A` | Success toasts border, online network dot, copied-code color, success button. |
| `--warning` | `oklch(0.76 0.14 80)` | `#DFA635` | Warning toasts, reconnecting dot, error-boundary icon. |
| `--info` | `oklch(0.68 0.09 210)` | `#4AA7B7` | Info semantic (rarely used; info button is styled like secondary). |
| `--jury-gold` | `oklch(0.78 0.13 90)` | `#D8B349` | Jury/leader gold: crown icon, leader card border, necklace icon, victory subtitle, final-mode torch. |

### Shadows & glows (exact specs)

| Token | Value |
|---|---|
| `--shadow-sm` | `0 1px 2px oklch(0 0 0 / 0.35)` |
| `--shadow-md` | `0 6px 18px oklch(0 0 0 / 0.40)` |
| `--shadow-lg` | `0 14px 40px oklch(0 0 0 / 0.50)` |
| `--shadow-xl` | `0 24px 70px oklch(0 0 0 / 0.55)` |
| `--glow-torch` | `0 0 22px oklch(0.70 0.165 60 / 0.35)` (torch amber @ 35%, 22px blur, no offset) |
| `--glow-torch-strong` | `0 0 14px oklch(0.70 0.165 60 / 0.55), 0 0 44px oklch(0.70 0.165 60 / 0.25)` (double-layer) |
| `--glow-gold` | `0 0 24px oklch(0.78 0.13 90 / 0.4)` |

### Background scene layers

- **Torchlight radial** `--torchlight`: `radial-gradient(120% 55% at 50% -12%, oklch(0.42 0.10 55 / 0.42) → transparent 62%)`. Core color ≈ `#753B07` @ 42%. Painted above a `linear-gradient(180deg, var(--bg), var(--bg-deep))`, `background-attachment: fixed`.
- **Grain** (`body::before`): fixed full-screen overlay, `opacity: 0.05`, tiled 140×140px SVG `feTurbulence` fractalNoise (baseFrequency 0.9, 2 octaves). In SwiftUI: a static noise texture at 5% opacity over everything.
- **Vignette** (`body::after`): `radial-gradient(140% 100% at 50% 40%, transparent 40%, oklch(0 0 0 / 0.45) 100%)` — night presses in at the edges. Disabled in victory mode.
- `::selection` background: torch @ 35%.
- Background-color transitions over **900ms ease** when mode changes.

### Ceremony mode palettes (`body[data-mode=…]`)

**`council`** (tribal council — "the fire burns low and red"; set when `gameState.phase === 'tribal_council'`, ui.js `setBodyMode`):
- `--bg` `oklch(0.10 0.02 30)` `#080201`; `--bg-deep` `oklch(0.08 0.018 28)` `#040101`
- `--surface` `oklch(0.145 0.025 30)` `#130605`; `--surface-raised` `oklch(0.18 0.03 32)` `#1D0C09`; `--surface-sunken` `oklch(0.12 0.022 30)` `#0D0303`
- torchlight core: `oklch(0.40 0.14 35 / 0.5)` ≈ `#821E00` @ 50%
- `--line`: `oklch(0.75 0.1 45 / 0.14)` (warm-tinted hairline)

**`final`** (final tribal — jury gold; phase `final`/`final_tribal`):
- `--bg` `oklch(0.115 0.02 95)` `#070501`; `--bg-deep` `#030200`; `--surface` `#0F0B02`; `--surface-raised` `#181203`
- `--torch` becomes `--jury-gold` (`#D8B349`); `--flame-hot` becomes `oklch(0.86 0.13 95)` `#ECD065`
- torchlight core: `oklch(0.50 0.10 92 / 0.42)` ≈ `#786107` @ 42%
- `--line`: `oklch(0.85 0.1 90 / 0.13)`

**`victory`** (game finished — "dawn finally breaks"):
- `--bg` `oklch(0.32 0.06 55)` `#4A2A12` (noticeably lighter, warm dawn); `--bg-deep` `#2D1205`; `--surface` `#1A0B04`; `--surface-raised` `#251308`
- torchlight: bigger and brighter — `radial-gradient(130% 70% at 50% -18%, oklch(0.85 0.11 80 / 0.65) [`#F4C677`], oklch(0.62 0.13 55 / 0.25) [`#C16E2D`] 55%, transparent 75%)`
- `--vignette: none` (the night lifts)

### Significant hard-coded colors

- **Player identity colors** (avatar/ballot/dot backgrounds; ui.js `PLAYER_COLORS` + color-grid in HTML): `#FF6B6B` Red, `#4ECDC4` Teal, `#45B7D1` Blue, `#96CEB4` Sage, `#FFEAA7` Yellow, `#DDA0DD` Plum, `#98D8C8` Mint, `#F7DC6F` Gold. Fallback when missing: `#666`. Avatar initial text color on these: `oklch(0.18 0.02 60)` ≈ `#180F09`.
- **Confetti colors** (narrator.js — "Embers and gold — victory at dawn, not a birthday party"): `#e89a4a`, `#f2c14e`, `#c96a2f`, `#f6e3b4`, `#a94e24`, `#ffd98a`.
- **Ballot "X" overlay stroke** on a selected vote target: `#8a2b18` (dried-blood red, drawn as SVG X).
- **Eliminated red text** (VOTED OUT badge, eliminated names): `oklch(0.75 0.16 30)` ≈ `#FF826F`.
- Rock (bag meter): gray `oklch(0.6 0.01 90)` `#82807A`; the purple rock `oklch(0.5 0.16 305)` `#7945AB` with `0 0 6px` purple glow.
- Card-info button bg: black @ 30%. Vote bar track: black @ 35%. Modal backdrop: black @ 65% + 3px blur. Dramatic-pause overlay: black @ 72%.
- Settings screen (legacy, un-tokenized): seg-btn pressed text `#1a1108`, `.settings-danger` `#e0705a`, row divider `rgba(255,255,255,0.06)`, seg border `rgba(255,255,255,0.14)`.
- HTML `theme-color`: `#141d1a`. Favicon torch fill: `#e89a4a`.
- Toast icon tints: success `oklch(0.45 0.12 150)` `#09672E`, error `oklch(0.5 0.19 28)` `#B71A18`, warning `oklch(0.55 0.13 80)` `#996700`.
- `--ash` fallback (locked-card label): `oklch(0.72 0.02 60)` `#AEA298`.
- Story overlay scrim: `oklch(0.1 0.02 260 / 0.55)` (cool navy-black @ 55%) + 2px backdrop blur.

---

## §Typography

### Families (resolved values)

| Token | Stack | Loaded weights (Google Fonts) |
|---|---|---|
| `--font-display` | `"Fraunces", Georgia, "Times New Roman", serif` | Variable font: optical size 9–144, weight 400–900, roman + italic. Uses variation axes `SOFT` and `WONK`. |
| `--font-body` | `"Alegreya Sans", -apple-system, "Segoe UI", sans-serif` | 400, 500, 700, 800 + italic 400. |
| `--font-label` | `"Alegreya Sans SC", "Alegreya Sans", -apple-system, sans-serif` | 500, 700, 800. **This is a true small-caps font** — every "label" in the app renders as letter-spaced small caps without needing `text-transform` (SwiftUI: use Alegreya Sans SC, or `.smallCaps()` on Alegreya Sans, plus tracking). |

Google Fonts URL: `family=Fraunces:ital,opsz,wght@0,9..144,400..900;1,9..144,400..900&family=Alegreya+Sans:ital,wght@0,400;0,500;0,700;0,800;1,400&family=Alegreya+Sans+SC:wght@500;700;800`

### Size scale (rem = 16px base; clamps are viewport-fluid)

| Token | Value | ≈ px at 390pt phone |
|---|---|---|
| `--display-xl` | `clamp(2.7rem, 1.9rem + 4vw, 4.2rem)` | ~56px (43–67 range) |
| `--display-lg` | `clamp(2rem, 1.55rem + 2.2vw, 2.9rem)` | ~33px |
| `--display-md` | `clamp(1.45rem, 1.25rem + 1vw, 1.9rem)` | ~24px |
| `--display-sm` | `clamp(1.15rem, 1.05rem + 0.5vw, 1.4rem)` | ~19px |
| `--font-size-lg` | `clamp(1.05rem, 1rem + 0.3vw, 1.2rem)` | ~17px |
| `--font-size-base` | `clamp(0.95rem, 0.9rem + 0.25vw, 1.05rem)` | ~15.5px |
| `--font-size-sm` | `0.84rem` | 13.4px |
| `--font-size-xs` | `0.72rem` | 11.5px |

Body: `--font-body` at `--font-size-base`, `line-height: 1.5`. Headings `line-height: 1.12`.

### Letter-spacing tokens

- `--track-label: 0.14em` — standard label tracking (buttons, form labels, chips, phase pills).
- `--track-wide: 0.22em` — extra-wide (eyebrows, taglines, tribe label, loading text, card category).
- Others: badge wordmark 0.05em; big game code 0.08em; game-code input 0.3em; access-code input 0.18em; player-status 0.06em; wordmark h1 0.01em.

### Key role recipes (exact)

- **Wordmark H1 ("SURVIVOR", start screen)**: Fraunces 900, `--display-xl`, `font-variation-settings: "SOFT" 30, "WONK" 1`, letter-spacing 0.01em, color parchment, text-shadow `0 0 60px torch@35%, 0 4px 30px black@70%`.
- **Screen titles** (`.screen-title`): Fraunces weight **850**, `--display-lg`, `"SOFT" 40, "WONK" 1`, parchment, `text-shadow: 0 2px 24px black@60%`, `text-wrap: balance`, and **negative bottom margin -0.42em so the oversized title overlaps the panel below it** (signature editorial layout move).
- **Ceremony titles** (`.ceremony-title`): Fraunces 900 **italic**, `--display-lg`, `"SOFT" 60, "WONK" 1`, text-shadow `0 0 50px torch@30%`.
- **Eyebrow** (kicker above titles): label font 700, `--font-size-xs`, tracking 0.22em, color torch, followed by a 1px gradient rule (`torch@50% → transparent`) filling the remaining row width.
- **Buttons**: label font (small caps) 700, `--font-size-sm` (0.84rem), tracking 0.14em.
- **Form labels**: label font 700, xs, tracking 0.14em, text-secondary.
- **Chips (header)**: label font, xs, tracking 0.14em; strong content in torch color 700.
- **Big game code** (`.game-code-large`): Fraunces 900, `--display-xl`, `"SOFT" 50`, tracking 0.08em, color flame-hot, text-shadow `0 0 40px torch@50%`, line-height 1.05.
- **Card name**: Fraunces 700, 1.02rem (mini grid: 0.88rem), line-height 1.15, parchment, balanced wrap. **Card category**: label 700, 0.6rem (mini: 0.54rem), tracking 0.22em, text-faint. **Card description**: body 0.7rem, lh 1.35, text-secondary, clamped to 4 lines.
- **Narrator line**: Fraunces *italic*, `--font-size-sm`, parchment-dim. Quotes/leader phrases: Fraunces italic `--font-size-lg` with torch-colored curly quote marks.
- **Vote count number**: Fraunces 900, 1.7rem, flame-hot. Its "votes" label: label font 0.6rem, tracking 0.14em, text-faint.
- **Turn steps** (STEAL → PLAY → DRAW pills): label 700, xs, tracking 0.14em; done step gets line-through; current step is an amber pill.
- **Elimination heading** ("The Tribe Has Spoken"): Fraunces 900 italic, `--display-md`.

### Text-transform patterns

Most "uppercase" looks come free from Alegreya Sans SC small caps. Explicit `text-transform: uppercase` appears on: game-code input, camp-menu item titles, HOF dates, card-sheet timing labels + phase pills, cardname category/locked tags, RPS labels, `card-mini-now` badge, settings section headers. Explicit `lowercase` on the access-gate input. Player-facing body copy is sentence case; ritual/label layer is small-caps + tracked.

---

## §Animations

All 13 keyframes with definitions, timing, and triggers (class-application points verified in ui.js/game.js/narrator.js/index-optimized.html).

### 1. `torchFlicker` — the living flame
```css
@keyframes torchFlicker {
  0%, 100% { opacity: 1;    transform: scale(1); }
  18%      { opacity: 0.86; }
  42%      { opacity: 0.96; transform: scale(1.03); }
  50%      { opacity: 0.78; transform: scale(0.985); }
  74%      { opacity: 0.94; }
}
```
Irregular opacity dips (down to 0.78) with tiny scale wobble (0.985–1.03) — reads as candle flicker. Ease-in-out, infinite, always on flame-colored icons that also carry an amber `drop-shadow` glow. Usage and durations:
- `.header .torch` (top bar torch icon, 20px): **3.2s** infinite; `drop-shadow(0 0 6px torch@60%)`.
- `.wordmark .icon-torch-big` (44px start-screen torch): **3.2s**; `drop-shadow(0 0 14px torch@70%)`.
- `.ceremony .icon-ceremony` (52px tribal icon): **2.6s** (faster = more urgent); `drop-shadow(0 0 18px torch@70%)`.
- `.torch-lit` (life-token torch icons in rows): **3s**; second torch gets `animation-delay: -1.4s` so lives don't flicker in sync; `drop-shadow(0 0 4px torch@70%)`.
- `.reactive-banner-flame .icon` (Camp Raid waiting banner): **2.4s**.
Disabled entirely under reduced motion.

### 2. `smokeDrift` — the spent torch
```css
@keyframes smokeDrift {
  0%, 100% { transform: translateY(0) rotate(0deg);      opacity: 0.55; }
  50%      { transform: translateY(-1.5px) rotate(4deg); opacity: 0.38; }
}
```
Trigger: `.torch-spent` (a lost life's smoke-wisp icon, colored `--text-faint`): **5s ease-in-out infinite**. A barely-there 1.5px rise + 4° sway at ~half opacity — smoke, not fire.

### 3. `torchSnuff` — elimination
```css
@keyframes torchSnuff {
  0%   { filter: brightness(1) saturate(1);                 transform: scale(1); }
  30%  { filter: brightness(1.4) saturate(1.3);             transform: scale(1.02); }  /* flare up */
  100% { filter: brightness(0.3) saturate(0) grayscale(1);  transform: scale(0.96); opacity: 0.45; }  /* die to gray */
}
```
The torch *flares* before it dies. Two triggers:
- `.torch-snuff-icon` in the results screen's elimination announcement: **1.6s ease both**, with inline `animation-delay: (500 + ballotCount×320 + 250)ms` so it fires after the last ballot flips (ui.js `updateResultsScreen`).
- `.torch-snuff-animation` added to the eliminated player's row by narrator.js `AnimationManager.animateTorchSnuff(playerId)` on the `elimination` game event: **1.6s ease both**; class removed after 2000ms, then `.eliminated` (opacity 0.45, strikethrough name) is applied permanently. Accompanied by the `torch_snuff` sound.

### 4. `riseIn` — content entering the light
```css
@keyframes riseIn {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
```
- **Screen-change stagger** (the signature transition): `.screen.active > *` animates **420ms `cubic-bezier(0.22, 1, 0.36, 1)` both** (a strong ease-out "quint-like" curve); children 2–5 delayed 60/120/180/240ms. Applied automatically whenever ui.js `showScreen()` toggles `.active`.
- `.modal-content`: **260ms ease both** on every modal open.
- `.elimination-announcement`: **700ms ease both** with inline `--announce-delay`/`animation-delay` = `500 + resultCount×320`ms.

### 5. `fadeIn` — soft entrance
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
```
Utility class `.fade-in` = **300ms ease both**. Applied by ui.js to: newly-activated screens (`showScreen`), the modal overlay (`showModal`), toasts (`showToast`, paired with `.fade-out` = opacity 0 over 300ms before removal). Also used directly: `.reveal-row` (challenge reveal list) **0.35s ease backwards** staggered 0.15s per row (rows 2–6: 0.15/0.3/0.45/0.6/0.75s); `.reactive-banner` **0.3s ease**.

### 6. `ballotFlip` — reading the votes
```css
@keyframes ballotFlip {
  0%   { opacity: 0; transform: perspective(700px) rotateX(70deg)  translateY(18px); }
  60%  { opacity: 1; transform: perspective(700px) rotateX(-8deg) translateY(0); }    /* overshoot */
  100% { opacity: 1; transform: perspective(700px) rotateX(0deg)  translateY(0); }
}
```
A parchment ballot flipping face-up with 3D perspective (700px) and a −8° overshoot. Trigger: every `.vote-result-card` on the results screen: **560ms `cubic-bezier(0.22, 1, 0.36, 1)` both**, with inline `animation-delay: i × 320ms` per card (ui.js: "Ballots flip in one at a time — the reveal is a ceremony"). The result **bar** inside then grows via `transition: width 900ms cubic-bezier(0.22, 1, 0.36, 1)`.

### 7. `turnPulse` — "it's your turn" ring
```css
@keyframes turnPulse {
  0%   { box-shadow: 0 0 0 0    oklch(0.70 0.165 60 / 0.55); }
  100% { box-shadow: 0 0 0 22px oklch(0.70 0.165 60 / 0); }
}
```
An expanding amber ring (0 → 22px spread, fading 55% → 0). Trigger: `.phase-guidance.your-turn` — ui.js `updatePhaseGuidance` adds `your-turn` when `isMyTurn && phase === 'playing'`: **1.6s ease-out, 2 iterations** (pulses twice, then rests). The guidance text simultaneously turns flame-hot.

### 8. `pulseHighlight` — attention ping
```css
@keyframes pulseHighlight {
  0%   { box-shadow: 0 0 0 0    oklch(0.70 0.165 60 / 0.7); }
  70%  { box-shadow: 0 0 0 18px oklch(0.70 0.165 60 / 0); }
  100% { box-shadow: 0 0 0 0    oklch(0.70 0.165 60 / 0); }
}
```
Same idea as turnPulse but stronger start (70%), 18px spread, resolved by 70%. Class `.pulse-highlight` = **1s ease-out, 1 iteration**; applied by narrator.js `AnimationManager.pulseElement(elementId)` (adds class, removes after 1000ms). Note: `pulseElement` has **no active caller in the deployed build** — it is exposed API (available to `narrate(msg, {animation})`), so treat as an available effect, not a wired moment.

### 9. `voteSlam` — the vote card slammed on screen
```css
@keyframes voteSlam {
  0%   { transform: translate(-50%, -50%) scale(0)    rotate(-10deg); opacity: 0; }
  20%  { transform: translate(-50%, -50%) scale(1.2)  rotate(5deg);   opacity: 1; }  /* slam + overshoot */
  40%  { transform: translate(-50%, -50%) scale(1)    rotate(0deg); }
  100% { transform: translate(-50%, -50%) scale(0.85);                opacity: 0; }  /* linger, shrink away */
}
```
Trigger: narrator.js `AnimationManager.voteSlam(targetName)` creates a fixed, centered `.vote-slam` element (Fraunces 900 italic 2.4rem, parchment on `--surface-raised`, 1px torch border, radius 10px, `--shadow-xl` + `--glow-torch-strong`, padding 0.8rem 1.6rem): **1.5s ease both**, element removed after 1500ms. Also **no active caller in the deployed build** — available API for the vote-reveal moment.

### 10. `confettiFall` — victory embers
```css
@keyframes confettiFall {
  0%   { transform: translateY(-4vh)  rotate(0deg);   opacity: 1; }
  100% { transform: translateY(104vh) rotate(680deg); opacity: 0; }
}
```
Trigger: narrator.js `AnimationManager.showConfetti()` on **winner** (called from `narrateWinner`, fired on the `winner` event and phase → `finished`). Spawns **150** `.confetti-piece` divs: 9×14px, radius 2px, `top: -3vh`, random `left: 0–100%`, colors from the ember/gold set (`#e89a4a #f2c14e #c96a2f #f6e3b4 #a94e24 #ffd98a`), base animation **3.4s ease-in forwards** but each piece gets inline `animation-duration: 2–4s` (random) and `animation-delay: 0–3s` (random). Container removed after 6s. Pieces spin ~1.9 full turns while falling past the bottom. Hidden under reduced motion.

### 11. `spin` — loading
```css
@keyframes spin { to { transform: rotate(360deg); } }
```
Trigger: `.loading-spinner` inside the full-screen `.loading-overlay` (shown by ui.js `showLoading(text)`): 42px circle, 3px ring in `--line-strong` with `border-top-color: var(--torch)`, plus `--glow-torch` — "a torch being lit". **0.9s linear infinite**.

### 12. `emberFloat` — rising ember
```css
@keyframes emberFloat {
  0%   { transform: translateY(0)      translateX(0)   scale(1);   opacity: 0.9; }
  100% { transform: translateY(-46vh)  translateX(6vw) scale(0.4); opacity: 0; }
}
```
An ember drifting up 46% of the viewport, sideways 6vw, shrinking to 0.4 and fading. **Defined but not referenced by any selector or JS in the deployed build** — reserved/unused. If porting for parity, treat as an optional ambient particle effect (e.g., embers rising off the torchlight).

### 13. `stepGlow` — breathing glow
```css
@keyframes stepGlow {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.55; }
}
```
A simple opacity breath. Four triggers:
- `.turn-steps .step.now` (the active STEAL/PLAY/DRAW pill): **2.2s ease-in-out infinite**.
- `.narrator-cursor` (the ▋ typewriter cursor): **1s steps(2) infinite** — steps(2) makes it a hard blink, not a fade.
- `.status-reconnecting .network-status-dot`: **0.8s ease-in-out infinite**.
- `.dramatic-dots` ("..." in the dramatic-pause overlay, Fraunces 3rem torch, 0.3em tracking): **1s ease-in-out infinite**. (The overlay itself, via `AnimationManager.dramaticPause()`, has no active caller in the deployed build.)

### Reduced motion
Two mechanisms: `@media (prefers-reduced-motion: reduce)` forces all durations to 0.01ms and kills flicker/confetti; and an in-app setting `html.reduce-motion` forces 0.001s durations (deliberately non-zero so animation-end handlers still fire). SwiftUI equivalent: respect `accessibilityReduceMotion` plus an in-app toggle.

### Micro-interaction transitions (not keyframes, but part of the motion language)
- Buttons: `transform 120ms ease, box-shadow 200ms, filter 200ms`; `:active` = `translateY(1px) scale(0.99)` with reduced inset highlight.
- Hand cards: `transform 160ms ease`; `.playable` floats `translateY(-4px)` (hover −7px); `.pressing` = `translateY(-2px) scale(0.97)`.
- Toggle thumb: `transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1)` — springy overshoot (SwiftUI: `.spring(response:0.3, dampingFraction:0.6)`-ish).
- Story drawer: `transform 0.28s cubic-bezier(0.32, 0.72, 0.22, 1)` slide from right; overlay fades 0.25s.
- Vote targets: `transform 150ms`; hover straightens rotation and lifts −3px; selected scales 1.03.
- Color swatch: hover scale 1.08, selected scale 1.1.
- Rows/list items: press feedback `scale(0.985)`–`scale(0.94)` depending on element.
- Haptics accompany taps (ui.js `hapticFeedback`): light [10], medium [30], heavy [50], success [10,50,10], error [100,50,100], warning [50,30,50] (ms vibration patterns). Heavy on card play/vote cast; success on copy/share.

---

## §Components

### App shell / layout
- Content column: max-width **560px** (720px ≥768px viewport), centered, min-height 100dvh, flex column. Main padding: `1.1rem 1rem calc(1.5rem + safe-area-bottom)`.
- Radius scale: `--radius-sm 6px`, `--radius-md 10px`, `--radius-lg 16px`, `--radius-xl 22px`, `--radius-full 9999px`. Spacing scale: xs 4px, sm 8px, md 16px, lg 24px, xl 36px. Min touch target **48px** (`--touch-target-min`).

### Top bar (`.header`)
One slim "ritual bar": flex row, gap 0.6rem, padding `0.65rem 1rem 0.6rem`, **1px bottom border `--line`**, no background of its own (sits on the page's torchlit ground).
- Left: 20×20 torch icon in `--torch`, `drop-shadow(0 0 6px torch@60%)`, `torchFlicker 3.2s` infinite.
- Wordmark badge "SURVIVOR": Fraunces 800, 1.05rem, tracking 0.05em, parchment.
- Right cluster (`.game-info`, pushed with margin-left auto): pill **chips** — label font xs, tracking 0.14em, text-secondary; each chip: padding `0.2rem 0.55rem`, 1px `--line` border, full radius, `--surface-sunken` bg, ellipsized at 9rem max. Game-code chip shows `FIRE <code>` with code in torch 700. Icon chips (story scroll, settings gear, camp menu): same pill, icon 1.05rem, hover/focus turns icon+border torch, `:active scale(0.94)`.

### Buttons
**Primary CTA (`.btn`)** — "carved, warm-lit":
- Label font (small caps) 700, 0.84rem, tracking 0.14em; text color `--ink` (#2A1C10) — dark text on amber.
- Background: `linear-gradient(180deg, #F9AD26 (flame-hot), #E68100 (torch) 55%, oklch(0.60 0.16 52)≈#C75E00)` — three-stop vertical flame gradient.
- Border: 1px `oklch(0.55 0.14 50)` ≈ `#B0540E`.
- Box-shadow: `inset 0 1px 0 white@35%` (top bevel) + `--shadow-sm` + `--glow-torch` (0 0 22px torch@35%). The CTA literally glows.
- Radius **10px**, min-height 48px, padding `0.7rem 1.25rem`, inline-flex centered, gap 0.5rem.
- Hover `brightness(1.06)`; active `translateY(1px) scale(0.99)` + inset drops to white@20%, glow removed; disabled opacity 0.45 + `saturate(0.5)`, no shadow; focus-visible: 2px flame-hot outline offset 2px.

**Secondary (`.btn-secondary`)**: parchment text; `linear-gradient(180deg, --surface-raised, --surface-sunken)`; 1px `--line-strong` border; `inset 0 1px 0 white@6%` + shadow-sm. Hover: border becomes torch@50% (no brightness change). `.btn-info` styled identically.

**Success**: text `#041107`; gradient `#5CB572 → #429C5A`; border `#2B7440`; inset white@30%.
**Danger**: text `#FCEAE7`; gradient `#E24A3F → #AC1B18`; border `#901211`; inset white@20%.
**Warning**: ink text; gradient `#EBBD57 → #DFA635`; border `#A4780E`.
**Ghost (`.btn-ghost`)**: transparent, **1px dashed** `--line-strong` border, text-secondary, no shadow.
**Small (`.btn-sm`)**: min-height 40px, padding `0.4rem 0.85rem`, xs font.

### Panels (`.panel`) — "the lit panel"
`linear-gradient(180deg, --surface-raised, --surface 22%)` (a subtle lit top edge), 1px `--line` border, radius **22px**, padding `2.1rem 1.15rem 1.25rem` (extra top padding receives the overlapping screen title), `--shadow-lg`. Stacked panels separated 16px. Screen head above uses eyebrow + oversized title with `margin-bottom: -0.42em` overlapping the panel.

### Playing cards
**Hand card (`.card-button`)**: aspect ratio **3 : 4.1**, radius **14px**, padding `0.75rem 0.7rem 0.7rem`, background = `linear-gradient(180deg, white@4.5%, transparent 30%)` over `--surface-raised` (sheen at top), border 1px `--line-strong`, `--shadow-md`. A **4px category rule across the top** (`::before`), gradient per category:
- action: `90deg #579766 → #237356` (green)
- tribal_advantage: `90deg #D8B349 → #C48225` (gold)
- vote: `90deg #DDCCA9 → #AD9D7B` (parchment)
- challenge: `90deg #F3821D → #D84A00` (fire)
States: `.playable` = torch@55% border + glow-torch + floats `translateY(-4px)`; `.locked` = opacity 0.45, `saturate(0.35)`; `.pressing` = `translateY(-2px) scale(0.97)`. Info button: 26px circle top-right, black@30% bg, 1px line border.
**Hand grid minis (`.card-mini`, current layout)**: auto-fill grid, min column 104px, gap 0.55rem; min-height 84px, radius **11px**, padding `0.55rem`; category 0.54rem, name 0.88rem; badge row at bottom (idol/eye icons 0.8rem in text-faint) + `NOW` pill (0.56rem label, torch text, border `torch@55%`, full radius). Grid bottom padding `calc(4.5rem + safe-area)` to clear the sticky action bar.
**Card sheet** (detail modal content): same 4px category rule (rounded, full radius) at top; description at base size lh 1.5; phase pills: label xs, tracking 0.14em, uppercase, torch text, 1px border `torch@45%`, full radius, padding `0.12rem 0.55rem`; full-width Play button.

### Vote ballots (`.vote-target`) — parchment against the night
2-column grid, gap 0.7rem. Each: `linear-gradient(174deg, --parchment, --parchment-dim)`, ink text, radius **6px** (paper, not pill), no border, padding `0.9rem 0.75rem 0.8rem`, min-height 92px, `--shadow-md`, **rotated ±~1°** (odd −0.8°, even +0.9°) like scattered slips. Player avatar 38px circle in player color. Name: Fraunces 700 1.05rem ink. Selected: `0 0 0 3px var(--torch)` ring + shadow-lg + glow-torch, straightens and scales 1.03, and a **44px red X** (`#8a2b18` SVG strokes) stamps over the center at 85% opacity. Vote chips (`.vote-chip`, "your votes"): small parchment slips, radius 3px, rotate −1.2°/+1.4° alternating, ink 700 text; `.spent` = 35% opacity + line-through.

### Vote results (`.vote-result-card`)
`--surface-sunken` bg, 1px `--line`, radius 16px, padding `0.8rem 0.9rem`, ballotFlip entrance (see §Animations). Eliminated variant: border `danger@50%`, bg `linear-gradient(180deg, danger@10%, --surface-sunken 60%)`. Progress bar: 7px track (black@35%, full radius) with fill `linear-gradient(90deg, --ember, --torch)` + `0 0 10px torch@60%` glow, width animates 900ms; eliminated fill: `90deg oklch(0.45 0.17 28)→oklch(0.6 0.19 30)` (reds).

### Modal (`dialog.modal-overlay` + `.modal-content`)
Backdrop: black@65% + `backdrop-filter: blur(3px)`. Content: width `min(420px, 92vw)`; `linear-gradient(180deg, --surface-raised, --surface 30%)`; 1px `--line-strong` border **plus a 3px solid torch top border** (the signature "lit edge"); radius **16px**; `--shadow-xl` + `--glow-torch`; padding `1.25rem 1.1rem 1.1rem`; enters with riseIn 260ms. Title: Fraunces 800 `--display-sm` parchment. Close: 34px circle, `--surface-sunken` bg, 1px line border, top-right 10px.

### Story drawer (slide-over history)
Overlay: `oklch(0.1 0.02 260 / 0.55)` + 2px blur, fade 0.25s. Drawer: fixed right, `width: min(88vw, 380px)`, full height, `--bg-deep` bg, 1px left border `--line`, shadow `-18px 0 40px black@45%`, slides `translateX(102%) → 0` over 0.28s `cubic-bezier(0.32, 0.72, 0.22, 1)`. Header row with 1px bottom border; list is column-reverse (newest at top), items: padding `0.5rem 0.65rem`, 1px line border, radius 10px, `white@3%` bg, 0.86rem text-secondary, timestamps 0.7rem text-faint tabular-nums.

### Inputs (`.form-input`)
`--surface-sunken` bg, 1px `--line-strong` border, radius **10px**, min-height 48px, padding `0.65rem 0.9rem`, `--text` color, **caret-color torch**. Focus: border torch + `--glow-torch` (no default outline). Placeholder text-faint. Game-code input: label font, tracking 0.3em, uppercase, 700. Access-gate input: centered, 1.15rem, tracking 0.18em, lowercase.

### Toggle switch (`.checkbox-row input[type=checkbox]`)
Row: 1px line border, radius 10px, `--surface-sunken` bg, min-height 48px. Switch: **46×26px** pill, `--surface-raised` track, 1px `--line-strong`; thumb 20px circle in text-secondary, offset 2px. Checked: track `--ember-deep` (#7C1403), border torch, `--glow-torch`; thumb `translateX(20px)` and turns `--flame-hot`; thumb moves with spring `cubic-bezier(0.34, 1.56, 0.64, 1)` 200ms. The row's leading icon turns torch when checked.

### Segmented control (`.segmented`)
2-col grid, 4px gap and padding, `--surface-sunken` track, 1px line border, radius 10px; buttons min-height 44px, radius 7px (10−3), label font xs 700 tracked, text-secondary. Pressed: `linear-gradient(180deg, --surface-raised, --surface)` bg, parchment text, `inset 0 0 0 1px torch@55%` ring + `--glow-torch`; sub-caption turns torch.

### Toasts — parchment slips
`--parchment` bg, ink text, radius **4px**, `--shadow-lg`, padding `0.65rem 0.9rem`, max-width 320px, 0.84rem/500, **4px left border in torch** (success/error/warning variants recolor it to their semantic color), rotated **−0.5°**. Enter `.fade-in` 300ms, exit `.fade-out`.

### Player rows / avatars
Rows (`.player-card`/`.lives-row`): flex, min-height 48px, padding `0.6rem 0.8rem`, `--surface-sunken` bg, 1px line, radius **16px**. Avatars: 34px (30px lives-dot, 38px ballot) circles filled with the player's identity color, initial letter in label font 800 0.95rem colored `#180F09`, `2px black@35%` border, `inset 0 -4px 8px black@25%` (bottom-shaded sphere). States: `.me` = line-strong border + `--surface` bg; `.current-turn`/`.steal-target` = border torch@55–60% + `--glow-torch` (steal targets also press-scale 0.985 and show a torch-colored STEAL hint); `.leader` = jury-gold@40% border; `.eliminated` = 45% opacity + strikethrough name. Lives shown as drawn torch icons: lit = torch color + glow + flicker; spent = smoke icon in text-faint + smokeDrift.

### Turn ribbon
Centered: current player name in Fraunces 700 `--display-sm` (yours = flame-hot + `0 0 26px torch@45%` glow). Below, the STEAL → PLAY → DRAW step pills: label xs 700 tracked, text-faint; done = text-secondary + line-through; **now** = ink text on `linear-gradient(180deg, flame-hot, torch)` pill, border `oklch(0.55 0.14 50)`, glow-torch, breathing via stepGlow 2.2s.

### Phase guidance ("a note pinned by the fire")
Flex row: 1px line border with **3px torch left border**, radius 10px, `--surface-sunken` bg, padding `0.55rem 0.85rem`; torch-colored 20px icon; title in label xs 700 tracked parchment; action line xs text-secondary. Your-turn: border torch@60%, turnPulse ×2, title flame-hot.

### Challenge panel ("the orange card")
`linear-gradient(180deg, torch@10%, transparent 45%)` over `--surface`; border 1px torch@45% with **4px solid torch top border**; radius 16px; `--shadow-md` + `--glow-torch`. Bag-meter rocks: 11px blobs with irregular border-radius `46% 54% 52% 48% / 55% 48% 52% 45%`, gray `#82807A` (purple variant `#7945AB` + glow), inset bottom shading.

### Other components (brief exact specs)
- **Eyebrow rule**: 1px `linear-gradient(90deg, torch@50%, transparent)` filling after the label; tagline flanking rules: 2.4rem × 1px fading toward/away.
- **Wordmark/code hero**: tap-to-copy; `.copied` state (wired in index-optimized.html inline script, 1200ms) turns the giant code `--success` with green glow `0 0 40px success@50%`.
- **Color picker**: 48px circles, 2px black@40% border, `inset 0 -6px 12px black@30%`; selected: `0 0 0 3px var(--bg), 0 0 0 5px var(--torch)` double ring + glow + scale 1.1 + white check mark (masked SVG).
- **Camp menu items**: full-width rows, `--surface-sunken`, 1px line, radius 10px; leading torch icon 1.35rem; title label small caps + uppercase; hover = torch border + raised bg; danger variant mixes `--danger` 45% into border, danger icon/title, hover bg `color-mix(danger 10%, surface-sunken)`.
- **Hall of Fame**: rows like camp menu; rank in Fraunces 700 1.1rem text-faint; win count Fraunces 1.25rem torch; champion row: torch border + `linear-gradient(100deg, color-mix(torch 14%, surface-sunken), surface-sunken 65%)`.
- **Target/RPS/finger pickers** (modals): options on `white@3–4%` bg, 1px `white@8–10%` border, radius 10–16px; hover/focus = torch border + `oklch(0.65 0.18 55 / 0.10–0.12)` amber tint bg, lift −2px; active scale 0.96–0.98.
- **Reactive banner** (Camp Raid wait): fixed bottom-center pill, `oklch(0.13 0.02 60 / 0.94)` bg, border `oklch(0.65 0.18 55 / 0.5)`, full radius, shadow-lg. (Bug note: it references undefined `--shadow-glow-torch`; the intended token is `--glow-torch` — in a port, give it the torch glow.)
- **Network status**: 8px dot — green + green glow online, danger offline, warning + stepGlow 0.8s reconnecting.
- **Card tooltip**: `--bg-deep` bg, 1px line-strong, radius 10px, `--shadow-xl`, width min(300px, 88vw), non-interactive.
- **Action bar**: sticky bottom, background `linear-gradient(180deg, transparent, --bg-deep 38%)` (content fades into night under the buttons), buttons stretch equally.
- **Loading overlay**: full-screen `--bg-deep`; spinner (see §Animations) + label small caps tracked 0.22em.
- **Icons**: single hand-drawn SVG sprite (`#i-torch`, `#i-torch-out`, `#i-ballot`, `#i-idol`, `#i-necklace`, `#i-rock`, `#i-skull`, `#i-crown`, `#i-eye`, `#i-cards`, `#i-swap`, `#i-bot`, …) — 24×24 viewBox, stroke-based (~1.7–1.8 stroke width, round caps/joins), `currentColor`. No emoji anywhere in chrome ("hand-cut marks, no emoji chrome"). Standard inline icon size 1.1em, valigned −0.18em.
- **Text-size setting**: `html.text-large` = 110% root font, `html.text-xl` = 122% — everything is rem-based so the whole UI scales (SwiftUI: Dynamic Type does this natively).

---

## §Sound

All game sounds are **synthesized live with the Web Audio API** in narrator.js `SoundManager` — no audio files. Master gating: skipped if the device-level setting `SurvivorSettings.soundOn()` is false, or the narrator's own mute (persisted in `localStorage.survivorSoundMuted`) is on. In SwiftUI, reproduce with AVAudioEngine/AVAudioSourceNode or pre-render these exact recipes to short samples.

### 1. `tribal_gong` (`_playGong`) — deep gong
- **Synthesis**: single oscillator (default type = **sine**), frequency **80 Hz → exponential ramp → 40 Hz over 2.0s**.
- **Gain**: starts **0.5**, exponential decay to 0.01 over 2.0s. Duration **2.0s**.
- **Plays on**: game start (phase → `playing`), Tribal Council card drawn (phase → `tribal_announcement`), and the `tribal_start` event ("Come on in, guys!").

### 2. `torch_snuff` (`_playSnuff`) — sizzle/whoosh
- **Synthesis**: **white-noise buffer**, 1.5s long, amplitude pre-shaped by `exp(-i / (sampleRate × 0.3))` (≈300ms exponential decay envelope baked into the samples). Routed through a **lowpass BiquadFilter**: cutoff **3000 Hz → exponential ramp → 200 Hz over 1.5s** (the fire closing down to a hiss), then a gain node fixed at **0.4**.
- **Duration**: 1.5s buffer (audible tail ~0.5s due to baked decay).
- **Plays on**: the `elimination` event — simultaneous with the torchSnuff animation on the player's card.

### 3. `vote_reveal` (`_playDrum`) — dramatic drum hit
- **Synthesis**: single oscillator (sine), frequency **150 Hz → exponential ramp → 50 Hz over 0.2s** (classic kick-drum pitch drop).
- **Gain**: starts **0.6** (loudest cue), exponential decay to 0.01 over 0.3s. Duration **0.3s**.
- **Plays on**: phase → `tribal_reveal` ("I'll read the votes…").

### 4. `card_play` (`_playWhoosh`) — paper whoosh
- **Synthesis**: white-noise buffer **0.3s**, amplitude shaped by `sin(t·π) × 0.5` (smooth swell-and-fade envelope baked in). Routed through a **bandpass BiquadFilter** centered at **1000 Hz, Q = 1**. No extra gain node (unity).
- **Duration**: 0.3s.
- **Plays on**: `card_played` events (any card), including immunity-idol and idol-nullifier moments.

### 5. `victory` (`_playVictory`) — fanfare arpeggio
- **Synthesis**: four **triangle** oscillators playing **C5 523.25 Hz, E5 659.25 Hz, G5 783.99 Hz, C6 1046.50 Hz**, one note every **150 ms** (note i starts at `i × 0.15s`).
- **Gain per note**: 0 → linear ramp to **0.3** over 50ms (attack), then exponential decay to 0.01 by +0.5s. Each note lasts 0.5s; total ≈ 0.95s.
- **Plays on**: `winner` — fired together with the confetti drop.

### 6. `steal` (`_playSwoosh`) — quick descending zip
- **Synthesis**: single **sawtooth** oscillator, frequency **800 Hz → exponential ramp → 200 Hz over 0.15s**.
- **Gain**: starts **0.2**, exponential decay to 0.01 over 0.15s. Duration **0.15s** (the shortest, snappiest cue).
- **Plays on**: the `steal` event ("{thief} reaches into {victim}'s bag…").

### 7. `notification` (`_playNotification`) — soft ping
- **Synthesis**: single **sine** oscillator at a constant **880 Hz** (A5).
- **Gain**: starts **0.2**, exponential decay to 0.01 over 0.2s. Duration **0.2s**.
- **Plays on**: `vote_cast` ("{player} has voted.").

### Narration delivery (separate from sound — NOT speech synthesis)
narrator.js does **not** use `speechSynthesis`/TTS. The "narrator voice" is a **typewriter text effect**: messages type out at **30 ms per character** into the narrator panel (Fraunces italic, parchment-dim) with a blinking `▋` cursor (torch-colored, hard-blink via `stepGlow 1s steps(2) infinite`); the cursor lingers 500ms after the line completes, then hides. Lines queue (one at a time) with a 500ms pause between narrations; each finished line is prepended to a capped 50-entry history list with `HH:MM` timestamps. Commentary text is chosen at random from `NARRATOR_TEMPLATES` (Jeff-Probst-flavored lines per event: game_start, turn_start(_self), steal_success/blocked, card_play + idol/nullifier/steal-vote/extra-vote variants, tribal_drawn/start/advantage/discussion/voting/immunity, vote_reveal_*, elimination(+jury), final_tribal_*, winner, player_joined/left, game_reset) with `{placeholder}` interpolation.

# Part 2 — SwiftUI Mapping (iOS 17)

# TORCHLIT → SwiftUI (iOS 17.0 / Xcode 16) — Port Research

Companion to `torchlit-research-web.md` (the design-language extraction; that doc holds the exact
palette hex, type recipes, keyframe CSS, and Web Audio recipes). This doc is the **implementation
map**: for every motion/component/sound/font in that extraction, the concrete iOS-17 technique.

Target: **iOS 17.0 minimum**, Swift 6 strict concurrency (per `ios/project.yml`), pbxproj generated
by **xcodegen** from `ios/project.yml`. Every API below is iOS 17.0-or-earlier unless explicitly
tagged `⚠️ iOS 18+ (optional)`.

**Existing code this slots into:**
- `/Users/tylermcrae/Documents/GitHub/survivor-game/ios/SurvivorGame/Views/Components/SurvivorTheme.swift` — current (approximate, pre-torchlit) palette + `Background`. Replace its colors with the extraction's exact tokens.
- `/Users/tylermcrae/Documents/GitHub/survivor-game/ios/SurvivorGame/Views/Components/HapticEngine.swift` — `@MainActor enum HapticEngine` with static funcs, `isEnabled` gate on `UserDefaults` key `"hapticsEnabled"`. §Haptics extends this file's style.
- `/Users/tylermcrae/Documents/GitHub/survivor-game/ios/SurvivorGame/State/PlayerState.swift:189` — an existing `Color.init?(hex:)`. Reuse it; do **not** write a second one.
- `/Users/tylermcrae/Documents/GitHub/survivor-game/ios/SurvivorGame/Views/Cards/CardAnimations.swift` — existing ad-hoc `ViewModifier` animations; these get superseded by the keyframe/phase ports below.

**Greenfield note:** the project currently contains *zero* uses of `keyframeAnimator`,
`phaseAnimator`, `TimelineView`, `Canvas`, `Shader`, `CHHaptic*`, or `AVAudio*`. Nothing to migrate;
everything below is new surface.

---

## §Techniques

### 0. Shared groundwork (read first)

**CSS blur → SwiftUI shadow radius.** CSS `box-shadow: 0 Ypx Bpx color` maps empirically to
`.shadow(color:, radius: B/2, x: 0, y: Y)`. Precomputed table for the extraction's tokens:

| Token | CSS | SwiftUI |
|---|---|---|
| `--shadow-sm` | `0 1px 2px black/.35` | `.shadow(color: .black.opacity(0.35), radius: 1, y: 1)` |
| `--shadow-md` | `0 6px 18px black/.40` | `.shadow(color: .black.opacity(0.40), radius: 9, y: 6)` |
| `--shadow-lg` | `0 14px 40px black/.50` | `.shadow(color: .black.opacity(0.50), radius: 20, y: 14)` |
| `--shadow-xl` | `0 24px 70px black/.55` | `.shadow(color: .black.opacity(0.55), radius: 35, y: 24)` |
| `--glow-torch` | `0 0 22px torch/.35` | `.shadow(color: torch.opacity(0.35), radius: 11)` |
| `--glow-torch-strong` | `0 0 14px torch/.55, 0 0 44px torch/.25` | two stacked (see below), radius 7 + radius 22 |
| `--glow-gold` | `0 0 24px gold/.4` | `.shadow(color: juryGold.opacity(0.4), radius: 12)` |

⚠️ **Stacked `.shadow` modifiers compound** (the second shadow is cast by the first shadow's output),
unlike CSS which draws both from the same box. For multi-layer glows apply them to the **fill style**
instead — `ShapeStyle.shadow(_:)` (iOS 16+) composes correctly:

```swift
RoundedRectangle(cornerRadius: 10)
    .fill(ctaGradient
        .shadow(.drop(color: torch.opacity(0.55), radius: 7))
        .shadow(.drop(color: torch.opacity(0.25), radius: 22))
        .shadow(.inner(color: .white.opacity(0.35), radius: 0, y: 1)))  // the CSS inset bevel
```

**Reduced motion.** Every effect below must consult one gate. Web has two mechanisms
(`prefers-reduced-motion` + an in-app toggle); mirror both:

```swift
struct MotionGate {
    var systemReduced: Bool          // @Environment(\.accessibilityReduceMotion)
    var appReduced: Bool             // UserDefaults "reduceMotion"
    var isReduced: Bool { systemReduced || appReduced }
    /// Web forces 0.001s (deliberately non-zero so end handlers fire). Same idea here:
    /// keep completion callbacks, kill the visible motion.
    func duration(_ d: Double) -> Double { isReduced ? 0.001 : d }
}
```
Ambient loops (torchFlicker, smokeDrift, stepGlow, emberFloat, confettiFall) are **removed entirely**
under reduced motion, not just shortened — matching the web.

**Easing translations.**
- `cubic-bezier(0.22, 1, 0.36, 1)` (the signature ease-out) → `.timingCurve(0.22, 1, 0.36, 1, duration: d)`, or in keyframes `UnitCurve.bezier(startControlPoint: UnitPoint(x: 0.22, y: 1), endControlPoint: UnitPoint(x: 0.36, y: 1))` (iOS 17).
- `cubic-bezier(0.34, 1.56, 0.64, 1)` (toggle-thumb springy overshoot) → `.spring(response: 0.3, dampingFraction: 0.62)`.
- `cubic-bezier(0.32, 0.72, 0.22, 1)` (story drawer) → `.timingCurve(0.32, 0.72, 0.22, 1, duration: 0.28)`.
- `ease` → `.easeInOut`, `ease-out` → `.easeOut`, `linear` → `.linear`.

**`animation-delay` inside keyframes.** SwiftUI has no delay on `keyframeAnimator`. Encode it as a
leading `LinearKeyframe` that holds the initial value:

```swift
KeyframeTrack(\.opacity) {
    LinearKeyframe(0.0, duration: delay)   // ← the CSS animation-delay
    CubicKeyframe(1.0, duration: 0.42)
}
```
This is exact, keeps the animation self-contained, and avoids `Task.sleep` races.

---

### 1. `torchFlicker` — the living flame

**Web:** opacity `1 → .86 → .96 → .78 → .94 → 1`, scale `1 → 1.03 → .985 → 1`, ease-in-out,
infinite, 2.4s / 2.6s / 3.0s / 3.2s per site, second life-torch offset `animation-delay: -1.4s`.

**Technique:** `keyframeAnimator(initialValue:repeating:)` with two parallel `KeyframeTrack`s.
The amber `drop-shadow` glow must flicker *with* the opacity — drive `.shadow` from the same value.

```swift
struct FlickerValues { var opacity = 1.0; var scale = 1.0 }

struct TorchFlicker: ViewModifier {
    var period: Double = 3.2
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        if reduceMotion { content } else {
            content.keyframeAnimator(initialValue: FlickerValues(), repeating: true) { view, v in
                view.opacity(v.opacity)
                    .scaleEffect(v.scale)
                    .shadow(color: SurvivorTheme.torch.opacity(0.7 * v.opacity), radius: 7)
            } keyframes: { _ in
                KeyframeTrack(\.opacity) {                 // 0/18/42/50/74/100 %
                    CubicKeyframe(0.86, duration: period * 0.18)
                    CubicKeyframe(0.96, duration: period * 0.24)
                    CubicKeyframe(0.78, duration: period * 0.08)
                    CubicKeyframe(0.94, duration: period * 0.24)
                    CubicKeyframe(1.00, duration: period * 0.26)
                }
                KeyframeTrack(\.scale) {
                    CubicKeyframe(1.00,  duration: period * 0.18)
                    CubicKeyframe(1.03,  duration: period * 0.24)
                    CubicKeyframe(0.985, duration: period * 0.08)
                    CubicKeyframe(1.00,  duration: period * 0.50)
                }
            }
        }
    }
}
```

**Desyncing the two life torches** (the `-1.4s` negative delay): `keyframeAnimator` has no phase
offset. Two options, both fine:
1. **Duration jitter (recommended)** — pass `period: 3.0` and `period: 3.27`. They drift apart within
   two cycles and never re-lock. Zero extra machinery, matches the *intent* ("lives don't flicker in
   sync") if not the literal CSS.
2. **Exact phase offset** — drive it from `TimelineView(.animation)` and evaluate a
   `KeyframeTimeline` at `(t + offset).truncatingRemainder(dividingBy: period)`:
   `KeyframeTimeline(initialValue:content:).value(time:)` (iOS 17) makes this a pure function.
   Costs a redraw per frame per icon; only use where literal parity matters.

**Feasibility: DIRECT PORT.**
**Performance:** `keyframeAnimator` is driven by the SwiftUI animation engine, not a per-frame body
re-eval of the whole tree — cheap. It **does not auto-pause off-screen**; wrap long lists so torch
icons outside the viewport aren't materialized (`LazyVStack` handles this), and gate on `scenePhase`
for the header torch.
**Do not** substitute `.symbolEffect(.pulse)` — fixed rhythm, symmetric fade, wrong character. If you
need a one-line stand-in during bring-up it's acceptable; for shipping it reads as generic iOS.

---

### 2. `smokeDrift` — the spent torch

**Web:** 5s ease-in-out infinite, `translateY(-1.5px)`, `rotate(4deg)`, opacity `.55 → .38`.
Perfectly symmetric two-state loop — a keyframe animator is overkill.

**Technique:** boolean state + `.repeatForever(autoreverses: true)`.

```swift
struct SmokeDrift: ViewModifier {
    @State private var drifted = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .offset(y: drifted ? -1.5 : 0)
            .rotationEffect(.degrees(drifted ? 4 : 0))
            .opacity(drifted ? 0.38 : 0.55)
            .animation(reduceMotion ? nil
                : .easeInOut(duration: 2.5).repeatForever(autoreverses: true), value: drifted)
            .onAppear { drifted = true }
    }
}
```
(2.5s half-cycle = the CSS 5s full cycle.) Applies to the smoke-wisp icon in `--text-faint`.

**Feasibility: DIRECT PORT.** **Performance:** negligible.

---

### 3. `torchSnuff` — elimination (flare, then die to gray)

**Web:** 1.6s ease both. `brightness(1)→(1.4)→(0.3)`, `saturate(1)→(1.3)→(0)`, `grayscale(1)` at end,
scale `1 → 1.02 → 0.96`, opacity → 0.45. Delay `500 + ballotCount×320 + 250` ms in the results
screen; on the player row it fires on the `elimination` event and leaves `.eliminated` permanently.

**Technique:** `keyframeAnimator(initialValue:trigger:)`. ⚠️ **Filter gotcha:** SwiftUI's
`.brightness(_:)` is **additive** (−1…1), CSS `brightness()` is **multiplicative**. Use
`.brightness(+0.15)` for the flare-up and `.colorMultiply(Color(white: 0.3))` for the dying-down —
`colorMultiply` *is* multiplicative and matches CSS `brightness(0.3)` exactly. `.saturation()` is
multiplicative in both, so it ports 1:1 (and `saturation(0)` subsumes `grayscale(1)`).

```swift
struct SnuffValues { var flare = 0.0; var sat = 1.0; var dim = 1.0; var scale = 1.0; var opacity = 1.0 }

extension View {
    func torchSnuff(trigger: Int, delay: Double = 0) -> some View {
        keyframeAnimator(initialValue: SnuffValues(), trigger: trigger) { v, s in
            v.brightness(s.flare).saturation(s.sat).colorMultiply(Color(white: s.dim))
             .scaleEffect(s.scale).opacity(s.opacity)
        } keyframes: { _ in
            KeyframeTrack(\.flare)   { LinearKeyframe(0.0, duration: delay)
                                       CubicKeyframe(0.15, duration: 0.48)   // 30% of 1.6s
                                       CubicKeyframe(0.0,  duration: 1.12) }
            KeyframeTrack(\.sat)     { LinearKeyframe(1.0, duration: delay)
                                       CubicKeyframe(1.3,  duration: 0.48)
                                       CubicKeyframe(0.0,  duration: 1.12) }
            KeyframeTrack(\.dim)     { LinearKeyframe(1.0, duration: delay + 0.48)
                                       CubicKeyframe(0.3,  duration: 1.12) }
            KeyframeTrack(\.scale)   { LinearKeyframe(1.0, duration: delay)
                                       CubicKeyframe(1.02, duration: 0.48)
                                       CubicKeyframe(0.96, duration: 1.12) }
            KeyframeTrack(\.opacity) { LinearKeyframe(1.0, duration: delay + 0.48)
                                       CubicKeyframe(0.45, duration: 1.12) }
        }
    }
}
```
After the run, flip a `@State isEliminated` (the web's 2000 ms class removal) so the permanent
`.eliminated` treatment (0.45 opacity + `.strikethrough()` on the name) takes over. Pair with
`SoundEngine.play(.torchSnuff)` and `HapticEngine.torchSnuff()` fired at `delay`.

**Feasibility: DIRECT PORT** (with the brightness→colorMultiply substitution).

---

### 4. `riseIn` — content entering the light

**Web:** `opacity 0→1`, `translateY(14px)→0`. Three uses: screen stagger 420 ms
`cubic-bezier(0.22,1,0.36,1)` with children 2–5 delayed 60/120/180/240 ms; modal 260 ms ease;
elimination announcement 700 ms with a computed delay. This is *the* signature transition.

**Technique:** a custom `Transition` (iOS 17 protocol) so it composes with `.transition()` and
`withAnimation`, plus an index-driven delay for the stagger.

```swift
struct RiseIn: Transition {
    var distance: CGFloat = 14
    func body(content: Content, phase: TransitionPhase) -> some View {
        content
            .opacity(phase.isIdentity ? 1 : 0)
            .offset(y: phase.isIdentity ? 0 : distance)
    }
}

/// The screen-change stagger: `.screen.active > *` children 2–5 delayed 60ms apart.
struct StaggeredRise<C: View>: View {
    let index: Int
    @ViewBuilder var content: C
    @State private var shown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : 14)
            .onAppear {
                let d = reduceMotion ? 0.001 : 0.42
                withAnimation(.timingCurve(0.22, 1, 0.36, 1, duration: d)
                    .delay(reduceMotion ? 0 : min(Double(index), 4) * 0.06)) { shown = true }
            }
    }
}
```
Modal variant: `.transition(RiseIn())` + `.animation(.easeOut(duration: 0.26))`.
Elimination announcement: same with `duration: 0.7` and `.delay(0.5 + Double(resultCount) * 0.32)`.

**Feasibility: DIRECT PORT.**

---

### 5. `fadeIn` — soft entrance

**Web:** 300 ms ease, opacity + 8 px rise. Used on screens, modal overlay, toasts (paired with a
300 ms `.fade-out`), `.reveal-row` staggered 0.15 s per row, reactive banner.

**Technique:** the same `RiseIn` transition with `distance: 8`, or plainly:

```swift
extension AnyTransition {
    static var torchFade: AnyTransition {
        .asymmetric(insertion: .opacity.combined(with: .offset(y: 8)), removal: .opacity)
    }
}
// Toast:
ToastView(toast).transition(.torchFade)
    .animation(.easeOut(duration: 0.3), value: toast.id)

// Challenge reveal rows (0.15s stagger, `backwards` fill = start hidden):
ForEach(Array(rows.enumerated()), id: \.element.id) { i, row in
    RevealRow(row).opacity(shown ? 1 : 0)
        .animation(.easeOut(duration: 0.35).delay(Double(i) * 0.15), value: shown)
}
```

**Feasibility: DIRECT PORT.**

---

### 6. `ballotFlip` — reading the votes

**Web:** `perspective(700px) rotateX(70°) translateY(18px)` → `rotateX(-8°)` at 60% (overshoot) →
`0°`. 560 ms `cubic-bezier(0.22,1,0.36,1)`, per-card delay `i × 320 ms`. The result bar inside then
grows over 900 ms with the same curve.

**Technique:** `keyframeAnimator` + `.rotation3DEffect(_:axis:anchor:perspective:)`.
CSS `perspective: 700px` on a card ≈ `perspective` parameter of `cardWidth / 700` — for the ~340 pt
content column that's **≈ 0.5**. Tune visually; larger = more dramatic.

```swift
struct FlipValues { var rotX = 70.0; var y = 18.0; var opacity = 0.0 }

struct BallotCard: View {
    let result: VoteResult
    let index: Int
    @State private var flipped = false

    var body: some View {
        VoteResultRow(result)
            .keyframeAnimator(initialValue: FlipValues(), trigger: flipped) { v, s in
                v.rotation3DEffect(.degrees(s.rotX), axis: (x: 1, y: 0, z: 0),
                                   anchor: .center, perspective: 0.5)
                 .offset(y: s.y).opacity(s.opacity)
            } keyframes: { _ in
                let delay = Double(index) * 0.32
                KeyframeTrack(\.rotX)    { LinearKeyframe(70, duration: delay)
                                           CubicKeyframe(-8, duration: 0.336)   // 60% of 0.56
                                           CubicKeyframe(0,  duration: 0.224) }
                KeyframeTrack(\.y)       { LinearKeyframe(18, duration: delay)
                                           CubicKeyframe(0,  duration: 0.336) }
                KeyframeTrack(\.opacity) { LinearKeyframe(0,  duration: delay)
                                           CubicKeyframe(1,  duration: 0.336) }
            }
            .onAppear { flipped = true }
    }
}
```
Result bar: `Capsule().fill(LinearGradient(colors: [ember, torch], startPoint: .leading, endPoint: .trailing))`
`.frame(width: trackWidth * fraction)` `.shadow(color: torch.opacity(0.6), radius: 5)` with
`.animation(.timingCurve(0.22, 1, 0.36, 1, duration: 0.9), value: fraction)`.

**Feasibility: DIRECT PORT.** The −8° overshoot is what sells it — don't drop it.
**Performance:** `rotation3DEffect` forces an offscreen render per card. With ≤ 8 ballots on screen
this is fine; do **not** apply it inside a scrolling list of dozens.

---

### 7. `turnPulse` — "it's your turn" ring

**Web:** `box-shadow: 0 0 0 0 torch/.55` → `0 0 0 22px torch/0`, 1.6 s ease-out, **2 iterations**,
on `.phase-guidance.your-turn`; the guidance title simultaneously turns `--flame-hot`.

**Technique:** a CSS box-shadow **spread** with zero blur is a solid halo, not a blur — model it as a
stroke that grows *outward* from the shape's edge and fades. `MoveKeyframe` restarts the ring for the
second iteration inside a single animator.

```swift
struct PulseRing: ViewModifier {
    var trigger: Int
    var maxSpread: CGFloat = 22, startAlpha: Double = 0.55
    var cornerRadius: CGFloat = 10, duration: Double = 1.6, iterations: Int = 2

    struct S { var spread: CGFloat = 0; var alpha: Double = 0 }

    func body(content: Content) -> some View {
        content.keyframeAnimator(initialValue: S(), trigger: trigger) { view, s in
            view.overlay(
                RoundedRectangle(cornerRadius: cornerRadius + s.spread / 2, style: .continuous)
                    .inset(by: -s.spread / 2)
                    .stroke(SurvivorTheme.torch.opacity(s.alpha), lineWidth: s.spread)
                    .allowsHitTesting(false))
        } keyframes: { _ in
            KeyframeTrack(\.spread) { for _ in 0..<iterations {
                MoveKeyframe(0); CubicKeyframe(maxSpread, duration: duration) } }
            KeyframeTrack(\.alpha)  { for _ in 0..<iterations {
                MoveKeyframe(startAlpha); CubicKeyframe(0, duration: duration) } }
        }
    }
}
```
Wire: `updatePhaseGuidance` equivalent bumps `trigger` when `isMyTurn && phase == .playing`.
Fire `HapticEngine.turnPulse()` on the same state change.

**Feasibility: DIRECT PORT.**

---

### 8. `pulseHighlight` — attention ping

Identical mechanism, different constants: `maxSpread: 18`, `startAlpha: 0.7`, `duration: 1.0`,
`iterations: 1`, and the alpha resolves at 70% of the run (add a trailing zero-alpha hold):

```swift
.modifier(PulseRing(trigger: pingCount, maxSpread: 18, startAlpha: 0.7,
                    duration: 0.7, iterations: 1))
// then hold 0.3s of nothing — or just accept the 1.0s linear fade; visually indistinguishable.
```
Web note: `pulseElement` has **no active caller** in the deployed build — it's exposed API for
`narrate(msg, {animation})`. On iOS keep it as a reusable modifier on the narrator surface, ready to
be pointed at any element.

**Feasibility: DIRECT PORT.**

---

### 9. `voteSlam` — the vote card slammed on screen

**Web (unused in the deployed build; iOS will use it):** a fixed centered card — Fraunces 900 italic
2.4 rem parchment on `--surface-raised`, 1 px torch border, radius 10, `--shadow-xl` +
`--glow-torch-strong`, padding `0.8rem 1.6rem`. `scale 0 → 1.2 (rot −10° → 5°) → 1 (0°) → 0.85` with
opacity `0 → 1 → 0`, 1.5 s ease, element removed after 1.5 s.

**Technique:** `keyframeAnimator` on a full-screen overlay. Use `SpringKeyframe` for the 20 %
overshoot beat — it reads far more like a *slam* than a cubic curve.

```swift
struct SlamValues { var scale = 0.0; var rot = -10.0; var opacity = 0.0 }

struct VoteSlamOverlay: View {
    let name: String
    var onFinished: () -> Void
    @State private var go = false

    var body: some View {
        Text(name)
            .font(.custom("Fraunces", size: 38).italic()).fontWeight(.black)
            .foregroundStyle(SurvivorTheme.parchment)
            .padding(.vertical, 13).padding(.horizontal, 26)
            .background(RoundedRectangle(cornerRadius: 10).fill(SurvivorTheme.surfaceRaised
                .shadow(.drop(color: .black.opacity(0.55), radius: 35, y: 24))
                .shadow(.drop(color: SurvivorTheme.torch.opacity(0.55), radius: 7))
                .shadow(.drop(color: SurvivorTheme.torch.opacity(0.25), radius: 22))))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(SurvivorTheme.torch, lineWidth: 1))
            .keyframeAnimator(initialValue: SlamValues(), trigger: go) { v, s in
                v.scaleEffect(s.scale).rotationEffect(.degrees(s.rot)).opacity(s.opacity)
            } keyframes: { _ in
                KeyframeTrack(\.scale)   { SpringKeyframe(1.2, duration: 0.30, spring: .snappy)
                                           CubicKeyframe(1.0, duration: 0.30)
                                           CubicKeyframe(0.85, duration: 0.90) }
                KeyframeTrack(\.rot)     { CubicKeyframe(5, duration: 0.30)
                                           CubicKeyframe(0, duration: 0.30)
                                           CubicKeyframe(0, duration: 0.90) }
                KeyframeTrack(\.opacity) { CubicKeyframe(1, duration: 0.30)
                                           CubicKeyframe(1, duration: 0.30)
                                           CubicKeyframe(0, duration: 0.90) }
            }
            .onAppear { go = true
                Task { try? await Task.sleep(for: .seconds(1.5)); onFinished() } }
            .allowsHitTesting(false)
    }
}
```
Present via `.overlay()` on the root, not a sheet. Fire `HapticEngine.voteSlam()` at t=0.

**Feasibility: DIRECT PORT.**

---

### 10. `confettiFall` — victory embers

**Web:** 150 pieces, 9 × 14 px, radius 2, `top: -3vh`, random `left`, ember/gold palette
(`#e89a4a #f2c14e #c96a2f #f6e3b4 #a94e24 #ffd98a`), `translateY(-4vh → 104vh)` +
`rotate(0 → 680deg)`, opacity 1 → 0, per-piece random duration 2–4 s and delay 0–3 s, ease-in,
container removed after 6 s.

**Technique:** **`TimelineView(.animation)` + `Canvas`** — one view, one draw call tree, 150 pieces.
150 individual animated SwiftUI views would be a disaster; this is the correct tool.

```swift
struct ConfettiPiece { let x: CGFloat; let dur: Double; let delay: Double
                       let color: Color; let spin: Double }

struct ConfettiLayer: View {
    let start: Date
    @State private var pieces: [ConfettiPiece] = (0..<150).map { _ in
        ConfettiPiece(x: .random(in: 0...1), dur: .random(in: 2...4), delay: .random(in: 0...3),
                      color: SurvivorTheme.emberConfetti.randomElement()!, spin: 680)
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60.0, paused: false)) { ctx in
            Canvas { g, size in
                let now = ctx.date.timeIntervalSince(start)
                for p in pieces {
                    let t = (now - p.delay) / p.dur
                    guard t > 0, t < 1 else { continue }
                    let e = t * t                                    // ease-in
                    let y = (-0.04 + 1.08 * e) * size.height
                    g.drawLayer { l in
                        l.translateBy(x: p.x * size.width, y: y)
                        l.rotate(by: .degrees(p.spin * e))
                        l.opacity = 1 - t
                        l.fill(Path(roundedRect: CGRect(x: -4.5, y: -7, width: 9, height: 14),
                                    cornerRadius: 2), with: .color(p.color))
                    }
                }
            }
        }
        .allowsHitTesting(false).accessibilityHidden(true).ignoresSafeArea()
    }
}
```

**Feasibility: DIRECT PORT.**
**Performance — this is the one to watch.** `TimelineView(.animation)` re-evaluates the body every
display frame (up to 120 Hz on ProMotion). Mitigations, all required:
- Mount the layer **only** while confetti is live; tear it down after 6 s (`Task.sleep` → remove from
  the overlay), exactly as the web removes the container.
- Pass `paused:` from `scenePhase != .active` so a backgrounded app stops redrawing.
- `minimumInterval: 1/60` caps ProMotion at 60 fps — halves the cost, visually identical for confetti.
- Drop to ~90 pieces if you see frame drops on the oldest supported device.
- Hidden entirely under reduced motion (web does the same).

---

### 11. `spin` — loading

**Web:** 42 px circle, 3 px ring in `--line-strong` with `border-top-color: var(--torch)` plus
`--glow-torch`. `0.9s linear infinite`.

**Technique:** two stacked `Circle` strokes (the full faint ring + a trimmed torch arc) rotated by a
`repeatForever(autoreverses: false)` linear animation. `ProgressView().tint(torch)` is the one-liner
fallback but loses the torch-arc-on-faint-ring look — APPROXIMATE.

```swift
struct TorchSpinner: View {
    @State private var spinning = false
    var body: some View {
        ZStack {
            Circle().stroke(SurvivorTheme.lineStrong, lineWidth: 3)
            Circle().trim(from: 0, to: 0.25)
                .stroke(SurvivorTheme.torch, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .rotationEffect(.degrees(spinning ? 360 : 0))
                .animation(.linear(duration: 0.9).repeatForever(autoreverses: false), value: spinning)
        }
        .frame(width: 42, height: 42)
        .shadow(color: SurvivorTheme.torch.opacity(0.35), radius: 11)
        .onAppear { spinning = true }
        .accessibilityLabel("Loading")
    }
}
```
**Feasibility: DIRECT PORT.**

---

### 12. `emberFloat` — rising ember

**Web: defined but unreferenced.** `translateY(0 → -46vh)`, `translateX(0 → 6vw)`, `scale 1 → 0.4`,
opacity `0.9 → 0`. The extraction's suggestion — embers rising off the torchlight — is the right
iOS use.

**Technique:** the **same `TimelineView` + `Canvas` emitter** as confetti, different parameters and
much lower count. Keep it as one shared `ParticleField` view parameterized by a config struct;
`confettiFall` and `emberFloat` become two configs, not two engines.

```swift
struct EmberField: View {
    var count = 14
    @State private var seeds: [(x: CGFloat, dur: Double, phase: Double, r: CGFloat)] =
        (0..<14).map { _ in (.random(in: 0.28...0.72), .random(in: 5...9),
                             .random(in: 0...1), .random(in: 1.5...3)) }
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: false)) { ctx in
            Canvas { g, size in
                let now = ctx.date.timeIntervalSinceReferenceDate
                for s in seeds {
                    let t = ((now / s.dur) + s.phase).truncatingRemainder(dividingBy: 1)
                    let y = size.height * 0.08 - CGFloat(t) * size.height * 0.46
                    let x = s.x * size.width + CGFloat(t) * size.width * 0.06
                    let k = 1 - 0.6 * CGFloat(t)
                    g.opacity = 0.9 * (1 - t)
                    g.fill(Path(ellipseIn: CGRect(x: x, y: y, width: s.r * k, height: s.r * k)),
                           with: .color(SurvivorTheme.flameHot))
                }
            }
        }
        .allowsHitTesting(false).accessibilityHidden(true).blendMode(.plusLighter)
    }
}
```
`.blendMode(.plusLighter)` makes embers read as *light* over the dark ground rather than paint.

**Feasibility: DIRECT PORT (new for iOS).**
**Performance:** ambient and permanent → this one must be disciplined. `minimumInterval: 1/30`,
≤ 18 particles, `paused` whenever `scenePhase != .active` **or** the app is on a ceremony screen
where it competes, and removed entirely under reduced motion. Do not mount two of these at once.

---

### 13. `stepGlow` — breathing glow

**Web:** `opacity 1 → 0.55 → 1`. Four sites, two different characters:
- **Breathing** (`.step.now` 2.2 s ease-in-out; `.network-status-dot` reconnecting 0.8 s;
  `.dramatic-dots` 1 s) → the smooth version.
- **Hard blink** (`.narrator-cursor` **`1s steps(2)`**) → a square wave, not a fade.

```swift
// Breathing — 2.2s CSS full cycle = 1.1s half-cycle.
struct StepGlow: ViewModifier {
    var period: Double = 2.2
    @State private var dim = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func body(content: Content) -> some View {
        content.opacity(dim ? 0.55 : 1.0)
            .animation(reduceMotion ? nil
                : .easeInOut(duration: period / 2).repeatForever(autoreverses: true), value: dim)
            .onAppear { dim = true }
    }
}

// Hard blink (steps(2)) — a periodic schedule is exact and costs one redraw per 0.5s.
struct NarratorCursor: View {
    var body: some View {
        TimelineView(.periodic(from: .now, by: 0.5)) { ctx in
            Text("\u{258B}").foregroundStyle(SurvivorTheme.torch)
                .opacity(Int(ctx.date.timeIntervalSinceReferenceDate * 2) % 2 == 0 ? 1 : 0)
        }
    }
}
```
**Feasibility: DIRECT PORT.** Note the deliberate use of `.periodic` (not `.animation`) for the
cursor — a 2 Hz schedule, not a 120 Hz one.

---

### Component treatment: the glowing CTA button

**Web:** label font small-caps 700 / 0.84 rem / tracking 0.14 em, `--ink` `#2A1C10` text on a
three-stop vertical flame gradient `#F9AD26 → #E68100 @55% → #C75E00`, 1 px `#B0540E` border,
`inset 0 1px 0 white/.35` + `--shadow-sm` + `--glow-torch`, radius 10, min-height 48.
Active: `translateY(1px) scale(0.99)`, inset drops to white/.20, **glow removed**.
Disabled: opacity 0.45 + `saturate(0.5)`, no shadow.

**Technique:** a `ButtonStyle`. The inset top bevel is `ShapeStyle.shadow(.inner(...))` on the fill.

```swift
struct TorchButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        configuration.label
            .font(SurvivorFont.label(13.4).weight(.bold)).tracking(1.9)   // 0.84rem, 0.14em
            .foregroundStyle(SurvivorTheme.ink)
            .frame(maxWidth: .infinity, minHeight: 48)
            .padding(.horizontal, 20)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(LinearGradient(stops: [
                        .init(color: SurvivorTheme.flameHot, location: 0),
                        .init(color: SurvivorTheme.torch,    location: 0.55),
                        .init(color: SurvivorTheme.torchDeep, location: 1)],
                        startPoint: .top, endPoint: .bottom)
                    .shadow(.inner(color: .white.opacity(pressed ? 0.20 : 0.35), radius: 0, y: 1))))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(SurvivorTheme.torchBorder, lineWidth: 1))
            .shadow(color: .black.opacity(0.35), radius: 1, y: 1)
            .shadow(color: SurvivorTheme.torch.opacity(pressed || !isEnabled ? 0 : 0.35), radius: 11)
            .offset(y: pressed ? 1 : 0).scaleEffect(pressed ? 0.99 : 1)
            .saturation(isEnabled ? 1 : 0.5).opacity(isEnabled ? 1 : 0.45)
            .animation(.easeOut(duration: 0.12), value: pressed)
    }
}
```
Secondary / success / danger / warning / ghost are the same shape with the extraction's gradient +
border + inset values swapped; make the style generic over a small `TorchButtonPalette` struct so
there is one implementation, five palettes.

**Feasibility: DIRECT PORT.**

---

### Component treatment: layered card backgrounds

**Web hand card:** `linear-gradient(180deg, white/4.5%, transparent 30%)` **over** `--surface-raised`
(a sheen at the top edge), 1 px `--line-strong`, radius 14, `--shadow-md`, aspect 3 : 4.1, plus a
**4 px category rule across the top** with a per-category gradient. `.playable` adds a torch/55 %
border + glow-torch and floats −4 pt; `.locked` is opacity 0.45 + `saturate(0.35)`.
**Panel:** `linear-gradient(180deg, --surface-raised, --surface 22%)`, radius 22, `--shadow-lg`.

**Technique:** `.background { ZStack }` with the base fill and the sheen gradient, `.overlay` for the
category rule clipped to the shape, `.overlay(...strokeBorder)` for the hairline.

```swift
struct TorchCardBackground: View {
    var corner: CGFloat = 14
    var categoryGradient: LinearGradient?
    var borderColor: Color = SurvivorTheme.lineStrong

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: corner, style: .continuous)
        shape.fill(SurvivorTheme.surfaceRaised)
            .overlay(shape.fill(LinearGradient(stops: [
                .init(color: .white.opacity(0.045), location: 0),
                .init(color: .clear,                location: 0.30)],
                startPoint: .top, endPoint: .bottom)))
            .overlay(alignment: .top) {
                if let g = categoryGradient { Rectangle().fill(g).frame(height: 4) }
            }
            .clipShape(shape)                                // rule follows the rounded corners
            .overlay(shape.strokeBorder(borderColor, lineWidth: 1))
            .compositingGroup()                              // one opacity/shadow target
            .shadow(color: .black.opacity(0.40), radius: 9, y: 6)
    }
}
```
Category gradients (90°, from the extraction): action `#579766 → #237356`;
tribal_advantage `#D8B349 → #C48225`; vote `#DDCCA9 → #AD9D7B`; challenge `#F3821D → #D84A00`.
`.compositingGroup()` before `.opacity(0.45)` for `.locked` — otherwise each sublayer fades
independently and the border ghosts through.

**Feasibility: DIRECT PORT.**

---

### Component treatment: box-shadow glows

Use the mapping table in §0. Three rules:
1. **Single glow** → `.shadow(color:radius:)` on the view. Fine.
2. **Multiple glows on one shape** → `ShapeStyle.shadow(.drop(...))` chained on the *fill* (does not
   compound). This is the correct port of `--glow-torch-strong`.
3. **Inset shadows** (`inset 0 1px 0 white/.35` bevel, avatar `inset 0 -4px 8px black/.25`) →
   `ShapeStyle.shadow(.inner(color:radius:x:y:))`, iOS 16+. There is no view-level `.innerShadow`.

**Glow that must animate** (e.g. torchFlicker's drop-shadow) — put the animated value straight into
the `.shadow` color's opacity, not into a separate modifier, so it interpolates in the same pass.

**Feasibility: DIRECT PORT.** ⚠️ Never wrap a glowing view in `.drawingGroup()` — it flattens to an
offscreen buffer and clips the glow at the bounds.

---

### Component treatment: gradient borders

**Web sites:** eyebrow rule (`90deg torch/50% → transparent`), tagline flanking rules, the modal's
3 px solid torch **top** border, the challenge panel's 4 px torch top border, the phase-guidance
3 px torch **left** border, the toast's 4 px torch left border.

```swift
// 1. Uniform gradient stroke:
.overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
    .strokeBorder(LinearGradient(colors: [SurvivorTheme.torch.opacity(0.6), .clear],
                                 startPoint: .top, endPoint: .bottom), lineWidth: 1))

// 2. One-sided thick edge (modal top / phase-guidance left) — overlay + clip, not a border:
.overlay(alignment: .top) { Rectangle().fill(SurvivorTheme.torch).frame(height: 3) }
.clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

// 3. Eyebrow rule filling the rest of the row:
HStack(spacing: 10) {
    Text("THE TRIBE").font(SurvivorFont.label(11.5).weight(.bold)).tracking(2.5)
        .foregroundStyle(SurvivorTheme.torch)
    Rectangle().fill(LinearGradient(colors: [SurvivorTheme.torch.opacity(0.5), .clear],
                                    startPoint: .leading, endPoint: .trailing))
        .frame(height: 1)
}
```
For a rounded-only-at-the-top thick edge, `UnevenRoundedRectangle(topLeadingRadius:…)` (iOS 16.4+)
is available and cleaner than clipping.

**Feasibility: DIRECT PORT.**

---

### Component treatment: the background scene (torchlight radial + grain + vignette)

**Web:** `linear-gradient(180deg, --bg, --bg-deep)` base; `--torchlight`
`radial-gradient(120% 55% at 50% -12%, oklch(.42 .10 55 / .42) → transparent 62%)` painted over it,
`background-attachment: fixed`; `body::before` = a fixed 140×140 tiled `feTurbulence` fractalNoise
SVG at **opacity 0.05**; `body::after` = vignette
`radial-gradient(140% 100% at 50% 40%, transparent 40%, black/.45 100%)`, `none` in victory mode.
Palette crossfades over **900 ms ease** on mode change.

**Technique:** one `ZStack` behind everything, `.ignoresSafeArea()`, placed *outside* the ScrollView
so it doesn't scroll (that is what `background-attachment: fixed` means). CSS elliptical radials map
to **`EllipticalGradient`** (iOS 15+), not `RadialGradient` (which is circular).

```swift
struct TorchlitBackground: View {
    var mode: CeremonyMode                  // .normal / .council / .final / .victory

    var body: some View {
        GeometryReader { geo in
            ZStack {
                LinearGradient(colors: [mode.bg, mode.bgDeep], startPoint: .top, endPoint: .bottom)

                EllipticalGradient(stops: [.init(color: mode.torchlightCore, location: 0),
                                           .init(color: .clear,             location: 0.62)],
                                   center: .center, endRadiusFraction: 0.5)
                    .frame(width: geo.size.width * 1.2, height: geo.size.height * 1.1)
                    .position(x: geo.size.width / 2, y: -0.12 * geo.size.height)

                Grain.tile.resizable(resizingMode: .tile).opacity(0.05).blendMode(.overlay)

                if mode != .victory {
                    EllipticalGradient(stops: [.init(color: .clear,               location: 0.40),
                                               .init(color: .black.opacity(0.45), location: 1.0)],
                                       center: UnitPoint(x: 0.5, y: 0.4),
                                       endRadiusFraction: 0.7)
                }
            }
            .animation(.easeInOut(duration: 0.9), value: mode)   // the 900ms mode crossfade
        }
        .ignoresSafeArea().allowsHitTesting(false)
    }
}
```

**Grain — two options.**

*(A) Cached noise tile (recommended — DIRECT PORT, zero per-frame cost):*

```swift
enum Grain {
    static let tile: Image = {
        let n = 140
        let ctx = CGContext(data: nil, width: n, height: n, bitsPerComponent: 8,
                            bytesPerRow: n * 4, space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        let buf = ctx.data!.assumingMemoryBound(to: UInt8.self)
        for i in stride(from: 0, to: n * n * 4, by: 4) {
            let v = UInt8.random(in: 0...255)
            buf[i] = v; buf[i + 1] = v; buf[i + 2] = v; buf[i + 3] = 255
        }
        return Image(decorative: ctx.makeImage()!, scale: 1)
    }()
}
```
White noise vs. the CSS `feTurbulence` fractalNoise: at 140 px tile / 5 % opacity the difference is
imperceptible. Generated once, lives for the process, `resizingMode: .tile` costs one draw.

*(B) Metal `colorEffect` shader (APPROXIMATE — optional):* a `[[ stitchable ]] half4 grain(float2 pos,
half4 color, float amount)` that hashes `pos` and adds it to the source color. Resolution-independent
and animatable (film grain that crawls), but adds a `.metal` file, a render pass, and a
simulator-compat risk. Only worth it if you later want *moving* grain. Wiring, if you take it:
put `Shaders/Grain.metal` under `ios/SurvivorGame/` (xcodegen's `sources: - SurvivorGame` picks up
`.metal` into Compile Sources automatically; verify with `xcodegen generate` + a build), then
`.colorEffect(ShaderLibrary.grain(.float(0.05)))`. Verify on device *and* simulator — early Xcode 15
simulators mishandled stitchable shaders.

**Feasibility: DIRECT PORT** (option A). **Performance:** the whole scene is static geometry — no
TimelineView, no redraws. If you add `EmberField`, it is the only live layer.

---

### `matchedGeometryEffect` — where it earns its keep

Not in the web design (the web has no shared-element transitions), so every use is an **enhancement**:
- **Hand card → card detail sheet.** The web opens a `.card-sheet` modal with `riseIn`. On iOS, a
  `matchedGeometryEffect(id: card.id, in: ns)` between the mini card and the sheet's header reads
  markedly better than a modal pop and costs ~6 lines. **APPROXIMATE** (improves on the web).
- **Turn-steps "now" pill.** Web recolors the pill in place; a matched-geometry pill that *slides*
  STEAL → PLAY → DRAW is a natural iOS idiom. **APPROXIMATE (enhancement)** — but it changes the
  motion language; get design sign-off before shipping it.
- **Segmented control selection.** Same story: slide the pressed background between segments.

⚠️ Do **not** use `matchedGeometryEffect` across a `.sheet` boundary — SwiftUI does not share a
namespace with a presented sheet's own window. Use a custom in-hierarchy overlay presentation if you
want the card→detail morph. **SKIP** if you're not prepared to hand-roll the presentation.

---

### `.symbolEffect` — limited applicability

The design uses a **hand-drawn SVG sprite** (`#i-torch`, `#i-ballot`, `#i-idol`, `#i-necklace`,
`#i-rock`, `#i-skull`, `#i-crown`, `#i-eye`, …), 24×24 viewBox, ~1.7–1.8 stroke, round caps,
`currentColor`, explicitly *"hand-cut marks, no emoji chrome."* SF Symbols are the wrong voice for
these — port the sprite as an SF Symbol-shaped asset catalog **custom symbol set** (`.svg` symbol
template) so it still gets `foregroundStyle`, Dynamic Type scaling, and `.symbolEffect`.

Given custom symbols, iOS 17 offers exactly: `.bounce`, `.pulse`, `.variableColor`, `.scale`,
`.appear`, `.disappear`, `.replace`. Useful here:
- `.symbolEffect(.bounce, value: voteCount)` on the ballot icon when a vote lands — **APPROXIMATE**,
  a nice iOS-native accent with no web equivalent.
- `.contentTransition(.symbolEffect(.replace))` for lit-torch → smoke-torch when a life is spent —
  **APPROXIMATE**, cleaner than a crossfade.
- `.symbolEffect(.pulse)` as a torchFlicker substitute — **SKIP**, wrong rhythm (see §1).
- ⚠️ `.wiggle`, `.rotate`, `.breathe` are **iOS 18+** — do not use.

---

### Micro-interaction transitions (the rest of the motion language)

| Web | SwiftUI |
|---|---|
| Buttons `transform 120ms ease`, `:active translateY(1px) scale(.99)` | in `TorchButtonStyle`, `.animation(.easeOut(duration: 0.12), value: pressed)` |
| Hand cards `transform 160ms`; `.playable` −4 pt; `.pressing` −2 pt scale .97 | `.offset(y:)` + `.scaleEffect` with `.easeOut(duration: 0.16)` |
| Toggle thumb `cubic-bezier(.34,1.56,.64,1) 200ms` | `.spring(response: 0.3, dampingFraction: 0.62)` |
| Story drawer `translateX(102%) → 0` over `.28s cubic-bezier(.32,.72,.22,1)` | `.transition(.move(edge: .trailing))` + `.timingCurve(0.32, 0.72, 0.22, 1, duration: 0.28)`; overlay `.opacity` 0.25 s |
| Vote targets rotate ±0.8–0.9°, selected straightens + scale 1.03 | `.rotationEffect(.degrees(isSelected ? 0 : (i.isMultiple(of: 2) ? 0.9 : -0.8)))` + `.scaleEffect(isSelected ? 1.03 : 1)`, `.easeOut(duration: 0.15)` |
| Rows press feedback scale .985–.94 | `ButtonStyle` with `.scaleEffect(pressed ? 0.985 : 1)` |
| Toast rotated −0.5°, 4 px torch left border | `.rotationEffect(.degrees(-0.5))` + the one-sided edge recipe above |

---

## §Haptics

The web fires plain `navigator.vibrate` patterns (`hapticFeedback`: light `[10]`, medium `[30]`,
heavy `[50]`, success `[10,50,10]`, error `[100,50,100]`, warning `[50,30,50]`). iOS can do far
better with Core Haptics for the five ceremony moments below, while keeping the existing
`UIFeedbackGenerator` calls for everyday taps.

**Integration shape** — same file, same style as the existing
`ios/SurvivorGame/Views/Components/HapticEngine.swift`: `@MainActor enum HapticEngine`, static funcs,
`isEnabled` gate on `UserDefaults` key `"hapticsEnabled"`. Add a lazily-started `CHHapticEngine` and
have every new pattern fall back to the existing generator calls when the hardware can't do it.

```swift
import CoreHaptics
import UIKit

@MainActor
extension HapticEngine {
    private static let supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics
    private static var engine: CHHapticEngine?

    /// Lazily create + start. Safe to call on every pattern play.
    private static func liveEngine() -> CHHapticEngine? {
        guard supportsHaptics else { return nil }
        if let e = engine { return e }
        guard let e = try? CHHapticEngine() else { return nil }
        e.playsHapticsOnly = true            // ← does NOT touch our AVAudioSession (see §Audio)
        e.isAutoShutdownEnabled = true       // powers down when idle, restarts on demand
        e.resetHandler  = { try? e.start() }
        e.stoppedHandler = { _ in engine = nil }
        try? e.start()
        engine = e
        return e
    }

    /// One entry point; every pattern below routes through it.
    static func play(_ make: () throws -> CHHapticPattern, fallback: () -> Void) {
        guard isEnabled else { return }
        guard let e = liveEngine(),
              let pattern = try? make(),
              let player = try? e.makePlayer(with: pattern) else { fallback(); return }
        try? player.start(atTime: CHHapticTimeImmediate)
    }
}
```

### `voteSlam` — heavy slam
The card hits at t=0 with a full-intensity, sharp transient, then a short low rumble tail and a
softer rebound thud. Matches the 1.5 s `voteSlam` keyframe's 0–20 % impact window.

```swift
static func voteSlam() {
    play({
        try CHHapticPattern(events: [
            // The strike.
            CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 1.00),
                .init(parameterID: .hapticSharpness, value: 0.90)], relativeTime: 0),
            // Low rumble tail under the overshoot.
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.80),
                .init(parameterID: .hapticSharpness, value: 0.25)],
                relativeTime: 0.01, duration: 0.16),
            // Rebound thud as it settles to scale 1.0.
            CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.55),
                .init(parameterID: .hapticSharpness, value: 0.20)], relativeTime: 0.10)
        ], parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 1.0),
                .init(relativeTime: 0.17, value: 0.0)], relativeTime: 0)
        ])
    }, fallback: { impact(.heavy) })
}
```

### `torchSnuff` — fading rumble
1.4 s continuous event whose **sharpness falls from 0.60 to 0.05** — the tactile analogue of the
audio cue's 3000 Hz → 200 Hz lowpass sweep — with a small intensity bump at 0.12 s for the flare-up
before the die-down. Start it at the same `delay` as the visual keyframe.

```swift
static func torchSnuff() {
    play({
        try CHHapticPattern(events: [
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.60),
                .init(parameterID: .hapticSharpness, value: 0.60)],
                relativeTime: 0, duration: 1.4)
        ], parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.55),   // fire steady
                .init(relativeTime: 0.12, value: 0.85),   // flare
                .init(relativeTime: 0.40, value: 0.45),
                .init(relativeTime: 1.40, value: 0.00)],  // out
                relativeTime: 0),
            CHHapticParameterCurve(parameterID: .hapticSharpnessControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.60),
                .init(relativeTime: 1.40, value: 0.05)],  // 3000Hz → 200Hz, felt
                relativeTime: 0)
        ])
    }, fallback: { notification(.warning) })
}
```

### `turnPulse` — soft pulse (×2, mirroring the 1.6 s ring × 2 iterations)

```swift
static func turnPulse() {
    play({
        try CHHapticPattern(events: (0..<2).map { i in
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.42),
                .init(parameterID: .hapticSharpness, value: 0.15)],
                relativeTime: Double(i) * 1.6, duration: 0.22)
        }, parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.0),   // swell in, not a tap
                .init(relativeTime: 0.09, value: 1.0),
                .init(relativeTime: 0.22, value: 0.0)], relativeTime: 0)
        ])
    }, fallback: { impact(.soft) })
}
```
(If the doubled ring feels heavy in testing, drop to a single event — the visual already pulses twice.)

### unlock / come-ashore — success
A **rising** three-tap: intensity and sharpness both climb, so it reads as "opening up" rather than
the flat system `.success`.

```swift
static func comeAshore() {
    play({
        let steps: [(Double, Float, Float)] = [(0.00, 0.40, 0.30),
                                               (0.10, 0.60, 0.50),
                                               (0.22, 0.95, 0.70)]
        return try CHHapticPattern(events: steps.map { t, i, s in
            CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: i),
                .init(parameterID: .hapticSharpness, value: s)], relativeTime: t)
        }, parameters: [])
    }, fallback: { notification(.success) })
}
```

### winner / confetti — fanfare
Four transients on the **exact arpeggio grid of the `victory` audio cue** (0 / 0.15 / 0.30 / 0.45 s,
C5-E5-G5-C6), riding a continuous shimmer that swells and decays under the confetti drop.

```swift
static func winner() {
    play({
        var events: [CHHapticEvent] = [
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.45),
                .init(parameterID: .hapticSharpness, value: 0.85)],
                relativeTime: 0, duration: 0.95)
        ]
        for (i, sharp) in [Float(0.45), 0.55, 0.65, 0.80].enumerated() {
            events.append(CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.55 + Float(i) * 0.12),
                .init(parameterID: .hapticSharpness, value: sharp)],
                relativeTime: Double(i) * 0.15))
        }
        return try CHHapticPattern(events: events, parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.20),
                .init(relativeTime: 0.45, value: 0.70),
                .init(relativeTime: 0.95, value: 0.00)], relativeTime: 0)
        ])
    }, fallback: { notification(.success) })
}
```

**Notes for the implementer**
- Keep the existing game-specific one-liners (`cardPlay()`, `cardDraw()`, `steal()`, `vote()`,
  `error()`, `tribalStart()`) exactly as they are — they already mirror the web's light/medium/heavy
  vibration table. Only `elimination()` and `winner()` should be re-pointed at the new patterns.
- `playsHapticsOnly = true` is important: it stops Core Haptics from claiming/altering the
  `AVAudioSession` that §Audio's engine owns.
- `isAutoShutdownEnabled = true` + `resetHandler` covers the engine being torn down on
  backgrounding; the `liveEngine()` lazy re-create handles the rest.
- ⚠️ Intensity/sharpness are `Float` 0…1; `relativeTime` is `TimeInterval` in seconds.
- SwiftUI's `.sensoryFeedback(_:trigger:)` (iOS 17) is a fine declarative shorthand for the *simple*
  cases (`.impact(weight: .heavy)`, `.success`) — it cannot express these patterns, so use it only
  where the current `HapticEngine.impact(...)` calls live, if you want to reduce imperative calls.

---

## §Audio

The web synthesizes **everything live** — no audio files (`narrator.js` `SoundManager`). Gated by
`SurvivorSettings.soundOn()` and a narrator mute in `localStorage.survivorSoundMuted`. iOS should
keep the "no assets, all math" property: it's ~200 lines, ships zero bytes of audio, and stays
perfectly in sync with the design doc.

### Architecture recommendation

Two viable shapes:

1. **Pre-render each cue once into an `AVAudioPCMBuffer`, play via `AVAudioPlayerNode`** —
   *recommended.* Synthesis is still procedural (the same formulas), but it happens **off** the
   realtime audio thread, at first use, into a cached buffer. No realtime-safety constraints, trivial
   overlapping playback, and re-triggering a cue is a scheduleBuffer call. Total memory for all seven
   cues at 44.1 kHz mono float32: ~1.1 MB.
2. **`AVAudioSourceNode` streaming synthesis** — what the brief names. Correct and workable, but the
   render block must be **realtime-compliant**: no allocation, no locks, no Swift runtime calls that
   can allocate, no `os_unfair_lock` contention with the main thread. Voice state has to live in a
   preallocated ring of structs. Use this only if you later want continuous/parameterized audio (a
   droning fire bed, pitch-bending on the fly).

The sketch below is (1), with the `AVAudioSourceNode` variant noted after it.

### Minimal procedural synth engine

```swift
import AVFoundation

actor SoundEngine {
    enum Cue: CaseIterable { case tribalGong, torchSnuff, voteReveal, cardPlay,
                                  victory, steal, notification }

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let format = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
    private var cache: [Cue: AVAudioPCMBuffer] = [:]
    private var started = false

    /// `.ambient` = respects the silent switch and never interrupts other audio — correct for a game
    /// whose sound is decoration, not content. Activated lazily on first cue.
    private func startIfNeeded() throws {
        guard !started else { return }
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.ambient, mode: .default, options: [.mixWithOthers])
        try session.setActive(true)
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
        try engine.start()
        player.play()
        started = true
    }

    func play(_ cue: Cue) {
        guard SettingsStore.soundOn, !SettingsStore.narratorMuted else { return }
        do {
            try startIfNeeded()
            let buf = try cache[cue] ?? render(cue)
            cache[cue] = buf
            player.scheduleBuffer(buf, at: nil, options: [])       // overlapping cues just layer
        } catch { started = false }                                 // retry cleanly next time
    }

    func suspend() { engine.pause(); try? AVAudioSession.sharedInstance().setActive(false)
                     started = false }                              // call on .background
}
```

Synthesis primitives (the parts that actually encode the recipes):

```swift
extension SoundEngine {
    /// Web Audio's exponentialRampToValueAtTime: v(t) = v0 * (v1/v0)^(t/T)
    @inline(__always)
    static func expRamp(_ v0: Float, _ v1: Float, _ t: Float, _ T: Float) -> Float {
        v0 * powf(v1 / v0, min(t / T, 1))
    }

    private func render(_ cue: Cue) throws -> AVAudioPCMBuffer {
        let sr = Float(format.sampleRate)
        let (dur, gen): (Float, (Int, Float) -> Float) = spec(for: cue, sampleRate: sr)
        let n = AVAudioFrameCount(dur * sr)
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: n)
        else { throw CocoaError(.coderInvalidValue) }
        buf.frameLength = n
        let out = buf.floatChannelData![0]
        var phase: Float = 0
        for i in 0..<Int(n) { out[i] = gen(i, phase); phase += 1 }   // phase kept per-generator
        return buf
    }
}
```

Per-cue generators follow directly from the table below. Two DSP helpers are needed:
- **One-pole lowpass** for `torch_snuff`, coefficient recomputed each sample as the cutoff sweeps:
  `let a = expf(-2 * .pi * fc / sr); y = (1 - a) * x + a * yPrev`. (An RBJ 2-pole lowpass is a closer
  match to `BiquadFilterNode` if the hiss sounds too soft; the one-pole is usually indistinguishable
  at 5 % of the mix.)
- **RBJ bandpass (constant 0 dB peak)** for `card_play` at f0 = 1000 Hz, Q = 1, computed once (static
  cutoff) — standard coefficients, ~8 lines.

### Per-cue parameter table

Taken verbatim from the extraction's §Sound. `exp` = Web Audio `exponentialRampToValueAtTime`.

| # | Cue | Source | Frequency envelope | Gain envelope | Duration | Trigger event |
|---|---|---|---|---|---|---|
| 1 | `tribal_gong` | 1 × **sine** osc | 80 Hz → 40 Hz, exp over 2.0 s | 0.5 → 0.01, exp over 2.0 s | 2.0 s | phase → `playing`; phase → `tribal_announcement`; `tribal_start` event |
| 2 | `torch_snuff` | **white noise** buffer, per-sample amplitude `exp(-i / (sr × 0.3))` baked in | lowpass cutoff 3000 Hz → 200 Hz, exp over 1.5 s | fixed **0.4** (post-filter) | 1.5 s buffer (audible tail ≈0.5 s) | `elimination` event — fire with `torchSnuff` visual + haptic |
| 3 | `vote_reveal` | 1 × **sine** osc | 150 Hz → 50 Hz, exp over 0.2 s | 0.6 → 0.01, exp over 0.3 s (loudest cue) | 0.3 s | phase → `tribal_reveal` |
| 4 | `card_play` | **white noise** buffer, amplitude `sin(t·π) × 0.5` baked in | bandpass f0 = **1000 Hz, Q = 1** (static) | unity (no gain node) | 0.3 s | `card_played` (all cards, incl. idol / nullifier) |
| 5 | `victory` | 4 × **triangle** oscs — C5 523.25, E5 659.25, G5 783.99, C6 1046.50 Hz; note *i* starts at `i × 0.15 s` | constant per note | per note: 0 → **0.3** linear over 50 ms, then exp → 0.01 by +0.5 s | ≈0.95 s total | `winner` — fire with confetti + `HapticEngine.winner()` |
| 6 | `steal` | 1 × **sawtooth** osc | 800 Hz → 200 Hz, exp over 0.15 s | 0.2 → 0.01, exp over 0.15 s | 0.15 s (snappiest) | `steal` event |
| 7 | `notification` | 1 × **sine** osc, constant **880 Hz** (A5) | — | 0.2 → 0.01, exp over 0.2 s | 0.2 s | `vote_cast` |

Triangle wave for cue 5: `2/π · asin(sin(2π f t))`, or an additive sum of odd harmonics
`Σ (-1)^k sin((2k+1)ωt) / (2k+1)²` truncated at 8 partials (cheaper and band-limited — avoids
aliasing on the C6).

### `AVAudioSourceNode` variant (if you take approach 2)

```swift
let node = AVAudioSourceNode(format: format) { _, _, frameCount, ablPointer -> OSStatus in
    let abl = UnsafeMutableAudioBufferListPointer(ablPointer)
    let out = abl[0].mData!.assumingMemoryBound(to: Float.self)
    for f in 0..<Int(frameCount) {
        out[f] = voices.renderOneSample()      // preallocated fixed-size voice pool, no allocs
    }
    return noErr
}
engine.attach(node); engine.connect(node, to: engine.mainMixerNode, format: format)
```
⚠️ Everything reachable from that block must be allocation-free and lock-free. Trigger cues by
writing into a lock-free SPSC ring buffer from the main actor and draining it at the top of the
render block. This is why approach (1) is the recommendation.

### Session and lifecycle notes
- **`.ambient`** (with `.mixWithOthers`) is the right category: the silent switch mutes the game, and
  the player's music keeps playing. Never use `.playback` — a card-game bleep should not duck Spotify.
- Activate the session and start the engine **lazily on first cue**, not at launch — avoids an audio
  session claim on every cold start and keeps startup cheap.
- On `scenePhase == .background`, call `suspend()` (pause engine + deactivate session). Re-arm on the
  next cue via `startIfNeeded()`.
- `AVAudioEngine` throws on route changes (headphones unplugged, call arrives). Observe
  `AVAudioSession.routeChangeNotification` and `.mediaServicesWereResetNotification`, and on either
  set `started = false` so the next cue rebuilds the graph.
- Respect **both** gates the web has: the device setting (`soundOn`) and the narrator's own mute
  (`survivorSoundMuted` → a `UserDefaults` key). Two independent switches, same as the web.
- Narration is **not** speech synthesis. The web narrator is a **typewriter effect at 30 ms/char**
  with a hard-blinking `▋` cursor. Port it as an async text-reveal (`Task` + `Task.sleep(for:
  .milliseconds(30))` appending to `@State private var shown: String`) plus the `NarratorCursor` from
  §Techniques 13. Do not reach for `AVSpeechSynthesizer` — it would change the app's character.

---

## §Fonts on iOS

Both families are **SIL Open Font License 1.1** — free to bundle and ship commercially, no paid
license, no attribution UI required (keep `OFL.txt` alongside the files in the repo).

### Fraunces (display / ceremony)

**On iOS: no.** Not a system font, not available via any Apple API.

**Recommendation: bundle it.** Fraunces is the single strongest signature of this design — the
wordmark, every screen title, ceremony titles, the giant game code, card names, narrator italics, and
vote-count numbers are all Fraunces, several of them at weight 850/900 with the `SOFT`/`WONK`
variation axes dialed in. Substituting New York makes the app read as generic-Apple.

**Files** (from `google/fonts/ofl/fraunces`, verified — this directory ships **only** the variable
fonts, no statics):
- `Fraunces[SOFT,WONK,opsz,wght].ttf`
- `Fraunces-Italic[SOFT,WONK,opsz,wght].ttf` (needed — ceremony titles and all narrator text are italic)

Two variable files cover every recipe in the extraction (weights 400–900, opsz 9–144, SOFT, WONK).

⚠️ Rename them before adding — square brackets and commas in a bundled resource filename are legal
but a maintenance hazard across xcodegen / Xcode / CI. Use `Fraunces-Variable.ttf` and
`Fraunces-Italic-Variable.ttf`. **Renaming the file does not change the internal family name**, which
is what `UIAppFonts` resolution and `Font.custom` use.

**Driving the variation axes at runtime** (this is how you get `"SOFT" 30, "WONK" 1` etc.):

```swift
import UIKit
import SwiftUI

enum SurvivorFont {
    // 4-char OpenType axis tags as OSType integers.
    private static let wght: UInt32 = 0x77676874   // 'wght'
    private static let opsz: UInt32 = 0x6F70737A   // 'opsz'
    private static let SOFT: UInt32 = 0x534F4654   // 'SOFT'
    private static let WONK: UInt32 = 0x574F4E4B   // 'WONK'

    /// e.g. screen titles: display(33, weight: 850, soft: 40, wonk: 1)
    static func display(_ size: CGFloat, weight: CGFloat, soft: CGFloat,
                        wonk: CGFloat = 1, italic: Bool = false,
                        relativeTo style: Font.TextStyle = .largeTitle) -> Font {
        let name = italic ? "Fraunces-Italic" : "Fraunces"      // verify at runtime, see below
        let desc = UIFontDescriptor(fontAttributes: [
            .name: name,
            UIFontDescriptor.AttributeName(rawValue: kCTFontVariationAttribute as String): [
                wght: weight, opsz: min(max(size, 9), 144), SOFT: soft, WONK: wonk
            ]
        ])
        return Font(UIFont(descriptor: desc, size: size)).leading(.tight)  // headings lh 1.12
    }
}
```
- Axis identifiers are the 4-byte tag as a number (`'wght'` = `0x77676874`). Confirmed working on iOS
  via `kCTFontVariationAttribute` on `UIFontDescriptor`.
- ⚠️ `UIFont(descriptor:size:)` **bakes the point size**, so Dynamic Type doesn't scale it for free.
  Wrap with `UIFontMetrics(forTextStyle: style).scaledFont(for: uiFont)` before `Font(_:)` to restore
  scaling. The web's `html.text-large` / `.text-xl` settings (110 % / 122 %) then become redundant —
  Dynamic Type covers it natively, as the extraction notes.
- ⚠️ **Verify the registered names on first run** — variable-font name tables vary. Print
  `UIFont.familyNames.filter { $0.contains("Fraunces") }` and
  `UIFont.fontNames(forFamilyName: "Fraunces")` once, and hard-code the exact PostScript names. Do not
  ship without doing this; a wrong name silently falls back to the system font.
- If runtime axes prove fiddly, the fonts.google.com download UI also emits a `static/` folder of
  baked instances (per opsz × SOFT × weight). Take only the instances the recipes need — but that's
  6–8 files vs. 2, so prefer the variable route.

**No-bundle fallback (if bundling is vetoed):** `Font.system(size:weight:design: .serif)` → **New
York**, free, Dynamic Type-native, weights to `.black`. Set `.fontDesign(.serif)` at the screen root.
Rated **APPROXIMATE**: correct genre, wrong voice — New York is a clean transitional serif; Fraunces
is a wonky soft-serif with visible personality. The 900-italic ceremony titles lose the most.

### Alegreya Sans (body)

**On iOS: no.** But the web stack is literally `"Alegreya Sans", -apple-system, "Segoe UI",
sans-serif` — **`-apple-system` is the sanctioned second choice, and that is SF**.

**Recommendation: do NOT bundle. Use the system font (SF).** Rationale:
- The design already blesses SF as the fallback.
- Body copy is the one place where SF's optical sizing, Dynamic Type, tabular figures
  (`.monospacedDigit()` for the story-drawer timestamps the extraction calls out), and full
  localisation coverage matter most.
- Saves five font files and ~700 KB.
- The distinctive-serif/plain-sans contrast that carries the design lives in **Fraunces**, not here.

If a designer insists on parity: `google/fonts/ofl/alegreyasans` (verified names) — bundle
`AlegreyaSans-Regular.ttf`, `-Medium.ttf`, `-Bold.ttf`, `-ExtraBold.ttf`, `-Italic.ttf` (the exact
weights the Google Fonts URL loads: 400/500/700/800 + italic 400). Rated **APPROXIMATE-to-DIRECT**,
but not worth the cost.

### Alegreya Sans SC (labels — small caps)

This is the "ritual layer": every button label, form label, chip, eyebrow, phase pill, turn step,
loading text. The extraction is explicit that it's a **true small-caps font** — every label renders
as letter-spaced small caps with no `text-transform`.

**On iOS: no — but SF has real small caps.** `Font.smallCaps()` maps to the OpenType
`lowerCaseSmallCaps` + `upperCaseSmallCaps` features, and **SF Pro ships them**, working
automatically with Dynamic Type.

**Recommendation: use SF small caps.** No bundling.

```swift
extension SurvivorFont {
    /// The label layer: SF small caps + the web's tracking tokens.
    /// track-label 0.14em, track-wide 0.22em → tracking = em × pointSize.
    static func label(_ size: CGFloat, wide: Bool = false,
                      relativeTo style: Font.TextStyle = .caption) -> Font {
        .system(size: size, weight: .bold, design: .default).smallCaps()
    }
}
// Usage — buttons: 0.84rem ≈ 13.4pt, 0.14em → 1.9pt tracking
Text("cast your vote").font(SurvivorFont.label(13.4)).tracking(13.4 * 0.14)
// Eyebrow: 0.72rem ≈ 11.5pt, 0.22em → 2.5pt tracking
Text("the tribe").font(SurvivorFont.label(11.5)).tracking(11.5 * 0.22)
    .foregroundStyle(SurvivorTheme.torch)
```
⚠️ Feed `.smallCaps()` **lowercase** source strings. Passing already-uppercase text produces
all-caps-sized glyphs, not small caps — a common and easily-missed bug. Where the web uses explicit
`text-transform: uppercase` (game-code input, camp-menu titles, HOF dates, card timing labels, phase
pills, RPS labels, settings headers), use `.textCase(.uppercase)` + tracking **without**
`.smallCaps()`, which matches the web exactly.

**If parity is required:** `google/fonts/ofl/alegreyasanssc` (verified) — `AlegreyaSansSC-Medium.ttf`,
`-Bold.ttf`, `-ExtraBold.ttf` (the three weights the Google Fonts URL loads: 500/700/800). Three
files. Rated **DIRECT PORT** if bundled. This is the *second*-highest-value bundle after Fraunces, so
if the budget is "bundle one more family," it's this one.

### Wiring bundled fonts (xcodegen)

⚠️ **The pbxproj is generated** — `ios/project.yml` says so explicitly ("Hand-edits get clobbered").
Every step goes through `project.yml` + `xcodegen generate`.

1. Put the files in `ios/SurvivorGame/Resources/Fonts/` alongside `OFL.txt`.
   The existing `resources` entry already covers them — `project.yml` has:
   ```yaml
   resources:
     - path: SurvivorGame/Resources
       buildPhase: resources
   ```
   Anything under `Resources/` is copied into the bundle. **No `project.yml` change needed for the
   files themselves.**
2. Declare `UIAppFonts` in the generated Info.plist via `project.yml`'s `info.properties` (this is the
   part that must go in `project.yml`, since `ios/SurvivorGame/App/Info.plist` is the *template* and
   xcodegen merges `properties` over it):
   ```yaml
   info:
     path: SurvivorGame/App/Info.plist
     properties:
       # ... existing keys ...
       UIAppFonts:
         - Fraunces-Variable.ttf
         - Fraunces-Italic-Variable.ttf
         - AlegreyaSansSC-Medium.ttf
         - AlegreyaSansSC-Bold.ttf
         - AlegreyaSansSC-ExtraBold.ttf
   ```
   `UIAppFonts` entries are **filenames only** — no `Resources/Fonts/` prefix — because the resources
   build phase flattens them to the bundle root.
3. `cd ios && xcodegen generate`, then build.
4. **Verify once at launch** (debug only) that every family registered:
   ```swift
   #if DEBUG
   for f in ["Fraunces", "Alegreya Sans SC"] {
       print(f, UIFont.fontNames(forFamilyName: f))   // empty array == not registered
   }
   #endif
   ```

### Type scale (rem → pt), for the implementer

The web is fully rem-based with viewport clamps; on a 390 pt phone the resolved sizes are:

| Token | ≈ pt @390 | Use |
|---|---|---|
| `--display-xl` | 56 | wordmark H1, big game code |
| `--display-lg` | 33 | screen titles, ceremony titles |
| `--display-md` | 24 | elimination heading |
| `--display-sm` | 19 | modal title, turn-ribbon name |
| `--font-size-lg` | 17 | narrator quotes |
| `--font-size-base` | 15.5 | body (line-height 1.5) |
| `--font-size-sm` | 13.4 | button labels, narrator line |
| `--font-size-xs` | 11.5 | eyebrows, chips, form labels, step pills |

Headings use `line-height: 1.12` → `.leading(.tight)`; body `1.5` → `.lineSpacing(size * 0.5)`.
Anchor each to a `Font.TextStyle` via `UIFontMetrics` so Dynamic Type scales the whole app the way
the web's `html.text-large` / `.text-xl` settings did.

The **screen-title overlap** (`margin-bottom: -0.42em`, the oversized title deliberately overlapping
the panel below it) is a signature editorial move and ports cleanly: give the panel
`.padding(.top, 34)` and the title `.padding(.bottom, -titleSize * 0.42)` inside a `VStack(spacing: 0)`,
with the title `.zIndex(1)` so it draws over the panel's top edge.

---

## Summary of feasibility ratings

| Item | Technique | Rating |
|---|---|---|
| torchFlicker | `keyframeAnimator(repeating:)`, 2 tracks + duration jitter | DIRECT PORT |
| smokeDrift | `repeatForever(autoreverses:)` on 2 states | DIRECT PORT |
| torchSnuff | `keyframeAnimator(trigger:)`; `colorMultiply` for CSS `brightness()` | DIRECT PORT |
| riseIn | custom `Transition` + index-delayed `withAnimation` | DIRECT PORT |
| fadeIn | `AnyTransition` combo | DIRECT PORT |
| ballotFlip | `keyframeAnimator` + `rotation3DEffect(perspective: 0.5)` | DIRECT PORT |
| turnPulse | `keyframeAnimator` + inset stroke ring, `MoveKeyframe` × 2 | DIRECT PORT |
| pulseHighlight | same modifier, different constants | DIRECT PORT |
| voteSlam | `keyframeAnimator` + `SpringKeyframe` overshoot, overlay | DIRECT PORT |
| confettiFall | `TimelineView(.animation)` + `Canvas`, 150 pieces | DIRECT PORT |
| spin | trimmed `Circle` + `repeatForever(autoreverses: false)` | DIRECT PORT |
| emberFloat | shared `Canvas` particle field, `.plusLighter` | DIRECT PORT (new) |
| stepGlow | `repeatForever` / `TimelineView(.periodic)` for the hard blink | DIRECT PORT |
| Glowing CTA | `ButtonStyle` + gradient + `ShapeStyle.shadow(.inner/.drop)` | DIRECT PORT |
| Layered cards | ZStack fills + clipped top rule + `compositingGroup` | DIRECT PORT |
| Box-shadow glows | `.shadow` table; `ShapeStyle.shadow` for stacks | DIRECT PORT |
| Gradient borders | `strokeBorder(LinearGradient)` / clipped edge overlay | DIRECT PORT |
| Background scene | `EllipticalGradient` × 2 + cached noise tile | DIRECT PORT |
| Grain via Metal shader | `colorEffect` + `.metal` | APPROXIMATE (optional) |
| matchedGeometry card→sheet | shared namespace, in-hierarchy overlay | APPROXIMATE / SKIP across `.sheet` |
| `.symbolEffect` for flicker | `.pulse` | SKIP — wrong rhythm |
| Fraunces | bundle 2 variable TTFs + `kCTFontVariationAttribute` | DIRECT PORT |
| Alegreya Sans | use system SF (design-sanctioned fallback) | APPROXIMATE (by design) |
| Alegreya Sans SC | SF `.smallCaps()` + tracking, or bundle 3 TTFs | APPROXIMATE / DIRECT if bundled |
| 7 audio cues | `AVAudioEngine` + pre-rendered procedural `AVAudioPCMBuffer`s | DIRECT PORT |
| 5 haptic patterns | Core Haptics `CHHapticPattern` + parameter curves | DIRECT PORT (improves on web) |

---

### Sources
- [SwiftUI keyframe animations (iOS 17)](https://www.hackingwithswift.com/quick-start/swiftui) · [Advanced Keyframe Animations in SwiftUI](https://blog.jacobstechtavern.com/p/swiftui-keyframe-animations) · [Keyframes in iOS 17 — Exyte](https://exyte.com/blog/keyframes-ios17)
- [Metal shaders in SwiftUI (layer/color/distortion effects, iOS 17)](https://www.hackingwithswift.com/quick-start/swiftui/how-to-add-metal-shaders-to-swiftui-views-using-layer-effects) · [Metal in SwiftUI: How to Write Shaders](https://blog.jacobstechtavern.com/p/metal-in-swiftui-how-to-write-shaders)
- [Animate symbols in your app — WWDC23](https://developer.apple.com/videos/play/wwdc2023/10258/) · [Animate SF Symbols with symbolEffect](https://sarunw.com/posts/animate-sf-symbols-with-symboleffect/)
- [CHHapticParameterCurve](https://www.hackingwithswift.com/example-code/core-haptics/how-to-modify-haptic-events-over-time-using-chhapticparametercurve) · [Custom vibrations with Core Haptics](https://www.hackingwithswift.com/example-code/core-haptics/how-to-play-custom-vibrations-using-core-haptics) · [Haptics on Apple platforms](https://blog.eidinger.info/haptics-on-apple-platforms)
- [AVAudioSourceNode low-level audio in Swift](https://orjpap.github.io/swift/real-time/audio/avfoundation/2020/06/19/avaudiosourcenode.html) · [Building a Synthesizer in Swift](https://betterprogramming.pub/building-a-synthesizer-in-swift-866cd15b731)
- [Fraunces (google/fonts, OFL)](https://github.com/google/fonts/tree/main/ofl/fraunces) · [Alegreya Sans (google/fonts, OFL)](https://github.com/google/fonts/tree/main/ofl/alegreyasans) · [Alegreya Sans SC (google/fonts, OFL)](https://github.com/google/fonts/tree/main/ofl/alegreyasanssc) · [Fraunces license — Font Squirrel](https://www.fontsquirrel.com/license/fraunces)
- [Variable fonts via kCTFontVariationAttribute on iOS](https://aplus.rs/2025/using-variable-custom-font-4-italic-condensed-black/) · [SwiftUI under the Hood: Fonts](https://movingparts.io/fonts-in-swiftui) · [Tweaking the iOS system fonts (small caps)](https://useyourloaf.com/blog/tweaking-the-ios-system-fonts/)
