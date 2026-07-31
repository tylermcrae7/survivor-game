import SwiftUI

struct PlayerStatusBar: View {
    let players: [PlayerState]
    let currentPlayerId: String?
    let myPlayerId: String?

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                ForEach(players) { player in
                    PlayerStatusCard(
                        player: player,
                        isCurrentTurn: player.id == currentPlayerId,
                        isMe: player.id == myPlayerId
                    )
                }
            }
            .padding(.horizontal)
        }
    }
}

private struct PlayerStatusCard: View {
    let player: PlayerState
    let isCurrentTurn: Bool
    let isMe: Bool

    var body: some View {
        VStack(spacing: 6) {
            PlayerAvatarView(
                player: player,
                size: 40,
                showName: false,
                isCurrentPlayer: isCurrentTurn
            )

            Text(isMe ? "You" : player.name)
                .font(.caption2.bold())
                .foregroundStyle(isMe ? .orange : .primary)
                .strikethrough(player.isEliminated)
                .lineLimit(1)

            TorchLivesView(lives: player.characterCards)

            HStack(spacing: 2) {
                Image(systemName: "rectangle.stack")
                    .font(.system(size: 8))
                Text("\(player.handCount)")
                    .font(.caption2)
            }
            .foregroundStyle(.secondary)
        }
        .frame(width: 60)
        .padding(.vertical, 8)
        .background(isCurrentTurn ? Color.orange.opacity(0.1) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isCurrentTurn ? .orange : .clear, lineWidth: 1)
        )
        // The torchSnuff end state, held: a snuffed player reads as
        // extinguished — desaturated, dimmed, faded (web `.eliminated`).
        .saturation(player.isEliminated ? 0 : 1)
        .colorMultiply(player.isEliminated ? Color(white: 0.55) : .white)
        .opacity(player.isEliminated ? 0.45 : 1)
    }
}
