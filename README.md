# Survivor: The Digital Board Game

A real-time multiplayer web adaptation of **Survivor: The Tribe Has Spoken** — the official board game — faithful to the official Survival Guide. Play with friends from any phone; no physical cards required.

Runs as a mobile-first PWA against a small Flask + Socket.IO server. One household hosts; everyone else just opens a link.

---

## Quick Start (For Players)

1. **One player creates the game** — pick a deck, optionally add the *Let's Go To Rocks* Challenges — and receives a fire code
2. **Share the code** (2–6 players total)
3. Everyone opens the game URL, taps **Join a Tribe**, and enters the code, a name, and a buff color
4. You can **change your name** any time in the lobby (pencil next to your name) — names lock when the game starts
5. The leader taps **Begin the Game**

If the server is code-locked (see *Access gate* below), everyone enters the shared island code once per device first.

### The camp menu (☰ in the header)
- **Hall of Fame** — every Sole Survivor ever recorded, ranked by wins. Wins record automatically when a game finishes, and the record is hand-editable (add a win from an off-app game night, fix a name or date, strike an entry)
- **Leave this game** — just you; the game continues without you
- **Burn it down** — wipes the game for *everyone* (with confirmation) and returns every phone to the start screen

---

## Game Rules (as implemented)

### Setup — per the official Survival Guide
- The official box holds **67 Action Cards**. Setup removes the 9 Tribal Council Cards and 6 Vote Cards, deals each player **3 Action Cards** and **1 Vote Card** (extra Vote Cards leave the game), *then* assembles the Draw Pile with the Tribal Council Cards spaced through it (one guaranteed at the bottom) — so a Tribal can never be dealt into an opening hand
- Each player has **2 Survivor Character Cards** (lives)
- One player is randomly the first **Council Leader**

### Deck modes
| Mode | Contents |
|------|----------|
| **Official** | The 67-card box, exactly as printed |
| **Extended** | +7 house cards: Idol Nullifier ×2, Steal A Vote ×2, Block A Vote ×2, Grant Immunity ×1 |

### Turn structure — Steal, Play, Draw
1. **Steal** — take a random card from any other player (the target may interrupt with *Sorry For You*)
2. **Play** (optional) — play one Action Card
3. **Draw** — take the top card of the Draw Pile. Drawing a **Tribal Council Card** starts a Tribal Council immediately

### Tribal Council
Announcement → Advantage play → Discussion → Voting → Reveal, run by the Council Leader.

**The vote economy (official):**
- **Vote Cards** and a **Goodwill Gamble** played on you **must** be cast at that Tribal
- **Extra Vote** *may* be cast, or saved
- A player wearing the **Immunity Idol Necklace** cannot be voted for
- **Hidden Immunity Idol** negates all votes against you; **Idol Nullifier** (extended) cancels an idol

**Elimination & ties (official):**
- *Single Elimination* — most votes is voted out
- *Double Elimination* — most votes **and** second-most votes are both voted out
- Tied or unclear results resolve through the official ladder, ending with the Council Leader's decision where the Guide says so

Being voted out turns over one Survivor Character Card. Lose both and you're eliminated — and join the **Jury**.

### Reward Challenges — real multiplayer minigames
These resolve as live interactions on everyone's phones, not dice rolls:
- **Do Or Die** — actual rock-paper-scissors throws between you and your target; winner steals 2 cards
- **Power Pair** — three players secretly show 1–5 fingers; anyone pairing with you hands over cards
- **It's A Numbers Game** — everyone secretly picks a number; the odd one out pays the price

### Final Tribal & winning
When **2 players remain**, Final Tribal begins: the Jury asks its questions, then votes for who **should win**. Most jury votes = **Sole Survivor**, carved into the Hall of Fame.

---

## Let's Go To Rocks (expansion)

Toggle on at game creation. Adds the **5 orange Challenge Cards** and the **Immunity Idol Necklace**:

