import Foundation

struct TribalVoteState: Codable, Equatable {
    var type: String?
    var phase: TribalPhase
    var voteType: String?
    var councilLeaderId: String?
    var votes: [String: [String: Int]]?
    var voteResults: [String: Int]?
    var protectedPlayers: [String]?
    var immunityPlayed: [String]?
    var tieBreakNeeded: Bool
    var tiedPlayers: [String]?
    var eliminated: [String]?
    var tieBreakResolvedBy: String?
    var advantageCardsPlayed: [AdvantageRecord]?

    struct AdvantageRecord: Codable, Equatable {
        let playerId: String
        let advantageType: String
        let targetId: String?
    }

    var isVotingPhase: Bool {
        phase == .voting
    }

    var isRevealPhase: Bool {
        phase == .reveal
    }

    var eliminatedPlayers: [String] {
        eliminated ?? []
    }
}
