import SwiftUI

struct PlayingScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: PlayingViewModel?

    var body: some View {
        if let vm = viewModel {
            PlayingContent(viewModel: vm)
        } else {
            ProgressView().onAppear {
                viewModel = PlayingViewModel(gameClient: gameClient)
            }
        }
    }
}

private struct PlayingContent: View {
    @Bindable var viewModel: PlayingViewModel
    @Environment(GameClient.self) private var gameClient
    @State private var showStory = false
    @State private var showPace = false
    @State private var showSettings = false
    @State private var showHallOfFame = false
    @State private var confirmBurn = false
    @State private var pendingStealTarget: String?
    @AppStorage("confirmSteals") private var confirmSteals = false

    var body: some View {
        VStack(spacing: 0) {
            // The camp strip: fire code chip, story drawer, camp menu
            HStack {
                if let code = gameClient.gameId {
                    SurvivorChip {
                        Text("FIRE").foregroundStyle(.secondary)
                        Text(code).font(.caption.monospaced().bold())
                    }
                }
                Spacer()
                Button {
                    showStory = true
                } label: {
                    Image(systemName: "scroll")
                }
                .accessibilityLabel("The story so far")

                Menu {
                    Button {
                        showSettings = true
                    } label: {
                        Label("Settings", systemImage: "gearshape")
                    }
                    Button {
                        showPace = true
                    } label: {
                        Label("Game Pace", systemImage: "hourglass")
                    }
                    Button {
                        showHallOfFame = true
                    } label: {
                        Label("Hall of Fame", systemImage: "crown")
                    }
                    Divider()
                    Button {
                        gameClient.leaveGame()
                    } label: {
                        Label("Leave this game", systemImage: "figure.walk.departure")
                    }
                    Button(role: .destructive) {
                        confirmBurn = true
                    } label: {
                        Label("Burn it down", systemImage: "flame")
                    }
                } label: {
                    Image(systemName: "line.3.horizontal")
                }
                .accessibilityLabel("Camp menu")
            }
            .font(.body)
            .padding(.horizontal, 16)
            .padding(.top, 6)

            // Turn indicator: the web's "Your torch burns" tracker on your
            // turn, the plain whose-turn strip otherwise
            if viewModel.isMyTurn, let phase = viewModel.turnPhase {
                TurnPhaseTracker(phase: phase)
                    .padding(.horizontal, 16)
                    .padding(.top, 4)
            } else {
                TurnIndicatorView(
                    currentPlayer: viewModel.currentPlayer,
                    isMyTurn: viewModel.isMyTurn,
                    turnPhase: viewModel.turnPhase,
                    deckCount: viewModel.deckCount
                )
            }

            // Player status bar
            PlayerStatusBar(
                players: viewModel.sortedPlayers,
                currentPlayerId: viewModel.gameState?.currentPlayerId,
                myPlayerId: viewModel.myPlayerId
            )
            .padding(.vertical, 8)

            Divider()

            // Main content area
            ScrollView {
                VStack(spacing: 16) {
                    // Action buttons (when it's your turn)
                    if viewModel.isMyTurn {
                        TurnActionsView(viewModel: viewModel)
                    } else {
                        WaitingView(playerName: viewModel.currentPlayerName)
                    }
                }
                .padding()
            }

            Divider()

            // Card hand
            CardHandView()
                .padding(.vertical, 8)
        }
        .sheet(isPresented: $showStory) {
            StorySoFarDrawer()
        }
        .sheet(isPresented: $showPace) {
            GameSettingsSheet()
        }
        .sheet(isPresented: $showSettings) {
            AppSettingsSheet()
        }
        .sheet(isPresented: $showHallOfFame) {
            HallOfFameView()
        }
        .confirmationDialog(
            "Burn this game down for everyone?",
            isPresented: $confirmBurn, titleVisibility: .visible
        ) {
            Button("Burn it down", role: .destructive) {
                Task {
                    _ = try? await gameClient.apiClient.deleteGame(gameId: gameClient.gameId ?? "")
                    gameClient.leaveGame()
                }
            }
        } message: {
            Text("Every player is sent back to the start screen and the game is gone for good.")
        }
        .sheet(isPresented: $viewModel.showStealPicker) {
            StealTargetPicker(targets: viewModel.stealTargets) { targetId in
                if confirmSteals {
                    pendingStealTarget = targetId
                } else {
                    Task { await viewModel.steal(targetId: targetId) }
                }
            }
        }
        .confirmationDialog(
            "Steal a random card?",
            isPresented: Binding(
                get: { pendingStealTarget != nil },
                set: { if !$0 { pendingStealTarget = nil } }),
            titleVisibility: .visible
        ) {
            Button("Steal", role: .destructive) {
                if let target = pendingStealTarget {
                    Task { await viewModel.steal(targetId: target) }
                }
                pendingStealTarget = nil
            }
        }
        .errorAlert($viewModel.error)
    }
}

private struct TurnActionsView: View {
    @Bindable var viewModel: PlayingViewModel

    var body: some View {
        VStack(spacing: 12) {
            if viewModel.canSteal {
                HStack(spacing: 12) {
                    Button {
                        viewModel.showStealPicker = true
                    } label: {
                        Label("Steal", systemImage: "hand.raised.fill")
                    }
                    .buttonStyle(.survivor(color: .red))
                    .disabled(viewModel.stealTargets.isEmpty || viewModel.isPerformingAction)
                    .accessibilityLabel("Steal card from player")
                    .accessibilityHint("Opens player selection to steal a random card from another player")
                }

                Text("You must steal a card first")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if viewModel.canPlay {
                Text("Play a card if you like, then draw to end your turn")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Official turn: the draw IS the end of the turn. No End Turn
            // button exists anywhere — the torch moves on by itself.
            Button {
                Task { await viewModel.drawCard() }
            } label: {
                Label("Draw Card & End Turn", systemImage: "arrow.down.doc.fill")
            }
            .buttonStyle(.survivor(color: .blue))
            .disabled(!viewModel.canDraw || viewModel.isPerformingAction)
            .accessibilityLabel("Draw card and end your turn")
            .accessibilityHint("Draws from the deck; drawing ends your turn automatically")

            if viewModel.isPerformingAction {
                ProgressView()
            }
        }
    }
}

private struct WaitingView: View {
    let playerName: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "hourglass")
                .font(.system(size: 32))
                .foregroundStyle(.secondary)
            Text("Waiting for \(playerName)...")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 32)
    }
}
