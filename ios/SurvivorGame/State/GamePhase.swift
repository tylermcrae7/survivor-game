import Foundation

enum GamePhase: String, Codable, Equatable {
    case lobby
    case playing
    case tribalCouncil = "tribal_council"
    case finalTribal = "final_tribal"
    case finished

    // Alias: server sometimes sends "final" instead of "final_tribal"
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        switch raw {
        case "lobby": self = .lobby
        case "playing": self = .playing
        case "tribal_council": self = .tribalCouncil
        case "final", "final_tribal": self = .finalTribal
        case "finished": self = .finished
        default: self = .lobby
        }
    }
}

/// The server's turn machine: steal → play (one card, optional) → draw, and the
/// draw ENDS the turn (there is no End Turn affordance anywhere).
enum TurnPhase: String, Codable, Equatable {
    case steal = "turn_steal"
    case play = "turn_play"
    case draw = "turn_draw"
    case done = "turn_done"
    case waiting

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = TurnPhase(rawValue: raw) ?? .waiting
    }
}

/// Raw values are the SERVER's currentVote.phase strings — bare words, no
/// prefix. (The old `tribal_voting`-style raws threw the moment any council
/// reached voting and bricked the whole GameState decode.) Unknown phases the
/// server grows later land on .waiting instead of throwing.
enum TribalPhase: String, Codable, Equatable {
    case waiting
    case announcement
    case advantagePlay = "advantage_play"
    case discussion
    case voting
    case immunity
    case reveal

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = TribalPhase(rawValue: raw) ?? .waiting
    }
}

enum FinalTribalPhase: String, Codable, Equatable {
    case waiting
    case questions
    case deliberation
    case voting
    case reveal

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = FinalTribalPhase(rawValue: raw) ?? .waiting
    }
}

/// Navigation state derived from GamePhase + local context
enum NavigationState: Equatable {
    case start
    case lobby
    case playing
    case tribal
    case finalTribal
    case finished
}
