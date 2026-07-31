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
    static func elimination() { notification(.warning) }
    static func winner() { notification(.success) }
    static func error() { notification(.error) }
    static func tribalStart() { impact(.heavy) }
}
