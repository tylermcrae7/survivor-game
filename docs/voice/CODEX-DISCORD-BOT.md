# Build the Survivor Discord voice bot

**Audience:** an AI coding agent (Codex) building this from scratch.
**Everything the bot talks to already exists and works.** The game server, the
places model, and both clients are built, tested, and deployed. Your job is the
Discord half only. Do not modify anything outside the files listed in §7.

---

## 0. What you are building, in one paragraph

Six friends play a Survivor card game on their phones and browsers while talking
in Discord voice. The game server already tracks which **place** each player is
standing in — Camp Fire, The Beach, The Water Well, or Tribal Council — and the
players move themselves by tapping in the app. Your bot's entire job is to make
Discord match: poll the server, move each linked player into the voice channel
for their place, and lock the side channels while Tribal Council is in session.
The bot is a mirror. The game plays perfectly with the bot switched off; players
just have to move themselves in Discord by hand.

**The one hard constraint:** Discord does not let a bot pull someone into voice
who isn't already connected. Players join **Camp Fire** manually when the night
starts. After that the bot can move them freely. A player who never joins voice
is simply skipped — that is a normal state, not an error.

---

## 1. Create the Discord server (human does this once, ~5 minutes)

1. Discord → **＋** (Add a Server) → **Create My Own** → **For me and my friends**
   → name it e.g. *Survivor Island*.
2. Create **four voice channels** (not text). Exact names are yours to choose,
   but the bot maps by ID, not name, so record each ID.
   - 🔥 Camp Fire → `camp_fire`
   - 🏝 The Beach → `the_beach`
   - 💧 The Water Well → `the_water_well`
   - 🗳 Tribal Council → `tribal_council`
3. **Set every one of them to `user_limit = 0`** (Edit Channel → no user limit).
   Discord does not document whether Move Members bypasses a channel's user
   limit, so do not find out the hard way.
4. Invite the five friends. Each of them must **join Camp Fire voice at the
   start of a session** — see the constraint in §0.
5. To copy IDs: User Settings → **Advanced** → enable **Developer Mode**, then
   right-click (or long-press) any channel → **Copy Channel ID**. Same gesture on
   the server name gives the **Guild ID**, and on a person gives their **User ID**.

Each player also pastes their own **Discord user ID** into the Survivor app once:
**Settings → Discord user ID**. That is what links `TDawg` in the game to
`@tyler` in Discord. Without it, that player is invisible to the bot.

---

## 2. Create the bot application (human does this once, ~3 minutes)

1. <https://discord.com/developers/applications?new_application=true> → name it →
   **Create**.
2. **There is no "Add Bot" button any more** — new applications have a bot user
   enabled by default. Older tutorials are wrong about this.
3. Left sidebar → **Bot** → **Reset Token** → copy it. You cannot view it again.
4. **Do not enable any Privileged Gateway Intent.** This bot needs none (§4). If
   you enable one without ticking its portal toggle the gateway closes and
   `discord.py` raises `PrivilegedIntentsRequired` — under `KeepAlive` that
   becomes a silent crash-loop every ten seconds.
5. Left sidebar → **Installation** → Installation Contexts: **Guild Install**
   only → Install Link: **Discord Provided Link** → Default Install Settings →
   scope **`bot`** → tick the permissions in §3.

**Invite URL** (substitute your application ID):

```
https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&scope=bot&permissions=290456576
```

`applications.commands` is **not** needed — this bot has no slash commands.

6. **After inviting: drag the bot's role near the top of Server Settings → Roles.**
   Discord's docs only state role-hierarchy rules for kick/ban/nickname, but a
   low role position is the single most common cause of a bewildering `Forbidden`
   on a bot that visibly holds the right permissions. This costs nothing.

**Token handling.** Read it from the environment variable `DISCORD_BOT_TOKEN`.
Never a literal, never a committed file. GitHub is a Discord secret-scanning
partner with push protection — a committed token gets the push blocked *and* the
token revoked. Treat the token as an opaque string; do not validate it by regex.

---

## 3. Permissions — exactly these, nothing more

| Permission | Bit | Decimal | Why |
|---|---|---|---|
| View Channel | `1 << 10` | 1024 | resolve the channels at all |
| Connect | `1 << 20` | 1048576 | **required to move anyone into a channel**, and required to deny CONNECT on one |
| Mute Members | `1 << 22` | 4194304 | optional voting-phase mute (§6, default off) |
| Move Members | `1 << 24` | 16777216 | the core operation |
| Manage Roles | `1 << 28` | 268435456 | writing the channel lock overwrite |

