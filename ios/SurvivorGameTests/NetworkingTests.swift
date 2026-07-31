import Testing
import Foundation
@testable import SurvivorGame

struct NetworkingTests {
    
    // MARK: - Connection State
    
    @Test func connectionStateTransitions() {
        let disconnected = ConnectionState.disconnected
        let connecting = ConnectionState.connecting
        let connected = ConnectionState.connected
        
        #expect(disconnected != connecting)
        #expect(connecting != connected)
    }
    
    @Test func failedStateContainsMessage() {
        let failed = ConnectionState.failed("Network timeout")
        
        if case .failed(let message) = failed {
            #expect(message == "Network timeout")
        } else {
            Issue.record("Expected failed state with message")
        }
    }
    
    // MARK: - Navigation State
    
    @Test func navigationStatesCoverAllPhases() {
        let states: [NavigationState] = [
            .start,
            .lobby,
            .playing,
            .tribal,
            .finalTribal,
            .finished
        ]
        
        #expect(states.count == 6)
        
        // All states should be unique
        let uniqueStates = Set(states.map { "\($0)" })
        #expect(uniqueStates.count == 6)
    }
    
    // MARK: - API Error Handling
    
    @Test func apiErrorHasLocalizedDescription() {
        let error = APIError.serverError(statusCode: 500, message: "Internal server error")
        #expect(error.localizedDescription.contains("server"))
    }

    @Test func accessErrorsAreIdentified() {
        let gated = APIError.serverError(statusCode: 401, message: "Access required")
        let missing = APIError.serverError(statusCode: 404, message: "Not found")

        #expect(gated.requiresIslandAccess)
        #expect(!missing.requiresIslandAccess)
    }
    
    @Test func gameClientErrorHasLocalizedDescription() {
        let error = GameClientError.noGame
        #expect(error.localizedDescription == "No active game session")
        
        let opError = GameClientError.operationFailed("Invalid move")
        #expect(opError.localizedDescription == "Invalid move")
    }
    
    // MARK: - URL Construction
    
    @Test func baseURLIsValid() {
        let validURLs = [
            "http://localhost:3000",
            "https://survivor-game.com",
            "http://192.168.1.100:3000"
        ]
        
        for urlString in validURLs {
            let url = URL(string: urlString)
            #expect(url != nil, "URL should be valid: \(urlString)")
        }
    }

    @Test func productionIslandUsesHTTPS() {
        #expect(ServerConfig.publicIslandURL.absoluteString == "https://survivor.mctech.biz")
    }

    @Test @MainActor func joinCodeIsNormalizedForTheServer() {
        #expect(StartViewModel.normalizedGameCode("  ABCD1234\n") == "abcd1234")
        #expect(PlayerColor.allCases.count == 8)
    }

    // MARK: - Locked Island Session

    @Test @MainActor func socketHandshakeReceivesTheRESTAccessCookie() throws {
        let url = try #require(URL(string: "https://survivor-auth-test.invalid"))
        let cookie = try #require(HTTPCookie(properties: [
            .domain: "survivor-auth-test.invalid",
            .path: "/",
            .name: "survivor_access",
            .value: "test-cookie",
            .secure: "TRUE",
        ]))
        let storage = HTTPCookieStorage.shared
        storage.setCookie(cookie)
        defer { storage.deleteCookie(cookie) }

        let socketCookies = SocketClient.connectionCookies(for: url, storage: storage)
        #expect(socketCookies.contains { $0.name == "survivor_access" && $0.value == "test-cookie" })
    }

    @Test func accessCookieSurvivesAProcessStyleJarReset() throws {
        let url = try #require(URL(string: "http://survivor-keychain-test.invalid"))
        let cookie = try #require(HTTPCookie(properties: [
            .domain: "survivor-keychain-test.invalid",
            .path: "/",
            .name: "survivor_access",
            .value: "persistent-test-cookie",
            .expires: Date().addingTimeInterval(3600),
        ]))
        let storage = HTTPCookieStorage.shared
        IslandAccessCookieStore.forget(for: url, storage: storage)
        defer { IslandAccessCookieStore.forget(for: url, storage: storage) }

        storage.setCookie(cookie)
        #expect(IslandAccessCookieStore.persist(for: url, storage: storage))
        storage.deleteCookie(cookie)
        #expect(storage.cookies(for: url)?.isEmpty != false)

        IslandAccessCookieStore.restore(for: url, storage: storage)
        #expect(storage.cookies(for: url)?.contains {
            $0.name == "survivor_access"
                && $0.value == "persistent-test-cookie"
                && !$0.isSecure
        } == true)
    }

    @Test func aggregatedWinnersDecodeWithVictoryCounts() throws {
        let json = Data(#"[{"winner_name":"Sandra","victories":2,"dates":["2026-07-30","2026-07-31"]}]"#.utf8)
        let winners = try JSONDecoder().decode([WinnerSummary].self, from: json)

        #expect(winners == [WinnerSummary(
            winnerName: "Sandra",
            victories: 2,
            dates: ["2026-07-30", "2026-07-31"]
        )])
    }
    
    // MARK: - Game Event Types
    
    @Test func gameEventTypes() {
        let resetEvent = GameEvent.reset
        let errorEvent = GameEvent.error("Something went wrong")
        let customEvent = GameEvent.custom(type: "player_joined", data: ["playerId": "p1"])
        
        if case .reset = resetEvent {
            // Success
        } else {
            Issue.record("Expected reset event")
        }
        
        if case .error(let message) = errorEvent {
            #expect(message == "Something went wrong")
        } else {
            Issue.record("Expected error event")
        }
        
        if case .custom(let type, let data) = customEvent {
            #expect(type == "player_joined")
            #expect(data["playerId"] as? String == "p1")
        } else {
            Issue.record("Expected custom event")
        }
    }
}
