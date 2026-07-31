import SwiftUI

struct VoteRevealView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var revealedCount = 0
    @State private var showAllVotes = false

    private var maxVotes: Int {
        viewModel.voteResults.map { $0.votes }.max() ?? 1
    }

    var body: some View {
        VStack(spacing: 20) {
            CeremonyTitle(text: "Vote Results")

            // Ballots flip in one at a time — the reveal is a ceremony.
            // The full stagger runs when everything shows at once; manual
            // reveals flip each fresh ballot immediately.
            ForEach(Array(viewModel.voteResults.enumerated()), id: \.offset) { index, result in
                if showAllVotes || index < revealedCount {
                    VoteResultRow(
                        player: result.player,
                        votes: result.votes,
                        maxVotes: maxVotes,
                        isEliminated: viewModel.voteState?.eliminated?.contains(result.player.id) ?? false,
                        isTied: viewModel.voteState?.tiedPlayers?.contains(result.player.id) ?? false,
                        barDelay: (showAllVotes ? Double(index) * 0.32 : 0) + 0.56
                    )
                    .ballotFlip(index: showAllVotes ? index : 0)
                    .transition(.identity) // the flip is the entrance
                }
            }

            if !showAllVotes && revealedCount < viewModel.voteResults.count {
                Button("Reveal Next Vote") {
                    withAnimation(.spring(response: 0.4)) {
                        revealedCount += 1
                        HapticEngine.vote()
                    }
                }
                .buttonStyle(.torchSecondary)
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

/// One parchment result card (web `.vote-result-card`): sunken council
/// surface, vote count in hot Fraunces, and the 7pt fire bar that grows
/// 900ms after the ballot lands.
private struct VoteResultRow: View {
    let player: PlayerState
    let votes: Int
    let maxVotes: Int
    let isEliminated: Bool
    let isTied: Bool
    let barDelay: Double
    @State private var grown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
    }

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 12) {
                PlayerAvatarView(player: player, size: 40, showName: false)

                Text(player.name)
                    .font(Torch.Font.display(Torch.TextSize.lg, weight: 700))
                    .foregroundStyle(isEliminated ? CouncilPalette.eliminatedRed : Torch.Color.parchment)

                Spacer()

                // Vote count
                HStack(spacing: 4) {
                    ForEach(0..<votes, id: \.self) { _ in
                        Image(systemName: "flame.fill")
                            .font(.caption)
                            .foregroundStyle(Torch.Color.torch)
                    }
                    Text("\(votes)")
                        .font(Torch.Font.display(27, weight: 900))
                        .foregroundStyle(isEliminated ? CouncilPalette.eliminatedRed : Torch.Color.flame)
                }

                if isTied {
                    Image(systemName: "equal.circle.fill")
                        .foregroundStyle(Torch.Color.warning)
                }
            }

            resultBar
        }
        .padding(12)
        .background {
            shape.fill(CouncilPalette.surfaceSunken)
            if isEliminated {
                shape.fill(LinearGradient(stops: [
                    .init(color: Torch.Color.danger.opacity(0.10), location: 0),
                    .init(color: .clear, location: 0.6),
                ], startPoint: .top, endPoint: .bottom))
            }
        }
        .overlay(
            shape.strokeBorder(isEliminated ? Torch.Color.danger.opacity(0.5) : CouncilPalette.line,
                               lineWidth: 1)
        )
        .onAppear {
            if reduceMotion {
                grown = true
            } else {
                withAnimation(.torchEaseOut(duration: 0.9).delay(barDelay)) { grown = true }
            }
        }
    }

    private var resultBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(.black.opacity(0.35))
                Capsule()
                    .fill(LinearGradient(colors: isEliminated
                            ? [CouncilPalette.barRedDark, CouncilPalette.barRedHot]
                            : [Torch.Color.ember, Torch.Color.torch],
                        startPoint: .leading, endPoint: .trailing))
                    .shadow(color: Torch.Color.torch.opacity(0.6), radius: 5)
                    .frame(width: grown ? geo.size.width * fraction : 0, alignment: .leading)
            }
        }
        .frame(height: 7)
    }

    private var fraction: CGFloat {
        maxVotes > 0 ? CGFloat(votes) / CGFloat(maxVotes) : 0
    }
}
