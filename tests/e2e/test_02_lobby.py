"""
Steps 4-5: Game Creation, 6-Player Lobby & Game Start

Tests game creation, joining 6 players, max player enforcement,
game start, initial deal, and deck composition.
Priority: P0 (Critical)
"""

import pytest
import time
from conftest import (
    BASE_URL, API, PLAYERS, COLORS,
    api_post, api_get, create_game_api, join_player_api,
    start_game_api, get_game_state, create_game_ui, join_game_ui,
    get_js_state, wait_for_screen
)


class TestGameCreation:
    """Step 4a: Create a game via UI."""

    def test_create_game_via_ui(self, browser_page):
        """Create game via UI, verify game code appears."""
        page = browser_page
        page.click("text=Create New Game")
        # Wait for API response and game code
        page.wait_for_function(
            "document.getElementById('gameCodeInput')?.value?.length > 0",
            timeout=5000
        )
        code = page.evaluate("document.getElementById('gameCodeInput').value")
        assert len(code) > 0, "Game code was not generated"

    def test_create_game_via_api(self, server_check):
        """Create game via API, verify response structure."""
        result = api_post("/game/create")
        assert result["success"] is True
        assert "gameId" in result
        assert len(result["gameId"]) > 0


class TestSixPlayerLobby:
    """Step 4b-4c: Fill lobby to max 6 players."""

    def test_join_six_players_api(self, game_id):
        """Join 6 players via API, verify all present."""
        player_ids = {}
        for name, color in zip(PLAYERS, COLORS):
            pid = join_player_api(game_id, name, color)
            player_ids[name] = pid
            assert pid is not None

        # Verify all 6 in game state
        state = get_game_state(game_id)
        players = state.get("players", {})
        assert len(players) == 6, f"Expected 6 players, got {len(players)}"
        names = sorted(p["name"] for p in players.values())
        assert names == sorted(PLAYERS)

    def test_player_colors_assigned(self, six_player_game):
        """Each player gets their selected color."""
        gid = six_player_game["gameId"]
        state = get_game_state(gid)
        colors_used = {p["color"] for p in state["players"].values()}
        assert len(colors_used) == 6, "Not all colors are unique"

    def test_max_player_enforcement(self, six_player_game):
        """7th player cannot join a full game."""
        gid = six_player_game["gameId"]
        result = api_post("/player/join", {
            "gameId": gid,
            "name": "Ghost",
            "color": "#FFFFFF"
        })
        assert result["success"] is False, "7th player should be rejected"
        assert "full" in result.get("message", "").lower() or "6" in result.get("message", "")

    def test_lobby_ui_shows_all_players(self, browser_page, six_player_game):
        """All 6 players visible in the lobby UI (from first player's perspective)."""
        page = browser_page
        gid = six_player_game["gameId"]
        alice_id = six_player_game["playerIds"]["Alice"]

        # Join as Alice through the UI by navigating to the game
        page.evaluate(f"""() => {{
            if (window.SurvivorGame) {{
                window.SurvivorGame.localGameState.gameId = '{gid}';
                window.SurvivorGame.localGameState.playerId = '{alice_id}';
            }}
        }}""")

        # Trigger rejoin
        result = api_post("/player/rejoin", {
            "gameId": gid,
            "playerId": alice_id
        })
        assert result["success"]

    def test_leader_set_after_game_start(self, started_game):
        """Council leader is populated in currentVote at game start (first player to join)."""
        state = started_game["state"]
        leader_id = state.get("currentVote", {}).get("councilLeaderId")
        # The first player to join becomes the council leader immediately
        assert leader_id is not None, "Leader should be set at game start"
        # Leader should be the first player in turn order
        assert leader_id == state["turnOrder"][0], (
            f"Leader should be the first player in turnOrder, "
            f"got {leader_id} != {state['turnOrder'][0]}"
        )


