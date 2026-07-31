import SwiftUI

// MARK: - Torch Flicker (web §torchFlicker)

/// Keyframe values for the living-flame flicker.
private struct FlickerValues {
    var opacity = 1.0
    var scale = 1.0
}

/// Irregular opacity dips with a tiny scale wobble — candle flicker, not a
/// metronome. The amber glow flickers with the opacity. Web sites/durations:
/// header torch 3.2s, wordmark 3.2s, ceremony icon 2.6s, life torches 3.0s
/// (desync neighbors with slightly different periods), banner 2.4s.
struct FlameFlickerModifier: ViewModifier {
    /// Full flicker cycle in seconds.
    var period: Double = 3.2
    /// Glow blur radius (CSS drop-shadow blur ÷ 2: header 6px → 3).
    var glowRadius: CGFloat = 3
    /// Glow opacity at full flame (CSS torch@60–70%).
    var glowOpacity: Double = 0.6

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        if reduceMotion {
            // Ambient loops are removed entirely under reduced motion.
            content.shadow(color: Torch.Color.torch.opacity(glowOpacity), radius: glowRadius)
        } else {
            content.keyframeAnimator(initialValue: FlickerValues(),
                                     repeating: scenePhase == .active) { view, v in
                view.opacity(v.opacity)
                    .scaleEffect(v.scale)
                    .shadow(color: Torch.Color.torch.opacity(glowOpacity * v.opacity),
                            radius: glowRadius)
            } keyframes: { _ in
                // CSS keyframes at 0/18/42/50/74/100% of the cycle.
                KeyframeTrack(\.opacity) {
                    CubicKeyframe(0.86, duration: period * 0.18)
                    CubicKeyframe(0.96, duration: period * 0.24)
                    CubicKeyframe(0.78, duration: period * 0.08)
                    CubicKeyframe(0.94, duration: period * 0.24)
                    CubicKeyframe(1.00, duration: period * 0.26)
                }
                KeyframeTrack(\.scale) {
                    CubicKeyframe(1.000, duration: period * 0.18)
                    CubicKeyframe(1.030, duration: period * 0.24)
                    CubicKeyframe(0.985, duration: period * 0.08)
                    CubicKeyframe(1.000, duration: period * 0.50)
                }
            }
        }
    }
}

// MARK: - Ember Field (web §emberFloat / §confettiFall — one shared engine)

/// One Canvas-driven particle field with two configs: ambient embers rising
/// off the torchlight, and the 150-piece victory confetti drop. Pauses when
/// the scene is inactive; hidden entirely under reduced motion.
struct EmberFieldView: View {
    enum Style {
        /// ~14 embers drifting up from the torchlight, looping. Additive
        /// blend so they read as light, not paint.
        case embers
        /// 150 ember/gold slips falling with spin, one-shot over ~7s
        /// (max delay 3s + max duration 4s), then the timeline pauses.
        case confetti
    }

    private struct Particle {
        let x: CGFloat        // horizontal seat, 0–1
        let duration: Double  // seconds per travel
        let phase: Double     // embers: loop phase 0–1; confetti: delay 0–3s
        let radius: CGFloat   // embers only
        let color: Color
    }

    let style: Style
    private let start = Date()
    @State private var particles: [Particle]
    @State private var finished = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    init(style: Style = .embers) {
        self.style = style
        _particles = State(initialValue: Self.seed(style))
    }

    var body: some View {
        if reduceMotion {
            EmptyView()
        } else {
            TimelineView(.animation(minimumInterval: style == .embers ? 1.0 / 30.0 : 1.0 / 60.0,
                                    paused: scenePhase != .active || finished)) { timeline in
                Canvas { context, size in
                    switch style {
                    case .embers: drawEmbers(context, size: size, date: timeline.date)
                    case .confetti: drawConfetti(context, size: size, date: timeline.date)
                    }
                }
            }
            .blendMode(style == .embers ? .plusLighter : .normal)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
            .task {
                // Confetti container is removed after ~6s on the web; here the
                // one-shot timeline simply stops redrawing once all pieces land.
                guard style == .confetti else { return }
                try? await Task.sleep(for: .seconds(7))
                finished = true
            }
        }
    }

    private static func seed(_ style: Style) -> [Particle] {
        switch style {
        case .embers:
            return (0..<14).map { _ in
                Particle(x: .random(in: 0.28...0.72), duration: .random(in: 5...9),
                         phase: .random(in: 0...1), radius: .random(in: 1.5...3),
                         color: Torch.Color.flame)
            }
        case .confetti:
            return (0..<150).map { _ in
                Particle(x: .random(in: 0...1), duration: .random(in: 2...4),
                         phase: .random(in: 0...3), radius: 0,
                         color: Torch.Color.emberConfetti.randomElement() ?? Torch.Color.torch)
            }
        }
    }

    /// emberFloat: rise 46% of the field, drift 6% sideways, shrink to 0.4×.
    private func drawEmbers(_ context: GraphicsContext, size: CGSize, date: Date) {
        let now = date.timeIntervalSinceReferenceDate
        for p in particles {
            let t = ((now / p.duration) + p.phase).truncatingRemainder(dividingBy: 1)
            let y = size.height * 0.08 - CGFloat(t) * size.height * 0.46
            let x = p.x * size.width + CGFloat(t) * size.width * 0.06
            let k = 1 - 0.6 * CGFloat(t)
            var layer = context
            layer.opacity = 0.9 * (1 - t)
            layer.fill(Path(ellipseIn: CGRect(x: x, y: y, width: p.radius * k, height: p.radius * k)),
                       with: .color(p.color))
        }
    }

    /// confettiFall: -4vh → 104vh with 680° of spin, ease-in, fading out.
    private func drawConfetti(_ context: GraphicsContext, size: CGSize, date: Date) {
        let now = date.timeIntervalSince(start)
        for p in particles {
            let t = (now - p.phase) / p.duration
            guard t > 0, t < 1 else { continue }
            let eased = t * t // CSS ease-in
            let y = (-0.04 + 1.08 * eased) * size.height
            context.drawLayer { layer in
                layer.translateBy(x: p.x * size.width, y: y)
                layer.rotate(by: .degrees(680 * eased))
                layer.opacity = 1 - t
                layer.fill(Path(roundedRect: CGRect(x: -4.5, y: -7, width: 9, height: 14),
                                cornerRadius: 2),
                           with: .color(p.color))
            }
        }
    }
}

// MARK: - Glow helpers

extension View {
    /// The torch flicker treatment for flame-colored icons.
    func flameFlicker(period: Double = 3.2, glowRadius: CGFloat = 3,
                      glowOpacity: Double = 0.6) -> some View {
        modifier(FlameFlickerModifier(period: period, glowRadius: glowRadius,
                                      glowOpacity: glowOpacity))
    }

    /// `--glow-torch`: 0 0 22px torch@35% → radius 11 (CSS blur ÷ 2).
    func torchGlow(_ opacity: Double = 0.35, radius: CGFloat = 11) -> some View {
        shadow(color: Torch.Color.torch.opacity(opacity), radius: radius)
    }
}
