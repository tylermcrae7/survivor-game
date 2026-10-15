#!/usr/bin/env python3
"""Mirror Survivor player places into Discord voice channels.

The game server remains authoritative. This process polls its voice plan, moves
linked Discord members who are already connected to voice, and applies the
channel locks described by the plan.

It writes exactly one thing, and only through `/link`: the Discord account that
ran the command, bound to a code the app is showing. That endpoint cannot reach
a game. Everything else here is read-only, and the game plays out identically
with no bot connected at all.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import aiohttp
import discord


LOG = logging.getLogger("survivor.discord")

PLACE_KEYS = (
    "camp_fire",
    "the_beach",
    "the_water_well",
    "tribal_council",
    "exile_island",
)

# Where a snuffed player sits out the rest of the season, and the room the
# whole tribe is called into. Neither is ever barred to anyone in the game.
GHOST_PLACE = "exile_island"
COUNCIL_PLACE = "tribal_council"

CHANNEL_ENV = {
    "camp_fire": "DISCORD_CAMP_FIRE_CHANNEL_ID",
    "the_beach": "DISCORD_THE_BEACH_CHANNEL_ID",
    "the_water_well": "DISCORD_THE_WATER_WELL_CHANNEL_ID",
    "tribal_council": "DISCORD_TRIBAL_COUNCIL_CHANNEL_ID",
    "exile_island": "DISCORD_EXILE_ISLAND_CHANNEL_ID",
}

# Exile Island arrived after the other four, so a server that has not made the
# channel yet must still run. Without it the snuffed simply stay where Discord
# last left them — the game itself is unaffected, since nothing about places
# depends on a bot existing.
OPTIONAL_PLACES = frozenset({"exile_island"})

PLAN_POLL_SECONDS = 2.0
# Also how often a watched game is checked against /api/voice/active.
IDLE_POLL_SECONDS = 10.0
# A failing poll waits 5s, then 10s, 20s ... up to five minutes.
ERROR_RETRY_SECONDS = 5.0
ERROR_RETRY_MAX_SECONDS = 300.0
# After the island refuses the access code, wait at least this long (doubling
# to ERROR_RETRY_MAX_SECONDS) before presenting it again.
AUTH_RETRY_SECONDS = 60.0
# How often a Discord server that failed validation is looked at again.
CONFIG_RECHECK_SECONDS = 60.0
# launchd follows SIGTERM with SIGKILL after 20 seconds.
SHUTDOWN_CLEANUP_SECONDS = 10.0
MOVE_GAP_SECONDS = 0.25

LINK_CLAIM_PATH = "/api/discord/link/claim"
LINK_UNAVAILABLE_MESSAGE = "The island could not be reached — try again."


def _backoff(failures: int, base: float, cap: float) -> float:
    """base, 2×base, 4×base … capped. `failures` counts from 1."""
    # The exponent is clamped too: 2**1100 does not fit in a float.
    return min(cap, base * 2 ** min(max(failures - 1, 0), 16))


class ConfigurationError(RuntimeError):
    """The process or Discord server is missing required configuration."""


class SurvivorAPIError(RuntimeError):
    """A request to the Survivor server failed."""

    def __init__(
        self,
        status: int,
        path: str,
        detail: str,
        *,
        user_message: str | None = None,
    ):
        super().__init__(f"Survivor API {status} for {path}: {detail}")
        self.status = status
        self.path = path
        # Always non-empty — for a dropped connection it is aiohttp's own
        # wording — so it belongs in the log, never in front of a player.
        self.detail = detail
        # Set only when the server refused a request with a JSON sentence
        # written for a person: a 4xx such as "that code has expired". A
        # refused /link shows it to whoever ran the command; swallowing it
        # would leave them with "something went wrong" and no idea what to do.
        self.user_message = user_message


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"missing required environment variable {name}")
    return value


def _snowflake(name: str) -> int:
    value = _required(name)
    if not value.isdigit() or int(value) <= 0:
        raise ConfigurationError(f"{name} must be a positive Discord ID")
    return int(value)


def _boolean(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name} must be true/false, yes/no, on/off, or 1/0"
    )


def _base_url() -> str:
    value = os.environ.get(
        "SURVIVOR_BASE_URL", "http://127.0.0.1:8080"
    ).strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(
            "SURVIVOR_BASE_URL must be an absolute http or https URL"
        )
    if parsed.username or parsed.password:
        raise ConfigurationError("SURVIVOR_BASE_URL must not contain credentials")
    return value


@dataclass(frozen=True)
class BotConfig:
    token: str
    guild_id: int
    channel_ids: dict[str, int]
    base_url: str
    access_code: str
    mute_during_voting: bool

    @classmethod
    def from_environment(cls) -> "BotConfig":
        channel_ids: dict[str, int] = {}
        for place, name in CHANNEL_ENV.items():
            if place in OPTIONAL_PLACES and not os.environ.get(name, "").strip():
                LOG.warning(
                    "%s is not set: snuffed players will not be moved to %s",
                    name, place,
                )
                continue
            channel_ids[place] = _snowflake(name)
        if len(set(channel_ids.values())) != len(channel_ids):
            raise ConfigurationError("the Discord channel IDs must be unique")
        return cls(
            # The token is deliberately treated as an opaque string. Do not add
            # format validation: Discord can change its token format at any time.
            token=_required("DISCORD_BOT_TOKEN"),
            guild_id=_snowflake("DISCORD_GUILD_ID"),
            channel_ids=channel_ids,
            base_url=_base_url(),
            access_code=os.environ.get("SURVIVOR_ACCESS_CODE", "").strip(),
            mute_during_voting=_boolean("DISCORD_MUTE_DURING_VOTING", False),
        )


class SurvivorAPI:
    """Small authenticated client for the server endpoints used by the bot."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self._authenticated = False
        self._auth_failures = 0
        self._auth_retry_at = 0.0
        self._auth_error: SurvivorAPIError | None = None

    async def open(self) -> None:
        """Create the HTTP session. Deliberately makes no request.

        The access cookie is fetched by the first real call instead, from the
        poll loop, which backs off. Authenticating here made an island that
        was still starting — redeploy.sh bounces the server and the bot
        together — a crash at boot, and launchd's restart a fresh Discord
        login on top of it.
        """
        if self.session is not None:
            return
        timeout = aiohttp.ClientTimeout(total=15)
        # unsafe=True is intentional: aiohttp otherwise refuses cookies from the
        # documented local development URL, http://127.0.0.1:8080.
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            cookie_jar=cookie_jar,
            headers={"User-Agent": "survivor-discord-bot/1.0"},
        )

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None
        self._authenticated = False

    async def authenticate(self) -> None:
        if self.session is None:
            raise RuntimeError("Survivor API session is not open")
        path = "/api/access"
        # The access gate allows ten attempts a minute per client IP, and
        # behind the tunnel that IP is the host's whole house. A rotated code
        # presented at poll speed would lock everyone at home out of the
        # island, so after a refusal stay away for a while. Only an answer
        # from the island itself counts: a dropped connection or a 5xx from
        # the tunnel while the server restarts never reached the gate, and is
        # left to the poll loop's own backoff.
        if self._auth_error is not None and time.monotonic() < self._auth_retry_at:
            last = self._auth_error
            raise SurvivorAPIError(
                last.status, path,
                f"{last.detail} (waiting before presenting the code again)",
            )
        self._authenticated = False
        try:
            status, payload, detail = await self._raw_request(
                "POST", path, json_body={"code": self.config.access_code}
            )
            if status < 200 or status >= 300:
                raise SurvivorAPIError(status, path, detail)
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise SurvivorAPIError(
                    status, path, "access response was not successful")
        except SurvivorAPIError as exc:
            if 0 < exc.status < 500:
                self._auth_failures += 1
                self._auth_error = exc
                self._auth_retry_at = time.monotonic() + _backoff(
                    self._auth_failures, AUTH_RETRY_SECONDS, ERROR_RETRY_MAX_SECONDS)
            raise
        self._authenticated = True
        self._auth_failures = 0
        self._auth_error = None
        self._auth_retry_at = 0.0
        LOG.info("authenticated with Survivor server at %s", self.config.base_url)

    async def get(self, path: str) -> dict[str, Any]:
        """GET JSON, re-authenticating and retrying exactly once after a 401."""
        status, payload, detail = await self._authorized_request("GET", path)
        if status < 200 or status >= 300:
            raise SurvivorAPIError(status, path, detail)
        if not isinstance(payload, dict):
            raise SurvivorAPIError(status, path, "expected a JSON object")
        return payload

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST JSON, with the same one-shot re-auth as `get`.

        The bot writes exactly one thing, through exactly one endpoint: a
        Discord account bound to a link code somebody is holding on a phone.
        It cannot reach a game through this.
        """
        status, payload, detail = await self._authorized_request(
            "POST", path, json_body=body)
        if status < 200 or status >= 300:
            # A 4xx here is usually a wrong or stale code, and the message is
            # meant to be read by the person who typed it. A 401 is the gate
            # refusing the bot, and anything else (a 5xx, the tunnel's HTML
            # error page) is ours to worry about, not theirs.
            user_message = None
            if 400 <= status < 500 and status != 401 and isinstance(payload, dict):
                message = payload.get("message")
                if isinstance(message, str) and message.strip():
                    user_message = message
            raise SurvivorAPIError(status, path, detail, user_message=user_message)
        if not isinstance(payload, dict):
            raise SurvivorAPIError(status, path, "expected a JSON object")
        return payload

    async def _authorized_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any, str]:
        if self.session is None:
            raise RuntimeError("Survivor API session is not open")
        for attempt in range(2):
            if not self._authenticated:
                await self.authenticate()
            status, payload, detail = await self._raw_request(
                method, path, json_body=json_body)
            if status != 401:
                return status, payload, detail
            # The cookie is derived from the access code, so it dies whenever
            # the host rotates the code.
            self._authenticated = False
            if attempt == 0:
                LOG.warning("Survivor access cookie expired; authenticating again")
        return status, payload, detail

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any, str]:
        assert self.session is not None
        url = f"{self.config.base_url}{path}"
        try:
            async with self.session.request(method, url, json=json_body) as response:
                body = await response.text()
                try:
                    payload = json.loads(body) if body else None
                except json.JSONDecodeError:
                    payload = None
                detail = _response_detail(payload, body)
                return response.status, payload, detail
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise SurvivorAPIError(0, path, str(exc)) from exc


def _response_detail(payload: Any, body: str) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    clean = " ".join(body.split())
    return clean[:300] if clean else "empty response"


def _validate_active_games(payload: dict[str, Any]) -> list[dict[str, Any]]:
    games = payload.get("games")
    if not isinstance(games, list):
        raise SurvivorAPIError(200, "/api/voice/active", "missing games list")
    valid: list[dict[str, Any]] = []
    for item in games:
        if not isinstance(item, dict) or not isinstance(item.get("gameId"), str):
            raise SurvivorAPIError(200, "/api/voice/active", "invalid game entry")
        # Optional: an older server neither sends it nor ranks the list. A
        # value that is not a number is dropped rather than refused, so the
        # bot still mirrors — it just will not trust that ordering.
        last_activity = item.get("lastActivity")
        if "lastActivity" in item and (
            isinstance(last_activity, bool)
            or not isinstance(last_activity, (int, float))
            or not math.isfinite(last_activity)
        ):
            LOG.warning("ignoring invalid lastActivity %r for game %s",
                        last_activity, item["gameId"])
            del item["lastActivity"]
        valid.append(item)
    return valid


def _ranked(games: list[dict[str, Any]]) -> bool:
    """Whether the server ordered `/api/voice/active` most relevant first.

    A server that sends `lastActivity` ranks the list (live games ahead of
    lobbies, then most recent). An older one sorts by gameId, which says
    nothing about which table is tonight's, so its order is not worth
    switching games over.
    """
    return all("lastActivity" in game for game in games)


def _validate_plan(payload: dict[str, Any], game_id: str) -> dict[str, Any]:
    if payload.get("gameId") != game_id:
        raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "gameId mismatch")
    version = payload.get("version")
    policy = payload.get("policy")
    places = payload.get("places")
    if not isinstance(version, str) or not version:
        raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "missing version")
    if not isinstance(policy, dict) or not isinstance(policy.get("open"), list):
        raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "invalid policy")
    if not isinstance(places, list):
        raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "invalid places")

    by_key: dict[str, dict[str, Any]] = {}
    for place in places:
        if not isinstance(place, dict):
            raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "invalid place")
        key = place.get("key")
        if key not in PLACE_KEYS:
            # A place this build has never heard of. Refusing the whole plan
            # would take the bot down for every game until it is restarted, so
            # skip the room and mirror the ones we do know. Exile Island was
            # exactly this skew; the next one should cost nothing.
            LOG.warning("ignoring unknown place %r in plan for %s", key, game_id)
            continue
        if key in by_key:
            raise SurvivorAPIError(
                200, f"/api/voice/plan/{game_id}", f"duplicate place key {key!r}"
            )
        if not isinstance(place.get("players"), list):
            raise SurvivorAPIError(
                200, f"/api/voice/plan/{game_id}", f"invalid players for {key}"
            )
        by_key[key] = place
    # Optional places may legitimately be absent — an older server does not
    # know Exile Island exists. Missing *required* rooms is still a broken plan.
    missing = set(PLACE_KEYS) - OPTIONAL_PLACES - set(by_key)
    if missing:
        raise SurvivorAPIError(
            200, f"/api/voice/plan/{game_id}", f"missing places: {sorted(missing)}"
        )

    forced = policy.get("forced")
    if forced is not None and forced not in PLACE_KEYS:
        raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "invalid forced place")
    open_known = [key for key in policy["open"] if key in PLACE_KEYS]
    if not open_known:
        raise SurvivorAPIError(200, f"/api/voice/plan/{game_id}", "invalid open place")
    policy["open"] = open_known
    if forced is not None and forced not in policy["open"]:
        raise SurvivorAPIError(
            200, f"/api/voice/plan/{game_id}", "forced place is not open"
        )
    return payload


def _activity_note(game: dict[str, Any]) -> str:
    """' (last active 3 min ago)' for the log, when the server says."""
    last_activity = game.get("lastActivity")
    if last_activity is None:
        return ""
    minutes = max(0, int((time.time() - last_activity) // 60))
    return f" (last active {minutes} min ago)"


def _is_voting_state(state: dict[str, Any]) -> bool:
    """Return whether the game is in an actual secret-ballot subphase."""
    phase = state.get("phase")
    if phase == "tribal_council":
        current_vote = state.get("currentVote")
        return isinstance(current_vote, dict) and current_vote.get("phase") == "voting"
    if phase == "final_tribal":
        final_tribal = state.get("finalTribal")
        return isinstance(final_tribal, dict) and final_tribal.get("phase") == "voting"
    return False


class SurvivorDiscordClient(discord.Client):
    def __init__(self, config: BotConfig):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.config = config
        self.api = SurvivorAPI(config)
        self.tree = discord.app_commands.CommandTree(self)
        self.guild: discord.Guild | None = None
        self.channels: dict[str, discord.VoiceChannel] = {}
        self._ready_for_reconcile = asyncio.Event()
        self._wake_reconcile = asyncio.Event()
        self._poll_task: asyncio.Task[None] | None = None
        self._config_task: asyncio.Task[None] | None = None
        self._shutdown_task: asyncio.Task[None] | None = None
        self._current_game_id: str | None = None
        self._last_plan_version: str | None = None
        self._last_mute_state = False
        self._force_reconcile = True
        self._muted_member_ids: set[int] = set()
        # Discord accounts linked in the watched (or just released) game: the
        # only members whose Connect denies the bot will ever lift.
        self._attributable_ids: set[int] = set()
        self._next_discovery_at = 0.0
        self._switch_candidate: str | None = None
        self._idle_logged = False
        self._multiple_games_signature: tuple[str, frozenset[str]] | None = None
        self._poll_failures = 0
        self._poll_failure_signature: str | None = None
        self._config_problem: str | None = None
        self._commands_synced = False
        self._closing = False

    async def setup_hook(self) -> None:
        # No network here: an island that is down at boot is the poll loop's
        # problem, retried with backoff, not a crash for launchd to restart.
        await self.api.open()
        self._register_commands()
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="survivor-voice-plan-poller"
        )

    def _register_commands(self) -> None:
        """`/link`, and nothing else the bot will ever accept from a person."""

        @self.tree.command(
            name="link",
            description="Link your Discord account to the Survivor app",
        )
        @discord.app_commands.describe(code="The code the app is showing you, e.g. PALM-472")
        async def link(interaction: discord.Interaction, code: str) -> None:
            # Who ran this is the whole point: Discord tells us, so nobody
            # types a snowflake and no username is matched. Ephemeral because
            # a link code is nobody else's business.
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                payload = await self.api.post(
                    LINK_CLAIM_PATH,
                    {"code": code, "discordUserId": str(interaction.user.id)},
                )
                message = payload.get("message") or "Linked."
            except SurvivorAPIError as exc:
                # Only the claim's own refusal is worth showing; a dropped
                # connection or a gateway error page is not the player's to
                # read, and the log keeps the detail.
                message = (
                    exc.user_message
                    if exc.path == LINK_CLAIM_PATH and exc.user_message
                    else LINK_UNAVAILABLE_MESSAGE
                )
                LOG.warning("link claim failed for %s: %s", interaction.user, exc)
            await interaction.followup.send(message, ephemeral=True)

    async def on_ready(self) -> None:
        if self._closing:
            return
        # A gateway session that could not RESUME arrives with new guild and
        # channel objects. Hold the poller until they have been resolved again.
        self._ready_for_reconcile.clear()
        if await self._configure():
            return
        # Exiting here handed the fault to launchd, which restarted the bot
        # every ThrottleInterval: a fresh gateway IDENTIFY each time, thousands
        # a day, for a problem only somebody editing the Discord server can
        # fix. Stay connected, say it once, and look again periodically.
        if self._config_task is None or self._config_task.done():
            self._config_task = asyncio.create_task(
                self._recheck_configuration(), name="survivor-config-recheck"
            )

    async def _configure(self) -> bool:
        """Resolve the guild and channels; True once the poller may run."""
        try:
            await self._resolve_discord_configuration()
            # A previous process could have died after applying a server mute.
            # Clean that up before reading the current plan; the poller will
            # reapply a voting mute if the optional policy still calls for it.
            # (A no-op unless the voting mute is turned on.)
            await self._unmute_everyone_in_managed_channels(
                "Survivor: startup mute safety cleanup"
            )
            # There is deliberately no startup sweep of Exile Island bars. A
            # fresh process cannot tell its own old denies from a moderator's,
            # and it does not need to: the first reconciliation of the live
            # game readmits every linked player it does not bar.
        except Exception as exc:
            problem = f"{type(exc).__name__}: {exc}"
            if problem != self._config_problem:
                self._config_problem = problem
                if isinstance(exc, ConfigurationError):
                    LOG.error(
                        "Discord configuration is incomplete — %s. Not mirroring; "
                        "checking again every %.0fs", exc, CONFIG_RECHECK_SECONDS,
                    )
                else:
                    LOG.exception(
                        "Discord configuration validation failed; checking again "
                        "every %.0fs", CONFIG_RECHECK_SECONDS,
                    )
            return False

        if self._config_problem is not None:
            LOG.info("Discord configuration is now complete")
            self._config_problem = None
        self._force_reconcile = True
        self._ready_for_reconcile.set()
        self._wake_reconcile.set()
        LOG.info("ready as %s (guild %s)", self.user, self.guild)
        return True

    async def _recheck_configuration(self) -> None:
        while not self._closing:
            await asyncio.sleep(CONFIG_RECHECK_SECONDS)
            # A later on_ready may have succeeded on its own in the meantime.
            if self._closing or self._ready_for_reconcile.is_set():
                return
            if await self._configure():
                return

    async def on_resumed(self) -> None:
        LOG.info("Discord gateway session resumed; forcing voice reconciliation")
        self._force_reconcile = True
        self._wake_reconcile.set()

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # Mute, deafen, camera and stream events keep the same channel and should
        # not wake the server poller. Bot moves do wake it once; reconciliation
        # is idempotent and confirms the move landed.
        if before.channel == after.channel:
            return
        if member.bot or member.guild.id != self.config.guild_id:
            return
        self._force_reconcile = True
        self._wake_reconcile.set()

    async def close(self) -> None:
        # The SIGTERM handler and discord.py's own teardown both land here.
        # Every caller waits on the one shutdown, so a second call cannot
        # return early and let asyncio.run cancel the cleanup half-way.
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._shutdown(), name="survivor-shutdown"
            )
        await self._shutdown_task

    async def _shutdown(self) -> None:
        self._closing = True
        self._ready_for_reconcile.set()
        self._wake_reconcile.set()
        if self._config_task is not None:
            self._config_task.cancel()
            self._config_task = None
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            except Exception:
                LOG.exception("voice plan poller failed while stopping")
            self._poll_task = None
        # The bot is a mirror, not a dependency. Once it stops nothing will
        # lift a Tribal Council lock or readmit a snuffed player, and the game
        # is meant to carry on with people moving themselves — so hand the
        # rooms back first. A restart (redeploy) puts back whatever the live
        # game still calls for within one poll. Bounded, because launchd's
        # SIGKILL follows SIGTERM whether or not Discord has answered.
        try:
            await asyncio.wait_for(
                self._shutdown_cleanup(), timeout=SHUTDOWN_CLEANUP_SECONDS
            )
        except asyncio.TimeoutError:
            LOG.warning("shutdown cleanup did not finish within %.0fs",
                        SHUTDOWN_CLEANUP_SECONDS)
        except Exception:
            LOG.exception("shutdown cleanup failed")
        await self.api.close()
        await super().close()

    async def _shutdown_cleanup(self) -> None:
        if self.guild is None or not self.channels:
            return
        await self._release_game("Survivor: bot shutting down")
        await self._unmute_everyone_in_managed_channels(
            "Survivor: shutdown mute safety cleanup"
        )
        LOG.info("released Discord channels for shutdown")

    async def _resolve_discord_configuration(self) -> None:
        guild = self.get_guild(self.config.guild_id)
        if guild is None:
            raise ConfigurationError(
                f"bot cannot see configured guild {self.config.guild_id}"
            )

        # Report every problem at once. Failing on the first channel makes
        # fixing a Discord server a round trip per room, and the fix is nearly
        # always the same one applied everywhere.
        channels: dict[str, discord.VoiceChannel] = {}
        faults: list[str] = []
        for place, channel_id in self.config.channel_ids.items():
            channel = guild.get_channel(channel_id)
            if channel is None:
                faults.append(
                    f"{CHANNEL_ENV[place]}={channel_id} is not visible in guild {guild.id}"
                )
                continue
            if not isinstance(channel, discord.VoiceChannel):
                faults.append(f"{channel_id} for {place} is not a voice channel")
                continue
            channels[place] = channel
        if faults:
            raise ConfigurationError("; ".join(faults))

        bot_member = guild.me
        if bot_member is None:
            raise ConfigurationError("bot member record is unavailable in the guild")

        for place, channel in channels.items():
            category = channel.category
            category_connect = None
            if category is not None:
                category_connect = category.overwrites_for(guild.default_role).connect
            LOG.info(
                "channel %-20s id=%s name=%r users=%d limit=%d category=%r "
                "category_everyone_connect=%r",
                place,
                channel.id,
                channel.name,
                len(channel.voice_states),
                channel.user_limit,
                category.name if category else None,
                category_connect,
            )
            if channel.user_limit != 0:
                LOG.warning(
                    "CHANNEL MISCONFIGURED: %s has user_limit=%d; set it to 0",
                    channel.name,
                    channel.user_limit,
                )

            permissions = channel.permissions_for(bot_member)
            everyone_overwrite = channel.overwrites_for(guild.default_role)
            required = {
                "view_channel": permissions.view_channel,
                "manage_roles": permissions.manage_roles,
            }
            # A CONNECT deny written by this bot applies to @everyone and can
            # make Connect/Move appear false for the bot until it clears that
            # deny. Reconciliation opens destinations before moving into them.
            if everyone_overwrite.connect is not False:
                required["connect"] = permissions.connect
                required["move_members"] = permissions.move_members
            if self.config.mute_during_voting:
                required["mute_members"] = permissions.mute_members
            missing = [name for name, allowed in required.items() if not allowed]
            if missing:
                faults.append(
                    f"{channel.name}: needs {', '.join(missing)}"
                )

        if faults:
            raise ConfigurationError(
                "the bot role is missing channel permissions — "
                + "; ".join(faults)
                + ". Grant them on the category and sync, or per channel "
                  "(Discord calls manage_roles 'Manage Permissions')"
            )

        self.guild = guild
        self.channels = channels
        await self._sync_commands(guild)

    async def _sync_commands(self, guild: discord.Guild) -> None:
        """Publish `/link` to this one guild, and say plainly if we cannot.

        Guild-scoped rather than global: a global command can take an hour to
        appear, and there is exactly one server. Registration needs the
        `applications.commands` scope on the invite — a bot added with only
        `bot` connects, runs, mirrors voice perfectly, and simply has no slash
        commands, with nothing anywhere saying why. Hence the loud failure.

        Once per process: the command set cannot change without a restart,
        and Discord rate-limits registration, so a gateway reconnect (which
        fires on_ready again) has nothing to publish. A failure is retried on
        the next on_ready, since nothing was registered.
        """
        if self._commands_synced:
            return
        self.tree.copy_global_to(guild=guild)
        try:
            synced = await self.tree.sync(guild=guild)
        except discord.Forbidden:
            LOG.error(
                "cannot register slash commands in guild %s — the bot was "
                "invited without the applications.commands scope. Re-invite it "
                "with both `bot` and `applications.commands`; /link will not "
                "appear until you do. Voice mirroring is unaffected.",
                guild.id,
            )
            return
        except discord.HTTPException as exc:
            LOG.error("slash command registration failed: %s", exc)
            return
        self._commands_synced = True
        LOG.info("registered %d slash command(s): %s",
                 len(synced), ", ".join(f"/{c.name}" for c in synced) or "none")

    async def _poll_loop(self) -> None:
        try:
            while not self._closing:
                await self._ready_for_reconcile.wait()
                if self._closing:
                    break
                # Clear before polling so a voice event that arrives during the
                # reconciliation remains set and causes an immediate follow-up.
                self._wake_reconcile.clear()
                try:
                    delay = await self._poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    delay = self._poll_failed(exc)
                else:
                    self._poll_succeeded()

                try:
                    await asyncio.wait_for(self._wake_reconcile.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self._unmute_everyone_in_managed_channels(
                "Survivor: poller exit mute safety cleanup"
            )

    def _poll_failed(self, exc: Exception) -> float:
        """Log a failed poll and return how long to wait before the next one.

        An island that is down tends to stay down for a while. Retrying every
        five seconds with a full traceback each time buried the log under
        thousands of identical stacks, so back off to five minutes and print
        the traceback once per new kind of failure, one line per retry after.
        A voice event still wakes the poller early, so a recovered server is
        noticed as soon as anybody moves.
        """
        self._poll_failures += 1
        delay = _backoff(
            self._poll_failures, ERROR_RETRY_SECONDS, ERROR_RETRY_MAX_SECONDS)
        signature = f"{type(exc).__name__}: {exc}"
        if signature != self._poll_failure_signature:
            self._poll_failure_signature = signature
            LOG.error("voice plan poll failed; retrying in %.0fs", delay,
                      exc_info=exc)
        else:
            LOG.warning("voice plan poll still failing (%d in a row): %s; "
                        "retrying in %.0fs", self._poll_failures, signature, delay)
        return delay

    def _poll_succeeded(self) -> None:
        if self._poll_failures:
            LOG.info("voice plan polling recovered after %d failed attempt(s)",
                     self._poll_failures)
        self._poll_failures = 0
        self._poll_failure_signature = None

    async def _poll_once(self) -> float:
        # Every channel that *was* configured must have resolved. Exile Island
        # is optional, so comparing against PLACE_KEYS would idle the bot
        # forever on a server that has not made that channel yet.
        if self.guild is None or len(self.channels) != len(self.config.channel_ids):
            return ERROR_RETRY_SECONDS

        if (self._current_game_id is None
                or time.monotonic() >= self._next_discovery_at):
            idle_delay = await self._discover()
            if idle_delay is not None:
                return idle_delay

        game_id = self._current_game_id
        assert game_id is not None
        try:
            plan = _validate_plan(
                await self.api.get(f"/api/voice/plan/{game_id}"), game_id
            )
        except SurvivorAPIError as exc:
            if exc.status == 404:
                LOG.info("game %s disappeared; releasing channel locks", game_id)
                await self._release_game("Survivor: game no longer exists")
                return PLAN_POLL_SECONDS
            raise

        ghosts, living = self._linked_by_state(plan)
        self._attributable_ids |= ghosts | living

        # A lobby can outlive the linked player who made it discoverable. Once
        # that player leaves, the game still exists and its voice plan remains
        # perfectly valid, so the old 404/finished release paths never run.
        # Holding on to it forever prevents active-game discovery from seeing
        # the next table. Release immediately and let the following poll choose
        # from /api/voice/active again.
        linked_players = self._linked_players(plan)
        if not linked_players:
            LOG.info(
                "game %s has no linked players; returning to active-game discovery",
                game_id,
            )
            await self._release_game("Survivor: no linked players remain in the game")
            return PLAN_POLL_SECONDS

        version_changed = plan["version"] != self._last_plan_version
        if version_changed or self._force_reconcile:
            reconciled = await self._reconcile(plan)
            self._force_reconcile = not reconciled
            if reconciled:
                self._last_plan_version = plan["version"]

        if self.config.mute_during_voting:
            desired_mute = False
            try:
                state = await self.api.get(f"/api/game/{game_id}/state")
                desired_mute = _is_voting_state(state)
            except SurvivorAPIError:
                # Silence must fail open. A temporary server problem should not
                # strand friends in a server-muted state.
                LOG.exception("cannot confirm voting phase; failing open to unmuted")
            if desired_mute != self._last_mute_state or self._force_reconcile:
                if await self._set_vote_mute(linked_players, desired_mute):
                    self._last_mute_state = desired_mute

        if plan.get("phase") == "finished" and not self._force_reconcile:
            LOG.info("game %s finished; returning to active-game discovery", game_id)
            self._forget_game()

        return PLAN_POLL_SECONDS

    async def _discover(self) -> float | None:
        """Choose the game to mirror; return a delay if there is none.

        Runs on every poll while idle and every IDLE_POLL_SECONDS while
        watching. Only looking up again notices that tonight's table has
        overtaken one the friends abandoned last night: an unfinished game
        stays listed for a day, and nothing about its own plan changes.
        """
        games = _validate_active_games(await self.api.get("/api/voice/active"))
        self._next_discovery_at = time.monotonic() + IDLE_POLL_SECONDS
        if not games:
            if self._current_game_id is not None:
                LOG.info("game %s is no longer active; releasing it",
                         self._current_game_id)
                await self._release_game("Survivor: game is no longer active")
            if not self._idle_logged:
                LOG.info("no active linked Survivor game; waiting")
                await self._unlock_all_channels("Survivor: no active game")
                await self._set_vote_mute([], False)
                self._idle_logged = True
            return IDLE_POLL_SECONDS

        self._idle_logged = False
        game_ids = [game["gameId"] for game in games]
        top = game_ids[0]
        current = self._current_game_id
        if current == top:
            self._switch_candidate = None
        elif current is not None and current not in game_ids:
            LOG.info("game %s is no longer active; switching to %s", current, top)
            await self._release_game("Survivor: switching to the active game")
        elif current is not None and _ranked(games):
            # Still listed but outranked. One look is not enough: lastActivity
            # moves whenever anybody touches a game, so a single poke at last
            # night's table would otherwise drag everyone's voice across and
            # straight back. Switch when the same game leads two looks running.
            # (An unranked list from an older server never gets this far.)
            if self._switch_candidate != top:
                self._switch_candidate = top
            else:
                LOG.info("game %s has overtaken %s; switching", top, current)
                await self._release_game("Survivor: switching to the active game")

        if self._current_game_id is None:
            self._switch_candidate = None
            self._current_game_id = top
            self._last_plan_version = None
            self._last_mute_state = False
            self._force_reconcile = True
            self._attributable_ids = set()
            LOG.info("watching Survivor game %s%s", top,
                     _activity_note(games[0]))

        others = frozenset(game_ids) - {self._current_game_id}
        signature = (self._current_game_id, others) if others else None
        if signature is not None and signature != self._multiple_games_signature:
            LOG.warning(
                "multiple active games found; mirroring %s and ignoring %s",
                self._current_game_id, ", ".join(sorted(others)),
            )
        self._multiple_games_signature = signature
        return None

    async def _release_game(self, reason: str) -> None:
        """Let go of the watched game: open its doors, lift its mutes and bars.

        The bars are lifted for the released game's linked players only, so
        this must run before the next game resets `_attributable_ids`.
        """
        if self.guild is not None:
            await self._unlock_all_channels(reason)
            await self._set_vote_mute([], False)
            await self._clear_every_member_bar(reason)
        self._forget_game()

    def _forget_game(self) -> None:
        self._current_game_id = None
        self._last_plan_version = None
        self._last_mute_state = False
        self._force_reconcile = True
        self._switch_candidate = None

    async def _reconcile(self, plan: dict[str, Any]) -> bool:
        success = True
        assignments = self._assignments(plan)
        policy = plan["policy"]
        forced = policy.get("forced")

        # A channel locked during the previous phase also denies the API user
        # Connect there. Open every valid destination before attempting moves;
        # only then close the doors that the new plan marks unavailable.
        destinations = {forced} if forced is not None else set(policy["open"])
        # Exile Island is a destination whenever anybody is on it, whatever the
        # table's policy says — the table's policy is the living's.
        destinations |= {place["key"] for place in plan["places"] if place["players"]}
        for place_key in self.channels:
            if place_key in destinations:
                if not await self._set_channel_lock(place_key, False):
                    success = False

        # Movement deliberately precedes locks. Discord does not promise that a
        # CONNECT deny ejects anyone already inside a channel.
        for user_id, place_key, label, player_name in assignments:
            if not await self._move_member(user_id, place_key, label, player_name):
                success = False

        if forced is not None:
            for place_key in self.channels:
                # Exile is never locked to @everyone: the snuffed are there
                # during a council the living are all standing in.
                locked = place_key not in (forced, GHOST_PLACE)
                if not await self._set_channel_lock(place_key, locked):
                    success = False
        else:
            for place_key in policy["open"]:
                if not await self._set_channel_lock(place_key, False):
                    success = False

        if not await self._reconcile_ghost_locks(plan, forced):
            success = False

        LOG.info(
            "reconciled game=%s phase=%s version=%s forced=%s linked=%d success=%s",
            plan.get("gameId"),
            plan.get("phase"),
            plan.get("version"),
            forced,
            len(assignments),
            success,
        )
        return success

    def _assignments(
        self, plan: dict[str, Any]
    ) -> list[tuple[int, str, str, str]]:
        result: list[tuple[int, str, str, str]] = []
        assigned: dict[int, str] = {}
        for place in plan["places"]:
            place_key = place["key"]
            label = str(place.get("label") or place_key)
            for player in place["players"]:
                if not isinstance(player, dict):
                    LOG.warning("skipping malformed player in %s", place_key)
                    continue
                raw_user_id = player.get("discordUserId")
                if raw_user_id is None:
                    continue
                if not isinstance(raw_user_id, str) or not raw_user_id.isdigit():
                    LOG.warning(
                        "skipping %r: invalid discordUserId %r",
                        player.get("name"),
                        raw_user_id,
                    )
                    continue
                user_id = int(raw_user_id)
                if user_id in assigned:
                    LOG.error(
                        "Discord user %s is linked more than once (%s and %s); "
                        "keeping the first assignment",
                        user_id,
                        assigned[user_id],
                        place_key,
                    )
                    continue
                assigned[user_id] = place_key
                result.append(
                    (user_id, place_key, label, str(player.get("name") or user_id))
                )
        return result

    def _linked_players(self, plan: dict[str, Any]) -> list[int]:
        return [assignment[0] for assignment in self._assignments(plan)]

    @staticmethod
    def _linked_by_state(plan: dict[str, Any]) -> tuple[set[int], set[int]]:
        """Linked Discord ids, split into (ghosts, living)."""
        ghosts: set[int] = set()
        living: set[int] = set()
        for place in plan["places"]:
            for player in place["players"]:
                raw = player.get("discordUserId")
                if not isinstance(raw, str) or not raw.isdigit():
                    continue
                (ghosts if player.get("eliminated") else living).add(int(raw))
        return ghosts, living - ghosts

    async def _reconcile_ghost_locks(
        self, plan: dict[str, Any], forced: str | None
    ) -> bool:
        """Keep snuffed players out of the breakout rooms, not merely out of
        them right now.

        Moving a ghost back to the Camp Fire is a one-off: the plan version
        only moves when the *game* changes, so nothing would notice them
        walking straight back into The Beach afterwards. A per-member Connect
        deny is what Discord will actually enforce at the door.

        Only linked players in this game are ever touched, and only their
        denies — an allow written by an administrator is left alone, exactly as
        the @everyone lock does.
        """
        ghosts, living = self._linked_by_state(plan)
        everyone_linked = ghosts | living
        success = True
        # With no Exile channel configured there is nowhere to send them, and
        # barring the rooms anyway would leave a snuffed player unable to join
        # anything at all. Clear every bar instead and behave as before.
        if GHOST_PLACE not in self.channels:
            ghosts = set()
        for place_key in self.channels:
            # While the tribe is called together nobody is anywhere else and
            # the @everyone lock already says so, so bar nobody individually —
            # which also clears yesterday's denies the moment camp reopens.
            barred = (
                ghosts
                if forced is None and place_key not in (GHOST_PLACE, COUNCIL_PLACE)
                else set()
            )
            for user_id in everyone_linked:
                if not await self._set_member_lock(
                    place_key, user_id, locked=user_id in barred
                ):
                    success = False
        return success

    async def _set_member_lock(
        self, place_key: str, user_id: int, locked: bool
    ) -> bool:
        assert self.guild is not None
        channel = self.channels[place_key]
        # Read the overwrite by id. Without the members intent only people in
        # voice are cached, and for anyone else channel.overwrites hands back
        # a bare discord.Object rather than a Member.
        overwrite = channel.overwrites_for(discord.Object(id=user_id))
        if locked and overwrite.connect is False:
            return True
        if not locked and overwrite.connect is not False:
            return True   # nothing of ours to clear (and never erase an allow)
        member = self.guild.get_member(user_id)
        if member is None and locked:
            # Not cached and not worth a fetch per channel per reconcile: an
            # absent member cannot be in a voice channel to bar, and joining
            # one forces a reconcile that bars them then.
            return True
        if member is None:
            # Readmitting cannot wait for that. The snuffed player who gave up
            # and left voice is exactly the one who is not cached, and a deny
            # skipped here bars them from The Beach for good. set_permissions
            # needs a real Member, so fetch one.
            try:
                member = await self.guild.fetch_member(user_id)
            except discord.NotFound:
                return True   # left the server; there is no door to open
            except discord.HTTPException as exc:
                LOG.error("cannot fetch Discord user %s to readmit them to %s: %s",
                          user_id, channel.name, exc)
                return False
        overwrite.connect = False if locked else None
        try:
            await channel.set_permissions(
                member,
                overwrite=None if overwrite.is_empty() else overwrite,
                reason=("Survivor: snuffed players do not join breakouts"
                        if locked else "Survivor: restore access after the game"),
            )
            LOG.info(
                "%s %s for %s", "barred" if locked else "readmitted",
                channel.name, member.display_name,
            )
            return True
        except discord.Forbidden as exc:
            LOG.error("cannot set member permissions for %s: %s", channel.name, exc)
        except discord.HTTPException as exc:
            LOG.error("failed to set member permissions for %s: %s", channel.name, exc)
        return False

    def _voice_channel_for_user(self, user_id: int) -> Any | None:
        if self.guild is None:
            return None
        for channel in (*self.guild.voice_channels, *self.guild.stage_channels):
            if user_id in channel.voice_states:
                return channel
        return None

    async def _member(self, user_id: int) -> discord.Member | None:
        assert self.guild is not None
        member = self.guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await self.guild.fetch_member(user_id)
        except discord.NotFound:
            LOG.warning("linked Discord user %s is not in guild %s", user_id, self.guild.id)
        except discord.Forbidden as exc:
            LOG.error("cannot fetch linked Discord user %s: %s", user_id, exc)
        except discord.HTTPException as exc:
            LOG.error("failed to fetch linked Discord user %s: %s", user_id, exc)
        return None

    async def _move_member(
        self, user_id: int, place_key: str, label: str, player_name: str
    ) -> bool:
        target = self.channels.get(place_key)
        if target is None:
            # An optional place with no channel configured. Nothing to move
            # anyone into, and the game does not care.
            return True
        current = self._voice_channel_for_user(user_id)
        if current is None:
            return True  # Not connected to voice is a normal state.
        if current.id == target.id:
            return True
        member = await self._member(user_id)
        if member is None:
            return False
        # Voice state can change while the REST member fetch is in flight.
        current = self._voice_channel_for_user(user_id)
        if current is None:
            return True
        if current.id == target.id:
            return True
        try:
            await member.move_to(target, reason=f"Survivor: {label}")
            LOG.info(
                "moved %s (%s) from %s to %s",
                player_name,
                user_id,
                current.name,
                target.name,
            )
        except discord.Forbidden as exc:
            LOG.error("cannot move %s (%s): %s", player_name, user_id, exc)
            return False
        except discord.HTTPException as exc:
            if exc.status == 400:
                LOG.info("%s (%s) left voice before the move", player_name, user_id)
                return True
            LOG.error("Discord failed to move %s (%s): %s", player_name, user_id, exc)
            return False
        await asyncio.sleep(MOVE_GAP_SECONDS)
        return True

    async def _set_channel_lock(self, place_key: str, locked: bool) -> bool:
        assert self.guild is not None
        channel = self.channels[place_key]
        overwrite = channel.overwrites_for(self.guild.default_role)
        desired = False if locked else None
        if locked and overwrite.connect is False:
            return True
        # An explicit allow already leaves the channel open. Do not erase an
        # administrator's allow just to replace it with inherited access.
        if not locked and overwrite.connect in {None, True}:
            return True
        overwrite.connect = desired
        reason = (
            "Survivor: Tribal Council channel lock"
            if locked
            else "Survivor: restore inherited channel access"
        )
        try:
            await channel.set_permissions(
                self.guild.default_role, overwrite=overwrite, reason=reason
            )
            LOG.info("%s channel %s", "locked" if locked else "unlocked", channel.name)
            return True
        except discord.Forbidden as exc:
            LOG.error("cannot change permissions for %s: %s", channel.name, exc)
        except discord.HTTPException as exc:
            LOG.error("failed to change permissions for %s: %s", channel.name, exc)
        return False

    async def _unlock_all_channels(self, reason: str) -> None:
        assert self.guild is not None
        for place_key, channel in self.channels.items():
            overwrite = channel.overwrites_for(self.guild.default_role)
            if overwrite.connect is not False:
                continue
            overwrite.connect = None
            try:
                await channel.set_permissions(
                    self.guild.default_role, overwrite=overwrite, reason=reason
                )
                LOG.info("unlocked %s after game release", place_key)
            except (discord.Forbidden, discord.HTTPException):
                LOG.exception("cannot release channel lock for %s", channel.name)

    async def _set_vote_mute(self, user_ids: list[int], muted: bool) -> bool:
        success = True
        targets = set(user_ids)
        if not muted:
            targets.update(self._muted_member_ids)
        for user_id in sorted(targets):
            member = await self._member(user_id) if self.guild is not None else None
            if member is None:
                success = False
                continue
            if self._voice_channel_for_user(user_id) is None:
                # Discord rejects server-mute edits for disconnected members.
                continue
            try:
                await member.edit(
                    mute=muted,
                    reason=(
                        "Survivor: secret ballot in progress"
                        if muted
                        else "Survivor: secret ballot complete"
                    ),
                )
                if muted:
                    self._muted_member_ids.add(user_id)
                else:
                    self._muted_member_ids.discard(user_id)
            except discord.Forbidden as exc:
                LOG.error("cannot %s %s: %s", "mute" if muted else "unmute", member, exc)
                success = False
            except discord.HTTPException as exc:
                if exc.status == 400:
                    LOG.info("%s left voice before mute state changed", member)
                else:
                    LOG.error("failed to change mute for %s: %s", member, exc)
                    success = False
            await asyncio.sleep(MOVE_GAP_SECONDS)
        if targets:
            LOG.info("voting mute=%s applied to %d linked members", muted, len(targets))
        return success

    async def _clear_every_member_bar(self, reason: str) -> None:
        """Drop the per-member Connect denies this bot can account for.

        Releasing a game must readmit its snuffed players: nothing will be
        left running to let them back into The Beach otherwise.

        Discord keeps no record of who wrote an overwrite, so the rule is
        deliberately narrow. A deny is the bot's to lift only when it sits on
        a Discord account linked in the game being released — the same
        accounts reconciliation bars and readmits. A moderator's deny on
        anybody else is never touched, and neither is an allow. The cost is a
        bar left by a process that died for a game that ended before it came
        back: that player is readmitted by the first reconciliation of the
        next game they are linked in, or by hand.
        """
        if self.guild is None or not self.channels or not self._attributable_ids:
            return
        for place_key in self.channels:
            for user_id in sorted(self._attributable_ids):
                await self._set_member_lock(place_key, user_id, locked=False)
        LOG.info("cleared linked players' channel bars (%s)", reason)

    async def _unmute_everyone_in_managed_channels(self, reason: str) -> None:
        if self.guild is None or not self.channels:
            return
        # With the voting mute off this bot never server-mutes anybody, so
        # every mute in these rooms belongs to a person or a moderator.
        if not self.config.mute_during_voting and not self._muted_member_ids:
            return
        user_ids: set[int] = set(self._muted_member_ids)
        for channel in self.channels.values():
            user_ids.update(channel.voice_states)
        for user_id in sorted(user_ids):
            member = await self._member(user_id)
            if member is None or self._voice_channel_for_user(user_id) is None:
                continue
            voice = member.voice
            if voice is not None and not voice.mute and user_id not in self._muted_member_ids:
                continue
            try:
                await member.edit(mute=False, reason=reason)
                self._muted_member_ids.discard(user_id)
            except discord.Forbidden as exc:
                LOG.error("mute safety cleanup forbidden for %s: %s", member, exc)
            except discord.HTTPException as exc:
                if exc.status != 400:
                    LOG.error("mute safety cleanup failed for %s: %s", member, exc)


def _configure_logging() -> None:
    level_name = os.environ.get("SURVIVOR_DISCORD_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ConfigurationError(
            f"SURVIVOR_DISCORD_LOG_LEVEL has unknown level {level_name!r}"
        )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def _run(client: SurvivorDiscordClient, token: str) -> None:
    """Client.run, plus a clean exit on SIGTERM.

    launchd stops a job with SIGTERM — every redeploy, every bootout. Python's
    default for it is to die on the spot, leaving Tribal Council locked and
    any voting mute in place with nothing running to lift them. Route it, and
    Ctrl-C, through close(), which releases the channels before disconnecting.
    """
    loop = asyncio.get_running_loop()
    stopping: set[asyncio.Task[None]] = set()

    def stop(signame: str) -> None:
        LOG.info("%s received; releasing Discord channels and shutting down",
                 signame)
        task = asyncio.create_task(client.close())
        stopping.add(task)   # keep a reference until it finishes
        task.add_done_callback(stopping.discard)

    installed = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop, sig.name)
            installed.append(sig)
        except (NotImplementedError, RuntimeError):
            pass   # no loop signal support here; Ctrl-C still interrupts

    try:
        async with client:
            await client.start(token, reconnect=True)
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)


def main() -> int:
    try:
        _configure_logging()
        config = BotConfig.from_environment()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    client = SurvivorDiscordClient(config)
    try:
        asyncio.run(_run(client, config.token))
    except discord.LoginFailure:
        LOG.error("Discord rejected DISCORD_BOT_TOKEN; rotate the token and restart")
        return 3
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
