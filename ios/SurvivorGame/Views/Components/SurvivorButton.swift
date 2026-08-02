import SwiftUI

/// The app's primary button. On iOS 26 it wears Liquid Glass (tinted,
/// prominent); earlier systems get the flat ember fill. One style, every
/// call site upgrades together.
struct SurvivorButton: ButtonStyle {
    var color: Color = SurvivorTheme.ember
    var isWide: Bool = true

    // A custom ButtonStyle gets NO disabled appearance for free, and this one
    // paints its own .white foreground, which defeats even the system's text
    // greying. So `.disabled(...)` used to change literally nothing: the
    // button sat there looking live while swallowing every tap. That is the
    // whole of "the rocks buttons are slow and need multiple taps" — you tap,
    // it goes inert without saying so, you tap again into the void. Every
    // Torch style already reads this; these two were the stragglers.
    @Environment(\.isEnabled) private var isEnabled

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
        // Liquid Glass is a material, not a View background, so on iOS 26 the
        // capsule has to carry its own hit area (same reason TorchGhostButton
        // does).
        .contentShape(Capsule())
        .saturation(isEnabled ? 1 : 0.5)
        .opacity(isEnabled ? 1 : 0.45)
        .accessibilityAddTraits(.isButton)
    }
}

struct SurvivorSecondaryButton: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

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
        .contentShape(Capsule())
        .saturation(isEnabled ? 1 : 0.5)
        .opacity(isEnabled ? 1 : 0.45)
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
