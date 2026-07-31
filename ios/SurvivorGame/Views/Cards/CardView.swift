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

    // MARK: - Compact chip (AdvantagePlayView's horizontal row — unchanged)

    private var compactFace: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Category badge
            HStack {
                Text(card.cardCategory.displayName.uppercased())
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(card.cardCategory.color)
                    .clipShape(Capsule())
                Spacer()
            }

            // Card name
            Text(card.displayName)
                .font(.caption.bold())
                .foregroundStyle(.primary)
                .lineLimit(1)
        }
        .padding(8)
        // Compact stays fixed for the advantage picker's horizontal row.
        .frame(maxWidth: 80, alignment: .topLeading)
        .frame(width: 80, height: 70)
        .background(isPlayable ? card.cardCategory.color.opacity(0.15) : Color(.systemGray6))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(
                    isPlayable ? card.cardCategory.color : .clear,
                    lineWidth: 2
                )
        )
        .shadow(color: isPlayable ? card.cardCategory.color.opacity(0.3) : .clear, radius: 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(card.displayName), \(card.cardCategory.displayName) card")
        .accessibilityValue(card.description ?? "")
        .accessibilityAddTraits(isPlayable ? [.isButton] : [])
        .accessibilityHint(isPlayable ? "Double tap to play this card" : "")
    }
}
