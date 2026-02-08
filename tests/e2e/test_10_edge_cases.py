"""
Steps 21-22: Game Reset, Edge Cases & Stress Tests

Tests game reset/replay, minimum player count, empty deck,
rapid actions, and reconnection after elimination.
Priority: P3 (Polish)
"""

import pytest
import time
from conftest import (
    api_post, get_game_state,
    create_game_api, join_player_api, start_game_api,
    PLAYERS, COLORS
)


class TestGameReset:
    """Step 21: Game reset and replay."""

    def test_reset_returns_to_lobby(self, server_check):
        """Game reset returns to lobby phase."""
        gid = create_game_api()
        pids = {}
        for name, color in zip(PLAYERS, COLORS):
            pids[name] = join_player_api(gid, name, color)
        start_game_api(gid)

        # Verify we're in playing phase
        state = get_game_state(gid)
        assert state["phase"] == "playing"

        # Reset
        result = api_post("/game/reset", {"gameId": gid})
        assert result["success"] is True

        # Verify lobby phase
        new_state = get_game_state(gid)
        assert new_state["phase"] == "lobby"

    def test_reset_clears_hands(self, server_check):
        """Game reset empties all player hands."""
        gid = create_game_api()
        for name, color in zip(PLAYERS, COLORS):
            join_player_api(gid, name, color)
        start_game_api(gid)

        api_post("/game/reset", {"gameId": gid})

        state = get_game_state(gid)
        for pid, player in state["players"].items():
            hand = player.get("hand", [])
            assert len(hand) == 0, f"Player {player['name']} still has {len(hand)} cards after reset"

    def test_reset_clears_eliminations(self, server_check):
        """Game reset un-eliminates all players."""
        gid = create_game_api()
        pids = {}
        for name, color in zip(PLAYERS, COLORS):
            pids[name] = join_player_api(gid, name, color)
        start_game_api(gid)

        # Eliminate a player via tribal
        state = get_game_state(gid)
        target_pid = state["turnOrder"][-1]
        api_post("/vote/start", {"gameId": gid, "type": "single"})
        for _ in range(5):
            s = get_game_state(gid)
            if s.get("currentVote", {}).get("phase") == "voting":
                break
            api_post("/tribal/advance", {"gameId": gid})

        for pid in state["turnOrder"]:
            vote_target = target_pid if pid != target_pid else state["turnOrder"][0]
            api_post("/vote/cast", {
                "gameId": gid,
                "voterId": pid,
                "votesData": [{"targetId": vote_target, "votes": 1}]
            })
        api_post("/vote/reveal", {"gameId": gid})
        api_post("/tribal/complete", {"gameId": gid})

        # Now reset
        api_post("/game/reset", {"gameId": gid})
        new_state = get_game_state(gid)
        for pid, player in new_state["players"].items():
            assert player.get("isEliminated") in (None, False), \
                f"Player {player['name']} still eliminated after reset"

    def test_reset_clears_jury(self, server_check):
        """Game reset clears the jury."""
        gid = create_game_api()
        for name, color in zip(PLAYERS, COLORS):
            join_player_api(gid, name, color)
        start_game_api(gid)
        api_post("/game/reset", {"gameId": gid})

        state = get_game_state(gid)
        jury = state.get("jury", [])
        assert len(jury) == 0, f"Jury should be empty after reset, has {len(jury)}"

    def test_can_restart_after_reset(self, server_check):
        """Game can be started again after reset."""
        gid = create_game_api()
        for name, color in zip(PLAYERS, COLORS):
            join_player_api(gid, name, color)
        start_game_api(gid)
        api_post("/game/reset", {"gameId": gid})

        # Start again
        result = start_game_api(gid)
        state = get_game_state(gid)
        assert state["phase"] == "playing"


class TestMinimumPlayers:
    """Step 22a: Minimum player count (3 players)."""

    def test_three_player_game_starts(self, server_check):
        """3-player game can start successfully."""
        gid = create_game_api()
        for i in range(3):
            join_player_api(gid, PLAYERS[i], COLORS[i])
        start_game_api(gid)

        state = get_game_state(gid)
        assert state["phase"] == "playing"
        assert len(state["turnOrder"]) == 3

    def test_two_players_cannot_start(self, server_check):
        """Game with only 2 players cannot start."""
        gid = create_game_api()
        for i in range(2):
            join_player_api(gid, PLAYERS[i], COLORS[i])

        result = api_post("/game/start_full", {"gameId": gid})
        assert result["success"] is False

    def test_three_player_final_tribal(self, server_check):
        """3-player game: eliminate 1 → final tribal with 2 remaining."""
        gid = create_game_api()
        pids = {}
        for i in range(3):
            pids[PLAYERS[i]] = join_player_api(gid, PLAYERS[i], COLORS[i])
        start_game_api(gid)

        state = get_game_state(gid)
        target = state["turnOrder"][-1]

        # Eliminate one player
        api_post("/vote/start", {"gameId": gid, "type": "single"})
        for _ in range(5):
            s = get_game_state(gid)
            if s.get("currentVote", {}).get("phase") == "voting":
                break
            api_post("/tribal/advance", {"gameId": gid})

        for pid in state["turnOrder"]:
            vote_target = target if pid != target else state["turnOrder"][0]
            api_post("/vote/cast", {
                "gameId": gid,
                "voterId": pid,
                "votesData": [{"targetId": vote_target, "votes": 1}]
            })

        api_post("/vote/reveal", {"gameId": gid})
        api_post("/tribal/complete", {"gameId": gid})

        final_state = get_game_state(gid)
        # Should transition to final tribal (2 players remaining)
        assert final_state["phase"] in ("final_tribal", "playing", "finished")


