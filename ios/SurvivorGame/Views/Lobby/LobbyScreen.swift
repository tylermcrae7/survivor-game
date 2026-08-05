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
                    .tint(Torch.Color.torch)
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
    @Environment(GameClient.self) private var gameClient
    @Bindable var viewModel: LobbyViewModel
    @State private var knownPlayerIds: Set<String> = []
    @State private var newPlayerIds: Set<String> = []

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: Torch.Spacing.lg) {
                    StaggeredRise(index: 0) { gameCodeCard }
                    StaggeredRise(index: 1) { playersPanel }
                    if viewModel.isHost {
                        StaggeredRise(index: 2) { botPanel }
                    }
                }
                .padding(Torch.Spacing.lg)
            }
            .scrollBounceBehavior(.basedOnSize)

            StaggeredRise(index: 3) { startSection }
                .padding(.horizontal, Torch.Spacing.lg)
                .padding(.bottom, Torch.Spacing.lg)
        }
        .background(TorchNightBackground(radialColor: Torch.Color.torch.opacity(0.14),
                                         showEmbers: false, startRadius: 0, endRadius: 460))
        .tint(Torch.Color.torch)
        .errorAlert($viewModel.error)
        .onAppear { knownPlayerIds = Set(viewModel.players.map(\.id)) }
        .onChange(of: viewModel.players.map(\.id)) { _, ids in
            let incoming = Set(ids)
            newPlayerIds = incoming.subtracting(knownPlayerIds)
            knownPlayerIds = incoming
        }
    }

    // Game code — the hero element: Fraunces 900 on the lit panel.
    private var gameCodeCard: some View {
        VStack(spacing: Torch.Spacing.sm) {
            Text("Game Code")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.wide * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            HStack(spacing: 12) {
                Text(viewModel.gameId)
                    .font(Torch.Font.display(Torch.TextSize.displayXL, weight: 900,
                                             soft: 50, wonk: 0, relativeTo: .largeTitle))
                    .tracking(0.08 * Torch.TextSize.displayXL)
                    .foregroundStyle(Torch.Color.flame)
                    .shadow(color: Torch.Color.torch.opacity(0.5), radius: 20)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                    .accessibilityLabel("Game code: \(viewModel.gameId.map { String($0) }.joined(separator: " "))")
                    .accessibilityIdentifier("lobby-game-code")
                    .accessibilityValue(gameClient.connectionState.statusText)

                ShareLink(
                    item: gameClient.baseURL.appending(queryItems: [
                        URLQueryItem(name: "join", value: viewModel.gameId)
                    ]),
                    subject: Text("Join my Survivor game"),
                    message: Text("Fire code: \(viewModel.gameId)")
                ) {
                    Image(systemName: "square.and.arrow.up")
                        .font(.title3)
                        .foregroundStyle(Torch.Color.torch)
                }
                .accessibilityLabel("Share game code")
                .accessibilityHint("Share the game code with other players")
            }
        }
        .padding(Torch.Spacing.md)
        .padding(.vertical, Torch.Spacing.sm)
        .frame(maxWidth: .infinity)
        .torchCard()
    }

    // Players
    private var playersPanel: some View {
        VStack(alignment: .leading, spacing: Torch.Spacing.md) {
            HStack(spacing: Torch.Spacing.sm) {
                Text("Players")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.wide * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.torch)
                LinearGradient(colors: [Torch.Color.torch.opacity(0.5), .clear],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(height: 1) // eyebrow rule
                Text("\(viewModel.playerCount)/8")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)
            }

            if viewModel.players.isEmpty {
                Text("Waiting for players...")
                    .font(Torch.Font.body())
                    .foregroundStyle(Torch.Color.textSecondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 32)
            } else {
                VStack(spacing: Torch.Spacing.sm) {
                    ForEach(Array(viewModel.players.enumerated()), id: \.element.id) { index, player in
                        StaggeredRise(index: index) {
                            LobbyPlayerRow(
                                player: player,
                                isMe: player.id == viewModel.myPlayerId,
                                isNew: newPlayerIds.contains(player.id)
                            )
                        }
                    }
                }
            }
        }
        .padding(Torch.Spacing.md)
        .torchCard()
    }

    // Computer players: fill the tribe and play solo
    private var botPanel: some View {
        VStack(alignment: .leading, spacing: Torch.Spacing.sm) {
            Label("Computer players", systemImage: "cpu")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            ForEach(viewModel.players.filter(\.isBot)) { bot in
                HStack {
                    Circle().fill(bot.swiftUIColor).frame(width: 10, height: 10)
                    Text(bot.name)
                        .font(Torch.Font.body(Torch.TextSize.sm))
                        .foregroundStyle(Torch.Color.text)
                    Spacer()
                    Button {
                        Task { await viewModel.removeBot(bot.id) }
                    } label: {
                        Image(systemName: "minus.circle")
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                    .accessibilityLabel("Remove \(bot.name)")
                }
            }

            Button {
                Task { await viewModel.addBot() }
            } label: {
                Label("Add a computer player", systemImage: "plus")
            }
            .buttonStyle(.torchGhost) // the web uses .btn-ghost here
            .disabled(viewModel.playerCount >= 8)
            .accessibilityLabel("Add a computer player")
        }
        .padding(Torch.Spacing.md)
        .torchCard()
    }

    // Start button
    @ViewBuilder
    private var startSection: some View {
        if viewModel.isHost {
            VStack(spacing: Torch.Spacing.sm) {
                Button {
                    Task { await viewModel.startGame() }
                } label: {
                    if viewModel.isStarting {
                        ProgressView()
                            .tint(Torch.Color.ink)
                    } else {
                        Text("Start Game")
                    }
                }
                .buttonStyle(.torchGlow)
                .disabled(!viewModel.canStart || viewModel.isStarting)
                .accessibilityLabel(viewModel.isStarting ? "Starting game" : "Start game")
                .accessibilityHint(viewModel.canStart ? "Begins the game for all players" : "Need at least 3 players to start")

                if viewModel.playerCount < 3 {
                    Text("Need at least 3 players to start")
                        .font(Torch.Font.label(Torch.TextSize.xs, weight: .semibold))
                        .tracking(Torch.Track.label * Torch.TextSize.xs)
                        .foregroundStyle(Torch.Color.textSecondary)
                }
            }
        } else {
            Text("Waiting for host to start...")
                .font(Torch.Font.display(Torch.TextSize.lg, weight: 500, soft: 40,
                                         wonk: 0, italic: true, relativeTo: .body))
                .foregroundStyle(Torch.Color.parchmentDim)
                .frame(maxWidth: .infinity)
        }
    }
}

