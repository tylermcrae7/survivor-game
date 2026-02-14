import Foundation

@MainActor
@Observable
final class LobbyViewModel {
    var error: ViewModelError?
    var isStarting = false

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

    func leaveGame() {
        gameClient.leaveGame()
    }
}
