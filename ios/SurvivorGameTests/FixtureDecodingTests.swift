import Testing
import Foundation
@testable import SurvivorGame

/// The wire-contract lock. Every fixture is REAL server output
/// (get_game_state — secrets already stripped) captured at a moment the app
/// must decode flawlessly. Regenerate after server wire changes with
/// `ios/SurvivorGameTests/Fixtures/generate_fixtures.py`.
struct FixtureDecodingTests {

    static let allFixtures = [
        "lobby", "playing_midturn", "tribal_announcement", "tribal_voting",
        "tribal_immunity", "tribal_reveal_tie", "challenge_active",
        "interaction_active", "pending_theft_open", "legacy_no_settings",
        "finished",
    ]

    private func load(_ name: String) throws -> GameState {
        let bundle = Bundle(for: BundleToken.self)
        guard let url = bundle.url(forResource: name, withExtension: "json") else {
            throw FixtureError.missing(name)
        }
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(GameState.self, from: data)
    }

    @Test(arguments: allFixtures)
    func everyRealServerShapeDecodes(fixture: String) throws {
        let state = try load(fixture)
        #expect(!state.id.isEmpty)
        #expect(!state.players.isEmpty)
    }

    @Test func votingCouncilDecodesWithBallotsAndSpentCards() throws {
        // The exact shape that used to throw ("voting" vs "tribal_voting")
        // and brick the entire state the moment any council reached a vote.
        let state = try load("tribal_voting")
        #expect(state.phase == .tribalCouncil)
        #expect(state.currentVote?.phase == .voting)
        // The fixture's ballot is split across two targets — the wire shape
        // the split-ballot UI builds on.
        let ballots = state.currentVote?.votes?.values.first
        #expect(ballots?.count == 2)
        #expect(state.currentVote?.cardsSpent == ["vote", "extra_vote"])
    }

    @Test func immunityPhaseCarriesProtection() throws {
        let state = try load("tribal_immunity")
        #expect(state.currentVote?.phase == .immunity)
        #expect(state.players.values.contains { $0.immunityIdolProtection })
    }

    @Test func tieBreakStateSurfacesTiedPlayers() throws {
        let state = try load("tribal_reveal_tie")
        #expect(state.currentVote?.tieBreakNeeded == true)
        #expect(state.currentVote?.tiedPlayers?.count == 2)
    }

    @Test func challengePresenceNeverBricksDecode() throws {
        let state = try load("challenge_active")
        #expect(state.challenge != nil)
        #expect(state.challenge?.type?.isEmpty == false)
        #expect(state.expansion == true)
    }

    @Test func interactionPresenceNeverBricksDecode() throws {
        let state = try load("interaction_active")
        #expect(state.interaction != nil)
        #expect(state.interaction?.awaiting?.isEmpty == false)
    }

    @Test func pendingTheftWindowDecodes() throws {
        let state = try load("pending_theft_open")
        #expect(state.pendingTheft?.reactiveWindowOpen == true)
        #expect(state.pendingTheft?.targetId != nil)
    }

    @Test func legacySavesWithoutSettingsStillDecode() throws {
        let state = try load("legacy_no_settings")
        #expect(state.settings == nil)
        #expect(state.phase == .playing)
    }

    @Test func eventLogRidesAlong() throws {
        let state = try load("playing_midturn")
        #expect(state.eventLog?.first?.msg?.contains("drew a card") == true)
    }

    @Test func unknownTribalPhaseLandsOnWaitingNotAThrow() throws {
        let json = """
        {"id": "x", "phase": "tribal_council",
         "players": {"p1": {"id": "p1", "name": "Ana", "color": "#FF6B6B"}},
         "turnOrder": ["p1"], "currentTurnIndex": 0,
         "currentVote": {"phase": "some_future_phase"}}
        """.data(using: .utf8)!
        let state = try JSONDecoder().decode(GameState.self, from: json)
        #expect(state.currentVote?.phase == .waiting)
    }

    enum FixtureError: Error { case missing(String) }
}

private final class BundleToken {}
