import Testing
@testable import SurvivorGame

/// The phone used to drop ten of the server's eleven event types on the floor,
/// which is why a card could leave your hand with no explanation. These pin the
/// decode against the exact payloads `survivor_server._emit_narrator_events`
/// sends — including the ones it sends badly.
@Suite("Narration events")
struct NarrationEventTests {

    @Test("Every event the server emits decodes")
    func decodesTheServerVocabulary() {
        #expect(NarrationEvent(type: "steal",
                               data: ["thief": "Ana", "victim": "Ben"]) != nil)
        #expect(NarrationEvent(type: "card_played",
                               data: ["player": "Ana", "card": "Camp Raid"]) != nil)
        #expect(NarrationEvent(type: "vote_cast", data: ["player": "Ana"]) != nil)
        #expect(NarrationEvent(type: "immunity_played", data: ["player": "Ana"]) != nil)
        #expect(NarrationEvent(type: "immunity_nullified", data: ["target": "Ben"]) != nil)
        #expect(NarrationEvent(type: "elimination",
                               data: ["player": "Ana", "playerId": "p1"]) != nil)
        #expect(NarrationEvent(type: "game_start", data: ["count": 4]) != nil)
        #expect(NarrationEvent(type: "winner", data: ["player": "Ana"]) != nil)
        #expect(NarrationEvent(type: "tribal_start", data: [:]) != nil)
        #expect(NarrationEvent(type: "player_joined",
                               data: ["player": "Ana", "count": 2]) != nil)
        #expect(NarrationEvent(type: "inheritance", data: [
            "heir": "Mango", "dead": "Coconut", "count": 2,
            "message": "Mango inherits Coconut's 2 cards — Inheritance (Red) is spent",
        ]) != nil)
    }

    @Test("An unknown event is ignored, not rendered and not crashed on")
    func unknownTypeIsDropped() {
        #expect(NarrationEvent(type: "some_future_event",
                               data: ["player": "Ana"]) == nil)
    }

    /// The steal emit read `playerId` where the route requires `thiefId`, so
    /// for the whole life of the game every steal narrated as "Unknown". The
    /// server is fixed, but a phone in the field will keep receiving the old
    /// payload until its server is updated — and "Unknown raided Ben's camp" is
    /// worse than saying nothing.
    @Test("A steal with an unresolved thief is dropped rather than shown")
    func unknownThiefIsDropped() {
        #expect(NarrationEvent(type: "steal",
                               data: ["thief": "Unknown", "victim": "Ben"]) == nil)
        #expect(NarrationEvent(type: "steal",
                               data: ["thief": "", "victim": "Ben"]) == nil)
    }

    @Test("Steal carries the player ids, because names are not unique")
    func stealCarriesIds() {
        let event = NarrationEvent(type: "steal",
                                   data: ["thief": "Ana", "victim": "Ben",
                                          "thiefId": "p1", "victimId": "p2"])
        #expect(event == .steal(thief: "Ana", victim: "Ben",
                                thiefId: "p1", victimId: "p2",
                                count: 1, message: nil))
    }

    @Test("A steal with a count reads the number of cards, not just 'a card'")
    func stealWithCountReadsCards() {
        let event = NarrationEvent(type: "steal", data: [
            "thief": "TDawg", "victim": "Mango", "count": 2,
            "message": "TDawg stole 2 cards from Mango",
        ])
        #expect(event?.message == "TDawg stole 2 cards from Mango")
    }

    @Test("A steal with no count still reads — an older server never sent one")
    func stealWithoutCountStillReads() {
        let event = NarrationEvent(type: "steal",
                                   data: ["thief": "A", "victim": "B"])
        #expect(event?.message.contains("A") == true)
        #expect(event?.message == "A stole a card from B")
    }

    @Test("Without a server message, the count builds honest wording")
    func stealFallsBackToConstructedWording() {
        let single = NarrationEvent(type: "steal",
                                    data: ["thief": "Ana", "victim": "Ben", "count": 1])
        #expect(single?.message == "Ana stole a card from Ben")

        let plural = NarrationEvent(type: "steal",
                                    data: ["thief": "Ana", "victim": "Ben", "count": 3])
        #expect(plural?.message == "Ana stole 3 cards from Ben")
    }

    @Test("A blocked raid uses the server's own words")
    func raidBlockedUsesTheServersWords() {
        let event = NarrationEvent(type: "raid_blocked", data: [
            "defender": "Mango",
            "message": "Mango played Sorry For You — the raid fails",
        ])
        #expect(event?.message == "Mango played Sorry For You — the raid fails")
    }

    @Test("A blocked raid with no message is dropped rather than shown blank")
    func raidBlockedWithNoMessageIsDropped() {
        #expect(NarrationEvent(type: "raid_blocked", data: ["defender": "Mango"]) == nil)
    }

    @Test("A blocked raid toasts and outranks chatter, same as a steal")
    func raidBlockedCueAndPriority() {
        let event = NarrationEvent(type: "raid_blocked", data: [
            "defender": "Mango", "message": "Mango played Sorry For You — the raid fails",
        ])
        #expect(event?.cue == .steal)
        #expect(event?.priority == .normal)
    }

    /// The transfer already worked silently; only the announcement is new.
    @Test("An Inheritance firing uses the server's own words")
    func inheritanceUsesTheServersWords() {
        let event = NarrationEvent(type: "inheritance", data: [
            "heirId": "p1", "heir": "Mango", "deadId": "p2", "dead": "Coconut",
            "count": 2, "seatLabel": "Red",
            "message": "Mango inherits Coconut's 2 cards — Inheritance (Red) is spent",
        ])
        #expect(event?.message == "Mango inherits Coconut's 2 cards — Inheritance (Red) is spent")
    }

    @Test("An Inheritance with no message is dropped rather than shown blank")
    func inheritanceWithNoMessageIsDropped() {
        #expect(NarrationEvent(type: "inheritance", data: [
            "heir": "Mango", "dead": "Coconut", "count": 2,
        ]) == nil)
    }

    /// It rides in on the elimination moment, so it must not be evicted by
    /// chatter ahead of it in the queue — unlike a steal, which is merely
    /// `.normal`.
    @Test("An Inheritance toasts critical, and reuses the steal cue")
    func inheritanceCueAndPriority() {
        let event = NarrationEvent(type: "inheritance", data: [
            "heir": "Mango", "dead": "Coconut", "count": 2,
            "message": "Mango inherits Coconut's 2 cards — Inheritance (Red) is spent",
        ])
        #expect(event?.cue == .steal)
        #expect(event?.priority == .critical)
    }

    /// The server's old placeholder was the literal string "a card".
    @Test("The card placeholder never renders as 'a a card'")
    func cardPlaceholder() {
        let event = NarrationEvent(type: "card_played",
                                   data: ["player": "Ana", "card": "a card"])
        #expect(event?.message == "Ana played a card")
    }

    @Test("A named card names itself, and its target")
    func namedCard() {
        let event = NarrationEvent(type: "card_played",
                                   data: ["player": "Ana", "card": "Camp Raid",
                                          "target": "Ben"])
        #expect(event?.message == "Ana played Camp Raid on Ben")
    }

    /// `game_event` is a room-wide broadcast with no audience filter, so
    /// anything this type learns to render is rendered to everybody. The
    /// initialiser reads only the keys each case names.
    @Test("Unknown payload keys cannot reach the screen")
    func extraKeysAreNotRendered() {
        let event = NarrationEvent(type: "card_played",
                                   data: ["player": "Ana", "card": "The Spy Shack",
                                          "peekedCard": "Immunity Idol",
                                          "victimHand": ["immunity_idol", "vote"]])
        #expect(event?.message.contains("Immunity Idol") == false)
        #expect(event?.message.contains("immunity_idol") == false)
        #expect(event?.message == "Ana played The Spy Shack")
    }

    /// Nine screens already fire their own audio off state diffs. Narrating
    /// these again would double the snuff, the fanfare and the gong — the
    /// game's three most dramatic sounds.
    @Test("Events owned by a screen carry no sound of their own")
    func ownedCuesAreSilent() {
        #expect(NarrationEvent(type: "elimination", data: ["player": "Ana"])?.cue == nil)
        #expect(NarrationEvent(type: "winner", data: ["player": "Ana"])?.cue == nil)
        #expect(NarrationEvent(type: "tribal_start", data: [:])?.cue == nil)
        // ...while the unowned ones keep theirs.
        #expect(NarrationEvent(type: "steal",
                               data: ["thief": "Ana", "victim": "Ben"])?.cue == .steal)
    }

    @Test("Dramatic events outrank chatter")
    func priorityOrdering() {
        let elimination = NarrationEvent(type: "elimination", data: ["player": "Ana"])!
        let steal = NarrationEvent(type: "steal",
                                   data: ["thief": "Ana", "victim": "Ben"])!
        let vote = NarrationEvent(type: "vote_cast", data: ["player": "Ana"])!
        #expect(elimination.priority > steal.priority)
        #expect(steal.priority > vote.priority)
    }
}

