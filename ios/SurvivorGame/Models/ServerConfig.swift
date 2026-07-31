import Foundation
import SwiftData

@Model
final class ServerConfig {
    static let publicIslandURL = URL(string: "https://survivor.mctech.biz")!
    private static let legacyLANURL = URL(string: "http://192.168.0.189:8080")!

    @Attribute(.unique) var id: String
    var baseURL: URL
    var playerName: String
    var preferredColor: String?
    var lastGameId: String?
    var lastPlayerId: String?

    init(
        // Production installs use the public HTTPS island. Simulator and local
        // development can override this with SURVIVOR_SERVER_URL.
        baseURL: URL = ServerConfig.publicIslandURL,
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
            // The first native builds shipped one machine's LAN address as the
            // default. Move only that exact legacy value to the stable public
            // island; user-entered servers remain untouched.
            if existing.baseURL == legacyLANURL {
                existing.baseURL = publicIslandURL
                try? context.save()
            }
            return existing
        }
        let config = ServerConfig()
        context.insert(config)
        try? context.save()
        return config
    }
}
