#!/usr/bin/env python3

"""
Computer player tests.

Covers the add/remove lifecycle, the house rule that bot games never touch the
Hall of Fame, the decision functions, and — the big one — complete games where
three bots and one scripted human play to a finished winner in both deck modes.
That soak test exercises every mechanic in the box end to end.
"""

import os
import random
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SURVIVOR_BOT_DELAY"] = "0"   # windows collapse to zero for tests

from survivor_server import GameState
import bots
from bots import BotRunner, next_action


def fresh_state():
    tmp = tempfile.mkdtemp()
    original = os.getcwd()
    os.chdir(tmp)
    return GameState(), original, tmp


def test_add_remove_bot():
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing add/remove bot ===")
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")

        # Test: add a bot
        result = gs.add_bot(gid)
        print(f"Add: {result}")
        assert result["success"] is True
        bot_id = result["playerId"]
        assert gs.games[gid]["players"][bot_id]["isBot"] is True
        assert bot_id in gs.games[gid]["turnOrder"]

        # Test: bot names never collide, even past bots.py's 6-name roster
        # (Task A4 moved the cap to 8, one human + 7 bots)
        names = {result["name"]}
        for _ in range(6):
            r = gs.add_bot(gid)
            assert r["success"], r
            names.add(r["name"])
        assert len(names) == 7

        # Test: ninth player refused (cap 8)
        r = gs.add_bot(gid)
        print(f"Over cap: {r}")
        assert r["success"] is False

        # Test: humans can't be removed through remove_bot
        r = gs.remove_bot(gid, playerId=human)
        assert r["success"] is False and "computer players" in r["message"]

        # Test: remove a bot
        r = gs.remove_bot(gid, playerId=bot_id)
        print(f"Remove: {r}")
        assert r["success"] is True
        assert bot_id not in gs.games[gid]["players"]
        assert bot_id not in gs.games[gid]["turnOrder"]

        # Test: no adds or removes after the game starts
        gs.start_full_game(gid)
        assert gs.games[gid]["phase"] != "lobby"
        assert gs.add_bot(gid)["success"] is False
        some_bot = next(p for p, pl in gs.games[gid]["players"].items() if pl.get("isBot"))
        assert gs.remove_bot(gid, playerId=some_bot)["success"] is False

        print("✅ add/remove bot tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_bot_games_never_reach_hall_of_fame():
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing the Hall of Fame guard ===")
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")
        gs.add_player(gid, "Trace", "blue")
        gs.add_bot(gid)
        gs.start_full_game(gid)

        result = gs.record_winner(gid, winnerId=human)
        print(f"record_winner with a bot present: {result}")
        assert result["success"] is False
        assert "Hall of Fame" in result["message"]
        assert not os.path.exists(GameState._WINNERS_FILE)

        # A bot winner is refused just the same
        bot_id = next(p for p, pl in gs.games[gid]["players"].items() if pl.get("isBot"))
        assert gs.record_winner(gid, winnerId=bot_id)["success"] is False

        # Control: an all-human game records normally
        gid2 = gs.create_game()
        h1 = gs.add_player(gid2, "Ana", "red")
        gs.add_player(gid2, "Ben", "blue")
        gs.add_player(gid2, "Cam", "green")
        gs.start_full_game(gid2)
        assert gs.record_winner(gid2, winnerId=h1)["success"] is True
        assert os.path.exists(GameState._WINNERS_FILE)

        print("✅ Hall of Fame guard tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_decision_basics():
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing bot decisions ===")
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")
        gs.add_bot(gid)
        gs.add_bot(gid)
        gs.start_full_game(gid)
        game = gs.games[gid]
        rng = random.Random(7)

        # Test: nothing to do when it's the human's move
        game["currentTurnIndex"] = game["turnOrder"].index(human)
        plan = next_action(game, rng=rng, turn_memory={})
        assert plan is None, plan

        # Test: a bot on the clock steals from the card leader first
        bot_id = next(p for p in game["turnOrder"] if game["players"][p].get("isBot"))
        game["currentTurnIndex"] = game["turnOrder"].index(bot_id)
        game["players"][bot_id]["hasStolen"] = False
        plan = next_action(game, rng=rng, turn_memory={})
        assert plan and plan["method"] == "steal_card", plan
        assert plan["kwargs"]["thiefId"] == bot_id
        assert plan["kwargs"]["targetId"] != bot_id

        # Test: bots never steal from or vote for the Necklace wearer
        others = [p for p in game["turnOrder"] if p != bot_id]
        game["necklaceHolder"] = others[0]
        # give the necklace holder the biggest hand so they'd otherwise be chosen
        game["players"][others[0]]["hand"] = [{"type": "vote"}] * 9
        target = bots._biggest_threat(game, bot_id)
        assert target != others[0]
        game["necklaceHolder"] = None

        # Test: an all-bot game goes quiet (no humans left to watch)
        for pid in list(game["players"]):
            game["players"][pid]["isBot"] = True
        assert next_action(game, rng=rng, turn_memory={}) is None
        game["players"][human]["isBot"] = False

        print("✅ decision tests passed!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def _highest_bidder_state(style="normal", current_bid=0):
    """Small pure-decision fixture; no server or scheduler needed."""
    actions = ["bid"] if current_bid == 0 else ["bid", "pass"]
    return {
        "phase": "playing",
        "settings": {"botStyle": style},
        "players": {
            "human": {"name": "Tyler", "isBot": False},
            "bot": {"name": "Coconut", "isBot": True},
        },
        "turnOrder": ["human", "bot"],
        "challenge": {
            "type": "highest_bidder",
            "phase": "bidding",
            "round": 1,
            "starterId": "human",
            "currentPlayerId": "bot",
            "currentBid": current_bid,
            "maxBid": 11,
            "actions": actions,
            "knockedOut": [],
        },
    }


def test_highest_bidder_bot_limits_follow_style_and_stay_private():
    samples = {}
    for style, expected_range in bots.HIGHEST_BIDDER_CAP_RANGE.items():
        caps = []
        openings = set()
        for seed in range(100):
            game = _highest_bidder_state(style)
            memory = {}
            plan = next_action(game, rng=random.Random(seed), turn_memory=memory)
            assert plan["method"] == "challenge_action"
            assert plan["kwargs"]["action"] == "bid"
            openings.add(plan["kwargs"]["value"])

            state = memory["highest_bidder"]
            cap = state["caps"]["bot"]
            assert expected_range[0] <= cap <= expected_range[1]
            caps.append(cap)

            # The cap belongs to BotRunner memory, never the public Challenge.
            assert "caps" not in game["challenge"]

            # Re-reading the same round preserves the reservation bid.
            game["challenge"]["currentBid"] = 1
            game["challenge"]["actions"] = ["bid", "pass"]
            next_action(game, rng=random.Random(seed + 1000), turn_memory=memory)
            assert memory["highest_bidder"]["caps"]["bot"] == cap

        samples[style] = sum(caps) / len(caps)
        assert len(openings) > 1, f"{style} bots should vary their opening bid"

    assert samples["chill"] < samples["normal"] < samples["cutthroat"]


def test_highest_bidder_bots_mix_bids_and_passes_before_the_limit():
    # Test each style near the middle of its risk band.  Across seeded bots we
    # should see both choices, rather than a deterministic march to eleven.
    decision_points = {"chill": 3, "normal": 5, "cutthroat": 7}
    for style, current_bid in decision_points.items():
        decisions = set()
        for seed in range(200):
            game = _highest_bidder_state(style, current_bid=current_bid)
            plan = next_action(game, rng=random.Random(seed), turn_memory={})
            decisions.add(plan["kwargs"]["action"])
        assert decisions == {"bid", "pass"}, (style, decisions)


def test_highest_bidder_bots_never_bid_the_entire_bag():
    for style in bots.HIGHEST_BIDDER_CAP_RANGE:
        for seed in range(100):
            game = _highest_bidder_state(style, current_bid=10)
            plan = next_action(game, rng=random.Random(seed), turn_memory={})
            assert plan["kwargs"]["action"] == "pass", (style, seed, plan)
            assert plan["kwargs"].get("value") is None


# ─────────────────────────── the full-game soak ──────────────────────────────

def _human_move(gs, gid, human, rng):
    """A minimal legal-move script for the one human seat. Returns True if it
    acted. Mirrors what a person tapping the obvious buttons would do."""
    game = gs.games.get(gid)
    if not game:
        return False
    phase = game.get("phase")
    players = game["players"]
    me = players.get(human)
    if not me:
        return False

    theft = game.get("pending_theft")
    if theft and theft.get("reactive_window_open"):
        if theft.get("targetId") == human:
            gs.complete_pending_theft(gid)
            return True
        return False

    # A blocked raid leaves the raider owing a chosen discard, and the table is
    # frozen until it is paid. A human who never answers would spin here
    # forever — the real game has a forfeit clock, but a test loop runs faster
    # than any wall-clock deadline.
    pd = game.get("pending_discards")
    if pd and human in (pd.get("awaiting") or []):
        hand = players[human].get("hand") or []
        givable = [i for i, c in enumerate(hand) if c.get("type") != "vote"]
        if givable:
            gs.choose_penalty_discard(gid, playerId=human, cardIdx=givable[0])
            return True
        return False

    it = game.get("interaction")
    if it:
        if it.get("phase") == "picking" and human in it.get("awaiting", []):
            kind = it.get("type")
            value = (rng.choice(["rock", "paper", "scissors"]) if kind == "do_or_die"
                     else rng.randint(1, 3) if kind == "power_pair" else rng.randint(1, 5))
            gs.interaction_action(gid, playerId=human, action="pick", value=value)
            return True
        if it.get("phase") == "give" and human in it.get("awaiting", []):
            # Not index 0 blindly — the Vote Card can't be handed over, and
            # offering it would be refused on a loop.
            givable = next((i for i, c in enumerate(me.get("hand") or [])
                            if c.get("type") != "vote"), None)
            if givable is not None:
                gs.interaction_action(gid, playerId=human, action="give", value=givable)
                return True
        if it.get("phase") == "choose_victim" and it.get("winnerId") == human:
            victim = next((p for p in game["turnOrder"]
                           if p != human and not players[p].get("isEliminated")), None)
            if victim:
                gs.interaction_action(gid, playerId=human, action="steal_from", value=victim)
                return True
        if it.get("phase") == "complete" and it.get("initiatorId") == human:
            gs.interaction_action(gid, playerId=human, action="dismiss")
            return True
        return False

    ch = game.get("challenge")
    if ch:
        if ch.get("phase") == "complete" and ch.get("winnerId") == human:
            gs.challenge_action(gid, playerId=human, action="dismiss")
            return True
        if ch.get("phase") != "complete" and ch.get("currentPlayerId") == human:
            actions = ch.get("actions") or []
            if actions:
                action, value = actions[0], None
                if action == "bid":
                    nxt = ch.get("currentBid", 0) + 1
                    if nxt > ch.get("maxBid", nxt) and "pass" in actions:
                        action = "pass"
                    else:
                        value = nxt
                elif action == "pull" and ch.get("type") == "lowest_score_loses":
                    value = 1
                elif action == "steal":
                    action = "pull" if "pull" in actions else action
                gs.challenge_action(gid, playerId=human, action=action, value=value)
                return True
        return False

    if phase == "playing":
        order = game["turnOrder"]
        current = order[game.get("currentTurnIndex", 0) % len(order)]
        if current != human or me.get("isEliminated"):
            return False
        if not me.get("hasStolen"):
            target = next((p for p in order
                           if p != human and not players[p].get("isEliminated")), None)
            if target:
                gs.steal_card(gid, thiefId=human, targetId=target)
                return True
        gs.draw_card(gid, playerId=human)
        # Drawing ends the turn - the server advances it on its own.
        return True

    if phase == "tribal_council":
        cv = game.get("currentVote") or {}
        vph = cv.get("phase")
        leader = cv.get("councilLeaderId")

        # An idol is on the table awaiting its answer. This outranks the rest
        # of the ceremony: a human holding a nullifier who says nothing freezes
        # the council for everyone, which is precisely the wedge this branch
        # exists to prove cannot happen.
        window = game.get("pending_nullifier")
        if window and window.get("reactive_window_open"):
            if human in (window.get("_responderIds") or []) \
                    and human not in (window.get("_answered") or []):
                gs.decline_nullifier(gid, playerId=human)
                return True
            return False
        if vph == "voting" and human not in (cv.get("votes") or {}) \
                and not me.get("isEliminated"):
            mandatory = max(0, me.get("mandatoryVotes", 1))
            target = next((p for p in game["turnOrder"]
                           if p != human and not players[p].get("isEliminated")
                           and p != game.get("necklaceHolder")), None)
            if mandatory and target:
                gs.cast_vote(gid, voterId=human,
                             votesData=[{"targetId": target, "votes": mandatory}])
            else:
                gs.cast_vote(gid, voterId=human, votesData=[])
            return True
        if leader == human:
            transitions = {"announcement": "advantage_play",
                           "advantage_play": "discussion",
                           "discussion": "voting"}
            if vph in transitions:
                gs.advance_tribal_phase(gid, phase=transitions[vph])
                return True
            if vph == "voting":
                # A vote-banned player never places a ballot — the box is full
                # without them (Block A Vote).
                alive = [p for p in game["turnOrder"]
                         if not players[p].get("isEliminated")
                         and not players[p].get("voteBanned")]
                if len(cv.get("votes") or {}) >= len(alive):
                    # Seals the box and opens the idol window; it does NOT
                    # tally. The Leader taps a second time from `immunity`.
                    gs.reveal_votes(gid)
                    return True
                return False
            if vph == "immunity":
                # The idol window is mandatory now. A leader who reveals once
                # and never comes back leaves the ceremony parked here — which
                # is exactly what this helper used to do, spinning on
                # complete_tribal forever.
                gs.reveal_votes(gid)
                return True
            if cv.get("tieBreakNeeded") and cv.get("tiedPlayers"):
                gs.tie_break(gid, leaderId=human, chosenId=cv["tiedPlayers"][0])
                return True
            gs.complete_tribal(gid)
            return True
        return False

    if phase in ("final", "final_tribal"):
        ft = game.get("finalTribal") or {}
        fph = ft.get("phase")
        jury = ft.get("jury") or []
        finalists = ft.get("finalists") or []
        if fph == "questions" and ft.get("leader") == human:
            gs.advance_final_phase(gid, phase="voting")
            return True
        if fph == "deliberation" and human in jury \
                and human not in (ft.get("juryReady") or []):
            gs.signal_jury_ready(gid, juryMemberId=human)
            return True
        if fph == "deliberation" and ft.get("leader") == human:
            ready = ft.get("juryReady") or []
            if all(p in ready for p in jury):
                gs.advance_final_phase(gid, phase="voting")
                return True
            return False
        if fph == "voting" and human in jury and human not in (ft.get("votes") or {}):
            gs.cast_final_vote(gid, juryMemberId=human, finalistId=finalists[0])
            return True
        if fph == "reveal" and ft.get("tieBreakNeeded") and ft.get("leader") == human:
            gs.break_final_tie(gid, leaderId=human, chosenWinner=finalists[0])
            return True
        return False

    return False


def _play_full_bot_game(deck_mode, expansion, seed, settings=None):
    gs, original_cwd, tmp = fresh_state()
    try:
        rng = random.Random(seed)
        gid = gs.create_game(deckMode=deck_mode, expansion=expansion,
                             settings=settings)
        human = gs.add_player(gid, "Tyler", "red")
        for _ in range(3):
            assert gs.add_bot(gid)["success"]
        gs.start_full_game(gid)

        runner = BotRunner(gs, rng=rng)
        stall = 0
        for step in range(20000):
            game = gs.games.get(gid)
            if not game or game.get("phase") == "finished":
                break
            acted = runner.step(gid)
            acted = _human_move(gs, gid, human, rng) or acted
            if acted:
                stall = 0
            else:
                stall += 1
                if stall > 50:
                    cv = game.get("currentVote") or {}
                    ft = game.get("finalTribal") or {}
                    raise AssertionError(
                        f"Game wedged: phase={game.get('phase')} "
                        f"vote_phase={cv.get('phase')} final_phase={ft.get('phase')} "
                        f"interaction={bool(game.get('interaction'))} "
                        f"challenge={bool(game.get('challenge'))} "
                        f"theft={bool(game.get('pending_theft'))} "
                        f"nullifier={game.get('pending_nullifier')}")
        else:
            raise AssertionError("Game did not finish within the step budget")

        game = gs.games[gid]
        assert game.get("phase") == "finished", game.get("phase")
        winner = game.get("winner")
        winner_id = winner.get("playerId") if isinstance(winner, dict) else winner
        assert winner_id in game["players"], f"finished without a winner: {winner!r}"
        # And the house rule held throughout: nothing was carved into the record
        assert not os.path.exists(GameState._WINNERS_FILE)
        return game["players"][winner_id].get("name", "?"), step
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_full_game_official():
    print("=== Full game: 1 human + 3 bots, official deck ===")
    for seed in (11, 23):
        name, steps = _play_full_bot_game("official", False, seed)
        print(f"  seed {seed}: {name} won after {steps} steps")
    print("✅ official-deck bot games finish!\n")


def test_full_game_extended_expansion():
    print("=== Full game: 1 human + 3 bots, extended deck + Rocks ===")
    for seed in (5, 42):
        name, steps = _play_full_bot_game("extended", True, seed)
        print(f"  seed {seed}: {name} won after {steps} steps")
    print("✅ extended+expansion bot games finish!\n")


def test_refusal_circuit_breaker():
    """A bot stuck on a permanently-refused action sits out instead of hammering.

    The live wedge: one illegal move retried every ~2s for hours, spamming the
    log long after the game was unrecoverable. After enough consecutive
    refusals the runner cools the game down and stops even asking for a plan.
    """
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing refusal circuit breaker ===")
        gid = gs.create_game()
        gs.add_player(gid, "Tyler", "red")
        for _ in range(3):
            assert gs.add_bot(gid)["success"]
        gs.start_full_game(gid)

        runner = BotRunner(gs, rng=random.Random(7))
        bot_id = next(p for p, pl in gs.games[gid]["players"].items()
                      if pl.get("isBot"))

        # With no Challenge running this is refused every time — the shape of
        # the live wedge.
        plan = {"method": "challenge_action",
                "kwargs": {"playerId": bot_id, "action": "pull", "value": 1}}
        calls = {"n": 0}

        def stuck(*args, **kwargs):
            calls["n"] += 1
            return plan

        orig = bots.next_action
        bots.next_action = stuck
        try:
            for _ in range(bots.REFUSAL_BREAKER_STRIKES):
                assert runner.step(gid) is False
            assert runner._cooldown.get(gid, 0) > time.time(), \
                "breaker should have tripped"
            before = calls["n"]
            assert runner.step(gid) is False
            assert calls["n"] == before, "a cooled-down game must not be planned"
        finally:
            bots.next_action = orig
        print("✅ breaker trips and the game sits out the cooldown!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_bot_draw_logs_a_redacted_entry():
    """The shared history says a bot drew — never what it drew."""
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing bot draws stay hidden in the history ===")
        gid = gs.create_game()
        gs.add_player(gid, "Tyler", "red")
        for _ in range(3):
            assert gs.add_bot(gid)["success"]
        gs.start_full_game(gid)
        game = gs.games[gid]

        bot_id = next(p for p, pl in game["players"].items() if pl.get("isBot"))
        game["currentTurnIndex"] = game["turnOrder"].index(bot_id)
        bot = game["players"][bot_id]
        bot["hasStolen"] = True
        bot["hasPlayed"] = True          # forces the draw branch
        game["deck"].insert(0, {"type": "the_spy_shack"})   # known, name-able

        runner = BotRunner(gs, rng=random.Random(3))
        assert runner.step(gid) is True
        entry = (game.get("eventLog") or [])[-1]["msg"]
        print(f"  log entry: {entry}")
        assert "Spy Shack" not in entry, entry
        assert "drew a card" in entry, entry
        print("✅ bot draws are redacted in the story so far!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def _bot_led_council(gs, gid, human, human_hand):
    """Stage a bot-led Tribal Council with every ballot in and a scripted human hand."""
    game = gs.games[gid]
    leader = next(p for p in game["turnOrder"] if game["players"][p].get("isBot"))
    gs._trigger_tribal_council(game, "single", drawer_id=leader)
    gs.start_voting(gid, "elimination")

    for pid in game["turnOrder"]:
        game["players"][pid]["hand"] = [{"type": "vote"}]
    game["players"][human]["hand"] = list(human_hand)
    gs.rules_engine.sync_vote_counters(game)

    for pid in game["turnOrder"]:
        target = next(p for p in game["turnOrder"] if p != pid)
        mandatory = max(0, game["players"][pid].get("mandatoryVotes", 0))
        votes = [{"targetId": target, "votes": mandatory}] if mandatory else []
        res = gs.cast_vote(gid, voterId=pid, votesData=votes)
        assert res["success"], res.get("message")
    return game, leader


def test_bot_leader_opens_the_idol_window_for_a_human():
    """
    A Hidden Immunity Idol is playable only AFTER everyone has voted. A bot
    Council Leader used to reveal straight out of the voting phase, so a human
    holding an idol never got a window in a bot-led council.
    """
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing the bot leader's idol window ===")
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")
        for _ in range(3):
            assert gs.add_bot(gid)["success"]
        gs.start_full_game(gid)

        game, leader = _bot_led_council(
            gs, gid, human, [{"type": "immunity_idol"}, {"type": "vote"}])
        assert game["currentVote"]["phase"] == "voting"

        runner = BotRunner(gs, rng=random.Random(11))
        assert runner.step(gid) is True
        assert game["currentVote"]["phase"] == "immunity", \
            f"bot leader skipped the idol window: {game['currentVote']['phase']}"

        # The human can actually use the window
        played = gs.play_immunity(gid, playerId=human, targetId=human)
        assert played["success"], played.get("message")
        assert game["players"][human].get("immunityIdolProtection")

        # ...and the leader still closes the ceremony from the immunity phase
        assert runner.step(gid) is True
        assert game["currentVote"]["phase"] == "reveal", game["currentVote"]["phase"]
        assert game["currentVote"]["voteResults"] is not None
        print("✅ bot leaders give humans a real idol window!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_bot_leader_opens_the_idol_window_even_when_nobody_can_use_it():
    """The window is unconditional — its timing must not betray a hand.

    This used to assert the opposite: a bot Leader peeked into human hands and
    skipped the ceremony when nobody held an idol. That was two faults in one.
    It read information no Council Leader is entitled to, and it made the
    length of the pause a tell — a table that notices "the long pause means
    somebody has an idol" has been handed, by the pacing alone, the exact
    secret the Survival Guide asks the Leader to discover by asking out loud.
    """
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing the idol window opens for everyone ===")
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")
        for _ in range(3):
            assert gs.add_bot(gid)["success"]
        gs.start_full_game(gid)

        # A human holding nothing but their Vote Card: no idol anywhere at the
        # table, and the window opens anyway.
        game, leader = _bot_led_council(gs, gid, human, [{"type": "vote"}])
        runner = BotRunner(gs, rng=random.Random(11))
        assert runner.step(gid) is True
        assert game["currentVote"]["phase"] == "immunity", game["currentVote"]["phase"]
        print("✅ the idol window opens whether or not it can be used!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_bots_never_wait_on_a_vote_banned_player():
    """Block A Vote takes its target out of the box — bots must not stall on it."""
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing bots and Block A Vote ===")
        gid = gs.create_game()
        human = gs.add_player(gid, "Tyler", "red")
        for _ in range(3):
            assert gs.add_bot(gid)["success"]
        gs.start_full_game(gid)
        game = gs.games[gid]

        leader = next(p for p in game["turnOrder"] if game["players"][p].get("isBot"))
        banned = next(p for p in game["turnOrder"]
                      if game["players"][p].get("isBot") and p != leader)
        gs._trigger_tribal_council(game, "single", drawer_id=leader)
        gs.start_voting(gid, "elimination")
        for pid in game["turnOrder"]:
            game["players"][pid]["hand"] = [{"type": "vote"}]
        gs.rules_engine.sync_vote_counters(game)
        game["players"][banned]["voteBanned"] = True

        # A banned bot is never asked to vote, and never blocks the reveal
        runner = BotRunner(gs, rng=random.Random(5))
        # Runs to the tally, not merely out of `voting` — the ceremony now
        # passes through the mandatory idol window on its way to the reveal.
        for _ in range(20):
            if game["currentVote"]["phase"] == "reveal":
                break
            if not runner.step(gid) and game["currentVote"]["phase"] == "voting":
                # only the human's ballot is left to place
                gs.cast_vote(gid, voterId=human,
                             votesData=[{"targetId": leader, "votes": 1}])
        assert banned not in (game["currentVote"].get("votes") or {})
        assert game["currentVote"]["phase"] == "reveal", game["currentVote"]["phase"]
        assert game["currentVote"]["blockedVoters"] == [banned]
        print("✅ bots resolve a council with a blocked player!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_lost_timer_self_heals():
    """A spawn_later timer that never fires must not wedge the game forever.

    Reproduces the five-hour rocks wedge: poke() marks the game scheduled, the
    scheduler loses the callback, and every later poke/heartbeat used to bail
    out on the stale entry. With expiring entries, the next poke after
    TIMER_GRACE re-arms the timer.
    """
    gs, original_cwd, tmp = fresh_state()
    try:
        print("=== Testing lost-timer self-healing ===")
        gid = gs.create_game()
        gs.add_player(gid, "Tyler", "red")
        gs.add_bot(gid)

        runner = BotRunner(gs, rng=random.Random(7))
        fired = []
        runner.attach(lambda delay, fn, *a: fired.append((delay, fn, a)))

        # First poke arms a timer; simulate the scheduler losing it (we never
        # invoke the callback). A pending, in-grace entry must block re-arming.
        runner.poke(gid, delay=0.05)
        assert len(fired) == 1, "first poke should schedule"
        runner.poke(gid, delay=0.05)
        assert len(fired) == 1, "a live pending timer must not double-schedule"

        # Once the timer is overdue past its grace, poke treats it as lost.
        runner._scheduled[gid] = time.time() - (bots.TIMER_GRACE + 1)
        runner.poke(gid, delay=0.05)
        assert len(fired) == 2, "an overdue entry must re-arm (the wedge fix)"

        # And a timer that actually fires clears the entry the normal way.
        delay, fn, args = fired[-1]
        fn(*args)
        assert gid not in runner._scheduled, "_tick clears the entry"
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("🧪 Testing Computer Players")
    print("=" * 50)

    try:
        test_add_remove_bot()
        test_bot_games_never_reach_hall_of_fame()
        test_decision_basics()
        test_refusal_circuit_breaker()
        test_bot_draw_logs_a_redacted_entry()
        test_bot_leader_opens_the_idol_window_for_a_human()
        test_bot_leader_opens_the_idol_window_even_when_nobody_can_use_it()
        test_bots_never_wait_on_a_vote_banned_player()
        test_full_game_official()
        test_full_game_extended_expansion()
        test_lost_timer_self_heals()
        print("🎉 All computer player tests passed!")
    except AssertionError as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
