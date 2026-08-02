import Foundation
import Testing
@testable import SurvivorGame

/// Cards can finally say which card they are.
///
/// `CardInstance.id` used to be `type + name`, so two Vote Cards in one hand
/// were the same identity — which is why the hand grid had to key off array
/// position, which in turn is why it could never be reordered or animated.
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
}
