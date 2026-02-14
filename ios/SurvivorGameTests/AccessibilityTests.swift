import Testing
import Foundation
import SwiftUI
@testable import SurvivorGame

struct AccessibilityTests {
    
    // MARK: - Color Hex Parsing
    
    @Test func colorHexParsingValid() {
        let color1 = Color(hex: "#FF6B6B")
        let color2 = Color(hex: "4ECDC4")
        let color3 = Color(hex: "#45B7D1FF")
        
        #expect(color1 != nil, "Should parse 6-digit hex with #")
        #expect(color2 != nil, "Should parse 6-digit hex without #")
        #expect(color3 != nil, "Should parse 8-digit hex with alpha")
    }
    
    @Test func colorHexParsingInvalid() {
        let invalidColor1 = Color(hex: "invalid")
        let invalidColor2 = Color(hex: "GG6B6B")
        let invalidColor3 = Color(hex: "#12345")
        let invalidColor4 = Color(hex: "")
        
        #expect(invalidColor1 == nil, "Should return nil for invalid hex")
        #expect(invalidColor2 == nil, "Should return nil for non-hex characters")
        #expect(invalidColor3 == nil, "Should return nil for invalid length")
        #expect(invalidColor4 == nil, "Should return nil for empty string")
    }
    
    @Test func playerColorFallback() {
        let player = PlayerState.sample(id: "p1", name: "Test", color: "invalid_color")
        
        // With the improved Color extension, invalid colors should fallback to gray
        let color = player.swiftUIColor
        #expect(color == .gray, "Should fallback to gray for invalid color")
    }
    
    // MARK: - Accessibility Labels
    
    @Test func cardDisplayName() {
        let card1 = CardInstance(
            type: "vote",
            category: "vote",
            name: "Vote",
            description: "Basic vote",
            playablePhases: nil,
            requiresTarget: nil,
            requiresMultipleTargets: nil,
            requiresConfirmation: nil,
            reactiveOnly: nil
        )
        
        #expect(card1.displayName == "Vote")
        
        let card2 = CardInstance(
            type: "immunity_idol",
            category: nil,
            name: nil,
            description: nil,
            playablePhases: nil,
            requiresTarget: nil,
            requiresMultipleTargets: nil,
            requiresConfirmation: nil,
            reactiveOnly: nil
        )
        
        // Should capitalize and replace underscores
        #expect(card2.displayName == "Immunity Idol")
    }
    
    @Test func cardCategoryDisplayNames() {
        #expect(CardCategory.vote.displayName == "Vote")
        #expect(CardCategory.tribalAdvantage.displayName == "Tribal Advantage")
        #expect(CardCategory.action.displayName == "Action")
        #expect(CardCategory.tribalCouncil.displayName == "Tribal Council")
    }
    
    // MARK: - Player Status
    
    @Test func playerAccessibilityStatus() {
        let activePlayer = PlayerState.sample(id: "p1", name: "Alice", isEliminated: false)
        #expect(activePlayer.isAlive == true)
        #expect(activePlayer.isEliminated == false)
        
        let eliminatedPlayer = PlayerState.sample(id: "p2", name: "Bob", isEliminated: true)
        #expect(eliminatedPlayer.isAlive == false)
        #expect(eliminatedPlayer.isEliminated == true)
    }
    
    @Test func playerHandCount() {
        let emptyHand = PlayerState.sample(id: "p1", name: "Test", hand: [])
        #expect(emptyHand.handCount == 0)
        
        let card = CardInstance(type: "vote", category: nil, name: nil, description: nil, playablePhases: nil, requiresTarget: nil, requiresMultipleTargets: nil, requiresConfirmation: nil, reactiveOnly: nil)
        let withCards = PlayerState.sample(id: "p2", name: "Test", hand: [card, card, card])
        #expect(withCards.handCount == 3)
    }
    
    // MARK: - Error Accessibility
    
    @Test func viewModelErrorHasAccessibleInfo() {
        let error = ViewModelError.networkError("Connection failed")
        
        #expect(error.title == "Connection Error")
        #expect(error.message == "Connection failed")
        #expect(error.isRetryable == true)
        
        // Error has unique ID for accessibility identification
        #expect(error.id != UUID())
    }
    
    @Test func gameErrorIsNotRetryable() {
        let error = ViewModelError.gameError("Invalid move")
        
        #expect(error.title == "Game Error")
        #expect(error.isRetryable == false)
    }
}
