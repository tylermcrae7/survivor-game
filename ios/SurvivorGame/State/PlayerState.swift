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
    var hasPlayed: Bool
    var hasDrawn: Bool
    var hasVoted: Bool
    var extraVotes: Int
    var characterCards: Int
    var immunityPlayed: Bool
    var voteBanned: Bool?
    var isBot: Bool
    var maxVotes: Int?
    var mandatoryVotes: Int?
    var goodwillVotes: Int?
    var drawBonus: Int?
    var stealBonus: Int?
    var immunityIdolProtection: Bool
    var campRaidedBy: String?
    var inheritanceTarget: String?
    /// Which named place this player is standing in (`camp_fire`, `the_beach`,
    /// `the_water_well`, `tribal_council`). Always present on current servers;
    /// optional here so an older state can't brick the decode.
    var place: String?
    /// The Discord account this player has claimed, for the voice-channel
    /// mirror. Absent for anyone who never set one, and for every bot.
    var discordUserId: String?

    /// The place this player occupies, falling back to the fire when the
    /// server said nothing.
    var placeKey: String { place ?? Place.fallback.key }

    var swiftUIColor: Color {
        Color(hex: color) ?? .gray
    }

    var handCount: Int { hand.count }

    var isAlive: Bool { !isEliminated }

    /// Where this player is in the official turn: steal → play → draw → done.
    var turnPhase: TurnPhase {
        if !hasStolen { return .steal }
        if hasDrawn { return .done }
        if hasPlayed { return .draw }
        return .play
    }

    enum CodingKeys: String, CodingKey {
        case id, name, color, hand, isEliminated, isActive, isCouncilLeader
        case hasStolen, hasPlayed, hasDrawn, hasVoted, extraVotes, characterCards
        case immunityPlayed, voteBanned, isBot, maxVotes, mandatoryVotes
        case goodwillVotes, drawBonus, stealBonus, immunityIdolProtection
        case campRaidedBy, inheritanceTarget, place, discordUserId
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
        hasPlayed = try container.decodeIfPresent(Bool.self, forKey: .hasPlayed) ?? false
        hasDrawn = try container.decodeIfPresent(Bool.self, forKey: .hasDrawn) ?? false
        hasVoted = try container.decodeIfPresent(Bool.self, forKey: .hasVoted) ?? false
        extraVotes = try container.decodeIfPresent(Int.self, forKey: .extraVotes) ?? 0
        characterCards = try container.decodeIfPresent(Int.self, forKey: .characterCards) ?? 2
        immunityPlayed = try container.decodeIfPresent(Bool.self, forKey: .immunityPlayed) ?? false
        voteBanned = try container.decodeIfPresent(Bool.self, forKey: .voteBanned)
        isBot = try container.decodeIfPresent(Bool.self, forKey: .isBot) ?? false
        maxVotes = try container.decodeIfPresent(Int.self, forKey: .maxVotes)
        mandatoryVotes = try container.decodeIfPresent(Int.self, forKey: .mandatoryVotes)
        goodwillVotes = try container.decodeIfPresent(Int.self, forKey: .goodwillVotes)
        drawBonus = try container.decodeIfPresent(Int.self, forKey: .drawBonus)
        stealBonus = try container.decodeIfPresent(Int.self, forKey: .stealBonus)
        immunityIdolProtection = try container.decodeIfPresent(Bool.self, forKey: .immunityIdolProtection) ?? false
        campRaidedBy = try container.decodeIfPresent(String.self, forKey: .campRaidedBy)
        inheritanceTarget = try container.decodeIfPresent(String.self, forKey: .inheritanceTarget)
        place = try? container.decodeIfPresent(String.self, forKey: .place)
        discordUserId = try? container.decodeIfPresent(String.self, forKey: .discordUserId)
    }

    /// Designated memberwise init for tests and previews (extension inits in
    /// other files can't assign `let` stored properties).
    init(
        id: String, name: String, color: String,
        hand: [CardInstance] = [], isEliminated: Bool = false,
        isActive: Bool = true, isCouncilLeader: Bool = false,
        hasStolen: Bool = false, hasPlayed: Bool = false, hasDrawn: Bool = false,
        hasVoted: Bool = false, extraVotes: Int = 0, characterCards: Int = 2,
        immunityPlayed: Bool = false, voteBanned: Bool? = nil, isBot: Bool = false,
        maxVotes: Int? = nil, mandatoryVotes: Int? = nil, goodwillVotes: Int? = nil,
        drawBonus: Int? = nil, stealBonus: Int? = nil,
        immunityIdolProtection: Bool = false, campRaidedBy: String? = nil,
        inheritanceTarget: String? = nil, place: String? = nil,
        discordUserId: String? = nil
    ) {
        self.id = id
        self.name = name
        self.color = color
        self.hand = hand
        self.isEliminated = isEliminated
        self.isActive = isActive
        self.isCouncilLeader = isCouncilLeader
        self.hasStolen = hasStolen
        self.hasPlayed = hasPlayed
        self.hasDrawn = hasDrawn
        self.hasVoted = hasVoted
        self.extraVotes = extraVotes
        self.characterCards = characterCards
        self.immunityPlayed = immunityPlayed
        self.voteBanned = voteBanned
        self.isBot = isBot
        self.maxVotes = maxVotes
        self.mandatoryVotes = mandatoryVotes
        self.goodwillVotes = goodwillVotes
        self.drawBonus = drawBonus
        self.stealBonus = stealBonus
        self.immunityIdolProtection = immunityIdolProtection
        self.campRaidedBy = campRaidedBy
        self.inheritanceTarget = inheritanceTarget
        self.place = place
        self.discordUserId = discordUserId
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
    case challenge
    case house

    var displayName: String {
        switch self {
        case .vote: return "Vote"
        case .tribalAdvantage: return "Tribal Advantage"
        case .action: return "Action"
        case .tribalCouncil: return "Tribal Council"
        case .challenge: return "Challenge"
        case .house: return "House"
        }
    }

    var color: Color {
        switch self {
        case .vote: return .blue
        case .tribalAdvantage: return .purple
        case .action: return .orange
        case .tribalCouncil: return .red
        case .challenge: return Color(hex: "#e8862a") ?? .orange
        case .house: return .teal
        }
    }

    /// The web's per-category 4px card-rule gradient (research §Playing
    /// cards): a left-to-right two-stop wash across the card's top edge.
    var torchGradient: LinearGradient {
        let stops: (Color, Color) = switch self {
        case .action:          (Color(hex: "#579766") ?? .green, Color(hex: "#237356") ?? .green)
        case .tribalAdvantage: (Color(hex: "#D8B349") ?? .yellow, Color(hex: "#C48225") ?? .yellow)
        case .vote:            (Color(hex: "#DDCCA9") ?? .gray, Color(hex: "#AD9D7B") ?? .gray)
        case .challenge:       (Color(hex: "#F3821D") ?? .orange, Color(hex: "#D84A00") ?? .orange)
        case .tribalCouncil, .house: (Torch.Color.textFaint, Torch.Color.textFaint)
        }
        return LinearGradient(colors: [stops.0, stops.1], startPoint: .leading, endPoint: .trailing)
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
