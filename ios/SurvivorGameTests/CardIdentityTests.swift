import Foundation
import Testing
@testable import SurvivorGame

/// Cards can finally say which card they are.
///
/// `CardInstance.id` used to be `type + name`, so two Vote Cards in one hand
/// were the same identity and nothing could name one of them: no reordering,
/// no animating a specific card, no Camp Raid marker on the card you drew.
///
/// The uid fixes that where the server sends one. It still falls back to
/// `type + name`, so the id remains unsafe as a collection key — see
/// `fallbackIdIsNotUnique`.
@MainActor
@Suite("Card identity")
struct CardIdentityTests {

    @Test("A card decodes its server-minted uid")
    func decodesUid() throws {
        let json = #"{"type": "vote", "uid": "a3f9c21b04de"}"#
        let card = try JSONDecoder().decode(CardInstance.self, from: Data(json.utf8))
        #expect(card.uid == "a3f9c21b04de")
        #expect(card.id == "a3f9c21b04de")
    }

    @Test("Two cards of the same type are now distinct")
    func sameTypeDistinctIdentity() throws {
        let json = #"[{"type": "vote", "uid": "aaa"}, {"type": "vote", "uid": "bbb"}]"#
        let hand = try JSONDecoder().decode([CardInstance].self, from: Data(json.utf8))
        #expect(hand[0].id != hand[1].id)
        #expect(Set(hand.map { $0.id }).count == 2)
    }

    /// A server that predates uids must not brick the decode — the app ships
    /// ahead of, and behind, the server it talks to.
    @Test("A card without a uid still decodes and still has an id")
    func fallsBackWithoutUid() throws {
        let json = #"{"type": "vote"}"#
        let card = try JSONDecoder().decode(CardInstance.self, from: Data(json.utf8))
        #expect(card.uid == nil)
        #expect(card.id == "vote")
    }

    /// The bug that would have made all of this silently useless.
    ///
    /// `CardCatalog.resolve` returned the shared catalog entry, discarding the
    /// instance — so every card in the hand grid would have arrived with a nil
    /// uid, every row would have shared an identity, and SwiftUI would have
    /// collapsed the grid. It would have read as a server bug.
    @Test("Resolving a card against the catalog keeps its identity")
    func resolvePreservesUid() {
        let stub = CardInstance(type: "camp_raid", uid: "abc123")
        let resolved = CardCatalog.shared.resolve(stub)
        #expect(resolved.uid == "abc123")
        #expect(resolved.id == "abc123")
        // ...and it did gain the catalog's detail, or the merge is pointless.
        #expect(resolved.name != nil)
        #expect(resolved.category != nil)
    }

    @Test("A whole hand of duplicates resolves to distinct identities")
    func resolvedHandStaysDistinct() {
        let hand = [
            CardInstance(type: "vote", uid: "one"),
            CardInstance(type: "vote", uid: "two"),
            CardInstance(type: "vote", uid: "three"),
        ]
        let resolved = hand.map { CardCatalog.shared.resolve($0) }
        #expect(Set(resolved.map { $0.id }).count == 3)
    }

    @Test("An unknown card type passes through with its identity intact")
    func unknownTypeKeepsUid() {
        let stub = CardInstance(type: "some_future_card", uid: "xyz789")
        let resolved = CardCatalog.shared.resolve(stub)
        #expect(resolved.uid == "xyz789")
    }

    /// Why the hand grid keys on position and not on `card.id`.
    ///
    /// Shipped as a build that talked to a server without uids, and the fallback
    /// id collapsed a real six-card hand to four rendered cards with two blank
    /// cells — SwiftUI drops duplicate ForEach ids. The client cannot assume the
    /// server it reaches is the one it was built against, so the identity a view
    /// keys on has to be unique for *any* payload.
    @Test("Without uids the fallback id collides, so it is not a ForEach key")
    func fallbackIdIsNotUnique() {
        let handAsProductionSentIt = [
            CardInstance(type: "vote"),
            CardInstance(type: "block_a_vote"),
            CardInstance(type: "vote"),
            CardInstance(type: "hidden_immunity_idol"),
            CardInstance(type: "reward_challenge_numbers"),
            CardInstance(type: "vote"),
        ]
        #expect(handAsProductionSentIt.count == 6)
        #expect(Set(handAsProductionSentIt.map(\.id)).count == 4,
                "three Vote Cards share one id — this is the four-of-six bug")

        // Position is unique whatever the server sends, which is the property
        // the grid actually needs.
        let byPosition = handAsProductionSentIt.enumerated().map(\.offset)
        #expect(Set(byPosition).count == 6)
    }
}
