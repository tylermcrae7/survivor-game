import Testing
@testable import SurvivorGame

/// The ballot headline's one invariant: any number it leads with must never
/// contradict the total the player can actually cast. The two-line version
/// broke it live — "you cast 2 votes tonight" over "you hold 1 Extra Vote"
/// while Tyler went on to cast 3 (game 3851c768, council 0).
struct BallotHeadlineTests {
    @Test func anOrdinaryHandGetsNoHeadline() {
        #expect(BallotHeadline.text(mandatory: 1, extras: 0) == nil)
    }

    @Test func extrasAloneReadAsTheyAlwaysHave() {
        #expect(BallotHeadline.text(mandatory: 1, extras: 1) == "You hold 1 Extra Vote")
        #expect(BallotHeadline.text(mandatory: 1, extras: 2) == "You hold 2 Extra Votes")
    }

    @Test func aTakenVoteAloneStatesTheBox() {
        let line = BallotHeadline.text(mandatory: 2, extras: 0)
        #expect(line == "You cast 2 votes tonight — every Vote Card you hold goes in the box")
    }

    /// The live failure case: both kinds in one hand must name the ceiling.
    @Test func aCombinedHandNamesTheCeiling() {
        #expect(BallotHeadline.text(mandatory: 2, extras: 1)
                == "You cast 2 votes tonight — your 1 Extra Vote can make it 3")
        #expect(BallotHeadline.text(mandatory: 2, extras: 2)
                == "You cast 2 votes tonight — your 2 Extra Votes can make it 4")
    }
}
