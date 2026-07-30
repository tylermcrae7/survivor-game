#!/usr/bin/env python3

"""
Test script to validate error handling in GameState methods.

Every message asserted here is surfaced verbatim to players as a toast, so these
tests pin the wording, not just the failure.
"""

import os
import sys
import shutil
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState


def fresh_state():
    """A GameState rooted in a throwaway directory so games.json isn't touched."""
    tmp = tempfile.mkdtemp()
    original = os.getcwd()
    os.chdir(tmp)
    return GameState(), original, tmp


def test_add_player_errors():
    """Test player-join validation messages"""
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing player join validation ===")

        # Test: Game not found
        result = gs.validate_new_player("nonexistent", "TestPlayer", "red")
        print(f"Game not found: {result}")
        assert result["success"] is False
        assert "Game not found" in result["message"]
        # add_player itself returns None for an unknown game
        assert gs.add_player("nonexistent", "TestPlayer", "red") is None

        game_id = gs.create_game()
        print(f"Created game: {game_id}")

        # Test: Empty name
        result = gs.validate_new_player(game_id, "", "red")
        print(f"Empty name: {result}")
        assert result["success"] is False
        assert "Player name is required" in result["message"]

        # Test: Whitespace-only name
        result = gs.validate_new_player(game_id, "   ", "blue")
        print(f"Whitespace name: {result}")
        assert result["success"] is False
        assert "Player name is required" in result["message"]

        # Test: Illegal characters
        result = gs.validate_new_player(game_id, "<script>", "blue")
        print(f"Illegal characters: {result}")
        assert result["success"] is False
        assert "can only contain" in result["message"]

        # Test: Successful addition
        result = gs.validate_new_player(game_id, "Player1", "red")
        print(f"Valid join: {result}")
        assert result["success"] is True
        player1_id = gs.add_player(game_id, "Player1", "red")
        assert player1_id, "add_player should return the new player id"

        # Test: Duplicate name (case-insensitive)
        result = gs.validate_new_player(game_id, "player1", "blue")
        print(f"Duplicate name: {result}")
        assert result["success"] is False
        assert "already exists" in result["message"]

        # Test: Duplicate color
        result = gs.validate_new_player(game_id, "Player2", "red")
        print(f"Duplicate color: {result}")
        assert result["success"] is False
        assert "already taken" in result["message"]

        # Fill the game up to the 6-player maximum
        for i in range(2, 7):
            assert gs.validate_new_player(game_id, f"Player{i}", f"color{i}")["success"] is True
            gs.add_player(game_id, f"Player{i}", f"color{i}")

        # Test: Game full (7th player)
        result = gs.validate_new_player(game_id, "Player7", "color7")
        print(f"Game full: {result}")
        assert result["success"] is False
        assert "maximum 6 players" in result["message"]

        print("✅ player join validation tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_steal_card_errors():
    """Test steal_card error handling improvements"""
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing steal_card error handling ===")

        # Test: Game not found
        result = gs.steal_card("nonexistent", "player1", "player2")
        print(f"Game not found: {result}")
        assert result["success"] is False
        assert "Game not found" in result["message"]

        game_id = gs.create_game()
        player1_id = gs.add_player(game_id, "Player1", "red")
        player2_id = gs.add_player(game_id, "Player2", "blue")

        # Test: Wrong phase (not started)
        result = gs.steal_card(game_id, player1_id, player2_id)
        print(f"Wrong phase: {result}")
        assert result["success"] is False
        assert "not in playing phase" in result["message"]

        # A 3rd player is required to start
        gs.add_player(game_id, "Player3", "green")
        assert gs.start_full_game(game_id)["success"] is True

        game = gs.games[game_id]
        current_player = game["turnOrder"][game["currentTurnIndex"]]
        other_player = next(p for p in game["turnOrder"] if p != current_player)

        # Test: Steal from self
        result = gs.steal_card(game_id, current_player, current_player)
        print(f"Steal from self: {result}")
        assert result["success"] is False
        assert "cannot steal from yourself" in result["message"]

        # Test: Nonexistent thief
        result = gs.steal_card(game_id, "fake_player", other_player)
        print(f"Nonexistent thief: {result}")
        assert result["success"] is False
        assert "Thief player not found" in result["message"]

        # Test: Nonexistent target
        result = gs.steal_card(game_id, current_player, "fake_player")
        print(f"Nonexistent target: {result}")
        assert result["success"] is False
        assert "Target player not found" in result["message"]

        # Test: Not your turn
        result = gs.steal_card(game_id, other_player, current_player)
        print(f"Not your turn: {result}")
        assert result["success"] is False
        assert "not your turn" in result["message"]

        print("✅ steal_card error handling tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_cast_vote_errors():
    """Test cast_vote error handling improvements"""
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing cast_vote error handling ===")

        # Test: Game not found
        result = gs.cast_vote("nonexistent", "player1", [{"targetId": "player2", "votes": 1}])
        print(f"Game not found: {result}")
        assert result["success"] is False
        assert "Game not found" in result["message"]

        game_id = gs.create_game()
        player1_id = gs.add_player(game_id, "Player1", "red")
        player2_id = gs.add_player(game_id, "Player2", "blue")
        gs.add_player(game_id, "Player3", "green")
        gs.start_full_game(game_id)

        # Deterministic hands: setup deals random action cards, and a random
        # Goodwill Gamble would change how many votes a player must cast.
        for player in gs.games[game_id]["players"].values():
            player["hand"] = [{"type": "camp_raid"}, {"type": "vote"}]
        gs.rules_engine.sync_vote_counters(gs.games[game_id])

        # Test: Not in voting phase
        result = gs.cast_vote(game_id, player1_id, [{"targetId": player2_id, "votes": 1}])
        print(f"Not in voting phase: {result}")
        assert result["success"] is False
        assert "Tribal council voting has not started" in result["message"]

        # Force a tribal council into the voting phase
        game = gs.games[game_id]
        gs._trigger_tribal_council(game, "single", drawer_id=player1_id)
        game["currentVote"]["phase"] = "voting"

        # Test: Vote for self
        result = gs.cast_vote(game_id, player1_id, [{"targetId": player1_id, "votes": 1}])
        print(f"Vote for self: {result}")
        assert result["success"] is False
        assert "Cannot vote for yourself" in result["message"]

        # Test: Invalid vote data
        result = gs.cast_vote(game_id, player1_id, None)
        print(f"Invalid vote data: {result}")
        assert result["success"] is False
        assert "Invalid vote data" in result["message"]

        # Test: More votes than the player holds cards for
        result = gs.cast_vote(game_id, player1_id, [{"targetId": player2_id, "votes": 4}])
        print(f"Too many votes: {result}")
        assert result["success"] is False
        assert "only 1 available" in result["message"]

        # Test: Valid vote, then no double voting
        result = gs.cast_vote(game_id, player1_id, [{"targetId": player2_id, "votes": 1}])
        print(f"Valid vote: {result}")
        assert result["success"] is True

        result = gs.cast_vote(game_id, player1_id, [{"targetId": player2_id, "votes": 1}])
        print(f"Second vote: {result}")
        assert result["success"] is False
        assert "already voted" in result["message"]

        print("✅ cast_vote error handling tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_advance_tribal_phase_errors():
    """
    Test tribal phase transition validation.

    GameState.advance_tribal_phase returns a bool; the rules engine returns the
    (success, message) pair that the wording assertions below check.
    """
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing advance_tribal_phase error handling ===")

        # Test: Game not found
        assert gs.advance_tribal_phase("nonexistent", "discussion") is False
        print("Game not found: rejected")

        game_id = gs.create_game()
        game = gs.games[game_id]

        # Test: Wrong game phase
        assert gs.advance_tribal_phase(game_id, "discussion") is False
        ok, message = gs.rules_engine.advance_tribal_phase(game, "discussion")
        print(f"Wrong game phase: {message}")
        assert ok is False
        assert "not tribal council" in message

        # Set game to tribal council
        game["phase"] = "tribal_council"
        game["currentVote"]["phase"] = "announcement"

        # Test: Invalid phase name
        assert gs.advance_tribal_phase(game_id, "invalid_phase") is False
        ok, message = gs.rules_engine.advance_tribal_phase(game, "invalid_phase")
        print(f"Invalid phase: {message}")
        assert ok is False
        assert "Invalid tribal phase" in message

        # Test: Skip phases (announcement -> voting is not a legal transition)
        assert gs.advance_tribal_phase(game_id, "voting") is False
        ok, message = gs.rules_engine.advance_tribal_phase(game, "voting")
        print(f"Skip phases: {message}")
        assert ok is False
        assert "Cannot advance from announcement to voting" in message
        assert game["currentVote"]["phase"] == "announcement"

        # Test: Go backwards
        game["currentVote"]["phase"] = "voting"
        assert gs.advance_tribal_phase(game_id, "discussion") is False
        ok, message = gs.rules_engine.advance_tribal_phase(game, "discussion")
        print(f"Go backwards: {message}")
        assert ok is False
        assert "Cannot advance from voting to discussion" in message

        # Test: Valid progression
        game["currentVote"]["phase"] = "announcement"
        assert gs.advance_tribal_phase(game_id, "advantage_play") is True
        assert game["currentVote"]["phase"] == "advantage_play"
        print("Valid progression: advanced to 'advantage_play'")

        print("✅ advance_tribal_phase error handling tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("🧪 Testing GameState Error Handling")
    print("=" * 50)

    try:
        test_add_player_errors()
        test_steal_card_errors()
        test_cast_vote_errors()
        test_advance_tribal_phase_errors()

        print("🎉 All error handling tests passed!")
        print("✅ Specific, user-friendly error messages are working correctly")

    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