**Combined integer: `290456576`**

Two non-obvious points, both from Discord's docs:

- Locking a channel needs **Manage Roles**, *not* Manage Channels. Discord's own
  client UI labels this permission **"Manage Permissions"** at channel level.
- **A bot can only deny a permission it itself holds.** To deny `CONNECT` to
  `@everyone`, the bot must have `CONNECT`. That is why Connect appears above
  even though the bot never joins voice.

**Never grant Administrator.** It bypasses channel overwrites, which will mask
permission bugs in development and surprise you in a correctly configured server.

---

## 4. Gateway intents — no privileged intents required

```python
intents = discord.Intents.none()   # start from zero, NOT Intents.default()
intents.guilds = True              # 1 << 0
intents.voice_states = True        # 1 << 7
client = discord.Client(intents=intents)   # intents value == 129
```

- `voice_states` alone delivers `on_voice_state_update` and populates
  `VoiceChannel.voice_states` / `.members`.
- **You do not need the privileged `members` intent.** Enabling `voice_states`
  automatically turns on `MemberCacheFlags.voice`, so members who are in voice —
  exactly the ones you care about — are cached. Resolve with
  `guild.get_member(uid)` and fall back to `await guild.fetch_member(uid)` only
  when that returns `None`. Never call `guild.chunk()`; it raises without the
  members intent.
- **Ignore any training data about a "100 servers" privileged-intent threshold.**
  Discord replaced it with 10,000 unique visible users. `discord.py`'s own
  docstrings are stale here; the live docs win. Either way this bot is nowhere
  near it and needs no privileged intent at all.

---

## 5. The game server API (already built and running — code against this)

Base URL is the island, e.g. `https://survivor.mctech.biz` (or
`http://127.0.0.1:8080` locally). **Every `/api/*` route is behind an access
gate.** Authenticate once at startup and reuse the cookie:

```python
session = requests.Session()                       # or aiohttp
session.post(f"{BASE}/api/access", json={"code": os.environ["SURVIVOR_ACCESS_CODE"]})
# -> sets an HttpOnly `survivor_access` cookie; reuse the session for everything
```

If a later call returns **401**, re-authenticate and retry once — the cookie is
derived from the access code, so it dies whenever the host rotates the code.

### `GET /api/voice/active` — which games to watch

The bot cannot learn a game code on its own, and restarting it per session would
be miserable. This returns every game worth mirroring: not finished, active in
the last 24 hours, and with at least one human who has linked a Discord ID.

```json
{ "games": [ { "gameId": "be9c1b8d", "phase": "playing", "linkedPlayers": 3 } ] }
```

In practice there will be one. Handle zero (idle — poll slowly) and more than one
(mirror only the first, and log that you're ignoring the rest — six friends
cannot be in two voice sets at once).

### `GET /api/voice/plan/<gameId>` — the whole picture

```json
{
  "gameId": "be9c1b8d",
  "phase": "playing",
  "version": "f46080065ad1",
  "policy": { "open": ["camp_fire", "the_beach", "the_water_well"], "forced": null },
  "places": [
    { "key": "camp_fire",      "label": "Camp Fire",
      "players": [ { "playerId": "a1b2c3d4", "name": "TDawg", "discordUserId": "123456789012345678" } ] },
    { "key": "the_beach",      "label": "The Beach",      "players": [] },
    { "key": "the_water_well", "label": "The Water Well", "players": [] },
    { "key": "tribal_council", "label": "Tribal Council", "players": [] }
  ]
}
```

Guarantees you can rely on:

- **All four place keys are always present**, empty ones included, so you can
  clear a channel you no longer need.
- **Computer players are excluded entirely** — they have no Discord presence.
  Eliminated human players *are* included; they become the jury and still belong
  in a voice channel.
- `discordUserId` is a digit string or `null`. **Skip `null` players silently** —
  a friend who hasn't linked their account is not an error.
- `version` is a 12-character content hash of `{policy, places}`. Poll it,
  compare it, and only reconcile when it changes. It is stable when nothing has
  changed and it changes whenever anyone moves or the phase flips.
