# iOS Review Fixes + Torchlit Design Pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four island-access-gate review findings, then bring the iOS app's motion, typography, color, components, sound, haptics, and app icon in line with the web app's torchlit design language.

**Architecture:** Workstream A (fixes, branch `fix/review-findings`) and Workstream B (design research, no code) run in parallel. Workstream C (design system then per-screen application, branch `feature/torchlit-design`) branches from main after A merges and consumes B's research doc. Verification uses XcodeBuildMCP (build, test, simulator screenshots) with the Python scratch server for UI tests.

**Tech Stack:** SwiftUI (iOS 17), SwiftData, CoreHaptics, AVAudioEngine, XcodeGen (pbxproj is generated — all project changes go through `ios/project.yml` + `xcodegen generate`), XCTest/XCUITest, Python scratch server.

**Spec:** `docs/superpowers/specs/2026-07-31-ios-fixes-and-torchlit-design.md`

---

## Ground rules for every task

- Repo root: `/Users/tylermcrae/Documents/GitHub/survivor-game`. iOS code lives in `ios/`.
- NEVER hand-edit `ios/SurvivorGame.xcodeproj/project.pbxproj`. Change `ios/project.yml`, then run `cd ios && xcodegen generate`.
- Match the existing code style: 4-space indent, `// MARK:` sections, sparse comments that state contracts only.
- Commit after each task with a message in the repo's narrative style (lowercase, story-flavored, e.g. "the lobby shares the island it's actually on").
- Unit test command (from `ios/`): `xcodebuild test -project SurvivorGame.xcodeproj -scheme SurvivorGame -destination 'platform=iOS Simulator,name=iPhone 16'` — or the XcodeBuildMCP `test_sim` tool.
- Scratch server for UI tests (from repo root):
  `SURVIVOR_ACCESS_CODE=torchtest2468 PORT=8099 .venv/bin/python survivor_server.py`

---

## Workstream A — Review fixes (branch `fix/review-findings`)

### Task A1: Reconnect the socket after mid-game re-unlock

**Files:**
- Modify: `ios/SurvivorGame/Networking/GameClient.swift:74-94` (`unlockIsland`)
- Modify: `ios/SurvivorGame/App/ContentView.swift:32` (banner condition)
- Test: `ios/SurvivorGameTests/ViewModelTests.swift` (follow existing GameClient test patterns there and in `NetworkingTests.swift`)

- [ ] **Step 1: Inspect existing GameClient test patterns.** Read `ios/SurvivorGameTests/ViewModelTests.swift` and `NetworkingTests.swift`. If a mock/stub for `APIClient`/`SocketClient` exists, write a failing test asserting that after `unlockIsland` succeeds with `gameId` set, the socket client receives a connect call and a sync occurs. If GameClient is not mockable without new seams, skip the unit test — coverage comes from Task A4's UI test flow — and note that in the commit message.

- [ ] **Step 2: Implement the reconnect.** In `GameClient.swift`, `unlockIsland(with:)` currently ends:

```swift
        IslandAccessCookieStore.persist(for: apiClient.baseURL)
        accessState = .unlocked
    }
```

Change to:

```swift
        IslandAccessCookieStore.persist(for: apiClient.baseURL)
        accessState = .unlocked
        // A mid-game 401 tore the socket down; a successful re-unlock must
        // revive it, or the table goes silent until relaunch.
        if gameId != nil {
            connect()
            await syncState()
        }
    }
```

- [ ] **Step 3: Make a dead socket visible mid-game.** In `ContentView.swift` line 32, change:

```swift
                if gameClient.connectionState == .reconnecting {
```

to:

```swift
                if gameClient.connectionState == .reconnecting
                    || (gameClient.connectionState == .disconnected && gameClient.gameId != nil) {
```

Check `ConnectionBanner`'s implementation (`ios/SurvivorGame/Views/Components/`): if its copy assumes "reconnecting", parameterize or generalize the text so a disconnected state reads honestly (e.g. "Connection lost — updates paused").

- [ ] **Step 4: Run unit tests.** Expect PASS (or pre-existing green if Step 1 was skipped).

- [ ] **Step 5: Commit.**

### Task A2: ShareLink uses the connected island

**Files:**
- Modify: `ios/SurvivorGame/Views/Lobby/LobbyScreen.swift:69-72`

- [ ] **Step 1: Replace the hardcoded URL.** Change:

