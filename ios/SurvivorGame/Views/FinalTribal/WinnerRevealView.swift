import SwiftUI

struct WinnerRevealView: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.modelContext) private var modelContext
    @State private var showConfetti = false

    var body: some View {
        let winner = resolveWinner()

        NavigationStack {
            VStack(spacing: 24) {
                Spacer()

                if let winner {
                    WinnerRevealContent(winner: winner)
                        .onAppear {
                            HapticEngine.winner()
                            showConfetti = true
                            saveGameRecord(winner: winner)
                        }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "flag.checkered")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary)
                        Text("Game Over")
                            .font(.title.bold())
                    }
                }

                Spacer()

                VStack(spacing: 12) {
                    Button("New Game") {
                        gameClient.leaveGame()
                    }
                    .buttonStyle(.survivor)

                    NavigationLink("View History") {
                        GameHistoryView()
                    }
                    .buttonStyle(.survivorSecondary)
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 40)
            }
            .navigationTitle("Game Over")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func resolveWinner() -> PlayerState? {
        if let winnerId = gameClient.gameState?.finalTribal?.winner {
            return gameClient.gameState?.players[winnerId]
        }
        if let winnerId = gameClient.gameState?.winner {
            return gameClient.gameState?.players[winnerId]
        }
        return nil
    }

    private func saveGameRecord(winner: PlayerState) {
        guard let gameId = gameClient.gameId,
              let state = gameClient.gameState
        else { return }

        let record = GameRecord(
            gameId: gameId,
            winnerName: winner.name,
            playerNames: state.sortedPlayers.map(\.name)
        )
        modelContext.insert(record)
        try? modelContext.save()
    }
}

struct WinnerRevealContent: View {
    let winner: PlayerState

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "crown.fill")
                .font(.system(size: 56))
                .foregroundStyle(.yellow)

            Text("Sole Survivor")
                .font(.title3)
                .foregroundStyle(.secondary)

            PlayerAvatarView(player: winner, size: 80)

            Text(winner.name)
                .font(.largeTitle.bold())

            Text("Congratulations!")
                .font(.title3)
                .foregroundStyle(.orange)
        }
    }
}
