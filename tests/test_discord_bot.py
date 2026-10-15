#!/usr/bin/env python3
"""Discord poller regressions that require the real discord.py dependency."""

import asyncio
import os
import signal
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

import discord_bot
from discord_bot import (
    AUTH_RETRY_SECONDS,
    ERROR_RETRY_MAX_SECONDS,
    ERROR_RETRY_SECONDS,
    IDLE_POLL_SECONDS,
    LINK_CLAIM_PATH,
    LINK_UNAVAILABLE_MESSAGE,
    PLAN_POLL_SECONDS,
    BotConfig,
    ConfigurationError,
    SurvivorAPI,
    SurvivorAPIError,
    SurvivorDiscordClient,
    _backoff,
    _ranked,
    _validate_active_games,
)


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


def listed(game_id, last_activity=None, phase="playing"):
    """One /api/voice/active entry; lastActivity only when given, as a newer
    server sends it."""
    entry = {"gameId": game_id, "phase": phase, "linkedPlayers": 1}
    if last_activity is not None:
        entry["lastActivity"] = last_activity
    return entry


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    async def get(self, path):
        self.requests.append(path)
        return self.responses[path]


def bot_config(**overrides):
    values = dict(
        token="token",
        guild_id=1,
        channel_ids={},
        base_url="http://127.0.0.1:9",
        access_code="wrong",
        mute_during_voting=False,
    )
    values.update(overrides)
    return BotConfig(**values)


def poller(responses, current_game_id, discovery_due=False):
    """A networkless client with Discord writes replaced by async spies.

    While a game is being watched, discovery re-runs only when it is due;
    `discovery_due` makes the first poll look again.
    """
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
    client._attributable_ids = set()
    client._next_discovery_at = 0.0 if discovery_due else float("inf")
    client._switch_candidate = None
    client._poll_failures = 0
    client._poll_failure_signature = None
    client._config_problem = None
    client._config_task = None
    client._poll_task = None
    client._shutdown_task = None
    client._closing = False
    client._ready_for_reconcile = asyncio.Event()
    client._wake_reconcile = asyncio.Event()
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


