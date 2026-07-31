#!/usr/bin/env python3
"""
Regenerate the iOS decode fixtures from the REAL server.

Each fixture is the exact JSON a phone receives (GameState.get_game_state —
secrets already stripped) at a moment the app must decode flawlessly. Run from
the repo root after server-side wire changes:

    .venv/bin/python ios/SurvivorGameTests/Fixtures/generate_fixtures.py
"""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, REPO)
os.environ["SURVIVOR_BOT_DELAY"] = "0"

OUT = os.path.dirname(os.path.abspath(__file__))

from survivor_server import GameState  # noqa: E402


def fresh(expansion=False, settings=None):
    gs = GameState()
    gid = gs.create_game(deckMode="official", expansion=expansion, settings=settings)
    pids = [gs.add_player(gid, n, c) for n, c in
            (("Ana", "#FF6B6B"), ("Ben", "#4ECDC4"), ("Cam", "#45B7D1"))]
    return gs, gid, pids


def dump(gs, gid, name):
    state = gs.get_game_state(gid)
    with open(os.path.join(OUT, f"{name}.json"), "w") as f:
        json.dump(state, f, indent=1)
    print(f"  {name}.json  (phase={state.get('phase')})")


def open_voting(gs, gid, game, leader):
    game["phase"] = "tribal_council"
    game["currentVote"] = {
        "type": "single", "votes": {}, "phase": "voting",
        "councilLeaderId": leader, "immunityPlayed": [],
        "tieBreakNeeded": False, "tiedPlayers": [], "eliminated": []
    }
    for p in game["players"].values():
        p["hasVoted"] = False


def main():
    tmp = tempfile.mkdtemp()
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        # lobby
        gs, gid, pids = fresh()
        dump(gs, gid, "lobby")

        # playing, mid-turn (stolen, not yet drawn), with an event log
        gs.start_full_game(gid)
        game = gs.games[gid]
        game["currentTurnIndex"] = 0
        game["players"][pids[0]]["hasStolen"] = True
        game.setdefault("eventLog", []).append({"t": 1753900000.0, "msg": "Ana drew a card — their turn is over"})
        dump(gs, gid, "playing_midturn")

        # tribal: announcement, then voting (the decode-killer), then a cast ballot
        game["phase"] = "tribal_council"
        game["currentVote"] = {
            "type": "single", "votes": {}, "phase": "announcement",
            "councilLeaderId": pids[0], "immunityPlayed": [],
            "tieBreakNeeded": False, "tiedPlayers": [], "eliminated": []
        }
        dump(gs, gid, "tribal_announcement")

        open_voting(gs, gid, game, pids[0])
        game["players"][pids[0]]["hand"] = [{"type": "vote"}, {"type": "extra_vote"}]
        gs.rules_engine.sync_vote_counters(game)
        result = gs.cast_vote(gid, voterId=pids[0], votesData=[
            {"targetId": pids[1], "votes": 1}, {"targetId": pids[2], "votes": 1}])
        assert result["success"], result
        dump(gs, gid, "tribal_voting")

        # immunity phase with a shielded player
        game["currentVote"]["phase"] = "immunity"
        game["players"][pids[1]]["immunityIdolProtection"] = True
        dump(gs, gid, "tribal_immunity")

        # reveal with a tie
        game["currentVote"]["phase"] = "reveal"
        game["currentVote"]["tieBreakNeeded"] = True
        game["currentVote"]["tiedPlayers"] = [pids[1], pids[2]]
        game["currentVote"]["voteResults"] = {pids[1]: 1, pids[2]: 1}
        dump(gs, gid, "tribal_reveal_tie")

        # rocks challenge mid-flight
        gs2, gid2, pids2 = fresh(expansion=True)
        gs2.start_full_game(gid2)
        g2 = gs2.games[gid2]
        g2["currentTurnIndex"] = 0
        g2["players"][pids2[0]]["hasStolen"] = True
        g2["players"][pids2[0]]["hand"].append({"type": "challenge_lowest_score_loses"})
        idx = len(g2["players"][pids2[0]]["hand"]) - 1
        r = gs2.play_card(gid2, pids2[0], idx)
        assert r["success"], r
        dump(gs2, gid2, "challenge_active")

        # reward interaction mid-flight (Do Or Die)
        gs3, gid3, pids3 = fresh()
        gs3.start_full_game(gid3)
        g3 = gs3.games[gid3]
        g3["currentTurnIndex"] = 0
        g3["players"][pids3[0]]["hasStolen"] = True
        g3["players"][pids3[0]]["hand"] = [{"type": "reward_challenge_do_or_die"}]
        r = gs3.play_card(gid3, pids3[0], 0,
                          {"targetId": pids3[1], "choice": "rock"})
        assert r["success"], r
        dump(gs3, gid3, "interaction_active")

        # pending Sorry-For-You window
        gs4, gid4, pids4 = fresh()
        gs4.start_full_game(gid4)
        g4 = gs4.games[gid4]
        g4["currentTurnIndex"] = 0
        g4["players"][pids4[1]]["hand"] = [{"type": "sorry_for_you"}]
        r = gs4.steal_card(gid4, thiefId=pids4[0], targetId=pids4[1])
        assert g4.get("pending_theft", {}).get("reactive_window_open"), r
        dump(gs4, gid4, "pending_theft_open")

        # legacy save: no settings key, no event log
        gs5, gid5, pids5 = fresh()
        gs5.start_full_game(gid5)
        gs5.games[gid5].pop("settings", None)
        dump(gs5, gid5, "legacy_no_settings")

        # finished game with a winner
        gs6, gid6, pids6 = fresh()
        gs6.start_full_game(gid6)
        g6 = gs6.games[gid6]
        g6["phase"] = "finished"
        g6["winner"] = pids6[0]
        for pid in pids6[1:]:
            g6["players"][pid]["isEliminated"] = True
        dump(gs6, gid6, "finished")
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
    print("fixtures written")
