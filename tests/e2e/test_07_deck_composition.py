"""
Step 14: Deck Composition by Player Count

Verifies tribal card distribution follows official Survivor board game rules
for all player counts (3-6).
Priority: P2 (Quality)
"""

import pytest
from conftest import (
    api_post, get_game_state,
    create_game_api, join_player_api, start_game_api,
    PLAYERS, COLORS
)


# Official deck composition rules per player count
DECK_RULES = {
    3: {"single": 4, "double": 0},
    4: {"single": 2, "double": 2},
    5: {"single": 2, "double": 3},
    6: {"single": 0, "double": 5},
}


def make_game_with_n_players(n):
    """Create and start a game with exactly n players."""
    gid = create_game_api()
    pids = {}
    for i in range(n):
        pids[PLAYERS[i]] = join_player_api(gid, PLAYERS[i], COLORS[i])
    start_game_api(gid)
    return gid, pids


def count_tribal_cards(gid):
    """Count all tribal council cards (deck + all hands)."""
    state = get_game_state(gid)
    all_cards = list(state.get("deck", []))
    for p in state["players"].values():
        all_cards.extend(p.get("hand", []))

    singles = sum(1 for c in all_cards if c.get("type") == "tribal_council_single")
    doubles = sum(1 for c in all_cards if c.get("type") == "tribal_council_double")
    return singles, doubles


class TestDeckComposition:
    """Verify deck follows official Survivor rules for each player count."""

    def test_three_player_deck(self, server_check):
        """3 players: 4 single + 0 double tribal cards."""
        gid, _ = make_game_with_n_players(3)
        singles, doubles = count_tribal_cards(gid)
        assert singles == DECK_RULES[3]["single"], \
            f"3-player: expected {DECK_RULES[3]['single']} singles, got {singles}"
        assert doubles == DECK_RULES[3]["double"], \
            f"3-player: expected {DECK_RULES[3]['double']} doubles, got {doubles}"

    def test_four_player_deck(self, server_check):
        """4 players: 2 single + 2 double tribal cards."""
        gid, _ = make_game_with_n_players(4)
        singles, doubles = count_tribal_cards(gid)
        assert singles == DECK_RULES[4]["single"], \
            f"4-player: expected {DECK_RULES[4]['single']} singles, got {singles}"
        assert doubles == DECK_RULES[4]["double"], \
            f"4-player: expected {DECK_RULES[4]['double']} doubles, got {doubles}"

    def test_five_player_deck(self, server_check):
        """5 players: 2 single + 3 double tribal cards."""
        gid, _ = make_game_with_n_players(5)
        singles, doubles = count_tribal_cards(gid)
        assert singles == DECK_RULES[5]["single"], \
            f"5-player: expected {DECK_RULES[5]['single']} singles, got {singles}"
        assert doubles == DECK_RULES[5]["double"], \
            f"5-player: expected {DECK_RULES[5]['double']} doubles, got {doubles}"

    def test_six_player_deck(self, server_check):
        """6 players: 0 single + 5 double tribal cards."""
        gid, _ = make_game_with_n_players(6)
        singles, doubles = count_tribal_cards(gid)
        assert singles == DECK_RULES[6]["single"], \
            f"6-player: expected {DECK_RULES[6]['single']} singles, got {singles}"
        assert doubles == DECK_RULES[6]["double"], \
            f"6-player: expected {DECK_RULES[6]['double']} doubles, got {doubles}"

    def test_total_non_tribal_cards_constant(self, server_check):
        """Non-tribal card count is the same regardless of player count."""
        totals = []
        for n in (3, 4, 5, 6):
            gid, _ = make_game_with_n_players(n)
            state = get_game_state(gid)
            all_cards = list(state.get("deck", []))
            for p in state["players"].values():
                all_cards.extend(p.get("hand", []))

            non_tribal = sum(
                1 for c in all_cards
                if c.get("type") not in ("tribal_council_single", "tribal_council_double")
            )
            totals.append(non_tribal)

        # All should be equal (60 non-tribal cards)
        assert all(t == totals[0] for t in totals), \
            f"Non-tribal card counts vary: {totals}"

    def test_five_cards_dealt_each_player(self, server_check):
        """Every player gets exactly 5 cards regardless of player count."""
        for n in (3, 4, 5, 6):
            gid, _ = make_game_with_n_players(n)
            state = get_game_state(gid)
            for pid, p in state["players"].items():
                hand_size = len(p.get("hand", []))
                assert hand_size == 5, \
                    f"{n}-player game: {p['name']} has {hand_size} cards, expected 5"

    def test_tribal_cards_distributed_in_deck(self, server_check):
        """Tribal cards are spread throughout the deck, not clumped at the end."""
        gid, _ = make_game_with_n_players(6)
        state = get_game_state(gid)
        deck = state.get("deck", [])

        tribal_indices = [
            i for i, c in enumerate(deck)
            if c.get("type") in ("tribal_council_single", "tribal_council_double")
        ]

        if len(tribal_indices) >= 2:
            # Check that tribal cards are not all adjacent
            gaps = [tribal_indices[i+1] - tribal_indices[i] for i in range(len(tribal_indices)-1)]
            avg_gap = sum(gaps) / len(gaps)
            assert avg_gap > 1, "Tribal cards should be distributed, not clumped together"
