import Foundation

/// Public shape of `game.interaction` — a Reward Challenge minigame
/// (Do Or Die rock-paper-scissors, Power Pair / Numbers Game fingers).
/// Secrets are stripped server-side; lenient by construction.
struct InteractionState: Codable, Equatable {
    var type: String?
    var phase: String?
    var prompt: String?
    var round: Int?
    var awaiting: [String]?
    var participants: [String]?
    var initiatorId: String?
    var targetId: String?

    enum CodingKeys: String, CodingKey {
        case type, phase, prompt, round, awaiting, participants
        case initiatorId, targetId
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try? c.decodeIfPresent(String.self, forKey: .type)
        phase = try? c.decodeIfPresent(String.self, forKey: .phase)
        prompt = try? c.decodeIfPresent(String.self, forKey: .prompt)
        round = try? c.decodeIfPresent(Int.self, forKey: .round)
        awaiting = try? c.decodeIfPresent([String].self, forKey: .awaiting)
        participants = try? c.decodeIfPresent([String].self, forKey: .participants)
        initiatorId = try? c.decodeIfPresent(String.self, forKey: .initiatorId)
        targetId = try? c.decodeIfPresent(String.self, forKey: .targetId)
    }
}
