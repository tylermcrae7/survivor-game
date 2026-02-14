import Foundation
@testable import SurvivorGame

/// Mock GameClient for unit testing ViewModels
@MainActor
final class MockGameClient {
    var mockGameState: GameState?
    var lastAction: String?
    var shouldFail = false

    static func sampleGameState() -> GameState {
        let player1 = PlayerState.sample(id: "p1", name: "Alice", color: "#FF6B6B")
        let player2 = PlayerState.sample(id: "p2", name: "Bob", color: "#4ECDC4")
        let player3 = PlayerState.sample(id: "p3", name: "Charlie", color: "#45B7D1")

        return GameState(
            id: "test123",
            phase: .playing,
            players: ["p1": player1, "p2": player2, "p3": player3],
            turnOrder: ["p1", "p2", "p3"],
            currentTurnIndex: 0,
            deck: [],
            gameHistory: [],
            currentVote: TribalVoteState(
                type: "single",
                phase: .waiting,
                voteType: nil,
                councilLeaderId: "p1",
                votes: nil,
                voteResults: nil,
                protectedPlayers: nil,
                immunityPlayed: nil,
                tieBreakNeeded: false,
                tiedPlayers: nil,
                eliminated: nil,
                tieBreakResolvedBy: nil,
                advantageCardsPlayed: nil
            ),
            jury: [],
            finalTribal: FinalTribalState(
                phase: .waiting,
                finalists: [],
                votes: nil,
                voteCounts: nil,
                juryReady: nil,
                tieBreakNeeded: false,
                tiedFinalists: nil,
                tieBreakerLeader: nil,
                tieBreakBy: nil,
                winner: nil
            ),
            winner: nil,
            createdAt: Date().timeIntervalSince1970,
            lastActivity: Date().timeIntervalSince1970
        )
    }
}

// MARK: - Sample Data Helpers

extension PlayerState {
    static func sample(
        id: String = "p1",
        name: String = "Test Player",
        color: String = "#FF6B6B",
        hand: [CardInstance] = [],
        isEliminated: Bool = false
    ) -> PlayerState {
        let json: [String: Any] = [
            "id": id,
            "name": name,
            "color": color,
            "hand": hand.map { card -> [String: Any] in
                var dict: [String: Any] = ["type": card.type]
                if let cat = card.category { dict["category"] = cat }
                if let n = card.name { dict["name"] = n }
                if let d = card.description { dict["description"] = d }
                return dict
            },
            "isEliminated": isEliminated,
            "isActive": true,
            "isCouncilLeader": false,
            "hasStolen": false,
            "hasVoted": false,
            "extraVotes": 0,
            "characterCards": 2,
            "immunityPlayed": false
        ]

        let data = try! JSONSerialization.data(withJSONObject: json)
        return try! JSONDecoder().decode(PlayerState.self, from: data)
    }
}
