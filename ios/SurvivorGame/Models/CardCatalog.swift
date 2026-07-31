import Foundation
import Observation

/// The card registry. Hands arrive from the server as bare `{"type": …}`
/// stubs — this catalog turns a stub into a full card (name, category,
/// playable phases) for rendering and playability checks.
///
/// Seeded synchronously from the bundled `survivor_cards.json`, refreshed
/// opportunistically from `/api/cards` so new server cards appear without an
/// app update. Replaces the never-wired SwiftData CardDefinition path.
@MainActor
@Observable
final class CardCatalog {
    static let shared = CardCatalog()

    private(set) var cards: [String: CardInstance] = [:]

    init() {
        loadBundled()
    }

    /// A full card for a bare hand stub. Unknown types pass through untouched
    /// (they still render by prettified type name).
    func resolve(_ card: CardInstance) -> CardInstance {
        guard card.category == nil, let full = cards[card.type] else { return card }
        return full
    }

    func info(for type: String) -> CardInstance? { cards[type] }

    /// The phases a card may be played in (server vocabulary: turn_play,
    /// tribal_discussion, tribal_voting, tribal_immunity, reactive).
    func playablePhases(for card: CardInstance) -> [String] {
        resolve(card).playablePhases ?? []
    }

    // MARK: - Loading

    private func loadBundled() {
        guard let url = Bundle.main.url(forResource: "survivor_cards", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return }
        ingest(data)
    }

    /// Refresh from the live server; bundled data stays if this fails.
    func refresh(from baseURL: URL) async {
        let url = baseURL.appendingPathComponent("api/cards")
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return }
        ingest(data)
    }

    private func ingest(_ data: Data) {
        struct Registry: Decodable { let cards: [String: CardInstance]? }
        let decoder = JSONDecoder()
        if let registry = try? decoder.decode(Registry.self, from: data),
           let loaded = registry.cards, !loaded.isEmpty {
            cards = loaded
        } else if let flat = try? decoder.decode([String: CardInstance].self, from: data),
                  !flat.isEmpty {
            cards = flat
        }
    }
}