class GameSwitchingTest(unittest.IsolatedAsyncioTestCase):
    """The bot used to consult /api/voice/active only while idle, and then
    stayed on games[0] for good — so last night's abandoned table kept the
    voice channels all through tonight's game."""

    OLD_USER = "111111111111111111"
    NEW_USER = "222222222222222222"

    def responses(self, *active):
        return {
            "/api/voice/active": {"games": list(active)},
            "/api/voice/plan/old": plan("old", self.OLD_USER),
            "/api/voice/plan/tonight": plan("tonight", self.NEW_USER),
        }

    async def look_again(self, client):
        client._next_discovery_at = 0.0
        return await client._poll_once()

    async def test_discovery_waits_for_its_interval_while_watching(self):
        client = poller(self.responses(listed("old")), current_game_id=None)

        await client._poll_once()
        await client._poll_once()

        self.assertEqual(
            client.api.requests,
            ["/api/voice/active", "/api/voice/plan/old", "/api/voice/plan/old"],
        )
        self.assertGreater(client._next_discovery_at, time.monotonic())
        self.assertLessEqual(
            client._next_discovery_at, time.monotonic() + IDLE_POLL_SECONDS)

    async def test_tonights_game_overtaking_an_abandoned_one_takes_over(self):
        responses = self.responses(
            listed("tonight", last_activity=2_000.0),
            listed("old", last_activity=1_000.0),
        )
        client = poller(responses, current_game_id="old", discovery_due=True)

        await client._poll_once()
        # One look is not enough to move everybody's voice.
        self.assertEqual(client._current_game_id, "old")
        client._unlock_all_channels.assert_not_awaited()

        await self.look_again(client)

        self.assertEqual(client._current_game_id, "tonight")
        client._unlock_all_channels.assert_awaited_once()
        client._set_vote_mute.assert_awaited_once_with([], False)
        client._clear_every_member_bar.assert_awaited_once()
        self.assertEqual(client._reconcile.await_args.args[0]["gameId"], "tonight")

    async def test_a_single_poke_at_the_old_game_does_not_switch(self):
        responses = self.responses(
            listed("tonight", last_activity=2_000.0),
            listed("old", last_activity=1_000.0),
        )
        client = poller(responses, current_game_id="tonight", discovery_due=True)

        responses["/api/voice/active"]["games"].reverse()   # old leads once
        await client._poll_once()
        responses["/api/voice/active"]["games"].reverse()   # tonight again
        await self.look_again(client)
        responses["/api/voice/active"]["games"].reverse()   # old leads once more
        await self.look_again(client)

        self.assertEqual(client._current_game_id, "tonight")
        client._unlock_all_channels.assert_not_awaited()
        client._clear_every_member_bar.assert_not_awaited()

    async def test_a_watched_game_that_leaves_the_list_is_released_at_once(self):
        client = poller(
            self.responses(listed("tonight")),
            current_game_id="old",
            discovery_due=True,
        )

        await client._poll_once()

        self.assertEqual(client._current_game_id, "tonight")
        client._unlock_all_channels.assert_awaited_once()
        client._set_vote_mute.assert_awaited_once_with([], False)
        client._clear_every_member_bar.assert_awaited_once()
        self.assertEqual(client._reconcile.await_args.args[0]["gameId"], "tonight")

    async def test_an_empty_active_list_releases_the_watched_game(self):
        client = poller(self.responses(), current_game_id="old",
                        discovery_due=True)

        delay = await client._poll_once()

        self.assertEqual(delay, IDLE_POLL_SECONDS)
        self.assertIsNone(client._current_game_id)
        client._unlock_all_channels.assert_awaited()
        client._clear_every_member_bar.assert_awaited_once()
        client._reconcile.assert_not_awaited()

    async def test_an_older_servers_order_is_not_followed(self):
        # No lastActivity: the list is sorted by gameId and ranks nothing.
        client = poller(
            self.responses(listed("aaa"), listed("old")),
            current_game_id="old",
            discovery_due=True,
        )

        await client._poll_once()
        await self.look_again(client)
        await self.look_again(client)

        self.assertEqual(client._current_game_id, "old")
        client._unlock_all_channels.assert_not_awaited()

    async def test_the_bars_lifted_on_a_switch_are_the_released_games(self):
        responses = self.responses(listed("tonight"))
        client = poller(responses, current_game_id="old")
        await client._poll_once()   # reads old's plan
        seen = []
        client._clear_every_member_bar = AsyncMock(
            side_effect=lambda reason: seen.append(set(client._attributable_ids)))

        await self.look_again(client)

        self.assertEqual(seen, [{int(self.OLD_USER)}])
        self.assertEqual(client._attributable_ids, {int(self.NEW_USER)})

    def test_last_activity_is_optional_and_a_bad_one_is_dropped(self):
        games = _validate_active_games({"games": [
            listed("a"),
            {"gameId": "b", "lastActivity": "yesterday"},
            {"gameId": "c", "lastActivity": float("nan")},
            {"gameId": "d", "lastActivity": True},
        ]})

        self.assertEqual([g["gameId"] for g in games], ["a", "b", "c", "d"])
        self.assertFalse(any("lastActivity" in g for g in games))
        self.assertFalse(_ranked(games))
        self.assertTrue(_ranked([listed("a", 1.0), listed("b", 2)]))


