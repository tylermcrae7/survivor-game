"""
Shared fixtures and helpers for Survivor E2E Playwright tests.

Provides multi-player browser contexts, API helpers, and game state utilities.
Server must be running on localhost:8081 before tests execute.
"""

import pytest
import time
import json
import requests

BASE_URL = "http://localhost:8081"
API = f"{BASE_URL}/api"

PLAYERS = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"]
COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#F9844A", "#90BE6D", "#F9C74F"]


# ── API helpers ──────────────────────────────────────────────────

def api_post(endpoint, data=None):
    """POST to game API, return JSON."""
    r = requests.post(f"{API}{endpoint}", json=data or {}, timeout=10)
    return r.json()


def api_get(endpoint):
    """GET from game API, return JSON."""
    r = requests.get(f"{API}{endpoint}", timeout=10)
    return r.json()


def create_game_api():
    """Create a game via API, return game ID."""
    result = api_post("/game/create")
    assert result["success"], f"Failed to create game: {result}"
    return result["gameId"]


def join_player_api(game_id, name, color):
    """Join a player via API, return player ID."""
    result = api_post("/player/join", {
        "gameId": game_id,
        "name": name,
        "color": color
    })
    assert result["success"], f"Failed to join {name}: {result}"
    return result["playerId"]


def start_game_api(game_id):
    """Start the game via API."""
    result = api_post("/game/start_full", {"gameId": game_id})
    assert result["success"], f"Failed to start game: {result}"
    return result


def get_game_state(game_id):
    """Get current game state via API."""
    return api_get(f"/game/{game_id}/state")


# ── Playwright fixtures ──────────────────────────────────────────

@pytest.fixture(scope="session")
def server_check():
    """Verify server is running before any tests."""
    try:
        r = requests.get(f"{API}/ping", timeout=5)
        data = r.json()
        assert data["success"], "Server ping failed"
    except Exception as e:
        pytest.skip(f"Server not running at {BASE_URL}: {e}")


@pytest.fixture
def game_id(server_check):
    """Create a fresh game and return its ID."""
    return create_game_api()


@pytest.fixture
def six_player_game(server_check):
    """Create a game with 6 players joined (still in lobby)."""
    gid = create_game_api()
    player_ids = {}
    for name, color in zip(PLAYERS, COLORS):
        pid = join_player_api(gid, name, color)
        player_ids[name] = pid
    return {"gameId": gid, "playerIds": player_ids}


@pytest.fixture
def started_game(six_player_game):
    """Create a 6-player game that has been started (playing phase)."""
    gid = six_player_game["gameId"]
    start_game_api(gid)
    state = get_game_state(gid)
    return {
        **six_player_game,
        "state": state
    }


@pytest.fixture
def browser_page(page):
    """Single browser page navigated to the app."""
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    # Wait for all modules to load (appReady set by module init system)
    page.wait_for_function(
        "window.appReady === true || document.getElementById('loading-overlay')?.style.display === 'none'",
        timeout=15000
    )
    # Extra wait for deferred module initialization (DOMContentLoaded callbacks)
    page.wait_for_timeout(2000)
    return page


@pytest.fixture
def six_browser_pages(browser):
    """Create 6 separate browser contexts (one per player) for multi-player testing."""
    pages = []
    contexts = []
    for _ in range(6):
        ctx = browser.new_context()
        p = ctx.new_page()
        p.goto(BASE_URL)
        p.wait_for_load_state("networkidle")
        p.wait_for_function(
            "window.appReady === true || document.getElementById('loading-overlay')?.style.display === 'none'",
            timeout=10000
        )
        pages.append(p)
        contexts.append(ctx)
    yield pages
    for ctx in contexts:
        ctx.close()


# ── Page interaction helpers ─────────────────────────────────────

def create_game_ui(page):
    """Click 'Create New Game' and return the game code."""
    page.click("text=Create New Game")
    # Wait for game code to appear in the input
    page.wait_for_function(
        "document.getElementById('gameCodeInput')?.value?.length > 0",
        timeout=5000
    )
    game_code = page.evaluate("document.getElementById('gameCodeInput').value")
    return game_code


def join_game_ui(page, game_code, name, color_index=0):
    """Join an existing game through the UI."""
    # Click "Join Existing Game" to show form (if not already shown)
    join_form = page.locator("#joinForm")
    if not join_form.is_visible():
        page.click("text=Join Existing Game")
        page.wait_for_selector("#joinForm", state="visible", timeout=3000)

    # Fill in game code
    page.fill("#gameCodeInput", game_code)

    # Fill in player name
    page.fill("#playerNameInput", name)

    # Click a color
    color_btns = page.locator(".color-btn")
    color_btns.nth(color_index).click()

    # Click Join
    page.click("text=Join Game")

    # Wait for lobby screen
    page.wait_for_selector("#lobbyScreen.active", timeout=5000)


def get_js_state(page, expression):
    """Evaluate a JS expression and return the result."""
    return page.evaluate(expression)


def wait_for_screen(page, screen_id, timeout=5000):
    """Wait for a specific screen to become active."""
    page.wait_for_selector(f"#{screen_id}.active", timeout=timeout)
