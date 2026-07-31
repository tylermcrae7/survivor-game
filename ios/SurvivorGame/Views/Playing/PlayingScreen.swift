import SwiftUI

struct PlayingScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: PlayingViewModel?

    var body: some View {
        if let vm = viewModel {
            PlayingContent(viewModel: vm)
        } else {
            ProgressView()
                .tint(Torch.Color.torch)
                .onAppear {
                    viewModel = PlayingViewModel(gameClient: gameClient)
                }
        }
    }
}

/// Header pill chip (web §Top bar): small-caps label on a sunken capsule.
private struct CampChip<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        HStack(spacing: 6) { content }
            .font(Torch.Font.label(Torch.TextSize.xs))
            .tracking(Torch.Track.label * Torch.TextSize.xs)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Capsule().fill(Torch.Color.surfaceSunken))
            .overlay(Capsule().strokeBorder(Torch.Color.line, lineWidth: 1))
    }
}

/// "A note pinned by the fire" (web §Phase guidance): sunken row with a
/// 3px torch left edge.
private struct GuidanceNote: View {
    let text: String

    var body: some View {
        Text(text)
            .font(Torch.Font.body(Torch.TextSize.xs))
            .foregroundStyle(Torch.Color.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 8)
            .padding(.horizontal, 12)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(Torch.Color.surfaceSunken)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(Torch.Color.line, lineWidth: 1)
            )
            .overlay(alignment: .leading) {
                UnevenRoundedRectangle(topLeadingRadius: Torch.Radius.md,
                                       bottomLeadingRadius: Torch.Radius.md)
                    .fill(Torch.Color.torch)
                    .frame(width: 3)
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
    @State private var turnPulseTrigger = 0
    @AppStorage("confirmSteals") private var confirmSteals = false

    private var eliminatedIds: [String] {
        viewModel.sortedPlayers.filter(\.isEliminated).map(\.id)
    }

    private var hairline: some View {
        Rectangle().fill(Torch.Color.line).frame(height: 1)
    }

    var body: some View {
        VStack(spacing: 0) {
            // The camp strip: fire code chip, story drawer, camp menu
            StaggeredRise(index: 0) {
                HStack {
                    Image(systemName: "flame.fill")
                        .foregroundStyle(Torch.Color.torch)
                        .flameFlicker()
                        .accessibilityHidden(true)
                    if let code = gameClient.gameId {
                        CampChip {
                            Text("FIRE").foregroundStyle(Torch.Color.textSecondary)
                            Text(code)
                                .font(.caption.monospaced().bold())
                                .foregroundStyle(Torch.Color.torch)
                        }
                    }
                    Spacer()
                    Button {
                        showStory = true
                    } label: {
                        Image(systemName: "scroll")
                            .foregroundStyle(Torch.Color.textSecondary)
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
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                    .accessibilityLabel("Camp menu")
                }
                .font(.body)
                .padding(.horizontal, 16)
                .padding(.top, 6)
            }

            // Turn indicator: the web's "Your torch burns" tracker on your
            // turn, the plain whose-turn strip otherwise
            StaggeredRise(index: 1) {
                if viewModel.isMyTurn, let phase = viewModel.turnPhase {
                    TurnPhaseTracker(phase: phase)
                        .turnPulse(trigger: turnPulseTrigger, cornerRadius: 16)
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
            }

            // Player status bar
            StaggeredRise(index: 2) {
                PlayerStatusBar(
                    players: viewModel.sortedPlayers,
                    currentPlayerId: viewModel.gameState?.currentPlayerId,
                    myPlayerId: viewModel.myPlayerId
                )
                .padding(.vertical, 8)
            }

            hairline

            // Main content area — the lit action panel and the hand flow
            // together in ONE scroll region (the web's glanceable pattern).
            ScrollView {
                VStack(spacing: Torch.Spacing.md) {
                    StaggeredRise(index: 3) {
                        VStack(spacing: 16) {
                            // Action buttons (when it's your turn)
                            if viewModel.isMyTurn {
                                TurnActionsView(viewModel: viewModel)
                            } else {
                                WaitingView(playerName: viewModel.currentPlayerName)
                            }
                        }
                        .padding(Torch.Spacing.md)
                        .frame(maxWidth: .infinity)
                        .torchCard()
                    }

                    StaggeredRise(index: 4) {
                        CardHandView()
                    }
                }
                .padding(Torch.Spacing.md)
                .padding(.bottom, Torch.Spacing.lg)
            }
        }
        .background(TorchNightBackground(radialColor: Torch.Color.torch.opacity(0.14),
                                         showEmbers: false, startRadius: 0, endRadius: 460))
        .tint(Torch.Color.torch)
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
        // "It's your turn" — amber ring + soft double swell, on the same
        // turn-order change the indicator already reacts to.
        .onChange(of: viewModel.gameState?.currentPlayerId, initial: true) { _, _ in
            guard viewModel.isMyTurn else { return }
            turnPulseTrigger += 1
            HapticEngine.turnPulse()
        }
        // Tribal snuffs belong to EliminationView (it fires the pattern
        // there); this covers only eliminations that land while the camp is
        // on screen, so nothing double-fires.
        .onChange(of: eliminatedIds) { old, new in
            guard new.count > old.count else { return }
            HapticEngine.elimination()
            TorchSound.play(.torchSnuff)
        }
        .errorAlert($viewModel.error)
    }
}

private struct TurnActionsView: View {
    @Bindable var viewModel: PlayingViewModel

    var body: some View {
        VStack(spacing: 12) {
            if viewModel.canSteal {
                Button {
                    viewModel.showStealPicker = true
                } label: {
                    Label("Steal", systemImage: "hand.raised.fill")
                }
                .buttonStyle(.torchGlow)
                .disabled(viewModel.stealTargets.isEmpty || viewModel.isPerformingAction)
                .accessibilityLabel("Steal card from player")
                .accessibilityHint("Opens player selection to steal a random card from another player")

                GuidanceNote(text: "You must steal a card first")
            }

            if viewModel.canPlay {
                GuidanceNote(text: "Play a card if you like, then draw to end your turn")
            }

            // Official turn: the draw IS the end of the turn. No End Turn
            // button exists anywhere — the torch moves on by itself.
            Button {
                Task { await viewModel.drawCard() }
            } label: {
                Label("Draw Card & End Turn", systemImage: "arrow.down.doc.fill")
            }
            .buttonStyle(.torchSecondary)
            .disabled(!viewModel.canDraw || viewModel.isPerformingAction)
            .accessibilityLabel("Draw card and end your turn")
            .accessibilityHint("Draws from the deck; drawing ends your turn automatically")

            if viewModel.isPerformingAction {
                ProgressView()
                    .tint(Torch.Color.torch)
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
                .foregroundStyle(Torch.Color.textFaint)
            Text("Waiting for \(playerName)...")
                .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                .foregroundStyle(Torch.Color.parchment)
        }
        .padding(.vertical, 32)
    }
}
