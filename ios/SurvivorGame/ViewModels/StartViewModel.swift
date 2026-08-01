import Foundation
import SwiftUI
import SwiftData

@MainActor
@Observable
final class StartViewModel {
    var playerName = ""
    var preferredColor: String?
    /// Set in Settings, not here — carried along so every join tells the
    /// server which Discord account to move between voice channels.
    var discordUserId: String?
    var joinCode = ""
    var loadingState: LoadingState = .idle
    var error: ViewModelError?

    private let gameClient: GameClient
    private var modelContext: ModelContext?
    private var savedGameId: String?
    private var savedPlayerId: String?
    private var attemptedRestore = false

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    func loadSavedConfig(from context: ModelContext) {
        modelContext = context
        let config = ServerConfig.loadDefault(from: context)
        playerName = config.playerName
        preferredColor = config.preferredColor
        discordUserId = config.discordUserId
        if let lastGameId = config.lastGameId, let lastPlayerId = config.lastPlayerId {
            joinCode = lastGameId
            savedGameId = lastGameId
            savedPlayerId = lastPlayerId
        }

        let defaults = UserDefaults.standard
        deckMode = defaults.string(forKey: "defaultDeckMode") ?? "official"
        expansion = defaults.bool(forKey: "defaultExpansion")
        botPace = defaults.string(forKey: "defaultBotPace") ?? "normal"
        tribalPace = defaults.string(forKey: "defaultTribalPace") ?? "normal"
        botStyle = defaults.string(forKey: "defaultBotStyle") ?? "normal"
    }

    var deckMode = "official"
    var expansion = false
    var botPace = "normal"
    var tribalPace = "normal"
    var botStyle = "normal"

    func createGame() async {
        guard validateInputs() else { return }
        loadingState = .loading

        do {
            var settings: [String: String]? = nil
            if botPace != "normal" || tribalPace != "normal" || botStyle != "normal" {
                settings = ["botPace": botPace, "tribalPace": tribalPace, "botStyle": botStyle]
            }
            let gameId = try await gameClient.createGame(
                deckMode: deckMode, expansion: expansion, settings: settings)
            try await gameClient.joinGame(
                gameId: gameId,
                name: playerName.trimmingCharacters(in: .whitespaces),
                color: preferredColor,
                discordUserId: currentDiscordUserId
            )
            saveSession()
            loadingState = .loaded
        } catch {
            loadingState = .error(.from(error))
            self.error = .from(error)
        }
    }

    func joinGame() async {
        let normalizedCode = Self.normalizedGameCode(joinCode)
        guard validateInputs(), !normalizedCode.isEmpty else {
            error = .gameError("Please enter a game code")
            return
        }
        guard normalizedCode.range(of: "^[a-f0-9]{8}$", options: .regularExpression) != nil else {
            error = .gameError("Game codes are eight letters or numbers")
            return
        }
        loadingState = .loading

        do {
            try await gameClient.joinGame(
                gameId: normalizedCode,
                name: playerName.trimmingCharacters(in: .whitespaces),
                color: preferredColor,
                discordUserId: currentDiscordUserId
            )
            joinCode = normalizedCode
            saveSession()
            loadingState = .loaded
        } catch {
            loadingState = .error(.from(error))
            self.error = .from(error)
        }
    }

    func restoreSavedGameIfNeeded() async {
        guard !attemptedRestore, gameClient.accessState == .unlocked,
              let gameId = savedGameId, let playerId = savedPlayerId
        else { return }
        attemptedRestore = true
        await tryRejoin(gameId: gameId, playerId: playerId)
    }

    static func normalizedGameCode(_ code: String) -> String {
        code.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    // MARK: - Private

    /// Read fresh at join time. The ID is edited in Settings, which writes
    /// straight to the store, while this view model is built once per launch —
    /// caching it would send a stale (usually nil) value forever after.
    private var currentDiscordUserId: String? {
        guard let modelContext else { return discordUserId }
        return ServerConfig.loadDefault(from: modelContext).discordUserId
    }

    private func tryRejoin(gameId: String, playerId: String) async {
        loadingState = .loading
        do {
            // Restoring a saved session is how most players enter a game after
            // the first launch — a Discord ID set later would never reach the
            // server if only the fresh-join path carried it.
            try await gameClient.rejoinGame(
                gameId: gameId, playerId: playerId, discordUserId: currentDiscordUserId)
            saveSession()
            loadingState = .loaded
        } catch {
            // Rejoin failed — that's fine, just stay on start screen
            loadingState = .idle
        }
    }

    private func saveSession() {
        guard let modelContext else { return }
        let config = ServerConfig.loadDefault(from: modelContext)
        config.playerName = playerName.trimmingCharacters(in: .whitespacesAndNewlines)
        config.preferredColor = preferredColor
        config.lastGameId = gameClient.gameId
        config.lastPlayerId = gameClient.playerId
        try? modelContext.save()
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
    case sage = "#96CEB4"
    case yellow = "#FFEAA7"
    case plum = "#DDA0DD"
    case mint = "#98D8C8"
    case gold = "#F7DC6F"

    var displayName: String {
        switch self {
        case .coral: return "Coral"
        case .teal: return "Teal"
        case .sky: return "Blue"
        case .sage: return "Sage"
        case .yellow: return "Yellow"
        case .plum: return "Plum"
        case .mint: return "Mint"
        case .gold: return "Gold"
        }
    }

    var color: Color {
        Color(hex: rawValue) ?? .gray
    }
}
