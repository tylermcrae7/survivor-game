#!/usr/bin/env python3
"""
E2E test of survivor_server.py via its real HTTP API (the same calls network.js makes).

Requires a running server:  .venv/bin/python survivor_server.py   (port 8080)

Covers the official rules end to end: setup and deck composition, the mandatory
Steal -> Play -> Draw order, the vote-card economy, the Survivor Character Card
lives system, the tie-break cascade, final tribal, and the Let's Go To Rocks
expansion (challenges + Immunity Idol Necklace).
"""
import http.cookiejar
import json
import os
import sys
import urllib.error
import time
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
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ((" — " + str(detail)[:200]) if detail else ""))


# Every game this run creates — used to scrub its recorded wins afterwards,
# so test victories never pollute the real Hall of Fame.
CREATED_GAMES = set()

def api(path, body=None, method=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
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
    st, s = api(f"/api/game/{gid}/state", method="GET")
    return s if isinstance(s, dict) else {}


def alive(game):
    return [pid for pid, p in game["players"].items() if not p.get("isEliminated")]


def cast_all_votes(gid, game, target, skip=()):
    """Every player still in the game casts all the votes they hold."""
    order = [p for p in game["turnOrder"] if not game["players"][p].get("isEliminated")]
    ok = []
    for voter in order:
        if voter in skip:
            continue
        vote_for = target if voter != target else next(p for p in order if p != target)
        votes = max(1, game["players"][voter].get("mandatoryVotes", 1))
        st, resp = api("/api/vote/cast", {"gameId": gid, "voterId": voter,
                                          "votesData": [{"targetId": vote_for, "votes": votes}]})
        if resp.get("success"):
            ok.append(True)
            continue
        message = str(resp.get("message", ""))
        if "no Vote Card" in message:
            # Their Vote Card was stolen during play — passing the box is legal.
            print(f"   {game['players'][voter]['name']} has no Vote Card, passes")
            api("/api/vote/cast", {"gameId": gid, "voterId": voter, "votesData": []})
            ok.append(True)
            continue
        print(f"   vote fail {game['players'][voter]['name']}: {message}")
        ok.append(False)
    return all(ok)


def run_tribal(gid, target):
    """Run a complete tribal council that votes `target` out. Returns the final state."""
    game = state(gid)
    api("/api/vote/start", {"gameId": gid, "voteType": "elimination"})
    game = state(gid)
    cast_all_votes(gid, game, target)
    api("/api/tribal/advance", {"gameId": gid, "phase": "immunity"})
    api("/api/vote/reveal", {"gameId": gid})
    game = state(gid)
    cv = game.get("currentVote", {})
    if cv.get("tieBreakNeeded"):
        api("/api/vote/tiebreak", {"gameId": gid, "leaderId": cv.get("councilLeaderId"),
                                   "chosenId": target})
    voted_out = list(state(gid).get("currentVote", {}).get("eliminated", []))
    api("/api/tribal/complete", {"gameId": gid})
    return state(gid), voted_out


def play_turn(gid, game):
    """Steal, then draw, for whoever's turn it is. Returns (state, tribal_triggered)."""
    order = game["turnOrder"]
    cp = order[game.get("currentTurnIndex", 0)]
    victim = next(p for p in order if p != cp and not game["players"][p].get("isEliminated"))
    api("/api/turn/steal", {"gameId": gid, "thiefId": cp, "targetId": victim})
    st, resp = api("/api/reactive/complete_theft", {"gameId": gid})  # no-op if no window
    st, resp = api("/api/turn/draw", {"gameId": gid, "playerId": cp})
    triggered = bool(resp.get("tribal_triggered"))
    if not triggered:
        api("/api/turn/advance", {"gameId": gid})
    return state(gid), triggered


# ══════════════════════════════ 1. server basics ══════════════════════════════

try:
    with urllib.request.urlopen(BASE + "/", timeout=10) as r:
        html = r.read().decode()
        check("index_serves", r.status == 200 and len(html) > 5000)
        check("no_https_redirect_wedge", "location.replace('https" not in html,
              "inline force-HTTPS redirect must stay removed (F4)")
        check("deck_options_in_ui", "deckModeSelect" in html and "expansionToggle" in html)
        check("challenge_panel_in_ui", "challengePanel" in html and "livesTracker" in html)
except Exception as e:
    check("index_serves", False, e)

st, resp = api("/api/cards", method="GET")
cards = resp.get("cards", {}) if isinstance(resp, dict) else {}
check("cards_endpoint", st == 200 and bool(cards), f"{len(cards)} card types")
official = sum(c["count"] for t, c in cards.items()
               if c.get("official") is not False and c["category"] != "challenge")
check("official_deck_is_67_cards", official == 67, official)
check("cards_metadata_not_claiming_74_official",
      resp.get("metadata", {}).get("official_action_cards") == 67,
      resp.get("metadata", {}).get("source"))

st, resp = api("/api/game/1234/state", method="GET")
check("unknown_game_404s", st == 404, st)

# ══════════════════════════ 2. official 3-player game ══════════════════════════

st, resp = api("/api/game/create", {"deckMode": "official", "expansion": False})
gid = resp.get("gameId")
check("create_game", st == 200 and bool(gid), resp.get("message", ""))
check("create_game_reports_deck_mode", resp.get("deckMode") == "official", resp)
if not gid:
    sys.exit(1)

pids = {}
for name in ("Alice", "Bob", "Cara"):
    st, resp = api("/api/player/join", {"gameId": gid, "name": name})
    if resp.get("success"):
        pids[name] = resp["playerId"]
    else:
        print("   join fail:", name, resp)
check("three_players_join", len(pids) == 3, pids)
alice, bob, cara = pids["Alice"], pids["Bob"], pids["Cara"]

st, resp = api("/api/player/join", {"gameId": gid, "name": ""})
check("empty_name_rejected", not resp.get("success"), resp.get("message"))
st, resp = api("/api/player/join", {"gameId": gid, "name": "Alice"})
check("duplicate_name_rejected", not resp.get("success"), resp.get("message"))

st, resp = api("/api/game/start_full", {"gameId": gid})
check("start_game", resp.get("success"), resp.get("message", ""))

g = state(gid)
players = g.get("players", {})
check("state_fetch", bool(players), list(g.keys())[:12])

# ── setup composition (official rules steps 2-5) ──
hand_sizes = {p["name"]: len(p.get("hand", [])) for p in players.values()}
check("initial_hand_is_3_action_plus_1_vote", all(v == 4 for v in hand_sizes.values()), hand_sizes)
vote_counts = {p["name"]: sum(1 for c in p.get("hand", []) if c.get("type") == "vote")
               for p in players.values()}
check("exactly_one_vote_card_each", all(v == 1 for v in vote_counts.values()), vote_counts)
check("no_vote_cards_left_in_deck",
      not [c for c in g.get("deck", []) if c.get("type") == "vote"],
      "official setup removes the 6 Vote Cards from the deck")
check("no_tribal_cards_dealt_into_hands",
      not [c for p in players.values() for c in p.get("hand", [])
           if str(c.get("type", "")).startswith("tribal_council")],
      "deal happens before the tribal cards are assembled in")

lives = {p["name"]: p.get("characterCards") for p in players.values()}
check("two_character_cards_each", all(v == 2 for v in lives.values()), lives)

tribal_types = {}
for c in g.get("deck", []):
    t = c.get("type", "")
    if t.startswith("tribal_council"):
        tribal_types[t] = tribal_types.get(t, 0) + 1
check("tribal_mix_3p_4single_0double",
      tribal_types.get("tribal_council_single", 0) == 4 and tribal_types.get("tribal_council_double", 0) == 0,
      tribal_types)
check("bottom_card_is_tribal",
      str(g.get("deck", [{}])[-1].get("type", "")).startswith("tribal_council"))
check("official_3p_deck_is_47_cards", len(g.get("deck", [])) == 47, len(g.get("deck", [])))
check("no_house_cards_in_official_deck",
      not [c for c in g.get("deck", []) if c.get("type") in
           ("idol_nullifier", "steal_vote", "block_vote", "grant_immunity")])
check("no_challenge_cards_without_expansion",
      not [c for c in g.get("deck", []) if str(c.get("type", "")).startswith("challenge_")])

# ── turn order enforcement (F5) ──
first = g["turnOrder"][g["currentTurnIndex"]]
st, resp = api("/api/turn/draw", {"gameId": gid, "playerId": first})
check("draw_before_steal_rejected", not resp.get("success"), resp.get("message"))
check("draw_rejection_explains_order", "steal" in str(resp.get("message", "")).lower(),
      resp.get("message"))

victim = next(p for p in g["turnOrder"] if p != first)
st, resp = api("/api/turn/steal", {"gameId": gid, "thiefId": first, "targetId": victim})
check("steal_endpoint", resp.get("success"), resp.get("message"))
api("/api/reactive/complete_theft", {"gameId": gid})
st, resp = api("/api/turn/draw", {"gameId": gid, "playerId": first})
check("draw_after_steal", resp.get("success"), resp.get("message"))
st, resp = api("/api/turn/steal", {"gameId": gid, "thiefId": first, "targetId": victim})
check("double_steal_rejected", not resp.get("success"), resp.get("message"))
api("/api/turn/advance", {"gameId": gid})

# ── play until the first tribal council ──
g = state(gid)
tribal = g.get("phase") == "tribal_council"
turns = 0
while not tribal and turns < 300 and g.get("phase") == "playing":
    turns += 1
    g, tribal = play_turn(gid, g)
check("tribal_triggered", tribal, f"after {turns} turns, phase={g.get('phase')}")

cv = g.get("currentVote", {})
leader = cv.get("councilLeaderId")
check("tribal_has_leader", bool(leader))
check("tribal_starts_in_announcement", cv.get("phase") == "announcement", cv.get("phase"))
check("eliminations_needed_matches_card_type",
      cv.get("eliminationsNeeded") == (2 if cv.get("type") == "double" else 1),
      f"type={cv.get('type')} needed={cv.get('eliminationsNeeded')}")

# ── vote card economy (F2) ──
api("/api/vote/start", {"gameId": gid, "voteType": "elimination"})
g = state(gid)
st, resp = api("/api/vote/cast", {"gameId": gid, "voterId": bob,
                                  "votesData": [{"targetId": bob, "votes": 1}]})
check("self_vote_rejected", not resp.get("success"), resp.get("message"))
st, resp = api("/api/vote/cast", {"gameId": gid, "voterId": bob,
                                  "votesData": [{"targetId": alice, "votes": 9}]})
check("overvoting_rejected", not resp.get("success"), resp.get("message"))

target = bob
check("all_vote", cast_all_votes(gid, g, target))
g = state(gid)
spent_ok = all(sum(1 for c in p["hand"] if c.get("type") == "vote") == 0
               for p in g["players"].values())
check("vote_cards_consumed_from_hands", spent_ok,
      {p["name"]: [c["type"] for c in p["hand"]] for p in g["players"].values()})
st, resp = api("/api/vote/cast", {"gameId": gid, "voterId": bob,
                                  "votesData": [{"targetId": alice, "votes": 1}]})
check("double_vote_rejected", not resp.get("success"), resp.get("message"))

api("/api/tribal/advance", {"gameId": gid, "phase": "immunity"})
st, resp = api("/api/vote/reveal", {"gameId": gid})
check("reveal_votes", resp.get("success"), resp.get("message", ""))
g = state(gid)
cv = g.get("currentVote", {})
check("reveal_reports_resolution", bool(cv.get("resolution")), cv.get("resolution"))
if cv.get("tieBreakNeeded"):
    st, resp = api("/api/vote/tiebreak", {"gameId": gid, "leaderId": cv.get("councilLeaderId"),
                                          "chosenId": target})
    check("tie_break_resolves", resp.get("success"), resp.get("message"))
    g = state(gid)
    cv = g.get("currentVote", {})
voted_out = cv.get("eliminated", [])
vote_results = cv.get("voteResults", {})
top = max(vote_results.values()) if vote_results else 0
expected_out = [pid for pid, n in vote_results.items() if n == top]
check("most_votes_is_voted_out", len(voted_out) == 1 and voted_out[0] in expected_out,
      f"eliminated={voted_out} voteResults={vote_results}")
cards_before = {pid: p.get("characterCards") for pid, p in g["players"].items()}

st, resp = api("/api/tribal/complete", {"gameId": gid})
check("tribal_complete", resp.get("success"), resp.get("message", ""))
g = state(gid)

# ── lives system (F1) ──
out = voted_out[0]
out_player = g["players"][out]
check("vote_out_flips_one_character_card",
      out_player.get("characterCards") == cards_before[out] - 1,
      f"{out_player['name']}: {cards_before[out]} -> {out_player.get('characterCards')}")
check("voted_out_player_still_in_the_game", not out_player.get("isEliminated"),
      f"{out_player['name']} had {cards_before[out]} cards, so one vote-out can't eliminate them")
check("no_jury_yet_after_one_vote_out", g.get("jury", []) == [], g.get("jury"))
check("others_keep_both_character_cards",
      all(p.get("characterCards") == cards_before[pid]
          for pid, p in g["players"].items() if pid != out))
check("back_to_playing", g.get("phase") == "playing", g.get("phase"))

vote_have = {p["name"]: sum(1 for c in p.get("hand", []) if c.get("type") == "vote")
             for p in g["players"].values()}
check("vote_card_returned_to_everyone_still_in", all(v >= 1 for v in vote_have.values()), vote_have)

# ── second vote-out eliminates and juries ──
api("/api/tribal/advance", {"gameId": gid, "phase": "discussion"}) if g.get("phase") == "tribal_council" else None
g = state(gid)
if g.get("phase") == "playing":
    # Force another tribal by walking turns
    tribal = False
    turns = 0
    while not tribal and turns < 300 and g.get("phase") == "playing":
        turns += 1
        g, tribal = play_turn(gid, g)
    check("second_tribal_triggered", tribal, f"phase={g.get('phase')}")

while g.get("phase") == "tribal_council" or (g.get("phase") == "playing" and len(alive(g)) > 2):
    if g.get("phase") == "playing":
        tribal = False
        turns = 0
        while not tribal and turns < 300 and g.get("phase") == "playing":
            turns += 1
            g, tribal = play_turn(gid, g)
        if not tribal:
            break
    # Vote out whoever is closest to elimination so the game converges
    order = [p for p in g["turnOrder"] if not g["players"][p].get("isEliminated")]
    victim = min(order, key=lambda p: g["players"][p].get("characterCards", 2))
    before = dict((p, g["players"][p].get("characterCards")) for p in order)
    g, voted_out = run_tribal(gid, victim)

    if voted_out:
        for pid in voted_out:
            player = g["players"][pid]
            expected = max(0, before[pid] - 1)
            check(f"vote_out_decrements_{player['name']}_to_{expected}",
                  player.get("characterCards") == expected,
                  f"{before[pid]} -> {player.get('characterCards')}")
            if expected == 0:
                check(f"{player['name']}_eliminated_at_zero_cards", player.get("isEliminated"))
                check(f"{player['name']}_joins_the_jury", pid in g.get("jury", []), g.get("jury"))
            else:
                check(f"{player['name']}_still_in_the_game_with_one_card",
                      not player.get("isEliminated"))
    if g.get("phase") in ("final_tribal", "final", "finished"):
        break

check("final_tribal_fires_at_two_players",
      g.get("phase") in ("final_tribal", "final") and len(alive(g)) == 2,
      f"phase={g.get('phase')} alive={len(alive(g))}")

# ── final tribal + jury vote + winner ──
if g.get("phase") in ("final_tribal", "final"):
    ft = g.get("finalTribal", {})
    check("final_tribal_official_questions",
          ft.get("questions") == ["What was your strategy coming into the game?",
                                  "What was your best move in the game?",
                                  "How did you outplay your opponent?"],
          ft.get("questions"))
    check("most_recent_eliminee_leads_final_tribal",
          ft.get("leader") == (g.get("jury") or [None])[-1], ft.get("leader"))

    api("/api/final/advance", {"gameId": gid, "phase": "voting"})
    finalists = ft.get("finalists", [])
    jury = ft.get("jury", [])
    for juror in jury:
        st, resp = api("/api/final/vote", {"gameId": gid, "juryMemberId": juror,
                                           "finalistId": finalists[0]})
    g = state(gid)
    ft = g.get("finalTribal", {})
    check("jury_vote_determines_winner", ft.get("winner") == finalists[0],
          f"winner={ft.get('winner')} counts={ft.get('voteCounts')}")

    st, resp = api("/api/game/finish", {"gameId": gid, "winnerId": finalists[0]})
    check("winner_recorded", resp.get("success"), resp.get("message"))
    st, winners = api("/api/winners", method="GET")
    winner_name = g["players"][finalists[0]]["name"]
    check("winner_in_hall_of_fame",
          any(w.get("winner_name") == winner_name for w in (winners or [])), winner_name)

# ══════════════════════════ 3. expansion game ══════════════════════════

st, resp = api("/api/game/create", {"deckMode": "official", "expansion": True})
egid = resp.get("gameId")
check("create_expansion_game", resp.get("expansion") is True, resp)

epids = {}
for name in ("Dana", "Eli", "Fern", "Gus"):
    st, resp = api("/api/player/join", {"gameId": egid, "name": name})
    if resp.get("success"):
        epids[name] = resp["playerId"]
check("four_players_join_expansion", len(epids) == 4, epids)
api("/api/game/start_full", {"gameId": egid})
eg = state(egid)
# The 5 Orange cards join the Action Card pile, so some may be dealt into opening
# hands — count them across the deck and every hand.
challenge_cards = [c for c in eg.get("deck", []) if str(c.get("type", "")).startswith("challenge_")]
challenge_cards += [c for p in eg["players"].values() for c in p.get("hand", [])
                    if str(c.get("type", "")).startswith("challenge_")]
check("five_challenge_cards_in_expansion_game", len(challenge_cards) == 5,
      sorted(c["type"] for c in challenge_cards))
check("necklace_starts_on_the_table", eg.get("necklaceHolder") is None)

# Walk turns until somebody draws a Challenge Card, then play it. Challenge cards
# are a small slice of the deck, so if a game finishes before two have surfaced we
# start another expansion game rather than leaving the coverage to luck.
challenges_played = 0
expansion_games = [egid]


def play_expansion_game(egid):
    global challenges_played, eg
    turns = 0
    while challenges_played < 2 and turns < 400:
        turns += 1
        eg = state(egid)
        phase = eg.get("phase")
        if phase == "tribal_council":
            # Resolve it so play can continue. Vote out whoever has the most Survivor
            # Character Cards so the game stays alive long enough to draw challenges.
            order = [p for p in eg["turnOrder"] if not eg["players"][p].get("isEliminated")]
            wearer = eg.get("necklaceHolder")
            candidates = [p for p in order if p != wearer] or order
            eg, _ = run_tribal(egid, max(candidates,
                                         key=lambda p: eg["players"][p].get("characterCards", 2)))
            continue
        if phase not in ("playing",):
            break

        cp = eg["turnOrder"][eg.get("currentTurnIndex", 0)]
        hand = eg["players"][cp].get("hand", [])
        idx = next((i for i, c in enumerate(hand)
                    if str(c.get("type", "")).startswith("challenge_")
                    and c.get("type") != "challenge_hide_n_seek"), None)

        if idx is None:
            eg, _ = play_turn(egid, eg)
            continue

        # Steal first so the play phase is legal
        victim = next(p for p in eg["turnOrder"] if p != cp and not eg["players"][p].get("isEliminated"))
        api("/api/turn/steal", {"gameId": egid, "thiefId": cp, "targetId": victim})
        api("/api/reactive/complete_theft", {"gameId": egid})
        eg = state(egid)
        hand = eg["players"][cp].get("hand", [])
        idx = next((i for i, c in enumerate(hand)
                    if str(c.get("type", "")).startswith("challenge_")
                    and c.get("type") != "challenge_hide_n_seek"), None)
        if idx is None:
            eg, _ = play_turn(egid, eg)
            continue

        card_type = hand[idx]["type"]
        st, resp = api("/api/turn/play_card", {"gameId": egid, "playerId": cp, "cardIdx": idx})
        if not resp.get("success"):
            print("   challenge play failed:", resp.get("message"))
            eg, _ = play_turn(egid, eg)
            continue

        eg = state(egid)
        ch = eg.get("challenge") or {}
        holder_before = eg.get("necklaceHolder")
        check(f"challenge_started_{ch.get('type', card_type)}", ch.get("phase") not in (None, "complete"),
              ch.get("prompt"))
        check(f"challenge_secrets_hidden_{ch.get('type', card_type)}",
              not [k for k in ch if k.startswith("_")], list(ch)[:12])

        # Other players can't act out of turn
        outsider = next(p for p in ch["order"] if p != ch["currentPlayerId"])
        st, resp = api("/api/challenge/action", {"gameId": egid, "playerId": outsider, "action": "pull"})
        check(f"challenge_turn_enforced_{ch.get('type')}", not resp.get("success"), resp.get("message"))

        # Drive the challenge to completion using only legal actions
        steps = 0
        while ch and ch.get("phase") != "complete" and steps < 400:
            steps += 1
            actions = ch.get("actions", [])
            action = actions[0] if actions else None
            if not action:
                break
            value = None
            if action == "bid":
                nxt = ch.get("currentBid", 0) + 1
                if nxt > ch.get("maxBid", nxt) and "pass" in actions:
                    action = "pass"
                else:
                    value = nxt
            elif action == "pull" and ch.get("type") == "lowest_score_loses":
                value = 1
            elif action == "steal":
                value = (ch.get("stealTargets") or [None])[0]
                if not value:
                    action = "pull"
            st, resp = api("/api/challenge/action",
                           {"gameId": egid, "playerId": ch["currentPlayerId"],
                            "action": action, "value": value})
            if not resp.get("success"):
                print(f"   challenge action {action}({value}) failed: {resp.get('message')}")
                break
            eg = state(egid)
            ch = eg.get("challenge") or {}

        check(f"challenge_completed_{ch.get('type', card_type)}", ch.get("phase") == "complete",
              ch.get("prompt"))
        winner = ch.get("winnerId")
        check(f"challenge_has_winner_{ch.get('type', card_type)}", bool(winner), winner)

        if holder_before is None:
            check(f"challenge_winner_wears_necklace_{challenges_played + 1}",
                  eg.get("necklaceHolder") == winner,
                  f"holder={eg.get('necklaceHolder')} winner={winner}")
        else:
            # "If someone is already wearing the Immunity Idol Necklace when you win a
            #  Challenge, you instead get to take 3 random cards from the Draw Pile."
            check("necklace_stays_with_the_original_wearer",
                  eg.get("necklaceHolder") == holder_before,
                  f"before={holder_before} after={eg.get('necklaceHolder')}")
            check("second_win_takes_three_cards_instead",
                  "3 random cards" in " ".join(ch.get("log", [])[-3:]),
                  ch.get("log", [])[-1:])

        api("/api/challenge/action", {"gameId": egid, "playerId": winner, "action": "dismiss"})
        # Finish the starter's turn so play continues
        api("/api/turn/draw", {"gameId": egid, "playerId": ch["starterId"]})
        api("/api/turn/advance", {"gameId": egid})

        challenges_played += 1



play_expansion_game(egid)
for _ in range(6):
    if challenges_played >= 2:
        break
    st, resp = api('/api/game/create', {'deckMode': 'official', 'expansion': True})
    egid = resp.get('gameId')
    expansion_games.append(egid)
    for name in ('Dana', 'Eli', 'Fern', 'Gus'):
        api('/api/player/join', {'gameId': egid, 'name': name})
    api('/api/game/start_full', {'gameId': egid})
    play_expansion_game(egid)

check("two_challenges_played", challenges_played >= 2, challenges_played)

# ── necklace immunity at a tribal council ──
eg = state(egid)
wearer = eg.get("necklaceHolder")
if wearer:
    if eg.get("phase") != "tribal_council":
        tribal = False
        turns = 0
        while not tribal and turns < 400 and eg.get("phase") == "playing":
            turns += 1
            eg, tribal = play_turn(egid, eg)
    if eg.get("phase") == "tribal_council":
        api("/api/vote/start", {"gameId": egid, "voteType": "elimination"})
        eg = state(egid)
        voter = next(p for p in eg["turnOrder"] if p != wearer and not eg["players"][p].get("isEliminated"))
        st, resp = api("/api/vote/cast", {"gameId": egid, "voterId": voter,
                                          "votesData": [{"targetId": wearer, "votes": 1}]})
        check("necklace_wearer_cannot_be_voted_for", not resp.get("success"), resp.get("message"))
        check("necklace_rejection_names_the_necklace",
              "Necklace" in str(resp.get("message", "")), resp.get("message"))
    else:
        check("necklace_wearer_cannot_be_voted_for", False,
              f"never reached a tribal council (phase={eg.get('phase')})")

# Hide 'n' Seek stub
st, resp = api("/api/game/create", {"expansion": True})
hgid = resp.get("gameId")
for name in ("Hank", "Iris", "Jo"):
    api("/api/player/join", {"gameId": hgid, "name": name})
api("/api/game/start_full", {"gameId": hgid})
hg = state(hgid)
hp = hg["turnOrder"][0]
victim = hg["turnOrder"][1]
api("/api/turn/steal", {"gameId": hgid, "thiefId": hp, "targetId": victim})
api("/api/reactive/complete_theft", {"gameId": hgid})
hg = state(hgid)
# Inject via a legal path is impossible; assert the card definition instead
st, cardsresp = api("/api/cards", method="GET")
hns = cardsresp.get("cards", {}).get("challenge_hide_n_seek", {})
check("hide_n_seek_marked_unavailable", hns.get("digital") is False and "NOT AVAILABLE" in hns.get("description", ""),
      hns.get("description", "")[:80])

# ══════════════════════════ 4. transport ══════════════════════════

st, resp = api(f"/api/game/{gid}/state", {}, method="POST")
check("state_route_is_get_only", st == 405, st)
st, resp = api("/api/ping", method="GET")
check("ping", resp.get("success"), resp)

# ── Wiping a game: gone for good, and every read path agrees ─────────────────
st, resp = api("/api/game/create", {})
wipe_gid = resp.get("gameId")
api("/api/player/join", {"gameId": wipe_gid, "name": "Wanda", "color": "red"})
api("/api/player/join", {"gameId": wipe_gid, "name": "Wes", "color": "blue"})
api("/api/game/start", {"gameId": wipe_gid})
st, resp = api("/api/game/delete", {"gameId": wipe_gid})
check("wipe_reports_success", resp.get("success") and resp.get("wiped"), resp)
check("wipe_counts_players", resp.get("playerCount") == 2, resp.get("playerCount"))
st, resp = api(f"/api/game/{wipe_gid}/state", method="GET")
check("wiped_game_state_is_gone", st == 404, st)
st, resp = api("/api/game/delete", {"gameId": wipe_gid})
check("wipe_twice_is_a_clean_error", resp.get("success") is False, resp)
st, resp = api("/api/game/delete", {"gameId": "ZZZZZZZZ"})
check("wipe_unknown_game_rejected", resp.get("success") is False, resp)

# ── Renaming: free in the lobby, locked once the game starts ─────────────────
st, resp = api("/api/game/create", {})
rn_gid = resp.get("gameId")
st, resp = api("/api/player/join", {"gameId": rn_gid, "name": "Rene", "color": "red"})
rn_pid = resp.get("playerId")
api("/api/player/join", {"gameId": rn_gid, "name": "Ren", "color": "blue"})
api("/api/player/join", {"gameId": rn_gid, "name": "Rey", "color": "green"})
st, resp = api("/api/player/rename", {"gameId": rn_gid, "playerId": rn_pid, "newName": "Renata"})
check("rename_in_lobby_works", resp.get("success") and resp.get("newName") == "Renata", resp)
game = state(rn_gid)
check("rename_visible_in_state", game.get("players", {}).get(rn_pid, {}).get("name") == "Renata",
      game.get("players", {}).get(rn_pid, {}).get("name"))
st, resp = api("/api/player/rename", {"gameId": rn_gid, "playerId": rn_pid, "newName": "Ren"})
check("rename_duplicate_rejected", resp.get("success") is False, resp)
api("/api/game/start_full", {"gameId": rn_gid})
st, resp = api("/api/player/rename", {"gameId": rn_gid, "playerId": rn_pid, "newName": "TooLate"})
check("rename_locked_after_start", resp.get("success") is False and "started" in resp.get("message", ""), resp)
api("/api/game/delete", {"gameId": rn_gid})

# ── Computer players: lifecycle + they actually take their turns ─────────────
st, resp = api("/api/game/create", {})
bot_gid = resp.get("gameId")
st, resp = api("/api/player/join", {"gameId": bot_gid, "name": "Human", "color": "red"})
human_pid = resp.get("playerId")
st, resp = api("/api/player/add_bot", {"gameId": bot_gid})
check("add_bot_works", resp.get("success") and resp.get("playerId"), resp)
first_bot = resp.get("playerId")
st, resp = api("/api/player/add_bot", {"gameId": bot_gid})
check("second_bot_gets_unique_name", resp.get("success"), resp)
game = state(bot_gid)
bots_in_state = [p for p, pl in game.get("players", {}).items() if pl.get("isBot")]
check("bots_flagged_in_state", len(bots_in_state) == 2, bots_in_state)
st, resp = api("/api/player/remove_bot", {"gameId": bot_gid, "playerId": first_bot})
check("remove_bot_works", resp.get("success"), resp)
st, resp = api("/api/player/remove_bot", {"gameId": bot_gid, "playerId": human_pid})
check("remove_bot_refuses_humans", resp.get("success") is False, resp)
api("/api/player/add_bot", {"gameId": bot_gid})
api("/api/game/start_full", {"gameId": bot_gid})

# The Hall of Fame stays clean no matter who wins a practice game
st, resp = api("/api/game/finish", {"gameId": bot_gid, "winnerId": human_pid})
check("bot_game_never_recorded", resp.get("success") is False
      and "Hall of Fame" in str(resp.get("message", "")), resp)

# Bots take their turns unattended: wait for the torch to come around to the
# human, play the human turn, then wait for it to come around again — that
# second arrival means every bot in between played a full turn on its own.
def _answer_the_island(g):
    """While waiting, the human seat must still answer anything aimed at it —
    a raid (Sorry For You window), a Reward Challenge pick, a Rocks turn —
    exactly like a person tapping the dialogs the app shows them."""
    theft = g.get("pending_theft") or {}
    if theft.get("reactive_window_open") and theft.get("targetId") == human_pid:
        api("/api/reactive/complete_theft", {"gameId": bot_gid})
        return True
    it = g.get("interaction") or {}
    if it:
        if it.get("phase") == "picking" and human_pid in (it.get("awaiting") or []):
            value = "rock" if it.get("type") == "do_or_die" else 2
            api("/api/interaction/act", {"gameId": bot_gid, "playerId": human_pid,
                                         "action": "pick", "value": value})
            return True
        if it.get("phase") == "give" and human_pid in (it.get("awaiting") or []):
            api("/api/interaction/act", {"gameId": bot_gid, "playerId": human_pid,
                                         "action": "give", "value": 0})
            return True
        if it.get("phase") == "choose_victim" and it.get("winnerId") == human_pid:
            victim = next((p for p in g.get("turnOrder", []) if p != human_pid), None)
            if victim:
                api("/api/interaction/act", {"gameId": bot_gid, "playerId": human_pid,
                                             "action": "steal_from", "value": victim})
            return True
    ch = g.get("challenge") or {}
    if ch and ch.get("phase") != "complete" and ch.get("currentPlayerId") == human_pid:
        actions = ch.get("actions") or []
        if actions:
            action, value = actions[0], None
            if action == "bid":
                value = ch.get("currentBid", 0) + 1
                if value > ch.get("maxBid", value) and "pass" in actions:
                    action, value = "pass", None
            elif action == "pull" and ch.get("type") == "lowest_score_loses":
                value = 1
            elif action == "steal":
                action = "pull" if "pull" in actions else action
            api("/api/challenge/action", {"gameId": bot_gid, "playerId": human_pid,
                                          "action": action, "value": value})
            return True
    if ch and ch.get("phase") == "complete" and ch.get("winnerId") == human_pid:
        api("/api/challenge/action", {"gameId": bot_gid, "playerId": human_pid,
                                      "action": "dismiss"})
        return True
    return False


def _wait_for_human_turn(timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        g = state(bot_gid)
        if g.get("phase") == "tribal_council":
            # a bot's draw triggered tribal — that's bots working too
            return "tribal", g
        if _answer_the_island(g):
            time.sleep(0.3)
            continue
        order = g.get("turnOrder") or []
        if order and order[g.get("currentTurnIndex", 0) % len(order)] == human_pid \
                and not g.get("interaction") and not g.get("challenge"):
            return "turn", g
        time.sleep(0.5)
    return "timeout", state(bot_gid)

outcome1, g = _wait_for_human_turn()
check("bots_play_until_human_turn", outcome1 in ("turn", "tribal"), outcome1)
if outcome1 == "turn":
    victim = next(p for p in g["turnOrder"] if p != human_pid)
    api("/api/turn/steal", {"gameId": bot_gid, "thiefId": human_pid, "targetId": victim})
    api("/api/reactive/complete_theft", {"gameId": bot_gid})
    r = api("/api/turn/draw", {"gameId": bot_gid, "playerId": human_pid})[1]
    if not r.get("tribal_triggered"):
        api("/api/turn/advance", {"gameId": bot_gid})
    outcome2, _ = _wait_for_human_turn()
    check("bots_keep_playing_after_human_turn", outcome2 in ("turn", "tribal"), outcome2)
api("/api/game/delete", {"gameId": bot_gid})

# ── Scrub this run's wins from the Hall of Fame ──────────────────────────────
try:
    _, _records = api("/api/winners/records", method="GET")
    _scrubbed = 0
    for _rec in (_records if isinstance(_records, list) else []):
        if isinstance(_rec, dict) and _rec.get("game_id") in CREATED_GAMES and _rec.get("id"):
            _st, _resp = api("/api/winners/delete", {"id": _rec["id"]})
            if _resp.get("success"):
                _scrubbed += 1
    if _scrubbed:
        print(f"(scrubbed {_scrubbed} test win(s) from the Hall of Fame)")
except Exception as _e:
    print(f"(warning: could not scrub test wins: {_e})")

print()
p = sum(1 for _, ok, _ in results if ok)
print(f"=== {p}/{len(results)} checks passed ===")
if p != len(results):
    print("\nFailures:")
    for name, ok, detail in results:
        if not ok:
            print(f"  ✗ {name} — {detail}")
sys.exit(0 if p == len(results) else 1)
