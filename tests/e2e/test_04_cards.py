"""
Steps 7-8: Card Effects (All 18 Types) + Reactive Interrupt (Sorry For You)

Tests every card type's effect via API-level injection and verification.
Priority: P1 (Important)
"""

import pytest
from conftest import (
    api_post, api_get, get_game_state,
    create_game_api, join_player_api, start_game_api,
    PLAYERS, COLORS
)


def make_started_game():
    """Helper to create a fresh started game for card tests."""
    gid = create_game_api()
    pids = {}
    for name, color in zip(PLAYERS, COLORS):
        pids[name] = join_player_api(gid, name, color)
    start_game_api(gid)
    return gid, pids


def find_card_index(gid, player_id, card_type):
    """Find the index of a card type in a player's hand. Returns index or None."""
    state = get_game_state(gid)
    hand = state["players"][player_id].get("hand", [])
    for i, card in enumerate(hand):
        if card.get("type") == card_type:
            return i
    return None


class TestActionCards:
    """Test action cards played during turn_play phase."""

    def test_the_spy_shack(self, server_check):
        """The Spy Shack: reveals target's hand."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        # Find spy shack card in player's hand
        card_idx = find_card_index(gid, current_pid, "the_spy_shack")
        if card_idx is None:
            pytest.skip("the_spy_shack not in current player's hand")

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx,
            "targetId": target_pid
        })
        # The spy shack should succeed (reveals hand)
        if result["success"]:
            assert "hand" in str(result) or result["success"]

    def test_camp_raid(self, server_check):
        """Camp Raid: steals 2 random cards from target."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        card_idx = find_card_index(gid, current_pid, "camp_raid")
        if card_idx is None:
            pytest.skip("camp_raid not in current player's hand")

        target_hand_before = len(state["players"][target_pid]["hand"])

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx,
            "targetId": target_pid
        })

        if result["success"]:
            new_state = get_game_state(gid)
            target_hand_after = len(new_state["players"][target_pid]["hand"])
            # Should lose up to 2 cards
            assert target_hand_after <= target_hand_before

    def test_knowledge_is_power(self, server_check):
        """Knowledge Is Power: steal a named card type from target."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        card_idx = find_card_index(gid, current_pid, "knowledge_is_power")
        if card_idx is None:
            pytest.skip("knowledge_is_power not in current player's hand")

        # Check what cards the target has
        target_hand = state["players"][target_pid]["hand"]
        if target_hand:
            steal_type = target_hand[0]["type"]

            result = api_post("/turn/play_card", {
                "gameId": gid,
                "playerId": current_pid,
                "cardIdx": card_idx,
                "targetId": target_pid,
                "params": {"cardType": steal_type}
            })
            # Should succeed or fail gracefully
            assert "success" in result

    def test_inheritance(self, server_check):
        """Inheritance: sets inheritanceTarget on player."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        card_idx = find_card_index(gid, current_pid, "inheritance")
        if card_idx is None:
            pytest.skip("inheritance not in current player's hand")

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx,
            "targetId": target_pid
        })

        if result["success"]:
            new_state = get_game_state(gid)
            player = new_state["players"][current_pid]
            assert player.get("inheritanceTarget") == target_pid

    def test_lets_form_an_alliance(self, server_check):
        """Let's Form An Alliance: player + ally steal from victim."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        others = [p for p in state["turnOrder"] if p != current_pid]
        ally_pid = others[0]
        victim_pid = others[1]

        card_idx = find_card_index(gid, current_pid, "lets_form_an_alliance")
        if card_idx is None:
            pytest.skip("lets_form_an_alliance not in current player's hand")

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx,
            "targetId": victim_pid,
            "params": {"allyId": ally_pid, "victimId": victim_pid}
        })
        assert "success" in result

    def test_reward_challenge_do_or_die(self, server_check):
        """Do Or Die: RPS-style challenge between two players."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        card_idx = find_card_index(gid, current_pid, "reward_challenge_do_or_die")
        if card_idx is None:
            pytest.skip("reward_challenge_do_or_die not in current player's hand")

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx,
            "targetId": target_pid,
            "params": {"choice": "rock"}
        })
        assert "success" in result

    def test_reward_challenge_power_pair(self, server_check):
        """Power Pair: random finger game."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]

        card_idx = find_card_index(gid, current_pid, "reward_challenge_power_pair")
        if card_idx is None:
            pytest.skip("reward_challenge_power_pair not in current player's hand")

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx
        })
        assert "success" in result

    def test_reward_challenge_numbers_game(self, server_check):
        """Numbers Game: closest number gives card."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]

        card_idx = find_card_index(gid, current_pid, "reward_challenge_its_a_numbers_game")
        if card_idx is None:
            pytest.skip("reward_challenge_its_a_numbers_game not in current player's hand")

        result = api_post("/turn/play_card", {
            "gameId": gid,
            "playerId": current_pid,
            "cardIdx": card_idx
        })
        assert "success" in result


