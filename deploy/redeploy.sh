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
    "$REPO_DIR/" "$DEPLOY_DIR/"

# Fresh venv on first run
if [ ! -x "$DEPLOY_DIR/.venv/bin/python" ]; then
    echo "Creating venv..."
    python3 -m venv "$DEPLOY_DIR/.venv"
fi
"$DEPLOY_DIR/.venv/bin/pip" install -q -r "$DEPLOY_DIR/requirements.txt"

# Bounce the server if its LaunchAgent is installed
PLIST="$HOME/Library/LaunchAgents/com.survivor-game.server.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "Server restarted."
fi

echo "=== Redeploy complete ==="
