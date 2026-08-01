import Foundation

/// One player's revealed pick. The server writes whatever the interaction type
/// uses into the same `picks` map: Do Or Die stores a throw string
/// (`"rock"`/`"paper"`/`"scissors"`, interactions.py `RPS_THROWS`), Power Pair
/// and It's A Numbers Game store an integer finger count.
enum InteractionPick: Equatable, Codable {
    case throwName(String)
    case fingers(Int)

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        // Int first: a JSON number must not be read as text.
        if let number = try? c.decode(Int.self) {
            self = .fingers(number)
        } else if let text = try? c.decode(String.self) {
            self = .throwName(text)
        } else {
            throw DecodingError.typeMismatch(
                InteractionPick.self,
                .init(codingPath: decoder.codingPath,
                      debugDescription: "A pick is a throw name or a finger count"))
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .throwName(let text): try c.encode(text)
        case .fingers(let number): try c.encode(number)
        }
    }

    /// "threw rock" / "held up 3 fingers" — the human sentence for the reveal.
    var revealPhrase: String {
        switch self {
        case .throwName(let text): "threw \(text)"
        case .fingers(1): "held up 1 finger"
        case .fingers(let number): "held up \(number) fingers"
        }
    }

    /// The bare value, for a compact trailing column.
    var displayValue: String {
        switch self {
        case .throwName(let text): text
        case .fingers(let number): "\(number)"
        }
    }
}

/// The last resolved round of an interaction (`interactions.py` writes
/// `{"round": int, "picks": {playerId: pick}, "outcome": str}` from
/// `_next_round` and each `_resolve_*`).
struct InteractionRound: Codable, Equatable {
    var round: Int?
    var picks: [String: InteractionPick]?
    /// NOT display copy — `_resolve_do_or_die`/`_resolve_numbers_game` write a
    /// raw player id into it ("p3 wins"). Kept for completeness; the reveal
    /// renders `interaction.prompt` instead.
    var outcome: String?

    enum CodingKeys: String, CodingKey {
        case round, picks, outcome
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        round = try? c.decodeIfPresent(Int.self, forKey: .round)
        picks = try? c.decodeIfPresent([String: InteractionPick].self, forKey: .picks)
        outcome = try? c.decodeIfPresent(String.self, forKey: .outcome)
    }
}

/// Public shape of `game.interaction` — a Reward Challenge minigame
/// (Do Or Die rock-paper-scissors, Power Pair / Numbers Game fingers).
/// Secrets are stripped server-side; lenient by construction.
struct InteractionState: Codable, Equatable {
    var type: String?
    var name: String?
    var phase: String?
    var prompt: String?
    var round: Int?
    var awaiting: [String]?
    var participants: [String]?
    var initiatorId: String?
    var targetId: String?
    /// The current round's reveal — empty while picks are still secret
    /// (`_picks` is stripped by `get_game_state`; `picks` fills in at
    /// `_resolve_picks`).
    var picks: [String: InteractionPick]?
    var lastRound: InteractionRound?
    /// Only It's A Numbers Game records a winner (`_resolve_numbers_game`).
    var winnerId: String?

    enum CodingKeys: String, CodingKey {
        case type, name, phase, prompt, round, awaiting, participants
        case initiatorId, targetId, picks, lastRound, winnerId
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try? c.decodeIfPresent(String.self, forKey: .type)
        name = try? c.decodeIfPresent(String.self, forKey: .name)
        phase = try? c.decodeIfPresent(String.self, forKey: .phase)
        prompt = try? c.decodeIfPresent(String.self, forKey: .prompt)
        round = try? c.decodeIfPresent(Int.self, forKey: .round)
        awaiting = try? c.decodeIfPresent([String].self, forKey: .awaiting)
        participants = try? c.decodeIfPresent([String].self, forKey: .participants)
        initiatorId = try? c.decodeIfPresent(String.self, forKey: .initiatorId)
        targetId = try? c.decodeIfPresent(String.self, forKey: .targetId)
        // Reveal data is best-effort: an unfamiliar pick shape must degrade to
        // an outcome-only reveal, never brick the whole GameState decode.
        picks = try? c.decodeIfPresent([String: InteractionPick].self, forKey: .picks)
        lastRound = try? c.decodeIfPresent(InteractionRound.self, forKey: .lastRound)
        winnerId = try? c.decodeIfPresent(String.self, forKey: .winnerId)
    }

    var isComplete: Bool { phase == "complete" }

    /// What the table should see at the reveal: the round that just resolved,
    /// falling back to the live `picks` map (web parity, ui.js
    /// `showInteractionReveal`).
    var revealedPicks: [String: InteractionPick] {
        if let last = lastRound?.picks, !last.isEmpty { return last }
        return picks ?? [:]
    }
}
