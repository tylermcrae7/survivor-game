import Foundation
import SwiftData

@Model
final class CardDefinition {
    @Attribute(.unique) var type: String
    var category: String
    var name: String
    var cardDescription: String
    var playablePhases: [String]
    var requiresTarget: Bool
    var requiresMultipleTargets: Bool
    var requiresConfirmation: Bool
    var reactiveOnly: Bool
    var count: Int

    init(
        type: String,
        category: String,
        name: String,
        cardDescription: String,
        playablePhases: [String],
        requiresTarget: Bool,
        requiresMultipleTargets: Bool,
        requiresConfirmation: Bool,
        reactiveOnly: Bool,
        count: Int
    ) {
        self.type = type
        self.category = category
        self.name = name
        self.cardDescription = cardDescription
        self.playablePhases = playablePhases
        self.requiresTarget = requiresTarget
        self.requiresMultipleTargets = requiresMultipleTargets
        self.requiresConfirmation = requiresConfirmation
        self.reactiveOnly = reactiveOnly
        self.count = count
    }

    static func loadBundledCards(into context: ModelContext) {
        guard let url = Bundle.main.url(forResource: "survivor_cards", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let cards = json["cards"] as? [String: [String: Any]]
        else { return }

        for (_, cardData) in cards {
            guard let type = cardData["type"] as? String,
                  let category = cardData["category"] as? String,
                  let name = cardData["name"] as? String,
                  let description = cardData["description"] as? String,
                  let playablePhases = cardData["playable_phases"] as? [String],
                  let requiresTarget = cardData["requires_target"] as? Bool,
                  let requiresMultipleTargets = cardData["requires_multiple_targets"] as? Bool,
                  let requiresConfirmation = cardData["requires_confirmation"] as? Bool,
                  let reactiveOnly = cardData["reactive_only"] as? Bool,
                  let count = cardData["count"] as? Int
            else { continue }

            let card = CardDefinition(
                type: type,
                category: category,
                name: name,
                cardDescription: description,
                playablePhases: playablePhases,
                requiresTarget: requiresTarget,
                requiresMultipleTargets: requiresMultipleTargets,
                requiresConfirmation: requiresConfirmation,
                reactiveOnly: reactiveOnly,
                count: count
            )
            context.insert(card)
        }

        try? context.save()
    }
}
