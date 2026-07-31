import SwiftUI

struct LobbyScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: LobbyViewModel?
    @State private var showRename = false
    @State private var newName = ""

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
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                newName = gameClient.playerName ?? ""
                                showRename = true
                            } label: {
                                Image(systemName: "pencil")
                            }
                            .accessibilityLabel("Change your name")
                        }
                    }
                    .alert("What does the tribe call you?", isPresented: $showRename) {
                        TextField("Your name", text: $newName)
                        Button("Rename") {
                            Task { await vm.renameSelf(to: newName) }
                        }
                        Button("Cancel", role: .cancel) {}
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

            // Computer players: fill the tribe and play solo
            if viewModel.isHost {
                VStack(spacing: 8) {
                    HStack {
                        Label("Computer players", systemImage: "cpu")
                            .font(.subheadline)
                        Spacer()
                        Button {
                            Task { await viewModel.addBot() }
                        } label: {
                            Image(systemName: "plus.circle.fill")
                                .font(.title3)
                        }
                        .disabled(viewModel.playerCount >= 6)
                        .accessibilityLabel("Add a computer player")
                    }
                    ForEach(viewModel.players.filter(\.isBot)) { bot in
                        HStack {
                            Circle().fill(bot.swiftUIColor).frame(width: 10, height: 10)
                            Text(bot.name).font(.caption)
                            Spacer()
                            Button {
                                Task { await viewModel.removeBot(bot.id) }
                            } label: {
                                Image(systemName: "minus.circle")
                                    .foregroundStyle(.secondary)
                            }
                            .accessibilityLabel("Remove \(bot.name)")
                        }
                    }
                }
                .padding()
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }

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
