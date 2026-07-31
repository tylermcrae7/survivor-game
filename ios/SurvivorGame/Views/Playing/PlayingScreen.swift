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

    var body: some View {
        VStack(spacing: 0) {
            // Utility strip: the story drawer + the Leader's pace dial
            HStack {
                Spacer()
                Button {
                    showStory = true
                } label: {
                    Image(systemName: "scroll")
                }
                .accessibilityLabel("The story so far")
                Button {
                    showPace = true
                } label: {
                    Image(systemName: "hourglass")
                }
                .accessibilityLabel("Game pace")
            }
            .font(.body)
            .padding(.horizontal, 16)
            .padding(.top, 6)

            // Turn indicator
            TurnIndicatorView(
                currentPlayer: viewModel.currentPlayer,
                isMyTurn: viewModel.isMyTurn,
                turnPhase: viewModel.turnPhase,
                deckCount: viewModel.deckCount
            )

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
        .sheet(isPresented: $viewModel.showStealPicker) {
            StealTargetPicker(targets: viewModel.stealTargets) { targetId in
                Task { await viewModel.steal(targetId: targetId) }
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
