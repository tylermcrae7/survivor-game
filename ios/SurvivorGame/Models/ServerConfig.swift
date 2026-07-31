import Foundation
import SwiftData

@Model
final class ServerConfig {
    static let publicIslandURL = URL(string: "https://survivor.mctech.biz")!
    static let legacyMigrationDefaultsKey = "didMigrateLegacyLANDefault"
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
        let migrationKey = legacyMigrationDefaultsKey
        let descriptor = FetchDescriptor<ServerConfig>(
            predicate: #Predicate { $0.id == "default" }
        )
        if let existing = try? context.fetch(descriptor).first {
            // The first native builds shipped one machine's LAN address as the
            // default. Move that exact legacy value to the stable public island
            // exactly once; user-entered servers — even that same LAN address,
            // re-entered deliberately — remain untouched.
            if existing.baseURL == legacyLANURL,
               !UserDefaults.standard.bool(forKey: migrationKey) {
                existing.baseURL = publicIslandURL
                try? context.save()
            }
            UserDefaults.standard.set(true, forKey: migrationKey)
            return existing
        }
        let config = ServerConfig()
        context.insert(config)
        try? context.save()
        // A fresh install has nothing to migrate — mark it done now so a LAN
        // URL entered right after first launch is never rewritten.
        UserDefaults.standard.set(true, forKey: migrationKey)
        return config
    }
}
