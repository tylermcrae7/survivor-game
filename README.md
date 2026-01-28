# Survivor: The Digital Board Game

A real-time multiplayer web adaptation of the official Survivor board game. Play with friends remotely from any device - no physical cards required!

## Quick Start (For Players)

### Joining a Game
1. **One player creates the game** and receives a 6-character code
2. **Share the code** with friends (2-6 players total)
3. **Everyone visits** the game URL
4. **Enter the code + your name** and you're in!

### Creating a Game
1. Open the game in your browser
2. Click **"Create Game"**
3. Enter your name
4. Share the game code with friends
5. Once everyone joins, the leader starts the game

---

## Game Rules

### Overview
Survivor is about making alliances, outwitting opponents, and surviving Tribal Councils. The last player standing (or one of the final two) wins!

### Setup
- Each player starts with **5 cards** (3 action cards + 1 vote card + initial draws)
- One player is randomly chosen as the first **Council Leader**
- The deck contains **Tribal Council cards** that trigger elimination votes

### Turn Structure
Each turn has 3 parts - **Steal, Play, Draw**:

1. **Steal a Card** - Take a random card from any other player
2. **Play a Card** (Optional) - Use one action card from your hand
3. **Draw a Card** - Take the top card from the deck

If you draw a **Tribal Council card**, a Tribal Council immediately begins!

### Tribal Council
When a Tribal Council is triggered:

1. **Announcement Phase** - Council Leader announces the tribal
2. **Advantage Phase** - Players may play Tribal Advantage cards
3. **Discussion Phase** - Debate who should be eliminated
4. **Voting Phase** - All players secretly vote
5. **Immunity Phase** - Players may reveal Hidden Immunity Idols
6. **Reveal Phase** - Votes are revealed one by one

#### Tribal Council Types
- **Single Elimination** - One player is voted out
- **Double Elimination** - Two players are voted out

#### Ties
The Council Leader breaks all ties by choosing who is eliminated.

### Character Lives
- Each player has **2 lives** (represented by Survivor Character Cards)
- Being voted out removes **1 life**
- Lose both lives = **Eliminated from the game**
- Eliminated players join the **Jury** for Final Tribal Council

### Winning the Game
When only **2 players remain**, the Final Tribal Council begins:
1. Both finalists make their case to the Jury
2. The Jury votes for who they think **should WIN**
3. Most votes wins - **Sole Survivor!**

---

## Card Reference (All 69 Official Cards)

### Vote Cards (13 total)

| Card | Count | Effect |
|------|-------|--------|
| **Vote** | 6 | Your basic vote at Tribal Council |
| **Extra Vote** | 7 | Gain an additional vote at the next Tribal Council |

### Tribal Advantage Cards (12 total)

| Card | Count | Effect |
|------|-------|--------|
| **Control The Vote** | 2 | Choose who the next Tribal Council Leader will be |
| **Goodwill Gamble** | 3 | Give away cards to gain influence at Tribal Council |
| **I'm The Leader Now** | 1 | Become the Tribal Council Leader immediately |
| **Hidden Immunity Idol** | 4 | Negate all votes against you at Tribal Council |
| **Idol Nullifier** | 2 | Nullify someone's immunity idol at Tribal Council |

### Action Cards (35 total)

| Card | Count | Effect |
|------|-------|--------|
| **Sorry For You** | 7 | REACTIVE: When someone tries to take cards from you - they get nothing and must discard 1 card |
| **The Spy Shack** | 3 | Look at target player's hand |
| **Knowledge Is Power** | 3 | Choose a card type - if target has it, they must give it to you |
| **Camp Raid** | 3 | Steal 2 random cards from target player |
| **Inheritance** | 6 | Choose a target - when they are eliminated, you inherit all their cards |
| **Let's Form An Alliance** | 4 | You and a teammate each steal a card from a victim |
| **Reward Challenge: Do Or Die** | 3 | Rock/Paper/Scissors - winner steals 2 cards |
| **Reward Challenge: Power Pair** | 3 | Three players show fingers, pairs give you their cards |
| **Reward Challenge: It's A Numbers Game** | 3 | Players pick 1-3, closest to your number gives you a card |

### Tribal Council Cards (9 total)

| Card | Count | Effect |
|------|-------|--------|
| **Single Elimination** | 4 | Triggers Tribal Council - 1 player voted out |
| **Double Elimination** | 5 | Triggers Tribal Council - 2 players voted out |

#### Tribal Cards by Player Count
The deck uses different tribal card distributions based on player count:

| Players | Single Elimination | Double Elimination |
|---------|-------------------|-------------------|
| 3 | 4 | 0 |
| 4 | 2 | 2 |
| 5 | 2 | 3 |
| 6 | 0 | 5 |

---

## Sharing the Game with Friends

### Method 1: Share the Game Code
After creating a game, you'll see a 6-character code (e.g., `ABC123`).

**Send this to your friends:**
> "Join my Survivor game! Go to [your-game-url] and enter code: ABC123"

Friends then:
1. Open the URL in their browser
2. Click "Join Game"
3. Enter the code and their name
4. They're in!

