import SwiftUI

struct AdvantagePlayView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var selectedAdvantage: CardInstance?
    @State private var selectedTarget: String?
    @State private var showTargetPicker = false

    var body: some View {
        VStack(spacing: 16) {
            CeremonyTitle(text: "Advantage Play Phase", size: Torch.TextSize.displayMD)

            Text("Play any tribal advantage cards now.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
                .multilineTextAlignment(.center)

            if !viewModel.isEliminated {
                // `myTribalCards` is already catalog-resolved; going back through
                // the catalog for the phases keeps this correct even for a card
                // that arrived fully formed. The advantage_play window maps to
                // the server's `tribal_discussion` playability token (the same
                // mapping CardHandViewModel.currentPhase makes).
                let advantages = viewModel.myTribalCards.filter { card in
                    card.category == "tribal_advantage"
                        && CardCatalog.shared.playablePhases(for: card).contains("tribal_discussion")
                }

                if advantages.isEmpty {
                    Text("You have no advantage cards to play.")
                        .foregroundStyle(Torch.Color.textSecondary)
                        .padding()
                } else {
                    ForEach(Array(advantages.enumerated()), id: \.offset) { _, card in
                        Button {
                            selectedAdvantage = card
                            if card.requiresTarget == true {
                                showTargetPicker = true
                            } else {
                                Task {
                                    await viewModel.playAdvantage(type: card.type)
                                }
                            }
                        } label: {
                            HStack {
                                CardView(card: card, isPlayable: true, isCompact: true)
                                VStack(alignment: .leading) {
                                    Text(card.displayName)
                                        .font(Torch.Font.body(Torch.TextSize.sm, weight: .bold))
                                        .foregroundStyle(Torch.Color.parchment)
                                    if let desc = card.description {
                                        Text(desc)
                                            .font(Torch.Font.body(Torch.TextSize.xs))
                                            .foregroundStyle(Torch.Color.textSecondary)
                                    }
                                }
                                Spacer()
                                Image(systemName: "play.fill")
                                    .foregroundStyle(Torch.Color.torch)
                            }
                            .padding(12)
                            .background(
                                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                                    .fill(CouncilPalette.surfaceRaised)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                                    .strokeBorder(CouncilPalette.line, lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Show played advantages
            if let played = viewModel.voteState?.advantageCardsPlayed, !played.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Advantages Played")
                        .font(Torch.Font.label(Torch.TextSize.sm))
                        .tracking(Torch.Track.label * Torch.TextSize.sm)
                        .foregroundStyle(Torch.Color.torch)

                    ForEach(Array(played.enumerated()), id: \.offset) { _, record in
                        let playerName = record.playerId
                            .flatMap { viewModel.gameState?.players[$0]?.name } ?? "Unknown"
                        let advantage = (record.advantageType ?? "an advantage")
                            .replacingOccurrences(of: "_", with: " ")
                        HStack {
                            Text(playerName)
                                .font(Torch.Font.body(Torch.TextSize.xs, weight: .bold))
                                .foregroundStyle(Torch.Color.parchment)
                            Text("played \(advantage)")
                                .font(Torch.Font.body(Torch.TextSize.xs))
                                .foregroundStyle(Torch.Color.textSecondary)
                        }
                    }
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .fill(Torch.Color.torch.opacity(0.1))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                        .strokeBorder(Torch.Color.torch.opacity(0.45), lineWidth: 1)
                )
            }
        }
        .sheet(isPresented: $showTargetPicker) {
            TargetPickerSheet(
                title: "Choose Target",
                players: viewModel.voteTargets
            ) { targetId in
                if let card = selectedAdvantage {
                    Task {
                        await viewModel.playAdvantage(type: card.type, targetId: targetId)
                    }
                }
            }
        }
    }
}

struct TargetPickerSheet: View {
    let title: String
    let players: [PlayerState]
    let onSelect: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(players) { player in
                Button {
                    onSelect(player.id)
                    dismiss()
                } label: {
                    HStack(spacing: 12) {
                        PlayerAvatarView(player: player, size: 36, showName: false)
                        Text(player.name)
                            .font(Torch.Font.body(Torch.TextSize.base))
                            .foregroundStyle(Torch.Color.text)
                        Spacer()
                    }
                }
                .listRowBackground(CouncilPalette.surfaceSunken)
                // Stable handle: the camp strip behind this sheet has buttons
                // carrying the same player names.
                .accessibilityIdentifier("target-\(player.name)")
            }
            .scrollContentBackground(.hidden)
            .background(CouncilBackground())
            .tint(Torch.Color.torch)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
