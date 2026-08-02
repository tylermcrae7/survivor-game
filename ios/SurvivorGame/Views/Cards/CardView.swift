import SwiftUI

/// The hand card. Non-compact is the web's glanceable mini (`.card-mini`):
/// category + NAME + status badges only — the rules live one tap away in
/// CardDetailSheet. Compact stays the fixed 80×70 chip the advantage picker
/// lays in a row.
struct CardView: View {
    let card: CardInstance
    var isPlayable: Bool = false
    var isCompact: Bool = false

    var body: some View {
        if isCompact {
            compactFace
        } else {
            miniFace
        }
    }

    // MARK: - Glanceable mini (web §Playing cards .card-mini)

    private var miniFace: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(card.cardCategory.displayName.lowercased())
                .font(Torch.Font.label(9))
                .tracking(Torch.Track.wide * 9)
                .foregroundStyle(Torch.Color.textFaint)
                .lineLimit(1)

            Text(card.displayName)
                .font(Torch.Font.display(15, weight: 700))
                .foregroundStyle(Torch.Color.parchment)
                .lineLimit(2)
                .multilineTextAlignment(.leading)

            Spacer(minLength: 4)

            // Badge row: what the card needs, and whether it's live NOW.
            HStack(spacing: 6) {
                if card.requiresTarget == true {
                    Image(systemName: "scope")
                        .font(.system(size: 10))
                        .foregroundStyle(Torch.Color.textFaint)
                }
                if card.reactiveOnly == true {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 10))
                        .foregroundStyle(Torch.Color.textFaint)
                }
                Spacer()
                if isPlayable {
                    Text("now")
                        .font(Torch.Font.label(9))
                        .foregroundStyle(Torch.Color.torch)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .overlay(
                            Capsule().strokeBorder(Torch.Color.torch.opacity(0.55),
                                                   lineWidth: 1)
                        )
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(Torch.Color.surfaceRaised)
                .overlay(
                    // Top sheen: white@4.5% fading out by 30%.
                    RoundedRectangle(cornerRadius: 11, style: .continuous)
                        .fill(LinearGradient(stops: [
                            .init(color: .white.opacity(0.045), location: 0),
                            .init(color: .clear, location: 0.30),
                        ], startPoint: .top, endPoint: .bottom))
                )
        )
        // The 4px category rule across the top edge.
        .overlay(alignment: .top) {
            UnevenRoundedRectangle(topLeadingRadius: 11, topTrailingRadius: 11)
                .fill(card.cardCategory.torchGradient)
                .frame(height: 4)
        }
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .strokeBorder(isPlayable ? Torch.Color.torch.opacity(0.55)
                                         : Torch.Color.lineStrong,
                              lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.4), radius: 9, y: 6) // --shadow-md
        .shadow(color: Torch.Color.torch.opacity(isPlayable ? 0.35 : 0), radius: 11)
        .offset(y: isPlayable ? -2 : 0) // playable cards float
        .opacity(isPlayable ? 1 : 0.45) // locked cards dim…
        .saturation(isPlayable ? 1 : 0.35) // …and desaturate
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "\(card.displayName), \(card.cardCategory.displayName) card"
                + (isPlayable ? ", playable now" : "")
        )
        .accessibilityValue(card.description ?? "")
        .accessibilityAddTraits(.isButton)
        // Locked cards stay tappable — the sheet is how you read a card.
        .accessibilityHint(isPlayable ? "Double tap to read and play"
                                      : "Double tap to read this card")
    }

    // MARK: - Compact chip (AdvantagePlayView's horizontal row)

    /// The advantage row's thumbnail. It sits beside the card's full name and
    /// rules text, so it carries no information of its own — it is the visual
    /// anchor for the row, and it says which card by echoing the mini's
    /// category rule and title.
    ///
    /// It used to be a pre-Torch chip: a solid `.purple` capsule holding
    /// "TRIBAL ADVANTAGE" in a fixed 80pt frame, which is roughly 20pt too
    /// narrow for that phrase. The label broke mid-word across three lines,
    /// spilled past the capsule, and pushed the title out of the tile.
    private var compactFace: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(card.cardCategory.displayName.lowercased())
                .font(Torch.Font.label(8))
                .tracking(Torch.Track.wide * 8)
                .foregroundStyle(Torch.Color.textFaint)
                .lineLimit(1)
                // "tribal advantage" is the longest label in the set and the
                // one that broke; let it shrink rather than wrap.
                .minimumScaleFactor(0.6)

            Text(card.displayName)
                .font(Torch.Font.display(12, weight: 700))
                .foregroundStyle(Torch.Color.parchment)
                .lineLimit(2)
                .minimumScaleFactor(0.75)
                .multilineTextAlignment(.leading)

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.top, 9)
        .padding(.bottom, 6)
        .frame(width: 96, height: 76, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: Torch.Radius.sm, style: .continuous)
                .fill(CouncilPalette.surfaceSunken)
        )
        .overlay(alignment: .top) {
            UnevenRoundedRectangle(topLeadingRadius: Torch.Radius.sm,
                                   topTrailingRadius: Torch.Radius.sm)
                .fill(card.cardCategory.torchGradient)
                .frame(height: 3)
        }
        .overlay(
            RoundedRectangle(cornerRadius: Torch.Radius.sm, style: .continuous)
                .strokeBorder(isPlayable ? Torch.Color.torch.opacity(0.55)
                                         : CouncilPalette.line,
                              lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(card.displayName), \(card.cardCategory.displayName) card")
        .accessibilityValue(card.description ?? "")
        .accessibilityAddTraits(isPlayable ? [.isButton] : [])
        .accessibilityHint(isPlayable ? "Double tap to play this card" : "")
    }
}
