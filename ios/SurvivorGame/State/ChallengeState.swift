import Foundation

/// Public shape of `game.challenge` — a running Let's Go To Rocks Challenge.
/// The server strips every `_`-prefixed secret before the state leaves it, so
/// everything here is safe to render. Lenient by construction: an unfamiliar
/// challenge shape must never brick the GameState decode.
struct ChallengeState: Codable, Equatable {
    var type: String?
    var phase: String?
    var prompt: String?
    var currentPlayerId: String?
    var pending: [String]?
    var actions: [String]?
    var log: [String]?
    var scores: [String: Int]?
    var round: Int?
    var maxPull: Int?
    var stealTargets: [String]?
    var winnerId: String?
    var actionCount: Int?

    enum CodingKeys: String, CodingKey {
        case type, phase, prompt, currentPlayerId, pending, actions, log
        case scores, round, maxPull, stealTargets, winnerId, actionCount
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try? c.decodeIfPresent(String.self, forKey: .type)
        phase = try? c.decodeIfPresent(String.self, forKey: .phase)
        prompt = try? c.decodeIfPresent(String.self, forKey: .prompt)
        currentPlayerId = try? c.decodeIfPresent(String.self, forKey: .currentPlayerId)
        pending = try? c.decodeIfPresent([String].self, forKey: .pending)
        actions = try? c.decodeIfPresent([String].self, forKey: .actions)
        log = try? c.decodeIfPresent([String].self, forKey: .log)
        scores = try? c.decodeIfPresent([String: Int].self, forKey: .scores)
        round = try? c.decodeIfPresent(Int.self, forKey: .round)
        maxPull = try? c.decodeIfPresent(Int.self, forKey: .maxPull)
        stealTargets = try? c.decodeIfPresent([String].self, forKey: .stealTargets)
        winnerId = try? c.decodeIfPresent(String.self, forKey: .winnerId)
        actionCount = try? c.decodeIfPresent(Int.self, forKey: .actionCount)
    }

    var isComplete: Bool { phase == "complete" }
}
