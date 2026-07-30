#!/usr/bin/env python3
"""
Two scripted full games over the live HTTP API, as the final acceptance check.

  1. A 3-player OFFICIAL game played to a Sole Survivor, verifying: character-card
     lives 2 -> 1 -> 0, Vote Cards consumed and returned each tribal, Final Tribal
     firing the moment 2 players remain, the jury vote, and the winner recorded.

  2. An EXPANSION game exercising at least 2 Challenges and the Immunity Idol
     Necklace blocking a vote at a Tribal Council.

Requires a running server:  .venv/bin/python survivor_server.py   (port 8080)
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

# Cookie-aware opener: when the target server is code-locked (SURVIVOR_ACCESS_CODE
# set on it, e.g. the live tunnel deployment), the gate cookie from /api/access
# must ride on every request.
_cookies = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookies))
urllib.request.install_opener(_opener)


def _unlock_gate(base):
    """If the server is gated, unlock with the code from env or ~/.survivor-access-code."""
    try:
        with urllib.request.urlopen(base + "/api/access/check", timeout=10) as r:
            check = json.loads(r.read().decode())
    except Exception:
        return  # server not up yet; the first real check will say so
    if not check.get("gated") or check.get("ok"):
        return
    code = os.environ.get("SURVIVOR_ACCESS_CODE", "").strip()
    if not code:
        code_file = os.path.expanduser("~/.survivor-access-code")
        if os.path.exists(code_file):
            code = open(code_file).read().strip()
    if not code:
        print("FATAL: server is code-locked and no access code found "
              "(set SURVIVOR_ACCESS_CODE or ~/.survivor-access-code)")
        sys.exit(2)
    req = urllib.request.Request(base + "/api/access",
                                 data=json.dumps({"code": code}).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        reply = json.loads(r.read().decode())
    if not reply.get("success"):
        print(f"FATAL: access code rejected: {reply.get('message')}")
        sys.exit(2)
    print("(access gate unlocked for this test run)")

# Override with SURVIVOR_TEST_BASE to run against a scratch server instead of :8080
BASE = os.environ.get("SURVIVOR_TEST_BASE", "http://localhost:8080").rstrip("/")
_unlock_gate(BASE)
failures = []


def log(msg):
    print(msg, flush=True)


def expect(label, ok, detail=""):
    if ok:
        log(f"    ✓ {label}" + (f" — {detail}" if detail else ""))
    else:
        failures.append(label)
        log(f"    ✗ {label} — {detail}")
    return ok


# Games this run creates — their recorded wins get scrubbed at the end so
# scripted victories never pollute the real Hall of Fame.
CREATED_GAMES = set()

def api(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 method=method or ("POST" if data is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            status, reply = r.status, json.loads(r.read().decode())
            if path == "/api/game/create" and isinstance(reply, dict) and reply.get("gameId"):
                CREATED_GAMES.add(reply["gameId"])
            return status, reply
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def state(gid):
    _, s = api(f"/api/game/{gid}/state", method="GET")
    return s if isinstance(s, dict) else {}



def _leader(gid):
    """The current Council Leader's id — tribal controls are leader-only now."""
    g = state(gid)
    return (g.get("currentVote") or {}).get("councilLeaderId")

def name(game, pid):
    return game["players"].get(pid, {}).get("name", pid)


def alive(game):
    return [p for p in game["turnOrder"] if not game["players"][p].get("isEliminated")]


def new_game(names, deck_mode="official", expansion=False):
    _, resp = api("/api/game/create", {"deckMode": deck_mode, "expansion": expansion})
    gid = resp["gameId"]
    pids = {}
    for n in names:
        _, r = api("/api/player/join", {"gameId": gid, "name": n})
        pids[n] = r["playerId"]
    _, r = api("/api/game/start_full", {"gameId": gid})
    assert r.get("success"), r
    return gid, pids


def take_turn(gid):
    """Steal then draw for the current player. Returns (state, tribal_triggered)."""
    game = state(gid)
    cp = game["turnOrder"][game.get("currentTurnIndex", 0)]
    victim = next(p for p in alive(game) if p != cp)
    api("/api/turn/steal", {"gameId": gid, "thiefId": cp, "targetId": victim})
    api("/api/reactive/complete_theft", {"gameId": gid})
    _, resp = api("/api/turn/draw", {"gameId": gid, "playerId": cp})
    if resp.get("tribal_triggered"):
        return state(gid), True
    api("/api/turn/advance", {"gameId": gid})
    return state(gid), False