```swift
                    ShareLink(
                        item: URL(string: "https://survivor.mctech.biz/?join=\(viewModel.gameId)")!,
```

to:

```swift
                    ShareLink(
                        item: gameClient.baseURL.appending(queryItems: [
                            URLQueryItem(name: "join", value: viewModel.gameId)
                        ]),
```

`gameClient` is already in scope in this view (used for `connectionState.statusText` a few lines up). Confirm `GameClient` exposes `baseURL`; if it is not public, add `var baseURL: URL { apiClient.baseURL }`.

- [ ] **Step 2: Build.** `build_sim` via XcodeBuildMCP (or `xcodebuild build`). Expect success.

- [ ] **Step 3: Commit.**

### Task A3: One-shot legacy-LAN migration

**Files:**
- Modify: `ios/SurvivorGame/Models/ServerConfig.swift:33-41` (`loadDefault`)
- Test: `ios/SurvivorGameTests/ViewModelTests.swift` (or a new `ServerConfigTests.swift` if no natural home exists — new test files must be under `ios/SurvivorGameTests/`, which project.yml already globs)

- [ ] **Step 1: Write the failing test.** Use an in-memory SwiftData container:

```swift
@MainActor
func testLegacyLANMigrationRunsOnce() throws {
    UserDefaults.standard.removeObject(forKey: "didMigrateLegacyLANDefault")
    let container = try ModelContainer(
        for: ServerConfig.self,
        configurations: ModelConfiguration(isStoredInMemoryOnly: true)
    )
    let context = container.mainContext

    // First load migrates the shipped LAN default to the public island.
    let config = ServerConfig()
    config.baseURL = URL(string: "http://192.168.0.189:8080")!
    context.insert(config)
    try context.save()
    XCTAssertEqual(ServerConfig.loadDefault(from: context).baseURL,
                   ServerConfig.publicIslandURL)

    // A deliberately re-entered LAN URL survives every later load.
    let reloaded = ServerConfig.loadDefault(from: context)
    reloaded.baseURL = URL(string: "http://192.168.0.189:8080")!
    try context.save()
    XCTAssertEqual(ServerConfig.loadDefault(from: context).baseURL.absoluteString,
                   "http://192.168.0.189:8080")
}
```

Adjust the `ServerConfig` init call to the real initializer signature (it takes `baseURL` as a parameter with a default — see `ServerConfig.swift:19`). Run; expect FAIL on the second assertion (today the rewrite repeats).

- [ ] **Step 2: Implement the one-shot flag.** In `loadDefault`, change:

```swift
            if existing.baseURL == legacyLANURL {
                existing.baseURL = publicIslandURL
                try? context.save()
            }
            return existing
```

to:

```swift
            let migrationKey = "didMigrateLegacyLANDefault"
            if existing.baseURL == legacyLANURL,
               !UserDefaults.standard.bool(forKey: migrationKey) {
                existing.baseURL = publicIslandURL
                try? context.save()
            }
            UserDefaults.standard.set(true, forKey: migrationKey)
            return existing
```

- [ ] **Step 3: Run the test.** Expect PASS.

- [ ] **Step 4: Commit.**

### Task A4: UI tests skip cleanly without the scratch server, and get documented

**Files:**
- Modify: `ios/SurvivorGameUITests/AuthenticationUITests.swift:6-8`
- Create: `ios/SurvivorGameUITests/README.md`

- [ ] **Step 1: Add the reachability pre-check.** Replace `setUpWithError`:

```swift
    override func setUpWithError() throws {
        continueAfterFailure = false
        try Self.requireScratchServer()
    }

    /// UI tests drive a real island. Without it, skip loudly instead of
    /// failing the whole default test action on a clean checkout.
    private static func requireScratchServer() throws {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8099/api/access/check")!)
        request.timeoutInterval = 2
        let semaphore = DispatchSemaphore(value: 0)
        var reachable = false
        URLSession.shared.dataTask(with: request) { _, response, _ in
            reachable = (response as? HTTPURLResponse) != nil
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + 3)
        if !reachable {
            throw XCTSkip("""
                Scratch server not running. Start it from the repo root:
                SURVIVOR_ACCESS_CODE=torchtest2468 PORT=8099 .venv/bin/python survivor_server.py
                """)
        }
    }
```

- [ ] **Step 2: Write `ios/SurvivorGameUITests/README.md`** documenting: what the suite covers, the exact server command above, why the access code must be `torchtest2468`, and that the suite auto-skips when the server is absent.

