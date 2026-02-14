import SwiftUI

struct JuryVotingView: View {
    @Bindable var viewModel: FinalTribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Text("Jury Voting")
                .font(.headline)

            if viewModel.isJuryMember {
                if viewModel.hasVoted {
                    VStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 32))
                            .foregroundStyle(.green)
                        Text("Vote Cast")
                            .font(.subheadline.bold())
                        Text("Waiting for other jury members...")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 24)
                } else {
                    Text("Vote for the player you want to WIN")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    ForEach(viewModel.finalists) { player in
                        Button {
                            HapticEngine.vote()
                            Task { await viewModel.castVote(for: player.id) }
                        } label: {
                            HStack(spacing: 12) {
                                PlayerAvatarView(player: player, size: 48, showName: false)

                                VStack(alignment: .leading) {
                                    Text(player.name)
                                        .font(.body.bold())
                                    Text("\(player.handCount) cards remaining")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }

                                Spacer()

                                Image(systemName: "crown.fill")
                                    .foregroundStyle(.yellow)
                            }
                            .padding(16)
                            .background(.yellow.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isPerformingAction)
                    }
                }
            } else if viewModel.isFinalist {
                VStack(spacing: 8) {
                    Image(systemName: "hourglass")
                        .font(.system(size: 32))
                        .foregroundStyle(.secondary)
                    Text("The jury is voting...")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Text("Your fate is in their hands.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 24)
            } else {
                Text("Spectating jury vote...")
                    .foregroundStyle(.secondary)
            }
        }
    }
}