def run_tribal(gid, target):
    """Full tribal council voting `target` out. Returns (state, voted_out, returned)."""
    game = state(gid)
    leader = game["currentVote"]["councilLeaderId"]
    log(f"    tribal council — leader {name(game, leader)}, "
        f"{game['currentVote']['type']} elimination, target {name(game, target)}")

    api("/api/vote/start", {"gameId": gid, "voteType": "elimination", "playerId": _leader(gid)})
    game = state(gid)

    spent = 0
    necklace = game.get("necklaceHolder")
    for voter in alive(game):
        votes = max(1, game["players"][voter].get("mandatoryVotes", 1))
        # Legal targets only: alive, not self, not the Necklace wearer
        options = [p for p in alive(game) if p != voter and p != necklace]
        preferred = [p for p in options if p == target] + [p for p in options if p != target]
        placed = False
        for vote_for in preferred:
            _, r = api("/api/vote/cast", {"gameId": gid, "voterId": voter,
                                          "votesData": [{"targetId": vote_for, "votes": votes}]})
            if r.get("success"):
                spent += votes
                placed = True
                break
            if "no Vote Card" in str(r.get("message", "")):
                _, r = api("/api/vote/cast", {"gameId": gid, "voterId": voter, "votesData": []})
                placed = bool(r.get("success"))
                break
        if not placed:
            # Last resort: pass the box so the tally can proceed
            api("/api/vote/cast", {"gameId": gid, "voterId": voter, "votesData": []})

    after_voting = state(gid)
    left_in_hands = sum(1 for p in after_voting["players"].values()
                        for c in p["hand"] if c["type"] == "vote")

    api("/api/tribal/advance", {"gameId": gid, "phase": "immunity", "playerId": _leader(gid)})
    api("/api/vote/reveal", {"gameId": gid, "playerId": _leader(gid)})
    game = state(gid)
    cv = game["currentVote"]
    log(f"      votes: { {name(game, k): v for k, v in cv.get('voteResults', {}).items()} } — {cv.get('resolution')}")
    if cv.get("tieBreakNeeded"):
        api("/api/vote/tiebreak", {"gameId": gid, "leaderId": cv["councilLeaderId"],
                                   "chosenId": target})
        game = state(gid)
        cv = game["currentVote"]
    voted_out = list(cv.get("eliminated", []))

    _, done = api("/api/tribal/complete", {"gameId": gid, "playerId": _leader(gid)})
    assert done.get("success"), done
    after = state(gid)
    returned = {name(after, pid): sum(1 for c in p["hand"] if c["type"] == "vote")
                for pid, p in after["players"].items() if not p.get("isEliminated")}
    return after, voted_out, (spent, left_in_hands, returned)


# ═════════════════════════ GAME 1 — official 3 players ═════════════════════════

log("\n" + "=" * 78)
log("GAME 1 — scripted 3-player OFFICIAL game to a Sole Survivor")
log("=" * 78)

gid, pids = new_game(["Alice", "Bob", "Cara"])
g = state(gid)
log(f"  game {gid} — deck {len(g['deck'])} cards, mode {g['deckMode']}, expansion {g['expansion']}")

expect("every player starts with 2 Survivor Character Cards",
       all(p["characterCards"] == 2 for p in g["players"].values()),
       {p["name"]: p["characterCards"] for p in g["players"].values()})
expect("every player is dealt 3 action cards + exactly 1 Vote Card",
       all(len(p["hand"]) == 4 and sum(1 for c in p["hand"] if c["type"] == "vote") == 1
           for p in g["players"].values()),
       {p["name"]: [c["type"] for c in p["hand"]] for p in g["players"].values()})

lives_seen = {}          # pid -> list of card counts observed after each vote-out
tribals = 0
turns = 0

while g.get("phase") in ("playing", "tribal_council") and turns < 600:
    if g["phase"] == "playing":
        g, triggered = take_turn(gid)
        turns += 1
        if not triggered:
            continue

    tribals += 1
    # Always target whoever is closest to elimination so the game converges
    order = alive(g)
    target = min(order, key=lambda p: g["players"][p]["characterCards"])
    before = g["players"][target]["characterCards"]

    g, voted_out, (spent, left, returned) = run_tribal(gid, target)

    for pid in voted_out:
        player = g["players"][pid]
        lives_seen.setdefault(pid, []).append(player["characterCards"])
        log(f"      {name(g, pid)} voted out: {before if pid == target else '?'} -> "
            f"{player['characterCards']} card(s)"
            + (" — ELIMINATED, joins the jury" if player["isEliminated"] else " — still in the game"))

    expect(f"tribal {tribals}: all Vote Cards were spent",
           left == 0, f"{left} still in hands after voting")
    expect(f"tribal {tribals}: 1 Vote Card returned to each surviving player",
           all(v == 1 for v in returned.values()), returned)

g = state(gid)
log(f"  {tribals} tribal councils, {turns} turns")

