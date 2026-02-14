import SwiftUI

struct VotingView: View {
    @Bindable var viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Text("Voting Phase")
                .font(.headline)

            if viewModel.isEliminated {
                Text("You have been eliminated and cannot vote.")
                    .foregroundStyle(.secondary)
            } else if viewModel.hasVoted {
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 32))
                        .foregroundStyle(.green)
                    Text("Vote Cast")
                        .font(.subheadline.bold())
                    Text("Waiting for other players...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 24)
            } else {
                Text("Choose who to vote for elimination")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                ForEach(viewModel.voteTargets) { player in
                    let isProtected = viewModel.protectedPlayers.contains(player.id)

                    Button {
                        HapticEngine.vote()
                        Task { await viewModel.castVote(targetId: player.id) }
                    } label: {
                        HStack(spacing: 12) {
                            PlayerAvatarView(player: player, size: 40, showName: false)

                            VStack(alignment: .leading) {
                                Text(player.name)
                                    .font(.body.bold())
                                if isProtected {
                                    Text("Protected")
                                        .font(.caption)
                                        .foregroundStyle(.blue)
                                }
                            }

                            Spacer()

                            Image(systemName: "hand.thumbsdown.fill")
                                .foregroundStyle(.red)
                        }
                        .padding(12)
                        .background(.regularMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isPerformingAction)
                }
            }

            // Show who has voted
            VStack(alignment: .leading, spacing: 4) {
                Text("Voting Status")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)

                ForEach(viewModel.activePlayers) { player in
                    HStack(spacing: 8) {
                        Image(systemName: player.hasVoted ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(player.hasVoted ? .green : .secondary)
                            .font(.caption)
                        Text(player.name)
                            .font(.caption)
                            .foregroundStyle(player.hasVoted ? .primary : .secondary)
                    }
                }
            }
            .padding()
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }
}