### Method 2: Copy & Share (Mobile)
1. Create a game
2. Tap the **Copy Code** button
3. Paste into your messaging app
4. Friends click the link or enter the code manually

### Method 3: Native Share (iOS/Android)
1. Create a game
2. Tap the **Share** button
3. Choose your messaging app
4. Friends receive a direct link to join

### Tips for Remote Play
- Use a **video call** (Zoom, FaceTime, Discord) for discussions
- The **in-game narrator** announces important events
- All players see the **same game state** in real-time
- Games auto-reconnect if you lose connection briefly

---

## Hosting Your Own Server

### Local Development
```bash
# Clone the repository
git clone https://github.com/tylermcrae7/survivor-game.git
cd survivor-game

# Install dependencies
pip install -r requirements.txt

# Run the server
python survivor_server.py
```

The server runs on `http://localhost:8080` by default.

### Exposing to the Internet with Cloudflare Tunnel

To let friends connect from anywhere, use a Cloudflare Tunnel:

#### 1. Install cloudflared
```bash
# macOS
brew install cloudflare/cloudflare/cloudflared

# Windows
winget install --id Cloudflare.cloudflared

# Linux
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

#### 2. Login to Cloudflare
```bash
cloudflared tunnel login
```

#### 3. Create a Tunnel
```bash
cloudflared tunnel create survivor-game
```

#### 4. Run the Tunnel
```bash
# Quick tunnel (temporary URL)
cloudflared tunnel --url http://localhost:8080

# Or with your custom domain
cloudflared tunnel run --url http://localhost:8080 survivor-game
```

#### 5. Share the URL
Cloudflare provides a URL like `https://random-name.trycloudflare.com` - share this with friends!

### Running on iOS (Pythonista)
This app was specifically designed to run on iOS using Pythonista 3:

1. Copy all files to Pythonista's Documents folder
2. Open `survivor_server.py`
3. Run the script
4. Access via your device's local IP address

---

## Technical Architecture

### Stack
- **Backend**: Python Flask + Flask-SocketIO
- **Frontend**: Vanilla JavaScript (no framework)
- **Real-time**: WebSocket via Socket.IO
- **Storage**: JSON file persistence

### Key Files
```
SurvivorApp/
├── survivor_server.py      # Main Flask server
├── rules_engine.py         # Game logic & card effects
├── survivor_cards.json     # All 69 card definitions
├── client/dist/
│   ├── index-optimized.html  # Main app entry
│   ├── game.js              # Core game module
│   ├── network.js           # Socket.IO handling
│   ├── ui.js                # UI rendering
│   ├── narrator.js          # Game event narrator
│   ├── state-manager.js     # State management
│   ├── styles.css           # Mobile-first CSS
│   ├── sw.js                # Service Worker (PWA)
│   └── manifest.json        # PWA manifest
├── tests/                   # 150+ automated tests
└── docs/                    # Game rules & documentation
```

### Features
- **Real-time multiplayer** - All players see updates instantly
- **Mobile-first design** - Optimized for phone screens
- **PWA support** - Add to home screen, offline capability
- **Auto-reconnect** - Seamless recovery from network issues
- **Narrator system** - Dramatic game commentary
- **Phase guidance** - Always know what actions are available

---

## Game Strategy Tips

### Early Game
- Build alliances before the first Tribal Council
- **Sorry For You** cards are valuable protection - don't waste them
- Track who has **Hidden Immunity Idols**

### Mid Game
- Use **The Spy Shack** to identify threats
- **Inheritance** on a likely elimination target = free cards
- Save your idols for when you're really in danger

### Late Game
- **Idol Nullifier** can blindside idol holders
- **Control The Vote** to become leader and break ties your way
- In Final Tribal, own your gameplay - the Jury respects bold moves

### Social Strategy
- Promises can be broken - but remember who broke them
- Whisper privately (in your video call) to form secret alliances
- The quiet player often makes it to the end

---

## Troubleshooting

### "Connection lost" / Game not updating
- Check your internet connection
- Refresh the page - the game auto-reconnects
- If hosting: ensure the server is still running

### "Game not found"
- Double-check the 6-character code
- Games expire after 24 hours of inactivity
- The host may need to create a new game

### Cards not appearing
- Pull down to refresh on mobile
- Check that JavaScript is enabled
- Try a different browser (Chrome/Safari recommended)

### Can't steal/play cards
- Read the **phase indicator** - you may be in the wrong phase
- Some cards are **reactive only** (like Sorry For You)
- You must complete actions in order: Steal → Play → Draw

---

## Contributing

Found a bug or have a suggestion? Open an issue on GitHub!

### Running Tests
```bash
python run_all_tests.py
```

The test suite includes 150+ tests covering:
- All 69 card effects
- Tribal Council mechanics
- Edge cases and error handling
- Rules compliance verification

---

## Credits

Based on **Survivor: The Tribe Has Spoken** board game by Exploding Kittens.

Survivor TM & © 2024 Survivor Productions, LLC

---

## License

This is a fan project for personal use. All Survivor intellectual property belongs to its respective owners.