full_arc = [pid for pid, seen in lives_seen.items() if seen and seen[-1] == 0]
expect("at least one player went 2 -> 1 -> 0 character cards",
       any(len(seen) >= 2 and seen[0] == 1 and seen[-1] == 0 for seen in lives_seen.values()),
       {name(g, k): v for k, v in lives_seen.items()})
expect("eliminated players are exactly the jury",
       sorted(g["jury"]) == sorted(pid for pid, p in g["players"].items() if p["isEliminated"]),
       g["jury"])
expect("final tribal fired with exactly 2 players left",
       g["phase"] in ("final_tribal", "final") and len(alive(g)) == 2,
       f"phase={g['phase']} alive={[name(g, p) for p in alive(g)]}")

ft = g.get("finalTribal", {})
expect("the official three final-tribal questions are asked",
       ft.get("questions") == ["What was your strategy coming into the game?",
                               "What was your best move in the game?",
                               "How did you outplay your opponent?"],
       ft.get("questions"))
expect("the most recently eliminated player is the Final Tribal Council Leader",
       ft.get("leader") == g["jury"][-1], name(g, ft.get("leader", "")))

_, r = api("/api/final/advance", {"gameId": gid, "phase": "voting"})
expect("final tribal advances to voting", r.get("success"), r.get("message"))

finalists = ft["finalists"]
for juror in ft["jury"]:
    _, r = api("/api/final/vote", {"gameId": gid, "juryMemberId": juror,
                                   "finalistId": finalists[0]})
g = state(gid)
ft = g["finalTribal"]
log(f"  jury vote: { {name(g, k): name(g, v) for k, v in ft['votes'].items()} }")
expect("jury vote produces a winner", ft.get("winner") == finalists[0],
       f"winner={name(g, ft.get('winner', ''))} counts={ft.get('voteCounts')}")

_, r = api("/api/game/finish", {"gameId": gid, "winnerId": finalists[0]})
expect("winner recorded", r.get("success"), r.get("message"))
_, winners = api("/api/winners", method="GET")
winner_name = name(g, finalists[0])
expect("winner appears in the hall of fame",
       any(w.get("winner_name") == winner_name for w in (winners or [])), winner_name)
log(f"  🏆 Sole Survivor: {winner_name}")


# ═════════════════════════ GAME 2 — expansion ═════════════════════════

log("\n" + "=" * 78)
log("GAME 2 — scripted EXPANSION game: challenges + Immunity Idol Necklace")
log("=" * 78)


def drive_challenge(gid):
    """Play the active challenge to completion using only legal actions."""
    game = state(gid)
    ch = game.get("challenge") or {}
    steps = 0
    while ch and ch.get("phase") != "complete" and steps < 400:
        steps += 1
        actions = ch.get("actions") or []
        if not actions:
            break
        action, value = actions[0], None
        if action == "bid":
            nxt = ch.get("currentBid", 0) + 1
            if nxt > ch.get("maxBid", nxt) and "pass" in actions:
                action = "pass"
            else:
                value = nxt
        elif action == "pull" and ch["type"] == "lowest_score_loses":
            value = 1
        elif action == "steal":
            value = (ch.get("stealTargets") or [None])[0]
            if not value:
                action = "pull"
        _, r = api("/api/challenge/action", {"gameId": gid, "playerId": ch["currentPlayerId"],
                                             "action": action, "value": value})
        if not r.get("success"):
            log(f"      illegal move rejected: {action}({value}) — {r.get('message')}")
            break
        game = state(gid)
        ch = game.get("challenge") or {}
    return game, ch


challenges_run = []
necklace_blocked = False
egid, epids = new_game(["Dana", "Eli", "Fern", "Gus"], expansion=True)
eg = state(egid)
in_play = [c["type"] for c in eg["deck"] if c["type"].startswith("challenge_")]
in_play += [c["type"] for p in eg["players"].values() for c in p["hand"]
            if c["type"].startswith("challenge_")]
expect("all 5 Orange Challenge Cards are in the expansion game", len(in_play) == 5, sorted(in_play))
expect("the Necklace starts on the table", eg.get("necklaceHolder") is None)

