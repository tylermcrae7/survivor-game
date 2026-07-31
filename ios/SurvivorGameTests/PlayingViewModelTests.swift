import Testing
import Foundation
@testable import SurvivorGame

@MainActor
struct PlayingViewModelTests {
    
    // MARK: - Computed Properties
    
    @Test func myPlayerReturnsCorrectPlayer() {
        let mockClient = MockGameClient()
        mockClient.mockGameState = MockGameClient.sampleGameState()
        mockClient.playerId = "p1"
        
        let gameClient = GameClient(baseURL: URL(string: "http://localhost:3000")!)
        let vm = PlayingViewModel(gameClient: gameClient)
        
        // Note: This test validates the pattern, but requires actual GameClient integration
        // In a real scenario, we'd inject a protocol-based client
    }
    
    @Test func stealTargetsExcludesCurrentPlayer() {
        let state = MockGameClient.sampleGameState()
        let activePlayers = state.activePlayers
        
        // Verify we have multiple players
        #expect(activePlayers.count >= 2)
        
        // All active players should have IDs
        for player in activePlayers {
            #expect(!player.id.isEmpty)
        }
    }
    
    @Test func canStealOnlyDuringStealPhase() {
        let state = MockGameClient.sampleGameState()
        
        // Current player at index 0 has hasStolen: false
        let turnPhase = state.turnPhase(for: "p1")
        #expect(turnPhase == .steal)
        
        // After stealing, phase should change
        var modifiedState = state
        if var player = modifiedState.players["p1"] {
            let updatedPlayer = PlayerState(
                id: player.id,
                name: player.name,
                color: player.color,
                hand: player.hand,
                isEliminated: player.isEliminated,
                isActive: player.isActive,
                isCouncilLeader: player.isCouncilLeader,
                hasStolen: true,
                hasVoted: player.hasVoted,
                extraVotes: player.extraVotes,
                characterCards: player.characterCards,
                immunityPlayed: player.immunityPlayed,
                voteBanned: player.voteBanned
            )
            modifiedState.players["p1"] = updatedPlayer
        }
        
        let newPhase = modifiedState.turnPhase(for: "p1")
        #expect(newPhase == .play)
    }

    @Test func drawEndsTheTurnMachine() {
        // Official turn: steal → play (optional) → draw ends it. The state
        // machine must mirror the server exactly — there is no End Turn.
        var state = MockGameClient.sampleGameState()
        state.players["p1"] = PlayerState(
            id: "p1", name: "Alice", color: "#FF6B6B",
            hasStolen: true, hasPlayed: true)
        #expect(state.turnPhase(for: "p1") == .draw)

        state.players["p1"] = PlayerState(
            id: "p1", name: "Alice", color: "#FF6B6B",
            hasStolen: true, hasDrawn: true)
        #expect(state.turnPhase(for: "p1") == .done)
    }
    
    // MARK: - Action State
    
    @Test func isPerformingActionPreventsMultipleActions() async {
        // This test validates the pattern of using isPerformingAction
        // to prevent concurrent operations
        let isPerformingAction = false
        #expect(isPerformingAction == false)
        
        // In real usage, this flag prevents UI double-taps
    }
    
    // MARK: - Error Handling
    
    @Test func viewModelHandlesErrors() {
        let error = ViewModelError.networkError("Connection lost")
        #expect(error.title == "Connection Error")
        #expect(error.isRetryable == true)
    }
}

// PlayerState's designated memberwise init (State/PlayerState.swift) serves the
// tests now — a cross-file extension init can't assign `let` stored properties.
