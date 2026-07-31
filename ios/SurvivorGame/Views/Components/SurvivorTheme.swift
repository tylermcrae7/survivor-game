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

/// A capsule chip like the web header's FIRE code / player chips.
/// Liquid Glass on iOS 26, thin material earlier.
struct SurvivorChip<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        let inner = HStack(spacing: 6) { content }
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

        if #available(iOS 26.0, *) {
            inner.glassEffect(.regular, in: Capsule())
        } else {
            inner
                .background(.ultraThinMaterial)
                .clipShape(Capsule())
        }
    }
}

/// Torch lives, exactly like the web's player rows: one lit flame per
/// remaining Survivor Character Card, dimmed once spent.
struct TorchLivesView: View {
    let lives: Int
    let total: Int

    init(lives: Int, total: Int = 2) {
        self.lives = lives
        self.total = total
    }

    var body: some View {
        HStack(spacing: 2) {
            ForEach(0..<total, id: \.self) { index in
                Image(systemName: "flame.fill")
                    .font(.caption2)
                    .foregroundStyle(index < lives
                        ? SurvivorTheme.ember
                        : Color.secondary.opacity(0.3))
            }
        }
        .accessibilityLabel("\(lives) of \(total) torches lit")
    }
}

/// "Your torch burns" — the Steal → Play → Draw strip from the web app.
struct TurnPhaseTracker: View {
    let phase: TurnPhase

    private let steps: [(TurnPhase, String)] = [
        (.steal, "Steal"), (.play, "Play"), (.draw, "Draw"),
    ]

    private func stepState(_ step: TurnPhase) -> Int {
        // -1 done, 0 active, 1 upcoming
        let order: [TurnPhase] = [.steal, .play, .draw]
        guard let current = order.firstIndex(of: phase == .done ? .draw : phase),
              let mine = order.firstIndex(of: step) else { return 1 }
        if phase == .done { return -1 }
        return mine < current ? -1 : (mine == current ? 0 : 1)
    }

    var body: some View {
        VStack(spacing: 8) {
            Text("Your torch burns")
                .font(.title3.weight(.black))
                .fontDesign(.serif)
                .foregroundStyle(SurvivorTheme.flame)

            HStack(spacing: 10) {
                ForEach(steps, id: \.1) { step, label in
                    let state = stepState(step)
                    Text(label.uppercased())
                        .font(.caption2.weight(.bold))
                        .tracking(1.5)
                        .strikethrough(state == -1)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(
                            Capsule().fill(state == 0
                                ? SurvivorTheme.ember
                                : Color.clear)
                        )
                        .foregroundStyle(state == 0 ? .black
                            : (state == -1 ? .secondary : Color.secondary.opacity(0.7)))
                    if label != "Draw" {
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(SurvivorTheme.inkRaised.opacity(0.8))
                .overlay(RoundedRectangle(cornerRadius: 16)
                    .stroke(SurvivorTheme.ember.opacity(0.35), lineWidth: 1))
        )
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
