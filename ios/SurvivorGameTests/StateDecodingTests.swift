import Testing
import Foundation
@testable import SurvivorGame

struct StateDecodingTests {

    // MARK: - GamePhase

    @Test func decodesGamePhases() throws {
        let phases = ["lobby", "playing", "tribal_council", "final", "final_tribal", "finished"]
        let expected: [GamePhase] = [.lobby, .playing, .tribalCouncil, .finalTribal, .finalTribal, .finished]

        for (raw, expected) in zip(phases, expected) {
            let json = "\"\(raw)\""
            let decoded = try JSONDecoder().decode(GamePhase.self, from: Data(json.utf8))
            #expect(decoded == expected)
        }
    }

    @Test func decodesUnknownPhaseAsLobby() throws {
        let decoded = try JSONDecoder().decode(GamePhase.self, from: Data("\"unknown\"".utf8))
        #expect(decoded == .lobby)
    }

    // MARK: - PlayerState

    @Test func decodesPlayerState() throws {
        let json = """
        {
            "id": "abc123",
            "name": "Tyler",
            "color": "#FF6B6B",
            "hand": [
                {"type": "vote", "category": "vote", "name": "Vote", "description": "Basic vote"}
            ],
            "isEliminated": false,
            "isActive": true,
            "isCouncilLeader": true,
            "hasStolen": false,
            "hasVoted": false,
            "extraVotes": 0,
            "characterCards": 2,
            "immunityPlayed": false
        }
        """
        let player = try JSONDecoder().decode(PlayerState.self, from: Data(json.utf8))

        #expect(player.id == "abc123")
        #expect(player.name == "Tyler")
        #expect(player.color == "#FF6B6B")
        #expect(player.hand.count == 1)
        #expect(player.hand[0].type == "vote")
        #expect(player.isEliminated == false)
        #expect(player.isCouncilLeader == true)
    }

    @Test func decodesPlayerWithMissingOptionalFields() throws {
        let json = """
        {
            "id": "abc123",
            "name": "Tyler",
            "color": "#FF6B6B"
        }
        """
        let player = try JSONDecoder().decode(PlayerState.self, from: Data(json.utf8))
        #expect(player.hand.isEmpty)
        #expect(player.isEliminated == false)
        #expect(player.extraVotes == 0)
    }

    // MARK: - CardInstance

    @Test func decodesCompactCard() throws {
        let json = """
        {"type": "vote"}
        """
        let card = try JSONDecoder().decode(CardInstance.self, from: Data(json.utf8))
        #expect(card.type == "vote")
        #expect(card.category == nil)
    }

    @Test func decodesFullCard() throws {
        let json = """
        {
            "type": "immunity_idol",
            "category": "tribal_advantage",
            "name": "Hidden Immunity Idol",
            "description": "Negate all votes",
            "playable_phases": ["tribal_immunity"],
            "requires_target": false,
            "requires_multiple_targets": false,
            "requires_confirmation": false,
            "reactive_only": false
        }
        """
        let card = try JSONDecoder().decode(CardInstance.self, from: Data(json.utf8))
        #expect(card.type == "immunity_idol")
        #expect(card.category == "tribal_advantage")
        #expect(card.playablePhases == ["tribal_immunity"])
        #expect(card.requiresTarget == false)
    }

    // MARK: - GameState

