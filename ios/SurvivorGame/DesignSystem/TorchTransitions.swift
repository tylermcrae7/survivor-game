import SwiftUI

// MARK: - Signature easing

extension Animation {
    /// The web's signature ease-out: cubic-bezier(0.22, 1, 0.36, 1).
    static func torchEaseOut(duration: Double) -> Animation {
        .timingCurve(0.22, 1, 0.36, 1, duration: duration)
    }
}

// MARK: - riseIn / fadeIn (web §riseIn / §fadeIn)

/// Content entering the light: fade up from below. riseIn travels 14pt
/// (screens 420ms torchEaseOut, modals 260ms ease); fadeIn travels 8pt
/// (toasts and soft entrances, 300ms ease).
struct RiseInTransition: Transition {
    var distance: CGFloat = 14

    func body(content: Content, phase: TransitionPhase) -> some View {
        content
            .opacity(phase.isIdentity ? 1 : 0)
            .offset(y: phase.isIdentity ? 0 : distance)
    }
}

extension Transition where Self == RiseInTransition {
    static var riseIn: RiseInTransition { RiseInTransition() }
    static var fadeIn: RiseInTransition { RiseInTransition(distance: 8) }
}

/// The screen-change stagger: children rise 420ms on the signature curve,
/// each index delayed 60ms (capped at the web's 240ms for children 5+).
struct StaggeredRise<C: View>: View {
    let index: Int
    @ViewBuilder var content: C
    @State private var shown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : 14)
            .onAppear {
                let duration = reduceMotion ? 0.001 : 0.42
                withAnimation(.torchEaseOut(duration: duration)
                    .delay(reduceMotion ? 0 : min(Double(index), 4) * 0.06)) { shown = true }
            }
    }
}

// MARK: - torchSnuff (web §torchSnuff — flare, then die to gray)

private struct SnuffValues {
    var flare = 0.0    // additive brightness for the flare-up
    var sat = 1.0
    var dim = 1.0      // multiplicative dim (CSS brightness(0.3)) via colorMultiply
    var scale = 1.0
    var opacity = 1.0
}

extension View {
    /// The elimination treatment: 1.6s — flare at 30%, then desaturate,
    /// dim to 30% white, shrink to 0.96 and settle at 45% opacity. The final
    /// keyframe state persists; callers then apply the permanent
    /// `.eliminated` styling. `delay` mirrors the web's inline
    /// animation-delay (e.g. 0.5 + ballotCount × 0.32 + 0.25).
    func torchSnuff(trigger: Int, delay: Double = 0) -> some View {
        modifier(TorchSnuffModifier(trigger: trigger, delay: delay))
    }
}

struct TorchSnuffModifier: ViewModifier {
    var trigger: Int
    var delay: Double = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        // Reduced motion keeps the end state (web forces 0.001s durations
        // so end handlers still fire); the motion itself vanishes.
        let f = reduceMotion ? 0.001 : 1.0
        let lead = max(delay * f, 0.0001)
        content.keyframeAnimator(initialValue: SnuffValues(), trigger: trigger) { view, s in
            view.brightness(s.flare)                     // additive flare (+0.15 ≈ CSS 1.4×)
                .saturation(s.sat)
                .colorMultiply(Color(white: s.dim))      // multiplicative, = CSS brightness(0.3)
                .scaleEffect(s.scale)
                .opacity(s.opacity)
        } keyframes: { _ in
            KeyframeTrack(\.flare) {
                LinearKeyframe(0.0, duration: lead)
                CubicKeyframe(0.15, duration: 0.48 * f)  // 30% of 1.6s
                CubicKeyframe(0.0, duration: 1.12 * f)
            }
            KeyframeTrack(\.sat) {
                LinearKeyframe(1.0, duration: lead)
                CubicKeyframe(1.3, duration: 0.48 * f)
                CubicKeyframe(0.0, duration: 1.12 * f)
            }
            KeyframeTrack(\.dim) {
                LinearKeyframe(1.0, duration: lead + 0.48 * f)
                CubicKeyframe(0.3, duration: 1.12 * f)
            }
            KeyframeTrack(\.scale) {
                LinearKeyframe(1.0, duration: lead)
                CubicKeyframe(1.02, duration: 0.48 * f)
                CubicKeyframe(0.96, duration: 1.12 * f)
            }
            KeyframeTrack(\.opacity) {
                LinearKeyframe(1.0, duration: lead + 0.48 * f)
                CubicKeyframe(0.45, duration: 1.12 * f)
            }
        }
    }
}

