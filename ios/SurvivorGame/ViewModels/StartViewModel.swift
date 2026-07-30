import Foundation
import SwiftUI
import SwiftData

@MainActor
@Observable
final class StartViewModel {
    var playerName = ""
    var preferredColor: String?
    var serverURL = "http://localhost:8080"
    var joinCode = ""
    var loadingState: LoadingState = .idle
    var error: ViewModelError?

    private let gameClient: GameClient

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    func loadSavedConfig(from context: ModelContext) {
        let config = ServerConfig.loadDefault(from: context)
        playerName = config.playerName
        preferredColor = config.preferredColor
        serverURL = config.baseURL.absoluteString
        if let lastGameId = config.lastGameId, let lastPlayerId = config.lastPlayerId {
            joinCode = lastGameId
            // Attempt rejoin
            Task { await tryRejoin(gameId: lastGameId, playerId: lastPlayerId) }
        }
    }

    func saveConfig(to context: ModelContext) {
        let config = ServerConfig.loadDefault(from: context)
        config.playerName = playerName
        config.preferredColor = preferredColor
        config.baseURL = URL(string: serverURL) ?? URL(string: "http://localhost:8080")!
        config.lastGameId = gameClient.gameId
        config.lastPlayerId = gameClient.playerId
        try? context.save()
    }

    func createGame() async {
        guard validateInputs() else { return }
        loadingState = .loading

        do {
            let gameId = try await gameClient.createGame()
            try await gameClient.joinGame(
                gameId: gameId,
                name: playerName.trimmingCharacters(in: .whitespaces),
                color: preferredColor
            )
            loadingState = .loaded
        } catch {
            loadingState = .error(.from(error))
            self.error = .from(error)
        }
    }

    func joinGame() async {
        guard validateInputs(), !joinCode.trimmingCharacters(in: .whitespaces).isEmpty else {
            error = .gameError("Please enter a game code")
            return
        }
        loadingState = .loading

        do {
            try await gameClient.joinGame(
                gameId: joinCode.trimmingCharacters(in: .whitespaces),
                name: playerName.trimmingCharacters(in: .whitespaces),
                color: preferredColor
            )
            loadingState = .loaded
        } catch {
            loadingState = .error(.from(error))
            self.error = .from(error)
        }
    }

    func testConnection() async -> Bool {
        do {
            _ = try await gameClient.apiClient.ping()
            return true
        } catch {
            self.error = .networkError("Cannot reach server at \(serverURL)")
            return false
        }
    }

    // MARK: - Private

    private func tryRejoin(gameId: String, playerId: String) async {
        loadingState = .loading
        do {
            try await gameClient.rejoinGame(gameId: gameId, playerId: playerId)
            loadingState = .loaded
        } catch {
            // Rejoin failed — that's fine, just stay on start screen
            loadingState = .idle
        }
    }

    private func validateInputs() -> Bool {
        let name = playerName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else {
            error = .gameError("Please enter your name")
            return false
        }
        guard name.range(of: "^[a-zA-Z0-9_\\-\\. ]+$", options: .regularExpression) != nil else {
            error = .gameError("Name can only contain letters, numbers, spaces, dots, hyphens, and underscores")
            return false
        }
        return true
    }
}

// MARK: - Player Colors

enum PlayerColor: String, CaseIterable {
    case coral = "#FF6B6B"
    case teal = "#4ECDC4"
    case sky = "#45B7D1"
    case orange = "#F9844A"
    case green = "#90BE6D"
    case yellow = "#F9C74F"

    var displayName: String {
        switch self {
        case .coral: return "Coral"
        case .teal: return "Teal"
        case .sky: return "Sky"
        case .orange: return "Orange"
        case .green: return "Green"
        case .yellow: return "Yellow"
        }
    }

    var color: Color {
        Color(hex: rawValue) ?? .gray
    }
}
