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
        let wipedEvent = GameEvent.wiped
        let errorEvent = GameEvent.error("Something went wrong")
        let customEvent = GameEvent.custom(type: "player_joined", data: ["playerId": "p1"])
        
        if case .reset = resetEvent {
            // Success
        } else {
            Issue.record("Expected reset event")
        }

        if case .wiped = wipedEvent {
            // Success
        } else {
            Issue.record("Expected wiped event")
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

    @Test @MainActor func leaveAndWipeClearThePersistedSession() {
        var clearCount = 0
        let client = GameClient(
            baseURL: URL(string: "https://survivor-session-test.invalid")!,
            clearSavedSession: { clearCount += 1 }
        )

        client.gameId = "deadbeef"
        client.playerId = "player-1"
        client.leaveGame()
        #expect(clearCount == 1)
        #expect(client.gameId == nil)
        #expect(client.playerId == nil)
        #expect(client.navigationState == .start)

        client.gameId = "deadbeef"
        client.playerId = "player-1"
        client.handleEvent(.wiped)
        #expect(clearCount == 2)
        #expect(client.gameId == nil)
        #expect(client.playerId == nil)
        #expect(client.navigationState == .start)
    }

    // MARK: - Alliance routing (I4)

    private func allianceEventData() -> [String: Any] {
        [
            "initiatorId": "p1", "initiator": "TDawg",
            "allyId": "p2", "ally": "Mango",
            "victimId": "p3", "victim": "Coconut",
            "message": "TDawg forms an alliance with Mango — they raid Coconut's camp together",
        ]
    }

    /// The initiator's own phone gets the blocking overlay, not the toast —
    /// `Let's Form An Alliance` used to leave this exact phone silent.
    @Test @MainActor func allianceGivesTheInitiatorTheOverlayNotTheToast() {
        let client = GameClient(baseURL: URL(string: "https://survivor-alliance-test.invalid")!)
        client.playerId = "p1"
        client.handleEvent(.custom(type: "alliance", data: allianceEventData()))
        #expect(client.allianceAlert == AllianceOverlayContent(partnerName: "Mango", victimName: "Coconut"))
        #expect(client.narration.queueDepthForTesting == 0)
    }

    /// The ally's phone gets the overlay too — that side used to get only a
    /// normal-priority steal toast.
    @Test @MainActor func allianceGivesTheAllyTheOverlayNotTheToast() {
        let client = GameClient(baseURL: URL(string: "https://survivor-alliance-test.invalid")!)
        client.playerId = "p2"
        client.handleEvent(.custom(type: "alliance", data: allianceEventData()))
        #expect(client.allianceAlert == AllianceOverlayContent(partnerName: "TDawg", victimName: "Coconut"))
        #expect(client.narration.queueDepthForTesting == 0)
    }

    /// Everyone else at the table — the victim included — keeps the ordinary
    /// toast and never sees the overlay.
    @Test @MainActor func allianceLeavesEveryoneElseWithTheOrdinaryToast() {
        let client = GameClient(baseURL: URL(string: "https://survivor-alliance-test.invalid")!)
        client.playerId = "p3"
        client.handleEvent(.custom(type: "alliance", data: allianceEventData()))
        #expect(client.allianceAlert == nil)
        #expect(client.narration.pendingForTesting.contains {
            $0.message == "TDawg forms an alliance with Mango — they raid Coconut's camp together"
        })
    }

    /// A reset must not leave a stale overlay open on the next game.
    @Test @MainActor func resetClearsAPendingAllianceAlert() {
        let client = GameClient(baseURL: URL(string: "https://survivor-alliance-test.invalid")!)
        client.playerId = "p1"
        client.handleEvent(.custom(type: "alliance", data: allianceEventData()))
        #expect(client.allianceAlert != nil)
        client.handleEvent(.reset)
        #expect(client.allianceAlert == nil)
    }

    /// Leaving a lobby has to stick. A broadcast already in flight when the
    /// leave lands used to be applied anyway, which re-derived navigation and
    /// walked straight back into the lobby — the Leave button looked broken.
    @Test @MainActor func aStatePushAfterLeavingIsIgnored() {
        let client = GameClient(baseURL: URL(string: "https://survivor-leave-test.invalid")!)
        client.gameId = "test123"
        client.applyState(MockGameClient.sampleGameState())
        #expect(client.gameState != nil)

        client.leaveGame()
        #expect(client.gameState == nil)

        client.applyState(MockGameClient.sampleGameState())
        #expect(client.gameState == nil, "a push for the game we just left must not revive it")
        #expect(client.navigationState == .start)
    }

    /// The same guard by game id: two games in one session must never cross.
    @Test @MainActor func aStatePushForADifferentGameIsIgnored() {
        let client = GameClient(baseURL: URL(string: "https://survivor-leave-test.invalid")!)
        client.gameId = "someOtherGame"
        client.applyState(MockGameClient.sampleGameState())
        #expect(client.gameState == nil)
    }

    // MARK: - Robbery routing (A3)

    private func robbedEventData() -> [String: Any] {
        [
            "thiefId": "p1", "thief": "TDawg", "victimId": "p2",
            "cards": [["name": "Hidden Immunity Idol", "type": "advantage"]],
            "message": "TDawg took your Hidden Immunity Idol",
        ]
    }

    /// The named victim gets the banner and — unlike an ordinary steal —
    /// never a queued toast for the same event: two notices for one theft is
    /// the double-toast mistake `_emit_narrator_events` documents.
    @Test @MainActor func robbedGivesTheVictimTheBannerNotTheToast() {
        let client = GameClient(baseURL: URL(string: "https://survivor-robbery-test.invalid")!)
        client.playerId = "p2"
        client.handleEvent(.custom(type: "robbed", data: robbedEventData()))
        #expect(client.robberyAlert == RobberyBannerContent(
            thiefId: "p1", thiefName: "TDawg", cards: ["Hidden Immunity Idol"],
            message: "TDawg took your Hidden Immunity Idol"))
        #expect(client.narration.queueDepthForTesting == 0)
    }

    /// Private and public events share the `game_event` channel — this is the
    /// only defense if a routing bug ever leaks a robbed event naming someone
    /// else. It must be ignored entirely: no banner, and no toast either.
    @Test @MainActor func robbedNamingAnotherVictimLeavesTheAlertNil() {
        let client = GameClient(baseURL: URL(string: "https://survivor-robbery-test.invalid")!)
        client.playerId = "p3"
        client.handleEvent(.custom(type: "robbed", data: robbedEventData()))
        #expect(client.robberyAlert == nil)
        #expect(client.narration.queueDepthForTesting == 0)
    }

    /// A reset must not leave a stale banner open on the next game.
    @Test @MainActor func resetClearsAPendingRobberyAlert() {
        let client = GameClient(baseURL: URL(string: "https://survivor-robbery-test.invalid")!)
        client.playerId = "p2"
        client.handleEvent(.custom(type: "robbed", data: robbedEventData()))
        #expect(client.robberyAlert != nil)
        client.handleEvent(.reset)
        #expect(client.robberyAlert == nil)
    }

    /// Leaving the game (and `.wiped`, which routes through the same
    /// function) must not carry a robbery banner into whatever comes next.
    @Test @MainActor func leaveGameClearsAPendingRobberyAlert() {
        let client = GameClient(baseURL: URL(string: "https://survivor-robbery-test.invalid")!)
        client.playerId = "p2"
        client.handleEvent(.custom(type: "robbed", data: robbedEventData()))
        #expect(client.robberyAlert != nil)
        client.leaveGame()
        #expect(client.robberyAlert == nil)
    }
}
