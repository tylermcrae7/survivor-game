import SwiftUI

/// The torchlit look — the native twin of the web app's palette: deep ink
/// greens, ember orange, parchment text, serif ceremony headers.
enum SurvivorTheme {
    /// Ember orange — the accent everywhere (web --primary/--torch family).
    static let ember = Color(hex: "#E8862A") ?? .orange
    static let flame = Color(hex: "#F2A65A") ?? .orange
    /// Deep ink-green backgrounds (web #141d1a family).
    static let ink = Color(hex: "#101714") ?? .black
    static let inkRaised = Color(hex: "#18211D") ?? Color(.systemGray6)
    static let parchment = Color(hex: "#EFE6D8") ?? .primary

    /// The ambient screen background: a slow ember glow over deep ink.
    struct Background: View {
        var body: some View {
            ZStack {
                SurvivorTheme.ink.ignoresSafeArea()
                RadialGradient(
                    colors: [SurvivorTheme.ember.opacity(0.16), .clear],
                    center: .top, startRadius: 10, endRadius: 420
                )
                .ignoresSafeArea()
            }
        }
    }
}

extension View {
    /// Torchlit screen treatment: ink background, dark scheme, ember tint.
    func survivorScreen() -> some View {
        self
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(SurvivorTheme.Background())
    }
}

/// The ceremonial wordmark used on the start screen and big moments.
struct SurvivorWordmark: View {
    var subtitle: String = "The Tribe Has Spoken"

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: "flame.fill")
                .font(.system(size: 54))
                .foregroundStyle(
                    LinearGradient(colors: [SurvivorTheme.flame, SurvivorTheme.ember],
                                   startPoint: .top, endPoint: .bottom))
                .shadow(color: SurvivorTheme.ember.opacity(0.55), radius: 18)
            Text("Survivor")
                .font(.system(size: 44, weight: .black, design: .serif))
            Text(subtitle.uppercased())
                .font(.caption.weight(.semibold))
                .tracking(3.5)
                .foregroundStyle(.secondary)
        }
    }
}
