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

        # Test: a full human-plus-bot lobby uses only the curated names. The
        # numeric-suffix path is a defensive backstop, not ordinary UX.
        names = {result["name"]}
        for _ in range(6):
            r = gs.add_bot(gid)
            assert r["success"], r
            names.add(r["name"])
        assert len(names) == 7
        assert names.issubset(set(bots.BOT_NAMES)), names
        assert all(not name[-1:].isdigit() for name in names), names

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


def test_bot_leader_opens_final_deliberation_before_voting():
    """The jury-ready finger lives in deliberation, so bots cannot skip it."""
    game = {
        "phase": "final_tribal",
        "players": {
            "finalist": {"name": "Tyler", "isBot": False, "isEliminated": False},
            "leader": {"name": "Coconut", "isBot": True, "isEliminated": True},
        },
        "turnOrder": ["finalist", "leader"],
        "finalTribal": {
            "phase": "questions",
            "leader": "leader",
            "jury": ["leader"],
            "finalists": ["finalist"],
        },
    }

    plan = next_action(
        game,
        phase_age=lambda _: 999,
        turn_memory={},
        rng=random.Random(7),
    )
    assert plan["method"] == "advance_final_phase"
    assert plan["kwargs"] == {"phase": "deliberation"}


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
            gs.advance_final_phase(gid, phase="deliberation")
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


# ───────────────────────── D2: tribal votes stop clumping ─────────────────────

def _vote_game(hands, necklace=None, eliminated=(), bot_ids=None, style="normal",
               gid="voteg", council=0):
    """Minimal fixture for _vote_target: hands is {pid: cardCount}. Every pid
    not named in `eliminated` is alive; every pid not named in `bot_ids`
    (default: everyone) is still scored the same way — D2's whole point is
    that no path may exclude a human."""
    bot_ids = set(hands.keys()) if bot_ids is None else set(bot_ids)
    return {
        "id": gid,
        "turnOrder": list(hands.keys()),
        "necklaceHolder": necklace,
        "settings": {"botStyle": style},
        "_ledger": {"councilIndex": council, "players": {}},
        "players": {
            pid: {"hand": [{"type": "vote"}] * n,
                  "isEliminated": pid in eliminated,
                  "isBot": pid in bot_ids}
            for pid, n in hands.items()
        },
    }


def test_vote_target_favours_the_biggest_hand_including_a_human():
    print("=== Testing D2: votes chase the biggest hand, humans included ===")
    hands = {"bot1": 2, "bot2": 3, "human": 9}
    game = _vote_game(hands, bot_ids={"bot1", "bot2"})
    for council in range(10):
        game["_ledger"] = {"councilIndex": council, "players": {}}
        target1 = bots._vote_target(game, "bot1")
        target2 = bots._vote_target(game, "bot2")
        assert target1 == "human", (council, target1)
        assert target2 == "human", (council, target2)
    print("✅ the human holding the most cards gets voted for, every council!\n")


def test_vote_target_breaks_the_bloc_on_near_equal_scores():
    print("=== Testing D2: bots don't clump on one target when scores tie ===")
    hands = {f"bot{i}": 3 for i in range(8)}   # identical hands, empty ledger
    game = _vote_game(hands)
    picks = {bots._vote_target(game, pid) for pid in hands}
    picks.discard(None)
    print(f"  distinct targets chosen: {picks}")
    assert len(picks) > 1, f"every bot converged on the same target: {picks}"
    print("✅ near-identical bots split their votes instead of clumping!\n")


def test_vote_target_never_targets_self_necklace_or_eliminated():
    print("=== Testing D2: unvotable players are structurally excluded ===")
    hands = {"bot1": 1, "necklace_holder": 20, "eliminated_guy": 20, "bot2": 2}
    game = _vote_game(hands, necklace="necklace_holder",
                      eliminated=("eliminated_guy",))
    target = bots._vote_target(game, "bot1")
    assert target not in ("bot1", "necklace_holder", "eliminated_guy"), target
    assert target == "bot2", target   # the only other legal candidate
    print("✅ the necklace holder and the eliminated are never picked!\n")


def test_vote_target_is_deterministic():
    print("=== Testing D2: identical inputs give identical output ===")
    hands = {"bot1": 2, "bot2": 4, "bot3": 4}
    game = _vote_game(hands)
    first = bots._vote_target(game, "bot1")
    second = bots._vote_target(game, "bot1")
    assert first == second, (first, second)
    print("✅ repeated calls with the same state agree!\n")


# ───────────────────────────── D3: a jury with a memory ───────────────────────

def _jury_game(finalists, jurors, ledger_players=None, hands=None, style="normal",
               gid="juryg", council=5):
    """Minimal fixture for _jury_vote."""
    hands = hands or {}
    players = {}
    for pid in finalists:
        players[pid] = {"hand": [{"type": "vote"}] * hands.get(pid, 1), "isBot": True,
                        "isEliminated": False}
    for pid in jurors:
        players[pid] = {"hand": [{"type": "vote"}], "isBot": True, "isEliminated": True}
    return {
        "id": gid,
        "turnOrder": finalists + jurors,
        "necklaceHolder": None,
        "settings": {"botStyle": style},
        "players": players,
        "_ledger": {"councilIndex": council, "players": dict(ledger_players or {})},
    }


