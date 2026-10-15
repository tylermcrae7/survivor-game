#!/bin/bash
# Survivor Game — Mac Mini Hosting Setup
# Run this once to set up everything needed to host the game.

set -e

echo "=== Survivor Game — Hosting Setup ==="
echo ""

# 1. Install cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "Installing cloudflared..."
    brew install cloudflare/cloudflare/cloudflared
else
    echo "cloudflared already installed: $(cloudflared --version)"
fi

# 2. Python dependencies, in the venv the LaunchAgent actually runs.
#    The server runs from ~/srv/survivor-game, never from this checkout: macOS
#    TCC blocks launchd from ~/Documents (Python hangs opening the venv), and
#    redeploy.sh only ever updates ~/srv. A LaunchAgent pointed at the checkout
#    is a server no deploy ever reaches.
echo ""
echo "Installing Python dependencies..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$HOME/srv/survivor-game"
mkdir -p "$DEPLOY_DIR"
if [ ! -x "$DEPLOY_DIR/.venv/bin/python" ]; then
    python3 -m venv "$DEPLOY_DIR/.venv"
fi
"$DEPLOY_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

# 3. Login to Cloudflare (opens browser)
echo ""
echo "Logging in to Cloudflare (browser will open)..."
cloudflared tunnel login

# 4. Create the tunnel (once — re-running setup must not fail here)
echo ""
if cloudflared tunnel info survivor-game >/dev/null 2>&1; then
    echo "Tunnel 'survivor-game' already exists"
else
    echo "Creating 'survivor-game' tunnel..."
    cloudflared tunnel create survivor-game
fi

# 5. Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list | grep survivor-game | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

# 6. Create Cloudflare config
HOSTNAME="${SURVIVOR_HOSTNAME:-survivor.mctech.biz}"
CRED_FILE="$HOME/.cloudflared/${TUNNEL_ID}.json"
cat > "$HOME/.cloudflared/config.yml" << YAML
tunnel: $TUNNEL_ID
credentials-file: $CRED_FILE

ingress:
  - hostname: $HOSTNAME
    service: http://localhost:8080
  - service: http_status:404
YAML

echo ""
echo "Cloudflare config written to ~/.cloudflared/config.yml (hostname: $HOSTNAME)"

# 6b. Route DNS for the hostname to this tunnel
cloudflared tunnel route dns survivor-game "$HOSTNAME" || true

# 6c. Access code — the shared "island code" that gates the public URL.
#     Generated once and stored ONLY in the installed LaunchAgent (never in git).
if [ -z "$SURVIVOR_ACCESS_CODE" ]; then
    SURVIVOR_ACCESS_CODE=$(python3 - << 'PYEOF'
import secrets
words = ["torch","ember","tribe","idol","rock","tide","palm","reef","spear","flint",
         "husk","vine","drift","coral","kelp","mango","lagoon","dune","cove","raft"]
print(f"{secrets.choice(words)}-{secrets.choice(words)}-{secrets.randbelow(9000)+1000}")
PYEOF
)
    echo ""
    echo "Generated access code: $SURVIVOR_ACCESS_CODE"
    echo "(Set SURVIVOR_ACCESS_CODE before running this script to choose your own.)"
fi

# 7. Install launchd services
echo ""
echo "Installing launchd services..."

# Server plist (deploy path + access code + public origin substituted in).
# Values are escaped for sed — a code containing & or | used to corrupt the
# plist — and the result is private to this user: it holds the island code.
sed_escape() { printf '%s' "$1" | sed -e 's/[\\/&|]/\\&/g'; }
SERVER_PLIST="$HOME/Library/LaunchAgents/com.survivor-game.server.plist"
sed -e "s|{{REPO_DIR}}|$(sed_escape "$DEPLOY_DIR")|g" \
    -e "s|{{ACCESS_CODE}}|$(sed_escape "$SURVIVOR_ACCESS_CODE")|g" \
    -e "s|{{REVIEW_ACCESS_CODE}}|$(sed_escape "${SURVIVOR_REVIEW_ACCESS_CODE:-}")|g" \
    -e "s|{{PUBLIC_ORIGIN}}|$(sed_escape "https://$HOSTNAME")|g" \
    "$SCRIPT_DIR/com.survivor-game.server.plist" \
    > "$SERVER_PLIST"
chmod 600 "$SERVER_PLIST"

# Tunnel plist
cp "$SCRIPT_DIR/com.survivor-game.tunnel.plist" \
   "$HOME/Library/LaunchAgents/com.survivor-game.tunnel.plist"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Copy the code into place and start the server (and every later deploy):"
echo "  bash $REPO_DIR/deploy/redeploy.sh"
echo "To start the tunnel:       launchctl load ~/Library/LaunchAgents/com.survivor-game.tunnel.plist"
echo "The Discord bot's LaunchAgent is installed by hand — see docs/voice/DISCORD-OPERATIONS.md"
echo ""
echo "Quick tunnel (no custom domain, temporary URL):"
echo "  cloudflared tunnel --url http://localhost:8080"
echo ""
echo "Public URL:   https://$HOSTNAME"
echo "Access code:  $SURVIVOR_ACCESS_CODE   (friends enter this once per phone)"
echo ""
echo "To change the code later: edit SURVIVOR_ACCESS_CODE in"
echo "  ~/Library/LaunchAgents/com.survivor-game.server.plist"
echo "then: launchctl unload && launchctl load that plist. Old phones re-enter the new code."
