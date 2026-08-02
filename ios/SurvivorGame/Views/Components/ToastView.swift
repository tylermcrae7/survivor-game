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
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
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
    @Environment(GameClient.self) private var gameClient
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content.overlay(alignment: .top) {
            if let event = gameClient.narration.current {
                ToastView(message: event.message, type: .narration)
                    .padding(.horizontal, 20)
                    .padding(.top, 8)
                    .transition(reduceMotion
                                ? .opacity
                                : .move(edge: .top).combined(with: .opacity))
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)   // announced instead, below
                    .id(event.message)
            }
        }
        .animation(reduceMotion ? .none : .torchEaseOut(duration: 0.26),
                   value: gameClient.narration.current)
        .onChange(of: gameClient.narration.current) { _, new in
            guard let new else { return }
            AccessibilityNotification.Announcement(new.message).post()
        }
    }
}

extension View {
    func narrationHost() -> some View { modifier(NarrationHost()) }
}