// MARK: - ballotFlip (web §ballotFlip — reading the votes)

private struct FlipValues {
    var rotX = 70.0
    var y = 18.0
    var opacity = 0.0
}

extension View {
    /// A parchment ballot flipping face-up: rotateX 70° → −8° overshoot → 0°
    /// over 560ms on the signature curve, each card delayed index × 320ms.
    /// Fires on appearance, like the web's results screen.
    func ballotFlip(index: Int) -> some View {
        modifier(BallotFlipModifier(index: index))
    }
}

struct BallotFlipModifier: ViewModifier {
    var index: Int
    @State private var flipped = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        let f = reduceMotion ? 0.001 : 1.0
        let lead = max(Double(index) * 0.32 * f, 0.0001)
        content
            .keyframeAnimator(initialValue: FlipValues(), trigger: flipped) { view, s in
                // CSS perspective(700px) on a ~340pt column ≈ 0.5.
                view.rotation3DEffect(.degrees(s.rotX), axis: (x: 1, y: 0, z: 0),
                                      anchor: .center, perspective: 0.5)
                    .offset(y: s.y)
                    .opacity(s.opacity)
            } keyframes: { _ in
                KeyframeTrack(\.rotX) {
                    LinearKeyframe(70, duration: lead)
                    CubicKeyframe(-8, duration: 0.336 * f)  // 60% of 0.56s — the overshoot
                    CubicKeyframe(0, duration: 0.224 * f)
                }
                KeyframeTrack(\.y) {
                    LinearKeyframe(18, duration: lead)
                    CubicKeyframe(0, duration: 0.336 * f)
                }
                KeyframeTrack(\.opacity) {
                    LinearKeyframe(0, duration: lead)
                    CubicKeyframe(1, duration: 0.336 * f)
                }
            }
            .onAppear { flipped = true }
    }
}

// MARK: - turnPulse / pulseHighlight (web §turnPulse / §pulseHighlight)

private struct PulseValues {
    var spread: CGFloat = 0
    var alpha = 0.0
}

/// A CSS box-shadow spread ring: a solid amber halo growing outward from the
/// shape's edge while fading. turnPulse runs twice (1.6s each, 22pt spread,
/// 55% start); pulseHighlight once (18pt, 70%, resolved by 0.7s + rest).
struct PulseRingModifier: ViewModifier {
    var trigger: Int
    var maxSpread: CGFloat = 22
    var startAlpha: Double = 0.55
    var cornerRadius: CGFloat = Torch.Radius.md
    var duration: Double = 1.6
    var secondPulse: Bool = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        let f = reduceMotion ? 0.001 : 1.0
        content.keyframeAnimator(initialValue: PulseValues(), trigger: trigger) { view, s in
            view.overlay(
                RoundedRectangle(cornerRadius: cornerRadius + s.spread / 2, style: .continuous)
                    .inset(by: -s.spread / 2)
                    .stroke(Torch.Color.torch.opacity(s.alpha), lineWidth: s.spread)
                    .allowsHitTesting(false)
            )
        } keyframes: { _ in
            // Second segment doubles as the single-pulse trailing rest.
            KeyframeTrack(\.spread) {
                MoveKeyframe(0)
                CubicKeyframe(maxSpread, duration: duration * f)
                MoveKeyframe(0)
                CubicKeyframe(secondPulse ? maxSpread : 0,
                              duration: (secondPulse ? duration : 0.3) * f)
            }
            KeyframeTrack(\.alpha) {
                MoveKeyframe(startAlpha)
                CubicKeyframe(0, duration: duration * f)
                MoveKeyframe(secondPulse ? startAlpha : 0)
                CubicKeyframe(0, duration: (secondPulse ? duration : 0.3) * f)
            }
        }
    }
}

