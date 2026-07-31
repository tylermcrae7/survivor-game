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

private struct CardHandContent: View {
    @Bindable var viewModel: CardHandViewModel
    @Environment(GameClient.self) private var gameClient

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Your Hand")
                    .font(.headline)
                Spacer()
                Text("\(viewModel.hand.count) cards")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal)

            if viewModel.hand.isEmpty {
                Text("No cards in hand")
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 20)
            } else {
                // Two-column hand, like the web's card grid; scrolls when the
                // hand outgrows two rows so the bottom slot stays bounded.
                ScrollView(showsIndicators: false) {
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 8),
                                        GridItem(.flexible(), spacing: 8)],
                              spacing: 8) {
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
                    .padding(.horizontal)
                }
                .frame(maxHeight: 296) // two full rows; more cards scroll
            }
        }
        .sheet(isPresented: $viewModel.showCardDetail) {
            if let card = viewModel.selectedCard, let index = viewModel.selectedCardIndex {
                CardDetailSheet(
                    card: card,
                    index: index,
                    isPlayable: viewModel.isPlayable(card, at: index)
                )
            }
        }
    }
}