| Challenge | How it plays digitally |
|-----------|------------------------|
| Lowest Score Loses | Every player pulls rocks from a shared bag — lowest total loses |
| Pull or Steal | Pull from the bag, or steal a rival's pull |
| 1 Now or 2 Later | Take one rock now, or gamble on two later |
| Highest Bidder | Open bidding on the bag's contents |
| Hide 'n' Seek | *Not available digitally* (physical sleight-of-hand) — the card explains itself |

The Challenge winner **wears the Necklace** (immune to votes) until the next Tribal Council ends. Win a Challenge while already wearing it and you take **3 cards from the Draw Pile** instead. Secret information (bag contents, hidden pulls) never leaves the server.

---

## Card Reference

Counts are per the card registry (`survivor_cards.json`). *(Extended)* marks house cards outside the official 67.

### Vote Cards
| Card | Count | Effect |
|------|-------|--------|
| Vote | 6 | Dealt 1 per player at setup. MUST be cast at Tribal Council |
| Extra Vote | 7 | An additional vote — cast it or save it |

### Tribal Advantage Cards
| Card | Count | Effect |
|------|-------|--------|
| Hidden Immunity Idol | 4 | Negate all votes against you at Tribal Council |
| Goodwill Gamble | 3 | Give to another player before voting; counts as 1 vote and MUST be used at that Tribal |
| Control The Vote | 2 | Choose the next Council Leader |
| I'm The Leader Now | 1 | Become the Council Leader immediately |
| Idol Nullifier *(Extended)* | 2 | Cancel someone's played idol |
| Steal A Vote *(Extended)* | 2 | Take another player's vote; they can't vote, you vote twice |
| Block A Vote *(Extended)* | 2 | Block a player's vote at this Tribal |
| Grant Immunity *(Extended)* | 1 | Make a player immune this Tribal |

### Action Cards
| Card | Count | Effect |
|------|-------|--------|
| Sorry For You | 7 | REACTIVE — when someone tries to take your cards: they get nothing and discard 1 |
| Inheritance | 6 | Mark a player — when they're eliminated, you inherit their cards |
| Let's Form An Alliance | 4 | You and an ally each steal a card from a victim |
| Camp Raid | 3 | Steal 2 random cards from a target |
| The Spy Shack | 3 | Look at a player's hand and take one card |
| Knowledge Is Power | 3 | Name a card type — if the target holds it, it's yours |
| Reward Challenge: Do Or Die | 3 | Live rock-paper-scissors; winner steals 2 |
| Reward Challenge: Power Pair | 3 | Live finger match with two rivals |
| Reward Challenge: It's A Numbers Game | 3 | Live secret number pick |

### Tribal Council Cards
| Card | Count |
|------|-------|
| Single Elimination | 4 |
| Double Elimination | 5 |

Distribution scales by player count (3 players: 4 single / 0 double … 6 players: 0 single / 5 double).

---

## The Interface

- **TORCHLIT design** — a night-on-the-island look (Fraunces + Alegreya Sans, OKLCH fire palette). The whole app shifts atmosphere with the game: ember-red for Tribal Council, jury gold for Final Tribal, dawn for victory
- **Hand grid + card sheet** — your whole hand is visible at once as named mini-cards; playable cards glow **NOW**. Tap a card for its full rules, timing, and the *Play This Card* button — no card ever leaves your hand on a single stray tap
- **Narrator** — dramatic, optional-sound commentary on every major event
- **Phase guidance** — a strip at the top always says whose moment it is and what to do
- **PWA** — add to home screen (the icon is the torch); runs standalone, auto-reconnects, keeps working through brief drops

---

## Hosting Your Own Server

### Local / LAN play
```bash
git clone https://github.com/tylermcrae7/survivor-game.git
cd survivor-game
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python survivor_server.py        # serves on http://localhost:8080
```
`PORT` overrides the port. Anyone on your Wi-Fi can join via your machine's LAN IP.

### Production (always-on Mac + Cloudflare Tunnel)
The `deploy/` folder holds the full pattern used for the live deployment:

