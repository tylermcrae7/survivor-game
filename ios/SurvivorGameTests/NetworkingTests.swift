import Testing
import Foundation
@testable import SurvivorGame

struct NetworkingTests {
    
    // MARK: - Connection State
    
    @Test func connectionStateTransitions() {
        let disconnected = ConnectionState.disconnected
        let connecting = ConnectionState.connecting
        let connected = ConnectionState.connected
        
        #expect(disconnected != connecting)
        #expect(connecting != connected)
    }
    
    @Test func failedStateContainsMessage() {
        let failed = ConnectionState.failed("Network timeout")
        
        if case .failed(let message) = failed {
            #expect(message == "Network timeout")
        } else {
            Issue.record("Expected failed state with message")
        }
    }
    
    // MARK: - Navigation State
    
    @Test func navigationStatesCoverAllPhases() {
        let states: [NavigationState] = [
            .start,
            .lobby,
            .playing,
            .tribal,
            .finalTribal,
            .finished
        ]
        
        #expect(states.count == 6)
        
        // All states should be unique
        let uniqueStates = Set(states.map { "\($0)" })
        #expect(uniqueStates.count == 6)
    }
    
    // MARK: - API Error Handling
    
    @Test func apiErrorHasLocalizedDescription() {
        let error = APIError.serverError("Internal server error")
        #expect(error.localizedDescription.contains("server"))
    }
    
    @Test func gameClientErrorHasLocalizedDescription() {
        let error = GameClientError.noGame
        #expect(error.localizedDescription == "No active game session")
        
        let opError = GameClientError.operationFailed("Invalid move")
        #expect(opError.localizedDescription == "Invalid move")
    }
    
    // MARK: - URL Construction
    
    @Test func baseURLIsValid() {
        let validURLs = [
            "http://localhost:3000",
            "https://survivor-game.com",
            "http://192.168.1.100:3000"
        ]
        
        for urlString in validURLs {
            let url = URL(string: urlString)
            #expect(url != nil, "URL should be valid: \(urlString)")
        }
    }
    
    // MARK: - Game Event Types
    
    @Test func gameEventTypes() {
        let resetEvent = GameEvent.reset
        let errorEvent = GameEvent.error("Something went wrong")
        let customEvent = GameEvent.custom(type: "player_joined", data: ["playerId": "p1"])
        
        if case .reset = resetEvent {
            // Success
        } else {
            Issue.record("Expected reset event")
        }
        
        if case .error(let message) = errorEvent {
            #expect(message == "Something went wrong")
        } else {
            Issue.record("Expected error event")
        }
        
        if case .custom(let type, let data) = customEvent {
            #expect(type == "player_joined")
            #expect(data["playerId"] as? String == "p1")
        } else {
            Issue.record("Expected custom event")
        }
    }
}

// MARK: - Mock API Error

enum APIError: LocalizedError {
    case serverError(String)
    case networkError
    case invalidResponse
    
    var errorDescription: String? {
        switch self {
        case .serverError(let message):
            return "Server error: \(message)"
        case .networkError:
            return "Network connection failed"
        case .invalidResponse:
            return "Invalid server response"
        }
    }
}
