import SwiftUI

struct LobbyScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: LobbyViewModel?

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                LobbyContent(viewModel: vm)
                    .navigationTitle("Game Lobby")
                    .toolbar {
                        ToolbarItem(placement: .topBarLeading) {
                            Button("Leave") {
                                vm.leaveGame()
                            }
                        }
                    }
            } else {
                ProgressView()
            }
        }
        .onAppear {
            if viewModel == nil {
                viewModel = LobbyViewModel(gameClient: gameClient)
            }
        }
    }
}

private struct LobbyContent: View {
    @Bindable var viewModel: LobbyViewModel

    var body: some View {
        VStack(spacing: 24) {
            // Game code
            VStack(spacing: 8) {
                Text("Game Code")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                HStack(spacing: 12) {
                    Text(viewModel.gameId)
                        .font(.system(.title, design: .monospaced).bold())
                        .tracking(4)
                        .accessibilityLabel("Game code: \(viewModel.gameId.map { String($0) }.joined(separator: " "))")

                    ShareLink(item: "Join my Survivor game! Code: \(viewModel.gameId)") {
                        Image(systemName: "square.and.arrow.up")
                            .font(.title3)
                    }
                    .accessibilityLabel("Share game code")
                    .accessibilityHint("Share the game code with other players")
                }
            }
            .padding()
            .frame(maxWidth: .infinity)
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Players
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Players")
                        .font(.headline)
                    Spacer()
                    Text("\(viewModel.playerCount)/6")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if viewModel.players.isEmpty {
                    Text("Waiting for players...")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 32)
                } else {
                    LazyVGrid(columns: [
                        GridItem(.flexible()),
                        GridItem(.flexible()),
                        GridItem(.flexible())
                    ], spacing: 16) {
                        ForEach(viewModel.players) { player in
                            PlayerAvatarView(
                                player: player,
                                size: 56,
                                isCurrentPlayer: player.id == viewModel.myPlayerId
                            )
                        }
                    }
                }
            }
            .padding()
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            Spacer()

            // Start button
            if viewModel.isHost {
                VStack(spacing: 8) {
                    Button {
                        Task { await viewModel.startGame() }
                    } label: {
                        if viewModel.isStarting {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text("Start Game")
                        }
                    }
                    .buttonStyle(.survivor)
                    .disabled(!viewModel.canStart || viewModel.isStarting)
                    .accessibilityLabel(viewModel.isStarting ? "Starting game" : "Start game")
                    .accessibilityHint(viewModel.canStart ? "Begins the game for all players" : "Need at least 3 players to start")

                    if viewModel.playerCount < 3 {
                        Text("Need at least 3 players to start")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            } else {
                Text("Waiting for host to start...")
                    .foregroundStyle(.secondary)
            }
        }
        .padding(24)
        .errorAlert($viewModel.error)
    }
}
