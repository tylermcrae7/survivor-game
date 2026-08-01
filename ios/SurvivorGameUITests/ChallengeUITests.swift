import XCTest

/// Reproduces the live "1 Now or 2 Later" wedge: on a real device the
/// pull/pass buttons (the nil-value challenge actions) produced no
/// POST /api/challenge/action at all and the game waited on the human forever.
/// These tests stage that exact challenge against the scratch server and tap
/// the same buttons — including after an app relaunch mid-challenge, which is
/// the session the real player was in when the taps went missing.
final class ChallengeUITests: XCTestCase {
    private static let serverURL = "http://127.0.0.1:8099"
    private static let accessCode = "torchtest2468"
    private static let playerName = "Simulator Tyler"

    private var api: ScratchAPI!

    override func setUpWithError() throws {
        continueAfterFailure = false
        try Self.requireScratchServer()
        api = ScratchAPI(baseURL: URL(string: Self.serverURL)!)
    }

    /// UI tests drive a real island. Without it, skip loudly instead of
    /// failing the whole default test action on a clean checkout.
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

    // MARK: - The tests

    /// Fresh session: the human starts the challenge and immediately passes.
    /// "Pass the bag" sends action=pass with NO value — the exact nil-value
    /// path that went silent in production.
    @MainActor
    func testPassTheBagRegistersOnTheServer() throws {
        let staged = try stageOneNowOrTwoLater()
        let app = staged.app

        let pass = app.buttons["Pass the bag"]
        XCTAssertTrue(pass.exists, "The starter's move offers pull AND pass")
        pass.tap()

        let passLog = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "\(Self.playerName) passes")
        ).firstMatch
        XCTAssertTrue(
            passLog.waitForExistence(timeout: 10),
            "Tapping Pass the bag must land POST /api/challenge/action — the challenge log echoes the pass"
        )
    }

    /// The production session: the app was relaunched MID-challenge, rejoined,
    /// and only then did the player tap "Pull from the bag" (action=pull, no
    /// value). The challenge waits on the human, so the relaunch window is
    /// deterministic — no bot acts until this tap lands.
    @MainActor
    func testPullFromTheBagAfterRelaunchRegistersOnTheServer() throws {
        let staged = try stageOneNowOrTwoLater()
        staged.app.terminate()

        let app = XCUIApplication()
        app.launchEnvironment = [
            "SURVIVOR_SERVER_URL": Self.serverURL,
            "SURVIVOR_PLAYER_NAME": Self.playerName,
        ]
        app.launch()

        // The saved session auto-rejoins and the live challenge takes the
        // screen back over — still the human's move.
        let pull = app.buttons["Pull from the bag"]
        XCTAssertTrue(
            pull.waitForExistence(timeout: 20),
            "Relaunch mid-challenge should rejoin straight back into the live challenge"
        )
        pull.tap()

        let pullLog = app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "\(Self.playerName) pulled 1 rock")
        ).firstMatch
        XCTAssertTrue(
            pullLog.waitForExistence(timeout: 10),
            "Tapping Pull from the bag must land POST /api/challenge/action — the challenge log echoes the pull"
        )
    }

    // MARK: - Staging

    private struct StagedChallenge {
        let app: XCUIApplication
        let gameId: String
        let humanId: String
    }

    /// Stages a live 1 Now or 2 Later challenge with the human on the move:
    /// scratch game via the API, join via the real UI, bots + deterministic
    /// hands via test hooks, then steal → play the challenge card through the
    /// actual screens. Returns with ChallengeScreen showing "pull or pass".
    @MainActor
    private func stageOneNowOrTwoLater() throws -> StagedChallenge {
        // Server side: trade the code for the access cookie, then create the
        // expansion game the app will join.
        try api.post("/api/access", ["code": Self.accessCode])
        let created = try api.post("/api/game/create", ["expansion": true])
        let gid = try XCTUnwrap(created["gameId"] as? String, "create should answer a gameId")

        // App: clean first launch, unlock the gate, join by code.
        let app = XCUIApplication()
        app.launchEnvironment = [
            "SURVIVOR_SERVER_URL": Self.serverURL,
            "SURVIVOR_PLAYER_NAME": Self.playerName,
            "SURVIVOR_RESET_ACCESS": UUID().uuidString,
        ]
        app.launch()

        // A clean container shows the island gate. A Keychain-restored access
        // cookie (it survives reinstalls) goes straight ashore — Release
        // builds skip the DEBUG-only reset hook, so handle both entrances.
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
        XCTAssertTrue(app.staticTexts["lobby-game-code"].waitForExistence(timeout: 10), "Joining should reach the lobby")

        // Server side: seat two bots, start, then stage deterministic hands —
        // the human holds the challenge card, the bots hold a lone (reactive-
        // free) Vote Card so the mandatory steal can't detour through a
        // Sorry For You window.
        try api.post("/api/player/add_bot", ["gameId": gid])
        try api.post("/api/player/add_bot", ["gameId": gid])

        let state = try api.get("/api/game/\(gid)/state")
        let players = try XCTUnwrap(state["players"] as? [String: [String: Any]])
        let humanId = try XCTUnwrap(
            players.first(where: { !(($0.value["isBot"] as? Bool) ?? false) })?.key,
            "The UI-joined human should be in the game"
        )
        let botName = try XCTUnwrap(
            players.values.first(where: { ($0["isBot"] as? Bool) == true })?["name"] as? String
        )

        try api.post("/api/game/start_full", ["gameId": gid])
        try api.post("/api/test/set_hand", [
            "gameId": gid, "playerId": humanId,
            "hand": ["vote", "challenge_1_now_or_2_later"],
        ])
        for (pid, player) in players where (player["isBot"] as? Bool) == true {
            try api.post("/api/test/set_hand", [
                "gameId": gid, "playerId": pid, "hand": ["vote"],
            ])
        }

        // App: start_full begins on the human's turn (join order is turn
        // order). The official turn opens with the mandatory steal.
        let steal = app.buttons["Steal card from player"]
        XCTAssertTrue(steal.waitForExistence(timeout: 20), "The started game should open on the human's turn")
        steal.tap()

        let botRow = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", botName)
        ).firstMatch
        XCTAssertTrue(botRow.waitForExistence(timeout: 8), "The steal picker should list the bots")
        botRow.tap()

        // Play the staged challenge card from the hand grid.
        let card = app.buttons.matching(
            NSPredicate(format: "label CONTAINS '1 Now or 2 Later'")
        ).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 10), "The staged challenge card should sit in the hand")
        if !card.isHittable { app.swipeUp() }
        card.tap()

        let play = app.buttons["play this card"]
        XCTAssertTrue(play.waitForExistence(timeout: 8), "The card sheet should offer the play button")
        play.tap()

        // The challenge takes the table over; the starter pulls first, so it
        // is immediately the human's move.
        let pull = app.buttons["Pull from the bag"]
        XCTAssertTrue(pull.waitForExistence(timeout: 10), "The challenge should open on the human's pull-or-pass move")

        return StagedChallenge(app: app, gameId: gid, humanId: humanId)
    }
}

// MARK: - Scratch-server orchestration

/// Minimal synchronous JSON caller for staging games against the scratch
/// server. Cookies (the island access cookie from POST /api/access) ride in
/// the default shared jar, so every later call stays ashore.
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
            guard let http = response as? HTTPURLResponse else {
                outcome = .failure(.transport("not an HTTP response"))
                return
            }
            let text = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            guard (200...299).contains(http.statusCode) else {
                outcome = .failure(.badStatus(http.statusCode, text))
                return
            }
            guard let data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                outcome = .failure(.notJSON)
                return
            }
            outcome = .success(json)
        }.resume()
        _ = semaphore.wait(timeout: .now() + 15)
        return try outcome.get()
    }
}
