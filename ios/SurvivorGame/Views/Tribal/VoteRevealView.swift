import SwiftUI

struct VoteRevealView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var revealedCount = 0
    @State private var showAllVotes = false

    var body: some View {
        VStack(spacing: 20) {
            Text("Vote Results")
                .font(.headline)

            // Vote results
            ForEach(Array(viewModel.voteResults.enumerated()), id: \.offset) { index, result in
                if showAllVotes || index < revealedCount {
                    VoteResultRow(
                        player: result.player,
                        votes: result.votes,
                        isEliminated: viewModel.voteState?.eliminated?.contains(result.player.id) ?? false,
                        isTied: viewModel.voteState?.tiedPlayers?.contains(result.player.id) ?? false
                    )
                    .transition(.asymmetric(
                        insertion: .move(edge: .trailing).combined(with: .opacity),
                        removal: .opacity
                    ))
                }
            }

            if !showAllVotes && revealedCount < viewModel.voteResults.count {
                Button("Reveal Next Vote") {
                    withAnimation(.spring(response: 0.4)) {
                        revealedCount += 1
                        HapticEngine.vote()
                    }
                }
                .buttonStyle(.survivorSecondary)
            } else {
                // All votes revealed
                if viewModel.voteState?.tieBreakNeeded == true {
                    TieBreakView(viewModel: viewModel)
                } else {
                    EliminationView(viewModel: viewModel)
                }
            }
        }
        .onAppear {
            // Auto-show all if already revealed
            if viewModel.voteState?.phase == .reveal {
                showAllVotes = true
            }
        }
    }
}

private struct VoteResultRow: View {
    let player: PlayerState
    let votes: Int
    let isEliminated: Bool
    let isTied: Bool

    var body: some View {
        HStack(spacing: 12) {
            PlayerAvatarView(player: player, size: 40, showName: false)

            Text(player.name)
                .font(.body.bold())
                .foregroundStyle(isEliminated ? .red : .primary)

            Spacer()

            // Vote count
            HStack(spacing: 4) {
                ForEach(0..<votes, id: \.self) { _ in
                    Image(systemName: "flame.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
                Text("\(votes)")
                    .font(.subheadline.bold())
                    .foregroundStyle(isEliminated ? .red : .primary)
            }

            if isTied {
                Image(systemName: "equal.circle.fill")
                    .foregroundStyle(.yellow)
            }
        }
        .padding(12)
        .background(isEliminated ? Color.red.opacity(0.1) : Color(.systemGray6))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
