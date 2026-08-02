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

}
