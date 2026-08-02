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
                                thiefId: "p1", victimId: "p2"))
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
        let feed = NarrationFeed(dwell: .milliseconds(1), gap: .milliseconds(1))
        for name in ["Ana", "Ben", "Cam"] {
            feed.enqueue(NarrationEvent(type: "vote_cast", data: ["player": name])!)
        }
        // Three ballots are one piece of news; the queue must not have grown
        // to three separate toasts.
        #expect(feed.queueDepthForTesting <= 1)
    }

    @Test("A burst is bounded — nobody reads a dozen toasts")
    func queueIsBounded() {
        let feed = NarrationFeed(dwell: .seconds(60), gap: .seconds(60))
        for i in 0..<12 {
            feed.enqueue(NarrationEvent(type: "card_played",
                                        data: ["player": "P\(i)", "card": "Camp Raid"])!)
        }
        #expect(feed.queueDepthForTesting <= 3)
    }

    @Test("An elimination gets through a queue full of chatter")
    func criticalEventsSurviveTheCap() {
        let feed = NarrationFeed(dwell: .seconds(60), gap: .seconds(60))
        for name in ["A", "B", "C", "D", "E"] {
            feed.enqueue(NarrationEvent(type: "player_joined",
                                        data: ["player": name, "count": 1])!)
        }
        feed.enqueue(NarrationEvent(type: "elimination", data: ["player": "Doomed"])!)
        #expect(feed.pendingForTesting.contains { $0.priority == .critical })
    }

    @Test("A reset silences the previous game")
    func resetClears() {
        let feed = NarrationFeed(dwell: .seconds(60), gap: .seconds(60))
        feed.enqueue(NarrationEvent(type: "winner", data: ["player": "Ana"])!)
        feed.reset()
        #expect(feed.current == nil)
        #expect(feed.pendingForTesting.isEmpty)
    }
}
