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

enum TurnPhase: String, Codable, Equatable {
    case steal = "turn_steal"
    case play = "turn_play"
    case draw = "turn_draw"
}

enum TribalPhase: String, Codable, Equatable {
    case waiting
    case announcement
    case advantagePlay = "advantage_play"
    case discussion = "tribal_discussion"
    case immunity = "tribal_immunity"
    case voting = "tribal_voting"
    case reveal = "tribal_reveal"
}

enum FinalTribalPhase: String, Codable, Equatable {
    case waiting
    case questions
    case deliberation
    case voting
    case reveal
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
