import Foundation
import SwiftUI

@MainActor
@Observable
final class GameClient {
    // MARK: - Public State

    private(set) var gameState: GameState?
    private(set) var connectionState: ConnectionState = .disconnected
    private(set) var navigationState: NavigationState = .start
    private(set) var lastError: String?
    private(set) var isLoading = false

    var gameId: String?
    var playerId: String?
    var playerName: String?

    // MARK: - Private

    let apiClient: APIClient
    private let socketClient = SocketClient()
    private var stateListenerTask: Task<Void, Never>?
    private var eventListenerTask: Task<Void, Never>?
    private var connectionListenerTask: Task<Void, Never>?

    init(baseURL: URL) {
        self.apiClient = APIClient(baseURL: baseURL)
        startListening()
    }

    deinit {
        stateListenerTask?.cancel()
        eventListenerTask?.cancel()
        connectionListenerTask?.cancel()
    }

    // MARK: - Connection

    func connect() {
        socketClient.connect(to: apiClient.baseURL)
    }

    func disconnect() {
        socketClient.disconnect()
        connectionState = .disconnected
    }

    // Note: To change server URL, create a new GameClient via SurvivorGameApp
    // and pass it through the environment. The URL is set at init time.

    // MARK: - Game Lifecycle

    func createGame() async throws -> String {
        isLoading = true
        defer { isLoading = false }

        let response = try await apiClient.createGame()
        guard response.success else {
            throw GameClientError.operationFailed("Failed to create game")
        }
        self.gameId = response.gameId
        return response.gameId
    }

    func joinGame(gameId: String, name: String, color: String? = nil) async throws {
        isLoading = true
        defer { isLoading = false }

        let response = try await apiClient.joinGame(gameId: gameId, name: name, color: color)
        guard response.success else {
            throw GameClientError.operationFailed("Failed to join game")
        }

        self.gameId = gameId
        self.playerId = response.playerId
        self.playerName = name
        self.gameState = response.gameState
        updateNavigationState()

        // Connect socket and join room
        connect()
        socketClient.joinGame(gameId)
    }

    func rejoinGame(gameId: String, playerId: String) async throws {
        isLoading = true
        defer { isLoading = false }

        let response = try await apiClient.rejoinGame(gameId: gameId, playerId: playerId)
        guard response.success else {
            throw GameClientError.operationFailed("Failed to rejoin game")
        }

        self.gameId = gameId
        self.playerId = playerId
        self.playerName = response.playerName
        self.gameState = response.gameState
        updateNavigationState()

        connect()
        socketClient.joinGame(gameId)
    }

    func startGame() async throws {
        guard let gameId else { throw GameClientError.noGame }
        isLoading = true
        defer { isLoading = false }

        let response = try await apiClient.startGame(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Failed to start game")
        }
    }