extension View {
    /// "It's your turn" — the expanding amber ring, pulsed twice then still.
    func turnPulse(trigger: Int, cornerRadius: CGFloat = Torch.Radius.md) -> some View {
        modifier(PulseRingModifier(trigger: trigger, maxSpread: 22, startAlpha: 0.55,
                                   cornerRadius: cornerRadius, duration: 1.6,
                                   secondPulse: true))
    }

    /// One stronger attention ping (narrator `pulseElement` API).
    func pulseHighlight(trigger: Int, cornerRadius: CGFloat = Torch.Radius.md) -> some View {
        modifier(PulseRingModifier(trigger: trigger, maxSpread: 18, startAlpha: 0.7,
                                   cornerRadius: cornerRadius, duration: 0.7,
                                   secondPulse: false))
    }
}

// MARK: - stepGlow (web §stepGlow — breathing glow)

/// The smooth opacity breath (1 → 0.55 → 1). Web sites: active turn-step
/// pill 2.2s, reconnecting dot 0.8s, dramatic dots 1s.
struct StepGlowModifier: ViewModifier {
    var period: Double = 2.2
    @State private var dim = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        content
            .opacity(dim ? 0.55 : 1.0)
            .animation(reduceMotion ? nil
                : .easeInOut(duration: period / 2).repeatForever(autoreverses: true),
                value: dim)
            .onAppear { dim = true }
    }
}

extension View {
    func stepGlow(period: Double = 2.2) -> some View {
        modifier(StepGlowModifier(period: period))
    }
}

// MARK: - voteSlam (web §voteSlam — the vote card slammed on screen)

private struct SlamValues {
    var scale = 0.0
    var rot = -10.0
    var opacity = 0.0
}

/// The centered vote card: slams in with a spring overshoot, lingers, then
/// shrinks away — 1.5s total, removed via `onFinished`. Present as an
/// `.overlay` on the root, not a sheet. Fire `HapticEngine.voteSlam()` and
/// `TorchSound.play(.voteReveal)` alongside.
struct VoteSlamOverlay: View {
    let name: String
    var onFinished: () -> Void = {}
    @State private var go = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Text(name)
            .font(Torch.Font.display(38, weight: 900, soft: 60, italic: true))
            .foregroundStyle(Torch.Color.parchment)
            .padding(.vertical, 13)
            .padding(.horizontal, 26)
            .background(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .fill(Torch.Color.surfaceRaised
                        .shadow(.drop(color: .black.opacity(0.55), radius: 35, y: 24)) // --shadow-xl
                        .shadow(.drop(color: Torch.Color.torch.opacity(0.55), radius: 7))
                        .shadow(.drop(color: Torch.Color.torch.opacity(0.25), radius: 22)))
                        // ↑ --glow-torch-strong, composed on the fill so the
                        //   layers don't compound.
            )
            .overlay(
                RoundedRectangle(cornerRadius: Torch.Radius.md, style: .continuous)
                    .strokeBorder(Torch.Color.torch, lineWidth: 1)
            )
            .keyframeAnimator(initialValue: SlamValues(), trigger: go) { view, s in
                view.scaleEffect(s.scale)
                    .rotationEffect(.degrees(s.rot))
                    .opacity(s.opacity)
            } keyframes: { _ in
                let f = reduceMotion ? 0.001 : 1.0
                KeyframeTrack(\.scale) {
                    SpringKeyframe(1.2, duration: 0.30 * f, spring: .snappy) // the slam
                    CubicKeyframe(1.0, duration: 0.30 * f)
                    CubicKeyframe(0.85, duration: 0.90 * f)
                }
                KeyframeTrack(\.rot) {
                    CubicKeyframe(5, duration: 0.30 * f)
                    CubicKeyframe(0, duration: 0.30 * f)
                    CubicKeyframe(0, duration: 0.90 * f)
                }
                KeyframeTrack(\.opacity) {
                    CubicKeyframe(1, duration: 0.30 * f)
                    CubicKeyframe(1, duration: 0.30 * f)
                    CubicKeyframe(0, duration: 0.90 * f)
                }
            }
            .onAppear {
                go = true
                Task {
                    try? await Task.sleep(for: .seconds(1.5))
                    onFinished()
                }
            }
            .allowsHitTesting(false)
    }
}