def test_jury_vote_punishes_the_finalist_who_blindsided_the_juror():
    print("=== Testing D3: betrayal at MY elimination council loses the vote ===")
    ledger_players = {
        "juror": {"eliminatedAtCouncil": 2,
                  "votesAgainst": [{"council": 2, "voters": {"finA": 1}}]},
    }
    game = _jury_game(["finA", "finB"], ["juror"], ledger_players=ledger_players)
    pick = bots._jury_vote(game, "juror", ["finA", "finB"])
    assert pick == "finB", pick
    print("✅ the finalist who blindsided the juror loses their vote!\n")


def test_jury_vote_rewards_a_loyal_finalist():
    print("=== Testing D3: voting together is a positive with the jury ===")
    ledger_players = {
        "juror": {"votesCast": [{"council": 0, "votes": {"someone": 1}},
                                {"council": 1, "votes": {"someone-else": 1}}]},
        "finA": {"votesCast": [{"council": 0, "votes": {"someone": 1}},
                               {"council": 1, "votes": {"someone-else": 1}}]},
        "finB": {"votesCast": [{"council": 0, "votes": {"nobody1": 1}},
                               {"council": 1, "votes": {"nobody2": 1}}]},
    }
    game = _jury_game(["finA", "finB"], ["juror"], ledger_players=ledger_players)
    pick = bots._jury_vote(game, "juror", ["finA", "finB"])
    assert pick == "finA", pick
    print("✅ a finalist who voted alongside the juror wins their vote!\n")


def test_jury_can_split():
    """Three jury bots, the SAME botStyle dial, and one game — but each
    juror's own history with the finalists differs, so they don't have to
    agree. This is the direct fix for finding 10 (a bot jury was always
    unanimous)."""
    print("=== Testing D3: a bot jury can disagree ===")
    ledger_players = {
        # A strong résumé that (absent any personal grudge) sways a juror
        # toward finA — and a finB who did nothing at all.
        "finA": {"challengeWins": 3, "idolsPlayed": 2},
        "finB": {},
        # juror_x was personally blindsided by finA at their own elimination
        # council — betrayal outweighs finA's résumé for juror_x alone.
        "juror_x": {"eliminatedAtCouncil": 1,
                    "votesAgainst": [{"council": 1, "voters": {"finA": 1}}]},
        # juror_y and juror_z have no history with either finalist, so
        # finA's résumé (and finB's "did nothing" penalty) carries them.
        "juror_y": {},
        "juror_z": {},
    }
    game = _jury_game(["finA", "finB"], ["juror_x", "juror_y", "juror_z"],
                      ledger_players=ledger_players,
                      hands={"finA": 1, "finB": 1})

    votes = {j: bots._jury_vote(game, j, ["finA", "finB"])
             for j in ("juror_x", "juror_y", "juror_z")}
    print(f"  jury votes: {votes}")
    assert votes["juror_x"] == "finB", votes
    assert votes["juror_y"] == "finA", votes
    assert votes["juror_z"] == "finA", votes
    assert len(set(votes.values())) > 1, "the jury must not be forced unanimous"
    print("✅ the jury splits when the jurors' own histories differ!\n")


def test_jury_vote_robbery_direction_and_style_asymmetry():
    """The robbery signal reads MY ledger keyed by the finalist — cards
    they took from me. The reverse direction (cards I took from them)
    must count for nothing, and the sign flips with botStyle: a chill
    juror resents the robbery, a cutthroat juror respects it. Regression:
    the first cut read cand_entry['stolenFrom'][juror] — exactly
    backwards — and no test caught it."""
    print("=== Testing D3: robbery direction + chill/cutthroat asymmetry ===")
    ledger_players = {
        # finA robbed the juror three times; finB never touched them.
        "juror": {"stolenFrom": {"finA": 3}},
    }
    chill = _jury_game(["finA", "finB"], ["juror"],
                       ledger_players=ledger_players, style="chill")
    assert bots._jury_vote(chill, "juror", ["finA", "finB"]) == "finB", \
        "a chill juror must resent the finalist who robbed them"
    cutthroat = _jury_game(["finA", "finB"], ["juror"],
                           ledger_players=ledger_players, style="cutthroat")
    assert bots._jury_vote(cutthroat, "juror", ["finA", "finB"]) == "finA", \
        "a cutthroat juror must respect the finalist who robbed them"

    # The reverse direction is not robbery: the JUROR robbed finA. That
    # fact lives on finA's entry and must not sway this juror's ballot in
    # either style — equal hands + jitter-only otherwise, so just assert
    # both styles agree with the no-history baseline.
    reverse = {"finA": {"stolenFrom": {"juror": 3}}}
    for style in ("chill", "cutthroat"):
        baseline = bots._jury_vote(
            _jury_game(["finA", "finB"], ["juror"], ledger_players={}, style=style),
            "juror", ["finA", "finB"])
        swayed = bots._jury_vote(
            _jury_game(["finA", "finB"], ["juror"], ledger_players=reverse, style=style),
            "juror", ["finA", "finB"])
        assert swayed == baseline, \
            f"cards the juror took from a finalist must not read as robbery ({style})"
    print("✅ robbery points the right way, and the styles disagree on purpose!\n")


