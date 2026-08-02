import SwiftUI

struct TieBreakView: View {
    @Bindable var viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "equal.circle.fill")
                .font(.system(size: 40))
                .foregroundStyle(Torch.Color.warning)
                .shadow(color: Torch.Color.warning.opacity(0.4), radius: 12)

            CeremonyTitle(text: "Tie Break!", size: Torch.TextSize.displayMD)

            Text("The council leader must break the tie.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
                .multilineTextAlignment(.center)

            if viewModel.isCouncilLeader {
                Text("Choose who to eliminate:")
                    .font(Torch.Font.label(Torch.TextSize.sm))
                    .tracking(Torch.Track.label * Torch.TextSize.sm)
                    .foregroundStyle(Torch.Color.parchment)

                ForEach(viewModel.tiedPlayers) { player in
                    Button {
                        HapticEngine.elimination()
                        Task { await viewModel.resolveTieBreak(chosenId: player.id) }
                    } label: {
                        HStack(spacing: 12) {
                            PlayerAvatarView(player: player, size: 40, showName: false)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(player.name)
                                    .font(Torch.Font.body(Torch.TextSize.base, weight: .bold))
                                    .foregroundStyle(Torch.Color.parchment)
                                // The stake, at the moment of the decision.
                                // Lives are decremented later, in
                                // complete_tribal, so this is the count the
                                // player still has: two torches means this
                                // costs them a Character Card, one means it
                                // ends their game.
                                TorchLivesView(lives: player.characterCards)
                            }
                            Spacer()
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(Torch.Color.danger)
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel(
                            "\(player.name), \(player.characterCards) of 2 torches lit")
                        .accessibilityHint(player.characterCards > 1
                                           ? "Takes one of their Survivor Character Cards"
                                           : "Eliminates them from the game")
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                                .fill(Torch.Color.danger.opacity(0.1))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                                .strokeBorder(Torch.Color.danger.opacity(0.5), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isPerformingAction)
                }
            } else {
                Text("Waiting for the council leader to decide...")
                    .foregroundStyle(Torch.Color.textSecondary)
                    .padding()
            }
        }
        .padding()
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                .fill(CouncilPalette.surface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                .strokeBorder(CouncilPalette.line, lineWidth: 1)
        )
    }
}
