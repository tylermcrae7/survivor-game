import Foundation

@MainActor
@Observable
final class PlayingViewModel {
    var error: ViewModelError?
    var isPerformingAction = false
    /// Kept apart from `isPerformingAction`: wandering off to the beach must
    /// not grey out the draw button mid-turn.
    var isMovingPlace = false
    var selectedStealTarget: String?
    var showStealPicker = false

    private let gameClient: GameClient

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    // MARK: - Computed

    var gameState: GameState? { gameClient.gameState }
    var myPlayer: PlayerState? { gameClient.myPlayer }
    var isMyTurn: Bool { gameClient.isMyTurn }
    var myPlayerId: String? { gameClient.playerId }

    var currentPlayer: PlayerState? { gameState?.currentPlayer }
    var currentPlayerName: String { currentPlayer?.name ?? "Unknown" }

    var turnPhase: TurnPhase? {
        guard let playerId = gameClient.playerId else { return nil }
        return gameState?.turnPhase(for: playerId)
    }

    var sortedPlayers: [PlayerState] { gameState?.sortedPlayers ?? [] }
    var activePlayers: [PlayerState] { gameState?.activePlayers ?? [] }

    var stealTargets: [PlayerState] {
        guard let myId = myPlayerId else { return [] }
        return activePlayers.filter { $0.id != myId && !$0.hand.isEmpty }
    }

    var canSteal: Bool { isMyTurn && turnPhase == .steal }
    var canPlay: Bool { isMyTurn && turnPhase == .play }
    var canDraw: Bool { isMyTurn }

    var myHand: [CardInstance] { myPlayer?.hand ?? [] }
    var deckCount: Int { gameState?.deckCount ?? 0 }

    // MARK: - Places

    /// Mine, not the table's. They differ once your torch is out: the living
    /// may wander, you are held at the fire. Falls back to the game-wide
    /// policy for a server that predates the per-player one.
    var placePolicy: PlacePolicy? {
        gameClient.myPlayer?.placePolicy ?? gameState?.placePolicy
    }
    var myPlace: String? { gameClient.myPlace }

    // MARK: - Actions

    func steal(targetId: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }

        do {
            try await gameClient.steal(targetId: targetId)
            showStealPicker = false
        } catch {
            self.error = .from(error)
        }
    }

    func playCard(at index: Int) async {
        isPerformingAction = true
        defer { isPerformingAction = false }

        do {
            _ = try await gameClient.playCard(at: index)
        } catch {
            self.error = .from(error)
        }
    }

    func drawCard() async {
        isPerformingAction = true
        // The defer-clear is only safe because GameClient.drawCard applies the
        // response's fresh state (hasDrawn flipped) before it returns — the
        // draw button re-enables against fresh flags, not the pre-draw ones,
        // so a fast double-tap can't slip a second draw through.
        defer { isPerformingAction = false }

        do {
            _ = try await gameClient.drawCard()
        } catch {
            self.error = .from(error)
        }
    }

    func moveToPlace(_ place: String) async {
        guard placePolicy?.canMove(to: place, from: myPlace) == true else { return }
        isMovingPlace = true
        defer { isMovingPlace = false }

        do {
            try await gameClient.moveToPlace(place)
            HapticEngine.selection()
        } catch {
            self.error = .from(error)
        }
    }

    func advanceTurn() async {
        isPerformingAction = true
        defer { isPerformingAction = false }

        do {
            try await gameClient.advanceTurn()
        } catch {
            self.error = .from(error)
        }
    }

    func playReactiveCard(at index: Int, theftContext: [String: Any]) async {
        isPerformingAction = true
        defer { isPerformingAction = false }

        do {
            // Safe to pass dictionary - immediately serialized to JSON in network layer
            nonisolated(unsafe) let context = theftContext
            try await gameClient.playReactiveCard(at: index, theftContext: context)
        } catch {
            self.error = .from(error)
        }
    }

    func completeTheft() async {
        isPerformingAction = true
        defer { isPerformingAction = false }

        do {
            try await gameClient.completeTheft()
        } catch {
            self.error = .from(error)
        }
    }
}
