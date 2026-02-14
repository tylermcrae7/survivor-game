import SwiftUI

// MARK: - Card Play Animation

struct CardPlayEffect: ViewModifier {
    let isPlaying: Bool

    func body(content: Content) -> some View {
        content
            .scaleEffect(isPlaying ? 0.1 : 1.0)
            .opacity(isPlaying ? 0 : 1)
            .offset(y: isPlaying ? -100 : 0)
            .animation(.easeIn(duration: 0.3), value: isPlaying)
    }
}

// MARK: - Card Draw Animation

struct CardDrawEffect: ViewModifier {
    let isDrawing: Bool

    func body(content: Content) -> some View {
        content
            .scaleEffect(isDrawing ? 1.1 : 1.0)
            .opacity(isDrawing ? 0.5 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: isDrawing)
    }
}

// MARK: - Steal Animation

struct StealEffect: ViewModifier {
    let isStealing: Bool

    func body(content: Content) -> some View {
        content
            .rotationEffect(.degrees(isStealing ? -5 : 0))
            .offset(x: isStealing ? -20 : 0)
            .animation(.easeInOut(duration: 0.2).repeatCount(3, autoreverses: true), value: isStealing)
    }
}

extension View {
    func cardPlayEffect(_ isPlaying: Bool) -> some View {
        modifier(CardPlayEffect(isPlaying: isPlaying))
    }

    func cardDrawEffect(_ isDrawing: Bool) -> some View {
        modifier(CardDrawEffect(isDrawing: isDrawing))
    }

    func stealEffect(_ isStealing: Bool) -> some View {
        modifier(StealEffect(isStealing: isStealing))
    }
}
