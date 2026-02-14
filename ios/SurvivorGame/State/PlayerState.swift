import Foundation
import SwiftUI

struct PlayerState: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let color: String
    var hand: [CardInstance]
    var isEliminated: Bool
    var isActive: Bool
    var isCouncilLeader: Bool
    var hasStolen: Bool
    var hasVoted: Bool
    var extraVotes: Int
    var characterCards: Int
    var immunityPlayed: Bool
    var voteBanned: Bool?

    var swiftUIColor: Color {
        Color(hex: color) ?? .gray
    }

    var handCount: Int { hand.count }

    var isAlive: Bool { !isEliminated }

    enum CodingKeys: String, CodingKey {
        case id, name, color, hand, isEliminated, isActive, isCouncilLeader
        case hasStolen, hasVoted, extraVotes, characterCards, immunityPlayed, voteBanned
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        color = try container.decode(String.self, forKey: .color)
        hand = try container.decodeIfPresent([CardInstance].self, forKey: .hand) ?? []
        isEliminated = try container.decodeIfPresent(Bool.self, forKey: .isEliminated) ?? false
        isActive = try container.decodeIfPresent(Bool.self, forKey: .isActive) ?? true
        isCouncilLeader = try container.decodeIfPresent(Bool.self, forKey: .isCouncilLeader) ?? false
        hasStolen = try container.decodeIfPresent(Bool.self, forKey: .hasStolen) ?? false
        hasVoted = try container.decodeIfPresent(Bool.self, forKey: .hasVoted) ?? false
        extraVotes = try container.decodeIfPresent(Int.self, forKey: .extraVotes) ?? 0
        characterCards = try container.decodeIfPresent(Int.self, forKey: .characterCards) ?? 2
        immunityPlayed = try container.decodeIfPresent(Bool.self, forKey: .immunityPlayed) ?? false
        voteBanned = try container.decodeIfPresent(Bool.self, forKey: .voteBanned)
    }
}

struct CardInstance: Codable, Equatable, Identifiable {
    let type: String
    var category: String?
    var name: String?
    var description: String?
    var playablePhases: [String]?
    var requiresTarget: Bool?
    var requiresMultipleTargets: Bool?
    var requiresConfirmation: Bool?
    var reactiveOnly: Bool?

    /// Stable identity: type + position-based (set externally)
    var id: String { type + (name ?? "") }

    enum CodingKeys: String, CodingKey {
        case type, category, name, description
        case playablePhases = "playable_phases"
        case requiresTarget = "requires_target"
        case requiresMultipleTargets = "requires_multiple_targets"
        case requiresConfirmation = "requires_confirmation"
        case reactiveOnly = "reactive_only"
    }

    var displayName: String { name ?? type.replacingOccurrences(of: "_", with: " ").capitalized }

    var cardCategory: CardCategory {
        CardCategory(rawValue: category ?? "") ?? .action
    }
}

enum CardCategory: String, Codable {
    case vote
    case tribalAdvantage = "tribal_advantage"
    case action
    case tribalCouncil = "tribal_council"

    var displayName: String {
        switch self {
        case .vote: return "Vote"
        case .tribalAdvantage: return "Tribal Advantage"
        case .action: return "Action"
        case .tribalCouncil: return "Tribal Council"
        }
    }

    var color: Color {
        switch self {
        case .vote: return .blue
        case .tribalAdvantage: return .purple
        case .action: return .orange
        case .tribalCouncil: return .red
        }
    }
}

// MARK: - Color Extension

extension Color {
    /// Creates a Color from a hex string (e.g., "#FF6B6B" or "FF6B6B")
    /// Returns nil if the hex string is invalid
    init?(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        
        // Validate hex string can be scanned
        guard Scanner(string: hex).scanHexInt64(&int) else {
            return nil
        }
        
        let a, r, g, b: UInt64
        switch hex.count {
        case 6:
            (a, r, g, b) = (255, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = ((int >> 24) & 0xFF, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            return nil
        }
        
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}
