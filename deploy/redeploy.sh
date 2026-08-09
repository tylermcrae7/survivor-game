#!/bin/bash
# Survivor Game — redeploy the live server copy.
#
# The LaunchAgent must NOT run from ~/Documents: macOS TCC blocks launchd
# processes from Documents, and Python hangs forever opening the venv there
# (observed: stuck in open() during interpreter startup). The live server
# therefore runs from ~/srv/survivor-game — run this script after pulling or
# editing the repo to ship the changes.

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$HOME/srv/survivor-game"

echo "=== Redeploying $REPO_DIR -> $DEPLOY_DIR ==="
mkdir -p "$DEPLOY_DIR"

# Sync code; never touch live runtime state (games.json / winners.json / logs)
rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'ios' \
    --exclude '__pycache__' \
    --exclude 'games.json' \
    --exclude 'games.json.*' \
    --exclude 'winners.json' \
    --exclude 'push_keys.json' \
    --exclude 'push_subs.json' \
    --exclude '*.log' \
    --exclude 'archive' \
    "$REPO_DIR/" "$DEPLOY_DIR/"

# Fresh venv on first run
if [ ! -x "$DEPLOY_DIR/.venv/bin/python" ]; then
    echo "Creating venv..."
    python3 -m venv "$DEPLOY_DIR/.venv"
fi
"$DEPLOY_DIR/.venv/bin/pip" install -q -r "$DEPLOY_DIR/requirements.txt"

# Bounce the server and the Discord bot if their LaunchAgents are installed.
#
# The bot is not optional to restart. It validates the voice plan it polls
# against its own list of places, so a server that knows about a place the
# running bot does not — Exile Island was exactly this — makes every poll fail
# until the bot is restarted onto the new code.
for label in server discord-bot; do
    PLIST="$HOME/Library/LaunchAgents/com.survivor-game.$label.plist"
    if [ -f "$PLIST" ]; then
        launchctl unload "$PLIST" 2>/dev/null || true
        launchctl load "$PLIST"
        echo "Restarted com.survivor-game.$label"
    fi
done

echo "=== Redeploy complete ==="