    @Test func decodesFullGameState() throws {
        let json = """
        {
            "id": "test1234",
            "phase": "playing",
            "players": {
                "p1": {
                    "id": "p1",
                    "name": "Alice",
                    "color": "#FF6B6B",
                    "hand": [{"type": "vote"}],
                    "isEliminated": false,
                    "isActive": true,
                    "isCouncilLeader": true,
                    "hasStolen": true,
                    "hasVoted": false,
                    "extraVotes": 0,
                    "characterCards": 2,
                    "immunityPlayed": false
                },
                "p2": {
                    "id": "p2",
                    "name": "Bob",
                    "color": "#4ECDC4",
                    "hand": [],
                    "isEliminated": false,
                    "isActive": true,
                    "isCouncilLeader": false,
                    "hasStolen": false,
                    "hasVoted": false,
                    "extraVotes": 0,
                    "characterCards": 2,
                    "immunityPlayed": false
                }
            },
            "turnOrder": ["p1", "p2"],
            "currentTurnIndex": 0,
            "deck": [{"type": "tribal_council_single"}],
            "gameHistory": [],
            "currentVote": {
                "type": "single",
                "phase": "waiting",
                "councilLeaderId": "p1",
                "votes": {},
                "tieBreakNeeded": false,
                "eliminated": []
            },
            "jury": [],
            "finalTribal": {
                "phase": "waiting",
                "finalists": [],
                "tieBreakNeeded": false
            },
            "createdAt": 1700000000.0,
            "lastActivity": 1700000001.0
        }
        """
        let state = try JSONDecoder().decode(GameState.self, from: Data(json.utf8))

        #expect(state.id == "test1234")
        #expect(state.phase == .playing)
        #expect(state.players.count == 2)
        #expect(state.turnOrder == ["p1", "p2"])
        #expect(state.currentTurnIndex == 0)
        #expect(state.currentPlayerId == "p1")
        #expect(state.currentPlayer?.name == "Alice")
        #expect(state.activePlayers.count == 2)
        #expect(state.deckCount == 1)
    }

    @Test func decodesTribalCouncilState() throws {
        let json = """
        {
            "type": "single",
            "phase": "voting",
            "voteType": "elimination",
            "councilLeaderId": "p1",
            "tieBreakNeeded": false,
            "eliminated": [],
            "immunityPlayed": ["p2"],
            "protectedPlayers": ["p2"]
        }
        """
        let vote = try JSONDecoder().decode(TribalVoteState.self, from: Data(json.utf8))
        #expect(vote.phase == .voting)
        #expect(vote.councilLeaderId == "p1")
        #expect(vote.immunityPlayed == ["p2"])
        #expect(vote.tieBreakNeeded == false)
    }

    @Test func decodesFinalTribalState() throws {
        let json = """
        {
            "phase": "voting",
            "finalists": ["p1", "p2"],
            "votes": {"p3": "p1", "p4": "p2"},
            "voteCounts": {"p1": 1, "p2": 1},
            "juryReady": ["p3", "p4"],
            "tieBreakNeeded": false
        }
        """
        let ft = try JSONDecoder().decode(FinalTribalState.self, from: Data(json.utf8))
        #expect(ft.phase == .voting)
        #expect(ft.finalists == ["p1", "p2"])
        #expect(ft.votes?["p3"] == "p1")
        #expect(ft.voteCounts?["p1"] == 1)
    }

    // MARK: - API Responses

    @Test func decodesCreateGameResponse() throws {
        let json = """
        {"success": true, "gameId": "abc12345"}
        """
        let response = try JSONDecoder().decode(CreateGameResponse.self, from: Data(json.utf8))
        #expect(response.success == true)
        #expect(response.gameId == "abc12345")
    }

    @Test func decodesPlayCardResponse() throws {
        let json = """
        {"success": true, "message": "Played Vote", "tribal_triggered": false}
        """
        let response = try JSONDecoder().decode(PlayCardResponse.self, from: Data(json.utf8))
        #expect(response.success == true)
        #expect(response.tribalTriggered == false)
    }

    // MARK: - Derived Properties

    @Test func turnPhaseReflectsStealing() throws {
        let state = MockGameClient.sampleGameState()
        // Player p1 at index 0 hasn't stolen yet (hasStolen: false)
        #expect(state.turnPhase(for: "p1") == .steal)
    }

    @Test func isCurrentTurnWorks() throws {
        let state = MockGameClient.sampleGameState()
        #expect(state.isCurrentTurn(for: "p1") == true)
        #expect(state.isCurrentTurn(for: "p2") == false)
    }
}