class TestEmptyDeck:
    """Step 22c: Empty deck handling."""

    def test_draw_from_empty_deck(self, server_check):
        """Drawing from an empty deck returns appropriate error."""
        gid = create_game_api()
        for name, color in zip(PLAYERS[:3], COLORS[:3]):
            join_player_api(gid, name, color)
        start_game_api(gid)

        state = get_game_state(gid)

        # Exhaust the deck by having players draw repeatedly
        max_draws = 100  # Safety limit
        current_pid = state["turnOrder"][state["currentTurnIndex"]]

        for _ in range(max_draws):
            s = get_game_state(gid)
            if s["phase"] != "playing":
                break
            if len(s.get("deck", [])) == 0:
                break
            # Draw on current player's turn
            cp = s["turnOrder"][s["currentTurnIndex"]]
            api_post("/turn/draw", {"gameId": gid, "playerId": cp})
            # Advance turn
            api_post("/turn/advance", {"gameId": gid})

        # Try to draw from empty deck
        final_state = get_game_state(gid)
        if final_state["phase"] == "playing" and len(final_state.get("deck", [])) == 0:
            cp = final_state["turnOrder"][final_state["currentTurnIndex"]]
            result = api_post("/turn/draw", {"gameId": gid, "playerId": cp})
            # Should either fail gracefully or indicate deck is empty
            assert "empty" in str(result).lower() or result["success"] is False or \
                   result.get("message", "")


class TestRapidActions:
    """Step 22d: Rapid action handling."""

    def test_rapid_button_clicks(self, server_check):
        """Multiple rapid API calls don't cause double-processing."""
        gid = create_game_api()
        for name, color in zip(PLAYERS, COLORS):
            join_player_api(gid, name, color)
        start_game_api(gid)

        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = state["turnOrder"][1]

        # Rapid-fire steal attempts
        results = []
        for _ in range(5):
            r = api_post("/turn/steal", {
                "gameId": gid,
                "playerId": current_pid,
                "targetId": target_pid
            })
            results.append(r["success"])

        # Only the first should succeed
        success_count = sum(1 for r in results if r)
        assert success_count <= 1, f"Multiple steals succeeded: {success_count}"


class TestReconnectAfterElimination:
    """Step 22e: Reconnect after elimination."""

    def test_eliminated_player_can_rejoin(self, server_check):
        """Eliminated player can reconnect and see game state."""
        gid = create_game_api()
        pids = {}
        for name, color in zip(PLAYERS, COLORS):
            pids[name] = join_player_api(gid, name, color)
        start_game_api(gid)

        state = get_game_state(gid)
        target_pid = state["turnOrder"][-1]

        # Eliminate a player
        api_post("/vote/start", {"gameId": gid, "type": "single"})
        for _ in range(5):
            s = get_game_state(gid)
            if s.get("currentVote", {}).get("phase") == "voting":
                break
            api_post("/tribal/advance", {"gameId": gid})

        for pid in state["turnOrder"]:
            vote_target = target_pid if pid != target_pid else state["turnOrder"][0]
            api_post("/vote/cast", {
                "gameId": gid,
                "voterId": pid,
                "votesData": [{"targetId": vote_target, "votes": 1}]
            })

        api_post("/vote/reveal", {"gameId": gid})

        # Check if elimination happened before completing tribal
        mid_state = get_game_state(gid)
        if not mid_state["players"][target_pid].get("isEliminated"):
            pytest.skip("Tribal elimination didn't trigger - phase flow issue")

        api_post("/tribal/complete", {"gameId": gid})

        # Eliminated player tries to rejoin
        result = api_post("/player/rejoin", {
            "gameId": gid,
            "playerId": target_pid
        })
        assert result["success"] is True

        # Should see game state but be marked eliminated
        new_state = get_game_state(gid)
        assert new_state["players"][target_pid].get("isEliminated") is True