class BackoffTest(unittest.IsolatedAsyncioTestCase):
    def test_backoff_doubles_from_five_seconds_to_five_minutes(self):
        delays = [_backoff(n, ERROR_RETRY_SECONDS, ERROR_RETRY_MAX_SECONDS)
                  for n in range(1, 10)]
        self.assertEqual(delays, [5, 10, 20, 40, 80, 160, 300, 300, 300])
        # A long outage must not overflow the float.
        self.assertEqual(
            _backoff(10**6, ERROR_RETRY_SECONDS, ERROR_RETRY_MAX_SECONDS), 300)

    def test_one_traceback_per_kind_of_failure_then_one_liners(self):
        client = poller({}, None)
        down = SurvivorAPIError(0, "/api/voice/active", "Cannot connect to host")
        gateway = SurvivorAPIError(502, "/api/voice/active", "Bad gateway")

        with self.assertLogs("survivor.discord", level="INFO") as logs:
            delays = [client._poll_failed(down), client._poll_failed(down),
                      client._poll_failed(gateway)]
            client._poll_succeeded()
            delays.append(client._poll_failed(down))

        self.assertEqual(delays, [5, 10, 20, 5])
        levels = [(r.levelname, r.exc_info is not None) for r in logs.records]
        self.assertEqual(levels, [
            ("ERROR", True),      # first failure: the traceback
            ("WARNING", False),   # same failure again: one line
            ("ERROR", True),      # a different failure: its traceback
            ("INFO", False),      # recovered
            ("ERROR", True),      # a new outage after recovery
        ])

    async def test_the_poll_loop_backs_off_and_resets_on_success(self):
        client = poller({}, None)
        client._ready_for_reconcile.set()
        delays = []
        record = client._poll_failed
        client._poll_failed = lambda exc: delays.append(record(exc)) or delays[-1]
        down = SurvivorAPIError(0, "/api/voice/active", "Cannot connect to host")
        outcomes = [down, down, down, PLAN_POLL_SECONDS, down]

        async def poll_once():
            client._wake_reconcile.set()   # do not actually wait out the delay
            outcome = outcomes.pop(0)
            if not outcomes:
                client._closing = True
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        client._poll_once = poll_once
        with self.assertLogs("survivor.discord", level="INFO"):
            await asyncio.wait_for(client._poll_loop(), timeout=5)

        self.assertEqual(delays, [5, 10, 20, 5])


class AuthenticationTest(unittest.IsolatedAsyncioTestCase):
    def api(self, *responses):
        api = SurvivorAPI(bot_config())
        api.session = object()   # never used: _raw_request is replaced
        api._raw_request = AsyncMock(side_effect=list(responses))
        return api

    async def test_opening_makes_no_request(self):
        # An island still starting at boot used to crash the bot right here.
        api = SurvivorAPI(bot_config())
        api._raw_request = AsyncMock()
        await api.open()
        try:
            api._raw_request.assert_not_awaited()
        finally:
            await api.close()

    async def test_the_first_call_authenticates_and_the_cookie_is_reused(self):
        api = self.api(
            (200, {"success": True}, "Welcome ashore"),
            (200, {"games": []}, ""),
            (200, {"games": []}, ""),
        )

        await api.get("/api/voice/active")
        await api.get("/api/voice/active")

        methods = [call.args[:2] for call in api._raw_request.await_args_list]
        self.assertEqual(methods, [
            ("POST", "/api/access"),
            ("GET", "/api/voice/active"),
            ("GET", "/api/voice/active"),
        ])

    async def test_a_refused_code_is_not_presented_again_until_cooldown(self):
        refused = (403, {"success": False, "message": "That's not the code."},
                   "That's not the code.")
        api = self.api(refused, refused)

        with self.assertRaises(SurvivorAPIError):
            await api.get("/api/voice/active")
        self.assertAlmostEqual(
            api._auth_retry_at - time.monotonic(), AUTH_RETRY_SECONDS, delta=5)

        # Inside the cooldown nothing reaches the island's rate limiter.
        with self.assertRaises(SurvivorAPIError) as cooling:
            await api.get("/api/voice/active")
        self.assertEqual(api._raw_request.await_count, 1)
        self.assertEqual(cooling.exception.status, 403)

        api._auth_retry_at = 0.0   # the cooldown has run out
        with self.assertRaises(SurvivorAPIError):
            await api.get("/api/voice/active")
        self.assertEqual(api._raw_request.await_count, 2)
        # ... and the next one is longer.
        self.assertAlmostEqual(
            api._auth_retry_at - time.monotonic(), 2 * AUTH_RETRY_SECONDS,
            delta=5)

    async def test_an_unreachable_island_is_not_a_cooldown(self):
        # It never reached the gate; the poll loop's own backoff spaces these.
        down = SurvivorAPIError(0, "/api/access", "Cannot connect to host")
        api = self.api(down, down)

        for _ in range(2):
            with self.assertRaises(SurvivorAPIError):
                await api.get("/api/voice/active")

        self.assertEqual(api._raw_request.await_count, 2)
        self.assertIsNone(api._auth_error)


