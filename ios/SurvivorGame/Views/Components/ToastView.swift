import SwiftUI

/// A single line of narration, in the show's voice.
struct ToastView: View {
    let message: String
    let type: ToastType

    enum ToastType {
        case narration, info, success, warning, error

        var color: Color {
            switch self {
            case .narration: Torch.Color.torch
            case .info: Torch.Color.textSecondary
            case .success: Torch.Color.success
            case .warning: Torch.Color.warning
            case .error: Torch.Color.danger
            }
        }

        var icon: String? {
            switch self {
            case .narration: nil          // the narrator doesn't need a badge
            case .info: "info.circle.fill"
            case .success: "checkmark.circle.fill"
            case .warning: "exclamationmark.triangle.fill"
            case .error: "xmark.circle.fill"
            }
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            if let icon = type.icon {
                Image(systemName: icon)
                    .foregroundStyle(type.color)
                    .accessibilityHidden(true)
            }
            Text(message)
                .font(type == .narration
                      ? Torch.Font.display(Torch.TextSize.sm, weight: 500, italic: true)
                      : Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.parchment)
                .multilineTextAlignment(type == .narration ? .center : .leading)
                // Narration is a ticker, not a paragraph. One line keeps the
                // strip a fixed height — a two-line line made the reserved
                // space jump mid-burst, which shifts every control on the
                // screen underneath it. Long card names shrink rather than
                // wrap.
                .lineLimit(type == .narration ? 1 : nil)
                .minimumScaleFactor(type == .narration ? 0.7 : 1)
                .fixedSize(horizontal: false, vertical: type != .narration)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            Capsule().fill(Torch.Color.surfaceRaised)
        )
        .overlay(
            Capsule().strokeBorder(type.color.opacity(0.35), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.45), radius: 12, y: 6)
    }
}

/// Mounts the narration toast above every screen.
///
/// Hit testing is off, always: a full-width strip floating over the game is a
/// perfect way to eat the tap the player meant for a button underneath, and
/// swallowed taps are a bug this app has already had once.
struct NarrationHost: ViewModifier {
    @Environment(NarrationFeed.self) private var narration
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        // An overlay, pinned to the very top of the safe area — and emphatically
        // NOT a safeAreaInset.
        //
        // Reserving space seemed tidier (the narrator can never hide the game)
        // but it moves every control on the screen down and back on each line,
        // and a tap aimed at a stepper during that animation lands somewhere
        // else. That is the same defect as the rocks buttons: things must not
        // move under a finger. Better to briefly cover something than to shift
        // everything.
        //
        // Trailing-aligned rather than centered, because centered sliced
        // straight through the camp's FIRE pill (found live: four repro
        // screenshots, a colored capsule cutting off the game code's last
        // digit mid-stroke — that reads as broken chrome, not as "briefly
        // covered"). The toast hugs its own content rather than stretching
        // full width, so pinning it to the trailing edge instead moves it
        // clear of the FIRE pill on the camp screen and clear of the
        // centered "Tribal Council" title on the council screen, at the one
        // vertical position that still clears both without an offset that
        // has to be tuned per screen. It can still graze the scroll/menu
        // icons at the far trailing edge for a long line — the quietest
        // casualty on either bar, and rare since narration text shrinks
        // before it grows past half the screen.
        content.overlay(alignment: .topTrailing) {
            if let event = narration.current {
                ToastView(message: event.message, type: .narration)
                    .padding(.horizontal, 20)
                    .transition(reduceMotion
                                ? .opacity
                                : .move(edge: .top).combined(with: .opacity))
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)   // announced instead, below
                    .id(event.message)
            }
        }
        .animation(reduceMotion ? .none : .torchEaseOut(duration: 0.26),
                   value: narration.current)
        .onChange(of: narration.current) { _, new in
            guard let new else { return }
            AccessibilityNotification.Announcement(new.message).post()
        }
    }
}

extension View {
    func narrationHost() -> some View { modifier(NarrationHost()) }
}
