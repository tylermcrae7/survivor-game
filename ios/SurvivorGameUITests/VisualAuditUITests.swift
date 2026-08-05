import XCTest

/// Screenshots of every surface this work touched, so they can be *looked at*.
///
/// The functional suites prove behaviour and are blind to layout: a toast that
/// covers the screen title, a monogram clipped out of its circle, or a modal
/// pushed under the home indicator all pass every assertion. This suite stages
/// each surface and writes a PNG. It asserts only that the surface appeared —
/// the point is the image.
final class VisualAuditUITests: XCTestCase {
    private static let serverURL = "http://127.0.0.1:8099"
    private static let accessCode = "torchtest2468"
    private static let playerName = "Tyler McRae"
    private static let shotDir =
        ProcessInfo.processInfo.environment["SURVIVOR_SHOT_DIR"]
        ?? "/private/tmp/survivor-shots/visual"

    private var api: QAScratchAPI!
    private var gid: String = ""

    override func setUpWithError() throws {
        continueAfterFailure = false
        var request = URLRequest(url: URL(string: Self.serverURL + "/api/access/check")!)
        request.timeoutInterval = 2
        let semaphore = DispatchSemaphore(value: 0)
        nonisolated(unsafe) var reachable = false
        URLSession.shared.dataTask(with: request) { _, response, _ in
            reachable = (response as? HTTPURLResponse) != nil
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + 3)
        if !reachable { throw XCTSkip("Scratch server not running on :8099") }
        try? FileManager.default.createDirectory(
            atPath: Self.shotDir, withIntermediateDirectories: true)
        api = QAScratchAPI(baseURL: URL(string: Self.serverURL)!)
        try api.post("/api/access", ["code": Self.accessCode])
    }

    override func tearDownWithError() throws {
        if !gid.isEmpty { _ = try? api.post("/api/game/delete", ["gameId": gid]) }
    }

    private func shot(_ name: String) {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        try? png.write(to: URL(fileURLWithPath: "\(Self.shotDir)/\(name).png"))
    }

    /// Names that collide on their first letter, which is the whole reason the
    /// monogram exists — and one long enough to truncate in the camp strip.
    private static let allyNames = ["Christopher", "Coconut", "Cleo"]

    @MainActor
    private func stage(bot: Bool = false) throws -> (app: XCUIApplication,
                                                     me: String, allies: [String]) {
        let created = try api.post("/api/game/create", ["expansion": true])
        gid = try XCTUnwrap(created["gameId"] as? String)

        let app = XCUIApplication()
        app.launchEnvironment = [
            "SURVIVOR_SERVER_URL": Self.serverURL,
            "SURVIVOR_PLAYER_NAME": Self.playerName,
            "SURVIVOR_RESET_ACCESS": UUID().uuidString,
        ]
        app.launch()

        let accessField = app.textFields["island-access-code"]
        if accessField.waitForExistence(timeout: 8) {
            accessField.tap()
            accessField.typeText(Self.accessCode)
            app.buttons["island-come-ashore"].tap()
        }
        let codeField = app.textFields["Game code"]
        XCTAssertTrue(codeField.waitForExistence(timeout: 10))
        codeField.tap()
        codeField.typeText(gid)
        app.buttons["Join game"].tap()
        XCTAssertTrue(app.staticTexts["lobby-game-code"].waitForExistence(timeout: 10))

        var allies: [String] = []
        for name in Self.allyNames {
            let joined = try api.post("/api/player/join", ["gameId": gid, "name": name])
            allies.append(try XCTUnwrap(joined["playerId"] as? String))
        }
        if bot { try api.post("/api/player/add_bot", ["gameId": gid]) }
        shot("00-lobby-monograms")

        let st = try api.get("/api/game/\(gid)/state")
        let players = try XCTUnwrap(st["players"] as? [String: [String: Any]])
        let me = try XCTUnwrap(players.first(where: {
            ($0.value["name"] as? String) == Self.playerName })?.key)

        try api.post("/api/game/start_full", ["gameId": gid])
        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": Array(repeating: "extra_vote", count: 10)])
        return (app, me, allies)
    }

    // MARK: - The camp, where names truncate and the circle identifies

