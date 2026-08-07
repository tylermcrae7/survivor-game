#!/usr/bin/env python3
"""Discord poller regressions that require the real discord.py dependency."""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot import PLAN_POLL_SECONDS, SurvivorDiscordClient


PLACE_KEYS = (
    "camp_fire",
    "the_beach",
    "the_water_well",
    "tribal_council",
    "exile_island",
)


def plan(game_id, discord_user_id=None):
    player = {
        "playerId": "player-1",
        "name": "Tyler",
        "discordUserId": discord_user_id,
        "eliminated": False,
    }
    return {
        "gameId": game_id,
        "phase": "lobby",
        "version": f"version-{game_id}",
        "policy": {"open": ["camp_fire"], "forced": "camp_fire"},
        "places": [
            {
                "key": key,
                "label": key,
                "players": [player] if key == "camp_fire" else [],
            }
            for key in PLACE_KEYS
        ],
    }


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses

    async def get(self, path):
        return self.responses[path]


def poller(responses, current_game_id):
    """A networkless client with Discord writes replaced by async spies."""
    client = object.__new__(SurvivorDiscordClient)
    client.api = FakeAPI(responses)
    client.guild = object()
    client.channels = {key: object() for key in PLACE_KEYS}
    client.config = SimpleNamespace(
        channel_ids={key: index + 1 for index, key in enumerate(PLACE_KEYS)},
        mute_during_voting=False,
    )
    client._current_game_id = current_game_id
    client._last_plan_version = None
    client._last_mute_state = False
    client._force_reconcile = False
    client._idle_logged = False
    client._multiple_games_signature = None
    client._muted_member_ids = set()
    client._unlock_all_channels = AsyncMock()
    client._set_vote_mute = AsyncMock(return_value=True)
    client._clear_every_member_bar = AsyncMock()
    client._reconcile = AsyncMock(return_value=True)
    return client


class AbandonedGameReleaseTest(unittest.IsolatedAsyncioTestCase):
    async def test_zero_linked_players_releases_the_game_and_permissions(self):
        client = poller(
            {"/api/voice/plan/stale": plan("stale")},
            current_game_id="stale",
        )

        delay = await client._poll_once()

        self.assertEqual(delay, PLAN_POLL_SECONDS)
        self.assertIsNone(client._current_game_id)
        client._unlock_all_channels.assert_awaited_once()
        client._set_vote_mute.assert_awaited_once_with([], False)
        client._clear_every_member_bar.assert_awaited_once()
        client._reconcile.assert_not_awaited()

    async def test_next_poll_discovers_the_real_linked_game(self):
        client = poller(
            {
                "/api/voice/plan/stale": plan("stale"),
                "/api/voice/active": {
                    "games": [
                        {"gameId": "live", "phase": "playing", "linkedPlayers": 1}
                    ]
                },
                "/api/voice/plan/live": plan("live", "111111111111111111"),
            },
            current_game_id="stale",
        )

        await client._poll_once()
        await client._poll_once()

        self.assertEqual(client._current_game_id, "live")
        client._reconcile.assert_awaited_once()

    async def test_a_linked_game_is_not_released(self):
        client = poller(
            {
                "/api/voice/plan/live": plan("live", "111111111111111111"),
            },
            current_game_id="live",
        )

        await client._poll_once()

        self.assertEqual(client._current_game_id, "live")
        client._unlock_all_channels.assert_not_awaited()
        client._clear_every_member_bar.assert_not_awaited()
        client._reconcile.assert_awaited_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