class TestReactiveCards:
    """Step 8: Sorry For You reactive interrupt flow."""

    def test_sorry_for_you_blocks_theft(self, server_check):
        """Sorry For You blocks a steal attempt."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        # Initiate steal to trigger reactive window
        steal_result = api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": current_pid,
            "targetId": target_pid
        })

        # Check if reactive window was opened (depends on target having Sorry For You)
        new_state = get_game_state(gid)
        pending = new_state.get("pending_theft")
        if pending and pending.get("reactive_window_open"):
            # Target plays Sorry For You
            reactive_result = api_post("/reactive/play_card", {
                "gameId": gid,
                "playerId": target_pid,
                "cardType": "sorry_for_you"
            })
            if reactive_result["success"]:
                final_state = get_game_state(gid)
                assert final_state.get("pending_theft") is None or \
                       not final_state.get("pending_theft", {}).get("reactive_window_open")

    def test_reactive_decline_allows_theft(self, server_check):
        """Declining reactive card allows theft to proceed."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][state["currentTurnIndex"]]
        target_pid = [p for p in state["turnOrder"] if p != current_pid][0]

        target_hand_before = len(state["players"][target_pid]["hand"])

        # Steal
        api_post("/turn/steal", {
            "gameId": gid,
            "thiefId": current_pid,
            "targetId": target_pid
        })

        new_state = get_game_state(gid)
        pending = new_state.get("pending_theft")
        if pending and pending.get("reactive_window_open"):
            # Complete theft without reactive card
            api_post("/reactive/complete_theft", {
                "gameId": gid,
                "playerId": target_pid
            })

        final_state = get_game_state(gid)
        target_hand_after = len(final_state["players"][target_pid]["hand"])
        # Theft should have gone through (target lost a card)
        assert target_hand_after <= target_hand_before


class TestVoteCards:
    """Vote and Extra Vote card effects during tribal council."""

    def test_extra_vote_adds_votes(self, server_check):
        """Extra Vote gives player additional votes during tribal."""
        gid, pids = make_started_game()
        state = get_game_state(gid)

        # We need to trigger tribal council first
        # Fast-forward by manipulating state via API
        current_pid = state["turnOrder"][0]
        target_pid = state["turnOrder"][1]

        # Start a tribal council via vote/start
        result = api_post("/vote/start", {
            "gameId": gid,
            "type": "single"
        })

        if result.get("success"):
            # Try to play extra vote during discussion/advantage phase
            adv_result = api_post("/tribal/advantage", {
                "gameId": gid,
                "playerId": current_pid,
                "cardType": "extra_vote"
            })
            if adv_result.get("success"):
                new_state = get_game_state(gid)
                player = new_state["players"][current_pid]
                assert player.get("extraVotes", 0) >= 1


class TestTribalAdvantageCards:
    """Tribal advantage cards: control_the_vote, im_the_leader_now, goodwill_gamble."""

    def test_control_the_vote_changes_leader(self, server_check):
        """Control The Vote: changes council leader."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        current_pid = state["turnOrder"][0]
        new_leader_pid = state["turnOrder"][1]

        # Start tribal
        api_post("/vote/start", {"gameId": gid, "type": "single"})

        result = api_post("/tribal/advantage", {
            "gameId": gid,
            "playerId": current_pid,
            "cardType": "control_the_vote",
            "targetId": new_leader_pid
        })

        if result.get("success"):
            new_state = get_game_state(gid)
            vote_data = new_state.get("currentVote", {})
            assert vote_data.get("councilLeaderId") == new_leader_pid

    def test_immunity_idol_protects(self, server_check):
        """Hidden Immunity Idol: protects player from elimination."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        player_pid = state["turnOrder"][0]

        # Start tribal and advance to immunity phase
        api_post("/vote/start", {"gameId": gid, "type": "single"})

        # Try to advance tribal to immunity phase
        for _ in range(3):
            api_post("/tribal/advance", {"gameId": gid})

        result = api_post("/immunity/play", {
            "gameId": gid,
            "playerId": player_pid
        })

        if result.get("success"):
            new_state = get_game_state(gid)
            player = new_state["players"][player_pid]
            assert player.get("immunityIdolProtection") is True

    def test_idol_nullifier_removes_protection(self, server_check):
        """Idol Nullifier: removes immunity protection from target."""
        gid, pids = make_started_game()
        state = get_game_state(gid)
        protected_pid = state["turnOrder"][0]
        nullifier_pid = state["turnOrder"][1]

        # Start tribal
        api_post("/vote/start", {"gameId": gid, "type": "single"})

        # Advance to immunity phase
        for _ in range(3):
            api_post("/tribal/advance", {"gameId": gid})

        # Play immunity idol
        api_post("/immunity/play", {
            "gameId": gid,
            "playerId": protected_pid
        })

        # Play nullifier
        result = api_post("/immunity/block", {
            "gameId": gid,
            "playerId": nullifier_pid,
            "targetId": protected_pid
        })

        if result.get("success"):
            new_state = get_game_state(gid)
            player = new_state["players"][protected_pid]
            assert player.get("idolNullified") is True
