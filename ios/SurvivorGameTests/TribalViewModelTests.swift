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
}
