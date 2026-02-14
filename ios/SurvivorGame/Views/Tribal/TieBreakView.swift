import SwiftUI

struct TieBreakView: View {
    @Bindable var viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "equal.circle.fill")
                .font(.system(size: 40))
                .foregroundStyle(.yellow)

            Text("Tie Break!")
                .font(.title2.bold())

            Text("The council leader must break the tie.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if viewModel.isCouncilLeader {
                Text("Choose who to eliminate:")
                    .font(.subheadline.bold())

                ForEach(viewModel.tiedPlayers) { player in
                    Button {
                        HapticEngine.elimination()
                        Task { await viewModel.resolveTieBreak(chosenId: player.id) }
                    } label: {
                        HStack(spacing: 12) {
                            PlayerAvatarView(player: player, size: 40, showName: false)
                            Text(player.name)
                                .font(.body.bold())
                            Spacer()
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.red)
                        }
                        .padding(12)
                        .background(.red.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isPerformingAction)
                }
            } else {
                Text("Waiting for the council leader to decide...")
                    .foregroundStyle(.secondary)
                    .padding()
            }
        }
        .padding()
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
