#!/usr/bin/env python3

"""
Test script to validate improved error handling in GameState methods
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState

def test_add_player_errors():
    """Test add_player error handling improvements"""
    gs = GameState()
    
    print("=== Testing add_player error handling ===")
    
    # Test: Game not found
    result = gs.add_player("nonexistent", "TestPlayer", "red")
    print(f"Game not found: {result}")
    assert result["success"] == False
    assert "Game not found" in result["message"]
    
    # Create a game for further testing
    game_id = gs.create_game()
    print(f"Created game: {game_id}")
    
    # Test: Empty name
    result = gs.add_player(game_id, "", "red")
    print(f"Empty name: {result}")
    assert result["success"] == False
    assert "Player name is required" in result["message"]
    
    # Test: Whitespace-only name
    result = gs.add_player(game_id, "   ", "blue")
    print(f"Whitespace name: {result}")
    assert result["success"] == False
    assert "Player name is required" in result["message"]
    
    # Test: Missing color
    result = gs.add_player(game_id, "TestPlayer", "")
    print(f"Empty color: {result}")
    assert result["success"] == False
    assert "Player color is required" in result["message"]
    
    # Test: Successful addition
    result = gs.add_player(game_id, "Player1", "red")
    print(f"Successful add: {result}")
    assert result["success"] == True
    assert "Player1" in result["message"]
    
    # Test: Duplicate name
    result = gs.add_player(game_id, "Player1", "blue")
    print(f"Duplicate name: {result}")
    assert result["success"] == False
    assert "already exists" in result["message"]
    
    # Test: Duplicate color
    result = gs.add_player(game_id, "Player2", "red")
    print(f"Duplicate color: {result}")
    assert result["success"] == False
    assert "already taken" in result["message"]
    
    # Add 5 more players to test game full
    for i in range(2, 7):
        result = gs.add_player(game_id, f"Player{i}", f"color{i}")
        print(f"Add Player{i}: {result['success']}")
    
    # Test: Game full (7th player)
    result = gs.add_player(game_id, "Player7", "color7")
    print(f"Game full: {result}")
    assert result["success"] == False
    assert "maximum 6 players" in result["message"]
    
    print("✅ add_player error handling tests passed!\n")


def test_steal_card_errors():
    """Test steal_card error handling improvements"""
    gs = GameState()
    
    print("=== Testing steal_card error handling ===")
    
    # Test: Game not found
    result = gs.steal_card("nonexistent", "player1", "player2")
    print(f"Game not found: {result}")
    assert result["success"] == False
    assert "Game not found" in result["message"]
    
    # Create game and add players
    game_id = gs.create_game()
    player1_result = gs.add_player(game_id, "Player1", "red")
    player2_result = gs.add_player(game_id, "Player2", "blue")
    player1_id = player1_result["playerId"]
    player2_id = player2_result["playerId"]
    
    # Test: Wrong phase (not started)
    result = gs.steal_card(game_id, player1_id, player2_id)
    print(f"Wrong phase: {result}")
    assert result["success"] == False
    assert "not in playing phase" in result["message"]
    
    # Start game
    gs.start_full_game(game_id)
    
    # Test: Steal from self
    result = gs.steal_card(game_id, player1_id, player1_id)
    print(f"Steal from self: {result}")
    assert result["success"] == False
    assert "cannot steal from yourself" in result["message"]
    
    # Test: Nonexistent thief
    result = gs.steal_card(game_id, "fake_player", player2_id)
    print(f"Nonexistent thief: {result}")
    assert result["success"] == False
    assert "Thief player not found" in result["message"]
    
    # Test: Nonexistent target
    result = gs.steal_card(game_id, player1_id, "fake_player")
    print(f"Nonexistent target: {result}")
    assert result["success"] == False
    assert "Target player not found" in result["message"]
    
    print("✅ steal_card error handling tests passed!\n")


def test_cast_vote_errors():
    """Test cast_vote error handling improvements"""
    gs = GameState()
    
    print("=== Testing cast_vote error handling ===")
    
    # Test: Game not found
    result = gs.cast_vote("nonexistent", "player1", [{"targetId": "player2", "votes": 1}])
    print(f"Game not found: {result}")
    assert result["success"] == False
    assert "Game not found" in result["message"]
    
    # Create game and add players
    game_id = gs.create_game()
    player1_result = gs.add_player(game_id, "Player1", "red")
    player2_result = gs.add_player(game_id, "Player2", "blue")
    player1_id = player1_result["playerId"]
    player2_id = player2_result["playerId"]
    
    # Test: Not in voting phase
    result = gs.cast_vote(game_id, player1_id, [{"targetId": player2_id, "votes": 1}])
    print(f"Not in voting phase: {result}")
    assert result["success"] == False
    assert "Tribal council voting has not started" in result["message"]
    
    # Test: Vote for self
    gs.games[game_id]["currentVote"]["phase"] = "voting"  # Force voting phase
    result = gs.cast_vote(game_id, player1_id, [{"targetId": player1_id, "votes": 1}])
    print(f"Vote for self: {result}")
    assert result["success"] == False
    assert "Cannot vote for yourself" in result["message"]
    
    # Test: Invalid vote data
    result = gs.cast_vote(game_id, player1_id, None)
    print(f"Invalid vote data: {result}")
    assert result["success"] == False
    assert "Invalid vote data" in result["message"]
    
    print("✅ cast_vote error handling tests passed!\n")


def test_advance_tribal_phase_errors():
    """Test advance_tribal_phase error handling improvements"""
    gs = GameState()
    
    print("=== Testing advance_tribal_phase error handling ===")
    
    # Test: Game not found
    result = gs.advance_tribal_phase("nonexistent", "discussion")
    print(f"Game not found: {result}")
    assert result["success"] == False
    assert "Game not found" in result["message"]
    
    # Create game
    game_id = gs.create_game()
    
    # Test: Wrong game phase
    result = gs.advance_tribal_phase(game_id, "discussion")
    print(f"Wrong game phase: {result}")
    assert result["success"] == False
    assert "not tribal council" in result["message"]
    
    # Set game to tribal council
    gs.games[game_id]["phase"] = "tribal_council"
    gs.games[game_id]["currentVote"]["phase"] = "announcement"
    
    # Test: Invalid phase
    result = gs.advance_tribal_phase(game_id, "invalid_phase")
    print(f"Invalid phase: {result}")
    assert result["success"] == False
    assert "Invalid tribal council phase" in result["message"]
    
    # Test: Skip phases
    result = gs.advance_tribal_phase(game_id, "voting")  # Skip advantage_play and discussion
    print(f"Skip phases: {result}")
    assert result["success"] == False
    assert "Cannot skip phases" in result["message"]
    
    # Test: Go backwards
    gs.games[game_id]["currentVote"]["phase"] = "voting"
    result = gs.advance_tribal_phase(game_id, "discussion")
    print(f"Go backwards: {result}")
    assert result["success"] == False
    assert "Cannot go backwards" in result["message"]
    
    # Test: Valid progression
    gs.games[game_id]["currentVote"]["phase"] = "announcement"
    result = gs.advance_tribal_phase(game_id, "advantage_play")
    print(f"Valid progression: {result}")
    assert result["success"] == True
    assert "advanced to 'advantage_play'" in result["message"]
    
    print("✅ advance_tribal_phase error handling tests passed!\n")


if __name__ == "__main__":
    print("🧪 Testing GameState Error Handling Improvements")
    print("=" * 50)
    
    try:
        test_add_player_errors()
        test_steal_card_errors()
        test_cast_vote_errors()
        test_advance_tribal_phase_errors()
        
        print("🎉 All error handling tests passed!")
        print("✅ Specific, user-friendly error messages are now working correctly")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)