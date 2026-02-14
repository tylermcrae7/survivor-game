import SwiftUI

struct CardView: View {
    let card: CardInstance
    var isPlayable: Bool = false
    var isCompact: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: isCompact ? 4 : 8) {
            // Category badge
            HStack {
                Text(card.cardCategory.displayName.uppercased())
                    .font(.system(size: isCompact ? 8 : 10, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(card.cardCategory.color)
                    .clipShape(Capsule())
                Spacer()
            }

            // Card name
            Text(card.displayName)
                .font(isCompact ? .caption.bold() : .subheadline.bold())
                .foregroundStyle(.primary)
                .lineLimit(isCompact ? 1 : 2)

            if !isCompact, let desc = card.description {
                Text(desc)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
        }
        .padding(isCompact ? 8 : 12)
        .frame(width: isCompact ? 80 : 120, height: isCompact ? 70 : 140)
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
