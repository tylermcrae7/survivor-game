import XCTest

/// Regression suite for the Challenge / Reward-Challenge takeover screens.
///
/// Written during the QA sweep that found two blockers and re-pointed at the
/// fixed behaviour afterwards:
///
///   BLOCKER A — a completed Reward Challenge is parked server-side until
///   somebody POSTs `dismiss`, and bots only clear the ones they started.
///   InteractionScreen must therefore render a reveal panel with a **Continue**
///   button for every client, or a human-played reward wedges the whole table
///   on "The reveal is coming…" forever.
///
///   BLOCKER B — a completed Rocks Challenge is parked the same way, and
///   `bots.next_action` returns None for a human-won one. ChallengeScreen must
///   stay mounted on `phase == "complete"` and show a victory panel with
///   **Continue**, or the table freezes invisibly on the bot's turn.
///
/// Everything is driven against the scratch server on :8099 with real taps;
/// the other seats are API-driven so each scenario is deterministic.
final class QASweepUITests: XCTestCase {
    private static let serverURL = "http://127.0.0.1:8099"
    private static let accessCode = "torchtest2468"
    private static let playerName = "Simulator Tyler"
    private static let shotDir =
        ProcessInfo.processInfo.environment["SURVIVOR_SHOT_DIR"]
        ?? "/private/tmp/survivor-shots/qa"

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
        api = QAScratchAPI(baseURL: URL(string: Self.serverURL)!)
        try api.post("/api/access", ["code": Self.accessCode])
    }

    override func tearDownWithError() throws {
        if !gid.isEmpty {
            _ = try? api.post("/api/game/delete", ["gameId": gid])
        }
    }

    // MARK: - Evidence helpers

    private func saveShot(_ name: String) {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        let url = URL(fileURLWithPath: "\(Self.shotDir)/\(name).png")
        do { try png.write(to: url) } catch {
            // Last resort: attach so it lands in the result bundle
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = name
            attachment.lifetime = .keepAlways
            add(attachment)
        }
    }

    private func dumpState(_ name: String) {
        guard let st = try? api.get("/api/game/\(gid)/state"),
              let data = try? JSONSerialization.data(withJSONObject: st, options: [.sortedKeys])
        else { return }
        try? data.write(to: URL(fileURLWithPath: "\(Self.shotDir)/\(name).json"))
    }

    private func serverState() throws -> [String: Any] {
        try api.get("/api/game/\(gid)/state")
    }

    private func interaction() throws -> [String: Any]? {
        try serverState()["interaction"] as? [String: Any]
    }

    private func challenge() throws -> [String: Any]? {
        try serverState()["challenge"] as? [String: Any]
    }

    private func currentTurnId(_ st: [String: Any]) -> String? {
        guard let order = st["turnOrder"] as? [String], !order.isEmpty else { return nil }
        let idx = (st["currentTurnIndex"] as? Int) ?? 0
        return order[idx % order.count]
    }

    @discardableResult
    private func waitServer(_ what: String, timeout: TimeInterval = 20,
                            until cond: ([String: Any]) -> Bool) throws -> [String: Any] {
        let deadline = Date().addingTimeInterval(timeout)
        var last: [String: Any] = [:]
        while Date() < deadline {
            last = try serverState()
            if cond(last) { return last }
            Thread.sleep(forTimeInterval: 0.5)
        }
        XCTFail("server never reached: \(what)")
        return last
    }

    /// Same poll, but a timeout is a legal outcome (used when a scenario has
    /// to probe "did this happen?" and branch).
    @discardableResult
    private func waitServerSoft(timeout: TimeInterval = 20,
                                until cond: ([String: Any]) -> Bool) throws -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if cond(try serverState()) { return true }
            Thread.sleep(forTimeInterval: 0.5)
        }
        return false
    }

    // MARK: - Staging

    private struct Camp {
        let app: XCUIApplication
        let humanId: String
        let allyIds: [String]   // API-driven humans, in join order
        let botId: String?
    }

    /// Launch clean, join a fresh expansion game via the UI, seat `allies`
    /// API-humans and optionally one bot, then start.
    @MainActor
    private func stageGame(allies: Int, bot: Bool,
                           settings: [String: String]? = nil) throws -> Camp {
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
        XCTAssertTrue(codeField.waitForExistence(timeout: 10), "start screen expected")
        codeField.tap()
        codeField.typeText(gid)
        app.buttons["Join game"].tap()
        XCTAssertTrue(app.staticTexts["lobby-game-code"].waitForExistence(timeout: 10),
                      "joining should reach the lobby")

        var allyIds: [String] = []
        let names = ["Ally", "Bran", "Cleo"]
        for i in 0..<allies {
            let joined = try api.post("/api/player/join",
                                      ["gameId": gid, "name": names[i]])
            allyIds.append(try XCTUnwrap(joined["playerId"] as? String))
        }
        if bot {
            try api.post("/api/player/add_bot", ["gameId": gid])
        }

        let st = try serverState()
        let players = try XCTUnwrap(st["players"] as? [String: [String: Any]])
        let humanId = try XCTUnwrap(players.first(where: {
            ($0.value["name"] as? String) == Self.playerName
        })?.key)
        let botId = players.first(where: { ($0.value["isBot"] as? Bool) == true })?.key

        try api.post("/api/game/start_full", ["gameId": gid])
        if let settings {
            try api.post("/api/game/update_settings",
                         ["gameId": gid, "playerId": humanId, "settings": settings])
        }
        // Human draws must never spring a Tribal Council mid-scenario
        try api.post("/api/test/stack_deck", ["gameId": gid, "top": Array(repeating: "extra_vote", count: 8)])
        return Camp(app: app, humanId: humanId, allyIds: allyIds, botId: botId)
    }

    private func setHand(_ pid: String, _ hand: [String]) throws {
        try api.post("/api/test/set_hand", ["gameId": gid, "playerId": pid, "hand": hand])
    }

    /// The human's mandatory opening steal, through the real UI.
    @MainActor
    private func stealViaUI(_ app: XCUIApplication, victimName: String) {
        let steal = app.buttons["Steal card from player"]
        XCTAssertTrue(steal.waitForExistence(timeout: 20), "human's turn should offer the steal")
        steal.tap()
        // By identifier, not by label: the camp strip's status cards are
        // buttons carrying the same player name, they sit behind this sheet,
        // and firstMatch was picking one of those instead.
        let row = app.buttons["steal-target-\(victimName)"]
        XCTAssertTrue(row.waitForExistence(timeout: 8), "steal picker should list \(victimName)")
        row.tap()
    }

    /// Steal + draw, entirely on-device: the whole of a human turn when the
    /// scenario only needs the clock to move on.
    @MainActor
    private func endHumanTurnViaUI(_ app: XCUIApplication, victimName: String) {
        stealViaUI(app, victimName: victimName)
        let draw = app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 15), "draw should end the human's turn")
        draw.tap()
    }

    /// Open the staged card's sheet and press play. Extra steps (targets,
    /// throws, pairs) are the caller's job.
    @MainActor
    private func openAndPlayCard(_ app: XCUIApplication, labelContains: String) {
        let card = app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", labelContains)).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 10), "staged card should sit in the hand")
        if !card.isHittable { app.swipeUp() }
        card.tap()
        let play = app.buttons["play this card"]
        XCTAssertTrue(play.waitForExistence(timeout: 8), "card sheet should offer play")
        play.tap()
    }

    private func interactionAct(_ pid: String, _ action: String, _ value: Any?) throws {
        var body: [String: Any] = ["gameId": gid, "playerId": pid, "action": action]
        if let value { body["value"] = value }
        try api.post("/api/interaction/act", body)
    }

    private func challengeAct(_ pid: String, _ action: String, _ value: Any?) throws {
        var body: [String: Any] = ["gameId": gid, "playerId": pid, "action": action]
        if let value { body["value"] = value }
        try api.post("/api/challenge/action", body)
    }

    // MARK: - BLOCKER A assertions

    /// The fix: a complete-phase interaction shows the reveal, NOT the eternal
    /// spinner, and offers Continue to every client.
    @MainActor
    private func assertInteractionReveal(_ app: XCUIApplication, shot: String) throws {
        let cont = app.buttons["Continue"]
        XCTAssertTrue(cont.waitForExistence(timeout: 15),
                      "a complete-phase interaction must offer Continue (BLOCKER A)")
        XCTAssertTrue(app.staticTexts["The Reveal"].exists,
                      "the reveal panel header should be on screen")
        XCTAssertFalse(app.staticTexts["The reveal is coming…"].exists,
                       "the waiting spinner must be gone once the interaction completes")
        saveShot(shot)
        dumpState(shot)

        // Nothing rescues the table on its own — the parked interaction is
        // still there and Continue is still the only door out.
        Thread.sleep(forTimeInterval: 6)
        let it = try interaction()
        XCTAssertNotNil(it, "server still parks the completed interaction until it is dismissed")
        XCTAssertEqual(it?["phase"] as? String, "complete")
        XCTAssertTrue(cont.exists, "Continue is still offered")

        // The buried PlayingScreen must not be reachable behind the takeover
        // (ContentView marks it accessibilityHidden + allowsHitTesting false).
        XCTAssertFalse(app.buttons["Draw card and end your turn"].exists,
                       "the table underneath a takeover must not be reachable")
    }

    /// A reveal row combines its children into a single accessibility element
    /// (`accessibilityElement(children: .ignore)`), so it surfaces as an
    /// "Other" element rather than a StaticText — query every type.
    @MainActor
    private func revealRowExists(_ app: XCUIApplication, containing phrase: String) -> Bool {
        app.descendants(matching: .any)
            .matching(NSPredicate(format: "label CONTAINS %@", phrase))
            .firstMatch.exists
    }

    /// Tap Continue on-device and prove the wedge is gone: the interaction is
    /// cleared server-side and the app is back on the table.
    @MainActor
    private func continueOutOfInteraction(_ app: XCUIApplication, shot: String? = nil) throws {
        let cont = app.buttons["Continue"]
        XCTAssertTrue(cont.waitForExistence(timeout: 10), "Continue should be on screen")
        cont.tap()
        try waitServer("interaction cleared by Continue", timeout: 15) {
            ($0["interaction"] as? [String: Any]) == nil
        }
        // The takeover has to come down. (A "back on the table" probe can't key
        // off the turn controls — the human is often not the one on the clock.)
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"),
                                             object: app.staticTexts["The Reveal"])
        XCTAssertEqual(XCTWaiter().wait(for: [gone], timeout: 15), .completed,
                       "the app should leave InteractionScreen once it is dismissed")
        XCTAssertFalse(app.buttons["Continue"].exists, "the reveal's Continue should be gone")
        if let shot { saveShot(shot) }
    }

    // MARK: - BLOCKER B assertions

    /// The fix: a complete-phase Challenge keeps ChallengeScreen mounted and
    /// shows the victory panel instead of silently vanishing.
    @MainActor
    private func assertChallengeVictoryPanel(_ app: XCUIApplication, winnerName: String?,
                                             expectNecklace: Bool, shot: String) throws {
        let cont = app.buttons["Continue"]
        XCTAssertTrue(cont.waitForExistence(timeout: 15),
                      "a complete-phase Challenge must offer Continue (BLOCKER B)")
        XCTAssertTrue(app.staticTexts["The Challenge Is Won"].exists,
                      "the victory panel header should be on screen")
        XCTAssertTrue(app.staticTexts["The Challenge"].exists,
                      "ChallengeScreen must stay mounted on complete, not unmount")
        if let winnerName {
            XCTAssertTrue(app.staticTexts[winnerName].exists,
                          "the winner's name belongs in the victory panel")
        }
        if expectNecklace {
            let necklace = app.staticTexts.containing(
                NSPredicate(format: "label CONTAINS 'Immunity Necklace'")).firstMatch
            XCTAssertTrue(necklace.exists,
                          "the necklace line should show when the winner holds it")
        }
        XCTAssertFalse(app.buttons["Draw card and end your turn"].exists,
                       "the table underneath a takeover must not be reachable")
        saveShot(shot)
        dumpState(shot)
        XCTAssertNotNil(try challenge(), "server still parks the completed Challenge")
    }

    @MainActor
    private func continueOutOfChallenge(_ app: XCUIApplication, shot: String? = nil) throws {
        let cont = app.buttons["Continue"]
        XCTAssertTrue(cont.waitForExistence(timeout: 10), "Continue should be on screen")
        cont.tap()
        try waitServer("challenge cleared by Continue", timeout: 15) {
            ($0["challenge"] as? [String: Any]) == nil
        }
        if let shot { saveShot(shot) }
    }

    // MARK: - 1. Numbers Game, human initiator + human winner (BLOCKER A)

    @MainActor
    func testNumbersGameHumanWinnerRevealsAndContinues() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "reward_challenge_its_a_numbers_game"])
        try setHand(camp.allyIds[0], ["vote", "extra_vote", "extra_vote"])
        try setHand(camp.allyIds[1], ["vote", "extra_vote"])
        stealViaUI(camp.app, victimName: "Ally")
        openAndPlayCard(camp.app, labelContains: "Numbers Game")

        // Everyone shows fingers: the app taps 1; allies pick 5 and 4.
        let one = camp.app.buttons["1"]
        XCTAssertTrue(one.waitForExistence(timeout: 10), "numbers-game finger buttons should show")
        saveShot("qa-01a-numbers-picking")
        one.tap()
        try interactionAct(camp.allyIds[0], "pick", 5)
        try interactionAct(camp.allyIds[1], "pick", 4)

        // Human showed the lowest unique number → choose a victim on-device.
        // By identifier — see stealViaUI: the camp strip's cards carry names too.
        let victimRow = camp.app.buttons["victim-Ally"]
        XCTAssertTrue(victimRow.waitForExistence(timeout: 10),
                      "winner's steal-2 victim picker should appear")
        saveShot("qa-01b-numbers-choose-victim")
        victimRow.tap()

        try waitServer("interaction complete") {
            (($0["interaction"] as? [String: Any])?["phase"] as? String) == "complete"
        }
        try assertInteractionReveal(camp.app, shot: "verify-01-blockerA-numbers-reveal")
        // Numbers Game is the one reward that records a winner — the panel
        // must name them.
        XCTAssertTrue(camp.app.staticTexts["\(Self.playerName) takes the reward"].exists,
                      "the winner line should name the human")
        try continueOutOfInteraction(camp.app, shot: "verify-02-blockerA-numbers-after-continue")

        // The wedge is gone: the human can still act — drawing ends the turn.
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 15),
                      "the human must be able to act again after Continue")
        let before = currentTurnId(try serverState())
        draw.tap()
        try waitServer("turn advances after the reveal is cleared", timeout: 15) {
            self.currentTurnId($0) != before
        }
    }

    // MARK: - 2. Do Or Die, human initiator + human winner (BLOCKER A)

    @MainActor
    func testDoOrDieHumanWinnerRevealsAndContinues() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "reward_challenge_do_or_die"])
        try setHand(camp.allyIds[0], ["vote", "extra_vote", "extra_vote"])
        try setHand(camp.allyIds[1], ["vote"])
        stealViaUI(camp.app, victimName: "Ally")
        openAndPlayCard(camp.app, labelContains: "Do Or Die")

        // Card sheet collects target + secret throw
        let targetRow = camp.app.buttons["target-Ally"]
        XCTAssertTrue(targetRow.waitForExistence(timeout: 8), "target picker should appear")
        targetRow.tap()
        let rock = camp.app.buttons["rock"]
        XCTAssertTrue(rock.waitForExistence(timeout: 8), "throw picker should appear")
        saveShot("qa-02a-dod-throw-picker")
        rock.tap()

        // Interaction live; ally answers with scissors → human wins, raids ally
        try waitServer("interaction started") { ($0["interaction"] as? [String: Any]) != nil }
        saveShot("qa-02b-dod-waiting-on-ally")
        try interactionAct(camp.allyIds[0], "pick", "scissors")

        try waitServer("interaction complete") {
            (($0["interaction"] as? [String: Any])?["phase"] as? String) == "complete"
        }
        try assertInteractionReveal(camp.app, shot: "verify-03-blockerA-doordie-reveal")
        // Do Or Die stores throw STRINGS in `picks` — the decoder must render
        // them rather than dropping the row. The rows collapse their children
        // into one a11y element, so query any element type.
        XCTAssertTrue(revealRowExists(camp.app, containing: "threw"),
                      "the reveal should show each player's throw")
        try continueOutOfInteraction(camp.app, shot: "verify-04-blockerA-doordie-after-continue")
    }

    // MARK: - 3. Power Pair, human in the winning pair (BLOCKER A)

    @MainActor
    func testPowerPairHumanWinnerRevealsAndContinues() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "reward_challenge_power_pair"])
        try setHand(camp.allyIds[0], ["vote", "extra_vote"])
        try setHand(camp.allyIds[1], ["vote", "extra_vote", "extra_vote"])
        stealViaUI(camp.app, victimName: "Ally")
        openAndPlayCard(camp.app, labelContains: "Power Pair")

        // Pair picker: choose both allies then call it
        for name in ["Ally", "Bran"] {
            // By identifier — the camp strip carries these names too.
            let row = camp.app.buttons["pair-\(name)"]
            XCTAssertTrue(row.waitForExistence(timeout: 8), "pair picker should list \(name)")
            row.tap()
        }
        saveShot("qa-03a-pair-picker")
        let call = camp.app.buttons["call the power pair"]
        XCTAssertTrue(call.waitForExistence(timeout: 5))
        call.tap()

        // Fingers: human 2, Ally 2 (the pair), Bran 3 (the odd one out)
        let two = camp.app.buttons["2"]
        XCTAssertTrue(two.waitForExistence(timeout: 10), "finger buttons 1–3 should show")
        two.tap()
        try interactionAct(camp.allyIds[0], "pick", 2)
        try interactionAct(camp.allyIds[1], "pick", 3)

        try waitServer("interaction complete") {
            (($0["interaction"] as? [String: Any])?["phase"] as? String) == "complete"
        }
        try assertInteractionReveal(camp.app, shot: "verify-05-blockerA-powerpair-reveal")
        // Power Pair stores INTEGER finger counts — the same decoder path must
        // render those too.
        XCTAssertTrue(revealRowExists(camp.app, containing: "held up"),
                      "the reveal should show each player's finger count")
        try continueOutOfInteraction(camp.app, shot: "verify-06-blockerA-powerpair-after-continue")
    }

    // MARK: - 4. Do Or Die against a BOT — the bot never clears a human's card

    @MainActor
    func testDoOrDieVsBotStillOffersContinue() throws {
        let camp = try stageGame(allies: 1, bot: true,
                                 settings: ["botPace": "fast"])
        let botId = try XCTUnwrap(camp.botId)
        let botName = try XCTUnwrap((try serverState()["players"] as? [String: [String: Any]])?[botId]?["name"] as? String)
        try setHand(camp.humanId, ["vote", "reward_challenge_do_or_die", "extra_vote"])
        try setHand(camp.allyIds[0], ["vote"])
        try setHand(botId, ["vote", "extra_vote"])
        stealViaUI(camp.app, victimName: botName)
        openAndPlayCard(camp.app, labelContains: "Do Or Die")

        let targetRow = camp.app.buttons["target-\(botName)"]
        XCTAssertTrue(targetRow.waitForExistence(timeout: 8))
        targetRow.tap()
        let rock = camp.app.buttons["rock"]
        XCTAssertTrue(rock.waitForExistence(timeout: 8))
        rock.tap()

        // The bot answers by itself. A tie routes through the give/swap panel.
        let outcome = try waitServer("interaction resolves", timeout: 30) { st in
            guard let it = st["interaction"] as? [String: Any] else { return false }
            let phase = it["phase"] as? String
            return phase == "complete" || phase == "give"
        }
        if ((outcome["interaction"] as? [String: Any])?["phase"] as? String) == "give" {
            // Tie: both swap one card — exercise the give panel
            let giveRow = camp.app.buttons.matching(
                NSPredicate(format: "label CONTAINS 'Extra Vote'")).firstMatch
            if giveRow.waitForExistence(timeout: 10) {
                saveShot("qa-04a-dod-give-panel")
                giveRow.tap()
            }
            try waitServer("give resolves", timeout: 30) {
                (($0["interaction"] as? [String: Any])?["phase"] as? String) == "complete"
            }
        }

        // Complete. Human initiated → per bots.py the BOT NEVER dismisses,
        // even when the bot itself won. Only the on-device Continue can clear
        // it — which is exactly why it has to exist.
        Thread.sleep(forTimeInterval: 20)
        let it = try interaction()
        XCTAssertNotNil(it, "human-initiated interaction must still be parked (bot did not dismiss)")
        XCTAssertEqual(it?["phase"] as? String, "complete")
        try assertInteractionReveal(camp.app, shot: "qa-04b-dod-vs-bot-reveal")
        try continueOutOfInteraction(camp.app, shot: "qa-04c-dod-vs-bot-after-continue")
    }

    // MARK: - 5. Bot-initiated Numbers Game self-clears

    @MainActor
    func testBotInitiatedNumbersGameSelfClears() throws {
        let camp = try stageGame(allies: 1, bot: true,
                                 settings: ["botPace": "fast", "botStyle": "cutthroat"])
        let botId = try XCTUnwrap(camp.botId)
        try setHand(camp.humanId, ["vote"])
        try setHand(camp.allyIds[0], ["vote"])
        try setHand(botId, ["vote", "reward_challenge_its_a_numbers_game"])

        // Human turn via UI: steal (nothing to take) then draw to end it
        stealViaUI(camp.app, victimName: "Ally")
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 10))
        draw.tap()
        // Ally turn via API
        try api.post("/api/turn/steal", ["gameId": gid, "thiefId": camp.allyIds[0], "targetId": camp.humanId])
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": camp.allyIds[0]])

        // Bot's turn: cutthroat bot plays its reward card
        try waitServer("bot starts the numbers game", timeout: 30) {
            ($0["interaction"] as? [String: Any]) != nil
        }

        // Rounds: the app taps 5, ally picks 5 → the bot wins any round it
        // doesn't also pick 5; tie rounds just repeat.
        for _ in 0..<6 {
            guard let it = try interaction() else { break }
            let phase = it["phase"] as? String
            if phase == "picking" {
                let awaiting = (it["awaiting"] as? [String]) ?? []
                if awaiting.contains(camp.humanId) {
                    let five = camp.app.buttons["5"]
                    XCTAssertTrue(five.waitForExistence(timeout: 10),
                                  "app should offer the finger buttons")
                    five.tap()
                }
                if awaiting.contains(camp.allyIds[0]) {
                    try interactionAct(camp.allyIds[0], "pick", 5)
                }
                Thread.sleep(forTimeInterval: 2)
            } else {
                break   // choose_victim / complete — bot handles the rest
            }
        }

        // The BOT initiated → it must dismiss its own completed interaction.
        try waitServer("interaction self-clears", timeout: 40) {
            ($0["interaction"] as? [String: Any]) == nil
        }
        // And the app must come back to the normal table on its own.
        let back = camp.app.buttons["Steal card from player"].waitForExistence(timeout: 20)
            || camp.app.buttons["Draw card and end your turn"].waitForExistence(timeout: 5)
            || camp.app.staticTexts["The story so far"].waitForExistence(timeout: 5)
        XCTAssertTrue(back, "app should leave InteractionScreen once the bot dismisses")
        saveShot("qa-05-bot-initiated-selfclear")
    }

    // MARK: - 6. Lowest Score Loses — human wins and gets a victory panel

    @MainActor
    func testLowestScoreHumanWinShowsVictoryPanel() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "challenge_lowest_score_loses"])
        try setHand(camp.allyIds[0], ["vote"])
        try setHand(camp.allyIds[1], ["vote"])
        stealViaUI(camp.app, victimName: "Ally")
        openAndPlayCard(camp.app, labelContains: "Lowest Score")

        // Round 1 — human first: stepper down to 0, reach into the bag
        let reach = camp.app.buttons["Reach into the bag"]
        XCTAssertTrue(reach.waitForExistence(timeout: 10), "stepper pull UI should show")
        // Control for the a11y duplication check in scenario 9: an untouched
        // `.buttonStyle(.survivor)` publishes exactly one element.
        XCTAssertEqual(camp.app.buttons.matching(
            NSPredicate(format: "label == %@", "Reach into the bag")).count, 1,
                       "a plain survivor-styled button publishes once")
        saveShot("qa-06a-lowest-stepper")
        // Deterministic, not best-effort. This was `if decrement.exists`, which
        // silently did nothing whenever the stepper had not settled — the human
        // then pulled 1 rock instead of 0 and the whole scenario drifted, with
        // the failure surfacing several steps later as "only 7 rocks left".
        let decrement = camp.app.steppers.buttons["Decrement"].firstMatch
        XCTAssertTrue(decrement.waitForExistence(timeout: 8), "the pull stepper should offer Decrement")
        decrement.tap()   // 1 → 0
        // Read it back off the stepper rather than assuming. The scenario needs
        // the human to pull ZERO; a silent miss here drifts the whole bag and
        // surfaces several steps later as "only 7 rocks left".
        let stepper = camp.app.steppers.firstMatch
        let pullsZero = NSPredicate(format: "label CONTAINS '0' OR value CONTAINS '0'")
        expectation(for: pullsZero, evaluatedWith: stepper)
        waitForExpectations(timeout: 5)
        reach.tap()
        // Ally takes ALL 8 rocks (score −1 guaranteed), Bran pretends (0)
        try challengeAct(camp.allyIds[0], "pull", 8)
        try challengeAct(camp.allyIds[1], "pull", 0)

        // Round 2 — Bran first (last actor), takes all 8 again; human pulls 0
        try waitServer("round 2 begins", timeout: 15) { st in
            guard let ch = st["challenge"] as? [String: Any] else { return false }
            return (ch["round"] as? Int) == 2
        }
        try challengeAct(camp.allyIds[1], "pull", 8)
        let reach2 = camp.app.buttons["Reach into the bag"]
        XCTAssertTrue(reach2.waitForExistence(timeout: 15), "human's round-2 pull should show")
        reach2.tap()

        // Human is last standing → wins, and takes the Necklace with it.
        let st = try waitServer("challenge complete") {
            (($0["challenge"] as? [String: Any])?["phase"] as? String) == "complete"
        }
        XCTAssertEqual((st["challenge"] as? [String: Any])?["winnerId"] as? String, camp.humanId)
        XCTAssertEqual(st["necklaceHolder"] as? String, camp.humanId,
                       "necklace awarded server-side")

        // ChallengeScreen STAYS mounted and shows the win (BLOCKER B fix).
        try assertChallengeVictoryPanel(camp.app, winnerName: Self.playerName,
                                        expectNecklace: true,
                                        shot: "qa-06b-lowest-win-victory-panel")
        try continueOutOfChallenge(camp.app, shot: "qa-06c-lowest-after-continue")

        // Continue clears it and the turn UI comes back.
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 15),
                      "the turn UI returns once the Challenge is dismissed")
        draw.tap()
        try waitServer("turn ends normally", timeout: 15) { st in
            (st["challenge"] as? [String: Any]) == nil
        }
    }

    // MARK: - 7. Highest Bidder — bid stepper + the bidding-specific pass label

    @MainActor
    func testHighestBidderBidAndPassUI() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "challenge_highest_bidder"])
        try setHand(camp.allyIds[0], ["vote"])
        try setHand(camp.allyIds[1], ["vote"])
        stealViaUI(camp.app, victimName: "Ally")
        openAndPlayCard(camp.app, labelContains: "Highest Bidder")

        // Human must open the bidding: stepper defaults to Bid 1
        let placeBid = camp.app.buttons["Place the bid"]
        XCTAssertTrue(placeBid.waitForExistence(timeout: 10), "bid UI should show")
        XCTAssertFalse(camp.app.buttons["Pass on bidding"].exists,
                       "first bidder cannot pass")
        XCTAssertFalse(camp.app.buttons["Pass the bag"].exists,
                       "first bidder cannot pass")
        saveShot("qa-07a-bid-opening")
        placeBid.tap()
        // Ally raises to 2, Bran passes → back to the human with bid/pass
        try challengeAct(camp.allyIds[0], "bid", 2)
        try challengeAct(camp.allyIds[1], "pass", nil)

        // In Highest Bidder you pass on the BIDDING; "Pass the bag" belongs to
        // 1 Now or 2 Later and must not appear here.
        let passButton = camp.app.buttons["Pass on bidding"]
        XCTAssertTrue(passButton.waitForExistence(timeout: 15),
                      "the bidding pass button should read 'Pass on bidding'")
        XCTAssertFalse(camp.app.buttons["Pass the bag"].exists,
                       "'Pass the bag' is the 1 Now or 2 Later label, not this one")
        saveShot("qa-07b-bid-or-pass")
        passButton.tap()

        // Ally won at 2 → pulls twice via API; both grey with p≈0.83
        try waitServer("pulling phase", timeout: 15) { st in
            guard let ch = st["challenge"] as? [String: Any] else { return false }
            return (ch["phase"] as? String) == "pulling"
        }
        for _ in 0..<2 {
            if let ch = try challenge(), (ch["phase"] as? String) == "pulling",
               (ch["currentPlayerId"] as? String) == camp.allyIds[0] {
                try challengeAct(camp.allyIds[0], "pull", nil)
            }
        }
        // Wherever the rocks fell, drive to completion via API
        for _ in 0..<12 {
            guard let ch = try challenge() else { break }
            if (ch["phase"] as? String) == "complete" { break }
            guard let cur = ch["currentPlayerId"] as? String else { break }
            if cur == camp.humanId { break }  // human's move — stop scripting
            let actions = (ch["actions"] as? [String]) ?? []
            if actions.contains("pull") {
                try challengeAct(cur, "pull", nil)
            } else if actions.contains("bid") {
                let bid = ((ch["currentBid"] as? Int) ?? 0) + 1
                try challengeAct(cur, "bid", bid)
            }
            Thread.sleep(forTimeInterval: 0.3)
        }
        let ch = try challenge()
        let phase = ch?["phase"] as? String
        dumpState("qa-07c-bidder-end")
        saveShot("qa-07c-bidder-end")
        // If it completed with an ALLY winner while the human still holds the
        // turn, the human still gets the reveal + Continue.
        if phase == "complete" {
            let winnerId = ch?["winnerId"] as? String
            let winnerName = winnerId.flatMap {
                ((try? serverState())?["players"] as? [String: [String: Any]])?[$0]?["name"] as? String
            }
            try assertChallengeVictoryPanel(camp.app, winnerName: winnerName,
                                            expectNecklace: false,
                                            shot: "qa-07d-bidder-victory-panel")
            try continueOutOfChallenge(camp.app, shot: "qa-07e-bidder-after-continue")
            let draw = camp.app.buttons["Draw card and end your turn"]
            XCTAssertTrue(draw.waitForExistence(timeout: 15),
                          "the turn UI returns once the Challenge is dismissed")
        }
    }

    // MARK: - 8. Pull or Steal — the steal-a-rock picker, then the reveal

    @MainActor
    func testPullOrStealStealUI() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote"])
        try setHand(camp.allyIds[0], ["vote", "challenge_pull_or_steal"])
        try setHand(camp.allyIds[1], ["vote"])

        // Human's turn via UI: steal from BRAN (lone vote — nothing to take,
        // so Ally keeps the staged challenge card) + draw (ends turn)
        stealViaUI(camp.app, victimName: "Bran")
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 10))
        draw.tap()

        // Ally's turn via API: skip the steal, play the challenge card
        try api.post("/api/test/set_flags",
                     ["gameId": gid, "playerId": camp.allyIds[0], "hasStolen": true])
        let st = try serverState()
        let players = try XCTUnwrap(st["players"] as? [String: [String: Any]])
        let hand = try XCTUnwrap(players[camp.allyIds[0]]?["hand"] as? [[String: Any]])
        let idx = try XCTUnwrap(hand.firstIndex(where: {
            ($0["type"] as? String) == "challenge_pull_or_steal" }))
        try api.post("/api/turn/play_card",
                     ["gameId": gid, "playerId": camp.allyIds[0], "cardIdx": idx])

        // Order: Ally (1) must pull, Bran (2) next — make Bran pull too so the
        // human (3) has two steal targets.
        try waitServer("challenge starts", timeout: 10) { ($0["challenge"] as? [String: Any]) != nil }
        try challengeAct(camp.allyIds[0], "pull", nil)
        try challengeAct(camp.allyIds[1], "pull", nil)

        // Human's move on-device: pull or steal — verify the steal section
        let stealHeader = camp.app.staticTexts["…or steal a rock"]
        XCTAssertTrue(stealHeader.waitForExistence(timeout: 15),
                      "steal option should render for the human")
        saveShot("qa-08a-pull-or-steal-options")
        let targetRow = camp.app.buttons["steal-rock-Ally"]
        XCTAssertTrue(targetRow.waitForExistence(timeout: 8), "steal target rows should list Ally")
        targetRow.tap()

        // Ally (robbed) takes the next turn: pulls the last rock → reveal
        try waitServer("ally back on the clock", timeout: 10) { st in
            ((st["challenge"] as? [String: Any])?["currentPlayerId"] as? String) == camp.allyIds[0]
        }
        try challengeAct(camp.allyIds[0], "pull", nil)
        let done = try waitServer("challenge completes") {
            (($0["challenge"] as? [String: Any])?["phase"] as? String) == "complete"
        }
        let winnerId = (done["challenge"] as? [String: Any])?["winnerId"] as? String
        let winnerName = winnerId.flatMap {
            (done["players"] as? [String: [String: Any]])?[$0]?["name"] as? String
        }
        dumpState("qa-08b-pull-or-steal-complete")

        // It is the ALLY's turn, not the human's — the old build unmounted the
        // screen here and nobody on this device could clear it. Now the human
        // sees the reveal and can Continue for the table.
        try assertChallengeVictoryPanel(camp.app, winnerName: winnerName,
                                        expectNecklace: false,
                                        shot: "qa-08c-pull-or-steal-victory-panel")
        try continueOutOfChallenge(camp.app, shot: "qa-08d-pull-or-steal-after-continue")
        try api.post("/api/turn/draw", ["gameId": gid, "playerId": camp.allyIds[0]])
        print("QA8 winner:", winnerName ?? "none")
    }

    // MARK: - 9. Sorry For You window over the InteractionScreen

    @MainActor
    func testSorryForYouOverlayOverInteraction() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "sorry_for_you"])
        try setHand(camp.allyIds[0], ["vote", "reward_challenge_do_or_die"])
        try setHand(camp.allyIds[1], ["vote"])

        // Human's turn quickly ends: steal + draw via UI
        stealViaUI(camp.app, victimName: "Bran")
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 10))
        draw.tap()

        // Ally's turn (API): skip steal, throw down Do Or Die at the human
        try api.post("/api/test/set_flags",
                     ["gameId": gid, "playerId": camp.allyIds[0], "hasStolen": true])
        let st = try serverState()
        let players = try XCTUnwrap(st["players"] as? [String: [String: Any]])
        let hand = try XCTUnwrap(players[camp.allyIds[0]]?["hand"] as? [[String: Any]])
        let idx = try XCTUnwrap(hand.firstIndex(where: {
            ($0["type"] as? String) == "reward_challenge_do_or_die" }))
        try api.post("/api/turn/play_card",
                     ["gameId": gid, "playerId": camp.allyIds[0], "cardIdx": idx,
                      "targetId": camp.humanId, "choice": "rock"])

        // The app is the challenged player: throw SCISSORS to lose on purpose
        let scissors = camp.app.buttons["Scissors"]
        XCTAssertTrue(scissors.waitForExistence(timeout: 15),
                      "the challenged human should get the throw buttons")
        saveShot("qa-09a-dod-target-throws")
        scissors.tap()

        // Ally won → raids the human, who holds Sorry For You → window opens
        let sorry = camp.app.buttons["Sorry for you!"].firstMatch
        XCTAssertTrue(sorry.waitForExistence(timeout: 15),
                      "defender dialog should cover the interaction screen")
        // A11y de-duplication. "Let them take it" is a plain-string Button and
        // publishes ONCE. "Sorry for you!" wraps a Label(_:systemImage:), whose
        // inner text `children: .combine` re-published as a second .button on
        // the same text frame; `children: .ignore` drops the subtree, so it now
        // publishes once too.
        XCTAssertEqual(camp.app.buttons.matching(
            NSPredicate(format: "label == %@", "Let them take it")).count, 1,
                       "the decline button must appear once in the a11y tree")
        XCTAssertEqual(camp.app.buttons.matching(
            NSPredicate(format: "label == %@", "Sorry for you!")).count, 1,
                       "the Sorry For You button must appear once in the a11y tree")
        saveShot("qa-09b-sorry-over-interaction")
        sorry.tap()

        // Window resolves; theft cancelled. The interaction underneath is
        // already complete → the table lands on the REVEAL, not a dead spinner.
        try waitServer("reactive window closed", timeout: 15) { st in
            let theft = st["pending_theft"] as? [String: Any]
            return theft == nil || (theft?["reactive_window_open"] as? Bool) != true
        }
        let it = try interaction()
        XCTAssertEqual(it?["phase"] as? String, "complete",
                       "interaction underneath finished while the raid hung")
        try assertInteractionReveal(camp.app, shot: "qa-09c-reveal-after-sorry")
        try continueOutOfInteraction(camp.app, shot: "qa-09d-after-continue")
    }

    // MARK: - 10. BLOCKER B — a bot-played Challenge that a human wins

    /// The exact wedge: the bot plays a Challenge on its own turn, the human
    /// wins it, and `bots.next_action` refuses to act while a human-won
    /// complete Challenge is parked. Nothing but an on-device Continue can
    /// free the table.
    ///
    /// Determinism: the bot always bids `currentBid + 1` while that stays inside
    /// the bag size, so baiting it to bid the whole bag (11) makes it pull every
    /// rock — the Purple Rock is then guaranteed to come out and knock it out.
    /// The API-driven ally is walked into the same trap in the following round,
    /// leaving the human as the last player standing every time.
    @MainActor
    func testBotPlayedChallengeHumanWinsShowsVictoryAndUnwedges() throws {
        // Three seats minimum — the server refuses to start a two-player game.
        let camp = try stageGame(allies: 1, bot: true,
                                 settings: ["botPace": "fast", "botStyle": "cutthroat"])
        let botId = try XCTUnwrap(camp.botId)
        let allyId = camp.allyIds[0]
        let botName = try XCTUnwrap((try serverState()["players"] as? [String: [String: Any]])?[botId]?["name"] as? String)
        try setHand(camp.humanId, ["vote"])
        try setHand(allyId, ["vote"])

        // Cycle turns until the bot actually throws down the Challenge card
        // (a bot holds its cards some turns — cutthroat plays 95% of them).
        var staged = false
        for _ in 0..<6 {
            if try challenge() != nil { break }
            let st = try serverState()
            let cur = currentTurnId(st)
            if cur == camp.humanId {
                endHumanTurnViaUI(camp.app, victimName: "Ally")
                staged = false
            } else if cur == allyId {
                _ = try? api.post("/api/turn/steal",
                                  ["gameId": gid, "thiefId": allyId, "targetId": camp.humanId])
                _ = try? api.post("/api/turn/draw", ["gameId": gid, "playerId": allyId])
                staged = false
            } else if cur == botId {
                if !staged {
                    try setHand(botId, ["challenge_highest_bidder"])
                    staged = true
                }
                _ = try waitServerSoft(timeout: 30) { st in
                    (st["challenge"] as? [String: Any]) != nil
                        || self.currentTurnId(st) != botId
                }
            } else {
                Thread.sleep(forTimeInterval: 1)
            }
        }
        let live = try XCTUnwrap(try challenge(), "the bot should have played its Challenge card")
        XCTAssertEqual(live["type"] as? String, "highest_bidder")
        saveShot("verify-07-blockerB-bot-challenge-live")

        // The human has to win this Challenge, and the bag decides who does.
        //
        // This used to drive the bidding instead: bait everyone to one under
        // the bag so a non-human bid the whole thing and was guaranteed the
        // Purple Rock. That encoded what the bots would do, and it stopped
        // being true the day they learned to bid strategically — no bot now
        // volunteers to pull all eleven, so nobody was ever knocked out and
        // the Challenge never ended.
        //
        // Take the luck out of the bag instead of predicting the players. All
        // grey means whoever wins the bidding pulls clean and wins, so the
        // only thing left to arrange is that the winner is the human — and a
        // bid of one under the bag is above every bot's appetite whatever
        // their private limit is.
        try api.post("/api/test/stack_bag",
                     ["gameId": gid, "bag": ["grey": 11, "purple": 0]])

        var done: [String: Any] = [:]
        for _ in 0..<80 {
            let st = try serverState()
            guard let ch = st["challenge"] as? [String: Any] else { break }
            if (ch["phase"] as? String) == "complete" { done = st; break }
            guard let cur = ch["currentPlayerId"] as? String else { break }
            let bid = (ch["currentBid"] as? Int) ?? 0
            let maxBid = (ch["maxBid"] as? Int) ?? 11

            if (ch["phase"] as? String) == "pulling" {
                // Whoever won the bidding empties their bid, one rock at a time.
                if cur == camp.humanId || cur == allyId {
                    try challengeAct(cur, "pull", nil)
                }
                Thread.sleep(forTimeInterval: 0.4)
                continue
            }
            switch cur {
            case camp.humanId:
                // One under the bag: above every bot's private limit, and the
                // bluff step cannot reach it either.
                if bid < maxBid - 1 {
                    try challengeAct(camp.humanId, "bid", maxBid - 1)
                } else {
                    try challengeAct(camp.humanId, "pass", nil)
                }
            case allyId:
                // The first bidder of a round is not allowed to pass.
                if bid == 0 {
                    try challengeAct(allyId, "bid", 1)
                } else {
                    try challengeAct(allyId, "pass", nil)
                }
            default:
                Thread.sleep(forTimeInterval: 0.4)   // the bot's move
            }
            Thread.sleep(forTimeInterval: 0.3)
        }
        if done.isEmpty {
            done = try waitServer("challenge completes", timeout: 60) { st in
                (st["challenge"] as? [String: Any])?["phase"] as? String == "complete"
            }
        }
        XCTAssertEqual((done["challenge"] as? [String: Any])?["winnerId"] as? String,
                       camp.humanId, "the human should have won the Challenge")
        XCTAssertEqual(currentTurnId(done), botId,
                       "the parked Challenge sits on the BOT's turn — the old wedge")

        // The bot is now stuck by design: it will not act while a human-won
        // Challenge is parked. Prove nothing moves...
        let turnBefore = currentTurnId(done)
        Thread.sleep(forTimeInterval: 15)
        XCTAssertNotNil(try challenge(), "no bot clears a human's Challenge win")
        XCTAssertEqual(currentTurnId(try serverState()), turnBefore,
                       "the table really is frozen until somebody dismisses")

        // ...and that the victory panel is the way out.
        try assertChallengeVictoryPanel(camp.app, winnerName: Self.playerName,
                                        expectNecklace: false,
                                        shot: "verify-08-blockerB-victory-panel")
        try continueOutOfChallenge(camp.app, shot: "verify-09-blockerB-after-continue")

        // The bot resumes: it draws and the turn comes back round.
        try waitServer("bot resumes after Continue", timeout: 25) { st in
            self.currentTurnId(st) != turnBefore
        }
        saveShot("verify-10-blockerB-bot-resumed")
    }

    // MARK: - 11. Tribal Council — the server-canonical phase order

    /// Control The Vote leaves two mandatory Vote Cards in one hand. They are
    /// separate parchments: both must be cast, but they may carry different
    /// names. This is the native regression for the web parity fix.
    @MainActor
    func testTwoMandatoryVoteCardsOfferOneNameOrSplit() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "vote"])
        try setHand(camp.allyIds[0], ["vote"])
        try setHand(camp.allyIds[1], ["vote"])
        try api.post("/api/test/stack_deck",
                     ["gameId": gid, "top": ["tribal_council_single"]])

        stealViaUI(camp.app, victimName: "Ally")
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 10))
        draw.tap()
        try waitServer("tribal council opens", timeout: 20) {
            ($0["phase"] as? String) == "tribal_council"
        }

        try tapLeaderButton(camp.app, tap: "Advance to Advantages",
                            to: "advantage_play")
        try tapLeaderButton(camp.app, tap: "Advance to Discussion", to: "discussion")
        try tapLeaderButton(camp.app, tap: "Start Voting", to: "voting")

        let mandatoryNotice = camp.app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "You cast 2 votes tonight")
        ).firstMatch
        XCTAssertTrue(mandatoryNotice.waitForExistence(timeout: 12),
                      "the ballot should explain that both Vote Cards must be cast")

        let allyParchment = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "Ally")
        ).firstMatch
        XCTAssertTrue(allyParchment.waitForExistence(timeout: 8),
                      "the ballot should offer Ally as a target")
        allyParchment.tap()

        XCTAssertTrue(camp.app.staticTexts["How many votes?"]
                        .waitForExistence(timeout: 8))
        XCTAssertTrue(camp.app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "You hold 2 Vote Cards tonight")
        ).firstMatch.exists)
        XCTAssertTrue(camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "2 votes against Ally")
        ).firstMatch.exists,
                      "both mandatory parchments may go on one name")

        let split = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS %@", "Split votes across players")
        ).firstMatch
        XCTAssertTrue(split.exists,
                      "two mandatory parchments may be split without an Extra Vote")
        split.tap()
        XCTAssertTrue(camp.app.staticTexts["Write your parchments"]
                        .waitForExistence(timeout: 8))
        XCTAssertTrue(camp.app.staticTexts.matching(
            NSPredicate(format: "label CONTAINS %@", "Cast at least 2")
        ).firstMatch.exists)
    }

    /// Open → Advantage → Talk → Vote → Idols → Reveal, driven end to end from
    /// the human leader's action bar (every LEADER_ONLY endpoint now carries
    /// the acting player's id, so the Leader's own buttons are accepted), with
    /// a staged tribal advantage that has to appear in the advantage window (it
    /// used to be filtered out because server hands are bare `{"type": …}`
    /// stubs).
    @MainActor
    func testTribalCouncilLeaderFlowInCanonicalOrder() throws {
        let camp = try stageGame(allies: 2, bot: false)
        try setHand(camp.humanId, ["vote", "control_the_vote"])
        try setHand(camp.allyIds[0], ["vote"])
        try setHand(camp.allyIds[1], ["vote"])
        // The drawer becomes Council Leader — put the card on top for the human
        try api.post("/api/test/stack_deck", ["gameId": gid, "top": ["tribal_council_single"]])

        stealViaUI(camp.app, victimName: "Ally")
        let draw = camp.app.buttons["Draw card and end your turn"]
        XCTAssertTrue(draw.waitForExistence(timeout: 10))
        draw.tap()

        let opened = try waitServer("tribal council opens", timeout: 20) {
            ($0["phase"] as? String) == "tribal_council"
        }
        XCTAssertEqual((opened["currentVote"] as? [String: Any])?["councilLeaderId"] as? String,
                       camp.humanId, "the drawer leads the council")

        // Tracker: six labels, canonical order, each rendered whole (no
        // mid-word hyphenation, no "Announ…" truncation).
        for label in ["Open", "Advantage", "Talk", "Vote", "Idols", "Reveal"] {
            XCTAssertTrue(camp.app.staticTexts[label].waitForExistence(timeout: 10),
                          "phase tracker should read '\(label)' unbroken")
        }
        saveShot("verify-11-tribal-tracker")
        saveShot("verify2-02-tracker")

        // Every transition below is a real tap by the human Council Leader —
        // no API fallback. LEADER_ONLY endpoints answered 403 to the phone
        // until APIClient started sending playerId; this is the proof.
        try tapLeaderButton(camp.app, tap: "Advance to Advantages",
                            to: "advantage_play")
        let advantage = camp.app.buttons.matching(
            NSPredicate(format: "label CONTAINS 'Control The Vote'")).firstMatch
        XCTAssertTrue(advantage.waitForExistence(timeout: 10),
                      "a staged tribal advantage must appear in the advantage window")
        saveShot("verify-12-tribal-advantage-window")

        try tapLeaderButton(camp.app, tap: "Advance to Discussion", to: "discussion")
        // Discussion's door is Start Voting — it used to read "Advance to Immunity".
        try tapLeaderButton(camp.app, tap: "Start Voting", to: "voting")
        // One door out of voting, not two. The bar used to offer "Open Idol
        // Window" and "Reveal Votes" side by side in identical styling, and
        // taking the second tallied on the spot — which silently voided every
        // idol at the table, because the only screen that offers an idol is
        // the immunity phase that button skipped.
        XCTAssertTrue(camp.app.buttons["Seal the Box · Call for Idols"]
                        .waitForExistence(timeout: 12),
                      "the voting leader bar must offer the seal-and-call-for-idols door")
        XCTAssertFalse(camp.app.buttons["Reveal Votes"].exists,
                       "voting must not offer a door that skips the idol window")
        saveShot("verify-13-tribal-voting")

        // Every ballot in (all three via API so the box is provably full).
        for (voter, target) in [(camp.humanId, camp.allyIds[0]),
                                (camp.allyIds[0], camp.allyIds[1]),
                                (camp.allyIds[1], camp.allyIds[0])] {
            try api.post("/api/vote/cast",
                         ["gameId": gid, "voterId": voter,
                          "votesData": [["targetId": target, "votes": 1]]])
        }

        // Sealing the box IS the call for idols: the tally waits one screen on.
        try tapLeaderButton(camp.app, tap: "Seal the Box · Call for Idols",
                            to: "immunity")
        saveShot("verify-14-tribal-immunity")

        // The tally, tapped by the Leader on the phone — no API rescue.
        try tapLeaderButton(camp.app, tap: "Read the Votes", to: "reveal",
                            alsoAccept: ["results"])
        saveShot("verify-15-tribal-reveal")
        saveShot("verify2-01-human-leader-council")

        // ...and the Leader closes the council from the phone too.
        let complete = camp.app.buttons["Complete Tribal"]
        if complete.waitForExistence(timeout: 12) {
            complete.tap()
            try waitServer("council closes", timeout: 20) { st in
                (st["phase"] as? String) != "tribal_council"
                    || (st["currentVote"] as? [String: Any]) == nil
            }
            XCTAssertFalse(camp.app.staticTexts["Server Error"].exists,
                           "Complete Tribal must not be refused for the Leader")
        }
    }

    /// Tap a leader-bar control and require the server to move: the phone's own
    /// request has to be accepted (LEADER_ONLY endpoints now carry playerId),
    /// so a "Server Error" alert or a stalled phase is a failure, not a detour.
    @MainActor
    private func tapLeaderButton(_ app: XCUIApplication, tap label: String,
                                 to phase: String,
                                 alsoAccept extra: [String] = []) throws {
        let button = app.buttons[label]
        XCTAssertTrue(button.waitForExistence(timeout: 12),
                      "the leader bar should offer '\(label)' here")
        button.tap()
        let accepted = Set([phase] + extra)
        let reached = try waitServerSoft(timeout: 15) {
            guard let p = ($0["currentVote"] as? [String: Any])?["phase"] as? String
            else { return false }
            return accepted.contains(p)
        }
        XCTAssertFalse(app.staticTexts["Server Error"].exists,
                       "'\(label)' was refused for the Council Leader")
        XCTAssertTrue(reached,
                      "'\(label)' should carry the council to \(phase) from the phone alone")
    }
}

// MARK: - Scratch-server orchestration (private copy for this file)

/// Shared by the visual-audit suite too, so it is not file-private.
final class QAScratchAPI {
    enum Failure: Error, CustomStringConvertible {
        case transport(String)
        case badStatus(Int, String)
        case notJSON
        var description: String {
            switch self {
            case .transport(let m): return "transport: \(m)"
            case .badStatus(let c, let b): return "HTTP \(c): \(b)"
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
        nonisolated(unsafe) var outcome: Result<[String: Any], Failure> = .failure(.transport("no response"))
        session.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            if let error { outcome = .failure(.transport(error.localizedDescription)); return }
            guard let http = response as? HTTPURLResponse else {
                outcome = .failure(.transport("not an HTTP response")); return
            }
            let text = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            guard (200...299).contains(http.statusCode) else {
                outcome = .failure(.badStatus(http.statusCode, text)); return
            }
            guard let data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                outcome = .failure(.notJSON); return
            }
            outcome = .success(json)
        }.resume()
        _ = semaphore.wait(timeout: .now() + 15)
        return try outcome.get()
    }
}
