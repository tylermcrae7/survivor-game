import SwiftUI

struct ContentView: View {
    @Environment(GameClient.self) private var gameClient

    var body: some View {
        ZStack {
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

            // A running Challenge or Reward Challenge takes the table over
            // (the server blocks ordinary turns while one is live).
            if gameClient.gameState?.challenge?.isComplete == false {
                ChallengeScreen()
            } else if gameClient.gameState?.interaction != nil {
                InteractionScreen()
            }

            // The Sorry-For-You window outranks every screen — an unresolved
            // raid freezes the game for the whole table until it's answered.
            ReactiveTheftOverlay()

            if gameClient.connectionState == .reconnecting {
                ConnectionBanner()
            }
        }
        .animation(.default, value: gameClient.navigationState)
        .onOpenURL { url in
            // survivorgame://join?code=XXXX — the app-side twin of the web's
            // ?join=CODE links.
            guard url.scheme == "survivorgame" else { return }
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
            if let code = components?.queryItems?.first(where: { $0.name == "code" })?.value {
                gameClient.pendingJoinCode = code
            }
        }
    }
}