- **`deploy/setup.sh`** — one-time install: creates a named Cloudflare Tunnel to your domain, installs two LaunchAgents (server + tunnel) so both start at boot, and generates an access code
- **`deploy/redeploy.sh`** — every subsequent release: rsyncs the repo to `~/srv/survivor-game` (excluding live game state) and bounces the server

> **macOS note:** launchd services cannot read `~/Documents` (TCC privacy protection blocks them silently — the server just hangs). That's why the live copy runs from `~/srv/`, and why you should too.

### Access gate (optional, recommended for public URLs)
Set `SURVIVOR_ACCESS_CODE` in the server's environment to code-lock the island:

- Every device enters the code once ("Speak the code to come ashore"); a signed HttpOnly cookie remembers it
- Every API call **and** websocket handshake is refused without it; per-IP rate limiting slows guessing
- Change the env value to instantly revoke every device
- Leave it unset and the gate disappears entirely — LAN play and development are unaffected

No accounts, no passwords, nothing stored about players.

---

## Technical Architecture

- **Backend:** Python Flask + Flask-SocketIO (gevent), JSON-file persistence with atomic writes and corruption recovery
- **Frontend:** vanilla JavaScript modules, no build step — what's in `client/dist/` is what ships
- **Real-time:** Socket.IO room per game; every state change pushes to every phone
- **Secrecy:** hidden information (Challenge bags, secret picks, pending interactions) lives in server-only state that is stripped before any client ever sees it

```
survivor-game/
├── survivor_server.py       # Flask server: routes, GameState, persistence, access gate
├── rules_engine.py          # Official rules: deck building, card effects, vote economy, ties
├── challenges.py            # Let's Go To Rocks challenge engine
├── interactions.py          # Reward Challenge multiplayer interaction engine
├── survivor_cards.json      # Card registry (single source of truth)
├── client/dist/             # The whole frontend (HTML/CSS/JS/PWA, no build step)
├── deploy/                  # Production setup + redeploy scripts, LaunchAgent templates
├── tests/                   # 19 suites, ~200 tests + live end-to-end harnesses
├── ios/                     # Native SwiftUI companion app (Xcode project)
└── docs/                    # Rules reference, design docs, progress log, screenshots
```

---

## Testing

```bash
.venv/bin/python run_all_tests.py          # 19 suites, ~200 tests
```

End-to-end harnesses drive a real running server through complete games (turns, thefts, Tribals, ties, Challenges, Final Tribal):

```bash
PORT=8099 .venv/bin/python survivor_server.py &          # scratch server
SURVIVOR_TEST_BASE=http://localhost:8099 \
  .venv/bin/python tests/e2e/e2e_api_live_test.py
SURVIVOR_TEST_BASE=http://localhost:8099 \
  .venv/bin/python tests/e2e/scripted_full_games.py
```

Run e2e against a **scratch server**, not your live one — the harnesses play games to completion. (They do scrub their own recorded wins from the Hall of Fame afterwards, so test victories never pollute the real record.)

---

## Remote Play Tips

- Share the fire code straight from the lobby (**Copy** / **Share** buttons)
- Pair the game with a video call for alliance whispering — the app runs the cards and votes, the call runs the scheming
- All phones stay in sync in real time; a phone that sleeps through something catches up the moment it wakes

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Connection lost" | It auto-reconnects; refresh if it lingers |
| "Game not found" | Check the code — or someone burned the game down |
| Stuck on an old look after an update | Refresh once; the service worker hands over the new version in the background |
| Old app icon on your home screen | Remove and re-add the bookmark (iOS caches icons with the bookmark) |
| Can't play a card | Tap it — the card sheet tells you exactly when it's playable |
| Access code rejected | Codes are case-insensitive; ask your host — they can read it from the server config |

---

## Credits

Based on **Survivor: The Tribe Has Spoken** by Exploding Kittens.
Survivor TM & © Survivor Productions, LLC.

This is a fan project for personal use. All Survivor intellectual property belongs to its respective owners.
