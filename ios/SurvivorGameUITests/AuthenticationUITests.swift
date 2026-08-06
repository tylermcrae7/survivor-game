import XCTest

final class AuthenticationUITests: XCTestCase {
    private static let serverURL = "http://127.0.0.1:8099"

    override func setUpWithError() throws {
        continueAfterFailure = false
        try Self.requireScratchServer()
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
                SURVIVOR_ACCESS_CODE=torchtest2468 PORT=8099 .venv/bin/python survivor_server.py
                """)
        }
    }

    @MainActor
    func testLockedIslandUnlockCreatesGameAndPersistsAccess() throws {
        let app = XCUIApplication()
        let resetToken = UUID().uuidString
        app.launchEnvironment = [
            "SURVIVOR_SERVER_URL": Self.serverURL,
            "SURVIVOR_PLAYER_NAME": "Simulator Tyler",
            "SURVIVOR_RESET_ACCESS": resetToken,
        ]
        app.launch()

        let accessCode = app.textFields["island-access-code"]
        XCTAssertTrue(accessCode.waitForExistence(timeout: 8), "A clean launch should show the island gate")
        accessCode.tap()
        accessCode.typeText("torchtest2468")
        app.buttons["island-come-ashore"].tap()

        let createGame = app.buttons["create-game-button"]
        XCTAssertTrue(createGame.waitForExistence(timeout: 8), "A valid code should unlock the start screen")
        createGame.tap()

        let extendedDeckOption = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Extended — +6 house cards"))
            .firstMatch
        XCTAssertTrue(
            extendedDeckOption.waitForExistence(timeout: 5),
            "The native deck picker should describe the six-card Extended deck"
        )

        let submit = app.buttons["create-game-submit"]
        app.collectionViews.firstMatch.swipeUp()
        app.collectionViews.firstMatch.swipeUp()
        XCTAssertTrue(submit.waitForExistence(timeout: 5))
        submit.tap()

        let lobbyCode = app.staticTexts["lobby-game-code"]
        XCTAssertTrue(lobbyCode.waitForExistence(timeout: 10), "Authenticated REST and Socket.IO should reach the lobby")

        let firstCode = lobbyCode.label
        XCTAssertFalse(firstCode.isEmpty)
        let socketConnected = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Connected"),
            object: lobbyCode
        )
        XCTAssertEqual(
            XCTWaiter.wait(for: [socketConnected], timeout: 8),
            .completed,
            "The authenticated Socket.IO handshake should connect"
        )

        app.terminate()
        let relaunchedApp = XCUIApplication()
        relaunchedApp.launchEnvironment = [
            "SURVIVOR_SERVER_URL": Self.serverURL,
            "SURVIVOR_PLAYER_NAME": "Simulator Tyler",
        ]
        relaunchedApp.launch()

        XCTAssertFalse(
            relaunchedApp.textFields["island-access-code"].waitForExistence(timeout: 3),
            "The access cookie should survive relaunch"
        )
        let relaunchedLobbyCode = relaunchedApp.staticTexts["lobby-game-code"]
        XCTAssertTrue(relaunchedLobbyCode.waitForExistence(timeout: 8))
        let reconnectedSocket = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", "Connected"),
            object: relaunchedLobbyCode
        )
        XCTAssertEqual(XCTWaiter.wait(for: [reconnectedSocket], timeout: 8), .completed)

        // Exercise the real lobby-leave route after a process-style reconnect.
        // The confirmation prevents an accidental tap, and success must return
        // to the start screen only after the server has freed the seat.
        relaunchedApp.buttons["Leave"].tap()
        let leaveGame = relaunchedApp.buttons["Leave Game"]
        XCTAssertTrue(leaveGame.waitForExistence(timeout: 3))
        leaveGame.tap()
        XCTAssertTrue(
            relaunchedApp.buttons["create-game-button"].waitForExistence(timeout: 8),
            "A confirmed lobby leave should clear the session and return home"
        )
    }
}