- [ ] **Step 3: Verify both paths via XcodeBuildMCP.** (a) With no server: run tests; expect UI test SKIPPED, units green. (b) Start the scratch server, run again; expect the UI test to PASS through the real unlock flow. Kill the server after.

- [ ] **Step 4: Commit.**

### Task A5: Merge Workstream A

- [ ] **Step 1:** Full suite green via XcodeBuildMCP (units + UI with server running).
- [ ] **Step 2:** `git checkout main && git merge --no-ff fix/review-findings && git push origin main`. Delete the branch.

---

## Workstream B — Design research (parallel with A, no code)

### Task B1: Extract the web design language

Agent reads `client/dist/styles.css`, `client/dist/ui.js`, `client/dist/narrator.js`, `client/dist/index-optimized.html` and writes the first half of `docs/design/torchlit-ios-research.md`:

- **§Palette** — every CSS custom property color with hex value and where it's used.
- **§Typography** — resolved values of `--font-body`, `--font-display`, `--font-label` (families, weights, letter-spacing, text-transform patterns).
- **§Animations** — for each of the 13 keyframes (torchFlicker, smokeDrift, torchSnuff, riseIn, fadeIn, ballotFlip, turnPulse, pulseHighlight, voteSlam, confettiFall, spin, emberFloat, stepGlow): what it animates, duration, easing, trigger context.
- **§Components** — button/card/drawer treatments: borders, radii, glows/shadows, background layers, textures.
- **§Sound** — every AudioContext cue in narrator.js: waveform, frequency envelope, duration, when it plays.

### Task B2: Map to SwiftUI (iOS 17)

Agent researches (WebSearch/WebFetch allowed, sosumi for Apple docs) and writes the second half of the same doc:

- **§Techniques** — for each §Animations entry and each component treatment, the concrete iOS-17 SwiftUI technique: `keyframeAnimator`/`phaseAnimator`, `TimelineView` + `Canvas` particles, shader view effects (`colorEffect`/`distortionEffect`/`layerEffect`), `matchedGeometryEffect`, custom `Transition`, `.shadow`/gradient layering — with a short code sketch each and a feasibility rating (direct port / approximate / skip).
- **§Haptics** — CoreHaptics pattern sketches for voteSlam, torchSnuff, turnPulse, unlock.
- **§Audio** — AVAudioEngine source-node synthesis mapping for each §Sound cue; audio session category `.ambient` (respects silent switch).
- **§Fonts on iOS** — whether the web families are iOS system-available; nearest bundled-free or SF-based substitutes if not (no paid font dependencies).

### Task B3: Commit the research doc to main

`docs/design/torchlit-ios-research.md` is documentation, not app code: commit directly to main and push (it must be on main before C branches).

---

## Workstream C — Torchlit implementation (branch `feature/torchlit-design` off updated main)

All visual constants (hex values, font names, durations, easings) come from `docs/design/torchlit-ios-research.md`. Tasks C2–C5 depend on C1; C2–C5 are parallelizable (disjoint files); C6 is independent of all of them.

### Task C1: Design system foundation

**Files:**
- Create: `ios/SurvivorGame/DesignSystem/Theme.swift` — `enum Torch` namespace: `Torch.Color.*` (background, surface, ember, flame, parchment, danger…), `Torch.Font.display(_:)/body(_:)/label(_:)`, spacing/radius constants. Values from §Palette/§Typography/§Fonts on iOS.
- Create: `ios/SurvivorGame/DesignSystem/FlameEffects.swift` — `FlameFlickerModifier` (TimelineView-driven glow/opacity flicker per §torchFlicker), `EmberFieldView` (Canvas particles per §emberFloat), `.torchGlow()` view extension.
- Create: `ios/SurvivorGame/DesignSystem/TorchComponents.swift` — `GlowButtonStyle`, `TorchCardModifier` (`.torchCard()`), matching §Components.
- Create: `ios/SurvivorGame/DesignSystem/TorchTransitions.swift` — `riseIn`/`fadeIn` transitions, `voteSlam`/`ballotFlip`/`torchSnuff` keyframe animations per §Techniques.
- Create: `ios/SurvivorGame/DesignSystem/TorchAudio.swift` — AVAudioEngine procedural cues per §Audio; a `TorchSound.play(_:)` API; `.ambient` session.
- Modify: `ios/SurvivorGame/Views/Components/HapticEngine.swift` — add the §Haptics patterns alongside existing API.
- Test: `ios/SurvivorGameTests/DesignSystemTests.swift` — theme values resolve (non-nil fonts/colors), sound engine builds its graph without throwing, haptic patterns compile into `CHHapticPattern` without error.

