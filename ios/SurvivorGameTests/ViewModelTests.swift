import Testing
import Foundation
@testable import SurvivorGame

struct ViewModelTests {

    // MARK: - CardCategory

    @Test func cardCategoryFromString() {
        #expect(CardCategory(rawValue: "vote") == .vote)
        #expect(CardCategory(rawValue: "tribal_advantage") == .tribalAdvantage)
        #expect(CardCategory(rawValue: "action") == .action)
        #expect(CardCategory(rawValue: "tribal_council") == .tribalCouncil)
        #expect(CardCategory(rawValue: "unknown") == nil)
    }

    // MARK: - GameState Computed

    @Test func sortedPlayersFollowsTurnOrder() {
        let state = MockGameClient.sampleGameState()
        let sorted = state.sortedPlayers
        #expect(sorted.count == 3)
        #expect(sorted[0].id == "p1")
        #expect(sorted[1].id == "p2")
        #expect(sorted[2].id == "p3")
    }

    @Test func activePlayersExcludesEliminated() throws {
        var state = MockGameClient.sampleGameState()
        // Manually create an eliminated player
        let eliminatedJSON = """
        {
            "id": "p2",
            "name": "Bob",
            "color": "#4ECDC4",
            "hand": [],
            "isEliminated": true,
            "isActive": true,
            "isCouncilLeader": false,
            "hasStolen": false,
            "hasVoted": false,
            "extraVotes": 0,
            "characterCards": 2,
            "immunityPlayed": false
        }
        """
        let eliminated = try JSONDecoder().decode(PlayerState.self, from: Data(eliminatedJSON.utf8))
        state.players["p2"] = eliminated

        #expect(state.activePlayers.count == 2)
        #expect(state.eliminatedPlayers.count == 1)
    }

    // MARK: - ViewModelError

    @Test func viewModelErrorFactory() {
        let networkError = ViewModelError.networkError()
        #expect(networkError.title == "Connection Error")
        #expect(networkError.isRetryable == true)

        let gameError = ViewModelError.gameError("Bad move")
        #expect(gameError.title == "Game Error")
        #expect(gameError.isRetryable == false)
    }

    // MARK: - NavigationState

    @Test func navigationStateMapping() {
        #expect(NavigationState.start == .start)
        #expect(NavigationState.lobby != .playing)
    }

    // MARK: - Color Extension

    @Test func hexColorParsing() {
        // Just verify it doesn't crash
        let _ = SwiftUI.Color(hex: "#FF6B6B")
        let _ = SwiftUI.Color(hex: "4ECDC4")
        let _ = SwiftUI.Color(hex: "#45B7D1FF")
        let _ = SwiftUI.Color(hex: "")
    }

    // MARK: - PlayerColor

    @Test func playerColorValues() {
        #expect(PlayerColor.allCases.count == 6)
        #expect(PlayerColor.coral.rawValue == "#FF6B6B")
        #expect(PlayerColor.teal.displayName == "Teal")
    }
}