    func resetGame() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.resetGame(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Failed to reset game")
        }
    }

    // MARK: - Turn Actions

    func steal(targetId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.steal(gameId: gameId, thiefId: playerId, targetId: targetId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Steal failed")
        }
    }

    func playCard(at index: Int) async throws -> PlayCardResponse {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        return try await apiClient.playCard(gameId: gameId, playerId: playerId, cardIdx: index)
    }

    func drawCard() async throws -> DrawResponse {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        return try await apiClient.draw(gameId: gameId, playerId: playerId)
    }

    func advanceTurn() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.advanceTurn(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Advance failed")
        }
    }

    // MARK: - Reactive

    func playReactiveCard(at index: Int, theftContext: [String: Any]) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.playReactiveCard(
            gameId: gameId, playerId: playerId, cardIdx: index, theftContext: theftContext
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Reactive play failed")
        }
    }

    func completeTheft() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.completeTheft(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Complete theft failed")
        }
    }

    // MARK: - Tribal Council

    func startVoting(type: String = "elimination") async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.startVoting(gameId: gameId, voteType: type)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Start voting failed")
        }
    }

    func castVote(targetId: String, count: Int = 1) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let votesData: [[String: Any]] = [["targetId": targetId, "count": count]]
        let response = try await apiClient.castVote(gameId: gameId, voterId: playerId, votesData: votesData)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast vote failed")
        }
    }

    func castVotes(votesData: [[String: Any]]) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.castVote(gameId: gameId, voterId: playerId, votesData: votesData)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast votes failed")
        }
    }

    func revealVotes() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.revealVotes(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Reveal votes failed")
        }
    }

    func resolveTieBreak(chosenId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.tieBreak(gameId: gameId, leaderId: playerId, chosenId: chosenId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Tie break failed")
        }
    }

    func completeTribal() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.completeTribial(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Complete tribal failed")
        }
    }

    func advanceTribal(to phase: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.advanceTribal(gameId: gameId, phase: phase)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Advance tribal failed")
        }
    }

    func playAdvantage(type: String, targetId: String? = nil) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.playAdvantage(
            gameId: gameId, playerId: playerId, advantageType: type, targetId: targetId
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Play advantage failed")
        }
    }

    func playImmunity() async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.playImmunity(gameId: gameId, playerId: playerId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Play immunity failed")
        }
    }

    func blockImmunity(targetId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.blockImmunity(gameId: gameId, playerId: playerId, targetId: targetId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Block immunity failed")
        }
    }

    func changeLeader(newLeaderId: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.changeLeader(gameId: gameId, newLeaderId: newLeaderId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Change leader failed")
        }
    }

    // MARK: - Final Tribal

    func advanceFinal(to phase: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.advanceFinal(gameId: gameId, phase: phase)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Advance final failed")
        }
    }

    func castFinalVote(finalistId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.castFinalVote(
            gameId: gameId, juryMemberId: playerId, finalistId: finalistId
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast final vote failed")
        }
    }

    func signalReady() async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.signalReady(gameId: gameId, juryMemberId: playerId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Signal ready failed")
        }
    }

    func finalTieBreak(chosenWinner: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.finalTieBreak(
            gameId: gameId, leaderId: playerId, chosenWinner: chosenWinner
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Final tie break failed")
        }
    }

    // MARK: - Session Management

    func leaveGame() {
        disconnect()
        gameState = nil
        gameId = nil
        playerId = nil
        playerName = nil
        navigationState = .start
        lastError = nil
    }

    // MARK: - Sync

    func syncState() async {
        guard let gameId else { return }
        do {
            let state = try await apiClient.getGameState(gameId: gameId)
            self.gameState = state
            updateNavigationState()
        } catch {
            print("[GameClient] Sync failed: \(error)")
        }
    }

    // MARK: - Private

    private func startListening() {
        stateListenerTask = Task { [weak self] in
            guard let self else { return }
            for await state in self.socketClient.gameStateStream {
                self.gameState = state
                self.updateNavigationState()
            }
        }

        eventListenerTask = Task { [weak self] in
            guard let self else { return }
            for await event in self.socketClient.gameEventStream {
                self.handleEvent(event)
            }
        }

        connectionListenerTask = Task { [weak self] in
            guard let self else { return }
            for await state in self.socketClient.connectionStream {
                self.connectionState = state
                // Auto-rejoin game room on reconnect
                if state == .connected, let gameId = self.gameId {
                    self.socketClient.joinGame(gameId)
                    await self.syncState()
                }
            }
        }
    }

    private func handleEvent(_ event: GameEvent) {
        switch event {
        case .reset:
            gameState?.phase = .lobby
            updateNavigationState()
        case .error(let message):
            lastError = message
        case .custom(let type, _):
            if type == "player_joined" {
                // Refresh state to get updated player list
                Task { await syncState() }
            }
        }
    }

    private func updateNavigationState() {
        guard let phase = gameState?.phase else {
            navigationState = .start
            return
        }

        switch phase {
        case .lobby:
            navigationState = .lobby
        case .playing:
            navigationState = .playing
        case .tribalCouncil:
            navigationState = .tribal
        case .finalTribal:
            navigationState = .finalTribal
        case .finished:
            navigationState = .finished
        }
    }
}

// MARK: - Computed helpers

extension GameClient {
    var myPlayer: PlayerState? {
        guard let playerId else { return nil }
        return gameState?.players[playerId]
    }

    var isMyTurn: Bool {
        guard let playerId else { return false }
        return gameState?.isCurrentTurn(for: playerId) ?? false
    }

    var isHost: Bool {
        guard let playerId, let turnOrder = gameState?.turnOrder else { return false }
        return turnOrder.first == playerId
    }

    var isCouncilLeader: Bool {
        myPlayer?.isCouncilLeader ?? false
    }

    var isEliminated: Bool {
        myPlayer?.isEliminated ?? false
    }

    var isJuryMember: Bool {
        guard let playerId else { return false }
        return gameState?.jury?.contains(playerId) ?? false
    }

    var isFinalist: Bool {
        guard let playerId else { return false }
        return gameState?.finalTribal?.finalists.contains(playerId) ?? false
    }
}

// MARK: - Errors

enum GameClientError: LocalizedError {
    case noGame
    case operationFailed(String)

    var errorDescription: String? {
        switch self {
        case .noGame:
            return "No active game session"
        case .operationFailed(let message):
            return message
        }
    }
}
