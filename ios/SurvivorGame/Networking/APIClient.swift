import Foundation

actor APIClient {
    let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: URL) {
        self.baseURL = baseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        // The island gate returns an HttpOnly cookie. Use the app's shared
        // cookie jar explicitly so it survives APIClient recreation and can
        // also be handed to the Socket.IO handshake.
        config.httpCookieStorage = .shared
        config.httpCookieAcceptPolicy = .always
        config.httpShouldSetCookies = true
        self.session = URLSession(configuration: config)
        self.decoder = JSONDecoder()
    }

    // MARK: - Generic Request

    private func request<T: Decodable>(
        _ method: String,
        path: String,
        body: [String: Any]? = nil
    ) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        // Foundation normally imports Set-Cookie into the configured jar, but
        // an immediate follow-up request can race that propagation on device.
        // Import response cookies synchronously before callers continue.
        let headerFields = httpResponse.allHeaderFields.reduce(into: [String: String]()) {
            guard let key = $1.key as? String else { return }
            $0[key] = String(describing: $1.value)
        }
        for cookie in HTTPCookie.cookies(withResponseHeaderFields: headerFields, for: url) {
            HTTPCookieStorage.shared.setCookie(cookie)
            IslandAccessCookieStore.persist(cookie, for: url)
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let errorBody = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let message = errorBody?["message"] as? String ?? "Request failed"
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: message)
        }

        return try decoder.decode(T.self, from: data)
    }

    private func post<T: Decodable>(path: String, body: [String: Any] = [:]) async throws -> T {
        try await request("POST", path: path, body: body)
    }

    private func get<T: Decodable>(path: String) async throws -> T {
        try await request("GET", path: path)
    }

    // MARK: - Game Management

    func createGame(
        deckMode: String = "official",
        expansion: Bool = false,
        settings: [String: String]? = nil
    ) async throws -> CreateGameResponse {
        var body: [String: Any] = ["deckMode": deckMode, "expansion": expansion]
        if let settings { body["settings"] = settings }
        return try await post(path: "/api/game/create", body: body)
    }

    func joinGame(gameId: String, name: String, color: String?) async throws -> JoinGameResponse {
        var body: [String: Any] = ["gameId": gameId, "name": name]
        if let color { body["color"] = color }
        return try await post(path: "/api/player/join", body: body)
    }

    func rejoinGame(gameId: String, playerId: String) async throws -> RejoinGameResponse {
        try await post(path: "/api/player/rejoin", body: ["gameId": gameId, "playerId": playerId])
    }

    func startGame(gameId: String) async throws -> ActionResponse {
        try await post(path: "/api/game/start_full", body: ["gameId": gameId])
    }

    func resetGame(gameId: String) async throws -> ActionResponse {
        try await post(path: "/api/game/reset", body: ["gameId": gameId])
    }

    func finishGame(gameId: String, winnerId: String) async throws -> ActionResponse {
        try await post(path: "/api/game/finish", body: ["gameId": gameId, "winnerId": winnerId])
    }

    func getGameState(gameId: String) async throws -> GameState {
        try await get(path: "/api/game/\(gameId)/state")
    }

    // MARK: - Turn Actions

    func steal(gameId: String, thiefId: String, targetId: String) async throws -> ActionResponse {
        try await post(path: "/api/turn/steal", body: [
            "gameId": gameId, "thiefId": thiefId, "targetId": targetId
        ])
    }

    func playCard(
        gameId: String, playerId: String, cardIdx: Int,
        params: [String: Any] = [:]
    ) async throws -> PlayCardResponse {
        // Card params (targetId, allyId, victimId, cardType, takeIndex, choice…)
        // ride along as top-level kwargs — the server reads them as effect args.
        var body: [String: Any] = [
            "gameId": gameId, "playerId": playerId, "cardIdx": cardIdx
        ]
        for (key, value) in params { body[key] = value }
        return try await post(path: "/api/turn/play_card", body: body)
    }

    func draw(gameId: String, playerId: String) async throws -> DrawResponse {
        try await post(path: "/api/turn/draw", body: [
            "gameId": gameId, "playerId": playerId
        ])
    }

    func advanceTurn(gameId: String) async throws -> ActionResponse {
        try await post(path: "/api/turn/advance", body: ["gameId": gameId])
    }

    // MARK: - Reactive

    func playReactiveCard(gameId: String, playerId: String, cardIdx: Int, theftContext: [String: Any]) async throws -> ActionResponse {
        try await post(path: "/api/reactive/play_card", body: [
            "gameId": gameId, "playerId": playerId, "cardIdx": cardIdx, "theftContext": theftContext
        ])
    }

    func completeTheft(gameId: String) async throws -> ActionResponse {
        try await post(path: "/api/reactive/complete_theft", body: ["gameId": gameId])
    }

    // MARK: - Tribal Council

    // Leader-only controls: the server checks playerId against the council
    // leader (LEADER_ONLY in survivor_server.py) and 403s without it.
    func startVoting(gameId: String, playerId: String, voteType: String) async throws -> ActionResponse {
        try await post(path: "/api/vote/start", body: [
            "gameId": gameId, "playerId": playerId, "voteType": voteType
        ])
    }

    func castVote(gameId: String, voterId: String, votesData: [[String: Any]]) async throws -> ActionResponse {
        try await post(path: "/api/vote/cast", body: [
            "gameId": gameId, "voterId": voterId, "votesData": votesData
        ])
    }

    func revealVotes(gameId: String, playerId: String) async throws -> ActionResponse {
        try await post(path: "/api/vote/reveal", body: ["gameId": gameId, "playerId": playerId])
    }

    func tieBreak(gameId: String, leaderId: String, chosenId: String) async throws -> ActionResponse {
        try await post(path: "/api/vote/tiebreak", body: [
            "gameId": gameId, "leaderId": leaderId, "chosenId": chosenId
        ])
    }

    func completeTribial(gameId: String, playerId: String) async throws -> ActionResponse {
        try await post(path: "/api/tribal/complete", body: ["gameId": gameId, "playerId": playerId])
    }

    func advanceTribal(gameId: String, playerId: String, phase: String) async throws -> ActionResponse {
        try await post(path: "/api/tribal/advance", body: [
            "gameId": gameId, "playerId": playerId, "phase": phase
        ])
    }

    func playAdvantage(gameId: String, playerId: String, advantageType: String, targetId: String?) async throws -> ActionResponse {
        var body: [String: Any] = [
            "gameId": gameId, "playerId": playerId, "advantageType": advantageType
        ]
        if let targetId { body["targetId"] = targetId }
        return try await post(path: "/api/tribal/advantage", body: body)
    }

    func playImmunity(gameId: String, playerId: String, targetId: String? = nil) async throws -> ActionResponse {
        // targetId lets you shield an ally with your idol; omitted = yourself
        var body: [String: Any] = ["gameId": gameId, "playerId": playerId]
        if let targetId { body["targetId"] = targetId }
        return try await post(path: "/api/immunity/play", body: body)
    }

    func blockImmunity(gameId: String, playerId: String, targetId: String) async throws -> ActionResponse {
        try await post(path: "/api/immunity/block", body: [
            "gameId": gameId, "playerId": playerId, "targetId": targetId
        ])
    }

    func resetTribal(gameId: String, playerId: String) async throws -> ActionResponse {
        try await post(path: "/api/tribal/reset", body: ["gameId": gameId, "playerId": playerId])
    }

    func changeLeader(gameId: String, newLeaderId: String) async throws -> ActionResponse {
        try await post(path: "/api/leader/change", body: ["gameId": gameId, "newLeaderId": newLeaderId])
    }

    func enhancedTieBreak(gameId: String, leaderId: String, eliminationType: String, tiedPlayers: [String], chosenIds: [String]) async throws -> ActionResponse {
        try await post(path: "/api/tribal/tie_enhanced", body: [
            "gameId": gameId, "leaderId": leaderId, "eliminationType": eliminationType,
            "tiedPlayers": tiedPlayers, "chosenIds": chosenIds
        ])
    }

    // MARK: - Final Tribal

    func advanceFinal(gameId: String, phase: String) async throws -> ActionResponse {
        try await post(path: "/api/final/advance", body: ["gameId": gameId, "phase": phase])
    }

    func castFinalVote(gameId: String, juryMemberId: String, finalistId: String) async throws -> ActionResponse {
        try await post(path: "/api/final/vote", body: [
            "gameId": gameId, "juryMemberId": juryMemberId, "finalistId": finalistId
        ])
    }

    func finalTieBreak(gameId: String, leaderId: String, chosenWinner: String) async throws -> ActionResponse {
        try await post(path: "/api/final/tie_break", body: [
            "gameId": gameId, "leaderId": leaderId, "chosenWinner": chosenWinner
        ])
    }

    func signalReady(gameId: String, juryMemberId: String) async throws -> ActionResponse {
        try await post(path: "/api/final/ready", body: ["gameId": gameId, "juryMemberId": juryMemberId])
    }

    // MARK: - Lobby & Settings

    func addBot(gameId: String) async throws -> ActionResponse {
        try await post(path: "/api/player/add_bot", body: ["gameId": gameId])
    }

    func removeBot(gameId: String, playerId: String) async throws -> ActionResponse {
        try await post(path: "/api/player/remove_bot", body: [
            "gameId": gameId, "playerId": playerId
        ])
    }

    func renamePlayer(gameId: String, playerId: String, newName: String) async throws -> ActionResponse {
        try await post(path: "/api/player/rename", body: [
            "gameId": gameId, "playerId": playerId, "newName": newName
        ])
    }

    func updateGameSettings(gameId: String, playerId: String, settings: [String: String]) async throws -> ActionResponse {
        try await post(path: "/api/game/update_settings", body: [
            "gameId": gameId, "playerId": playerId, "settings": settings
        ])
    }

    func deleteGame(gameId: String) async throws -> ActionResponse {
        try await post(path: "/api/game/delete", body: ["gameId": gameId])
    }

    // MARK: - Challenges & Interactions (Let's Go To Rocks)

    func challengeAction(gameId: String, playerId: String, action: String, value: ChallengeValue?) async throws -> ActionResponse {
        // value is an Int for pulls/bids, a player id String for steals
        var body: [String: Any] = [
            "gameId": gameId, "playerId": playerId, "action": action
        ]
        if let value { body["value"] = value.jsonValue }
        return try await post(path: "/api/challenge/action", body: body)
    }

    func interactionAct(gameId: String, playerId: String, action: String, value: ChallengeValue?) async throws -> ActionResponse {
        var body: [String: Any] = [
            "gameId": gameId, "playerId": playerId, "action": action
        ]
        if let value { body["value"] = value.jsonValue }
        return try await post(path: "/api/interaction/act", body: body)
    }

    // MARK: - Hall of Fame & Access

    func winners() async throws -> [WinnerSummary] {
        try await get(path: "/api/winners")
    }

    func winnerRecords() async throws -> [WinnerRecord] {
        try await get(path: "/api/winners/records")
    }

    func addWinner(name: String, date: String) async throws -> ActionResponse {
        try await post(path: "/api/winners/add", body: [
            "winner_name": name, "date": date,
        ])
    }

    func updateWinner(id: String, name: String, date: String) async throws -> ActionResponse {
        try await post(path: "/api/winners/update", body: [
            "id": id, "winner_name": name, "date": date,
        ])
    }

    func deleteWinner(id: String) async throws -> ActionResponse {
        try await post(path: "/api/winners/delete", body: ["id": id])
    }

    func accessCheck() async throws -> AccessCheckResponse {
        try await get(path: "/api/access/check")
    }

    func submitAccess(code: String) async throws -> ActionResponse {
        try await post(path: "/api/access", body: ["code": code])
    }

    // MARK: - Health

    func ping() async throws -> PingResponse {
        try await get(path: "/api/ping")
    }

    func fetchCards() async throws -> [String: Any] {
        let url = baseURL.appendingPathComponent("/api/cards")
        let (data, _) = try await session.data(from: url)
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw APIError.invalidResponse
        }
        return json
    }
}

