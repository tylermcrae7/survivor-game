import Foundation

@MainActor
@Observable
final class FinalTribalViewModel {
    var error: ViewModelError?
    var isPerformingAction = false

    private let gameClient: GameClient

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    // MARK: - Computed

    var gameState: GameState? { gameClient.gameState }
    var finalTribal: FinalTribalState? { gameState?.finalTribal }
    var phase: FinalTribalPhase { finalTribal?.phase ?? .waiting }
    var myPlayerId: String? { gameClient.playerId }

    var isJuryMember: Bool { gameClient.isJuryMember }
    var isFinalist: Bool { gameClient.isFinalist }
    var isCouncilLeader: Bool { gameClient.isCouncilLeader }

    var finalists: [PlayerState] {
        (finalTribal?.finalists ?? []).compactMap { gameState?.players[$0] }
    }

    var juryMembers: [PlayerState] {
        (gameState?.jury ?? []).compactMap { gameState?.players[$0] }
    }

    var juryReady: Set<String> {
        Set(finalTribal?.juryReady ?? [])
    }

    var voteCounts: [String: Int] {
        finalTribal?.voteCounts ?? [:]
    }

    var hasVoted: Bool {
        guard let myId = myPlayerId, let votes = finalTribal?.votes else { return false }
        return votes[myId] != nil
    }

    var isReady: Bool {
        guard let myId = myPlayerId else { return false }
        return juryReady.contains(myId)
    }

    var winner: PlayerState? {
        guard let winnerId = finalTribal?.winner ?? gameState?.winner else { return nil }
        return gameState?.players[winnerId]
    }

    var tieBreakNeeded: Bool { finalTribal?.tieBreakNeeded ?? false }

    var tiedFinalists: [PlayerState] {
        (finalTribal?.tiedFinalists ?? []).compactMap { gameState?.players[$0] }
    }

    // MARK: - Actions

    func advancePhase(to phase: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.advanceFinal(to: phase)
        } catch {
            self.error = .from(error)
        }
    }

    func signalReady() async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.signalReady()
        } catch {
            self.error = .from(error)
        }
    }

    func castVote(for finalistId: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.castFinalVote(finalistId: finalistId)
        } catch {
            self.error = .from(error)
        }
    }

    func breakTie(chosenWinner: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.finalTieBreak(chosenWinner: chosenWinner)
        } catch {
            self.error = .from(error)
        }
    }

    func finishGame(winnerId: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        guard let gameId = gameClient.gameId else { return }
        do {
            let response = try await gameClient.apiClient.finishGame(gameId: gameId, winnerId: winnerId)
            if !response.success {
                self.error = .gameError(response.message ?? "Failed to finish game")
            }
        } catch {
            self.error = .from(error)
        }
    }
}