- `policy.forced` is a place key (Tribal Council is in session — nobody may
  wander) or `null` (free movement among `policy.open`).

Poll every **2 seconds**. That is 30 requests/minute against a server on the
host's own Mac; it is nothing, and it keeps the code trivially simple.

---

## 6. Bot behaviour

### The reconcile loop

On every `version` change:

1. **Move people first, lock second.** For each place in the plan, for each
   listed player with a `discordUserId`, if their Discord member is in a voice
   channel *other than* that place's channel, move them.
2. **Then apply the locks.** If `policy.forced` is set, deny `CONNECT` on every
   channel that is not the forced one. Otherwise clear the denies on every
   channel in `policy.open`.

That ordering matters. Discord does **not** document whether denying `CONNECT`
ejects people already inside a channel, and it very likely does not. Never rely
on a lock to relocate anyone — place them deliberately, then close the doors.

### Moving a member

```python
member = guild.get_member(uid) or await guild.fetch_member(uid)

if member.voice is None or member.voice.channel is None:
    continue                     # not in voice — normal, skip silently
if member.voice.channel.id == target_channel.id:
    continue                     # already there — do not churn

try:
    await member.move_to(target_channel, reason=f"Survivor: {place_label}")
except discord.Forbidden as e:            # 403 — permission or role hierarchy
    log.error("cannot move %s: %s", member, e)
except discord.HTTPException as e:
    if e.status == 400:                   # incl. code 40032, not connected to voice
        log.info("%s is not in voice", member)
    else:
        raise
await asyncio.sleep(0.25)
```

- `member.move_to(channel, reason=...)` is `PATCH /guilds/{id}/members/{id}`.
  Always pass `reason=` — it lands in the audit log and turns a wall of mystery
  moderation entries into a readable game trace.
- **Guard on `member.voice` before calling.** "Not in voice" is expected, not
  exceptional.
- **Sequential with a 250 ms gap, not `asyncio.gather`.** Six moves is ~12% of
  Discord's 50 req/s global budget so throughput is a non-issue, and sequencing
  buys you per-player error attribution plus a phase transition that reads as a
  deliberate procession rather than six simultaneous teleports. `discord.py`
  retries 429s automatically; leave `max_ratelimit_timeout` unset so it simply
  waits.

### Locking and unlocking a channel

`set_permissions` **replaces** the whole overwrite, so read-modify-write:

```python
ow = channel.overwrites_for(guild.default_role)
ow.connect = False          # lock
# ow.connect = None         # UNLOCK — clears the key, restoring inheritance
await channel.set_permissions(guild.default_role, overwrite=ow, reason="Survivor: Tribal Council")
```

**Unlock with `connect=None`, never `connect=True`.** `None` removes the
override and restores whatever the category/guild intended; `True` writes a
permanent explicit allow that would stomp a deliberate category-level deny.

If the four channels live inside a category, log the category's overwrites at
startup too — a category that denies `CONNECT` to `@everyone` will make your
unlock appear to do nothing.

### Server-mute during voting — optional, default OFF

`await member.edit(mute=True)` requires **Mute Members** and throws a 400 if the
member isn't in voice. Two warnings:

- A server-muted user **cannot unmute themselves**. They will think their mic
  broke. Announce it in-game before applying it.
- `mute` is a field on the guild *member*, not just the voice state, so it very
  likely survives a disconnect/rejoin. **Always unmute explicitly** — in a
  `finally`, on phase exit, on bot startup, and on shutdown. Six people left
  permanently muted by a crash mid-vote is the worst realistic failure of this
  whole feature.

Put this behind a config flag defaulting to `false`.

### Voice state tracking

`on_voice_state_update(member, before, after)` fires for mute, deafen, camera and
stream toggles too — where `before.channel == after.channel`. **Filter those out**
or you will spam the game server. Derive the real cases:

```python
if before.channel is None and after.channel is not None:     # joined
elif before.channel is not None and after.channel is None:    # left
elif before.channel != after.channel:                          # moved
else:                                                          # ignore
```

Use `channel.voice_states` (populated straight from the gateway) as your source
of truth for occupancy rather than `.members`, which additionally depends on the
member cache.

**Voice state is session-scoped.** After a reconnect that cannot RESUME,
`discord.py` rebuilds it from a fresh `GUILD_CREATE`. Re-sync on **`on_ready`
and `on_resumed`**, not only at first boot.

