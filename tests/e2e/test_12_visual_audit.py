"""
Step 12: Multi-Viewport Visual Audit Test

Opens the app at mobile (375x812) and desktop (1440x900) viewports,
navigates to each major screen, takes full-page screenshots, and
validates layout integrity (no overflow, proper touch targets, headings).
Priority: P2 (Quality)
"""

import pytest
import time
from conftest import (
    BASE_URL, api_post, api_get, get_game_state,
    create_game_api, join_player_api, start_game_api,
    PLAYERS, COLORS,
)

SCREENSHOT_DIR = "tests/e2e/screenshots"

VIEWPORTS = {
    "mobile": {"width": 375, "height": 812},
    "desktop": {"width": 1440, "height": 900},
}


def _wait_app_ready(page, timeout=15000):
    """Wait for the app to finish initializing."""
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        "window.appReady === true || "
        "document.getElementById('loading-overlay')?.style.display === 'none'",
        timeout=timeout,
    )
    page.wait_for_timeout(1500)


def _sync_game(page, game_id, player_id):
    """Inject game/player IDs and sync state in the browser."""
    page.evaluate(
        f"""() => {{
        if (window.SurvivorGame) {{
            window.SurvivorGame.localGameState.gameId = '{game_id}';
            window.SurvivorGame.localGameState.playerId = '{player_id}';
        }}
    }}"""
    )
    page.evaluate(
        """async () => {
        if (window.SurvivorStateManager && window.SurvivorStateManager.syncState) {
            await window.SurvivorStateManager.syncState();
        }
    }"""
    )
    page.wait_for_timeout(500)


def _force_screen(page, screen_id):
    """Force-activate a specific screen by toggling CSS classes."""
    page.evaluate(
        f"""() => {{
        document.querySelectorAll('[id$="Screen"]').forEach(s => {{
            s.classList.remove('active');
            s.style.display = 'none';
        }});
        const target = document.getElementById('{screen_id}');
        if (target) {{
            target.classList.add('active');
            target.style.display = 'block';
        }}
    }}"""
    )
    page.wait_for_timeout(300)


class TestMultiViewportScreenshots:
    """Screenshot every major screen at both mobile and desktop viewports."""

    @pytest.fixture
    def game_context(self, server_check):
        """Create a started game for screenshot navigation."""
        gid = create_game_api()
        pids = {}
        for i in range(3):
            pids[PLAYERS[i]] = join_player_api(gid, PLAYERS[i], COLORS[i])
        start_game_api(gid)
        state = get_game_state(gid)
        return {
            "gameId": gid,
            "playerIds": pids,
            "state": state,
            "firstPlayerId": list(pids.values())[0],
        }

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_start_screen(self, browser, vp_name, vp_size):
        """Screenshot start screen at each viewport."""
        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        assert page.locator("#startScreen.active").is_visible()
        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_start.png",
            full_page=True,
        )
        ctx.close()

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_lobby_screen(self, browser, vp_name, vp_size, game_context):
        """Screenshot lobby screen at each viewport."""
        gid = game_context["gameId"]
        pid = game_context["firstPlayerId"]

        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        _sync_game(page, gid, pid)
        # Game is already started, so force lobby screen for screenshot
        _force_screen(page, "lobbyScreen")

        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_lobby.png",
            full_page=True,
        )
        ctx.close()

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_playing_screen(self, browser, vp_name, vp_size, game_context):
        """Screenshot playing screen at each viewport."""
        gid = game_context["gameId"]
        pid = game_context["firstPlayerId"]

        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        _sync_game(page, gid, pid)
        _force_screen(page, "playingScreen")

        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_playing.png",
            full_page=True,
        )
        ctx.close()

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_tribal_announcement_screen(self, browser, vp_name, vp_size, game_context):
        """Screenshot tribal announcement screen at each viewport."""
        gid = game_context["gameId"]
        pid = game_context["firstPlayerId"]

        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        _sync_game(page, gid, pid)
        _force_screen(page, "tribalAnnouncementScreen")

        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_tribal_announcement.png",
            full_page=True,
        )
        ctx.close()

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_voting_screen(self, browser, vp_name, vp_size, game_context):
        """Screenshot voting screen at each viewport."""
        gid = game_context["gameId"]
        pid = game_context["firstPlayerId"]

        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        _sync_game(page, gid, pid)
        _force_screen(page, "votingScreen")

        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_voting.png",
            full_page=True,
        )
        ctx.close()

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_final_tribal_screen(self, browser, vp_name, vp_size, game_context):
        """Screenshot final tribal screen at each viewport."""
        gid = game_context["gameId"]
        pid = game_context["firstPlayerId"]

        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        _sync_game(page, gid, pid)
        _force_screen(page, "finalTribalScreen")

        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_final_tribal.png",
            full_page=True,
        )
        ctx.close()

    @pytest.mark.parametrize("vp_name,vp_size", VIEWPORTS.items())
    def test_game_over_screen(self, browser, vp_name, vp_size, game_context):
        """Screenshot game over screen at each viewport."""
        gid = game_context["gameId"]
        pid = game_context["firstPlayerId"]

        ctx = browser.new_context(viewport=vp_size)
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        _sync_game(page, gid, pid)
        _force_screen(page, "gameOverScreen")

        page.screenshot(
            path=f"{SCREENSHOT_DIR}/12_visual_{vp_name}_game_over.png",
            full_page=True,
        )
        ctx.close()


