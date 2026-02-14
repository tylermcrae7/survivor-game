import Foundation

struct GameState: Codable, Equatable {
    let id: String
    var phase: GamePhase
    var players: [String: PlayerState]
    var turnOrder: [String]
    var currentTurnIndex: Int
    var deck: [CardInstance]?
    var gameHistory: [GameHistoryEntry]?
    var currentVote: TribalVoteState?
    var jury: [String]?
    var finalTribal: FinalTribalState?
    var winner: String?
    var createdAt: Double?
    var lastActivity: Double?

    // MARK: - Derived Properties

    var currentPlayerId: String? {
        guard !turnOrder.isEmpty,
              currentTurnIndex >= 0,
              currentTurnIndex < turnOrder.count
        else { return nil }
        return turnOrder[currentTurnIndex]
    }

    var currentPlayer: PlayerState? {
        guard let pid = currentPlayerId else { return nil }
        return players[pid]
    }

    var activePlayers: [PlayerState] {
        turnOrder.compactMap { players[$0] }.filter { $0.isAlive }
    }

    var eliminatedPlayers: [PlayerState] {
        players.values.filter { $0.isEliminated }.sorted { $0.name < $1.name }
    }

    var councilLeader: PlayerState? {
        if let leaderId = currentVote?.councilLeaderId {
            return players[leaderId]
        }
        return players.values.first { $0.isCouncilLeader }
    }

    var playerCount: Int { players.count }
    var aliveCount: Int { activePlayers.count }
    var deckCount: Int { deck?.count ?? 0 }

    func isCurrentTurn(for playerId: String) -> Bool {
        currentPlayerId == playerId
    }

    func turnPhase(for playerId: String) -> TurnPhase? {
        guard isCurrentTurn(for: playerId),
              let player = players[playerId]
        else { return nil }
        return player.hasStolen ? .play : .steal
    }

    var sortedPlayers: [PlayerState] {
        turnOrder.compactMap { players[$0] }
    }
}

struct GameHistoryEntry: Codable, Equatable {
    let action: String?
    let playerId: String?
    let timestamp: Double?
    let message: String?

    // Accept any extra keys without failing
    struct DynamicCodingKey: CodingKey {
        var stringValue: String
        var intValue: Int?
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { self.stringValue = "\(intValue)"; self.intValue = intValue }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        action = try container.decodeIfPresent(String.self, forKey: .action)
        playerId = try container.decodeIfPresent(String.self, forKey: .playerId)
        timestamp = try container.decodeIfPresent(Double.self, forKey: .timestamp)
        message = try container.decodeIfPresent(String.self, forKey: .message)
    }

    enum CodingKeys: String, CodingKey {
        case action, playerId, timestamp, message
    }
}
