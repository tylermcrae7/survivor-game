"""
Step 6: Turn Mechanics — Full Cycle (Steal → Play → Draw → Advance)

Tests complete turn flow across multiple players with state sync verification.
Priority: P0 (Critical)
"""

import pytest
from conftest import (
    api_post, get_game_state, PLAYERS
)


class TestTurnMechanics:
    """Full turn cycle: steal → play → draw → advance."""

    def test_first_player_is_current(self, started_game):
        """Turn 0 belongs to the first player in turn order."""
        state = started_game["state"]
        turn_order = state["turnOrder"]
        current_idx = state["currentTurnIndex"]
        current_pid = turn_order[current_idx]
        assert current_pid in state["players"]

    def test_steal_phase(self, started_game):
        """Current player can steal a card from another player."""
        gid = started_game["gameId"]
        state = started_game["state"]
        turn_order = state["turnOrder"]
        current_pid = turn_order[state["currentTurnIndex"]]
        # Pick a target (not self)
        target_pid = [p for p in turn_order if p != current_pid][0]

        target_hand_before = len(state["players"][target_pid]["hand"])
        current_hand_before = len(state["players"][current_pid]["hand"])

        result = api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": current_pid,
            "targetId": target_pid
        })
        assert result["success"] is True

        # If a reactive window opened (target has a Sorry For You card),
        # complete the theft so cards actually transfer.
        if result.get("reactive_window"):
            api_post("/reactive/complete_theft", {"gameId": gid})

        # Verify hand sizes changed
        new_state = get_game_state(gid)
        target_hand_after = len(new_state["players"][target_pid]["hand"])
        current_hand_after = len(new_state["players"][current_pid]["hand"])

        assert target_hand_after == target_hand_before - 1, "Target should lose 1 card"
        assert current_hand_after == current_hand_before + 1, "Thief should gain 1 card"

    def test_cannot_steal_twice(self, started_game):
        """Player cannot steal twice in the same turn."""
        gid = started_game["gameId"]
        state = started_game["state"]
        turn_order = state["turnOrder"]
        current_pid = turn_order[state["currentTurnIndex"]]
        target_pid = [p for p in turn_order if p != current_pid][0]

        # First steal
        first_result = api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": current_pid,
            "targetId": target_pid
        })

        # If a reactive window opened, complete the theft so hasStolen is set
        if first_result.get("reactive_window"):
            api_post("/reactive/complete_theft", {"gameId": gid})

        # Second steal should fail
        result = api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": current_pid,
            "targetId": target_pid
        })
        assert result["success"] is False

    def test_draw_card(self, started_game):
        """Current player can draw a card from the deck."""
        gid = started_game["gameId"]
        state = started_game["state"]
        turn_order = state["turnOrder"]
        current_pid = turn_order[state["currentTurnIndex"]]

        hand_before = len(state["players"][current_pid]["hand"])
        deck_before = len(state["deck"])

        result = api_post("/turn/draw", {
            "gameId": gid,
            "playerId": current_pid
        })
        assert result["success"] is True

        new_state = get_game_state(gid)
        # If a tribal card was drawn, the phase changes — handle both cases
        if new_state["phase"] == "playing":
            hand_after = len(new_state["players"][current_pid]["hand"])
            deck_after = len(new_state["deck"])
            assert hand_after == hand_before + 1, "Should gain 1 card from draw"
            assert deck_after == deck_before - 1, "Deck should shrink by 1"

    def test_advance_turn(self, started_game):
        """Advancing turn moves to the next player."""
        gid = started_game["gameId"]
        state = started_game["state"]
        initial_idx = state["currentTurnIndex"]

        result = api_post("/turn/advance", {"gameId": gid})
        assert result["success"] is True

        new_state = get_game_state(gid)
        new_idx = new_state["currentTurnIndex"]
        expected = (initial_idx + 1) % len(state["turnOrder"])
        assert new_idx == expected, f"Expected turn {expected}, got {new_idx}"

    def test_full_turn_cycle_three_players(self, started_game):
        """Execute 3 complete turn cycles (steal → draw → advance)."""
        gid = started_game["gameId"]
        state = get_game_state(gid)
        turn_order = state["turnOrder"]

        for turn in range(3):
            state = get_game_state(gid)
            if state["phase"] != "playing":
                break  # Tribal council triggered by draw

            current_idx = state["currentTurnIndex"]
            current_pid = turn_order[current_idx]
            target_pid = turn_order[(current_idx + 1) % len(turn_order)]

            # Steal
            api_post("/turn/steal", {
                "gameId": gid,
                "thiefId": current_pid,
                "targetId": target_pid
            })

            # Draw
            draw_result = api_post("/turn/draw", {
                "gameId": gid,
                "playerId": current_pid
            })

            # Check if tribal was triggered
            post_draw = get_game_state(gid)
            if post_draw["phase"] != "playing":
                break

            # Advance
            api_post("/turn/advance", {"gameId": gid})

        # Verify game state is still valid
        final_state = get_game_state(gid)
        assert final_state["phase"] in ("playing", "tribal_council")

    @pytest.mark.xfail(reason="BUG: Server allows non-current player to steal", strict=True)
    def test_wrong_player_cannot_steal(self, started_game):
        """Non-current player cannot steal."""
        gid = started_game["gameId"]
        state = started_game["state"]
        turn_order = state["turnOrder"]
        current_pid = turn_order[state["currentTurnIndex"]]
        wrong_pid = [p for p in turn_order if p != current_pid][0]
        target_pid = [p for p in turn_order if p != wrong_pid and p != current_pid][0]

        result = api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": wrong_pid,
            "targetId": target_pid
        })
        assert result["success"] is False

    @pytest.mark.xfail(reason="BUG: Server allows player to steal from themselves", strict=True)
    def test_cannot_steal_self(self, started_game):
        """Player cannot steal from themselves."""
        gid = started_game["gameId"]
        state = started_game["state"]
        turn_order = state["turnOrder"]
        current_pid = turn_order[state["currentTurnIndex"]]

        result = api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": current_pid,
            "targetId": current_pid
        })
        assert result["success"] is False
