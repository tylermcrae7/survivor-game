import Foundation

@MainActor
@Observable
final class CardHandViewModel {
    var selectedCardIndex: Int?
    var showCardDetail = false

    private let gameClient: GameClient

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    var hand: [CardInstance] { gameClient.myPlayer?.hand ?? [] }
    var isMyTurn: Bool { gameClient.isMyTurn }

    var currentPhase: String {
        guard let state = gameClient.gameState else { return "" }
        switch state.phase {
        case .playing:
            if let pid = gameClient.playerId, let tp = state.turnPhase(for: pid) {
                return tp.rawValue
            }
            return "turn_play"
        case .tribalCouncil:
            return state.currentVote?.phase.rawValue ?? "tribal_council"
        default:
            return state.phase.rawValue
        }
    }

    func isPlayable(_ card: CardInstance, at index: Int) -> Bool {
        guard isMyTurn else { return false }
        guard let phases = card.playablePhases else { return false }
        return phases.contains(currentPhase)
    }

    func selectCard(at index: Int) {
        selectedCardIndex = index
        showCardDetail = true
    }

    var selectedCard: CardInstance? {
        guard let idx = selectedCardIndex, idx < hand.count else { return nil }
        return hand[idx]
    }
}
