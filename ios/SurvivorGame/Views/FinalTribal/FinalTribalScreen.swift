import SwiftUI

struct FinalTribalScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: FinalTribalViewModel?

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                FinalTribalContent(viewModel: vm)
                    .navigationTitle("Final Tribal Council")
                    .navigationBarTitleDisplayMode(.inline)
            } else {
                ProgressView().onAppear {
                    viewModel = FinalTribalViewModel(gameClient: gameClient)
                    HapticEngine.tribalStart()
                }
            }
        }
    }
}

private struct FinalTribalContent: View {
    @Bindable var viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 0) {
            // Phase indicator
            PhaseProgressView(
                phases: ["Questions", "Deliberation", "Voting", "Reveal"],
                currentIndex: phaseIndex
            )
            .padding(.vertical, 12)

            Divider()

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
                        }
                    }
                }
                .padding()
            }

            // Council leader phase advance
            if viewModel.isCouncilLeader {
                Divider()
                FinalLeaderBar(viewModel: viewModel)
            }
        }
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
    let finalists: [PlayerState]

    var body: some View {
        VStack(spacing: 8) {
            Text("Finalists")
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)

            HStack(spacing: 24) {
                ForEach(finalists) { player in
                    VStack(spacing: 8) {
                        PlayerAvatarView(player: player, size: 56)
                        Text(player.name)
                            .font(.subheadline.bold())
                    }
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

private struct QuestionsPhase: View {
    let viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "questionmark.bubble.fill")
                .font(.system(size: 40))
                .foregroundStyle(.blue)

            Text("The jury may now question the finalists.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if viewModel.isJuryMember && !viewModel.isReady {
                Button("Ready to Vote") {
                    Task { await viewModel.signalReady() }
                }
                .buttonStyle(.survivor)
                .disabled(viewModel.isPerformingAction)
            }

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
                .foregroundStyle(.purple)

            Text("The jury is deliberating.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            if viewModel.isJuryMember && !viewModel.isReady {
                Button("Ready to Vote") {
                    Task { await viewModel.signalReady() }
                }
                .buttonStyle(.survivor)
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
                .font(.caption.bold())
                .foregroundStyle(.secondary)

            ForEach(juryMembers) { member in
                HStack(spacing: 8) {
                    Image(systemName: readySet.contains(member.id) ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(readySet.contains(member.id) ? .green : .secondary)
                        .font(.caption)
                    Text(member.name)
                        .font(.caption)
                }
            }
        }
        .padding()
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

private struct FinalTieBreakView: View {
    @Bindable var viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Text("Tie!")
                .font(.title.bold())
                .foregroundStyle(.yellow)

            Text("The council leader must choose the winner.")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            if viewModel.isCouncilLeader {
                ForEach(viewModel.tiedFinalists) { player in
                    Button {
                        Task { await viewModel.breakTie(chosenWinner: player.id) }
                    } label: {
                        HStack(spacing: 12) {
                            PlayerAvatarView(player: player, size: 48, showName: false)
                            Text(player.name)
                                .font(.headline)
                            Spacer()
                            Image(systemName: "crown.fill")
                                .foregroundStyle(.yellow)
                        }
                        .padding()
                        .background(.yellow.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isPerformingAction)
                }
            } else {
                Text("Waiting for the council leader...")
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct FinalLeaderBar: View {
    @Bindable var viewModel: FinalTribalViewModel

    var body: some View {
        HStack {
            switch viewModel.phase {
            case .waiting, .questions:
                Button("Advance to Deliberation") {
                    Task { await viewModel.advancePhase(to: "deliberation") }
                }
                .buttonStyle(.survivor)

            case .deliberation:
                Button("Start Voting") {
                    Task { await viewModel.advancePhase(to: "voting") }
                }
                .buttonStyle(.survivor)

            case .voting:
                EmptyView()

            case .reveal:
                if let winner = viewModel.winner {
                    Button("Record Winner") {
                        Task { await viewModel.finishGame(winnerId: winner.id) }
                    }
                    .buttonStyle(.survivor(color: .green))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.regularMaterial)
        .disabled(viewModel.isPerformingAction)
    }
}
