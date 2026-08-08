import XCTest

/// The player-to-player proof for Task A3: a REAL app on a REAL socket,
/// robbed by another player, is told exactly what was taken — and nobody
/// who isn't the victim ever sees that banner.
///
/// This is deliberately not a staged mock. The app joins a scratch-server
/// game through its own start screen, which exercises the entire new
/// delivery chain end to end: `joinGame(gameId, playerId:)` → the server's
/// `gid::pid` private room (`on_join`) → `_record_steal_alert`'s private
/// `robbed` alert → `emit_private_event` → `NarrationEvent.robbed` →
/// `GameClient.robberyAlert` → `RobberyBanner` on screen. A regression in
/// any link of that chain fails this test.
final class RobberyBannerUITests: XCTestCase {
    private static let serverURL = "http://127.0.0.1:8099"
    private static let accessCode = "torchtest2468"
    private static let playerName = "Simulator Tyler"

    private var api: ScratchAPI!

    override func setUpWithError() throws {
        continueAfterFailure = false
        try Self.requireScratchServer()
        api = ScratchAPI(baseURL: URL(string: Self.serverURL)!)
    }

    private static func requireScratchServer() throws {
        var request = URLRequest(url: URL(string: serverURL + "/api/access/check")!)
        request.timeoutInterval = 2
        let semaphore = DispatchSemaphore(value: 0)
        // The semaphore orders the write before the read.
        nonisolated(unsafe) var reachable = false
        URLSession.shared.dataTask(with: request) { _, response, _ in
            reachable = (response as? HTTPURLResponse) != nil
            semaphore.signal()
        }.resume()
        _ = semaphore.wait(timeout: .now() + 3)
        if !reachable {
            throw XCTSkip("""
                Scratch server not running. Start it from the repo root:
                SURVIVOR_TEST_HOOKS=1 SURVIVOR_ACCESS_CODE=torchtest2468 PORT=8099 .venv/bin/python survivor_server.py
                """)
        }
    }

