import Foundation

struct TribalVoteState: Codable, Equatable {
    var type: String?
    var phase: TribalPhase
    var voteType: String?
    var councilLeaderId: String?
    var votes: [String: [String: Int]]?
    var voteResults: [String: Int]?
    var protectedPlayers: [String]?
    var immunityPlayed: [ImmunityRecord]?
    var tieBreakNeeded: Bool
    var tiedPlayers: [String]?
    var eliminated: [String]?
    var eliminationsNeeded: Int?
    var tieBreakResolvedBy: String?
    var advantageCardsPlayed: [AdvantageRecord]?
    var cardsSpent: [String]?

    /// One played Immunity Idol. The server appends dictionaries here
    /// (survivor_server.py `play_immunity`), not player-id strings — so
    /// decoding this as `[String]` always threw, the `try?` swallowed it, and
    /// the "Immunity Played" panel silently never rendered. Nobody could see
    /// that an idol had been played, which is also what an Idol Nullifier
    /// holder needs in order to answer one.
    struct ImmunityRecord: Codable, Equatable {
        let playerId: String?
        let targetId: String?

        enum CodingKeys: String, CodingKey {
            case playerId, targetId
        }
    }

    struct AdvantageRecord: Codable, Equatable {
        let playerId: String?
        let advantageType: String?
        let targetId: String?

        // The server writes short keys (rules_engine.py advantageCardsPlayed).
        enum CodingKeys: String, CodingKey {
            case playerId = "player"
            case advantageType = "type"
            case targetId = "target"
        }
    }

    enum CodingKeys: String, CodingKey {
        case type, phase, voteType, councilLeaderId, votes, voteResults
        case protectedPlayers, immunityPlayed, tieBreakNeeded, tiedPlayers
        case eliminated, eliminationsNeeded, tieBreakResolvedBy
        case advantageCardsPlayed, cardsSpent
    }

    /// Lenient by construction: a council mid-anything must never brick the
    /// whole GameState decode. Missing/unknown phase → .waiting.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try? c.decodeIfPresent(String.self, forKey: .type)
        phase = (try? c.decodeIfPresent(TribalPhase.self, forKey: .phase)) ?? .waiting
        voteType = try? c.decodeIfPresent(String.self, forKey: .voteType)
        councilLeaderId = try? c.decodeIfPresent(String.self, forKey: .councilLeaderId)
        votes = try? c.decodeIfPresent([String: [String: Int]].self, forKey: .votes)
        voteResults = try? c.decodeIfPresent([String: Int].self, forKey: .voteResults)
        protectedPlayers = try? c.decodeIfPresent([String].self, forKey: .protectedPlayers)
        immunityPlayed = try? c.decodeIfPresent([ImmunityRecord].self, forKey: .immunityPlayed)
        tieBreakNeeded = (try? c.decodeIfPresent(Bool.self, forKey: .tieBreakNeeded)) ?? false
        tiedPlayers = try? c.decodeIfPresent([String].self, forKey: .tiedPlayers)
        eliminated = try? c.decodeIfPresent([String].self, forKey: .eliminated)
        eliminationsNeeded = try? c.decodeIfPresent(Int.self, forKey: .eliminationsNeeded)
        tieBreakResolvedBy = try? c.decodeIfPresent(String.self, forKey: .tieBreakResolvedBy)
        advantageCardsPlayed = try? c.decodeIfPresent([AdvantageRecord].self, forKey: .advantageCardsPlayed)
        cardsSpent = try? c.decodeIfPresent([String].self, forKey: .cardsSpent)
    }

    init(
        type: String? = nil, phase: TribalPhase = .waiting, voteType: String? = nil,
        councilLeaderId: String? = nil, votes: [String: [String: Int]]? = nil,
        voteResults: [String: Int]? = nil, protectedPlayers: [String]? = nil,
        immunityPlayed: [ImmunityRecord]? = nil, tieBreakNeeded: Bool = false,
        tiedPlayers: [String]? = nil, eliminated: [String]? = nil,
        eliminationsNeeded: Int? = nil, tieBreakResolvedBy: String? = nil,
        advantageCardsPlayed: [AdvantageRecord]? = nil, cardsSpent: [String]? = nil
    ) {
        self.type = type
        self.phase = phase
        self.voteType = voteType
        self.councilLeaderId = councilLeaderId
        self.votes = votes
        self.voteResults = voteResults
        self.protectedPlayers = protectedPlayers
        self.immunityPlayed = immunityPlayed
        self.tieBreakNeeded = tieBreakNeeded
        self.tiedPlayers = tiedPlayers
        self.eliminated = eliminated
        self.eliminationsNeeded = eliminationsNeeded
        self.tieBreakResolvedBy = tieBreakResolvedBy
        self.advantageCardsPlayed = advantageCardsPlayed
        self.cardsSpent = cardsSpent
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
