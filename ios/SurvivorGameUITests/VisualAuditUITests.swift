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
        "/private/tmp/claude-501/-Users-tylermcrae/d5ea8664-6416-4b12-8223-5eb4977a3928/scratchpad/visual"

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
                      "hand": ["camp_raid", "inheritance", "the_spy_shack", "vote"]])
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

}