    @MainActor
    func testCampStripAndPlayerCard() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))
        shot("01-camp-strip")

        // Tap a player card: the detail sheet is the answer to "who is that?"
        let card = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS 'Christopher'")).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 8), "camp strip should list Christopher")
        card.tap()
        XCTAssertTrue(camp.app.staticTexts["Christopher"].waitForExistence(timeout: 8),
                      "tapping a player should open their card")
        shot("02-player-detail-sheet")
    }

    // MARK: - The narration toast, over a screen that has a title

    @MainActor
    func testNarrationToastClearsTheNavigationBar() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        // Somebody else acts, so the toast fires without a modal in the way.
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": camp.me, "targetId": camp.allies[0]])
        shot("03-narration-toast")
    }

    // MARK: - The Sorry For You penalty, the new blocking choice

    @MainActor
    func testPenaltyDiscardPicker() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        // Me raiding into a Sorry For You, with a real choice of what to pay.
        try api.post("/api/test/set_hand",
                     ["gameId": gid, "playerId": camp.me,
                      "hand": ["camp_raid", "goodwill_gamble", "the_spy_shack", "vote"]])
        try api.post("/api/test/set_hand",
                     ["gameId": gid, "playerId": camp.allies[0],
                      "hand": ["sorry_for_you", "camp_raid"]])
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": camp.me, "targetId": camp.allies[0]])
        // The victim answers from their own seat, via the API.
        let st = try api.get("/api/game/\(gid)/state")
        let players = try XCTUnwrap(st["players"] as? [String: [String: Any]])
        let hand = try XCTUnwrap(players[camp.allies[0]]?["hand"] as? [[String: Any]])
        let idx = try XCTUnwrap(hand.firstIndex { ($0["type"] as? String) == "sorry_for_you" })
        try api.post("/api/reactive/play_card",
                     ["gameId": gid, "playerId": camp.allies[0],
                      "cardIdx": idx, "theftContext": [:]])

        XCTAssertTrue(camp.app.staticTexts["Sorry For You"].waitForExistence(timeout: 12),
                      "the raider should be asked what they give up")
        shot("04-penalty-discard-picker")
    }

    // MARK: - The hand grid renders every card it counts

    /// Reported from TestFlight as "4 shown with 6 in hand", with two empty
    /// cells in the grid. The hand held three Vote Cards; the grid was keyed on
    /// `CardInstance.id`, which collapses to the bare type when the server
    /// sends no uid, and SwiftUI drops duplicate ForEach ids.
    ///
    /// Three of one type is the shape that broke it, so that is the shape to
    /// stage. The header count and the rendered count have to agree.
    @MainActor
    func testHandRendersEveryCardItCounts() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        // The reported hand: Vote, Block A Vote, Hidden Immunity Idol, a
        // Reward Challenge — and the two Votes that never drew.
        let hand = ["vote", "block_vote", "vote",
                    "immunity_idol", "reward_challenge_its_a_numbers_game", "vote"]
        try api.post("/api/test/set_hand",
                     ["gameId": gid, "playerId": camp.me, "hand": hand])

        XCTAssertTrue(camp.app.staticTexts["· \(hand.count)"].waitForExistence(timeout: 12),
                      "the hand header should count all six")

        // Every card is a button labelled "<name>, <category> card".
        let votes = camp.app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH 'Vote, Vote card'"))
        XCTAssertEqual(votes.count, 3,
                       "all three Vote Cards must render, not collapse to one")

        for name in ["Block A Vote", "Hidden Immunity Idol",
                     "Reward Challenge: It's A Numbers Game"] {
            XCTAssertTrue(camp.app.buttons.matching(
                NSPredicate(format: "label BEGINSWITH %@", name)).firstMatch.exists,
                          "\(name) should be in the grid")
        }
        shot("05-hand-grid-with-duplicates")
    }

    // MARK: - Torches on the ballot

    /// "I want to see how many lives everyone has when voting." The slip you
    /// write a name on is where that belongs, and the case worth looking at is
    /// a table where somebody is one vote from the snuffer — the spent torch
    /// has to read on cream paper, not vanish into it.
    @MainActor
    func testBallotShowsTorchesIncludingTheLastOne() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        try api.post("/api/test/set_flags",
                     ["gameId": gid, "playerId": camp.allies[0], "characterCards": 1])
        for pid in [camp.me] + camp.allies {
            try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": ["vote"]])
        }

        // Straight to the ballot: the council itself is covered by QASweep.
        // Whoever holds the turn draws the council card and so leads it — the
        // seat order is dealt, not fixed, so read it rather than assume it.
        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": ["tribal_council_single"]])
        let before = try api.get("/api/game/\(gid)/state")
        let order = try XCTUnwrap(before["turnOrder"] as? [String])
        let onTurn = order[((before["currentTurnIndex"] as? Int) ?? 0) % order.count]
        let victim = try XCTUnwrap(order.first { $0 != onTurn })
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": onTurn, "targetId": victim])
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": onTurn])

        let opened = try api.get("/api/game/\(gid)/state")
        let leader = try XCTUnwrap(
            (opened["currentVote"] as? [String: Any])?["councilLeaderId"] as? String)
        try api.post("/api/tribal/advance", ["gameId": gid, "playerId": leader,
                                             "phase": "discussion"])
        try api.post("/api/vote/start", ["gameId": gid, "playerId": leader,
                                         "voteType": "elimination"])

        XCTAssertTrue(camp.app.staticTexts["one torch left"].waitForExistence(timeout: 15),
                      "the player on their last torch must say so on the ballot")
        XCTAssertTrue(camp.app.staticTexts["2 torches"].exists,
                      "and everyone else's count must be on their slip too")
        shot("06-ballot-torches")
    }

    // MARK: - The council says how many torches go out

    /// `currentVote.type` has been on the wire and decoded since before this
    /// work, and nothing ever read it — a double council played out
    /// identically to a single one until the reveal itself showed two
    /// names. Now the announcement says it out loud and a persistent chip
    /// keeps saying it for the rest of the ceremony.
    @MainActor
    func testCouncilAnnouncesADoubleElimination() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        for pid in [camp.me] + camp.allies {
            try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": ["vote"]])
        }

        // Straight to the ballot: whoever holds the turn draws the council
        // card and so leads it — the seat order is dealt, not fixed, so
        // read it rather than assume it.
        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": ["tribal_council_double"]])
        let before = try api.get("/api/game/\(gid)/state")
        let order = try XCTUnwrap(before["turnOrder"] as? [String])
        let onTurn = order[((before["currentTurnIndex"] as? Int) ?? 0) % order.count]
        let victim = try XCTUnwrap(order.first { $0 != onTurn })
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": onTurn, "targetId": victim])
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": onTurn])

        XCTAssertTrue(camp.app.staticTexts["TWO torches go out tonight."]
                        .waitForExistence(timeout: 15),
                      "a double council should say so out loud on the announcement")
        XCTAssertTrue(camp.app.staticTexts["DOUBLE ELIMINATION"].exists,
                      "and keep a badge up so the fact survives past the announcement")
        shot("17-double-elimination-banner")
    }

    // MARK: - Playing a targeted advantage from the advantage window

    /// Reported live: tapping Steal A Vote in the Advantage Play Phase answered
    /// "Server Error — Missing fields: targetId", and the same card played fine
    /// from the hand once the screen was left behind. So the row fired the card
    /// without ever asking who it was aimed at.
    @MainActor
    func testTargetedAdvantageAsksWhoBeforeItFires() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        for pid in [camp.me] + camp.allies {
            try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": ["vote"]])
        }
        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": ["tribal_council_single"]])
        let before = try api.get("/api/game/\(gid)/state")
        let order = try XCTUnwrap(before["turnOrder"] as? [String])
        let onTurn = order[((before["currentTurnIndex"] as? Int) ?? 0) % order.count]
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": onTurn,
                      "targetId": try XCTUnwrap(order.first { $0 != onTurn })])
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": onTurn])
        let opened = try api.get("/api/game/\(gid)/state")
        let leader = try XCTUnwrap(
            (opened["currentVote"] as? [String: Any])?["councilLeaderId"] as? String)
        try api.post("/api/tribal/advance", ["gameId": gid, "playerId": leader,
                                             "phase": "advantage_play"])

        // Both shapes on one screen: one that needs a target, one that doesn't.
        try api.post("/api/test/set_hand",
                     ["gameId": gid, "playerId": camp.me,
                      "hand": ["vote", "steal_vote", "im_the_leader_now"]])

        let row = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS 'Steal A Vote'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 15),
                      "the advantage window should offer Steal A Vote")
        shot("07-advantage-window")
        row.tap()

        XCTAssertTrue(camp.app.navigationBars["Choose Target"].waitForExistence(timeout: 8),
                      "a card that needs a target must ask before it fires")
        XCTAssertFalse(camp.app.staticTexts["Server Error"].exists,
                       "and it must not fire targetless on the way")
        shot("08-advantage-target-picker")
        camp.app.buttons["Cancel"].tap()

        // The card that actually broke: no target, so the phone sent no
        // targetId, and the door required the key regardless.
        let untargeted = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS 'Leader Now'")).firstMatch
        XCTAssertTrue(untargeted.waitForExistence(timeout: 8))
        untargeted.tap()

        XCTAssertFalse(camp.app.staticTexts["Server Error"]
                        .waitForExistence(timeout: 4),
                       "an advantage with no target must not be refused for want of one")
        _ = try waitFor("the leadership changes hands", timeout: 12) { st in
            ((st["currentVote"] as? [String: Any])?["councilLeaderId"] as? String) == camp.me
        }
        shot("09-advantage-untargeted-played")
    }

    // MARK: - Breakouts during the council's discussion

    /// The council is one room for its whole length except discussion, which
    /// is when the scheming happens — so camp reopens for that sub-phase and
    /// shuts again when the ballot starts. A snuffed player is on Exile Island
    /// throughout and cannot follow two players off to the well to hear the
    /// alliance being made.
    @MainActor
    func testCampReopensForDiscussionButTheExiledStayExiled() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))
        for pid in [camp.me] + camp.allies {
            try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": ["vote"]])
        }
        try api.post("/api/test/set_flags",
                     ["gameId": gid, "playerId": camp.allies[2],
                      "characterCards": 0, "isEliminated": true])

        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": ["tribal_council_single"]])
        let before = try api.get("/api/game/\(gid)/state")
        let order = try XCTUnwrap(before["turnOrder"] as? [String])
        let onTurn = order[((before["currentTurnIndex"] as? Int) ?? 0) % order.count]
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": onTurn,
                      "targetId": try XCTUnwrap(order.first { $0 != onTurn })])
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": onTurn])
        let opened = try api.get("/api/game/\(gid)/state")
        let leader = try XCTUnwrap(
            (opened["currentVote"] as? [String: Any])?["councilLeaderId"] as? String)

        // Locked for the opening of the ceremony…
        XCTAssertTrue(camp.app.staticTexts["Tribal Council"].firstMatch
                        .waitForExistence(timeout: 15))
        shot("10-council-locked")

        try api.post("/api/tribal/advance", ["gameId": gid, "playerId": leader,
                                             "phase": "advantage_play"])
        try api.post("/api/tribal/advance", ["gameId": gid, "playerId": leader,
                                             "phase": "discussion"])

        // …and the whole camp is back on the band for discussion.
        let well = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS 'The Water Well'")).firstMatch
        XCTAssertTrue(well.waitForExistence(timeout: 12),
                      "discussion should reopen camp")
        shot("11-council-discussion-open")
        well.tap()

        _ = try waitFor("the player walks off mid-council", timeout: 12) { st in
            let players = st["players"] as? [String: [String: Any]]
            return (players?[camp.me]?["place"] as? String) == "the_water_well"
        }
        shot("12-council-discussion-moved")

        // The snuffed ally is on Exile Island, not in anybody's breakout.
        let withDead = try api.get("/api/game/\(gid)/state")
        let players = try XCTUnwrap(withDead["players"] as? [String: [String: Any]])
        XCTAssertEqual(players[camp.allies[2]]?["place"] as? String, "exile_island",
                       "a torch that is out sits out the rest of the season")
        let refused = try? api.post("/api/place/move",
                                    ["gameId": gid, "playerId": camp.allies[2],
                                     "place": "the_water_well"])
        XCTAssertNil(refused, "the dead may not join a breakout")

        // Voting calls everyone back with no transition hook anywhere. Wait on
        // the *screen*, not the server: the point is that the phone follows.
        try api.post("/api/vote/start", ["gameId": gid, "playerId": leader,
                                         "voteType": "elimination"])
        XCTAssertTrue(camp.app.staticTexts["It Is Time to Vote"]
                        .waitForExistence(timeout: 12),
                      "the ballot should open")
        XCTAssertFalse(camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS 'The Water Well'")).firstMatch.exists,
                       "and the breakout rooms should be gone from the band")
        let regrouped = try api.get("/api/game/\(gid)/state")
        let back = try XCTUnwrap(regrouped["players"] as? [String: [String: Any]])
        XCTAssertEqual(back[camp.me]?["place"] as? String, "tribal_council")
        XCTAssertEqual(back[camp.allies[2]]?["place"] as? String, "exile_island",
                       "the exiled are not called back for an ordinary council")
        shot("13-council-regrouped")
    }

    // MARK: - Linking Discord without typing a snowflake

    /// The old flow was: turn on Developer Mode in Discord, long-press your own
    /// name, copy an 18-digit number, type it into Settings. The field's own
    /// help text had to tell you how long the number was.
    ///
    /// Now the phone shows a code and somebody runs `/link` in Discord. This
    /// drives the whole loop with the bot's half done over HTTP, because a real
    /// slash command needs a Discord gateway — but the claim endpoint it calls
    /// is exactly the one the bot calls.
    @MainActor
    func testLinkingDiscordShowsACodeAndCollectsTheAccount() throws {
        let app = XCUIApplication()
        app.launchEnvironment = [
            "SURVIVOR_SERVER_URL": Self.serverURL,
            "SURVIVOR_PLAYER_NAME": Self.playerName,
            "SURVIVOR_RESET_ACCESS": UUID().uuidString,
        ]
        app.launch()
        let accessField = app.textFields["island-access-code"]
        if accessField.waitForExistence(timeout: 8) {
            accessField.tap()
            accessField.typeText(Self.accessCode)
            app.buttons["island-come-ashore"].tap()
        }
        XCTAssertTrue(app.textFields["Game code"].waitForExistence(timeout: 10))

        app.buttons["Settings"].firstMatch.tap()
        let link = app.buttons["settings-link-discord"]
        XCTAssertTrue(link.waitForExistence(timeout: 8),
                      "Settings should offer to link Discord")
        link.tap()

        // The code is the point of the screen, so it has to be on it.
        let code = try waitForCode(in: app)
        shot("14-discord-link-code")

        // Stand in for the bot: same endpoint, same shape, real Discord id.
        try api.post("/api/discord/link/claim",
                     ["code": code, "discordUserId": "111111111111111111"])

        XCTAssertTrue(app.staticTexts["Linked"].waitForExistence(timeout: 12),
                      "the phone should collect the claim without being touched")
        shot("15-discord-linked")
    }

    /// Poll the server until `cond` holds, so a UI assertion is not racing a
    /// socket round trip.
    @discardableResult
    private func waitFor(_ what: String, timeout: TimeInterval,
                         until cond: ([String: Any]) -> Bool) throws -> [String: Any] {
        let deadline = Date().addingTimeInterval(timeout)
        var last: [String: Any] = [:]
        while Date() < deadline {
            last = try api.get("/api/game/\(gid)/state")
            if cond(last) { return last }
            Thread.sleep(forTimeInterval: 0.4)
        }
        XCTFail("server never reached: \(what)")
        return last
    }

    // MARK: - A steal announces itself

    /// Reported live: cards left a hand and arrived in another with nothing
    /// on anybody's screen to say so — a Do Or Die win looked like the win
    /// paid nothing. Every take now toasts its thief, victim and count.
    @MainActor
    func testAStealAnnouncesItselfOnEveryPhone() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        let before = try api.get("/api/game/\(gid)/state")
        let order = try XCTUnwrap(before["turnOrder"] as? [String])
        let onTurn = order[((before["currentTurnIndex"] as? Int) ?? 0) % order.count]
        let victim = try XCTUnwrap(order.first { $0 != onTurn })
        try api.post("/api/test/set_hand",
                     ["gameId": gid, "playerId": victim,
                      "hand": ["vote", "extra_vote", "camp_raid"]])
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": onTurn, "targetId": victim])

        let toast = camp.app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS 'stole a card from'")).firstMatch
        XCTAssertTrue(toast.waitForExistence(timeout: 10),
                      "a steal must toast on every phone, not only the thief's")
        shot("15-steal-toast")
    }

    // MARK: - The reveal keeps the votes immunity erased

    /// The idol negates the votes; it should not erase them from history.
    /// The reveal shows the immune player's would-be count, marked immune.
    @MainActor
    func testTheRevealShowsAnImmunePlayersUncountedVotes() throws {
        let camp = try stage()
        XCTAssertTrue(camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20))

        for pid in [camp.me] + camp.allies {
            try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": ["vote"]])
        }
        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": ["tribal_council_single"]])
        let before = try api.get("/api/game/\(gid)/state")
        let order = try XCTUnwrap(before["turnOrder"] as? [String])
        let onTurn = order[((before["currentTurnIndex"] as? Int) ?? 0) % order.count]
        try api.post("/api/turn/steal",
                     ["gameId": gid, "thiefId": onTurn,
                      "targetId": try XCTUnwrap(order.first { $0 != onTurn })])
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": onTurn])

        let opened = try api.get("/api/game/\(gid)/state")
        let leader = try XCTUnwrap(
            (opened["currentVote"] as? [String: Any])?["councilLeaderId"] as? String)
        try api.post("/api/tribal/advance", ["gameId": gid, "playerId": leader,
                                             "phase": "discussion"])
        try api.post("/api/vote/start", ["gameId": gid, "playerId": leader,
                                         "voteType": "elimination"])

        // Three votes land on the soon-to-be-immune ally; theirs lands on me,
        // so the reveal holds both row shapes: a counted one and an erased one.
        let immune = camp.allies[0]
        for pid in [camp.me] + camp.allies {
            let target = (pid == immune) ? camp.me : immune
            try api.post("/api/vote/cast",
                         ["gameId": gid, "voterId": pid,
                          "votesData": [["targetId": target, "votes": 1]]])
        }

        try api.post("/api/tribal/advance", ["gameId": gid, "playerId": leader,
                                             "phase": "immunity"])
        try api.post("/api/test/set_hand",
                     ["gameId": gid, "playerId": immune, "hand": ["immunity_idol"]])
        try api.post("/api/immunity/play", ["gameId": gid, "playerId": immune])

        let sealed = try api.post("/api/vote/reveal",
                                  ["gameId": gid, "playerId": leader])
        if (sealed["idolWindowOpened"] as? Bool) == true
            || (sealed["idolWindowOpened"] as? Int) == 1 {
            try api.post("/api/vote/reveal", ["gameId": gid, "playerId": leader])
        }

        let erased = camp.app.descendants(matching: .any).matching(
            NSPredicate(format: "label CONTAINS 'would have received'")).firstMatch
        XCTAssertTrue(erased.waitForExistence(timeout: 15),
                      "the immune player's would-be votes must be on the reveal")
        shot("16-reveal-immune-votes")
    }

    /// Read the code off the screen. The visible text is "/link PALM-472" and
    /// the spoken label spells it out, so the identifier is what carries it.
    private func waitForCode(in app: XCUIApplication) throws -> String {
        let prefix = "discord-link-code-"
        let element = app.staticTexts.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", prefix)).firstMatch
        guard element.waitForExistence(timeout: 15) else {
            shot("14-discord-link-FAILED")
            XCTFail("no link code appeared. On screen: "
                    + app.staticTexts.allElementsBoundByIndex
                        .prefix(20).map { $0.label }.joined(separator: " | "))
            return ""
        }
        // ...and while we are here, the spoken form is the whole reason a
        // sighted-only label would have been wrong.
        XCTAssertTrue(element.label.contains("dash"),
                      "VoiceOver should spell the code, not read it as a word")
        return String(element.identifier.dropFirst(prefix.count))
    }
}
