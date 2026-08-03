import Foundation
import UIKit

/// A named spot at camp. During `playing` everyone drifts between the open
/// places — who slipped off with whom is deliberately public, it is the
/// paranoia engine. Tribal Council forces one place and nobody may leave it,
/// except during its discussion, when camp reopens for exactly as long as the
/// scheming lasts. A snuffed torch goes to Exile Island until the Final
/// Tribal Council brings everyone back together.
///
/// The wire vocabulary is the server's snake_case key; this type owns the
/// key → label and key → SF Symbol mappings so no view has to.
enum Place: String, CaseIterable, Identifiable, Sendable {
    case campFire = "camp_fire"
    case theBeach = "the_beach"
    case theWaterWell = "the_water_well"
    case tribalCouncil = "tribal_council"
    case exileIsland = "exile_island"

    var id: String { rawValue }

    /// The server's wire key for this place.
    var key: String { rawValue }

    var label: String {
        switch self {
        case .campFire: "Camp Fire"
        case .theBeach: "The Beach"
        case .theWaterWell: "The Water Well"
        case .tribalCouncil: "Tribal Council"
        case .exileIsland: "Exile Island"
        }
    }

    var symbolName: String {
        switch self {
        case .campFire: "flame.fill"
        case .theBeach: Place.beachSymbol
        case .theWaterWell: "drop.fill"
        case .tribalCouncil: "person.3.fill"
        case .exileIsland: "moon.stars.fill"
        }
    }

    /// Where a player stands when the server hasn't said — the fire is the
    /// island's default gathering point, and `place` is only absent on states
    /// written before this feature existed.
    static let fallback = Place.campFire

    /// `beach.umbrella.fill` is an SF Symbols 4 glyph. Resolve it once at
    /// runtime rather than trusting a deployment-target table: a missing
    /// symbol renders as a silent blank, which would read as a bug.
    static let beachSymbol: String = {
        UIImage(systemName: "beach.umbrella.fill") != nil ? "beach.umbrella.fill" : "water.waves"
    }()

    /// The display name for any key the server sends — including one this
    /// build has never heard of, which is titleised rather than dropped.
    static func label(for key: String) -> String {
        if let known = Place(rawValue: key) { return known.label }
        return key.split(separator: "_").map(\.capitalized).joined(separator: " ")
    }

    /// The icon for any key the server sends; unknown places get a map pin.
    static func symbolName(for key: String) -> String {
        Place(rawValue: key)?.symbolName ?? "mappin.and.ellipse"
    }
}

/// Which places are open right now, and whether the ceremony has pinned
/// everyone to one of them. Absent from the state entirely on older servers —
/// decoded leniently, and the UI simply hides itself when it's nil.
struct PlacePolicy: Codable, Equatable, Sendable {
    /// The places players may move between. Empty means nobody moves.
    var open: [String]
    /// When set, every player is held here and no move is allowed.
    var forced: String?

    enum CodingKeys: String, CodingKey {
        case open, forced
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        open = (try? c.decode([String].self, forKey: .open)) ?? []
        forced = try? c.decodeIfPresent(String.self, forKey: .forced)
    }

    init(open: [String], forced: String? = nil) {
        self.open = open
        self.forced = forced
    }

    /// The ceremony is on: one place, no choices.
    var isForced: Bool { forced != nil }

    /// The rows the UI draws — the forced place alone, or every open place.
    var visibleKeys: [String] {
        if let forced { return [forced] }
        return open
    }

    /// Whether tapping `key` should send a move. The server is the authority
    /// and will refuse anything else; this only keeps dead taps off screen.
    func canMove(to key: String, from current: String?) -> Bool {
        guard forced == nil, open.contains(key) else { return false }
        return key != current
    }
}