@MainActor
@Suite("Narration pacing")
struct NarrationFeedTests {

    @Test("Repeated ballots collapse into one line")
    func chatterCoalesces() {
        let feed = NarrationFeed(minDwell: .milliseconds(1), gap: .milliseconds(1))
        for name in ["Ana", "Ben", "Cam"] {
            feed.enqueue(NarrationEvent(type: "vote_cast", data: ["player": name])!)
        }
        // Three ballots are one piece of news; the queue must not have grown
        // to three separate toasts.
        #expect(feed.queueDepthForTesting <= 1)
    }

    @Test("A burst is bounded — nobody reads a dozen toasts")
    func queueIsBounded() {
        let feed = NarrationFeed(minDwell: .seconds(60), gap: .seconds(60))
        for i in 0..<12 {
            feed.enqueue(NarrationEvent(type: "card_played",
                                        data: ["player": "P\(i)", "card": "Camp Raid"])!)
        }
        #expect(feed.queueDepthForTesting <= 3)
    }

    @Test("An elimination gets through a queue full of chatter")
    func criticalEventsSurviveTheCap() {
        let feed = NarrationFeed(minDwell: .seconds(60), gap: .seconds(60))
        for name in ["A", "B", "C", "D", "E"] {
            feed.enqueue(NarrationEvent(type: "player_joined",
                                        data: ["player": name, "count": 1])!)
        }
        feed.enqueue(NarrationEvent(type: "elimination", data: ["player": "Doomed"])!)
        #expect(feed.pendingForTesting.contains { $0.priority == .critical })
    }

