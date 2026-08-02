# Survivor Discord bot operations

The bot mirrors the game server's places into the four Discord voice channels.
It is a separate process from `survivor_server.py`; the game keeps working if
the bot is stopped.

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

1. In Discord, enable **User Settings → Advanced → Developer Mode**.
2. Right-click your own name on one of your messages and choose **Copy User ID**.
3. In Survivor, open **Settings → Discord user ID**, paste the digit string, and
   save it.
4. If you were already in a game when you saved the ID, relaunch or leave and
   rejoin so the join request synchronizes the link.
5. Join **Camp Fire** voice manually. Jeff can move a connected member, but
   Discord will not let a bot pull someone into voice from a disconnected state.

The Discord user ID is not the username, display name, guild ID, or channel ID.
It is a 15–25 digit value unique to that player and should remain a string when
sent through JSON.

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
| four `{{DISCORD_..._CHANNEL_ID}}` values | IDs of Camp Fire, Beach, Water Well, and Tribal Council |
| `{{SURVIVOR_BASE_URL}}` | normally `https://survivor.mctech.biz` |
| `{{SURVIVOR_ACCESS_CODE}}` | the current island access code |

All four Discord channels must be voice channels with no user limit. The bot
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

The bot logs the resolved guild and all four channels on every fresh gateway
connection. A channel limit, a category-level Connect deny, a missing permission,
an expired island cookie, or a failed member move is called out explicitly.
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

## Optional voting mute

`DISCORD_MUTE_DURING_VOTING` defaults to `false`. When set to `true`, linked
players already in voice are server-muted only while the game reports the
Tribal Council or Final Tribal `voting` subphase. They are explicitly unmuted on
phase exit, bot startup, poller exit, and clean shutdown. Leave this off until
players have been told that a server mute prevents self-unmuting.

## Common failures

- **Bot is online but nobody moves:** confirm each player linked the quoted
  Discord user ID in Survivor Settings and joined voice manually.
- **`Forbidden` when moving:** confirm Move Members and Connect on both source
  and destination channels, then move the bot role higher.
- **Unlock appears ineffective:** inspect the voice channel's category; a
  category-level Connect deny still applies after the bot correctly clears its
  channel-level override.
- **Immediate restart every ten seconds:** read the `.err` log. Common causes are
  an unreplaced `{{...}}`, invalid token, missing channel permission, or using an
  unsupported Python environment.
- **Wrong island code:** update the installed plist. The bot never reads secrets
  from the repository.
