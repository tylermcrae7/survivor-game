#!/usr/bin/env python3
"""E2E test of survivor_server.py via its real HTTP API (same calls network.js makes)."""
import json, sys, time, urllib.request, urllib.error

BASE = "http://localhost:8080"
results = []

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + ((" — " + str(detail)[:160]) if detail else ""))

def api(path, body=None, method=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

# 1. index
try:
    with urllib.request.urlopen(BASE + "/", timeout=10) as r:
        check("index_serves", r.status == 200 and len(r.read()) > 5000)
except Exception as e:
    check("index_serves", False, e)

# 2. cards endpoint
st, resp = api("/api/cards", method="GET")
ncards = len(resp.get("cards", resp)) if isinstance(resp, dict) else 0
check("cards_endpoint", st == 200, f"{ncards} keys")

# 3. create + join 3 players
st, resp = api("/api/game/create", {})
gid = resp.get("gameId")
check("create_game", st == 200 and bool(gid), resp.get("message",""))
if not gid: sys.exit(1)

pids = {}
for name in ("Alice", "Bob", "Cara"):
    st, resp = api("/api/player/join", {"gameId": gid, "name": name})
    if resp.get("success"): pids[name] = resp["playerId"]
    else: print("   join fail:", name, resp)
check("three_players_join", len(pids) == 3, pids)
alice, bob, cara = pids["Alice"], pids["Bob"], pids["Cara"]

# 4. bad name rejected?
st, resp = api("/api/player/join", {"gameId": gid, "name": ""})
check("empty_name_rejected", not resp.get("success"))

# 5. start
st, resp = api("/api/game/start_full", {"gameId": gid})
check("start_game", resp.get("success"), resp.get("message",""))

def get_state():
    st, s = api(f"/api/game/{gid}/state", method="GET")
    return s if isinstance(s, dict) else {}

g = get_state()
if "players" not in g and "gameState" in g: g = g["gameState"]
players = g.get("players", {})
check("state_fetch", bool(players), list(g.keys())[:12])

hand_sizes = {p["name"]: len(p.get("hand", [])) for p in players.values()}
check("initial_hand_size", all(v == 5 for v in hand_sizes.values()), hand_sizes)
vote_counts = {p["name"]: sum(1 for c in p.get("hand", []) if c.get("type") == "vote") for p in players.values()}
print(f"   NOTE vote cards in initial hands (official rules: exactly 1 each): {vote_counts}")
lives = {p["name"]: p.get("characterCards") for p in players.values()}
check("two_character_cards_each", all(v == 2 for v in lives.values()), lives)
deck_n = len(g.get("deck", []))
tribal_in_deck = sum(1 for c in g.get("deck", []) if "tribal" in str(c.get("type","")))
print(f"   deck={deck_n} cards, tribal cards in deck={tribal_in_deck} (3 players => rules want 4 single/0 double)")
tribal_types = {}
for c in g.get("deck", []):
    t = c.get("type","")
    if "tribal" in t: tribal_types[t] = tribal_types.get(t,0)+1
check("tribal_mix_3p_4single_0double", tribal_types.get("tribal_council_single",0)==4 and tribal_types.get("tribal_council_double",0)==0, tribal_types)
bottom_is_tribal = "tribal" in str(g.get("deck", [{}])[-1].get("type","")) if g.get("deck") else False
check("bottom_card_is_tribal", bottom_is_tribal)

# 6. play turns until tribal triggers
order = g.get("turnOrder", [alice, bob, cara])
steal_ok = draw_ok = None
tribal = False
turn_n = 0
for turn_n in range(300):
    g = get_state()
    if g.get("phase") == "tribal_council":
        tribal = True; break
    if g.get("phase") not in ("playing",):
        break
    cp = g.get("turnOrder", order)[g.get("currentTurnIndex", g.get("turnIndex", 0)) % len(order)] if isinstance(g.get("currentTurnIndex", g.get("turnIndex")), int) else g.get("currentPlayerId")
    if cp is None:
        # fall back: find player with hasStolen False and it's turn — try each
        cp = order[turn_n % len(order)]
    victim = [p for p in order if p != cp][0]
    st, resp = api("/api/turn/steal", {"gameId": gid, "thiefId": cp, "targetId": victim})
    if steal_ok is None:
        steal_ok = resp.get("success", False)
        if not steal_ok: print("   first steal resp:", json.dumps(resp)[:300])
    st, resp = api("/api/turn/draw", {"gameId": gid, "playerId": cp})
    if draw_ok is None:
        draw_ok = resp.get("success", False)
        if not draw_ok: print("   first draw resp:", json.dumps(resp)[:300])
    st, resp2 = api("/api/turn/advance", {"gameId": gid})
check("steal_endpoint", steal_ok)
check("draw_endpoint", draw_ok)
check("tribal_triggered", tribal, f"after {turn_n+1} loop turns, phase={g.get('phase')}")

# 7. tribal flow
if tribal:
    cv = g.get("currentVote", {})
    leader = cv.get("councilLeaderId")
    print(f"   leader={leader} phase={cv.get('phase')} type={cv.get('voteType') or cv.get('eliminationType')}")
    check("tribal_has_leader", bool(leader))
    st, resp = api("/api/vote/start", {"gameId": gid, "voteType": "elimination"})
    check("start_voting", resp.get("success"), resp.get("message",""))
    ok_votes = []
    for nm, pid in pids.items():
        target = bob if pid != bob else alice
        st, resp = api("/api/vote/cast", {"gameId": gid, "voterId": pid, "votesData": [{"targetId": target, "votes": 1}]})
        ok_votes.append(resp.get("success", False))
        if not resp.get("success"): print(f"   vote {nm}:", json.dumps(resp)[:250])
    check("all_vote", all(ok_votes), ok_votes)
    st, resp = api("/api/vote/reveal", {"gameId": gid})
    check("reveal_votes", resp.get("success"), resp.get("message",""))
    g = get_state()
    cv = g.get("currentVote", {})
    elim = cv.get("eliminated", [])
    check("bob_voted_out", bob in elim, f"eliminated={elim}")
    st, resp = api("/api/tribal/complete", {"gameId": gid})
    check("tribal_complete", resp.get("success"), resp.get("message",""))
    g = get_state()
    bob_cc = g["players"][bob].get("characterCards")
    check("bob_lost_character_card", bob_cc == 1, f"characterCards={bob_cc}")
    # vote card return check
    vote_after = {p["name"]: sum(1 for c in p.get("hand", [])) for p in g["players"].values()}
    vote_have = {p["name"]: sum(1 for c in p.get("hand", []) if c.get("type")=="vote") for p in g["players"].values()}
    print(f"   post-tribal hands={vote_after} vote cards={vote_have}")
    check("vote_cards_returned_all_alive", all(v >= 1 for k, v in vote_have.items()), vote_have)
    check("back_to_playing", g.get("phase") == "playing", g.get("phase"))

print()
p = sum(1 for _, ok, _ in results if ok)
print(f"=== {p}/{len(results)} checks passed ===")
