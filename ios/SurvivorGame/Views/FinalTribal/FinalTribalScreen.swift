import SwiftUI

/// Final-mode re-palette (web `body[data-mode="final"]` — jury gold).
/// Exact hex from docs/design/torchlit-ios-research.md; in this mode the
/// torch accent itself becomes jury gold.
enum FinalPalette {
    static let bg = Color(hex: "#070501") ?? .black
    static let bgDeep = Color(hex: "#030200") ?? .black
    static let surface = Color(hex: "#0F0B02") ?? .black
    static let surfaceRaised = Color(hex: "#181203") ?? .black
    /// `--flame-hot` in final mode (`oklch(0.86 0.13 95)`).
    static let flameHot = Color(hex: "#ECD065") ?? .yellow
    /// Torchlight radial core (`oklch(0.50 0.10 92 / 0.42)`), applied at 42%.
    static let torchlightCore = Color(hex: "#786107") ?? .yellow
    /// Gold-tinted hairline (`oklch(0.85 0.1 90 / 0.13)`).
    static let line = (Color(hex: "#E7CB80") ?? .yellow).opacity(0.13)
}

/// The final-council ground: gold-cast night with the torchlight pooling
/// gold instead of amber.
struct FinalBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [FinalPalette.bg, FinalPalette.bgDeep],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [FinalPalette.torchlightCore.opacity(0.42), .clear],
                           center: UnitPoint(x: 0.5, y: -0.12),
                           startRadius: 0, endRadius: 460)
        }
        .ignoresSafeArea()
    }
}

struct FinalTribalScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: FinalTribalViewModel?

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                FinalTribalContent(viewModel: vm)
                    .navigationTitle("Final Tribal Council")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbarBackground(FinalPalette.bg, for: .navigationBar)
            } else {
                ProgressView()
                    .tint(Torch.Color.juryGold)
                    .onAppear {
                        viewModel = FinalTribalViewModel(gameClient: gameClient)
                        // Mounts once per ceremony (ContentView swaps it in on
                        // navigationState == .finalTribal).
                        HapticEngine.tribalStart()
                        TorchSound.play(.tribalGong)
                    }
            }
        }
    }
}

private struct FinalTribalContent: View {
    @Bindable var viewModel: FinalTribalViewModel

    private var hairline: some View {
        Rectangle().fill(FinalPalette.line).frame(height: 1)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Phase indicator
            // Server tokens (survivor_server.advance_final_phase):
            // questions → deliberation → voting → reveal.
            PhaseProgressView(
                phases: ["Questions", "Deliberation", "Voting", "Reveal"],
                currentIndex: phaseIndex
            )
            // Keep the labels on one line instead of hyphenating mid-word;
            // both modifiers inherit into the tracker's Text views.
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .padding(.vertical, 12)

            hairline

            ScrollView {
                VStack(spacing: 20) {
                    // Finalists
                    FinalistsRow(finalists: viewModel.finalists)

                    switch viewModel.phase {
                    case .waiting, .questions:
                        QuestionsPhase(viewModel: viewModel)
                    case .deliberation:
                        DeliberationPhase(viewModel: viewModel)
                    case .voting:
                        JuryVotingView(viewModel: viewModel)
                    case .reveal:
                        if viewModel.tieBreakNeeded {
                            FinalTieBreakView(viewModel: viewModel)
                        } else if let winner = viewModel.winner {
                            WinnerRevealContent(winner: winner)
                        } else {
                            ProgressView("Revealing...")
                                .tint(Torch.Color.juryGold)
                        }
                    }
                }
                .padding()
            }

            // Council leader phase advance
            if viewModel.isCouncilLeader {
                hairline
                FinalLeaderBar(viewModel: viewModel)
            }
        }
        .background(FinalBackground())
        .tint(Torch.Color.juryGold)
        .errorAlert($viewModel.error)
    }

    private var phaseIndex: Int {
        switch viewModel.phase {
        case .waiting, .questions: return 0
        case .deliberation: return 1
        case .voting: return 2
        case .reveal: return 3
        }
    }
}

private struct FinalistsRow: View {
    @Environment(PlayerInspector.self) private var inspector
    let finalists: [PlayerState]

