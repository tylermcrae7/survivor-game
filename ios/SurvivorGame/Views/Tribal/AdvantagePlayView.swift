import SwiftUI

struct AdvantagePlayView: View {
    @Bindable var viewModel: TribalViewModel
    @State private var selectedAdvantage: CardInstance?
    @State private var selectedTarget: String?
    @State private var showTargetPicker = false

    var body: some View {
        VStack(spacing: 16) {
            Text("Advantage Play Phase")
                .font(.headline)

            Text("Play any tribal advantage cards now.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if !viewModel.isEliminated {
                let advantages = viewModel.myTribalCards.filter {
                    $0.category == "tribal_advantage" && $0.playablePhases?.contains("tribal_discussion") == true
                }

                if advantages.isEmpty {
                    Text("You have no advantage cards to play.")
                        .foregroundStyle(.secondary)
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
                                        .font(.subheadline.bold())
                                    if let desc = card.description {
                                        Text(desc)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                Image(systemName: "play.fill")
                                    .foregroundStyle(.orange)
                            }
                            .padding(12)
                            .background(.regularMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Show played advantages
            if let played = viewModel.voteState?.advantageCardsPlayed, !played.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Advantages Played")
                        .font(.subheadline.bold())

                    ForEach(Array(played.enumerated()), id: \.offset) { _, record in
                        let playerName = record.playerId
                            .flatMap { viewModel.gameState?.players[$0]?.name } ?? "Unknown"
                        let advantage = (record.advantageType ?? "an advantage")
                            .replacingOccurrences(of: "_", with: " ")
                        HStack {
                            Text(playerName)
                                .font(.caption.bold())
                            Text("played \(advantage)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
                .background(.orange.opacity(0.1))
                .clipShape(RoundedRectangle(cornerRadius: 10))
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
                            .font(.body)
                        Spacer()
                    }
                }
            }
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
