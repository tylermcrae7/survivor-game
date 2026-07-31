import CoreHaptics
import UIKit

/// Optimized haptic feedback engine with pre-prepared generators
/// Following Apple's best practices for haptic performance
@MainActor
enum HapticEngine {
    // Pre-created generators for better performance
    private static let impactLight = UIImpactFeedbackGenerator(style: .light)
    private static let impactMedium = UIImpactFeedbackGenerator(style: .medium)
    private static let impactHeavy = UIImpactFeedbackGenerator(style: .heavy)
    private static let impactSoft = UIImpactFeedbackGenerator(style: .soft)
    private static let impactRigid = UIImpactFeedbackGenerator(style: .rigid)
    private static let notificationGenerator = UINotificationFeedbackGenerator()
    private static let selectionGenerator = UISelectionFeedbackGenerator()
    
    /// Prepare all haptic generators for immediate use
    /// Call this during app initialization for best performance
    nonisolated static func prepare() {
        Task { @MainActor in
            impactLight.prepare()
            impactMedium.prepare()
            impactHeavy.prepare()
            impactSoft.prepare()
            impactRigid.prepare()
            notificationGenerator.prepare()
            selectionGenerator.prepare()
        }
    }
    
    static var isEnabled: Bool {
        UserDefaults.standard.object(forKey: "hapticsEnabled") as? Bool ?? true
    }

    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        guard isEnabled else { return }
        switch style {
        case .light:
            impactLight.impactOccurred()
        case .medium:
            impactMedium.impactOccurred()
        case .heavy:
            impactHeavy.impactOccurred()
        case .soft:
            impactSoft.impactOccurred()
        case .rigid:
            impactRigid.impactOccurred()
        @unknown default:
            impactMedium.impactOccurred()
        }
    }

    static func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        guard isEnabled else { return }
        notificationGenerator.notificationOccurred(type)
    }

    static func selection() {
        guard isEnabled else { return }
        selectionGenerator.selectionChanged()
    }

    // Game-specific haptics
    static func cardPlay() { impact(.medium) }
    static func cardDraw() { impact(.light) }
    static func steal() { impact(.heavy) }
    static func vote() { impact(.medium) }
    static func elimination() { torchSnuff() }
    static func error() { notification(.error) }
    static func tribalStart() { impact(.heavy) }

    // MARK: - Ceremony patterns (Core Haptics, generator fallbacks)

    private static let supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics
    private static var patternEngine: CHHapticEngine?

    /// Lazily create + start the pattern engine. Safe to call on every play.
    private static func liveEngine() -> CHHapticEngine? {
        guard supportsHaptics else { return nil }
        if let engine = patternEngine { return engine }
        guard let engine = try? CHHapticEngine() else { return nil }
        engine.playsHapticsOnly = true      // never touches TorchSound's AVAudioSession
        engine.isAutoShutdownEnabled = true // powers down idle, restarts on demand
        engine.resetHandler = { [weak engine] in try? engine?.start() }
        engine.stoppedHandler = { [weak engine] _ in
            Task { @MainActor in
                // Only clear our own registration — a late stop from a
                // superseded engine must not kill its replacement.
                if patternEngine === engine { patternEngine = nil }
            }
        }
        try? engine.start()
        patternEngine = engine
        return engine
    }

    /// One entry point; every ceremony pattern routes through it.
    private static func playPattern(_ make: () throws -> CHHapticPattern,
                                    fallback: () -> Void) {
        guard isEnabled else { return }
        guard let engine = liveEngine(),
              let pattern = try? make(),
              let player = try? engine.makePlayer(with: pattern) else {
            fallback()
            return
        }
        try? player.start(atTime: CHHapticTimeImmediate)
    }

    /// The vote card hitting the screen: sharp strike, low rumble tail,
    /// softer rebound thud as it settles.
    static func voteSlam() {
        playPattern(voteSlamPattern, fallback: { impact(.heavy) })
    }

    /// The torch dying: a 1.4s rumble that flares at 0.12s, then falls with
    /// sharpness sweeping 0.60 → 0.05 — the audio cue's lowpass sweep, felt.
    static func torchSnuff() {
        playPattern(torchSnuffPattern, fallback: { notification(.warning) })
    }

    /// "It's your turn" — two soft swells on the ring's 1.6s grid.
    static func turnPulse() {
        playPattern(turnPulsePattern, fallback: { impact(.soft) })
    }

    /// Success/unlock ("come ashore"): a rising three-tap that opens up.
    static func unlock() {
        playPattern(unlockPattern, fallback: { notification(.success) })
    }

    /// Winner fanfare: four transients on the victory arpeggio grid over a
    /// swelling shimmer under the confetti drop.
    static func winner() {
        playPattern(winnerPattern, fallback: { notification(.success) })
    }

    // Pattern builders are internal so tests can compile each one.

    static func voteSlamPattern() throws -> CHHapticPattern {
        try CHHapticPattern(events: [
            // The strike.
            CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 1.00),
                .init(parameterID: .hapticSharpness, value: 0.90),
            ], relativeTime: 0),
            // Low rumble tail under the overshoot.
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.80),
                .init(parameterID: .hapticSharpness, value: 0.25),
            ], relativeTime: 0.01, duration: 0.16),
            // Rebound thud as it settles to scale 1.0.
            CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.55),
                .init(parameterID: .hapticSharpness, value: 0.20),
            ], relativeTime: 0.10),
        ], parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 1.0),
                .init(relativeTime: 0.17, value: 0.0),
            ], relativeTime: 0),
        ])
    }

    static func torchSnuffPattern() throws -> CHHapticPattern {
        try CHHapticPattern(events: [
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.60),
                .init(parameterID: .hapticSharpness, value: 0.60),
            ], relativeTime: 0, duration: 1.4),
        ], parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.55), // fire steady
                .init(relativeTime: 0.12, value: 0.85), // flare
                .init(relativeTime: 0.40, value: 0.45),
                .init(relativeTime: 1.40, value: 0.00), // out
            ], relativeTime: 0),
            CHHapticParameterCurve(parameterID: .hapticSharpnessControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.60),
                .init(relativeTime: 1.40, value: 0.05), // 3000Hz → 200Hz, felt
            ], relativeTime: 0),
        ])
    }

    static func turnPulsePattern() throws -> CHHapticPattern {
        try CHHapticPattern(events: (0..<2).map { i in
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.42),
                .init(parameterID: .hapticSharpness, value: 0.15),
            ], relativeTime: Double(i) * 1.6, duration: 0.22)
        }, parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.0), // swell in, not a tap
                .init(relativeTime: 0.09, value: 1.0),
                .init(relativeTime: 0.22, value: 0.0),
            ], relativeTime: 0),
        ])
    }

    static func unlockPattern() throws -> CHHapticPattern {
        let steps: [(Double, Float, Float)] = [
            (0.00, 0.40, 0.30),
            (0.10, 0.60, 0.50),
            (0.22, 0.95, 0.70),
        ]
        return try CHHapticPattern(events: steps.map { time, intensity, sharpness in
            CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: intensity),
                .init(parameterID: .hapticSharpness, value: sharpness),
            ], relativeTime: time)
        }, parameters: [])
    }

    static func winnerPattern() throws -> CHHapticPattern {
        var events: [CHHapticEvent] = [
            CHHapticEvent(eventType: .hapticContinuous, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.45),
                .init(parameterID: .hapticSharpness, value: 0.85),
            ], relativeTime: 0, duration: 0.95),
        ]
        for (i, sharpness) in [Float(0.45), 0.55, 0.65, 0.80].enumerated() {
            events.append(CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 0.55 + Float(i) * 0.12),
                .init(parameterID: .hapticSharpness, value: sharpness),
            ], relativeTime: Double(i) * 0.15))
        }
        return try CHHapticPattern(events: events, parameterCurves: [
            CHHapticParameterCurve(parameterID: .hapticIntensityControl, controlPoints: [
                .init(relativeTime: 0.00, value: 0.20),
                .init(relativeTime: 0.45, value: 0.70),
                .init(relativeTime: 0.95, value: 0.00),
            ], relativeTime: 0),
        ])
    }
}
