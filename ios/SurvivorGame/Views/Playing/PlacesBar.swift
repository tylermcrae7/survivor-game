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
            // The whole premise of the band is seeing every place at once —
            // who wandered off with whom is the information, and it cannot be
            // information if a card is parked off the right edge. So the open
            // places share the width equally and the labels scale down rather
            // than truncate.
            //
            // `ViewThatFits` does the measuring, so no device width is baked
            // in: each card asks for `Layout.minCardWidth` as its ideal, and
            // if the phase ever opens more places than can stay legible side
            // by side, the scrolling row underneath is the graceful fallback.
            ViewThatFits(in: .horizontal) {
                openRow(equalWidth: true)
                ScrollView(.horizontal, showsIndicators: false) {
                    openRow(equalWidth: false)
                }
            }
        }
    }

    private func openRow(equalWidth: Bool) -> some View {
        HStack(spacing: PlacesBar.Layout.cardGap) {
            ForEach(policy.open, id: \.self) { key in
                PlaceCard(
                    placeKey: key,
                    occupants: occupants(of: key),
                    isHere: key == myPlace,
                    myPlayerId: myPlayerId,
                    isMoving: isMoving,
                    sharesWidth: equalWidth,
                    move: { onMove(key) }
                )
            }
        }
        .padding(.horizontal, 16)
    }

    enum Layout {
        static let cardGap: CGFloat = 8
        /// The narrowest a shared-width card may get before the band stops
        /// pretending everything fits and starts scrolling instead.
        static let minCardWidth: CGFloat = 96
    }
}

// MARK: - One open place

private struct PlaceCard: View {
    let placeKey: String
    let occupants: [PlayerState]
    let isHere: Bool
    let myPlayerId: String?
    let isMoving: Bool
    /// True when the band is laying every place out side by side, so this card
    /// takes an equal share of the width instead of its natural size.
    var sharesWidth: Bool = true
    let move: () -> Void

    var body: some View {
        Button(action: move) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 5) {
                    Image(systemName: Place.symbolName(for: placeKey))
                        .font(.system(size: 11))
                        .foregroundStyle(isHere ? Torch.Color.torch : Torch.Color.textSecondary)
                    Text(Place.label(for: placeKey))
                        .font(Torch.Font.label(Torch.TextSize.xs))
                        .tracking(Torch.Track.label * Torch.TextSize.xs)
                        .foregroundStyle(isHere ? Torch.Color.parchment : Torch.Color.textSecondary)
                        // A long name shrinks to fit its share of the band
                        // rather than truncating mid-word.
                        .lineLimit(1)
                        .minimumScaleFactor(0.6)
                }
                OccupantStrip(occupants: occupants, myPlayerId: myPlayerId, limit: 4)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
            .frame(
                minWidth: sharesWidth ? PlacesBar.Layout.minCardWidth : 108,
                idealWidth: sharesWidth ? PlacesBar.Layout.minCardWidth : nil,
                maxWidth: sharesWidth ? .infinity : nil,
                alignment: .leading
            )
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
        // "You are here" is a highlight, not a disabled state. `.disabled()`
        // dims the entire button label — the place name, its icon and your own
        // chip — which made the card you are standing in the faintest one on
        // the band and inverted the emphasis this card exists to carry. Take
        // the tap target away instead and let the amber border and glow mark
        // it; the view model refuses a move to where you already are anyway,
        // so a VoiceOver activation is a harmless no-op.
        .allowsHitTesting(!isHere && !isMoving)
        // A move in flight is the one genuinely transient case, and dimming
        // the whole band for the round trip is honest there.
        .disabled(isMoving)
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
    /// The most faces this row will ever show. It shows fewer when the card is
    /// too narrow to hold them, folding the remainder into `+N`.
    var limit: Int
    var size: CGFloat = 22

    /// Widest first — `ViewThatFits` takes the first row that actually fits
    /// the card it landed in, so a crowded place on a narrow band drops faces
    /// instead of spilling past its own border.
    private var candidateCounts: [Int] {
        Array(stride(from: min(limit, occupants.count), through: 1, by: -1))
    }

    var body: some View {
        content
            .frame(height: size, alignment: .leading)
            .accessibilityHidden(true)
    }

    @ViewBuilder private var content: some View {
        if occupants.isEmpty {
            Text("empty")
                .font(Torch.Font.label(Torch.TextSize.xs))
                .tracking(Torch.Track.label * Torch.TextSize.xs)
                .foregroundStyle(Torch.Color.textFaint)
                .lineLimit(1)
        } else {
            ViewThatFits(in: .horizontal) {
                ForEach(candidateCounts, id: \.self) { shown in
                    chips(showing: shown)
                }
            }
        }
    }

    private func chips(showing shown: Int) -> some View {
        HStack(spacing: 4) {
            ForEach(occupants.prefix(shown)) { player in
                OccupantChip(
                    player: player,
                    isMe: player.id == myPlayerId,
                    size: size
                )
            }
            if occupants.count > shown {
                Text("+\(occupants.count - shown)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Torch.Color.textSecondary)
                    .fixedSize()
            }
        }
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
                // Same two-letter monogram the avatars use — a band showing
                // "C, C, C" for Coconut, Cleo and Christopher identifies
                // nobody, and this row exists precisely to say who wandered
                // off with whom.
                Text(player.monogram)
                    .font(.system(size: size * (player.monogram.count > 1 ? 0.38 : 0.45),
                                  weight: .bold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                    .frame(width: size * 0.84)
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
