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
        assert "turn is over" in r1["message"]

        # The draw ended the turn all by itself — torch moved off Ana,
        # and every player's flags are fresh for the new turn
        current = game["turnOrder"][game["currentTurnIndex"]]
        assert current != ana, current
        assert game["players"][ana]["hasDrawn"] is False
        assert game["players"][ana]["hasPlayed"] is False

        # Second draw refused — it isn't Ana's turn any more
        r2 = gs.draw_card(gid, playerId=ana)
        print("second draw:", r2.get("message"))
        assert r2["success"] is False
        assert "not your turn" in r2["message"]

        # Playing after the draw refused too
        game["players"][ana]["hand"] = [{"type": "inheritance"}]
        r3 = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": ben})
        print("play after draw:", r3.get("message"))
        assert r3["success"] is False

        # The next player's phase machine starts at the steal step
        phase = gs.rules_engine.get_current_turn_phase(game, current)
        assert phase == "turn_steal", phase

        print("✅ draw discipline (draw auto-ends the turn)\n")
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
        game["players"][ben]["hand"] = [{"type": "camp_raid"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0,
                         params={"targetId": ben, "cardType": "camp_raid"})
        assert r["success"] is True
        assert not game.get("pending_theft")
        assert "camp_raid" in hand_types(game, ana)

        # ...but the Vote Card is never the prize — only Control The Vote takes one
        set_turn(game, ana, played=False)
        game["players"][ana]["hand"] = [{"type": "knowledge_is_power"}]
        game["players"][ben]["hand"] = [{"type": "vote"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0,
                         params={"targetId": ben, "cardType": "vote"})
        assert r["success"] is True
        assert "vote" not in hand_types(game, ana)
        assert "vote" in hand_types(game, ben)

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


def test_the_block_reason_does_not_confirm_the_answer():
    """
    While the reactive window is open, blocked turn actions explain the wait —
    but the refusal reaches whoever tried to act, so it must not confirm that
    the victim is holding Sorry For You. The window itself is what tells the
    HOLDER they may respond.
    """
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== The block reason keeps the secret ===")
        set_turn(game, ana)
        game["players"][ana]["hand"] = [{"type": "the_spy_shack"}]
        game["players"][ben]["hand"] = [{"type": "immunity_idol"}, {"type": "sorry_for_you"}]
        r = gs.play_card(gid, playerId=ana, cardIdx=0, params={"targetId": ben, "takeIndex": 0})
        assert r["success"] is True, r.get("message")
        assert (game.get("pending_theft") or {}).get("reactive_window_open")

        for blocked in (gs.draw_card(gid, playerId=ana), gs.advance_turn(gid)):
            assert blocked["success"] is False
            assert "Sorry For You" not in blocked["message"], blocked["message"]
            assert "may respond to the raid" in blocked["message"], blocked["message"]
            assert "Ben" in blocked["message"], blocked["message"]

        print("✅ block reason keeps the secret\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_three_players_left_rule():
    """
    Rulebook: "If there are only 3 players left and 2 players would be
    eliminated at the same time (leaving you with only 1 player left in the
    game), the Tribal Council Leader decides which of the tied players is
    eliminated. Immediately begin The Final Tribal Council."

    And the flip side: a double whose targets can absorb the flips delivers
    BOTH of them — the deck's elimination math depends on it.
    """
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== The 3-players-left rule ===")
        engine = gs.rules_engine

        # Case 1: both vote-getters on their last card -> leader decides ONE
        game["players"][ana]["characterCards"] = 1
        game["players"][ben]["characterCards"] = 1
        game["players"][cam]["characterCards"] = 2
        outcome = engine.resolve_tribal_eliminations(
            game, {ana: 2, ben: 1}, protected_players=(), idol_players=(),
            elimination_type="double")
        print("both lethal:", outcome["reason"])
        assert outcome["tieBreakNeeded"] is True
        assert sorted(outcome["tiedPlayers"]) == sorted([ana, ben])
        assert outcome["eliminationsNeeded"] == 1
        assert outcome["finalTribalAfter"] is True

        # Case 2: targets can absorb the flips -> the double delivers BOTH
        game["players"][ana]["characterCards"] = 2
        game["players"][ben]["characterCards"] = 2
        outcome = engine.resolve_tribal_eliminations(
            game, {ana: 2, ben: 1}, protected_players=(), idol_players=(),
            elimination_type="double")
        print("absorbable:", outcome["reason"])
        assert outcome["tieBreakNeeded"] is False
        assert sorted(outcome["eliminated"]) == sorted([ana, ben])
        assert outcome["eliminationsNeeded"] == 2

        # Case 3: one lethal, one absorbable -> both flip, one eliminated,
        # exactly 2 remain and Final Tribal follows naturally
        game["players"][ana]["characterCards"] = 1
        game["players"][ben]["characterCards"] = 2
        outcome = engine.resolve_tribal_eliminations(
            game, {ana: 2, ben: 1}, protected_players=(), idol_players=(),
            elimination_type="double")
        assert sorted(outcome["eliminated"]) == sorted([ana, ben])
        assert outcome["eliminationsNeeded"] == 2

        print("✅ three-players-left rule\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_deck_math_never_strands():
    """
    Tyler's invariant: the tribal-card table (3p:4S / 4p:2S+2D / 5p:2S+3D /
    6p:5D) guarantees Final Tribal before the Draw Pile empties, because every
    Tribal delivers its full rating unless the game is ending. Verify the
    arithmetic that the resolution code must now preserve.
    """
    print("=== Deck math invariant ===")
    table = {3: (4, 0), 4: (2, 2), 5: (2, 3), 6: (0, 5)}
    for n, (s_cards, d_cards) in table.items():
        flips = s_cards + 2 * d_cards
        adversarial_max_with_3_alive = 2 * n - 3
        assert flips > adversarial_max_with_3_alive, (
            f"{n} players: {flips} flips cannot force final-2")
    print("✅ every player count is guaranteed to reach Final Tribal\n")


def _open_voting(gs, gid, game):
    """Put the game straight into a tribal voting phase."""
    game["phase"] = "tribal_council"
    game["currentVote"] = {
        "type": "single", "votes": {}, "phase": "voting",
        "councilLeaderId": game["turnOrder"][0], "immunityPlayed": [],
        "tieBreakNeeded": False, "tiedPlayers": [], "eliminated": []
    }
    for p in game["players"].values():
        p["hasVoted"] = False


def test_spent_vote_cards_leave_the_game_not_the_discard():
    """
    The Voting Box is not the Discard Pile. Spent Vote/Extra/Goodwill cards
    used to be discarded; a long game legitimately empties the Draw Pile, the
    discard reshuffles in, and suddenly Vote Cards are drawable — and Camp
    Raid's force-take grabs them "no matter what it is". Tyler watched it
    happen. Spent vote cards leave play; the completion mint is the return.
    """
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== Spent vote cards never enter the discard ===")
        _open_voting(gs, gid, game)
        game["players"][ana]["hand"] = [{"type": "vote"}, {"type": "extra_vote"}]
        gs.rules_engine.sync_vote_counters(game)

        result = gs.cast_vote(gid, voterId=ana,
                              votesData=[{"targetId": ben, "votes": 2}])
        assert result["success"], result.get("message")
        discard_types = [c.get("type") for c in game.get("discard", [])]
        assert "vote" not in discard_types, discard_types
        assert "extra_vote" not in discard_types, discard_types
        # Bookkeeping for the UI survives
        assert game["currentVote"]["cardsSpent"] == ["vote", "extra_vote"]
        print("✅ the Voting Box is not the Discard Pile\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_the_reshuffle_filters_vote_cards_out_of_the_deck():
    """Defense in depth: live saves already carry polluted discards — the
    empty-deck reshuffle must never deal a vote-economy card back out."""
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== The reshuffle never returns vote cards ===")
        set_turn(game, ana, played=True)
        # Keep this assertion about the reshuffle itself. The normal initial
        # deal is randomized and can legitimately give Ana an Extra Vote before
        # the polluted discard is installed, which made this test flaky.
        game["players"][ana]["hand"] = [{"type": "vote"}]
        game["deck"] = []
        game["discard"] = [{"type": "vote"}, {"type": "extra_vote"},
                           {"type": "goodwill_gamble"}, {"type": "camp_raid"}]
        result = gs.draw_card(gid, ana)
        assert result["success"], result.get("message")
        deck_and_hand = [c.get("type") for c in game.get("deck", [])] + \
                        [c.get("type") for c in game["players"][ana]["hand"]]
        assert "extra_vote" not in deck_and_hand, deck_and_hand
        assert "goodwill_gamble" not in deck_and_hand, deck_and_hand
        # Ana's own returned Vote Card isn't in play here; the drawn card and
        # the remaining deck must be the camp_raid alone
        assert "camp_raid" in deck_and_hand, deck_and_hand
        vote_in_deck = [t for t in (c.get("type") for c in game.get("deck", []))
                        if t == "vote"]
        assert not vote_in_deck, vote_in_deck
        print("✅ polluted discards are scrubbed at the reshuffle\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_inheritance_never_transfers_the_vote_card():
    """A dead survivor's Vote Card goes back to the box, not to the heir —
    otherwise the heir votes twice at every council from then on."""
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== Inheritance skips the Vote Card ===")
        game["players"][ana]["inheritanceTarget"] = ben
        game["players"][ben]["hand"] = [{"type": "vote"},
                                        {"type": "goodwill_gamble"},
                                        {"type": "camp_raid"}]
        game["players"][ana]["hand"] = [{"type": "vote"}]
        game["players"][ben]["isEliminated"] = True
        gs.rules_engine.process_elimination_inheritance(game, ben)

        ana_hand = hand_types(game, ana)
        assert ana_hand.count("vote") == 1, ana_hand
        assert "goodwill_gamble" not in ana_hand, ana_hand
        assert "camp_raid" in ana_hand, ana_hand
        print("✅ the heir gets the estate, not the ballot\n")
    finally:
        os.chdir(cwd); shutil.rmtree(tmp, ignore_errors=True)


def test_a_ballot_may_split_across_targets():
    """Official: Extra Votes are separate ballots — 'you know how this works,
    played with your Vote Card for 2 total votes' on anyone you like. The
    server must tally a split ballot; the phone UI builds on this."""
    gs, gid, game, (ana, ben, cam), cwd, tmp = fresh_game()
    try:
        print("=== A split ballot tallies per target ===")
        _open_voting(gs, gid, game)
        game["players"][ana]["hand"] = [{"type": "vote"}, {"type": "extra_vote"}]
        gs.rules_engine.sync_vote_counters(game)

        result = gs.cast_vote(gid, voterId=ana, votesData=[
            {"targetId": ben, "votes": 1},
            {"targetId": cam, "votes": 1},
        ])
        assert result["success"], result.get("message")
        recorded = game["currentVote"]["votes"][ana]
        assert recorded == {ben: 1, cam: 1}, recorded
        print("✅ vote and extra vote can land on different heads\n")
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
        test_the_block_reason_does_not_confirm_the_answer()
        test_three_players_left_rule()
        test_deck_math_never_strands()
        test_spent_vote_cards_leave_the_game_not_the_discard()
        test_the_reshuffle_filters_vote_cards_out_of_the_deck()
        test_inheritance_never_transfers_the_vote_card()
        test_a_ballot_may_split_across_targets()
        print("🎉 All rules-enforcement tests passed!")
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