class LinkReplyTest(unittest.IsolatedAsyncioTestCase):
    """`/link` showed players raw transport errors, because the detail of a
    failed request is never empty."""

    async def claim_error(self, *responses):
        api = SurvivorAPI(bot_config())
        api.session = object()
        api._raw_request = AsyncMock(side_effect=list(responses))
        with self.assertRaises(SurvivorAPIError) as raised:
            await api.post(LINK_CLAIM_PATH, {"code": "PALM-472",
                                             "discordUserId": "42"})
        return raised.exception

    async def test_a_refused_claim_carries_the_servers_sentence(self):
        expired = "That code has expired — ask for a new one."
        exc = await self.claim_error(
            (200, {"success": True}, ""),
            (400, {"success": False, "message": expired}, expired),
        )
        self.assertEqual(exc.user_message, expired)

    async def test_gateway_pages_and_gate_refusals_are_not_for_players(self):
        gateway = await self.claim_error(
            (200, {"success": True}, ""),
            (502, None, "<html>Bad gateway</html>"),
        )
        gated = {"success": False, "gated": True,
                 "message": "This island is code-locked"}
        locked_out = await self.claim_error(
            (200, {"success": True}, ""),
            (401, gated, gated["message"]),
            (200, {"success": True}, ""),
            (401, gated, gated["message"]),
        )
        self.assertIsNone(gateway.user_message)
        self.assertIsNone(locked_out.user_message)

    async def run_link(self, outcome):
        client = SurvivorDiscordClient(bot_config())
        client._register_commands()
        client.api.post = AsyncMock(
            side_effect=outcome if isinstance(outcome, Exception) else None,
            return_value=outcome,
        )
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        with self.assertNoLogs("survivor.discord", level="ERROR"):
            await client.tree.get_command("link").callback(interaction, "PALM-472")
        interaction.followup.send.assert_awaited_once()
        return interaction.followup.send.await_args

    async def test_a_dropped_connection_gets_the_friendly_line(self):
        reply = await self.run_link(SurvivorAPIError(
            0, LINK_CLAIM_PATH,
            "Cannot connect to host 127.0.0.1:8080 ssl:default "
            "[Connect call failed ('127.0.0.1', 8080)]",
        ))
        self.assertEqual(reply.args, (LINK_UNAVAILABLE_MESSAGE,))
        self.assertEqual(reply.kwargs, {"ephemeral": True})

    async def test_an_island_that_will_not_let_the_bot_in_gets_it_too(self):
        reply = await self.run_link(SurvivorAPIError(
            403, "/api/access", "That's not the code. The island stays hidden.",
        ))
        self.assertEqual(reply.args, (LINK_UNAVAILABLE_MESSAGE,))

    async def test_the_claims_own_refusal_is_shown(self):
        expired = "That code has expired — ask for a new one."
        reply = await self.run_link(SurvivorAPIError(
            400, LINK_CLAIM_PATH, expired, user_message=expired))
        self.assertEqual(reply.args, (expired,))

    async def test_success_shows_the_servers_message(self):
        reply = await self.run_link({"success": True, "message": "Linked, Tyler."})
        self.assertEqual(reply.args, ("Linked, Tyler.",))


class FakeChannel:
    """Per-member Connect denies keyed by id, as Discord stores them."""

    def __init__(self, name, denied):
        self.name = name
        self.denied = set(denied)
        self.set_permissions = AsyncMock(side_effect=self._apply)

    def overwrites_for(self, target):
        return discord.PermissionOverwrite(
            connect=False if target.id in self.denied else None)

    async def _apply(self, target, *, overwrite, reason):
        if overwrite is not None and overwrite.connect is False:
            self.denied.add(target.id)
        else:
            self.denied.discard(target.id)