    /// One game, both halves of the contract:
    ///
    /// 1. The human robs a player whose only card is a Vote Card — nothing
    ///    moves, and nothing may appear. Then the human's own successful
    ///    turn ends with them holding the table's biggest hand.
    /// 2. A bot's mandatory turn steal therefore targets the human (biggest
    ///    hand), takes one of their two staged Hidden Immunity Idols, and
    ///    the banner must name it — not "a card", the card.
    @MainActor
    func testARobberyBannerNamesTheCardToTheVictimAlone() throws {
        // Server side: come ashore, build the table.
        try api.post("/api/access", ["code": Self.accessCode])
        let created = try api.post("/api/game/create", [:])
        let gid = try XCTUnwrap(created["gameId"] as? String, "create should answer a gameId")

        // App: clean first launch, unlock the gate if it shows, join by code
        // through the real start screen — this is what puts the socket in
        // the private room, so it must be the app's own join, not an API one.
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
        XCTAssertTrue(codeField.waitForExistence(timeout: 8), "The start screen should follow the gate")
        codeField.tap()
        codeField.typeText(gid)
        app.buttons["Join game"].tap()
        XCTAssertTrue(app.staticTexts["lobby-game-code"].waitForExistence(timeout: 10),
                      "Joining should reach the lobby")

        // Two bots make the game legal; deterministic hands make the robbery
        // deterministic: the human's two staged idols are their only takeable
        // cards (a Vote Card is never stealable), and the biggest hand at the
        // table, so the first bot steal must take an idol from the human.
        try api.post("/api/player/add_bot", ["gameId": gid])
        try api.post("/api/player/add_bot", ["gameId": gid])

        let state = try api.get("/api/game/\(gid)/state")
        let players = try XCTUnwrap(state["players"] as? [String: [String: Any]])
        let humanId = try XCTUnwrap(
            players.first(where: { !(($0.value["isBot"] as? Bool) ?? false) })?.key,
            "The UI-joined human should be in the game"
        )
        let botIds = players.filter { ($0.value["isBot"] as? Bool) == true }.map(\.key)

        try api.post("/api/game/start_full", ["gameId": gid])
        try api.post("/api/test/set_hand", [
            "gameId": gid, "playerId": humanId,
            "hand": ["vote", "immunity_idol", "immunity_idol"],
        ])
        for pid in botIds {
            try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": ["vote"]])
        }
        // The human must draw to end their turn. Pin that draw to another
        // untakeable Vote Card: a random Sorry For You here correctly opens a
        // 60-second reactive window when the bot steals, which means the
        // robbery has not completed and no banner should exist yet. This test
        // is specifically proving the completed-theft private-room delivery.
        try api.post("/api/test/stack_deck", ["gameId": gid, "top": ["vote"]])

        // Half 1 — start_full opens on the human's turn (join order is turn
        // order). Drive it over HTTP: the server doesn't care which client a
        // player's own moves arrive from, and the app still hears every
        // event. The mandatory steal finds only an untakeable Vote Card, so
        // no cards move and no banner may appear — and the victim was a bot
        // besides, which must never mint a private alert at all.
        try api.post("/api/turn/steal", ["gameId": gid, "thiefId": humanId, "targetId": botIds[0]])

        let anyBanner = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "took your")
        ).firstMatch
        // A short settle window, then the absence check. This can only fail
        // wrongly (never pass wrongly): if delivery were broken the test
        // still dies at the positive assertion below.
        Thread.sleep(forTimeInterval: 3)
        XCTAssertFalse(anyBanner.exists,
                       "no cards moved and the target was a bot — nothing may be announced here")

        // The draw ends the human's turn; the bots take over from here.
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": humanId])

        // Half 2 — the first bot turn's mandatory steal targets the biggest
        // hand: the human's. One of the two staged idols must cross, and the
        // banner must say which card left, not just that one did.
        let robbed = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "took your Hidden Immunity Idol")
        ).firstMatch
        XCTAssertTrue(robbed.waitForExistence(timeout: 30),
                      "the victim's phone must name the stolen card via the private room")

        // Keep the evidence: the banner, live on a real phone.
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "robbery-banner-on-victims-phone"
        shot.lifetime = .keepAlways
        add(shot)

        // Tap-to-dismiss is part of the contract — a banner that lingers
        // forever is a modal with extra steps.
        robbed.tap()
        XCTAssertTrue(waitForDisappearance(of: robbed, timeout: 5),
                      "tapping the banner should dismiss it")
    }

    @MainActor
    private func waitForDisappearance(of element: XCUIElement, timeout: TimeInterval) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !element.exists { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
        return !element.exists
    }
}

// MARK: - Scratch-server orchestration

/// Minimal synchronous JSON caller, same shape as ChallengeUITests' — kept
/// file-private there, so duplicated here rather than widening that type's
/// access for a test-support concern.
private final class ScratchAPI {
    enum Failure: Error, CustomStringConvertible {
        case transport(String)
        case badStatus(Int, String)
        case notJSON

        var description: String {
            switch self {
            case .transport(let message): return "transport: \(message)"
            case .badStatus(let code, let body): return "HTTP \(code): \(body)"
            case .notJSON: return "response was not a JSON object"
            }
        }
    }

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL) {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        session = URLSession(configuration: config)
    }

    @discardableResult
    func post(_ path: String, _ body: [String: Any] = [:]) throws -> [String: Any] {
        try call("POST", path, body: body)
    }

    func get(_ path: String) throws -> [String: Any] {
        try call("GET", path, body: nil)
    }

    private func call(_ method: String, _ path: String, body: [String: Any]?) throws -> [String: Any] {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = method
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let semaphore = DispatchSemaphore(value: 0)
        // The semaphore orders the write before the read.
        nonisolated(unsafe) var outcome: Result<[String: Any], Failure> = .failure(.transport("no response"))
        session.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            if let error {
                outcome = .failure(.transport(error.localizedDescription))
                return
            }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let text = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            guard (200..<300).contains(status) else {
                outcome = .failure(.badStatus(status, text))
                return
            }
            guard let data,
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                outcome = .failure(.notJSON)
                return
            }
            outcome = .success(object)
        }.resume()
        _ = semaphore.wait(timeout: .now() + 15)
        return try outcome.get()
    }
}
