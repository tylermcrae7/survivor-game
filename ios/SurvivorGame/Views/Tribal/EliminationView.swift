import SwiftUI

struct EliminationView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var snuffTrigger = 0

    var body: some View {
        VStack(spacing: 16) {
            if viewModel.eliminatedInTribal.isEmpty {
                Text("No one was eliminated.")
                    .font(Torch.Font.body(Torch.TextSize.sm))
                    .foregroundStyle(Torch.Color.textSecondary)
            } else {
                ForEach(viewModel.eliminatedInTribal) { player in
                    VStack(spacing: 12) {
                        // The torch: flares, then dies to gray. The snuff's
                        // end state persists — the fire stays out.
                        VStack(spacing: 8) {
                            Image(systemName: "flame.fill")
                                .font(.system(size: 40))
                                .foregroundStyle(Torch.Color.torch)
                                .torchGlow(0.7, radius: 9)
                                .accessibilityHidden(true)
                            PlayerAvatarView(player: player, size: 64, showName: false)
                        }
                        .torchSnuff(trigger: snuffTrigger, delay: 0.25)

                        Text(player.name)
                            .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                            .foregroundStyle(CouncilPalette.eliminatedRed)

                        Text("The tribe has spoken.")
                            .font(Torch.Font.display(Torch.TextSize.displayMD, weight: 900, soft: 60,
                                                     italic: true))
                            .foregroundStyle(Torch.Color.parchment)
                    }
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                            .fill(CouncilPalette.surface)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                            .strokeBorder(Torch.Color.danger.opacity(0.5), lineWidth: 1)
                    )
                }
            }
        }
        .onAppear {
            if !viewModel.eliminatedInTribal.isEmpty {
                HapticEngine.elimination()
                TorchSound.play(.torchSnuff)
                snuffTrigger += 1
            }
        }
    }
}