---

## 7. Files to create

| File | Purpose |
|---|---|
| `discord_bot.py` | the bot (repo root, beside `survivor_server.py`) |
| `deploy/com.survivor-game.discord-bot.plist` | LaunchAgent, mirroring `com.survivor-game.server.plist` exactly |
| `requirements.txt` | add `discord.py>=2.7,<3` |
| `docs/voice/DISCORD-OPERATIONS.md` | short operator runbook: how to start/stop, where the logs are, how to rotate the token |

Do **not** modify `survivor_server.py`, `places.py`, `ios/`, or `client/dist/`.
The API you need already exists.

### Runtime

- **`discord.py` 2.7.x** is the correct library — actively maintained, ~17× the
  stars of any fork. Python **3.11 or 3.12** (3.8 is EOL; 3.13+ is untested by
  the project's classifiers).
- **Do not run the bot inside the Flask process.** `discord.py` is asyncio and
  the game server is gevent/WSGI; mixing them is a needless event-loop
  minefield. Separate process, separate LaunchAgent, talking over HTTP.
- **Check for a dependency conflict before committing:** `discord.py` requires
  `aiohttp>=3.7.4,<4`, and the server venv already carries a Flask-SocketIO
  stack. If they clash, give the bot its own venv rather than downgrading
  anything the game server depends on.
- LaunchAgent must use the **absolute** venv python path (launchd provides
  almost no environment — never `python3`), with `RunAtLoad`, `KeepAlive`,
  `ThrottleInterval 10`, logs to `/tmp/survivor-game-discord.{log,err}`, and
  `EnvironmentVariables` carrying `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, the
  four channel IDs, `SURVIVOR_BASE_URL`, and `SURVIVOR_ACCESS_CODE`.
- Leave `reconnect=True` (the default). `discord.py` handles Wi-Fi drops and
  Discord blips with its own exponential backoff; `KeepAlive` is only the outer
  net for hard crashes. Do not write your own restart loop.
- `RunAtLoad` can fire before Wi-Fi is up at login. That first connect will fail
  and launchd will retry — this is expected, do not engineer around it.

---

## 8. Definition of done

- [ ] Bot connects, logs the guild and all four resolved channels at startup, and
      warns loudly if any channel ID is missing or has `user_limit != 0`.
- [ ] Authenticates through the access gate; re-authenticates once on a 401.
- [ ] Discovers the active game via `/api/voice/active`; idles gracefully with zero.
- [ ] Polls `/api/voice/plan/<gid>` every 2s and reconciles **only** on `version` change.
- [ ] Moves each linked player to their place's channel; skips unlinked players
      and players not in voice, without raising.
- [ ] On `policy.forced`: moves everyone to the forced channel **first**, then
      denies `CONNECT` on the others. On release: clears the denies with
      `connect=None`.
- [ ] Re-syncs on `on_ready` and `on_resumed`.
- [ ] Optional voting mute is behind a flag defaulting to off, and unmutes in a
      `finally` plus on startup.
- [ ] Survives: game ends mid-session; player quits Discord; bot restarted
      mid-Tribal (it must reconcile to the correct state from the plan alone —
      the bot holds no authoritative state of its own).
- [ ] Token only from the environment. Nothing secret committed.

---

## 9. Things Discord does not document — do not assert these as fact

| Claim | Reality |
|---|---|
| Denying `CONNECT` ejects people already in the channel | Unverified. Design around it: move first, then lock. |
| `MOVE_MEMBERS` bypasses `user_limit` | Unverified. Set every channel to `user_limit = 0`. |
| Audio continues seamlessly through a move | Unverified. Expect a brief renegotiation gap; don't design a transition that needs someone talking through it. |
| A screen-share survives a move | Unverified. Assume it drops; tell players not to be sharing at a phase boundary. |
| Server-mute persists across rejoin | Inferred from the schema, not stated. Always unmute explicitly. |
| Role hierarchy applies to Move/Mute Members | Unverified (docs name only kick/ban/nickname). Put the bot's role high regardless. |

**Expect audit-log noise.** Every move writes a `MEMBER_MOVE` (action 26) entry
and every mute a `MEMBER_UPDATE` (24). A single session produces dozens. Tell the
server owner up front so it isn't mistaken for a compromise — and pass a
descriptive `reason=` on every call so the log reads as a game, not a mystery.
