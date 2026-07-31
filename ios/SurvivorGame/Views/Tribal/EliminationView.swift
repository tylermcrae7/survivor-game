import SwiftUI

struct EliminationView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var snuffTrigger = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// The web's inline animation-delay recipe (see TorchTransitions.swift
    /// §torchSnuff): the torch waits for the last ballot to finish flipping —
    /// 0.5 + ballotCount × 0.32 + 0.25. Reduced motion collapses the ceremony
    /// (ballots land instantly), so the snuff fires promptly instead.
    private var snuffLead: Double {
        reduceMotion ? 0.05 : 0.5 + Double(viewModel.voteResults.count) * 0.32 + 0.25
    }

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
                        .torchSnuff(trigger: snuffTrigger, delay: snuffLead)

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
                snuffTrigger += 1
            }
        }
        .task {
            // Haptic + sound ride the same lead as the visual snuff, so all
            // three land together after the last ballot flips. Structured so
            // an early dismissal cancels the moment.
            guard !viewModel.eliminatedInTribal.isEmpty else { return }
            try? await Task.sleep(for: .seconds(snuffLead))
            guard !Task.isCancelled else { return }
            HapticEngine.elimination()
            TorchSound.play(.torchSnuff)
        }
    }
}