class MemberBarTest(unittest.IsolatedAsyncioTestCase):
    PLAYER = 111111111111111111
    MODERATED = 999999999999999999

    def client(self, denied):
        client = poller({}, None)
        del client._clear_every_member_bar   # the real one, not the spy
        client.channels = {"the_beach": FakeChannel("The Beach", denied)}
        # Nobody is cached: without the members intent, someone who left
        # voice is not, and the old code skipped exactly them.
        client.guild = SimpleNamespace(
            get_member=lambda user_id: None,
            fetch_member=AsyncMock(side_effect=lambda user_id: SimpleNamespace(
                id=user_id, display_name=f"user {user_id}")),
        )
        return client

    async def test_only_linked_players_bars_are_lifted_even_uncached(self):
        client = self.client({self.PLAYER, self.MODERATED})
        client._attributable_ids = {self.PLAYER}

        await client._clear_every_member_bar("test")

        self.assertEqual(client.channels["the_beach"].denied, {self.MODERATED})
        client.guild.fetch_member.assert_awaited_once_with(self.PLAYER)

    async def test_nothing_is_lifted_before_any_plan_has_been_read(self):
        client = self.client({self.PLAYER, self.MODERATED})

        await client._clear_every_member_bar("startup")

        self.assertEqual(client.channels["the_beach"].denied,
                         {self.PLAYER, self.MODERATED})
        client.channels["the_beach"].set_permissions.assert_not_awaited()

    async def test_barring_an_uncached_member_does_not_fetch(self):
        client = self.client(set())

        self.assertTrue(
            await client._set_member_lock("the_beach", self.PLAYER, locked=True))

        client.guild.fetch_member.assert_not_awaited()

    async def test_mutes_are_left_alone_when_the_voting_mute_is_off(self):
        client = poller({}, None)
        client.channels = {"camp_fire": SimpleNamespace(voice_states={5: None})}
        client._member = AsyncMock()

        await client._unmute_everyone_in_managed_channels("startup")

        client._member.assert_not_awaited()


class LifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_configuration_error_does_not_exit(self):
        client = poller({}, None)
        client._connection = SimpleNamespace(user="Jeff")
        client.close = AsyncMock()
        client._resolve_discord_configuration = AsyncMock(side_effect=[
            ConfigurationError("DISCORD_THE_BEACH_CHANNEL_ID is not visible"),
            ConfigurationError("DISCORD_THE_BEACH_CHANNEL_ID is not visible"),
            None,
        ])

        with patch.object(discord_bot, "CONFIG_RECHECK_SECONDS", 0):
            with self.assertLogs("survivor.discord", level="INFO") as logs:
                await client.on_ready()
                self.assertFalse(client._ready_for_reconcile.is_set())
                await asyncio.wait_for(client._config_task, timeout=5)

        client.close.assert_not_awaited()
        self.assertTrue(client._ready_for_reconcile.is_set())
        errors = [r for r in logs.records if r.levelname == "ERROR"]
        self.assertEqual(len(errors), 1)   # said once, not on every re-check

    async def test_close_releases_the_channels_once_however_often_called(self):
        client = poller({}, "live")
        client.api = SimpleNamespace(close=AsyncMock())
        with patch.object(discord.Client, "close", AsyncMock()) as disconnect:
            await asyncio.gather(client.close(), client.close())

        client._unlock_all_channels.assert_awaited_once()
        client._clear_every_member_bar.assert_awaited_once()
        client.api.close.assert_awaited_once()
        disconnect.assert_awaited_once()

    async def test_sigterm_runs_close_instead_of_killing_the_process(self):
        class FakeClient:
            def __init__(self):
                self.stopped = asyncio.Event()
                self.close_calls = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc_info):
                await self.close()

            async def start(self, token, reconnect):
                if signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, None):
                    raise unittest.SkipTest("loop signal handlers unavailable")
                os.kill(os.getpid(), signal.SIGTERM)
                await asyncio.wait_for(self.stopped.wait(), timeout=5)

            async def close(self):
                self.close_calls += 1
                self.stopped.set()

        client = FakeClient()
        before = signal.getsignal(signal.SIGTERM)
        with self.assertLogs("survivor.discord", level="INFO") as logs:
            await discord_bot._run(client, "token")

        self.assertGreaterEqual(client.close_calls, 1)
        self.assertIn("SIGTERM received", logs.output[0])
        if before == signal.SIG_DFL:   # and the handler does not outlive _run
            self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
