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
    private(set) var accessState: IslandAccessState = .checking

    var gameId: String?
    var playerId: String?
    var playerName: String?
    /// A join code that arrived via survivorgame://join?code=… before the
    /// start screen was ready to consume it.
    var pendingJoinCode: String?

    // MARK: - Private

    private(set) var apiClient: APIClient
    private let socketClient = SocketClient()
    private var stateListenerTask: Task<Void, Never>?
    private var eventListenerTask: Task<Void, Never>?
    private var connectionListenerTask: Task<Void, Never>?

    init(baseURL: URL) {
        IslandAccessCookieStore.restore(for: baseURL)
        self.apiClient = APIClient(baseURL: baseURL)
        startListening()
    }

    var baseURL: URL { apiClient.baseURL }

    nonisolated deinit {
        MainActor.assumeIsolated {
            stateListenerTask?.cancel()
            eventListenerTask?.cancel()
            connectionListenerTask?.cancel()
            pollTask?.cancel()
        }
    }

    // MARK: - Connection

    func connect() {
        guard accessState == .unlocked else { return }
        socketClient.connect(to: apiClient.baseURL)
    }

    func disconnect() {
        socketClient.disconnect()
        connectionState = .disconnected
    }

    // MARK: - Island Access

    @discardableResult
    func checkIslandAccess() async -> IslandAccessState {
        accessState = .checking
        do {
            let result = try await apiClient.accessCheck()
            accessState = result.gated && !result.ok ? .requiresCode : .unlocked
        } catch {
            accessState = .unavailable(error.localizedDescription)
        }
        return accessState
    }

    func unlockIsland(with code: String) async throws {
        isLoading = true
        defer { isLoading = false }

        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            throw GameClientError.operationFailed("Enter the island code first")
        }

        let response = try await apiClient.submitAccess(code: trimmed)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "That code was refused")
        }

        let status = try await apiClient.accessCheck()
        guard !status.gated || status.ok else {
            throw GameClientError.operationFailed("The island did not remember that code")
        }
        IslandAccessCookieStore.persist(for: apiClient.baseURL)
        accessState = .unlocked
        // A mid-game 401 tore the socket down; a successful re-unlock must
        // revive it, or the table goes silent until relaunch.
        if gameId != nil {
            connect()
            await syncState()
        }
    }

    func useServer(_ url: URL) async {
        leaveGame()
        IslandAccessCookieStore.restore(for: url)
        apiClient = APIClient(baseURL: url)
        await checkIslandAccess()
    }

    func forgetIslandAccess() async {
        IslandAccessCookieStore.forget(for: apiClient.baseURL)
        leaveGame()
        await checkIslandAccess()
    }

    // MARK: - Game Lifecycle

    func createGame(
        deckMode: String = "official",
        expansion: Bool = false,
        settings: [String: String]? = nil
    ) async throws -> String {
        isLoading = true
        defer { isLoading = false }

        let response = try await apiClient.createGame(
            deckMode: deckMode, expansion: expansion, settings: settings)
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
        applyState(response.gameState)

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
        applyState(response.gameState)

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
        applyState(response.gameState)
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
        applyState(response.gameState)
    }

    func playCard(at index: Int) async throws -> PlayCardResponse {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.playCard(gameId: gameId, playerId: playerId, cardIdx: index)
        applyState(response.gameState)
        return response
    }

    /// Targeted card play — params carry targetId/allyId/victimId/cardType/
    /// takeIndex/choice… straight through as the server's effect kwargs.
    nonisolated func playCard(at index: Int, params: [String: Any]) async throws -> PlayCardResponse {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        nonisolated(unsafe) let paramsCopy = params
        let response = try await apiClient.playCard(
            gameId: gameId, playerId: playerId, cardIdx: index, params: paramsCopy)
        await applyState(response.gameState)
        return response
    }

    func drawCard() async throws -> DrawResponse {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.draw(gameId: gameId, playerId: playerId)
        // Applying the returned state BEFORE returning matters: the view models
        // clear isPerformingAction on return, and hasDrawn must already be
        // fresh by then or a fast double-tap slips a second draw through.
        applyState(response.gameState)
        return response
    }

    func advanceTurn() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.advanceTurn(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Advance failed")
        }
        applyState(response.gameState)
    }

    // MARK: - Reactive

    nonisolated func playReactiveCard(at index: Int, theftContext: [String: Any]) async throws {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        
        // Transfer dictionary across isolation boundary
        // Safe because it's immediately JSON-serialized in the actor
        nonisolated(unsafe) let contextCopy = theftContext
        let response = try await apiClient.playReactiveCard(
            gameId: gameId, playerId: playerId, cardIdx: index, theftContext: contextCopy
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Reactive play failed")
        }
        await applyState(response.gameState)
    }

    func completeTheft() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.completeTheft(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Complete theft failed")
        }
        applyState(response.gameState)
    }

    // MARK: - Tribal Council

    func startVoting(type: String = "elimination") async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.startVoting(gameId: gameId, voteType: type)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Start voting failed")
        }
        applyState(response.gameState)
    }

    func castVote(targetId: String, count: Int = 1) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        // The server reads "votes", not "count" — a ballot of votes:0 is refused.
        let votesData: [[String: Any]] = [["targetId": targetId, "votes": count]]
        let response = try await apiClient.castVote(gameId: gameId, voterId: playerId, votesData: votesData)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast vote failed")
        }
        applyState(response.gameState)
    }

    /// A split ballot: your Vote (and any Extra Votes) across several players.
    /// allocations: playerId → votes (zero entries are dropped).
    nonisolated func castSplitBallot(_ allocations: [String: Int]) async throws {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        nonisolated(unsafe) let votesData: [[String: Any]] = allocations
            .filter { $0.value > 0 }
            .map { ["targetId": $0.key, "votes": $0.value] }
        let response = try await apiClient.castVote(gameId: gameId, voterId: playerId, votesData: votesData)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast votes failed")
        }
        await applyState(response.gameState)
    }

    /// Passing the box with no Vote Card is legal — an explicitly empty ballot.
    nonisolated func passVotingBox() async throws {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        nonisolated(unsafe) let empty: [[String: Any]] = []
        let response = try await apiClient.castVote(gameId: gameId, voterId: playerId, votesData: empty)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Pass failed")
        }
        await applyState(response.gameState)
    }

    nonisolated func castVotes(votesData: [[String: Any]]) async throws {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        
        // Transfer dictionary across isolation boundary
        // Safe because it's immediately JSON-serialized in the actor
        nonisolated(unsafe) let votesCopy = votesData
        let response = try await apiClient.castVote(gameId: gameId, voterId: playerId, votesData: votesCopy)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast votes failed")
        }
        await applyState(response.gameState)
    }

    func revealVotes() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.revealVotes(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Reveal votes failed")
        }
        applyState(response.gameState)
    }

    func resolveTieBreak(chosenId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.tieBreak(gameId: gameId, leaderId: playerId, chosenId: chosenId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Tie break failed")
        }
        applyState(response.gameState)
    }

    func completeTribal() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.completeTribial(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Complete tribal failed")
        }
        applyState(response.gameState)
    }

    func advanceTribal(to phase: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.advanceTribal(gameId: gameId, phase: phase)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Advance tribal failed")
        }
        applyState(response.gameState)
    }

    func playAdvantage(type: String, targetId: String? = nil) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.playAdvantage(
            gameId: gameId, playerId: playerId, advantageType: type, targetId: targetId
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Play advantage failed")
        }
        applyState(response.gameState)
    }

    func playImmunity(targetId: String? = nil) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.playImmunity(
            gameId: gameId, playerId: playerId, targetId: targetId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Play immunity failed")
        }
        applyState(response.gameState)
    }

    func blockImmunity(targetId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.blockImmunity(gameId: gameId, playerId: playerId, targetId: targetId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Block immunity failed")
        }
        applyState(response.gameState)
    }

    func changeLeader(newLeaderId: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.changeLeader(gameId: gameId, newLeaderId: newLeaderId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Change leader failed")
        }
        applyState(response.gameState)
    }

    // MARK: - Final Tribal

    func advanceFinal(to phase: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.advanceFinal(gameId: gameId, phase: phase)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Advance final failed")
        }
        applyState(response.gameState)
    }

    func castFinalVote(finalistId: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.castFinalVote(
            gameId: gameId, juryMemberId: playerId, finalistId: finalistId
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Cast final vote failed")
        }
        applyState(response.gameState)
    }

    func signalReady() async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.signalReady(gameId: gameId, juryMemberId: playerId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Signal ready failed")
        }
        applyState(response.gameState)
    }

    func finalTieBreak(chosenWinner: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.finalTieBreak(
            gameId: gameId, leaderId: playerId, chosenWinner: chosenWinner
        )
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Final tie break failed")
        }
        applyState(response.gameState)
    }

    // MARK: - Lobby, Settings, Rocks

    func addBot() async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.addBot(gameId: gameId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Add bot failed")
        }
        applyState(response.gameState)
    }

    func removeBot(playerId botId: String) async throws {
        guard let gameId else { throw GameClientError.noGame }
        let response = try await apiClient.removeBot(gameId: gameId, playerId: botId)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Remove bot failed")
        }
        applyState(response.gameState)
    }

    func renameSelf(to newName: String) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.renamePlayer(
            gameId: gameId, playerId: playerId, newName: newName)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Rename failed")
        }
        applyState(response.gameState)
        playerName = newName
    }

    func updateGameSettings(_ settings: [String: String]) async throws {
        guard let gameId, let playerId else { throw GameClientError.noGame }
        let response = try await apiClient.updateGameSettings(
            gameId: gameId, playerId: playerId, settings: settings)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Settings change refused")
        }
        applyState(response.gameState)
    }

    nonisolated func challengeAction(_ action: String, value: (any Sendable)? = nil) async throws {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        nonisolated(unsafe) let valueCopy: Any? = value
        let response = try await apiClient.challengeAction(
            gameId: gameId, playerId: playerId, action: action, value: valueCopy)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "Challenge refused that")
        }
        await applyState(response.gameState)
    }

    nonisolated func interactionAct(_ action: String, value: (any Sendable)? = nil) async throws {
        let gameId = await self.gameId
        let playerId = await self.playerId
        guard let gameId, let playerId else { throw GameClientError.noGame }
        nonisolated(unsafe) let valueCopy: Any? = value
        let response = try await apiClient.interactionAct(
            gameId: gameId, playerId: playerId, action: action, value: valueCopy)
        guard response.success else {
            throw GameClientError.operationFailed(response.message ?? "That move was refused")
        }
        await applyState(response.gameState)
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

    /// Single funnel for every fresh-state arrival — HTTP action responses,
    /// socket pushes, and poll syncs. Equality-guarded: an identical snapshot
    /// must not re-render the whole view tree, and since navigation derives
    /// purely from the state, an equal state can't change navigation either.
    func applyState(_ state: GameState?) {
        guard let state, state != gameState else { return }
        gameState = state
        updateNavigationState()
    }

    func syncState() async {
        guard let gameId else { return }
        do {
            let state = try await apiClient.getGameState(gameId: gameId)
            applyState(state)
        } catch {
            if let apiError = error as? APIError, apiError.requiresIslandAccess {
                accessState = .requiresCode
                disconnect()
            }
            print("[GameClient] Sync failed: \(error)")
        }
    }

    // MARK: - Private

    private var pollTask: Task<Void, Never>?

    private func startListening() {
        stateListenerTask = Task { [weak self] in
            guard let self else { return }
            for await state in self.socketClient.gameStateStream {
                self.applyState(state)
            }
        }

        // REST-first resilience: the web app ran on polling alone for months.
        // 3s cadence while the socket is down, a 10s safety sync while it's up.
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                let connected = self.connectionState == .connected
                try? await Task.sleep(for: .seconds(connected ? 10 : 3))
                if self.gameId != nil {
                    await self.syncState()
                }
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

enum IslandAccessState: Equatable, Hashable {
    case checking
    case unlocked
    case requiresCode
    case unavailable(String)
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
        // councilLeaderId on the vote outranks the per-player flag
        if let leaderId = gameState?.currentVote?.councilLeaderId {
            return leaderId == playerId
        }
        return myPlayer?.isCouncilLeader ?? false
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
