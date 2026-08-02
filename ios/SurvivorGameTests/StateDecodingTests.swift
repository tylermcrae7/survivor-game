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
            "immunityPlayed": [
                {"playerId": "p2", "targetId": "p2", "timestamp": 1754000000.0}
            ],
            "protectedPlayers": ["p2"]
        }
        """
        let vote = try JSONDecoder().decode(TribalVoteState.self, from: Data(json.utf8))
        #expect(vote.phase == .voting)
        #expect(vote.councilLeaderId == "p1")
        #expect(vote.immunityPlayed?.count == 1)
        #expect(vote.immunityPlayed?.first?.playerId == "p2")
        #expect(vote.tieBreakNeeded == false)
    }

    /// The server writes dictionaries into `immunityPlayed`
    /// (survivor_server.py `play_immunity`), never player-id strings. This
    /// field was typed `[String]?` and decoded behind a `try?`, so it silently
    /// resolved to nil forever and the "Immunity Played" panel never rendered —
    /// the fixture above had been asserting a shape the server does not send.
    @Test func decodesAnIdolPlayedForAnAlly() throws {
        let json = """
        {
            "phase": "immunity",
            "tieBreakNeeded": false,
            "immunityPlayed": [
                {"playerId": "p1", "targetId": "p3", "timestamp": 1754000000.0},
                {"playerId": "p2", "targetId": "p2", "timestamp": 1754000001.0}
            ]
        }
        """
        let vote = try JSONDecoder().decode(TribalVoteState.self, from: Data(json.utf8))
        #expect(vote.immunityPlayed?.count == 2)
        // Shielding an ally: the holder and the protected player differ.
        #expect(vote.immunityPlayed?.first?.playerId == "p1")
        #expect(vote.immunityPlayed?.first?.targetId == "p3")
        #expect(vote.immunityPlayed?.last?.playerId == "p2")
        #expect(vote.immunityPlayed?.last?.targetId == "p2")
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

    @MainActor @Test func turnPhaseReflectsStealing() throws {
        let state = MockGameClient.sampleGameState()
        // Player p1 at index 0 hasn't stolen yet (hasStolen: false)
        #expect(state.turnPhase(for: "p1") == .steal)
    }

    @MainActor @Test func isCurrentTurnWorks() throws {
        let state = MockGameClient.sampleGameState()
        #expect(state.isCurrentTurn(for: "p1") == true)
        #expect(state.isCurrentTurn(for: "p2") == false)
    }
}

// MARK: - Places

struct PlaceTests {

    /// The exact four keys the server writes, and the exact labels the UI
    /// (and later the Discord channel names) must show for them.
    @Test func everyServerKeyMapsToItsLabel() {
        let expected: [(String, String)] = [
            ("camp_fire", "Camp Fire"),
            ("the_beach", "The Beach"),
            ("the_water_well", "The Water Well"),
            ("tribal_council", "Tribal Council"),
        ]
        for (key, label) in expected {
            #expect(Place(rawValue: key)?.label == label, "wrong label for \(key)")
            #expect(Place.label(for: key) == label)
        }
        #expect(Place.allCases.count == expected.count)
        #expect(Set(Place.allCases.map(\.key)) == Set(expected.map(\.0)))
    }

    /// A place this build has never heard of is titleised, never dropped or
    /// shown raw — the server may open new ground before the app ships again.
    @Test func unknownKeysStillReadAsPlaces() {
        #expect(Place.label(for: "the_shipwreck") == "The Shipwreck")
        #expect(Place.symbolName(for: "the_shipwreck") == "mappin.and.ellipse")
    }

    @Test func decodesPlaceAndDiscordIdOnAPlayer() throws {
        let json = """
        {"id": "p1", "name": "Coconut", "color": "#FF6B6B",
         "place": "the_beach", "discordUserId": "123456789012345678"}
        """
        let player = try JSONDecoder().decode(PlayerState.self, from: Data(json.utf8))
        #expect(player.place == "the_beach")
        #expect(player.placeKey == "the_beach")
        #expect(player.discordUserId == "123456789012345678")
    }

    /// A player from before places existed stands at the fire rather than
    /// vanishing from every row.
    @Test func playerWithoutAPlaceFallsBackToTheFire() throws {
        let json = """
        {"id": "p1", "name": "Coconut", "color": "#FF6B6B"}
        """
        let player = try JSONDecoder().decode(PlayerState.self, from: Data(json.utf8))
        #expect(player.place == nil)
        #expect(player.discordUserId == nil)
        #expect(player.placeKey == Place.campFire.key)
    }

    @Test func decodesPlacePolicy() throws {
        let json = """
        {"open": ["camp_fire", "the_beach", "the_water_well"], "forced": null}
        """
        let policy = try JSONDecoder().decode(PlacePolicy.self, from: Data(json.utf8))
        #expect(policy.open == ["camp_fire", "the_beach", "the_water_well"])
        #expect(policy.forced == nil)
        #expect(policy.isForced == false)
        #expect(policy.visibleKeys == policy.open)
    }

    @Test func aForcedPolicyShowsOnlyTheForcedPlace() throws {
        let json = """
        {"open": [], "forced": "tribal_council"}
        """
        let policy = try JSONDecoder().decode(PlacePolicy.self, from: Data(json.utf8))
        #expect(policy.isForced)
        #expect(policy.visibleKeys == ["tribal_council"])
        // The ceremony is not optional: nothing is tappable, not even the
        // place everyone is already standing in.
        #expect(policy.canMove(to: "tribal_council", from: "tribal_council") == false)
        #expect(policy.canMove(to: "the_beach", from: "tribal_council") == false)
    }

    @Test func movementIsGatedByTheOpenList() {
        let policy = PlacePolicy(open: ["camp_fire", "the_beach"])
        #expect(policy.canMove(to: "the_beach", from: "camp_fire"))
        // Already there — marked, not tappable.
        #expect(policy.canMove(to: "camp_fire", from: "camp_fire") == false)
        // Not open — the server would refuse it anyway.
        #expect(policy.canMove(to: "the_water_well", from: "camp_fire") == false)
    }

    /// A state with no policy at all must decode fine (the UI hides itself);
    /// a malformed one must not brick the whole snapshot either.
    @Test func absentOrBrokenPolicyNeverBricksTheState() throws {
        let base = """
        {"id": "x", "phase": "playing",
         "players": {"p1": {"id": "p1", "name": "Ana", "color": "#FF6B6B"}},
         "turnOrder": ["p1"], "currentTurnIndex": 0
        """
        let without = try JSONDecoder().decode(GameState.self, from: Data((base + "}").utf8))
        #expect(without.placePolicy == nil)

        let broken = try JSONDecoder().decode(
            GameState.self, from: Data((base + #", "placePolicy": "nonsense"}"#).utf8))
        #expect(broken.placePolicy == nil)
        #expect(broken.players.count == 1)
    }

    /// Occupancy is what the whole feature shows: alive players only, in turn
    /// order, with the no-place fallback folded in.
    @Test func occupancyGroupsLivePlayersByPlaceInTurnOrder() {
        let state = GameState(
            id: "g", phase: .playing,
            players: [
                "p1": PlayerState(id: "p1", name: "Ana", color: "#FF6B6B", place: "the_beach"),
                "p2": PlayerState(id: "p2", name: "Bo", color: "#4ECDC4", place: "the_beach"),
                "p3": PlayerState(id: "p3", name: "Cy", color: "#45B7D1"),
                "p4": PlayerState(id: "p4", name: "Dee", color: "#96CEB4",
                                  isEliminated: true, place: "the_beach"),
            ],
            turnOrder: ["p1", "p2", "p3", "p4"], currentTurnIndex: 0,
            placePolicy: PlacePolicy(open: ["camp_fire", "the_beach"])
        )
        #expect(state.players(at: "the_beach").map(\.id) == ["p1", "p2"])
        #expect(state.players(at: "camp_fire").map(\.id) == ["p3"])
        #expect(state.players(at: "the_water_well").isEmpty)
    }
}
