import SwiftUI

struct CardDetailSheet: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss
    let card: CardInstance
    let index: Int
    let isPlayable: Bool

    @State private var isPlaying = false
    @State private var error: ViewModelError?

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                // Card type badge
                Text(card.cardCategory.displayName.uppercased())
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(card.cardCategory.color)
                    .clipShape(Capsule())

                // Card name
                Text(card.displayName)
                    .font(.title2.bold())

                // Description
                if let desc = card.description {
                    Text(desc)
                        .font(.body)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }

                // Card details
                VStack(alignment: .leading, spacing: 8) {
                    if let phases = card.playablePhases, !phases.isEmpty {
                        DetailRow(label: "Playable During", value: phases.map { formatPhase($0) }.joined(separator: ", "))
                    }
                    if card.requiresTarget == true {
                        DetailRow(label: "Requires Target", value: "Yes")
                    }
                    if card.reactiveOnly == true {
                        DetailRow(label: "Reactive Only", value: "Yes")
                    }
                }
                .padding()
                .background(.regularMaterial)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Spacer()

                // Play button
                if isPlayable {
                    Button {
                        Task { await playCard() }
                    } label: {
                        if isPlaying {
                            ProgressView().tint(.white)
                        } else {
                            Text("Play Card")
                        }
                    }
                    .buttonStyle(.survivor)
                    .disabled(isPlaying)
                } else {
                    Text("Cannot play this card right now")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(24)
            .navigationTitle("Card Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .errorAlert($error)
        }
    }

    private func playCard() async {
        isPlaying = true
        defer { isPlaying = false }
        do {
            _ = try await gameClient.playCard(at: index)
            HapticEngine.cardPlay()
            dismiss()
        } catch {
            self.error = .from(error)
        }
    }

    private func formatPhase(_ phase: String) -> String {
        phase.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

private struct DetailRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption.bold())
        }
    }
}
