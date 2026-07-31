import Foundation
import SwiftData

@Model
final class ServerConfig {
    @Attribute(.unique) var id: String
    var baseURL: URL
    var playerName: String
    var preferredColor: String?
    var lastGameId: String?
    var lastPlayerId: String?

    init(
        // The island's home on Tyler's LAN. A simulator overrides this via
        // SURVIVOR_SERVER_URL; any network change is editable in Settings.
        baseURL: URL = URL(string: "http://192.168.0.189:8080")!,
        playerName: String = "",
        preferredColor: String? = nil
    ) {
        self.id = "default"
        self.baseURL = baseURL
        self.playerName = playerName
        self.preferredColor = preferredColor
    }

    static func loadDefault(from context: ModelContext) -> ServerConfig {
        let descriptor = FetchDescriptor<ServerConfig>(
            predicate: #Predicate { $0.id == "default" }
        )
        if let existing = try? context.fetch(descriptor).first {
            return existing
        }
        let config = ServerConfig()
        context.insert(config)
        try? context.save()
        return config
    }
}
