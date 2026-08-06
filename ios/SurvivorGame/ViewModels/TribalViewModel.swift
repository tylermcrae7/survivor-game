import Foundation

@MainActor
@Observable
final class TribalViewModel {
    var error: ViewModelError?
    var isPerformingAction = false
    var isMovingPlace = false
    var selectedVoteTarget: String?
    var selectedAdvantageTarget: String?

    private let gameClient: GameClient

    init(gameClient: GameClient) {
        self.gameClient = gameClient
    }

    // MARK: - Computed

    var gameState: GameState? { gameClient.gameState }
    var voteState: TribalVoteState? { gameState?.currentVote }
    var tribalPhase: TribalPhase { voteState?.phase ?? .waiting }
    var myPlayerId: String? { gameClient.playerId }
    var isCouncilLeader: Bool { gameClient.isCouncilLeader }
    var isEliminated: Bool { gameClient.isEliminated }

    var councilLeader: PlayerState? { gameState?.councilLeader }

    var activePlayers: [PlayerState] { gameState?.activePlayers ?? [] }

    var sortedPlayers: [PlayerState] { gameState?.sortedPlayers ?? [] }

    /// The ceremony pins everyone to one place — except during discussion,
    /// when camp reopens and the tribe breaks up to scheme. So this row is
    /// locked for most of the council and live for one sub-phase of it.
    ///
    /// Mine, not the table's: a snuffed player stays at the fire while the
    /// living scatter. Falls back to the game-wide policy on an older server.
    var placePolicy: PlacePolicy? {
        gameClient.myPlayer?.placePolicy ?? gameState?.placePolicy
    }

    var myPlace: String? { gameClient.myPlayer?.placeKey }

    /// Walking off during the council's discussion. The same door the camp
    /// screen uses; the server refuses it in every other sub-phase.
    func moveToPlace(_ place: String) async {
        guard placePolicy?.canMove(to: place, from: myPlace) == true else { return }
        isMovingPlace = true
        defer { isMovingPlace = false }
        do {
            try await gameClient.moveToPlace(place)
            HapticEngine.selection()
        } catch {
            self.error = .from(error)
        }
    }

    var voteTargets: [PlayerState] {
        guard let myId = myPlayerId else { return activePlayers }
        return activePlayers.filter { $0.id != myId }
    }

    var hasVoted: Bool { gameClient.myPlayer?.hasVoted ?? false }

    /// A Steal A Vote / Block A Vote landed on me. The table stays dark about
    /// who did it (S2's `secret` effects never touch the eventLog or the
    /// narrator) — this only tells the one phone it actually happened to.
    var isVoteBanned: Bool { gameClient.myPlayer?.voteBanned ?? false }

    var eliminatedInTribal: [PlayerState] {
        guard let eliminated = voteState?.eliminated else { return [] }
        return eliminated.compactMap { gameState?.players[$0] }
    }

    var tiedPlayers: [PlayerState] {
        guard let tied = voteState?.tiedPlayers else { return [] }
        return tied.compactMap { gameState?.players[$0] }
    }

    /// Every counted ballot, plus a row for anyone immunity protected — their
    /// idol zeroes `voteResults` but the raw pre-immunity tally in
    /// `rawVoteResults` remembers what they would have received. Sorted the
    /// same way regardless, so an older server missing `rawVoteResults`
    /// (nothing to add) renders exactly as it always did.
    var voteResults: [(player: PlayerState, votes: Int, isImmune: Bool)] {
        let counted = voteState?.voteResults ?? [:]
        var rows = counted.compactMap { (id, count) -> (player: PlayerState, votes: Int, isImmune: Bool)? in
            guard let player = gameState?.players[id] else { return nil }
            return (player, count, false)
        }
        let raw = voteState?.rawVoteResults ?? [:]
        for playerId in protectedPlayers where counted[playerId] == nil {
            guard let votes = raw[playerId], votes > 0,
                  let player = gameState?.players[playerId] else { continue }
            rows.append((player, votes, true))
        }
        return rows.sorted { $0.votes > $1.votes }
    }

    var protectedPlayers: [String] { voteState?.protectedPlayers ?? [] }

    /// Tribal-playable cards, enriched through the card catalog first — server
    /// hands are bare `{"type": …}` stubs with no category/phases of their own,
    /// so filtering the raw hand matched nothing and every advantage window
    /// read as empty. Same resolve step the playing-hand grid uses.
    var myTribalCards: [CardInstance] {
        (gameClient.myPlayer?.hand ?? [])
            .map { CardCatalog.shared.resolve($0) }
            .filter { $0.category == "tribal_advantage" || $0.category == "vote" }
    }

    var hasImmunityIdol: Bool {
        gameClient.myPlayer?.hand.contains { $0.type == "immunity_idol" } ?? false
    }

    var hasIdolNullifier: Bool {
        gameClient.myPlayer?.hand.contains { $0.type == "idol_nullifier" } ?? false
    }

    // MARK: - Actions

    func advancePhase(to phase: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.advanceTribal(to: phase)
        } catch {
            self.error = .from(error)
        }
    }

    func startVoting(type: String = "elimination") async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.startVoting(type: type)
        } catch {
            self.error = .from(error)
        }
    }

    func castVote(targetId: String, count: Int = 1) async {
        isPerformingAction = true
        // Safe to defer-clear: GameClient.castVote applies the response's
        // fresh state (hasVoted flipped) before it returns, so the ballot UI
        // re-enables against fresh flags and a double-tap can't vote twice.
        defer { isPerformingAction = false }
        do {
            try await gameClient.castVote(targetId: targetId, count: count)
        } catch {
            self.error = .from(error)
        }
    }

    func castSplitBallot(_ allocations: [String: Int]) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.castSplitBallot(allocations)
        } catch {
            self.error = .from(error)
        }
    }

    func passVotingBox() async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.passVotingBox()
        } catch {
            self.error = .from(error)
        }
    }

    func castVotes(votesData: [[String: Any]]) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            // Safe to pass dictionary - immediately serialized to JSON in network layer
            nonisolated(unsafe) let votes = votesData
            try await gameClient.castVotes(votesData: votes)
        } catch {
            self.error = .from(error)
        }
    }

    func revealVotes() async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.revealVotes()
        } catch {
            self.error = .from(error)
        }
    }

    func resolveTieBreak(chosenId: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.resolveTieBreak(chosenId: chosenId)
        } catch {
            self.error = .from(error)
        }
    }

    func completeTribal() async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.completeTribal()
        } catch {
            self.error = .from(error)
        }
    }

    func playAdvantage(type: String, targetId: String? = nil) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.playAdvantage(type: type, targetId: targetId)
        } catch {
            self.error = .from(error)
        }
    }

    func playImmunity(targetId: String? = nil) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.playImmunity(targetId: targetId)
        } catch {
            self.error = .from(error)
        }
    }

    func blockImmunity(targetId: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.blockImmunity(targetId: targetId)
        } catch {
            self.error = .from(error)
        }
    }

    func changeLeader(to playerId: String) async {
        isPerformingAction = true
        defer { isPerformingAction = false }
        do {
            try await gameClient.changeLeader(newLeaderId: playerId)
        } catch {
            self.error = .from(error)
        }
    }
}
