# Voice, and the places people stand in

Remote play needs two things the game never had: a way to talk, and a way to
*stop* talking to everyone at once. Survivor runs on the second one — the show is
made of two people wandering off to the water well while everyone else watches
them go.

## The shape of it

The game server owns **places**. Discord carries **audio**. Neither knows much
about the other.

```
iOS app  ─┐                            ┌─ Discord bot ──→ Discord voice channels
          ├──→ survivor_server.py ─────┤   (see CODEX-DISCORD-BOT.md)
web app  ─┘     places.py is the truth └── polls /api/voice/plan
```

The important property: **the bot is a mirror, not a dependency.** With no bot
running, no Discord account, and no microphone, the app still shows that Coconut
and Driftwood have slipped off to The Beach together. That visibility *is* the
feature; voice is what makes it fun.

## The places

| key | label | open during |
|---|---|---|
| `camp_fire` | Camp Fire | always — the default gathering |
| `the_beach` | The Beach | `playing` |
| `the_water_well` | The Water Well | `playing` |
| `tribal_council` | Tribal Council | `tribal_council`, `final_tribal` (forced) |

Policy is **derived from the game phase**, never stored:

| phase | open | forced |
|---|---|---|
| `lobby` | Camp Fire | Camp Fire |
| `playing` | Camp Fire, Beach, Water Well | — |
| `tribal_council` | Tribal Council | Tribal Council |
| `final_tribal` | Tribal Council | Tribal Council |
| `finished` | Camp Fire | Camp Fire |

`game["phase"]` is assigned in nine different places in `survivor_server.py`, so
hooking every transition would rot the first time someone adds a tenth. Instead
`places.effective_place()` computes it: the player's stored choice, overridden by
the policy. Correct by construction, including for transitions written later.

## Why private talk is public

Everyone can see who is standing where. This is deliberate and it is the whole
design:

- **It's the paranoia engine.** "Why are those two at the well *again*?" is the
  richest thing this game generates. Hiding it would delete the feature to
  protect a privacy nobody asked for.
- **Hiding creates unfalsifiable claims.** Survivor thrives on deniable
  *content*, not deniable *contact*. "I never talked to her" should be checkable;
  what was said should not.
- **It's the only moderation available.** Six friends, no admin, unloggable
  audio. You cannot police a private conversation — but you can make it
  observable, and observability is what keeps it honest.

Anyone can follow you to the beach. That's not a leak, it's the show.

## For the same reason, whispers should not be logged

If in-app text whispers ever get built, make them **ephemeral**. Persisting them
turns "you promised me" into a receipt and quietly converts Survivor into a
legalistic game. The persistence is the easy part; wanting it is the mistake.

## API

Both routes sit behind the usual access gate.

**`POST /api/place/move`** — `{gameId, playerId, place}` → `{success, message, place, gameState}`.
Rejected when `placePolicy.forced` is set or the place isn't in `placePolicy.open`.
Moves are deliberately kept out of the event log; the log caps at 120 entries and
someone pacing between the beach and the well would erase the game's history.

**`GET /api/voice/active`** — games worth mirroring: not finished, touched in the
last 24 hours, at least one human with a linked Discord ID.

**`GET /api/voice/plan/<gameId>`** — the bot's whole view, with a 12-character
content-hash `version` so it can poll cheaply and act only on change. Every place
key always appears. Computer players are excluded; eliminated players are not —
they become the jury and still belong somewhere.

Game state also gains `players[pid].place`, `players[pid].discordUserId`, and a
top-level `placePolicy`, so both clients get all of this from the broadcast they
already receive.

## Linking a person to a Discord account

Each player pastes their Discord user ID once, in **Settings → Discord user ID**
(Discord → Settings → Advanced → Developer Mode, then long-press your own name →
Copy User ID). It rides along on join. A player who never links it stays
invisible to the bot and simply moves themselves — everything else still works.

IDs are validated as 15–25 digit strings and must arrive **quoted**. A Discord
snowflake exceeds 2^53, so a JavaScript client that sent one as a JSON number has
already corrupted it; the server refuses rather than silently storing garbage.

## Why Discord, and not voice in the app

Ten comparable games were surveyed. Seven deliberately never built voice —
including every discussion-driven browser game (Jackbox, Codenames, Wavelength,
netgames.io) and *Among Us*, the biggest social-deduction game there is. The
three that did build it had a studio, a subscription, or a single platform.

Building it here would mean: a WebRTC stack on two clients, a TURN server the
Cloudflare tunnel cannot host, `.playAndRecord` on iOS (which stops the silent
switch from muting the game), echo cancellation that needs an API gated to 2024+
iPhones, an age rating off 4+, export-compliance paperwork, and App Store
Guideline 1.2 obligations the moment it ships publicly — to replace something
Discord already does better, for free, for six people who are already in a group
chat together.

The full research is in this conversation's history; `CODEX-DISCORD-BOT.md` is
the buildable half.

## Status

- ✅ Places model, policy, and both endpoints — `places.py`, `survivor_server.py`
- ✅ iOS: places panel, Discord ID setting
- ✅ Web: places panel, Discord ID setting
- ⬜ The Discord bot — see `CODEX-DISCORD-BOT.md`

Before writing the bot, play one game with the four channels created and everyone
hopping manually. If the room metaphor feels good, the bot is a weekend. If it
doesn't, you've learned that for free.
