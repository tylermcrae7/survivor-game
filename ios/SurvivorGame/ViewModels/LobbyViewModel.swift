import Foundation

@MainActor
@Observable
final class LobbyViewModel {
    var error: ViewModelError?
    var isStarting = false
    var isLeaving = false

    private let gameClient: GameClient

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    var gameId: String { gameClient.gameId ?? "" }
    var players: [PlayerState] { gameClient.gameState?.sortedPlayers ?? [] }
    var playerCount: Int { players.count }
    var canStart: Bool { playerCount >= 3 && gameClient.isHost }
    var isHost: Bool { gameClient.isHost }
    var myPlayerId: String? { gameClient.playerId }

    func startGame() async {
        isStarting = true
        defer { isStarting = false }

        do {
            try await gameClient.startGame()
        } catch {
            self.error = .from(error)
        }
    }

    func renameSelf(to name: String) async {
        do {
            try await gameClient.renameSelf(to: name)
        } catch {
            self.error = .from(error)
        }
    }

    func removeBot(_ botId: String) async {
        do {
            try await gameClient.removeBot(playerId: botId)
        } catch {
            self.error = .from(error)
        }
    }

    func addBot() async {
        do {
            try await gameClient.addBot()
        } catch {
            self.error = .from(error)
        }
    }

    /// Self-leave, lobby only — refused once the game has started, and a
    /// 404 from an older server that predates the route surfaces the same
    /// way. Both land here, same as every other lobby action's error path.
    func leaveLobby() async {
        isLeaving = true
        defer { isLeaving = false }
        do {
            try await gameClient.leaveLobby()
        } catch {
            self.error = .from(error)
        }
    }
}