def test_kip_guess_is_never_an_illegal_demand():
    """The bot's Knowledge Is Power guess list used to include "vote" — a
    demand the engine refuses every single time (only Control The Vote takes
    a Vote Card), so a third of bot KIP plays burned the card for nothing
    (seen live: Tiki, game b11498a9). Now that the refusal keeps the card in
    hand, an illegal guess would also loop forever — the guess must be legal
    by construction."""
    print("=== Testing bots: KIP never demands the undemandable ===")
    gs, original_cwd, tmp = fresh_state()
    try:
        gid = gs.create_game()
        gs.add_player(gid, "Tyler", "red")
        gs.add_bot(gid)
        gs.add_bot(gid)
        gs.start_full_game(gid)
        game = gs.games[gid]
        bot_id = next(p for p, pl in game["players"].items() if pl.get("isBot"))
        game["players"][bot_id]["hand"] = [{"type": "knowledge_is_power"}]
        for seed in range(40):
            plan = bots._choose_card_play(game, bot_id, random.Random(seed))
            if plan is None:
                continue
            _, params = plan
            assert params.get("cardType") != "vote", \
                "a Vote Card can never be demanded — the guess list must not offer it"
        print("✅ every KIP guess is a legal demand!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_bot_gives_a_drawn_goodwill_at_council():
    """Since the `given` fix a drawn Goodwill Gamble only ever votes in
    someone ELSE'S hand — so a bot holding one gives it away during the
    advantage/discussion window, and one holding a RECEIVED (given) goodwill
    must NOT try to re-gift it (the server refuses, and a refused action
    proposed every tick is a wedge)."""
    print("=== Testing bots: a drawn goodwill is given, a received one is kept ===")
    gs, original_cwd, tmp = fresh_state()
    try:
        gid = gs.create_game()
        gs.add_player(gid, "Tyler", "red")
        gs.add_bot(gid)
        gs.add_bot(gid)
        gs.start_full_game(gid)
        game = gs.games[gid]
        bot_id = next(p for p, pl in game["players"].items() if pl.get("isBot"))
        gs._trigger_tribal_council(game, "single")
        gs.advance_tribal_phase(gid, "advantage_play")

        game["players"][bot_id]["hand"] = [{"type": "vote"},
                                           {"type": "goodwill_gamble"}]
        plan = bots._tribal_action(game, lambda k: 0.0, random.Random(3))
        assert plan is not None, "the bot should give its drawn goodwill"
        assert plan["method"] == "play_tribal_advantage", plan
        assert plan["kwargs"]["advantageType"] == "goodwill_gamble"
        target = plan["kwargs"]["targetId"]
        assert target != bot_id and target in game["players"]

        # Actually give it through the real server path — the plan must be
        # accepted, and the condition must clear so it can't re-fire.
        r = gs.play_tribal_advantage(gid, plan["kwargs"]["playerId"],
                                     "goodwill_gamble", target)
        assert r["success"], r.get("message")
        again = bots._tribal_action(game, lambda k: 0.0, random.Random(3))
        assert again is None or again.get("kwargs", {}).get("advantageType") != "goodwill_gamble", \
            "a given goodwill must never be proposed again"

        # A RECEIVED goodwill is a ballot, not a gift: the recipient bot
        # (if the target was a bot) must not try to pass it on.
        holder = target
        if game["players"][holder].get("isBot"):
            plan2 = bots._tribal_action(game, lambda k: 0.0, random.Random(3))
            assert plan2 is None or plan2.get("kwargs", {}).get("playerId") != holder, \
                "the recipient must keep the ballot it was given"
        print("✅ goodwill flows one way, and never wedges!\n")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def test_jury_vote_empty_ledger_falls_back_to_hand_size():
    print("=== Testing D3: an empty ledger falls back to the hand-count read ===")
    game = _jury_game(["finA", "finB"], ["juror"], ledger_players={},
                      hands={"finA": 5, "finB": 1})
    del game["_ledger"]   # no ledger has ever been created for this game
    pick = bots._jury_vote(game, "juror", ["finA", "finB"])
    assert pick == "finA", pick   # the bigger hand — the pre-D3 behaviour
    print("✅ a ledger-less game falls back without raising!\n")


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
        test_vote_target_favours_the_biggest_hand_including_a_human()
        test_vote_target_breaks_the_bloc_on_near_equal_scores()
        test_vote_target_never_targets_self_necklace_or_eliminated()
        test_vote_target_is_deterministic()
        test_jury_vote_punishes_the_finalist_who_blindsided_the_juror()
        test_jury_vote_rewards_a_loyal_finalist()
        test_jury_vote_robbery_direction_and_style_asymmetry()
        test_kip_guess_is_never_an_illegal_demand()
        test_bot_gives_a_drawn_goodwill_at_council()
        test_jury_can_split()
        test_jury_vote_empty_ledger_falls_back_to_hand_size()
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
