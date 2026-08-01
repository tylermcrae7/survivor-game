import SwiftUI

/// Where everyone is standing. The whole point is that it's public: two
/// players wandering off to the well together is exactly the information the
/// table is meant to see, with or without a Discord bot mirroring it to voice.
///
/// Sits directly under `PlayerStatusBar` and borrows its idiom — a horizontal
/// strip of small cards — so "who is who" and "who is where" read as one band.
struct PlacesBar: View {
    let policy: PlacePolicy
    /// The table in turn order (`GameState.sortedPlayers`).
    let players: [PlayerState]
    let myPlayerId: String?
    /// A move is in flight; every card goes inert until the state lands.
    var isMoving: Bool = false
    let onMove: (String) -> Void

    private var myPlace: String? {
        players.first { $0.id == myPlayerId }?.placeKey
    }

    /// Snuffed players are not at camp any more, wherever the server last
    /// left them.
    private func occupants(of key: String) -> [PlayerState] {
        players.filter { $0.isAlive && $0.placeKey == key }
    }

    var body: some View {
        if let forced = policy.forced {
            ForcedPlaceRow(
                placeKey: forced,
                occupants: occupants(of: forced),
                myPlayerId: myPlayerId
            )
            .padding(.horizontal, 16)
        } else if !policy.open.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(policy.open, id: \.self) { key in
                        PlaceCard(
                            placeKey: key,
                            occupants: occupants(of: key),
                            isHere: key == myPlace,
                            myPlayerId: myPlayerId,
                            isMoving: isMoving,
                            move: { onMove(key) }
                        )
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }
}

// MARK: - One open place

private struct PlaceCard: View {
    let placeKey: String
    let occupants: [PlayerState]
    let isHere: Bool
    let myPlayerId: String?
    let isMoving: Bool
    let move: () -> Void

    var body: some View {
        Button(action: move) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: Place.symbolName(for: placeKey))
                        .font(.system(size: 12))
                        .foregroundStyle(isHere ? Torch.Color.torch : Torch.Color.textSecondary)
                    Text(Place.label(for: placeKey))
                        .font(Torch.Font.label(Torch.TextSize.xs))
                        .tracking(Torch.Track.label * Torch.TextSize.xs)
                        .foregroundStyle(isHere ? Torch.Color.parchment : Torch.Color.textSecondary)
                        .lineLimit(1)
                }
                OccupantStrip(occupants: occupants, myPlayerId: myPlayerId, limit: 4)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(minWidth: 108, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(isHere ? Torch.Color.surfaceRaised : Torch.Color.surfaceSunken)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(isHere ? Torch.Color.torch : Torch.Color.line, lineWidth: 1)
            )
            .torchGlow(isHere ? 0.25 : 0)
            .contentShape(RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous))
        }
        .buttonStyle(.plain)
        // The place you're already in is marked, not tappable.
        .disabled(isHere || isMoving)
        .opacity(isMoving && !isHere ? 0.5 : 1)
        .animation(.easeOut(duration: 0.18), value: isHere)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlaceOccupancy.describe(
            placeKey: placeKey, occupants: occupants, myPlayerId: myPlayerId))
        .accessibilityHint(isHere ? "" : "Moves you to \(Place.label(for: placeKey))")
        .accessibilityAddTraits(isHere ? [.isSelected] : [])
    }
}

// MARK: - The forced place (the ceremony is not optional)

private struct ForcedPlaceRow: View {
    let placeKey: String
    let occupants: [PlayerState]
    let myPlayerId: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: Place.symbolName(for: placeKey))
                    .font(.system(size: 12))
                    .foregroundStyle(Torch.Color.textFaint)
                Text(Place.label(for: placeKey))
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)
                Image(systemName: "lock.fill")
                    .font(.system(size: 9))
                    .foregroundStyle(Torch.Color.textFaint)
                Spacer(minLength: 0)
            }
            OccupantStrip(occupants: occupants, myPlayerId: myPlayerId, limit: 8)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                .fill(Torch.Color.surfaceSunken)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                .strokeBorder(Torch.Color.line, lineWidth: 1)
        )
        // Closed: dimmed and desaturated, with no tap target anywhere on it.
        .saturation(0.5)
        .opacity(0.72)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            "\(PlaceOccupancy.describe(placeKey: placeKey, occupants: occupants, myPlayerId: myPlayerId)). Everyone is held here — you cannot move."
        )
    }
}

// MARK: - Occupants

private struct OccupantStrip: View {
    let occupants: [PlayerState]
    let myPlayerId: String?
    var limit: Int
    var size: CGFloat = 22

    var body: some View {
        HStack(spacing: 4) {
            if occupants.isEmpty {
                Text("empty")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textFaint)
            } else {
                ForEach(occupants.prefix(limit)) { player in
                    OccupantChip(
                        player: player,
                        isMe: player.id == myPlayerId,
                        size: size
                    )
                }
                if occupants.count > limit {
                    Text("+\(occupants.count - limit)")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Torch.Color.textSecondary)
                }
            }
        }
        .frame(height: size, alignment: .leading)
        .accessibilityHidden(true)
    }
}

private struct OccupantChip: View {
    let player: PlayerState
    let isMe: Bool
    let size: CGFloat

    var body: some View {
        Circle()
            .fill(player.swiftUIColor)
            .frame(width: size, height: size)
            .overlay {
                Text(player.name.prefix(1).uppercased())
                    .font(.system(size: size * 0.45, weight: .bold))
                    .foregroundStyle(.white)
            }
            .overlay {
                Circle().strokeBorder(isMe ? Torch.Color.torch : .clear, lineWidth: 1.5)
            }
            // Bots sit at the table and belong in the room count, but they
            // have no voice and no secrets — present, never loud.
            .saturation(player.isBot ? 0.3 : 1)
            .opacity(player.isBot ? 0.7 : 1)
    }
}

// MARK: - Spoken description

/// "The Beach, Coconut and Driftwood" — shared by the open cards and the
/// locked ceremony row so both read the same way.
enum PlaceOccupancy {
    static func describe(
        placeKey: String, occupants: [PlayerState], myPlayerId: String?
    ) -> String {
        let label = Place.label(for: placeKey)
        guard !occupants.isEmpty else { return "\(label), nobody" }
        let names = occupants.map { $0.id == myPlayerId ? "you" : $0.name }
        return "\(label), \(names.formatted(.list(type: .and)))"
    }
}
