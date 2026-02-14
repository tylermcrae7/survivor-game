import SwiftUI

struct PlayerAvatarView: View {
    let player: PlayerState
    var size: CGFloat = 48
    var showName: Bool = true
    var isCurrentPlayer: Bool = false

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                Circle()
                    .fill(player.swiftUIColor)
                    .frame(width: size, height: size)

                Text(player.name.prefix(1).uppercased())
                    .font(.system(size: size * 0.4, weight: .bold))
                    .foregroundStyle(.white)

                if player.isEliminated {
                    Circle()
                        .fill(.black.opacity(0.5))
                        .frame(width: size, height: size)
                    Image(systemName: "xmark")
                        .font(.system(size: size * 0.3, weight: .bold))
                        .foregroundStyle(.white)
                }

                if player.isCouncilLeader {
                    Image(systemName: "crown.fill")
                        .font(.system(size: size * 0.25))
                        .foregroundStyle(.yellow)
                        .offset(y: -(size / 2 + 4))
                }
            }
            .overlay {
                if isCurrentPlayer {
                    Circle()
                        .strokeBorder(.orange, lineWidth: 3)
                        .frame(width: size + 6, height: size + 6)
                }
            }

            if showName {
                Text(player.name)
                    .font(.caption)
                    .foregroundStyle(player.isEliminated ? .secondary : .primary)
                    .lineLimit(1)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityDescription)
        .accessibilityAddTraits(isCurrentPlayer ? [.isSelected] : [])
    }
    
    private var accessibilityDescription: String {
        var description = player.name
        
        if player.isEliminated {
            description += ", eliminated"
        } else {
            description += ", active player"
        }
        
        if player.isCouncilLeader {
            description += ", tribal council leader"
        }
        
        if isCurrentPlayer {
            description += ", you"
        }
        
        if !player.hand.isEmpty {
            description += ", \(player.handCount) card\(player.handCount == 1 ? "" : "s")"
        }
        
        return description
    }
}
