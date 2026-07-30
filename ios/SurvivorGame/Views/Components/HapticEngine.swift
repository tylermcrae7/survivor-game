import UIKit

/// Optimized haptic feedback engine with pre-prepared generators
/// Following Apple's best practices for haptic performance
@MainActor
enum HapticEngine {
    // Pre-created generators for better performance
    private static let impactLight = UIImpactFeedbackGenerator(style: .light)
    private static let impactMedium = UIImpactFeedbackGenerator(style: .medium)
    private static let impactHeavy = UIImpactFeedbackGenerator(style: .heavy)
    private static let notificationGenerator = UINotificationFeedbackGenerator()
    private static let selectionGenerator = UISelectionFeedbackGenerator()
    
    /// Prepare all haptic generators for immediate use
    /// Call this during app initialization for best performance
    nonisolated static func prepare() {
        Task { @MainActor in
            impactLight.prepare()
            impactMedium.prepare()
            impactHeavy.prepare()
            notificationGenerator.prepare()
            selectionGenerator.prepare()
        }
    }
    
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        switch style {
        case .light:
            impactLight.impactOccurred()
        case .medium:
            impactMedium.impactOccurred()
        case .heavy:
            impactHeavy.impactOccurred()
        @unknown default:
            impactMedium.impactOccurred()
        }
    }

    static func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        notificationGenerator.notificationOccurred(type)
    }

    static func selection() {
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
