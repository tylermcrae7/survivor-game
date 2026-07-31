import SwiftUI

struct JuryVotingView: View {
    @Bindable var viewModel: FinalTribalViewModel
    @State private var slamName: String?

    var body: some View {
        VStack(spacing: 16) {
            CeremonyTitle(text: "Jury Voting", glow: Torch.Color.juryGold)

            if viewModel.isJuryMember {
                if viewModel.hasVoted {
                    VStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 32))
                            .foregroundStyle(Torch.Color.juryGold)
                            .shadow(color: Torch.Color.juryGold.opacity(0.4), radius: 12)
                        Text("Vote Cast")
                            .font(Torch.Font.display(Torch.TextSize.base, weight: 700))
                            .foregroundStyle(Torch.Color.parchment)
                        Text("Waiting for other jury members...")
                            .font(Torch.Font.body(Torch.TextSize.xs))
                            .foregroundStyle(Torch.Color.textSecondary)
                    }
                    .padding(.vertical, 24)
                } else {
                    Text("Vote for the player you want to WIN")
                        .font(Torch.Font.body(Torch.TextSize.sm))
                        .foregroundStyle(Torch.Color.textSecondary)

                    // The final ballots: parchment slips, crowned in gold.
                    ForEach(Array(viewModel.finalists.enumerated()), id: \.element.id) { index, player in
                        Button {
                            HapticEngine.voteSlam()
                            TorchSound.play(.voteReveal)
                            slamName = player.name
                            Task { await viewModel.castVote(for: player.id) }
                        } label: {
                            HStack(spacing: 12) {
                                PlayerAvatarView(player: player, size: 48, showName: false)

                                VStack(alignment: .leading) {
                                    Text(player.name)
                                        .font(Torch.Font.display(Torch.TextSize.lg, weight: 700))
                                        .foregroundStyle(Torch.Color.ink)
                                    Text("\(player.handCount) cards remaining")
                                        .font(Torch.Font.body(Torch.TextSize.xs))
                                        .foregroundStyle(Torch.Color.inkSoft)
                                }

                                Spacer()

                                Image(systemName: "crown.fill")
                                    .foregroundStyle(Torch.Color.juryGold)
                            }
                            .padding(16)
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
            } else if viewModel.isFinalist {
                VStack(spacing: 8) {
                    Image(systemName: "hourglass")
                        .font(.system(size: 32))
                        .foregroundStyle(Torch.Color.textFaint)
                    Text("The jury is voting...")
                        .font(Torch.Font.body(Torch.TextSize.sm))
                        .foregroundStyle(Torch.Color.textSecondary)
                    Text("Your fate is in their hands.")
                        .font(Torch.Font.display(Torch.TextSize.sm, weight: 500, italic: true))
                        .foregroundStyle(Torch.Color.parchmentDim)
                }
                .padding(.vertical, 24)
            } else {
                Text("Spectating jury vote...")
                    .foregroundStyle(Torch.Color.textSecondary)
            }
        }
        .overlay {
            if let name = slamName {
                VoteSlamOverlay(name: name) { slamName = nil }
            }
        }
    }
}
