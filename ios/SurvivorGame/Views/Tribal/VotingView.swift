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
    @State private var slamName: String?
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

    /// The ballot-submitted flourish: slam card + strike haptic + drum,
    /// per the VoteSlamOverlay contract. Replaces the plain vote() tap so
    /// nothing double-fires.
    private func slamBallot(name: String?) {
        HapticEngine.voteSlam()
        TorchSound.play(.voteReveal)
        if let name { slamName = name }
    }

    var body: some View {
        VStack(spacing: 16) {
            CeremonyTitle(text: "It Is Time to Vote")

            Text("\(votedCount) of \(viewModel.activePlayers.count) players have voted")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            if viewModel.isEliminated {
                Text("Your torch is out — the vote passes you by.")
                    .font(Torch.Font.display(Torch.TextSize.base, weight: 500, italic: true))
                    .foregroundStyle(Torch.Color.textSecondary)
            } else if viewModel.hasVoted {
                votedConfirmation
            } else if maxVotes == 0 {
                passTheBox
            } else {
                ballot
            }

            votingStatus
        }
        .overlay {
            if let name = slamName {
                VoteSlamOverlay(name: name) { slamName = nil }
                    .accessibilityHidden(true) // transient decoration
            }
        }
        .sheet(item: $chooserTarget) { target in
            ExtraVoteChooser(
                target: target,
                mandatory: mandatoryVotes,
                maxTotal: maxVotes,
                onCast: { total in
                    chooserTarget = nil
                    slamBallot(name: target.name)
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
                    slamBallot(name: target.name)
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
                // No flourish for an empty ballot — only slam when a real
                // name got written. Submission is unchanged either way.
                let top = allocations.filter { $0.value > 0 }.max { $0.value < $1.value }?.key
                if let name = top.flatMap({ id in eligibleTargets.first { $0.id == id }?.name }) {
                    slamBallot(name: name)
                }
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
                .foregroundStyle(Torch.Color.torch)
                .torchGlow()
            Text("The parchment is in the box")
                .font(Torch.Font.display(Torch.TextSize.base, weight: 700))
                .foregroundStyle(Torch.Color.parchment)
            Text("Waiting for the rest of the tribe…")
                .font(Torch.Font.body(Torch.TextSize.xs))
                .foregroundStyle(Torch.Color.textSecondary)
        }
        .padding(.vertical, 24)
    }

    private var passTheBox: some View {
        VStack(spacing: 12) {
            Text("You have no Vote Card — the box passes you by.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
                .multilineTextAlignment(.center)
            Button("Pass the Voting Box") {
                Task { await viewModel.passVotingBox() }
            }
            .buttonStyle(.torchSecondary)
            .disabled(viewModel.isPerformingAction)
        }
        .padding(.vertical, 12)
    }

    private var ballot: some View {
        VStack(spacing: 10) {
            if extraVotes > 0 {
                Text("You hold \(extraVotes) Extra Vote\(extraVotes == 1 ? "" : "s")")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.flame)
            }
            Text("Tap a name to write it on your parchment")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)

            // Parchment slips against the night, rotated like scattered paper.
            ForEach(Array(eligibleTargets.enumerated()), id: \.element.id) { index, player in
                Button {
                    if extraVotes > 0 {
                        chooserTarget = player
                    } else if confirmVotes {
                        confirmTarget = player
                    } else {
                        slamBallot(name: player.name)
                        Task { await viewModel.castVote(targetId: player.id, count: mandatoryVotes) }
                    }
                } label: {
                    HStack(spacing: 12) {
                        PlayerAvatarView(player: player, size: 40, showName: false)
                        Text(player.name)
                            .font(Torch.Font.display(Torch.TextSize.lg, weight: 700))
                            .foregroundStyle(Torch.Color.ink)
                        Spacer()
                        Image(systemName: "pencil.line")
                            .foregroundStyle(Torch.Color.inkSoft)
                    }
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: Torch.Radius.sm, style: .continuous)
                            .fill(LinearGradient(colors: [Torch.Color.parchment,
                                                          Torch.Color.parchmentDim],
                                                 startPoint: .top, endPoint: .bottom))
                    )
                    .shadow(color: .black.opacity(0.40), radius: 9, y: 6) // --shadow-md
                    .rotationEffect(.degrees(index.isMultiple(of: 2) ? -0.8 : 0.9))
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isPerformingAction)
            }
        }
    }

    private var votingStatus: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("The Tribe")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textSecondary)

            ForEach(viewModel.activePlayers) { player in
                HStack(spacing: 8) {
                    Image(systemName: player.hasVoted ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(player.hasVoted ? Torch.Color.torch : Torch.Color.textFaint)
                        .font(.caption)
                    Text(player.name)
                        .font(Torch.Font.body(Torch.TextSize.xs))
                        .foregroundStyle(player.hasVoted ? Torch.Color.text : Torch.Color.textSecondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                .fill(CouncilPalette.surfaceSunken)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                .strokeBorder(CouncilPalette.line, lineWidth: 1)
        )
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
                        .font(Torch.Font.body(Torch.TextSize.sm))
                        .foregroundStyle(Torch.Color.textSecondary)
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
                        .buttonStyle(.torchGlow)
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
                        .buttonStyle(.torchSecondary)
                    }
                }
                .padding(20)
            }
            .background(CouncilBackground())
            .tint(Torch.Color.torch)
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
                        .font(Torch.Font.body(Torch.TextSize.xs))
                        .foregroundStyle(total < mandatory ? Torch.Color.flame : Torch.Color.textSecondary)

                    ForEach(targets) { player in
                        HStack {
                            Text(player.name)
                                .font(Torch.Font.body(Torch.TextSize.base, weight: .bold))
                                .foregroundStyle(Torch.Color.parchment)
                            Spacer()
                            Button {
                                if allocations[player.id, default: 0] > 0 {
                                    allocations[player.id, default: 0] -= 1
                                }
                            } label: { Image(systemName: "minus.circle") }
                            Text("\(allocations[player.id, default: 0])")
                                .font(.title3.monospacedDigit())
                                .foregroundStyle(Torch.Color.text)
                                .frame(minWidth: 28)
                            Button {
                                if total < maxTotal {
                                    allocations[player.id, default: 0] += 1
                                }
                            } label: { Image(systemName: "plus.circle") }
                        }
                        .padding(10)
                        .background(
                            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                                .fill(CouncilPalette.surfaceSunken)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                                .strokeBorder(CouncilPalette.line, lineWidth: 1)
                        )
                    }

                    Button("Cast this ballot") {
                        onCast(allocations)
                    }
                    .buttonStyle(.torchGlow)
                    .disabled(!castable)
                }
                .padding(20)
            }
            .background(CouncilBackground())
            .tint(Torch.Color.torch)
            .navigationTitle("Write your parchments")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
