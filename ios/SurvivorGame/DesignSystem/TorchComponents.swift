import SwiftUI

// MARK: - Buttons (web §Components .btn / .btn-secondary)

/// The glowing primary CTA — "carved, warm-lit". Small-caps ink label on the
/// three-stop flame gradient, top bevel, hairline border, torch glow that
/// drops while pressed. Feed lowercase label strings (SF small caps).
struct GlowButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        configuration.label
            .font(Torch.Font.label(Torch.TextSize.sm))
            .tracking(Torch.Track.label * Torch.TextSize.sm)
            .foregroundStyle(Torch.Color.ink)
            .frame(maxWidth: .infinity, minHeight: Torch.Spacing.touchTarget)
            .padding(.horizontal, 20)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(LinearGradient(stops: [
                        .init(color: Torch.Color.flame, location: 0),
                        .init(color: Torch.Color.torch, location: 0.55),
                        .init(color: Torch.Color.torchDeep, location: 1),
                    ], startPoint: .top, endPoint: .bottom)
                    // CSS `inset 0 1px 0 white@35%` bevel; @20% while pressed.
                    .shadow(.inner(color: .white.opacity(pressed ? 0.20 : 0.35), radius: 0, y: 1)))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(Torch.Color.torchBorder, lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.35), radius: 1, y: 1) // --shadow-sm
            .shadow(color: Torch.Color.torch.opacity(pressed || !isEnabled ? 0 : 0.35),
                    radius: 11) // --glow-torch, removed on press/disable
            .offset(y: pressed ? 1 : 0)
            .scaleEffect(pressed ? 0.99 : 1)
            .saturation(isEnabled ? 1 : 0.5)
            .opacity(isEnabled ? 1 : 0.45)
            .animation(.easeOut(duration: 0.12), value: pressed)
    }
}

/// The secondary button: parchment label on a raised→sunken surface gradient
/// with a strong hairline — quiet next to the glowing CTA.
struct TorchSecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        configuration.label
            .font(Torch.Font.label(Torch.TextSize.sm))
            .tracking(Torch.Track.label * Torch.TextSize.sm)
            .foregroundStyle(Torch.Color.parchment)
            .frame(maxWidth: .infinity, minHeight: Torch.Spacing.touchTarget)
            .padding(.horizontal, 20)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(LinearGradient(colors: [Torch.Color.surfaceRaised,
                                                  Torch.Color.surfaceSunken],
                                         startPoint: .top, endPoint: .bottom)
                    .shadow(.inner(color: .white.opacity(0.06), radius: 0, y: 1)))
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(pressed ? Torch.Color.torch.opacity(0.5) : Torch.Color.lineStrong,
                                  lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.35), radius: 1, y: 1) // --shadow-sm
            .offset(y: pressed ? 1 : 0)
            .scaleEffect(pressed ? 0.99 : 1)
            .saturation(isEnabled ? 1 : 0.5)
            .opacity(isEnabled ? 1 : 0.45)
            .animation(.easeOut(duration: 0.12), value: pressed)
    }
}

/// The ghost button (web `.btn-ghost`): transparent fill, 1px **dashed**
/// strong hairline, text-secondary label, no shadow — the quietest rung of
/// the ladder, for optional actions that shouldn't pull the eye.
struct TorchGhostButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let pressed = configuration.isPressed
        configuration.label
            .font(Torch.Font.label(Torch.TextSize.sm))
            .tracking(Torch.Track.label * Torch.TextSize.sm)
            .foregroundStyle(Torch.Color.textSecondary)
            .frame(maxWidth: .infinity, minHeight: Torch.Spacing.touchTarget)
            .padding(.horizontal, 20)
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(pressed ? Torch.Color.torch.opacity(0.5) : Torch.Color.lineStrong,
                                  style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
            )
            // Transparent fill, so the shape must carry the hit area itself.
            .contentShape(RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous))
            .offset(y: pressed ? 1 : 0)
            .scaleEffect(pressed ? 0.99 : 1)
            .saturation(isEnabled ? 1 : 0.5)
            .opacity(isEnabled ? 1 : 0.45)
            .animation(.easeOut(duration: 0.12), value: pressed)
    }
}

extension ButtonStyle where Self == GlowButtonStyle {
    /// The primary CTA.
    static var torchGlow: GlowButtonStyle { GlowButtonStyle() }
}

extension ButtonStyle where Self == TorchSecondaryButtonStyle {
    static var torchSecondary: TorchSecondaryButtonStyle { TorchSecondaryButtonStyle() }
}

extension ButtonStyle where Self == TorchGhostButtonStyle {
    static var torchGhost: TorchGhostButtonStyle { TorchGhostButtonStyle() }
}

