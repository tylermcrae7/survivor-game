#!/bin/bash
# Survivor Game — redeploy the live server copy.
#
# The LaunchAgent must NOT run from ~/Documents: macOS TCC blocks launchd
# processes from Documents, and Python hangs forever opening the venv there
# (observed: stuck in open() during interpreter startup). The live server
# therefore runs from ~/srv/survivor-game — run this script after pulling or
# editing the repo to ship the changes.
#
# Order matters: dependencies are installed BEFORE the code is swapped, so a
# failed pip install leaves the old code and the old venv running together
# instead of new code half-upgraded on an old venv. Runtime state is snapshotted
# before the bounce, and the script waits for the server to answer afterwards
# rather than declaring success on faith.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$HOME/srv/survivor-game"
BACKUP_ROOT="$HOME/srv/survivor-backups"
PORT="${PORT:-8080}"

echo "=== Redeploying $REPO_DIR -> $DEPLOY_DIR ==="
mkdir -p "$DEPLOY_DIR"

if command -v git >/dev/null 2>&1 && [ -d "$REPO_DIR/.git" ]; then
    if ! git -C "$REPO_DIR" diff --quiet HEAD -- 2>/dev/null; then
        echo "NOTE: the working tree has uncommitted changes — they ship too."
    fi
    echo "Deploying $(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo '?')"
fi

# Who is mid-ceremony right now? Bouncing drops sockets for a moment; players
# reconnect on their own, but a Tribal Council in progress is worth knowing about.
if [ -f "$DEPLOY_DIR/games.json" ]; then
    python3 - "$DEPLOY_DIR/games.json" <<'PY' || true
import json, sys, time
try:
    games = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
live = [(gid, g.get("phase")) for gid, g in games.items()
        if isinstance(g, dict) and g.get("phase") in ("tribal_council", "final_tribal")
        and time.time() - g.get("lastActivity", 0) < 3600]
for gid, phase in live:
    print(f"NOTE: game {gid} is in {phase} right now — the bounce drops its sockets briefly.")
PY
fi

# 1. Dependencies first, into the live venv, from the repo's requirements.
if [ ! -x "$DEPLOY_DIR/.venv/bin/python" ]; then
    echo "Creating venv..."
    python3 -m venv "$DEPLOY_DIR/.venv"
fi
"$DEPLOY_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

# 2. Snapshot runtime state before anything restarts (last 20 kept).
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_ROOT/$STAMP"
for f in games.json winners.json push_keys.json push_subs.json; do
    if [ -f "$DEPLOY_DIR/$f" ]; then cp -p "$DEPLOY_DIR/$f" "$BACKUP_ROOT/$STAMP/"; fi
done
# shellcheck disable=SC2012
ls -1t "$BACKUP_ROOT" | tail -n +21 | while read -r old; do rm -rf "${BACKUP_ROOT:?}/$old"; done

# 3. Sync code; never touch live runtime state. Patterns with a leading slash
#    are anchored to the deploy root, so docs/archive is not mistaken for the
#    runtime archive/ of swept games.
rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude '/ios' \
    --exclude '__pycache__' \
    --exclude '/games.json' \
    --exclude '/games.json.*' \
    --exclude '/winners.json' \
    --exclude '/winners.json.*' \
    --exclude '/push_keys.json' \
    --exclude '/push_keys.json.*' \
    --exclude '/push_subs.json' \
    --exclude '/push_subs.json.*' \
    --exclude '*.log' \
    --exclude '/archive/' \
    "$REPO_DIR/" "$DEPLOY_DIR/"

# 4. Bounce the server and the Discord bot if their LaunchAgents are installed.
#
# The bot is not optional to restart. It validates the voice plan it polls
# against its own list of places, so a server that knows about a place the
# running bot does not — Exile Island was exactly this — makes every poll fail
# until the bot is restarted onto the new code.
for label in server discord-bot; do
    PLIST="$HOME/Library/LaunchAgents/com.survivor-game.$label.plist"
    if [ -f "$PLIST" ]; then
        if [ "$label" = server ] && command -v plutil >/dev/null 2>&1; then
            wd="$(plutil -extract WorkingDirectory raw "$PLIST" 2>/dev/null || true)"
            if [ -n "$wd" ] && [ "$wd" != "$DEPLOY_DIR" ]; then
                echo "WARNING: the server LaunchAgent runs from $wd, not $DEPLOY_DIR —"
                echo "         this deploy will not be what players are running."
            fi
        fi
        launchctl unload "$PLIST" 2>/dev/null || true
        if launchctl load "$PLIST"; then
            echo "Restarted com.survivor-game.$label"
        else
            echo "WARNING: could not load com.survivor-game.$label"
        fi
    fi
done

# 5. Confirm it actually took. /api/ping is outside the access gate and reports
#    the client build the server is serving.
ok=""
for _ in $(seq 1 30); do
    if ping_json="$(curl -fsS "http://127.0.0.1:$PORT/api/ping" 2>/dev/null)"; then
        ok=1
        break
    fi
    sleep 1
done
if [ -n "$ok" ]; then
    echo "Server is answering on :$PORT — $ping_json"
    echo "=== Redeploy complete ==="
else
    echo "ERROR: the server is not answering on :$PORT after 30s. Recent errors:"
    tail -n 40 /tmp/survivor-game-server.err 2>/dev/null || true
    exit 1
fi
