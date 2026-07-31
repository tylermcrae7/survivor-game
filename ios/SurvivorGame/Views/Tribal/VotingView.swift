import SwiftUI

/// The vote: tap a name to write it on your parchment. Holding Extra Votes
/// asks how many ride along — or split them across several players. A hand
/// with no Vote Card passes the box. All rules enforced server-side; this UI
/// mirrors the web app's chooser + split builder.
struct VotingView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var chooserTarget: PlayerState?
    @State private var showSplitBuilder = false
    @State private var confirmTarget: PlayerState?
    @AppStorage("confirmVotes") private var confirmVotes = false

    private var me: PlayerState? { viewModel.gameState?.players[viewModel.myPlayerId ?? ""] }
    private var mandatoryVotes: Int { me?.mandatoryVotes ?? 1 }
    private var maxVotes: Int { me?.maxVotes ?? 1 }
    private var extraVotes: Int { max(0, maxVotes - mandatoryVotes) }

    private var eligibleTargets: [PlayerState] {
        viewModel.voteTargets.filter { player in
            player.id != viewModel.gameState?.necklaceHolder
                && !player.immunityIdolProtection
        }
    }

    private var votedCount: Int {
        viewModel.activePlayers.filter(\.hasVoted).count
    }

    var body: some View {
        VStack(spacing: 16) {
            Text("It Is Time to Vote")
                .font(.title2.bold())
                .fontDesign(.serif)

            Text("\(votedCount) of \(viewModel.activePlayers.count) players have voted")
                .font(.caption)
                .foregroundStyle(.secondary)

            if viewModel.isEliminated {
                Text("Your torch is out — the vote passes you by.")
                    .foregroundStyle(.secondary)
            } else if viewModel.hasVoted {
                votedConfirmation
            } else if maxVotes == 0 {
                passTheBox
            } else {
                ballot
            }

            votingStatus
        }
        .sheet(item: $chooserTarget) { target in
            ExtraVoteChooser(
                target: target,
                mandatory: mandatoryVotes,
                maxTotal: maxVotes,
                onCast: { total in
                    chooserTarget = nil
                    HapticEngine.vote()
                    Task { await viewModel.castVote(targetId: target.id, count: total) }
                },
                onSplit: (extraVotes >= 1 && eligibleTargets.count >= 2) ? {
                    chooserTarget = nil
                    showSplitBuilder = true
                } : nil
            )
            .presentationDetents([.medium])
        }
        .confirmationDialog(
            "Write \(confirmTarget?.name ?? "their name") on your parchment?",
            isPresented: Binding(
                get: { confirmTarget != nil },
                set: { if !$0 { confirmTarget = nil } }),
            titleVisibility: .visible
        ) {
            Button("Cast the vote", role: .destructive) {
                if let target = confirmTarget {
                    HapticEngine.vote()
                    Task { await viewModel.castVote(targetId: target.id, count: mandatoryVotes) }
                }
                confirmTarget = nil
            }
        } message: {
            Text("A vote can't be taken back.")
        }
        .sheet(isPresented: $showSplitBuilder) {
            SplitBallotBuilder(
                targets: eligibleTargets,
                mandatory: mandatoryVotes,
                maxTotal: maxVotes
            ) { allocations in
                showSplitBuilder = false
                HapticEngine.vote()
                Task { await viewModel.castSplitBallot(allocations) }
            }
            .presentationDetents([.medium, .large])
        }
    }

    // MARK: - Pieces

    private var votedConfirmation: some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: 32))
                .foregroundStyle(.orange)
            Text("The parchment is in the box")
                .font(.subheadline.bold())
            Text("Waiting for the rest of the tribe…")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 24)
    }

    private var passTheBox: some View {
        VStack(spacing: 12) {
            Text("You have no Vote Card — the box passes you by.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Pass the Voting Box") {
                Task { await viewModel.passVotingBox() }
            }
            .buttonStyle(.survivor(color: .gray))
            .disabled(viewModel.isPerformingAction)
        }
        .padding(.vertical, 12)
    }

    private var ballot: some View {
        VStack(spacing: 10) {
            if extraVotes > 0 {
                Text("You hold \(extraVotes) Extra Vote\(extraVotes == 1 ? "" : "s")")
                    .font(.caption.bold())
                    .foregroundStyle(.orange)
            }
            Text("Tap a name to write it on your parchment")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            ForEach(eligibleTargets) { player in
                Button {
                    if extraVotes > 0 {
                        chooserTarget = player
                    } else if confirmVotes {
                        confirmTarget = player
                    } else {
                        HapticEngine.vote()
                        Task { await viewModel.castVote(targetId: player.id, count: mandatoryVotes) }
                    }
                } label: {
                    HStack(spacing: 12) {
                        PlayerAvatarView(player: player, size: 40, showName: false)
                        Text(player.name)
                            .font(.body.bold())
                        Spacer()
                        Image(systemName: "pencil.line")
                            .foregroundStyle(.secondary)
                    }
                    .padding(12)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isPerformingAction)
            }
        }
    }

    private var votingStatus: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("The Tribe")
                .font(.caption.bold())
                .foregroundStyle(.secondary)

            ForEach(viewModel.activePlayers) { player in
                HStack(spacing: 8) {
                    Image(systemName: player.hasVoted ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(player.hasVoted ? .orange : .secondary)
                        .font(.caption)
                    Text(player.name)
                        .font(.caption)
                        .foregroundStyle(player.hasVoted ? .primary : .secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - Extra vote chooser

private struct ExtraVoteChooser: View {
    let target: PlayerState
    let mandatory: Int
    let maxTotal: Int
    let onCast: (Int) -> Void
    let onSplit: (() -> Void)?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    Text("You hold \(maxTotal - mandatory) Extra Vote\(maxTotal - mandatory == 1 ? "" : "s"). Spend them now, or keep them hidden for a later Tribal Council.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    ForEach(Array(max(1, mandatory)...max(max(1, mandatory), maxTotal)), id: \.self) { total in
                        Button {
                            onCast(total)
                        } label: {
                            VStack(spacing: 2) {
                                Text("\(total) vote\(total == 1 ? "" : "s") against \(target.name)")
                                    .font(.body.bold())
                                Text(total - mandatory == 0
                                     ? "Save your Extra Votes for later"
                                     : "Adds \(total - mandatory) Extra Vote\(total - mandatory == 1 ? "" : "s")")
                                    .font(.caption)
                                    .opacity(0.8)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                        }
                        .buttonStyle(.survivor)
                    }

                    if let onSplit {
                        Button {
                            onSplit()
                        } label: {
                            VStack(spacing: 2) {
                                Text("Split votes across players…")
                                Text("Write different names on different parchments")
                                    .font(.caption)
                                    .opacity(0.8)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                        }
                        .buttonStyle(.survivor(color: .gray))
                    }
                }
                .padding(20)
            }
            .navigationTitle("How many votes?")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

// MARK: - Split ballot builder

private struct SplitBallotBuilder: View {
    let targets: [PlayerState]
    let mandatory: Int
    let maxTotal: Int
    let onCast: ([String: Int]) -> Void

    @State private var allocations: [String: Int] = [:]

    private var total: Int { allocations.values.reduce(0, +) }
    private var castable: Bool { total >= mandatory && total <= maxTotal }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    Text(total < mandatory
                         ? "Cast at least \(mandatory) — your Vote Card must be used (\(total) placed)"
                         : "\(total) of up to \(maxTotal) votes placed")
                        .font(.caption)
                        .foregroundStyle(total < mandatory ? .orange : .secondary)

                    ForEach(targets) { player in
                        HStack {
                            Text(player.name).font(.body.bold())
                            Spacer()
                            Button {
                                if allocations[player.id, default: 0] > 0 {
                                    allocations[player.id, default: 0] -= 1
                                }
                            } label: { Image(systemName: "minus.circle") }
                            Text("\(allocations[player.id, default: 0])")
                                .font(.title3.monospacedDigit())
                                .frame(minWidth: 28)
                            Button {
                                if total < maxTotal {
                                    allocations[player.id, default: 0] += 1
                                }
                            } label: { Image(systemName: "plus.circle") }
                        }
                        .padding(10)
                        .background(.regularMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    }

                    Button("Cast this ballot") {
                        onCast(allocations)
                    }
                    .buttonStyle(.survivor)
                    .disabled(!castable)
                }
                .padding(20)
            }
            .navigationTitle("Write your parchments")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
