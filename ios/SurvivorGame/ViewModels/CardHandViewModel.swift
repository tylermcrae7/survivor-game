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

    /// The hand, enriched through the card catalog — server hands are bare
    /// `{"type": …}` stubs and carry no name/category/phases of their own.
    var hand: [CardInstance] {
        (gameClient.myPlayer?.hand ?? []).map { CardCatalog.shared.resolve($0) }
    }

    var isMyTurn: Bool { gameClient.isMyTurn }

    /// The server's playability vocabulary for THIS player right now — the
    /// exact mirror of rules_engine.get_current_turn_phase:
    /// your own turn maps to turn_steal/turn_play/turn_draw/turn_done, tribal
    /// council maps announcement/advantage_play/discussion → tribal_discussion,
    /// voting → tribal_voting, immunity → tribal_immunity, reveal → waiting.
    var currentPhase: String {
        guard let state = gameClient.gameState else { return "waiting" }
        switch state.phase {
        case .playing:
            if let pid = gameClient.playerId, let tp = state.turnPhase(for: pid) {
                return tp.rawValue
            }
            return "waiting"
        case .tribalCouncil:
            switch state.currentVote?.phase ?? .waiting {
            case .announcement, .advantagePlay, .discussion:
                return "tribal_discussion"
            case .voting:
                return "tribal_voting"
            case .immunity:
                return "tribal_immunity"
            case .reveal, .waiting:
                return "waiting"
            }
        default:
            return "waiting"
        }
    }

    func isPlayable(_ card: CardInstance, at index: Int) -> Bool {
        guard !(gameClient.myPlayer?.isEliminated ?? true) else { return false }
        let resolved = CardCatalog.shared.resolve(card)
        guard let phases = resolved.playablePhases, !phases.isEmpty else { return false }
        let phase = currentPhase
        // Tribal windows are open to every survivor; turn phases only to the
        // player whose torch is lit.
        if phase.hasPrefix("turn_") && !isMyTurn { return false }
        return phases.contains(phase)
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
