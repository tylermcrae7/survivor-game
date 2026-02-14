import SwiftUI

struct TribalScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: TribalViewModel?

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                TribalContent(viewModel: vm)
                    .navigationTitle("Tribal Council")
                    .navigationBarTitleDisplayMode(.inline)
            } else {
                ProgressView().onAppear {
                    viewModel = TribalViewModel(gameClient: gameClient)
                    HapticEngine.tribalStart()
                }
            }
        }
    }
}

private struct TribalContent: View {
    @Bindable var viewModel: TribalViewModel

    private let phaseNames = ["Announce", "Advantage", "Discuss", "Immunity", "Vote", "Reveal"]

    var body: some View {
        VStack(spacing: 0) {
            // Phase progress
            PhaseProgressView(
                phases: phaseNames,
                currentIndex: phaseIndex
            )
            .padding(.vertical, 12)

            Divider()

            // Phase content
            ScrollView {
                VStack(spacing: 16) {
                    switch viewModel.tribalPhase {
                    case .waiting, .announcement:
                        AnnouncementPhase(viewModel: viewModel)
                    case .advantagePlay:
                        AdvantagePlayView(viewModel: viewModel)
                    case .discussion:
                        DiscussionPhase(viewModel: viewModel)
                    case .immunity:
                        ImmunityView(viewModel: viewModel)
                    case .voting:
                        VotingView(viewModel: viewModel)
                    case .reveal:
                        VoteRevealView(viewModel: viewModel)
                    }
                }
                .padding()
            }

            // Council leader actions
            if viewModel.isCouncilLeader {
                Divider()
                LeaderActionsBar(viewModel: viewModel)
            }
        }
        .errorAlert($viewModel.error)
    }

    private var phaseIndex: Int {
        switch viewModel.tribalPhase {
        case .waiting, .announcement: return 0
        case .advantagePlay: return 1
        case .discussion: return 2
        case .immunity: return 3
        case .voting: return 4
        case .reveal: return 5
        }
    }
}

private struct AnnouncementPhase: View {
    let viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "flame.fill")
                .font(.system(size: 48))
                .foregroundStyle(.orange)

            Text("Tribal Council")
                .font(.title.bold())

            Text("The tribe has spoken... someone will be going home tonight.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if let leader = viewModel.councilLeader {
                HStack(spacing: 8) {
                    Text("Council Leader:")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    PlayerAvatarView(player: leader, size: 32, showName: true)
                }
            }
        }
        .padding(.vertical, 24)
    }
}

private struct DiscussionPhase: View {
    let viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Text("Discussion Phase")
                .font(.headline)

            Text("Players may discuss and play tribal advantage cards.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            // Show hand for tribal advantage cards
            CardHandView()
        }
    }
}

private struct LeaderActionsBar: View {
    @Bindable var viewModel: TribalViewModel

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                switch viewModel.tribalPhase {
                case .waiting, .announcement:
                    Button("Advance to Advantages") {
                        Task { await viewModel.advancePhase(to: "advantage_play") }
                    }
                    .buttonStyle(.survivor)

                case .advantagePlay:
                    Button("Advance to Discussion") {
                        Task { await viewModel.advancePhase(to: "tribal_discussion") }
                    }
                    .buttonStyle(.survivor)

                case .discussion:
                    Button("Advance to Immunity") {
                        Task { await viewModel.advancePhase(to: "tribal_immunity") }
                    }
                    .buttonStyle(.survivor)

                case .immunity:
                    Button("Start Voting") {
                        Task { await viewModel.startVoting() }
                    }
                    .buttonStyle(.survivor)

                case .voting:
                    Button("Reveal Votes") {
                        Task { await viewModel.revealVotes() }
                    }
                    .buttonStyle(.survivor(color: .red))

                case .reveal:
                    if viewModel.voteState?.tieBreakNeeded == true {
                        // Tie break handled in VoteRevealView
                    } else {
                        Button("Complete Tribal") {
                            Task { await viewModel.completeTribal() }
                        }
                        .buttonStyle(.survivor(color: .red))
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
        }
        .background(.regularMaterial)
        .disabled(viewModel.isPerformingAction)
    }
}
