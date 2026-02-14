import SwiftUI

struct TurnIndicatorView: View {
    let currentPlayer: PlayerState?
    let isMyTurn: Bool
    let turnPhase: TurnPhase?
    let deckCount: Int

    var body: some View {
        HStack(spacing: 12) {
            // Current player indicator
            if let player = currentPlayer {
                HStack(spacing: 8) {
                    Circle()
                        .fill(player.swiftUIColor)
                        .frame(width: 12, height: 12)
                    Text(isMyTurn ? "Your Turn" : "\(player.name)'s Turn")
                        .font(.subheadline.bold())
                        .foregroundStyle(isMyTurn ? .orange : .primary)
                }
            }

            Spacer()

            // Turn phase
            if let phase = turnPhase {
                Text(phaseLabel(phase))
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(phaseColor(phase))
                    .clipShape(Capsule())
            }

            // Deck count
            HStack(spacing: 4) {
                Image(systemName: "rectangle.stack.fill")
                    .font(.caption)
                Text("\(deckCount)")
                    .font(.caption.bold())
            }
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.regularMaterial)
    }

    private func phaseLabel(_ phase: TurnPhase) -> String {
        switch phase {
        case .steal: return "Steal"
        case .play: return "Play"
        case .draw: return "Draw"
        }
    }

    private func phaseColor(_ phase: TurnPhase) -> Color {
        switch phase {
        case .steal: return .red
        case .play: return .orange
        case .draw: return .blue
        }
    }
}
