import Foundation

struct FinalTribalState: Codable, Equatable {
    var phase: FinalTribalPhase
    var finalists: [String]
    var votes: [String: String]?
    var voteCounts: [String: Int]?
    var juryReady: [String]?
    var tieBreakNeeded: Bool
    var tiedFinalists: [String]?
    var tieBreakerLeader: String?
    var tieBreakBy: String?
    var winner: String?

    var allJuryVoted: Bool {
        guard let votes = votes, let juryReady = juryReady else { return false }
        return votes.count >= juryReady.count
    }
}