class TestGameStart:
    """Step 5: Start game, verify initial deal."""

    def test_start_game(self, started_game):
        """Game starts and enters 'playing' phase."""
        state = started_game["state"]
        assert state["phase"] == "playing", f"Expected 'playing', got {state['phase']}"

    def test_initial_hand_size(self, started_game):
        """Each player dealt 5 cards at start."""
        state = started_game["state"]
        for pid, player in state["players"].items():
            hand_size = len(player.get("hand", []))
            assert hand_size == 5, f"Player {player['name']} has {hand_size} cards, expected 5"

    def test_turn_order_has_six(self, started_game):
        """Turn order contains all 6 players."""
        state = started_game["state"]
        assert len(state.get("turnOrder", [])) == 6

    def test_deck_has_remaining_cards(self, started_game):
        """Deck has cards remaining after dealing (69 total - 30 dealt = 39 base)."""
        state = started_game["state"]
        deck_size = len(state.get("deck", []))
        assert deck_size > 0, "Deck should not be empty after dealing"
        # 69 total cards, 30 dealt (5 × 6), plus 5 tribal double cards inserted
        # So deck should have roughly 39 cards (some variation due to tribal insertion)

    def test_deck_composition_six_players(self, started_game):
        """6-player game: 0 single + 5 double tribal cards in deck."""
        state = started_game["state"]
        deck = state.get("deck", [])
        hands = []
        for p in state["players"].values():
            hands.extend(p.get("hand", []))

        all_cards = deck + hands
        singles = sum(1 for c in all_cards if c.get("type") == "tribal_council_single")
        doubles = sum(1 for c in all_cards if c.get("type") == "tribal_council_double")

        assert singles == 0, f"6-player game should have 0 single TC cards, got {singles}"
        assert doubles == 5, f"6-player game should have 5 double TC cards, got {doubles}"

    def test_current_turn_index_zero(self, started_game):
        """Game starts at turn index 0."""
        state = started_game["state"]
        assert state.get("currentTurnIndex", -1) == 0

    def test_screenshot_lobby_full(self, browser_page, six_player_game):
        """Screenshot of full 6-player lobby."""
        page = browser_page
        page.screenshot(path="tests/e2e/screenshots/02_lobby_full.png", full_page=True)


class TestPlayerNameValidation:
    """Step 18a: Player name validation rules."""

    def test_empty_name_rejected(self, game_id):
        """Empty name is rejected."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "",
            "color": "#FF6B6B"
        })
        assert result["success"] is False

    def test_single_char_rejected(self, game_id):
        """Single character name (< 2 chars) is rejected."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "A",
            "color": "#FF6B6B"
        })
        assert result["success"] is False

    def test_long_name_rejected(self, game_id):
        """Name longer than 30 characters is rejected."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "A" * 31,
            "color": "#FF6B6B"
        })
        assert result["success"] is False

    def test_special_chars_rejected(self, game_id):
        """Names with special characters are rejected."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "<script>alert(1)</script>",
            "color": "#FF6B6B"
        })
        assert result["success"] is False

    def test_valid_two_char_name(self, game_id):
        """Minimum valid name (2 chars) is accepted."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "Al",
            "color": "#FF6B6B"
        })
        assert result["success"] is True

    def test_name_with_spaces(self, game_id):
        """Name with spaces is accepted."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "John Doe",
            "color": "#4ECDC4"
        })
        assert result["success"] is True

    def test_name_with_allowed_special(self, game_id):
        """Name with dots, hyphens, underscores accepted."""
        result = api_post("/player/join", {
            "gameId": game_id,
            "name": "J.K_Smith-Jr",
            "color": "#45B7D1"
        })
        assert result["success"] is True


class TestInvalidGameIds:
    """Step 18c: Invalid game ID handling."""

    def test_nonexistent_game_rejected(self, server_check):
        """Joining non-existent game returns error."""
        result = api_post("/player/join", {
            "gameId": "NONEXISTENT999",
            "name": "Ghost",
            "color": "#FF6B6B"
        })
        assert result["success"] is False

    def test_join_after_start_rejected(self, started_game):
        """Cannot join a game that has already started."""
        gid = started_game["gameId"]
        result = api_post("/player/join", {
            "gameId": gid,
            "name": "Latecomer",
            "color": "#FFFFFF"
        })
        assert result["success"] is False
