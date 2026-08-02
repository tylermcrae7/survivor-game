import SwiftUI

struct CardHandView: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: CardHandViewModel?

    var body: some View {
        if let vm = viewModel {
            CardHandContent(viewModel: vm)
        } else {
            Color.clear.onAppear {
                viewModel = CardHandViewModel(gameClient: gameClient)
            }
        }
    }
}

/// Content-hugging hand grid: no inner scroll, no height cap, no padding of
/// its own — the parent scroll region pads and scrolls the whole flow.
private struct CardHandContent: View {
    @Bindable var viewModel: CardHandViewModel
    @Environment(GameClient.self) private var gameClient

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text("your hand")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)
                Text("· \(viewModel.hand.count)")
                    .font(Torch.Font.body(Torch.TextSize.xs))
                    .foregroundStyle(Torch.Color.textFaint)
            }

            if viewModel.hand.isEmpty {
                Text("No cards — the island provides at the next draw.")
                    .font(Torch.Font.body(Torch.TextSize.sm))
                    .foregroundStyle(Torch.Color.textFaint)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 20)
                    .overlay(
                        RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                            .strokeBorder(Torch.Color.line,
                                          style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    )
            } else {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: Torch.Spacing.sm),
                                    GridItem(.flexible(), spacing: Torch.Spacing.sm)],
                          spacing: Torch.Spacing.sm) {
                    // Keyed by position, not by `card.id`. A server that
                    // predates uids sends three identical Vote Cards, whose
                    // ids all collapse to "vote" — SwiftUI then renders the
                    // duplicates as empty cells and the grid silently shows
                    // four cards for a hand of six. Position is the only
                    // identity that is unique no matter what arrives.
                    ForEach(Array(viewModel.hand.enumerated()), id: \.offset) { index, card in
                        Button {
                            viewModel.selectCard(at: index)
                            HapticEngine.selection()
                        } label: {
                            CardView(
                                card: card,
                                isPlayable: viewModel.isPlayable(card, at: index)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .sheet(isPresented: $viewModel.showCardDetail) {
            if let card = viewModel.selectedCard, let index = viewModel.selectedCardIndex {
                CardDetailSheet(
                    card: card,
                    index: index,
                    isPlayable: viewModel.isPlayable(card, at: index)
                )
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
            }
        }
    }
}
