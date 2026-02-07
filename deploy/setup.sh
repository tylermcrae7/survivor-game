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

# 2. Install Python dependencies
echo ""
echo "Installing Python dependencies..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
pip3 install -r "$REPO_DIR/requirements.txt"

# 3. Login to Cloudflare (opens browser)
echo ""
echo "Logging in to Cloudflare (browser will open)..."
cloudflared tunnel login

# 4. Create the tunnel
echo ""
echo "Creating 'survivor-game' tunnel..."
cloudflared tunnel create survivor-game

# 5. Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list | grep survivor-game | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

# 6. Create Cloudflare config
CRED_FILE="$HOME/.cloudflared/${TUNNEL_ID}.json"
cat > "$HOME/.cloudflared/config.yml" << YAML
tunnel: $TUNNEL_ID
credentials-file: $CRED_FILE

ingress:
  - service: http://localhost:8080
YAML

echo ""
echo "Cloudflare config written to ~/.cloudflared/config.yml"

# 7. Install launchd services
echo ""
echo "Installing launchd services..."

# Server plist
sed "s|{{REPO_DIR}}|$REPO_DIR|g" "$SCRIPT_DIR/com.survivor-game.server.plist" \
    > "$HOME/Library/LaunchAgents/com.survivor-game.server.plist"

# Tunnel plist
cp "$SCRIPT_DIR/com.survivor-game.tunnel.plist" \
   "$HOME/Library/LaunchAgents/com.survivor-game.tunnel.plist"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start the game server:  launchctl load ~/Library/LaunchAgents/com.survivor-game.server.plist"
echo "To start the tunnel:       launchctl load ~/Library/LaunchAgents/com.survivor-game.tunnel.plist"
echo ""
echo "Or start both manually:"
echo "  python3 $REPO_DIR/survivor_server.py"
echo "  cloudflared tunnel run survivor-game"
echo ""
echo "Quick tunnel (no custom domain, temporary URL):"
echo "  cloudflared tunnel --url http://localhost:8080"
echo ""
echo "To set up a custom domain, add a DNS route:"
echo "  cloudflared tunnel route dns survivor-game survivor.yourdomain.com"