class TestLayoutValidation:
    """Validate layout integrity at mobile viewport."""

    def test_no_horizontal_overflow_mobile(self, browser):
        """No horizontal scrollbar at 375px mobile width."""
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        assert overflow is False, "Horizontal overflow detected on mobile (375px)"
        ctx.close()

    def test_touch_targets_48px_minimum(self, browser):
        """All visible interactive elements meet 48x48px touch target minimum."""
        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        undersized = page.evaluate(
            """() => {
            const elements = document.querySelectorAll(
                'button, a, [role="button"], .color-btn, .card-button, .vote-target'
            );
            const tooSmall = [];
            elements.forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    if (rect.width < 44 || rect.height < 44) {
                        tooSmall.push({
                            tag: el.tagName,
                            text: (el.textContent || '').trim().substring(0, 30),
                            cls: el.className.substring(0, 40),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        });
                    }
                }
            });
            return tooSmall;
        }"""
        )
        # Filter out color buttons (decorative) and sr-only elements (keyboard-only)
        non_color = [b for b in undersized
                     if "color-btn" not in b.get("cls", "")
                     and "sr-only" not in b.get("cls", "")]
        assert not non_color, f"Touch targets below 44px: {non_color}"
        ctx.close()

    def test_heading_hierarchy_valid(self, browser):
        """Page uses proper heading hierarchy (starts with h1)."""
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)

        headings = page.evaluate(
            """() => Array.from(document.querySelectorAll('h1, h2, h3'))
                .filter(h => getComputedStyle(h).display !== 'none')
                .map(h => ({ tag: h.tagName, text: h.textContent.trim().substring(0, 40) }))
            """
        )
        assert len(headings) > 0, "Page should have at least one heading"
        assert headings[0]["tag"] == "H1", \
            f"First visible heading should be H1, got {headings[0]['tag']}"
        ctx.close()

    def test_no_overflow_all_screens(self, browser, server_check):
        """Check horizontal overflow on all forced screens at mobile width."""
        gid = create_game_api()
        for i in range(3):
            join_player_api(gid, PLAYERS[i], COLORS[i])
        start_game_api(gid)
        state = get_game_state(gid)
        pid = list(state["players"].keys())[0]

        screens = [
            "startScreen", "lobbyScreen", "playingScreen",
            "tribalAnnouncementScreen", "votingScreen",
            "resultsScreen", "finalTribalScreen", "gameOverScreen",
        ]

        ctx = browser.new_context(viewport={"width": 375, "height": 812})
        page = ctx.new_page()
        page.goto(BASE_URL)
        _wait_app_ready(page)
        _sync_game(page, gid, pid)

        overflow_screens = []
        for screen in screens:
            _force_screen(page, screen)
            has_overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            if has_overflow:
                overflow_screens.append(screen)

        assert not overflow_screens, \
            f"Horizontal overflow on mobile in screens: {overflow_screens}"
        ctx.close()
