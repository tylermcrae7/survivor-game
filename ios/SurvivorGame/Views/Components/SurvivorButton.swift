import SwiftUI

/// The app's primary button. On iOS 26 it wears Liquid Glass (tinted,
/// prominent); earlier systems get the flat ember fill. One style, every
/// call site upgrades together.
struct SurvivorButton: ButtonStyle {
    var color: Color = SurvivorTheme.ember
    var isWide: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        let label = configuration.label
            .font(.headline)
            .frame(maxWidth: isWide ? .infinity : nil)
            .padding(.vertical, 14)
            .padding(.horizontal, 24)

        return Group {
            if #available(iOS 26.0, *) {
                label
                    .foregroundStyle(.white)
                    .glassEffect(.regular.tint(color.opacity(configuration.isPressed ? 0.6 : 0.9))
                        .interactive(), in: Capsule())
            } else {
                label
                    .foregroundStyle(.white)
                    .background(color.opacity(configuration.isPressed ? 0.7 : 1.0))
                    .clipShape(Capsule())
            }
        }
        .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
        .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
        .accessibilityAddTraits(.isButton)
    }
}

struct SurvivorSecondaryButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let label = configuration.label
            .font(.headline)
            .foregroundStyle(SurvivorTheme.ember)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .padding(.horizontal, 24)

        return Group {
            if #available(iOS 26.0, *) {
                label.glassEffect(.regular.interactive(), in: Capsule())
            } else {
                label
                    .background(SurvivorTheme.ember.opacity(0.1))
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(SurvivorTheme.ember.opacity(0.3), lineWidth: 1))
            }
        }
        .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
        .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
        .accessibilityAddTraits(.isButton)
    }
}

extension ButtonStyle where Self == SurvivorButton {
    static var survivor: SurvivorButton { SurvivorButton() }
    static func survivor(color: Color) -> SurvivorButton { SurvivorButton(color: color) }
}

extension ButtonStyle where Self == SurvivorSecondaryButton {
    static var survivorSecondary: SurvivorSecondaryButton { SurvivorSecondaryButton() }
}
