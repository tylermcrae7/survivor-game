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
    var deckMode: String?
    var expansion: Bool?
    var necklaceHolder: String?
    var eventLog: [EventLogEntry]?
    var discard: [CardInstance]?
    var settings: GameSettings?
    var challenge: ChallengeState?
    var interaction: InteractionState?
    var pendingTheft: PendingTheftState?
    /// Which places are open and whether the ceremony has forced everyone into
    /// one. Absent on servers that predate places — the Places UI hides itself.
    var placePolicy: PlacePolicy?

    enum CodingKeys: String, CodingKey {
        case id, phase, players, turnOrder, currentTurnIndex, deck, gameHistory
        case currentVote, jury, finalTribal, winner, createdAt, lastActivity
        case deckMode, expansion, necklaceHolder, eventLog, discard, settings
        case challenge, interaction, placePolicy
        case pendingTheft = "pending_theft"
    }

    /// Core keys decode strictly (they are always present); everything else is
    /// defensive — the presence of a shape this build has never seen must
    /// never brick the whole state.
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        phase = try c.decode(GamePhase.self, forKey: .phase)
        players = try c.decode([String: PlayerState].self, forKey: .players)
        turnOrder = try c.decodeIfPresent([String].self, forKey: .turnOrder) ?? []
        currentTurnIndex = try c.decodeIfPresent(Int.self, forKey: .currentTurnIndex) ?? 0
        deck = try? c.decodeIfPresent([CardInstance].self, forKey: .deck)
        gameHistory = try? c.decodeIfPresent([GameHistoryEntry].self, forKey: .gameHistory)
        currentVote = try? c.decodeIfPresent(TribalVoteState.self, forKey: .currentVote)
        jury = try? c.decodeIfPresent([String].self, forKey: .jury)
        finalTribal = try? c.decodeIfPresent(FinalTribalState.self, forKey: .finalTribal)
        winner = try? c.decodeIfPresent(String.self, forKey: .winner)
        createdAt = try? c.decodeIfPresent(Double.self, forKey: .createdAt)
        lastActivity = try? c.decodeIfPresent(Double.self, forKey: .lastActivity)
        deckMode = try? c.decodeIfPresent(String.self, forKey: .deckMode)
        expansion = try? c.decodeIfPresent(Bool.self, forKey: .expansion)
        necklaceHolder = try? c.decodeIfPresent(String.self, forKey: .necklaceHolder)
        eventLog = try? c.decodeIfPresent([EventLogEntry].self, forKey: .eventLog)
        discard = try? c.decodeIfPresent([CardInstance].self, forKey: .discard)
        settings = try? c.decodeIfPresent(GameSettings.self, forKey: .settings)
        challenge = try? c.decodeIfPresent(ChallengeState.self, forKey: .challenge)
        interaction = try? c.decodeIfPresent(InteractionState.self, forKey: .interaction)
        pendingTheft = try? c.decodeIfPresent(PendingTheftState.self, forKey: .pendingTheft)
        placePolicy = try? c.decodeIfPresent(PlacePolicy.self, forKey: .placePolicy)
    }

    /// Designated memberwise init for tests and previews.
    init(
        id: String, phase: GamePhase, players: [String: PlayerState],
        turnOrder: [String], currentTurnIndex: Int,
        deck: [CardInstance]? = nil, gameHistory: [GameHistoryEntry]? = nil,
        currentVote: TribalVoteState? = nil, jury: [String]? = nil,
        finalTribal: FinalTribalState? = nil, winner: String? = nil,
        createdAt: Double? = nil, lastActivity: Double? = nil,
        deckMode: String? = nil, expansion: Bool? = nil,
        necklaceHolder: String? = nil, eventLog: [EventLogEntry]? = nil,
        discard: [CardInstance]? = nil, settings: GameSettings? = nil,
        challenge: ChallengeState? = nil, interaction: InteractionState? = nil,
        pendingTheft: PendingTheftState? = nil, placePolicy: PlacePolicy? = nil
    ) {
        self.id = id
        self.phase = phase
        self.players = players
        self.turnOrder = turnOrder
        self.currentTurnIndex = currentTurnIndex
        self.deck = deck
        self.gameHistory = gameHistory
        self.currentVote = currentVote
        self.jury = jury
        self.finalTribal = finalTribal
        self.winner = winner
        self.createdAt = createdAt
        self.lastActivity = lastActivity
        self.deckMode = deckMode
        self.expansion = expansion
        self.necklaceHolder = necklaceHolder
        self.eventLog = eventLog
        self.discard = discard
        self.settings = settings
        self.challenge = challenge
        self.interaction = interaction
        self.pendingTheft = pendingTheft
        self.placePolicy = placePolicy
    }

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
        return player.turnPhase
    }

    var sortedPlayers: [PlayerState] {
        turnOrder.compactMap { players[$0] }
    }

    /// Who is standing in `placeKey`, in turn order. Snuffed players have left
    /// the island — their last place is not something anyone should still see.
    func players(at placeKey: String) -> [PlayerState] {
        sortedPlayers.filter { $0.isAlive && $0.placeKey == placeKey }
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

// MARK: - Lightweight companion shapes (all lenient by construction)

/// One line of "The Story So Far" — the server's shared, already-redacted log.
struct EventLogEntry: Codable, Equatable, Identifiable {
    let t: Double?
    let msg: String?

    var id: String { "\(t ?? 0)-\(msg ?? "")" }
    var date: Date? { t.map { Date(timeIntervalSince1970: $0) } }
}

/// Per-game settings the Leader controls (botPace / tribalPace / botStyle).
struct GameSettings: Codable, Equatable {
    var botPace: String?
    var tribalPace: String?
    var botStyle: String?
}

/// The paused Sorry-For-You window: a steal is hanging until the target answers.
struct PendingTheftState: Codable, Equatable {
    var thiefId: String?
    var thiefIds: [String]?
    var targetId: String?
    var source: String?
    var reactiveWindowOpen: Bool

    enum CodingKeys: String, CodingKey {
        case thiefId, thiefIds, targetId, source
        case reactiveWindowOpen = "reactive_window_open"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        thiefId = try? c.decodeIfPresent(String.self, forKey: .thiefId)
        thiefIds = try? c.decodeIfPresent([String].self, forKey: .thiefIds)
        targetId = try? c.decodeIfPresent(String.self, forKey: .targetId)
        source = try? c.decodeIfPresent(String.self, forKey: .source)
        reactiveWindowOpen = (try? c.decodeIfPresent(Bool.self, forKey: .reactiveWindowOpen)) ?? false
    }

    var allThiefIds: [String] {
        if let ids = thiefIds, !ids.isEmpty { return ids }
        return thiefId.map { [$0] } ?? []
    }
}