// MARK: - Cards & panels (web §Components .panel / .card-button)

/// The two surface treatments of the design: the lit panel (radius 22,
/// subtle lit top edge, shadow-lg) and the layered card (radius 14, top
/// sheen, strong hairline, shadow-md).
struct TorchCardModifier: ViewModifier {
    enum Kind {
        /// `.panel` — gradient surface-raised → surface at 22%.
        case panel
        /// `.card-button` — white@4.5% sheen fading out by 30%.
        case card
    }

    var kind: Kind = .panel

    private var cornerRadius: CGFloat {
        kind == .panel ? Torch.Radius.xl : 14
    }

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content
            .background {
                switch kind {
                case .panel:
                    shape.fill(LinearGradient(stops: [
                        .init(color: Torch.Color.surfaceRaised, location: 0),
                        .init(color: Torch.Color.surface, location: 0.22),
                    ], startPoint: .top, endPoint: .bottom))
                case .card:
                    shape.fill(Torch.Color.surfaceRaised)
                        .overlay(shape.fill(LinearGradient(stops: [
                            .init(color: .white.opacity(0.045), location: 0),
                            .init(color: .clear, location: 0.30),
                        ], startPoint: .top, endPoint: .bottom)))
                }
            }
            .overlay(shape.strokeBorder(kind == .panel ? Torch.Color.line : Torch.Color.lineStrong,
                                        lineWidth: 1))
            // One shadow/opacity target so a faded card doesn't ghost layers.
            .compositingGroup()
            .shadow(color: .black.opacity(kind == .panel ? 0.50 : 0.40),
                    radius: kind == .panel ? 20 : 9,
                    y: kind == .panel ? 14 : 6) // --shadow-lg / --shadow-md
    }
}

extension View {
    /// The lit-panel (default) or layered-card surface treatment.
    func torchCard(_ kind: TorchCardModifier.Kind = .panel) -> some View {
        modifier(TorchCardModifier(kind: kind))
    }
}

// MARK: - Wordmark (web §Start screen hero)

/// The ceremonial wordmark: the flickering flame mark over the Fraunces
/// title, with a small-caps tagline flanked by fading rules.
struct TorchWordmark: View {
    var subtitle: String = "The Tribe Has Spoken"

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "flame.fill")
                .font(.system(size: 44))
                .foregroundStyle(Torch.Color.torch)
                .flameFlicker(glowRadius: 7, glowOpacity: 0.7)
            Text("Survivor")
                .font(Torch.Font.display(Torch.TextSize.displayXL, weight: 900, soft: 30,
                                         relativeTo: .largeTitle))
                .foregroundStyle(Torch.Color.parchment)
                .shadow(color: Torch.Color.torch.opacity(0.35), radius: 30)
                .shadow(color: .black.opacity(0.7), radius: 15, y: 4)
            HStack(spacing: 10) {
                taglineRule(fadeIn: true)
                Text(subtitle)
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.wide * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)
                taglineRule(fadeIn: false)
            }
        }
        .multilineTextAlignment(.center)
    }

    private func taglineRule(fadeIn: Bool) -> some View {
        LinearGradient(colors: fadeIn ? [.clear, Torch.Color.torch.opacity(0.5)]
                                      : [Torch.Color.torch.opacity(0.5), .clear],
                       startPoint: .leading, endPoint: .trailing)
            .frame(width: 38, height: 1)
    }
}

// MARK: - Inputs (web §Components .form-input)

/// The sunken-well input chrome: `--surface-sunken` fill, strong hairline,
/// radius 10, 48pt minimum height, torch caret. Focus swaps the hairline to
/// torch and lights `--glow-torch`. Font, tracking and alignment stay with
/// the call site — the game-code, access-gate and name fields each differ.
struct TorchFieldModifier: ViewModifier {
    var focused: Bool = false

    func body(content: Content) -> some View {
        content
            .textFieldStyle(.plain)
            .foregroundStyle(Torch.Color.text)
            .tint(Torch.Color.torch) // caret-color: torch
            .frame(minHeight: Torch.Spacing.touchTarget)
            .padding(.horizontal, 14)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(Torch.Color.surfaceSunken)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(focused ? Torch.Color.torch : Torch.Color.lineStrong,
                                  lineWidth: 1)
            )
            .torchGlow(focused ? 0.35 : 0)
    }
}

extension View {
    /// The sunken-well input treatment; pass the field's focus state to get
    /// the torch focus border and glow.
    func torchField(focused: Bool = false) -> some View {
        modifier(TorchFieldModifier(focused: focused))
    }
}
