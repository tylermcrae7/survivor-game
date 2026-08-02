import SwiftUI

struct PlayerStatusBar: View {
    @Environment(GameClient.self) private var gameClient

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
                        isMe: player.id == myPlayerId,
                        // The Challenge winner wears the Immunity Necklace
                        // until the next Tribal Council spends it — until now
                        // the app tracked it but never showed it.
                        hasNecklace: player.id == gameClient.gameState?.necklaceHolder
                    )
                }
            }
            .padding(.horizontal)
        }
    }
}

private struct PlayerStatusCard: View {
    @Environment(PlayerInspector.self) private var inspector

    let player: PlayerState
    let isCurrentTurn: Bool
    let isMe: Bool
    var hasNecklace: Bool = false

    var body: some View {
        // The whole card is the tap target, not the 40pt avatar inside it —
        // 40 is under both the HIG minimum and this project's own 48pt token.
        Button { inspector.playerId = player.id } label: { card }
            .buttonStyle(.plain)
            .contentShape(RoundedRectangle(cornerRadius: 8))
            .accessibilityElement(children: .combine)
            .accessibilityLabel(
                "\(isMe ? "You" : player.name), \(player.characterCards) of 2 torches lit, "
                + "\(player.handCount) card\(player.handCount == 1 ? "" : "s")"
                + (hasNecklace ? ", wears the Immunity Necklace" : "")
                + (player.isEliminated ? ", eliminated" : ""))
            .accessibilityAddTraits(.isButton)
            .accessibilityHint("Opens their details")
    }

    private var card: some View {
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
        // A badge rather than a row: the necklace must not make one card
        // taller than the rest of the strip. Drawn AFTER the clipShape —
        // applied before it, the rounded corner shaved the shield.
        .overlay(alignment: .topTrailing) {
            if hasNecklace {
                Image(systemName: "shield.lefthalf.filled")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Torch.Color.juryGold)
                    .shadow(color: .black.opacity(0.6), radius: 2)
                    .padding(.top, 4)
                    .accessibilityLabel("holds the Immunity Necklace")
            }
        }
        // The torchSnuff end state, held: a snuffed player reads as
        // extinguished — desaturated, dimmed, faded (web `.eliminated`).
        .saturation(player.isEliminated ? 0 : 1)
        .colorMultiply(player.isEliminated ? Color(white: 0.55) : .white)
        .opacity(player.isEliminated ? 0.45 : 1)
    }
}
