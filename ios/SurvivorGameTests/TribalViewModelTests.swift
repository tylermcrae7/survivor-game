import Testing
import Foundation
@testable import SurvivorGame

/// The reveal must show the votes immunity erased — an immune player's
/// ballots are zeroed out of `voteResults` but remembered in
/// `rawVoteResults`. These pin `TribalViewModel.voteResults`, the merge point
/// `VoteRevealView` renders from.
@MainActor
struct TribalViewModelTests {

    private func makeViewModel(currentVote: TribalVoteState) -> TribalViewModel {
        let gameClient = GameClient(baseURL: URL(string: "http://localhost:3000")!)
        // applyState ignores pushes for a game we are not in (see
        // GameClient.applyState) — join the sample game first.
        gameClient.gameId = "test123"
        var state = MockGameClient.sampleGameState()
        state.currentVote = currentVote
        gameClient.applyState(state)
        return TribalViewModel(gameClient: gameClient)
    }

    @Test("An immune player with no counted votes still gets a row, from the raw tally")
    func immunePlayerAppearsAsARow() {
        let viewModel = makeViewModel(currentVote: TribalVoteState(
            phase: .reveal,
            voteResults: [:],
            rawVoteResults: ["p2": 3],
            protectedPlayers: ["p2"]
        ))
        let rows = viewModel.voteResults
        #expect(rows.count == 1)
        #expect(rows.first?.player.id == "p2")
        #expect(rows.first?.votes == 3)
        #expect(rows.first?.isImmune == true)
    }

    @Test("A counted result sits alongside the immune row, and neither is confused for the other")
    func countedAndImmuneRowsCoexist() {
        let viewModel = makeViewModel(currentVote: TribalVoteState(
            phase: .reveal,
            voteResults: ["p1": 2],
            rawVoteResults: ["p1": 2, "p2": 4],
            protectedPlayers: ["p2"]
        ))
        let rows = viewModel.voteResults
        #expect(rows.count == 2)
        // Sorted by votes descending, same as ever.
        #expect(rows[0].player.id == "p2")
        #expect(rows[0].votes == 4)
        #expect(rows[0].isImmune == true)
        #expect(rows[1].player.id == "p1")
        #expect(rows[1].votes == 2)
        #expect(rows[1].isImmune == false)
    }

    @Test("A protected player with zero raw votes gets no row at all")
    func protectedPlayerWithNoVotesGetsNoRow() {
        let viewModel = makeViewModel(currentVote: TribalVoteState(
            phase: .reveal,
            voteResults: [:],
            rawVoteResults: ["p2": 0],
            protectedPlayers: ["p2"]
        ))
        #expect(viewModel.voteResults.isEmpty)
    }

    @Test("An older server that never sends rawVoteResults renders exactly as before")
    func missingRawVoteResultsIsFineOnAnOlderServer() {
        let viewModel = makeViewModel(currentVote: TribalVoteState(
            phase: .reveal,
            voteResults: ["p1": 2],
            protectedPlayers: ["p2"]
        ))
        let rows = viewModel.voteResults
        #expect(rows.count == 1)
        #expect(rows.first?.player.id == "p1")
        #expect(rows.first?.isImmune == false)
    }

    @Test("Tied rows break by name, so every phone reveals them in the same order")
    func tiedRowsBreakByName() {
        let viewModel = makeViewModel(currentVote: TribalVoteState(
            phase: .reveal,
            voteResults: ["p3": 2, "p2": 1, "p1": 2]
        ))
        let ids = viewModel.voteResults.map { $0.player.id }
        // p1 Alice and p3 Charlie tie on 2 — alphabetical; p2 Bob trails.
        #expect(ids == ["p1", "p3", "p2"])
    }

    // MARK: - Final Tribal leader (P0: the ceremony's controls)

    /// p1 led the last ordinary council (`currentVote.councilLeaderId` in the
    /// sample state); the Final Tribal Leader is p3, the last juror.
    private func makeFinalViewModel(me: String, leader: String?) -> FinalTribalViewModel {
        let gameClient = GameClient(baseURL: URL(string: "http://localhost:3000")!)
        gameClient.gameId = "test123"
        gameClient.playerId = me
        var state = MockGameClient.sampleGameState()
        state.phase = .finalTribal
        state.jury = ["p3"]
        state.finalTribal = FinalTribalState(
            phase: .questions, finalists: ["p1", "p2"],
            leader: leader, jury: ["p3"],
            questions: ["What was your strategy coming into the game?"])
        gameClient.applyState(state)
        return FinalTribalViewModel(gameClient: gameClient)
    }

    @Test("The Final Tribal Leader gets the controls, not the last council's leader")
    func finalLeaderComesFromFinalTribal() {
        let leader = makeFinalViewModel(me: "p3", leader: "p3")
        #expect(leader.isFinalLeader == true)
        #expect(leader.isCouncilLeader == false, "the stale flag would have locked them out")
        #expect(leader.questions.count == 1)

        let staleCouncilLeader = makeFinalViewModel(me: "p1", leader: "p3")
        #expect(staleCouncilLeader.isCouncilLeader == true)
        #expect(staleCouncilLeader.isFinalLeader == false)
    }

    @Test("A server that predates finalTribal.leader falls back to the council-leader flag")
    func finalLeaderFallsBackOnAnOlderServer() {
        #expect(makeFinalViewModel(me: "p1", leader: nil).isFinalLeader == true)
        #expect(makeFinalViewModel(me: "p3", leader: nil).isFinalLeader == false)
    }

    // MARK: - isVoteBanned (I3: the ballot's quiet notice)

    /// Steal A Vote / Block A Vote never touch the eventLog or the narrator
    /// (S2) — the target's own ballot is the only place this ever surfaces,
    /// off the player's own `voteBanned` flag.
    @Test("A vote-banned player's view model knows it from their own flag alone")
    func voteBannedReflectsMyOwnFlag() {
        let gameClient = GameClient(baseURL: URL(string: "http://localhost:3000")!)
        // applyState ignores pushes for a game we are not in (see
        // GameClient.applyState) — join the sample game first.
        gameClient.gameId = "test123"
        gameClient.playerId = "p1"
        var state = MockGameClient.sampleGameState()
        state.players["p1"] = PlayerState(id: "p1", name: "Alice", color: "#FF6B6B",
                                          voteBanned: true)
        gameClient.applyState(state)
        let viewModel = TribalViewModel(gameClient: gameClient)
        #expect(viewModel.isVoteBanned == true)
    }

    @Test("An ordinary player — voteBanned absent or false — is not banned")
    func notVoteBannedByDefault() {
        let gameClient = GameClient(baseURL: URL(string: "http://localhost:3000")!)
        // applyState ignores pushes for a game we are not in (see
        // GameClient.applyState) — join the sample game first.
        gameClient.gameId = "test123"
        gameClient.playerId = "p1"
        gameClient.applyState(MockGameClient.sampleGameState())
        let viewModel = TribalViewModel(gameClient: gameClient)
        #expect(viewModel.isVoteBanned == false)
    }
}
