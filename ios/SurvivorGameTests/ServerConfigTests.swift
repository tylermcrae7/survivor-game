import Testing
import Foundation
import SwiftData
@testable import SurvivorGame

struct ServerConfigTests {

    // MARK: - Legacy LAN Migration

    @Test @MainActor func legacyLANMigrationRunsOnce() throws {
        UserDefaults.standard.removeObject(forKey: "didMigrateLegacyLANDefault")
        let container = try ModelContainer(
            for: ServerConfig.self,
            configurations: ModelConfiguration(isStoredInMemoryOnly: true)
        )
        let context = container.mainContext

        // First load migrates the shipped LAN default to the public island.
        let config = ServerConfig(baseURL: URL(string: "http://192.168.0.189:8080")!)
        context.insert(config)
        try context.save()
        #expect(ServerConfig.loadDefault(from: context).baseURL == ServerConfig.publicIslandURL)

        // A deliberately re-entered LAN URL survives every later load.
        let reloaded = ServerConfig.loadDefault(from: context)
        reloaded.baseURL = URL(string: "http://192.168.0.189:8080")!
        try context.save()
        #expect(ServerConfig.loadDefault(from: context).baseURL.absoluteString
            == "http://192.168.0.189:8080")
    }
}
