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
    /// The Final Tribal Leader — the last juror seated, or the first finalist
    /// when there is no jury (survivor_server `_start_final_tribal_council`).
    /// The only player the server lets break a final tie. This is NOT the
    /// tribal council leader: `currentVote.councilLeaderId` is left over from
    /// the last ordinary council. Absent before the ceremony starts and on
    /// servers that predate it.
    var leader: String?
    /// The jury as seated for this ceremony. Absent before it starts.
    var jury: [String]?
    /// The official Final Tribal questions, in order. Absent on older servers.
    var questions: [String]?

    enum CodingKeys: String, CodingKey {
        case phase, finalists, votes, voteCounts, juryReady, tieBreakNeeded
        case tiedFinalists, tieBreakerLeader, tieBreakBy, winner
        case leader, jury, questions
    }

    /// Lenient by construction, like `TribalVoteState`: the server's pre-game
    /// placeholder carries only phase/finalists/voteCounts/tieBreakNeeded, and
    /// a shape this build has never seen must never brick the whole
    /// GameState decode. Missing/unknown phase → .waiting.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        phase = (try? c.decodeIfPresent(FinalTribalPhase.self, forKey: .phase)) ?? .waiting
        finalists = (try? c.decodeIfPresent([String].self, forKey: .finalists)) ?? []
        votes = try? c.decodeIfPresent([String: String].self, forKey: .votes)
        voteCounts = try? c.decodeIfPresent([String: Int].self, forKey: .voteCounts)
        juryReady = try? c.decodeIfPresent([String].self, forKey: .juryReady)
        tieBreakNeeded = (try? c.decodeIfPresent(Bool.self, forKey: .tieBreakNeeded)) ?? false
        tiedFinalists = try? c.decodeIfPresent([String].self, forKey: .tiedFinalists)
        tieBreakerLeader = try? c.decodeIfPresent(String.self, forKey: .tieBreakerLeader)
        tieBreakBy = try? c.decodeIfPresent(String.self, forKey: .tieBreakBy)
        winner = try? c.decodeIfPresent(String.self, forKey: .winner)
        leader = try? c.decodeIfPresent(String.self, forKey: .leader)
        jury = try? c.decodeIfPresent([String].self, forKey: .jury)
        questions = try? c.decodeIfPresent([String].self, forKey: .questions)
    }

    /// Designated memberwise init for tests and previews.
    init(
        phase: FinalTribalPhase = .waiting, finalists: [String] = [],
        votes: [String: String]? = nil, voteCounts: [String: Int]? = nil,
        juryReady: [String]? = nil, tieBreakNeeded: Bool = false,
        tiedFinalists: [String]? = nil, tieBreakerLeader: String? = nil,
        tieBreakBy: String? = nil, winner: String? = nil,
        leader: String? = nil, jury: [String]? = nil, questions: [String]? = nil
    ) {
        self.phase = phase
        self.finalists = finalists
        self.votes = votes
        self.voteCounts = voteCounts
        self.juryReady = juryReady
        self.tieBreakNeeded = tieBreakNeeded
        self.tiedFinalists = tiedFinalists
        self.tieBreakerLeader = tieBreakerLeader
        self.tieBreakBy = tieBreakBy
        self.winner = winner
        self.leader = leader
        self.jury = jury
        self.questions = questions
    }

    var allJuryVoted: Bool {
        guard let votes = votes, let juryReady = juryReady else { return false }
        return votes.count >= juryReady.count
    }
}