// MARK: - Challenge/Interaction values

/// The payload of a challenge or interaction action — exactly the two JSON
/// shapes the server accepts (an Int for pulls/bids/finger counts, a String
/// for steal targets and RPS throws). Typed end to end so no `Any?` bridging
/// ever sits between a tapped button and the wire.
enum ChallengeValue: Sendable, Equatable {
    case int(Int)
    case string(String)

    /// The JSON-safe object for the request body. Only ever unwrapped inside
    /// the APIClient actor, right before serialization.
    var jsonValue: Any {
        switch self {
        case .int(let number): return number
        case .string(let text): return text
        }
    }
}

// MARK: - Response Types

struct CreateGameResponse: Codable {
    let success: Bool
    let gameId: String
}

struct JoinGameResponse: Codable {
    let success: Bool
    let playerId: String
    let gameState: GameState
}

struct RejoinGameResponse: Codable {
    let success: Bool
    let gameState: GameState
    let playerName: String?
}

struct ActionResponse: Decodable {
    let success: Bool
    let message: String?
    /// Fresh authoritative state the server includes on mutating actions, so
    /// the actor sees the result on the HTTP await without waiting on the
    /// socket. Decoded leniently — a missing or malformed state payload must
    /// never fail an otherwise-successful action.
    let gameState: GameState?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        success = try container.decode(Bool.self, forKey: .success)
        message = try container.decodeIfPresent(String.self, forKey: .message)
        gameState = try? container.decode(GameState.self, forKey: .gameState)
    }

    enum CodingKeys: String, CodingKey {
        case success, message, gameState
    }
}

