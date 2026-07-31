# iOS Review Fixes + Torchlit Design Pass

**Date:** 2026-07-31
**Approved by:** Tyler
**Branches:** `fix/review-findings`, `feature/torchlit-design` → both merge to `main` when green.

## Goal

Fix the four findings from the island-access-gate code review, then bring the iOS
app's look, motion, sound, and feel in line with the web app's torchlit design
language. Everything verified (build + unit tests + UI tests via Xcode MCP) and
pushed to GitHub.

## Workstream A — Review fixes (`fix/review-findings`)

### A1. Mid-game auth recovery reconnects the socket
`GameClient.unlockIsland` currently only sets `accessState = .unlocked`. After a
successful unlock, if `gameId != nil`, it must also re-establish the socket
(`connect()`, which performs the room rejoin) and `syncState()`. Additionally,
the ConnectionBanner must render when `connectionState == .disconnected` while a
game is active, so a dead socket is never invisible.

### A2. ShareLink uses the connected island
`LobbyScreen`'s ShareLink builds its URL from `gameClient.baseURL`
(`<baseURL>/?join=<gameId>`) instead of the hardcoded public island, matching
the web client's `window.location.origin` behavior.

### A3. Legacy-LAN migration becomes one-shot
`ServerConfig.loadDefault` rewrites the legacy LAN URL → public island on every
call. Gate the rewrite behind a persisted one-shot flag (UserDefaults, e.g.
`didMigrateLegacyLANDefault`) so a user-re-entered LAN URL is never clobbered.
The code comment ("user-entered servers remain untouched") becomes true.

### A4. UI tests: robust + documented + actually run
- `AuthenticationUITests` stays in the default scheme.
- `setUp` performs a reachability pre-check against the scratch server
  (`http://127.0.0.1:8099`); if unreachable, `XCTSkip` with a message that
  includes the exact server launch command. Clean checkouts stay green.
- Setup documented in `ios/SurvivorGameUITests/README.md` (server command,
  `SURVIVOR_ACCESS_CODE=torchtest2468`, port).
- Verification: start the scratch server locally, run the full suite (unit +
  UI) through the Xcode MCP tools, and confirm the UI test exercises the real
  unlock flow (not the skip path).

## Workstream B — Design research (parallel with A)

Two research agents; output committed as `docs/design/torchlit-ios-research.md`.

1. **Web design-language extraction** from `client/dist/styles.css`, `ui.js`,
   `narrator.js`: full palette (hex), the three font roles
   (`--font-body/display/label`) and their actual families, all 13 keyframe
   animations (torchFlicker, smokeDrift, torchSnuff, riseIn, fadeIn, ballotFlip,
   turnPulse, pulseHighlight, voteSlam, confettiFall, spin, emberFloat,
   stepGlow) with durations/easings/properties, component styling patterns
   (glows, borders, card treatments), and how AudioContext synthesizes each
   sound cue.
2. **SwiftUI capability mapping** (iOS 17 target): `keyframeAnimator` /
   `phaseAnimator`, `TimelineView` + `Canvas` for flicker/ember particles,
   Metal shader view effects (`colorEffect`/`distortionEffect`/`layerEffect`),
   `matchedGeometryEffect` and custom `Transition`s, CoreHaptics pattern
   design, AVAudioEngine procedural synthesis. Each web token/animation gets a
   concrete technique + feasibility call.

## Workstream C — Torchlit implementation (`feature/torchlit-design`)

Branches from `main` after A merges; consumes B's research doc.

### C1. Shared design system first (sequential foundation)
- `Theme` — colors + typography matching the web palette and font roles.
- Effect components — flame flicker, ember field, glow button style, card
  style, reveal transitions. One implementation each, reused everywhere.
- `HapticEngine` extensions — CoreHaptics patterns for vote slam, torch snuff,
  turn pulse, and similar signature moments.
- Procedural sound engine — AVAudioEngine synthesis mirroring `narrator.js`
  cues (respecting silent mode; audio session category `.ambient`).

### C2. Per-screen application (parallel agents after C1)
- Start + Island Access gate
- Lobby
- Playing screen (including vote/elimination signature moments: voteSlam,
  ballotFlip, torchSnuff with paired haptic + sound)
- Drawers/sheets (Story So Far, Hall of Fame, Settings)

### C3. App icon migration
The iOS `AppIcon.appiconset` is currently empty. Generate a 1024×1024 icon from
`client/dist/icon-512x512.png` (sips upscale, alpha flattened to opaque), wire
it as a single-size app icon, verify it appears on the simulator home screen.

## Verification & merge flow

- Workstream A: full suite (unit + UI with scratch server) via Xcode MCP →
  merge `fix/review-findings` → `main` → push.
- Workstream C: build + run in simulator via Xcode MCP; screenshot each
  restyled screen and compare against the web references in
  `docs/reviews/ios-port-audit/`; full test suite; then merge
  `feature/torchlit-design` → `main` → push.
- The pbxproj is generated: any target/resource changes go through
  `ios/project.yml` + `xcodegen generate`, never hand-edits.

## Out of scope

- Web client changes (reference only).
- Server changes.
- New game features; this effort is fixes + design parity only.
