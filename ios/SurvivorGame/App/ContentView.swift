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

            if gameClient.connectionState == .reconnecting {
                ConnectionBanner()
            }
        }
        .animation(.default, value: gameClient.navigationState)
    }
}