for attempt in range(8):
    if len(challenges_run) >= 2 and necklace_blocked:
        break
    if attempt:
        egid, epids = new_game(["Dana", "Eli", "Fern", "Gus"], expansion=True)
        log(f"  (previous game ended; starting expansion game {egid})")

    eg = state(egid)
    turns = 0
    while eg.get("phase") in ("playing", "tribal_council") and turns < 400:
        turns += 1

        if eg["phase"] == "tribal_council":
            wearer = eg.get("necklaceHolder")
            if wearer and not necklace_blocked:
                api("/api/vote/start", {"gameId": egid, "voteType": "elimination", "playerId": _leader(egid)})
                eg = state(egid)
                voter = next(p for p in alive(eg) if p != wearer)
                _, r = api("/api/vote/cast", {"gameId": egid, "voterId": voter,
                                              "votesData": [{"targetId": wearer, "votes": 1}]})
                necklace_blocked = expect(
                    "a vote for the Necklace wearer is rejected at Tribal Council",
                    not r.get("success") and "Necklace" in str(r.get("message", "")),
                    r.get("message"))
            order = alive(eg)
            candidates = [p for p in order if p != eg.get("necklaceHolder")] or order
            victim = max(candidates, key=lambda p: eg["players"][p]["characterCards"])
            eg, _, _ = run_tribal(egid, victim)
            if eg.get("necklaceHolder") is None:
                expect("the Necklace returns to the table when the Tribal Council ends", True)
            continue

        cp = eg["turnOrder"][eg.get("currentTurnIndex", 0)]
        hand = eg["players"][cp]["hand"]
        playable = next((i for i, c in enumerate(hand)
                         if c["type"].startswith("challenge_")
                         and c["type"] != "challenge_hide_n_seek"), None)
        if playable is None:
            eg, _ = take_turn(egid)
            continue

        # Steal first so the play phase is legal, then play the Challenge Card
        victim = next(p for p in alive(eg) if p != cp)
        api("/api/turn/steal", {"gameId": egid, "thiefId": cp, "targetId": victim})
        api("/api/reactive/complete_theft", {"gameId": egid})
        eg = state(egid)
        hand = eg["players"][cp]["hand"]
        playable = next((i for i, c in enumerate(hand)
                         if c["type"].startswith("challenge_")
                         and c["type"] != "challenge_hide_n_seek"), None)
        if playable is None:
            eg, _ = take_turn(egid)
            continue

        holder_before = eg.get("necklaceHolder")
        _, r = api("/api/turn/play_card", {"gameId": egid, "playerId": cp, "cardIdx": playable})
        if not r.get("success"):
            log(f"      challenge play rejected: {r.get('message')}")
            eg, _ = take_turn(egid)
            continue

        eg = state(egid)
        ch = eg.get("challenge") or {}
        log(f"    🪨 {ch.get('name')} started by {name(eg, cp)} "
            f"({len(ch.get('order', []))} participants, bag {ch.get('bag')})")

        outsider = next((p for p in ch["order"] if p != ch["currentPlayerId"]), None)
        if outsider:
            _, bad = api("/api/challenge/action", {"gameId": egid, "playerId": outsider,
                                                   "action": "pull"})
            expect(f"{ch['name']}: out-of-turn action rejected", not bad.get("success"),
                   bad.get("message"))
        expect(f"{ch['name']}: secret rock pulls never leave the server",
               not [k for k in ch if k.startswith("_")], list(ch)[:10])

        eg, ch = drive_challenge(egid)
        winner = ch.get("winnerId")
        expect(f"{ch.get('name')}: completed with exactly one winner",
               ch.get("phase") == "complete" and bool(winner), ch.get("prompt"))
        log(f"      winner: {name(eg, winner)}")

        if holder_before is None:
            expect(f"{ch.get('name')}: winner wears the Immunity Idol Necklace",
                   eg.get("necklaceHolder") == winner, name(eg, eg.get("necklaceHolder", "")))
        else:
            expect("Necklace already worn → winner takes 3 cards from the Draw Pile instead",
                   eg.get("necklaceHolder") == holder_before
                   and "3 random cards" in " ".join(ch.get("log", [])[-3:]),
                   ch.get("log", [])[-1:])

        challenges_run.append(ch.get("type"))
        api("/api/challenge/action", {"gameId": egid, "playerId": winner, "action": "dismiss"})
        api("/api/turn/draw", {"gameId": egid, "playerId": cp})
        api("/api/turn/advance", {"gameId": egid})
        eg = state(egid)

        if len(challenges_run) >= 2 and necklace_blocked:
            break

expect("at least 2 Challenges were played", len(challenges_run) >= 2, challenges_run)
expect("the Necklace blocked a vote at a Tribal Council", necklace_blocked)

# Scrub this run's wins from the Hall of Fame
try:
    _, records = api("/api/winners/records", method="GET")
    scrubbed = 0
    for rec in (records if isinstance(records, list) else []):
        if isinstance(rec, dict) and rec.get("game_id") in CREATED_GAMES and rec.get("id"):
            _, resp = api("/api/winners/delete", {"id": rec["id"]})
            if resp.get("success"):
                scrubbed += 1
    if scrubbed:
        log(f"(scrubbed {scrubbed} test win(s) from the Hall of Fame)")
except Exception as e:
    log(f"(warning: could not scrub test wins: {e})")

log("\n" + "=" * 78)
if failures:
    log(f"❌ {len(failures)} check(s) failed:")
    for f in failures:
        log(f"   - {f}")
    sys.exit(1)
log("✅ Both scripted games completed with every check passing")
sys.exit(0)
