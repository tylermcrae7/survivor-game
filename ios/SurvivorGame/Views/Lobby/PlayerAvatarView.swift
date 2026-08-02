import SwiftUI

struct PlayerAvatarView: View {
    let player: PlayerState
    var size: CGFloat = 48
    var showName: Bool = true
    var isCurrentPlayer: Bool = false
    /// Opt-in, and it must stay opt-in: six of the thirteen call sites already
    /// sit inside a Button that votes, steals or eliminates. Making every
    /// avatar tappable would nest a button in a button — SwiftUI hands the tap
    /// to the inner one and the outer action is swallowed.
    var onTap: (() -> Void)? = nil

    var body: some View {
        if let onTap {
            Button(action: onTap) { content }
                // .plain, never .survivor: SurvivorButton's style body adds
                // .isButton, and that trait propagates into a composed label's
                // separate parts (see ReactiveTheftOverlay).
                .buttonStyle(.plain)
                .contentShape(Rectangle())
                .accessibilityElement(children: .combine)
                .accessibilityLabel(accessibilityDescription)
                .accessibilityAddTraits(isCurrentPlayer ? [.isButton, .isSelected] : [.isButton])
                .accessibilityHint("Shows their lives, cards and where they're standing")
        } else {
            content
                .accessibilityElement(children: .combine)
                .accessibilityLabel(accessibilityDescription)
                .accessibilityAddTraits(isCurrentPlayer ? [.isSelected] : [])
        }
    }

    private var content: some View {
        VStack(spacing: 6) {
            ZStack {
                Circle()
                    .fill(player.swiftUIColor)
                    .frame(width: size, height: size)

                Text(player.monogram)
                    // Two characters need to be smaller than one to sit inside
                    // the same disc — 32pt is the smallest circle in the app.
                    .font(.system(size: size * (player.monogram.count > 1 ? 0.34 : 0.42),
                                  weight: .bold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .frame(width: size * 0.82)

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