    var body: some View {
        VStack(spacing: 8) {
            Text("Finalists")
                .font(Torch.Font.label(Torch.TextSize.sm))
                .tracking(Torch.Track.label * Torch.TextSize.sm)
                .foregroundStyle(Torch.Color.juryGold)

            HStack(spacing: 24) {
                ForEach(finalists) { player in
                    VStack(spacing: 8) {
                        // The avatar's own caption is suppressed — the serif
                        // title below is this finalist's single name.
                        PlayerAvatarView(player: player, size: 56, showName: false,
                                         onTap: { inspector.playerId = player.id })
                        Text(player.name)
                            .font(Torch.Font.display(Torch.TextSize.base, weight: 700))
                            .foregroundStyle(Torch.Color.parchment)
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                .fill(FinalPalette.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                .strokeBorder(Torch.Color.juryGold.opacity(0.4), lineWidth: 1)
        )
    }
}

private struct QuestionsPhase: View {
    let viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "questionmark.bubble.fill")
                .font(.system(size: 40))
                .foregroundStyle(Torch.Color.juryGold)
                .shadow(color: Torch.Color.juryGold.opacity(0.4), radius: 12)

            Text("The jury may now question the finalists.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
                .multilineTextAlignment(.center)

            // No "Ready to Vote" here — the server refuses a signal raised
            // before deliberation opens ("The finalists are still making
            // their cases — deliberation opens the vote"), so the finger only
            // ever appears once it can actually be raised (DeliberationPhase,
            // below). Live log: `signal_jury_ready` returned a bare `False`
            // ×2 from a jury member tapping this during questions.

            // Show ready status
            JuryReadyList(
                juryMembers: viewModel.juryMembers,
                readySet: viewModel.juryReady
            )
        }
    }
}

private struct DeliberationPhase: View {
    let viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "bubble.left.and.bubble.right.fill")
                .font(.system(size: 40))
                .foregroundStyle(Torch.Color.juryGold)
                .shadow(color: Torch.Color.juryGold.opacity(0.4), radius: 12)

            Text("The jury is deliberating.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)

            if viewModel.isJuryMember && !viewModel.isReady {
                Button("Ready to Vote") {
                    Task { await viewModel.signalReady() }
                }
                .buttonStyle(.torchGlow)
                .disabled(viewModel.isPerformingAction)
            }

            JuryReadyList(
                juryMembers: viewModel.juryMembers,
                readySet: viewModel.juryReady
            )
        }
    }
}

private struct JuryReadyList: View {
    let juryMembers: [PlayerState]
    let readySet: Set<String>

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Jury Status")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            ForEach(juryMembers) { member in
                HStack(spacing: 8) {
                    Image(systemName: readySet.contains(member.id) ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(readySet.contains(member.id)
                                         ? Torch.Color.juryGold : Torch.Color.textFaint)
                        .font(.caption)
                    Text(member.name)
                        .font(Torch.Font.body(Torch.TextSize.xs))
                        .foregroundStyle(Torch.Color.text)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                .fill(FinalPalette.surfaceRaised)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                .strokeBorder(FinalPalette.line, lineWidth: 1)
        )
    }
}

private struct FinalTieBreakView: View {
    @Bindable var viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            CeremonyTitle(text: "Tie!", glow: Torch.Color.juryGold)

            Text("The council leader must choose the winner.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)

            if viewModel.isCouncilLeader {
                ForEach(viewModel.tiedFinalists) { player in
                    Button {
                        Task { await viewModel.breakTie(chosenWinner: player.id) }
                    } label: {
                        HStack(spacing: 12) {
                            PlayerAvatarView(player: player, size: 48, showName: false)
                            Text(player.name)
                                .font(Torch.Font.display(Torch.TextSize.base, weight: 700))
                                .foregroundStyle(Torch.Color.parchment)
                            Spacer()
                            Image(systemName: "crown.fill")
                                .foregroundStyle(Torch.Color.juryGold)
                        }
                        .padding()
                        .background(
                            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                                .fill(Torch.Color.juryGold.opacity(0.1))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                                .strokeBorder(Torch.Color.juryGold.opacity(0.4), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isPerformingAction)
                }
            } else {
                Text("Waiting for the council leader...")
                    .foregroundStyle(Torch.Color.textSecondary)
            }
        }
    }
}

private struct FinalLeaderBar: View {
    @Bindable var viewModel: FinalTribalViewModel

    /// Any computer player in the game — bot games are barred from the Hall of
    /// Fame server-side, so "Record Winner" has nothing to do.
    private var gameHasBots: Bool {
        viewModel.gameState?.players.values.contains { $0.isBot } ?? false
    }

    var body: some View {
        HStack {
            switch viewModel.phase {
            case .waiting, .questions:
                Button("Advance to Deliberation") {
                    Task { await viewModel.advancePhase(to: "deliberation") }
                }
                .buttonStyle(.torchGlow)

            case .deliberation:
                Button("Start Voting") {
                    Task { await viewModel.advancePhase(to: "voting") }
                }
                .buttonStyle(.torchGlow)

            case .voting:
                EmptyView()

            case .reveal:
                // The server refuses to record a game containing computer
                // players ("Games with computer players aren't recorded in the
                // Hall of Fame" — survivor_server.record_winner), so the button
                // would only ever error. Hide it rather than dangle it.
                if let winner = viewModel.winner, !gameHasBots {
                    Button("Record Winner") {
                        Task { await viewModel.finishGame(winnerId: winner.id) }
                    }
                    .buttonStyle(.torchGlow)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(FinalPalette.surfaceRaised)
        .disabled(viewModel.isPerformingAction)
    }
}