Steps: write tests for the testable surface → implement each file → `cd ios && xcodegen generate` (new files are globbed, but regenerate to be safe) → build + tests green → commit.

### Task C2: Start + Island Access screens adopt the system

**Files:** Modify `ios/SurvivorGame/Views/Start/StartScreen.swift`, `IslandAccessScreen.swift`, `PlayerSetupView.swift`.

Apply `Torch` colors/fonts, `.torchCard()`, `GlowButtonStyle`, `FlameFlickerModifier` on the flame mark, `EmberFieldView` background, `riseIn` entrance per §Animations trigger contexts. Keep every existing `accessibilityIdentifier` intact (UI tests depend on them). Build green → commit.

### Task C3: Lobby adopts the system

**Files:** Modify `ios/SurvivorGame/Views/Lobby/LobbyScreen.swift`.

Torch styling for the code card and player list, `turnPulse`-style highlight for newly joined players, entrance transitions. Preserve accessibility identifiers (`lobby-game-code`). Build green → commit.

### Task C4: Playing screen + signature moments

**Files:** Modify `ios/SurvivorGame/Views/Playing/PlayingScreen.swift`, `ios/SurvivorGame/Views/Components/StorySoFarDrawer.swift`.

Torch styling throughout; the signature moments wired together: vote cast → `voteSlam` animation + slam haptic + thud cue; elimination → `torchSnuff` + snuff haptic + cue; turn change → `turnPulse` + soft haptic. Winner → `confettiFall`. Sounds/haptics fire from the same state changes that drive the animations. Build green → commit.

### Task C5: Drawers, Hall of Fame, Settings adopt the system

**Files:** Modify `ios/SurvivorGame/Views/History/HallOfFameView.swift`, `ios/SurvivorGame/Views/Settings/AppSettingsSheet.swift`.

Torch styling; `stepGlow`/`riseIn` list entrances per research doc. Build green → commit.

### Task C6: App icon migration

**Files:**
- Modify: `ios/SurvivorGame/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json`
- Create: `ios/SurvivorGame/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png`

- [ ] **Step 1:** Generate the 1024 icon (App Store requires opaque 1024×1024):

```bash
sips -z 1024 1024 client/dist/icon-512x512.png \
  --out ios/SurvivorGame/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png
# flatten any alpha:
sips -s format jpeg ios/SurvivorGame/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png --out /tmp/icon-flat.jpg
sips -s format png /tmp/icon-flat.jpg --out ios/SurvivorGame/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png
```

- [ ] **Step 2:** Write `Contents.json` for a single-size icon:

```json
{
  "images" : [
    {
      "filename" : "AppIcon-1024.png",
      "idiom" : "universal",
      "platform" : "ios",
      "size" : "1024x1024"
    }
  ],
  "info" : { "author" : "xcode", "version" : 1 }
}
```

- [ ] **Step 3:** Build, install on simulator, screenshot the home screen to confirm the flame icon renders. Commit.

### Task C7: Verify and merge Workstream C

- [ ] **Step 1:** `cd ios && xcodegen generate`; confirm `git diff` on pbxproj is only the expected new files.
- [ ] **Step 2:** Full suite via XcodeBuildMCP (units + UI with scratch server) — green.
- [ ] **Step 3:** Run in simulator; screenshot Start, Access gate, Lobby, Playing; compare against `docs/reviews/ios-port-audit/0*-web-*.png` for palette/typography/motion fidelity. Save screenshots to `docs/reviews/torchlit-design/`.
- [ ] **Step 4:** Commit screenshots. `git checkout main && git merge --no-ff feature/torchlit-design && git push origin main`. Delete the branch.

---

## Self-review notes

- Spec coverage: A1–A4 ↔ spec A1–A4; B1–B3 ↔ spec B; C1–C5 ↔ spec C1–C2; C6 ↔ spec C3 (icon); C7 ↔ spec verification. Sound/haptics (spec "all four dimensions") land in C1 (engines) + C4 (wiring).
- The only intentional deferrals: exact visual constants live in the research doc (a produced artifact, not a TBD), and A1's unit test is conditional on existing mock seams with UI-test fallback coverage — stated explicitly, not silently.