struct PlayCardResponse: Decodable {
    let success: Bool
    let message: String?
    let tribalTriggered: Bool?
    /// The Spy Shack's first call (no takeIndex) answers with the target's
    /// hand so the spy can choose which card to take.
    let spiedHand: [CardInstance]?
    /// Fresh authoritative state — lenient decode, see ActionResponse.
    let gameState: GameState?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        success = try container.decode(Bool.self, forKey: .success)
        message = try container.decodeIfPresent(String.self, forKey: .message)
        tribalTriggered = try container.decodeIfPresent(Bool.self, forKey: .tribalTriggered)
        spiedHand = try container.decodeIfPresent([CardInstance].self, forKey: .spiedHand)
        gameState = try? container.decode(GameState.self, forKey: .gameState)
    }

    enum CodingKeys: String, CodingKey {
        case success, message, gameState
        case tribalTriggered = "tribal_triggered"
        case spiedHand = "spied_hand"
    }
}

struct DrawResponse: Decodable {
    let success: Bool
    let message: String?
    let tribalTriggered: Bool?
    /// Fresh authoritative state — lenient decode, see ActionResponse.
    let gameState: GameState?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        success = try container.decode(Bool.self, forKey: .success)
        message = try container.decodeIfPresent(String.self, forKey: .message)
        tribalTriggered = try container.decodeIfPresent(Bool.self, forKey: .tribalTriggered)
        gameState = try? container.decode(GameState.self, forKey: .gameState)
    }

    enum CodingKeys: String, CodingKey {
        case success, message, gameState
        case tribalTriggered = "tribal_triggered"
    }
}

