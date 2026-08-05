import Testing
import SwiftUI
@testable import SurvivorGame

/// An immune player's uncounted tally used to draw a bar out of proportion
/// to a real, counted tally next to it (QA repro: an immune "3" bar reading
/// far longer than 3x an eliminated "1" bar). `VoteBarScale.fraction` is the
/// math `VoteResultRow` draws from; these pin it directly, independent of
/// the view and its `GeometryReader`.
@Suite("Vote reveal bar scaling")
struct VoteBarScaleTests {

    @Test("The exact QA repro: an immune 3-vote row and an eliminated 1-vote row")
    func immuneAndEliminatedRowsScaleHonestly() {
        let maxVotes = 3 // the largest count across BOTH rows, per VoteRevealView.maxVotes
        let immuneFraction = VoteBarScale.fraction(votes: 3, maxVotes: maxVotes)
        let eliminatedFraction = VoteBarScale.fraction(votes: 1, maxVotes: maxVotes)

        #expect(immuneFraction == 1.0)
        #expect(eliminatedFraction.isApproximatelyEqual(to: 1.0 / 3.0))
        // The immune row legitimately drew more raw votes, so it's allowed
        // to be longer — the point is the RATIO, not who wins.
        #expect(immuneFraction / eliminatedFraction == 3)
    }

    @Test("An eliminated row with MORE votes than an immune row draws longer — proportion, not a fixed winner")
    func eliminatedCanLegitimatelyBeLonger() {
        let maxVotes = 4
        let eliminatedFraction = VoteBarScale.fraction(votes: 4, maxVotes: maxVotes)
        let immuneFraction = VoteBarScale.fraction(votes: 1, maxVotes: maxVotes)

        #expect(eliminatedFraction == 1.0)
        #expect(immuneFraction == 0.25)
        #expect(eliminatedFraction > immuneFraction)
    }

    @Test("A tie draws identical bars")
    func tiedRowsMatch() {
        #expect(VoteBarScale.fraction(votes: 2, maxVotes: 2)
                == VoteBarScale.fraction(votes: 2, maxVotes: 2))
    }

    @Test("Zero votes draws no bar at all, even against a real max")
    func zeroVotesDrawsNothing() {
        #expect(VoteBarScale.fraction(votes: 0, maxVotes: 5) == 0)
    }

    @Test("A maxVotes of zero — a reveal with no votes at all — never divides by zero")
    func guardsAgainstZeroMax() {
        #expect(VoteBarScale.fraction(votes: 0, maxVotes: 0) == 0)
    }

    @Test("The winning row always fills its full track")
    func maxRowFillsCompletely() {
        #expect(VoteBarScale.fraction(votes: 5, maxVotes: 5) == 1.0)
    }
}

private extension CGFloat {
    func isApproximatelyEqual(to other: CGFloat, tolerance: CGFloat = 0.0001) -> Bool {
        abs(self - other) < tolerance
    }
}
