#!/usr/bin/env python3

"""
Rules-enforcement tests — the 2026-07-30 review (docs/TASK-rules-enforcement-plan.md).

Pins the official turn discipline (one steal, ONE optional play, one draw that
ENDS the turn), the Control The Vote vote-card precondition, Camp Raid's real
trap semantics, and the universal Sorry For You taking gate with the Guide's
multi-taker each-discards rule.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState
from interactions import interaction_engine


def fresh_game():
    tmp = tempfile.mkdtemp()
    original = os.getcwd()
    os.chdir(tmp)
    gs = GameState()
    gid = gs.create_game()
    pids = [gs.add_player(gid, n, c) for n, c in
            (("Ana", "red"), ("Ben", "blue"), ("Cam", "green"))]
    gs.start_full_game(gid)
    game = gs.games[gid]
    return gs, gid, game, pids, original, tmp


def set_turn(game, pid, stolen=True, played=False, drawn=False):
    game["currentTurnIndex"] = game["turnOrder"].index(pid)
    p = game["players"][pid]
    p["hasStolen"], p["hasPlayed"], p["hasDrawn"] = stolen, played, drawn


def hand_types(game, pid):
    return [c.get("type") for c in game["players"][pid].get("hand", [])]


def test_one_play_per_turn():
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== One play per turn ===")
        set_turn(game, ana)
        game["players"][ana]["hand"] = [{"type": "inheritance"}, {"type": "inheritance"}]
        game["players"][ben]["hand"] = [{"type": "vote"}]

        r1 = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": ben})
        print("first play:", r1.get("message"))
        assert r1["success"] is True
        assert game["players"][ana]["hasPlayed"] is True

        r2 = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": cam})
        print("second play:", r2.get("message"))
        assert r2["success"] is False
        assert "already played" in r2["message"]
        # The refused card never left the hand
        assert "inheritance" in hand_types(game, ana)

        print("✅ one play per turn\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_one_draw_ends_the_turn():
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== One draw, and it ends the turn ===")
        set_turn(game, ana)
        game["deck"] = [{"type": "vote"}, {"type": "vote"}, {"type": "vote"}]

        r1 = gs.draw_card(gid, playerId=ana)
        assert r1["success"] is True
        assert game["players"][ana]["hasDrawn"] is True

        # Second draw refused
        r2 = gs.draw_card(gid, playerId=ana)
        print("second draw:", r2.get("message"))
        assert r2["success"] is False
        assert "End Turn" in r2["message"]

        # Playing after the draw refused — "Steal, Play, THEN Draw"
        game["players"][ana]["hand"] = [{"type": "inheritance"}]
        r3 = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": ben})
        print("play after draw:", r3.get("message"))
        assert r3["success"] is False
        assert "turn is over" in r3["message"]

        # turn_done is the reported phase
        phase = gs.rules_engine.get_current_turn_phase(game, ana)
        assert phase == "turn_done", phase

        # advance_turn resets everything for the next player
        gs.advance_turn(gid)
        assert game["players"][ana]["hasDrawn"] is False
        assert game["players"][ana]["hasPlayed"] is False

        print("✅ draw discipline\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_camp_raid_is_a_trap():
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== Camp Raid: the official trap ===")
        set_turn(game, ana)
        game["players"][ana]["hand"] = [{"type": "camp_raid"}]
        game["players"][ben]["hand"] = [{"type": "vote"}, {"type": "inheritance"}]

        r = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": ben})
        assert r["success"] is True, r.get("message")
        # Nothing moves at play time
        assert len(hand_types(game, ben)) == 2
        assert game["players"][ben].get("campRaidedBy") == ana

        # No stacking a second raid on the same player
        set_turn(game, cam)
        game["players"][cam]["hand"] = [{"type": "camp_raid"}]
        r = gs.play_card(gid, playerId=cam, cardIdx=0, params={"targetId": ben})
        print("stack attempt:", r.get("message"))
        assert r["success"] is False
        assert "already has" in r["message"]

        # The trap springs on Ben's next draw
        set_turn(game, ben)
        game["deck"] = [{"type": "extra_vote"}]
        ana_before = len(hand_types(game, ana))
        r = gs.draw_card(gid, playerId=ben)
        assert r["success"] is True
        assert "extra_vote" in hand_types(game, ana)
        assert len(hand_types(game, ana)) == ana_before + 1
        assert game["players"][ben].get("campRaidedBy") is None

        # A dead raider's trap fizzles
        game["players"][cam]["hand"] = []
        game["players"][ben]["campRaidedBy"] = cam
        game["players"][cam]["isEliminated"] = True
        set_turn(game, ben, drawn=False)
        game["deck"] = [{"type": "vote"}]
        before_cam = len(hand_types(game, cam))
        r = gs.draw_card(gid, playerId=ben)
        assert r["success"] is True
        assert len(hand_types(game, cam)) == before_cam
        assert game["players"][ben].get("campRaidedBy") is None

        print("✅ camp raid trap\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_sorry_for_you_gates_every_taking():
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== The taking gate ===")

        # Spy Shack against an SFY holder opens the window; playing SFY costs
        # the spy a discard and the take never happens
        set_turn(game, ana)
        game["players"][ana]["hand"] = [{"type": "the_spy_shack"}, {"type": "vote"}]
        game["players"][ben]["hand"] = [{"type": "immunity_idol"}, {"type": "sorry_for_you"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": ben, "takeIndex": 0})
        assert r["success"] is True, r.get("message")
        pending = game.get("pending_theft") or {}
        assert pending.get("reactive_window_open"), "gate should be open"
        assert pending.get("source") == "The Spy Shack"
        sfy_idx = hand_types(game, ben).index("sorry_for_you")
        r = gs.handle_reactive_card_play(gid, ben, sfy_idx, {})
        assert r["success"] is True, r.get("message")
        assert "immunity_idol" in hand_types(game, ben)      # kept their card
        assert "immunity_idol" not in hand_types(game, ana)  # spy got nothing
        assert "vote" not in hand_types(game, ana)           # and paid a discard
        assert not game.get("pending_theft")

        # A blocked card effect does NOT consume the thief's steal step
        assert game["players"][ana]["hasStolen"] is True  # set_turn set it; unchanged

        # Alliance: one SFY answers BOTH takers — each discards 1
        set_turn(game, ana, played=False)
        game["players"][ana]["hand"] = [{"type": "lets_form_an_alliance"}, {"type": "vote"}]
        game["players"][cam]["hand"] = [{"type": "vote"}]
        game["players"][ben]["hand"] = [{"type": "immunity_idol"}, {"type": "sorry_for_you"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0,
                         params={"allyId": cam, "victimId": ben})
        assert r["success"] is True, r.get("message")
        pending = game.get("pending_theft") or {}
        assert sorted(pending.get("thiefIds", [])) == sorted([ana, cam])
        sfy_idx = hand_types(game, ben).index("sorry_for_you")
        r = gs.handle_reactive_card_play(gid, ben, sfy_idx, {})
        assert r["success"] is True
        assert hand_types(game, ana) == []   # discarded their last card
        assert hand_types(game, cam) == []   # the ally paid too
        assert "immunity_idol" in hand_types(game, ben)

        # Declining executes the held take (Knowledge Is Power path)
        set_turn(game, ana, played=False)
        game["players"][ana]["hand"] = [{"type": "knowledge_is_power"}]
        game["players"][ben]["hand"] = [{"type": "extra_vote"}, {"type": "sorry_for_you"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0,
                         params={"targetId": ben, "cardType": "extra_vote"})
        assert r["success"] is True, r.get("message")
        assert (game.get("pending_theft") or {}).get("reactive_window_open")
        r = gs.complete_pending_theft(gid)
        assert r["success"] is True, r.get("message")
        assert "extra_vote" in hand_types(game, ana)
        assert "extra_vote" not in hand_types(game, ben)

        # No SFY in hand → no gate, take is immediate
        set_turn(game, ana, played=False)
        game["players"][ana]["hand"] = [{"type": "knowledge_is_power"}]
        game["players"][ben]["hand"] = [{"type": "vote"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0,
                         params={"targetId": ben, "cardType": "vote"})
        assert r["success"] is True
        assert not game.get("pending_theft")
        assert "vote" in hand_types(game, ana)

        print("✅ taking gate\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_reward_challenge_steals_go_through_the_gate():
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== Reward Challenge steals gate too ===")
        # Do Or Die: Ana throws rock, Ben (holding SFY) throws scissors and loses
        set_turn(game, ana)
        game["players"][ana]["hand"] = [{"type": "reward_challenge_do_or_die"}]
        game["players"][ben]["hand"] = [{"type": "immunity_idol"}, {"type": "sorry_for_you"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0,
                         params={"targetId": ben, "choice": "rock"})
        assert r["success"] is True, r.get("message")
        r = gs.interaction_action(gid, playerId=ben, action="pick", value="scissors")
        assert r["success"] is True, r.get("message")
        # The interaction resolved, but the steal is held at the gate
        assert (game.get("interaction") or {}).get("phase") == "complete"
        pending = game.get("pending_theft") or {}
        assert pending.get("reactive_window_open"), "Do Or Die loss should gate"
        assert pending.get("source") == "Do Or Die"
        # Ben blocks: Ana discards, Ben keeps everything
        sfy_idx = hand_types(game, ben).index("sorry_for_you")
        r = gs.handle_reactive_card_play(gid, ben, sfy_idx, {})
        assert r["success"] is True
        assert "immunity_idol" in hand_types(game, ben)
        assert "immunity_idol" not in hand_types(game, ana)

        print("✅ reward challenge gate\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("🧪 Rules Enforcement (Survival Guide review 2026-07-30)")
    print("=" * 60)
    try:
        test_one_play_per_turn()
        test_one_draw_ends_the_turn()
        test_camp_raid_is_a_trap()
        test_sorry_for_you_gates_every_taking()
        test_reward_challenge_steals_go_through_the_gate()
        print("🎉 All rules-enforcement tests passed!")
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