    @Test("A reset silences the previous game")
    func resetClears() {
        let feed = NarrationFeed(minDwell: .seconds(60), gap: .seconds(60))
        feed.enqueue(NarrationEvent(type: "winner", data: ["player": "Ana"])!)
        feed.reset()
        #expect(feed.current == nil)
        #expect(feed.pendingForTesting.isEmpty)
    }

    /// A short line still gets the floor — nobody reads faster than that just
    /// because the sentence was short.
    @Test("A short message dwells the floor, not less")
    func dwellFloorsShortMessages() {
        let feed = NarrationFeed()
        let event = NarrationEvent(type: "raid_blocked",
                                   data: ["defender": "X",
                                          "message": String(repeating: "a", count: 10)])!
        #expect(feed.dwell(for: event) == .milliseconds(2400))
    }

    /// ~60ms per character once the line is long enough to clear the floor.
    @Test("A longer message dwells proportional to its length")
    func dwellScalesWithLength() {
        let feed = NarrationFeed()
        let event = NarrationEvent(type: "raid_blocked",
                                   data: ["defender": "X",
                                          "message": String(repeating: "a", count: 60)])!
        #expect(feed.dwell(for: event) == .milliseconds(3600))
    }

    /// A wordy event cannot dam the queue behind it.
    @Test("A wordy message caps its dwell rather than stalling the queue")
    func dwellCapsLongMessages() {
        let feed = NarrationFeed()
        let event = NarrationEvent(type: "raid_blocked",
                                   data: ["defender": "X",
                                          "message": String(repeating: "a", count: 200)])!
        #expect(feed.dwell(for: event) == .milliseconds(4200))
    }
}
