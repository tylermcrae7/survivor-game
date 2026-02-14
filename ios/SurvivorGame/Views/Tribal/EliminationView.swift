import SwiftUI

struct EliminationView: View {
    @Bindable var viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            if viewModel.eliminatedInTribal.isEmpty {
                Text("No one was eliminated.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.eliminatedInTribal) { player in
                    VStack(spacing: 12) {
                        PlayerAvatarView(player: player, size: 64, showName: false)

                        Text(player.name)
                            .font(.title3.bold())
                            .foregroundStyle(.red)

                        Text("The tribe has spoken.")
                            .font(.subheadline.italic())
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(.red.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
        }
        .onAppear {
            if !viewModel.eliminatedInTribal.isEmpty {
                HapticEngine.elimination()
            }
        }
    }
}
