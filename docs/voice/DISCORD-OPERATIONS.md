# Survivor Discord bot operations

The bot mirrors the game server's places into the five Discord voice channels
(Camp Fire, The Beach, The Water Well, Tribal Council, and Exile Island). It is
a separate process from `survivor_server.py`; the game keeps working if the bot
is stopped.

## Current production deployment

These identifiers are configuration, not credentials, and are safe to keep in
the repository. The bot token, island access code, and individual player user
IDs are deliberately **not** recorded here.

| Item | Production value |
|---|---|
| Discord application | `Survivor Game` |
| Application / bot ID | `1533280135451639869` |
| Bot username | `Jeff` (verified as `Jeff#7376` on August 1, 2026) |
| Discord portal Public Bot setting | On |
| Discord server | `Survivor: The Tribe Has Spoken` |
| Guild ID | `1533248320154370259` |
| Camp Fire | `🔥 Camp Fire` — `1533248321244758219` |
| Beach | `🏝 The Beach` — `1533248684148658276` |
| Water Well | `💧The Water Well` — `1533249063934234805` |
| Tribal Council | `🗳 Tribal Council` — `1533249111233527969` |
| Survivor server | `https://survivor.mctech.biz` |
| LaunchAgent label | `com.survivor-game.discord-bot` |
| Installed plist | `~/Library/LaunchAgents/com.survivor-game.discord-bot.plist` |
| Dedicated Python | `~/Library/Application Support/SurvivorGame/discord-venv/bin/python` |
| Deployed code | `~/srv/survivor-game/discord_bot.py` |
| Logs | `/tmp/survivor-game-discord.log` and `/tmp/survivor-game-discord.err` |
| Voting mute | Off (`DISCORD_MUTE_DURING_VOTING=false`) |

The installed plist is mode `0600`. It contains the current Discord token and
island access code, while the repository plist remains a placeholder-only
template. Never copy the installed plist into Git. If either credential is ever
exposed, rotate it rather than trying to hide the old value in Git history.

The production service was verified end to end on August 1, 2026: Jeff logged
in to Discord, authenticated with the live Survivor server, resolved all four
voice channels, found no channel user limits or category-level Connect denies,
and entered the idle polling state. The startup warnings about PyNaCl and DAVE
are harmless for this bot: Jeff moves members through Discord's API but never
joins a voice channel, receives audio, or records anyone.

The Discord Developer Portal's **Public Bot** setting is currently enabled.
This does not expose Jeff's token, but it allows another server administrator
with an installation link to add Jeff to another server. Turn it off under
**Bot → Public Bot** if installation should be restricted to the current owner.

### Player setup

