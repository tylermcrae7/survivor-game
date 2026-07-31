import SwiftUI

/// Victory-mode re-palette (web `body[data-mode="victory"]` — "dawn finally
/// breaks"). Noticeably lighter warm ground; the vignette lifts.
private enum VictoryPalette {
    static let bg = Color(hex: "#4A2A12") ?? .brown
    static let bgDeep = Color(hex: "#2D1205") ?? .brown
    /// Torchlight stops: bright dawn core → warm mid → clear.
    static let dawnCore = Color(hex: "#F4C677") ?? .orange
    static let dawnMid = Color(hex: "#C16E2D") ?? .orange
}

/// The dawn ground: bigger, brighter torchlight than any night mode.
private struct VictoryBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [VictoryPalette.bg, VictoryPalette.bgDeep],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(stops: [
                .init(color: VictoryPalette.dawnCore.opacity(0.65), location: 0),
                .init(color: VictoryPalette.dawnMid.opacity(0.25), location: 0.55),
                .init(color: .clear, location: 0.75),
            ], center: UnitPoint(x: 0.5, y: -0.18), startRadius: 0, endRadius: 560)
        }
        .ignoresSafeArea()
    }
}

struct WinnerRevealView: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.modelContext) private var modelContext
    @State private var showConfetti = false
    /// Popping back from "View History" re-runs onAppear; the fanfare (and
    /// the SwiftData record insert) must only happen once per reveal.
    @State private var hasCelebrated = false

    var body: some View {
        let winner = resolveWinner()

        NavigationStack {
            VStack(spacing: 24) {
                Spacer()

                if let winner {
                    WinnerRevealContent(winner: winner)
                        .onAppear {
                            guard !hasCelebrated else { return }
                            hasCelebrated = true
                            HapticEngine.winner()
                            TorchSound.play(.victory)
                            showConfetti = true
                            saveGameRecord(winner: winner)
                        }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "flag.checkered")
                            .font(.system(size: 48))
                            .foregroundStyle(Torch.Color.textSecondary)
                        Text("Game Over")
                            .font(Torch.Font.display(Torch.TextSize.displayLG, weight: 850))
                            .foregroundStyle(Torch.Color.parchment)
                    }
                }

                Spacer()

                VStack(spacing: 12) {
                    Button("New Game") {
                        gameClient.leaveGame()
                    }
                    .buttonStyle(.torchGlow)

                    NavigationLink("View History") {
                        GameHistoryView()
                    }
                    .buttonStyle(.torchSecondary)
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 40)
            }
            .frame(maxWidth: .infinity)
            .background(VictoryBackground())
            .overlay {
                // Embers and gold — victory at dawn, not a birthday party.
                if showConfetti {
                    EmberFieldView(style: .confetti)
                        .ignoresSafeArea()
                }
            }
            .tint(Torch.Color.torch)
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
                .foregroundStyle(Torch.Color.juryGold)
                .shadow(color: Torch.Color.juryGold.opacity(0.4), radius: 12) // --glow-gold

            Text("Sole Survivor")
                .font(Torch.Font.label(Torch.TextSize.sm))
                .tracking(Torch.Track.wide * Torch.TextSize.sm)
                .foregroundStyle(Torch.Color.juryGold)

            PlayerAvatarView(player: winner, size: 80)

            CeremonyTitle(text: winner.name)

            Text("Congratulations!")
                .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700, italic: true))
                .foregroundStyle(Torch.Color.juryGold)
        }
    }
}