/// One tribe-member row (web `.player-card`): sunken well, hairline, 34pt
/// avatar. A player who joins after the screen is up gets the amber
/// pulse-ring ping.
private struct LobbyPlayerRow: View {
    @Environment(PlayerInspector.self) private var inspector
    let player: PlayerState
    let isMe: Bool
    let isNew: Bool
    @State private var pulse = 0

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
        HStack(spacing: 12) {
            PlayerAvatarView(player: player, size: 34, showName: false, isCurrentPlayer: isMe,
                             onTap: { inspector.playerId = player.id })
            Text(player.name)
                .font(Torch.Font.body(weight: .semibold))
                .foregroundStyle(Torch.Color.parchment)
                .lineLimit(1)
                .accessibilityHidden(true) // the avatar element already speaks the row
            Spacer()
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 7)
        .frame(minHeight: Torch.Spacing.touchTarget)
        .background(shape.fill(isMe ? Torch.Color.surface : Torch.Color.surfaceSunken))
        .overlay(shape.strokeBorder(isMe ? Torch.Color.lineStrong : Torch.Color.line,
                                    lineWidth: 1))
        .pulseHighlight(trigger: pulse, cornerRadius: Torch.Radius.lg)
        .task(id: isNew) {
            // Async so the animator always observes the trigger *change*.
            if isNew { pulse += 1 }
        }
    }
}