1. **iOS app:** open **Settings → Link Discord**, then run `/link <code>` in
   the Discord server with the code it shows (see
   [Linking a Discord account](#linking-a-discord-account)). Nothing to copy.
2. **Web, or when Jeff is down:** enable Discord's **User Settings → Advanced →
   Developer Mode**, right-click your own name and choose **Copy User ID**, then
   paste it into Survivor's **Settings → Discord user ID** (on iOS, under
   **Enter ID manually**).
3. If you were already in a game when you linked, relaunch or leave and rejoin
   so the join request synchronizes the link.
4. Join **Camp Fire** voice manually. Jeff can move a connected member, but
   Discord will not let a bot pull someone into voice from a disconnected state.

A pasted Discord user ID is not the username, display name, guild ID, or
channel ID. It is a 15–25 digit value unique to that player and should remain a
string when sent through JSON.

## One-time installation

Use Python 3.11 or 3.12 for the bot. Keep its environment outside the deployed
repository so `deploy/redeploy.sh --delete` cannot remove it.

```bash
REPO_DIR="$HOME/srv/survivor-game"
BOT_VENV="$HOME/Library/Application Support/SurvivorGame/discord-venv"
/opt/homebrew/bin/python3.11 -m venv "$BOT_VENV"
"$BOT_VENV/bin/pip" install --upgrade pip
"$BOT_VENV/bin/pip" install -r "$REPO_DIR/requirements.txt"
```

Copy the template, then replace every `{{...}}` value in the installed copy.
Never put a real token or island code in the repository template.

```bash
PLIST="$HOME/Library/LaunchAgents/com.survivor-game.discord-bot.plist"
cp "$REPO_DIR/deploy/com.survivor-game.discord-bot.plist" "$PLIST"
chmod 600 "$PLIST"
open -e "$PLIST"
```

Required values:

| Placeholder | Value |
|---|---|
| `{{DISCORD_PYTHON}}` | `/Users/<you>/Library/Application Support/SurvivorGame/discord-venv/bin/python` |
| `{{REPO_DIR}}` | the absolute deployed repo path, normally `/Users/<you>/srv/survivor-game` |
| `{{DISCORD_BOT_TOKEN}}` | current token from Discord Developer Portal → Bot |
| `{{DISCORD_GUILD_ID}}` | server ID |
| five `{{DISCORD_..._CHANNEL_ID}}` values | IDs of Camp Fire, Beach, Water Well, Tribal Council, and Exile Island |
| `{{SURVIVOR_BASE_URL}}` | normally `https://survivor.mctech.biz` |
| `{{SURVIVOR_ACCESS_CODE}}` | the current island access code |

## Linking a Discord account

Players link from the app: **Settings → Link Discord** shows a code such as
`EMBER-441`, and they run `/link EMBER-441` in the server. Discord tells the bot
who ran the command, so nobody copies an 18-digit ID and no username is matched
— those change, and display names were never unique. The 18-digit field is
still there under "Enter ID manually" for when the bot is down.

The code binds to the **phone**, not to a player: the app stores
`discordUserId` and sends it on every join and reconnect, so you link once and
never again. Codes are single-use, last ten minutes, live only in memory, and
do not survive a redeploy — if one stops working mid-link, ask for another.

`/link` needs the **`applications.commands` scope** on the bot invite. A bot
added with only `bot` connects, mirrors voice perfectly, and simply has no
slash commands, with nothing saying why. The bot now logs that case explicitly
at startup:

```
cannot register slash commands in guild … — the bot was invited without the
applications.commands scope
```

If you see that, generate a fresh OAuth URL with **both** `bot` and
`applications.commands` and re-add the bot. Voice mirroring is unaffected
either way. On success it logs `registered 1 slash command(s): /link`, once per
process — a gateway reconnect does not register again.

A player whose `/link` fails sees the server's own sentence only when the
island refused the code itself ("that code has expired"). Anything else — the
island unreachable, a gateway error page, the bot locked out of the access gate
— shows "The island could not be reached — try again." and the detail goes to
the bot's log.

This is the one thing the bot writes back to the game server, through an
endpoint that can only bind an account to a pending code — it cannot reach a
game.

**Exile Island is optional to configure and required to work.** It arrived
after the other four, so the bot still starts without
`DISCORD_EXILE_ISLAND_CHANNEL_ID` — it logs a warning and simply never moves
snuffed players anywhere. The game itself is unaffected either way: places are
derived server-side and no client depends on a bot existing. Set the ID and the
snuffed are moved there on elimination and barred from the living's rooms until
the Final Tribal Council.

All five Discord channels must be voice channels with no user limit. The bot
role needs View Channel, Connect, Mute Members, Move Members, and Manage Roles
(Discord calls the last one **Manage Permissions** at channel level). Keep the
bot role near the top, and do not grant Administrator. No privileged gateway
intents are used or needed.

Validate and load the LaunchAgent:

```bash
plutil -lint "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/com.survivor-game.discord-bot"
launchctl kickstart -k "gui/$(id -u)/com.survivor-game.discord-bot"
```

Each person must join **Camp Fire** voice manually at the start of the night.
Discord cannot let the bot pull in someone who is not already connected.

## Which game the bot mirrors

The bot asks `/api/voice/active` for games worth mirroring and follows the
first one. While it is watching a game it asks again every ten seconds, so a
table abandoned last night does not keep the channels through tonight's game:

- **The watched game leaves the list** (finished, untouched for a day, or no
  linked players left): the bot releases it at once and moves on to the top
  game, or goes idle.
- **Another game outranks it:** the bot switches once the same game has led
  two looks in a row. `lastActivity` moves whenever anyone touches a game, so a
  single poke at an old table does not drag everybody's voice across and back.
  A server old enough not to send `lastActivity` sorts the list by game id,
  which ranks nothing; against one, the bot stays put until its game leaves
  the list.

Releasing a game unlocks the channels, lifts any voting mute the bot applied,
and readmits that game's snuffed players before the next game is reconciled.

## Start, stop, status, and logs

```bash
# Status
launchctl print "gui/$(id -u)/com.survivor-game.discord-bot"

# Restart
launchctl kickstart -k "gui/$(id -u)/com.survivor-game.discord-bot"

# Stop
launchctl bootout "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.survivor-game.discord-bot.plist"

# Follow logs
tail -F /tmp/survivor-game-discord.log /tmp/survivor-game-discord.err
```

The bot logs the resolved guild and every configured channel on every fresh
gateway connection. A channel limit, a category-level Connect deny, a missing
permission, an expired island cookie, or a failed member move is called out
explicitly.

Stopping the bot with SIGTERM — `bootout`, or the `unload` that
`deploy/redeploy.sh` does — releases the channels before it disconnects:
Tribal Council locks are lifted, the bot's own voting mutes are undone, and the
watched game's snuffed players are readmitted. The game is meant to carry on without the bot, with
people moving themselves. A restart reapplies whatever the live game still
calls for within one poll.
Discord's audit log will contain one entry for every move and permission change;
the bot supplies a `Survivor:` reason for each one.

At a phase transition, the bot first clears its old deny on the new destination,
moves the linked people, and only then locks the other channels. This avoids a
previous phase's lock blocking the next move while still ensuring people move
before any new doors close.

## Updating the bot

Redeploy the repository normally, refresh the dedicated bot environment, and
restart only the bot:

```bash
REPO_DIR="$HOME/srv/survivor-game"
BOT_VENV="$HOME/Library/Application Support/SurvivorGame/discord-venv"
"$BOT_VENV/bin/pip" install -r "$REPO_DIR/requirements.txt"
launchctl kickstart -k "gui/$(id -u)/com.survivor-game.discord-bot"
```

## Rotate the Discord token

1. Discord Developer Portal → the application → **Bot** → **Reset Token**.
2. Open the installed plist (not the repository template), replace only the
   `DISCORD_BOT_TOKEN` string, and save it.
3. Run `plutil -lint`, then `bootout` and `bootstrap` using the commands above.
4. Confirm `ready as ...` in `/tmp/survivor-game-discord.log`.

The old token stops working immediately. Do not paste either token into a log,
shell script, issue, or committed `.env` file.

## Rotate the island code or change channel IDs

Update the corresponding value in the installed bot plist whenever the server's
installed plist changes, then `bootout` and `bootstrap` the bot. The bot also
re-authenticates and retries once if a cookie receives a 401, so a code rotation
does not require code changes.

If the island refuses the bot's code, the bot waits a minute before presenting
it again (doubling to five minutes). The access gate allows ten attempts a
minute per IP, and behind the tunnel the bot shares the house's IP with every
player at home: retrying a stale code at poll speed would lock all of them out.

## Optional voting mute

`DISCORD_MUTE_DURING_VOTING` defaults to `false`. When set to `true`, linked
players already in voice are server-muted only while the game reports the
Tribal Council or Final Tribal `voting` subphase. They are explicitly unmuted on
phase exit, bot startup, poller exit, and clean shutdown. Leave this off until
players have been told that a server mute prevents self-unmuting.

With it off, the bot never changes anybody's mute — including the startup and
shutdown cleanups, which with it on unmute everyone in the five channels. If
you turn it off right after a crash mid-vote, unmute those players by hand.

## Exile Island bars

While camp is open, a snuffed player gets a per-member Connect deny on Camp
Fire, The Beach, and The Water Well so they cannot walk back in from Exile
Island (only when the Exile Island channel is configured). Discord does not
record who wrote an overwrite, so the bot only ever lifts a deny on a Discord
account linked in the game it is watching or has just released. A moderator's deny on anyone
else is never touched, and neither is any explicit allow.

The one gap: if the bot dies while a player is barred and that game ends before
it comes back, nothing it can see ties the deny to Survivor. That player is
readmitted by the first reconciliation of the next game they are linked in, or
an admin can remove the deny (its audit-log reason is `Survivor: snuffed
players do not join breakouts`).

## Common failures

- **Bot is online but nobody moves:** confirm each player linked the quoted
  Discord user ID in Survivor Settings and joined voice manually.
- **`Forbidden` when moving:** confirm Move Members and Connect on both source
  and destination channels, then move the bot role higher.
- **Unlock appears ineffective:** inspect the voice channel's category; a
  category-level Connect deny still applies after the bot correctly clears its
  channel-level override.
- **Online but `Discord configuration is incomplete` in the log:** a channel
  ID is wrong, a channel is not a voice channel, or the bot role is missing a
  permission. The bot does not exit for this — it stays connected, logs the
  problem once, and re-checks every minute, so fix the Discord server and wait.
- **`voice plan poll failed`:** the island is unreachable or erroring. The
  first failure logs a traceback; repeats log one line each while the bot
  backs off from 5 seconds to 5 minutes. It picks up again on its own (sooner
  if anybody moves in voice), and logs `recovered` when it does.
- **Restarting every minute:** read the `.err` log. Common causes are an
  unreplaced `{{...}}`, an invalid token, or an unsupported Python environment.
  The template's `ThrottleInterval` is 60 seconds; an installed plist copied
  before that change still says 10 — edit it there, since redeploys never
  touch the installed copy.
- **Wrong island code:** update the installed plist. The bot never reads secrets
  from the repository.