struct PingResponse: Codable {
    let success: Bool
    let timestamp: Double?
}

/// Aggregated response from GET /api/winners.
struct WinnerSummary: Codable, Equatable, Identifiable {
    let winnerName: String
    let victories: Int
    let dates: [String]

    var id: String { winnerName }

    enum CodingKeys: String, CodingKey {
        case victories, dates
        case winnerName = "winner_name"
    }
}

/// One editable row from GET /api/winners/records.
struct WinnerRecord: Codable, Equatable, Identifiable {
    let id: String
    let winnerName: String
    let date: String
    let gameId: String?

    enum CodingKeys: String, CodingKey {
        case id, date
        case winnerName = "winner_name"
        case gameId = "game_id"
    }
}

struct AccessCheckResponse: Codable {
    let success: Bool
    /// The island is code-locked.
    let gated: Bool
    /// This client already holds a valid access cookie.
    let ok: Bool
}

// MARK: - Errors

enum APIError: LocalizedError {
    case invalidResponse
    case serverError(statusCode: Int, message: String)
    case decodingFailed(Error)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from server"
        case .serverError(_, let message):
            return message
        case .decodingFailed(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        }
    }

    var requiresIslandAccess: Bool {
        if case .serverError(statusCode: 401, _) = self { return true }
        return false
    }
}
