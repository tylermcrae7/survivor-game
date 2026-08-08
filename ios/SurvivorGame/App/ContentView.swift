import SwiftUI

struct ContentView: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(PlayerInspector.self) private var inspector

    /// True while a Challenge / Reward Challenge screen is covering the table.
    /// A *complete* one counts: the server parks it until somebody dismisses
    /// it, so its reveal screen is still mounted and still the only thing the
    /// player may touch.
    private var takeoverActive: Bool {
        guard gameClient.accessState == .unlocked else { return false }
        return gameClient.gameState?.challenge != nil
            || gameClient.gameState?.interaction != nil
    }

    var body: some View {
        ZStack {
            Group {
                switch gameClient.accessState {
                case .checking:
                    ProgressView("Finding the island…")
                case .requiresCode:
                    IslandAccessScreen()
                case .unavailable(let message):
                    IslandUnavailableScreen(message: message)
                case .unlocked:
                    gameContent
                }
            }
            // The takeover screens paint over this content but do not remove
            // it, so without these the buried game stays reachable by
            // VoiceOver and by stray taps through transparent areas.
            .accessibilityHidden(takeoverActive)
            .allowsHitTesting(!takeoverActive)

            if gameClient.accessState == .unlocked {
                // A Challenge or Reward Challenge takes the table over (the
                // server blocks ordinary turns while one is live, and holds a
                // finished one until it is dismissed).
                if gameClient.gameState?.challenge != nil {
                    ChallengeScreen()
                } else if gameClient.gameState?.interaction != nil {
                    InteractionScreen()
                }

                // Reactive windows outrank every screen — an unresolved one
                // freezes the game for the whole table until it's answered.
                // Exactly one shows at a time: two stacked modals, each with
                // its own black scrim, would be unreadable and unclosable.
                if gameClient.gameState?.pendingTheft?.reactiveWindowOpen == true {
                    ReactiveTheftOverlay()
                } else if gameClient.gameState?.pendingDiscards?.awaiting.isEmpty == false {
                    PenaltyDiscardOverlay()
                } else {
                    NullifierWindowOverlay()
                }

                // The alliance overlay is its own thing, not part of the
                // "exactly one reactive window" chain above — it never waits
                // on a server answer, so it can sit alongside any of them.
                AllianceOverlay()

                // Same reasoning as AllianceOverlay, but non-blocking: a
                // steal happens on nearly every turn, so this floats over
                // whatever screen is up rather than taking it over.
                RobberyBanner()

                if gameClient.connectionState == .reconnecting
                    || (gameClient.connectionState == .disconnected && gameClient.gameState != nil) {
                    ConnectionBanner()
                }
            }
        }
        // Above every screen, hit-testing off — see NarrationHost.
        .narrationHost()
        // Mounted once at the root rather than per screen: the camp strip lives
        // inside a ScrollView that can unmount its rows, and a sheet presented
        // from a row that disappears goes with it.
        .sheet(isPresented: Binding(
            get: { inspector.playerId != nil },
            set: { if !$0 { inspector.playerId = nil } }
        )) {
            if let id = inspector.playerId {
                PlayerDetailSheet(playerId: id)
                    .environment(gameClient)
            }
        }
        .animation(.default, value: gameClient.navigationState)
        .task {
            if gameClient.accessState == .checking {
                await gameClient.checkIslandAccess()
            }
        }
        .onOpenURL { url in
            // survivorgame://join?code=XXXX, or — once B2's Universal Link
            // opens the app instead of Safari — a tapped https:// link.
            if let code = Self.joinCode(from: url) {
                gameClient.pendingJoinCode = code
            }
        }
        // .onOpenURL alone is sufficient in a SwiftUI-lifecycle app for a
        // registered URL scheme; this is belt-and-braces for the Universal
        // Link path specifically, since NSUserActivity is how iOS actually
        // hands a continued https:// activity to the app.
        .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
            guard let url = activity.webpageURL, let code = Self.joinCode(from: url) else { return }
            gameClient.pendingJoinCode = code
        }
    }

    /// The three shapes a join link arrives in, funnelled through one parser
    /// so `.onOpenURL` and `.onContinueUserActivity` can't drift apart:
    /// `survivorgame://join?code=X` (the app's own scheme), and — once a
    /// Universal Link routes an `https://` tap into the app instead of
    /// Safari — the web's own `/join/X` path and `?join=X` query forms.
    ///
    /// `nonisolated` deliberately: `ContentView` infers `@MainActor` from
    /// `View.body`, and without this a Swift Testing call from off the main
    /// actor traps at runtime (`_swift_task_checkIsolatedSwift`) even though
    /// nothing here touches UI state — pure URL parsing has no business
    /// being actor-isolated at all.
    nonisolated static func joinCode(from url: URL) -> String? {
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        if url.scheme == "survivorgame" {
            return components?.queryItems?.first(where: { $0.name == "code" })?.value
        }
        guard url.scheme == "http" || url.scheme == "https" else { return nil }
        if let joined = components?.queryItems?.first(where: { $0.name == "join" })?.value,
           !joined.isEmpty {
            return joined
        }
        let segments = url.pathComponents.filter { $0 != "/" }
        if let joinIndex = segments.firstIndex(of: "join"), segments.indices.contains(joinIndex + 1) {
            return segments[joinIndex + 1]
        }
        return nil
    }

    @ViewBuilder
    private var gameContent: some View {
        switch gameClient.navigationState {
        case .start:
            StartScreen()
        case .lobby:
            LobbyScreen()
        case .playing:
            PlayingScreen()
        case .tribal:
            TribalScreen()
        case .finalTribal:
            FinalTribalScreen()
        case .finished:
            WinnerRevealView()
        }
    }
}
