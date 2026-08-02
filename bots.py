"""
Computer players for Survivor: The Digital Board Game.

A bot is an ordinary player with ``isBot: True`` — same hand, same lives, same
rules. Bots act by calling the exact same GameState methods the HTTP layer
calls for humans, so a bot can never do anything a human couldn't.

Two pieces:

  * ``next_action(game, ...)`` — a pure function that inspects the game state
    and returns the single next bot action (or None). All strategy lives here,
    which makes it unit-testable without a server, a socket, or a clock.

  * ``BotRunner`` — the scheduler. ``poke(gid)`` after any state change queues
    a step after a humanlike delay; a heartbeat catches anything missed. Tests
    call ``step(gid)`` directly with delays at zero.

House rule enforced elsewhere but designed for here: games containing a bot
never write to the Hall of Fame.
"""

import logging
import os
import random
import time

logger = logging.getLogger(__name__)

# Names the island gives its constructs. The UI marks bots with a badge, so
# these just need to be friendly and distinct from likely human names.
BOT_NAMES = ["Coconut", "Driftwood", "Barnacle", "Mango", "Puddles", "Flint"]


# How much a bot wants each card — used when giving one up (give the lowest)
# and when The Spy Shack lets it take one (take the highest).
CARD_VALUE = {
    "immunity_idol": 10, "sorry_for_you": 8, "extra_vote": 7,
    "steal_vote": 6, "block_vote": 6, "grant_immunity": 6, "idol_nullifier": 6,
    "control_the_vote": 5, "im_the_leader_now": 5, "goodwill_gamble": 5,
    "camp_raid": 5, "the_spy_shack": 5, "knowledge_is_power": 5,
    "lets_form_an_alliance": 4,
    # Colour-bound and never played by hand — valued low so a bot gives one
    # up before anything it can actually use. Which is also the Guide's own
    # advice about an Inheritance for a colour that isn't in the game.
    "inheritance_red": 3, "inheritance_teal": 3, "inheritance_blue": 3,
    "inheritance_orange": 3, "inheritance_green": 3, "inheritance_yellow": 3,
    "reward_challenge_do_or_die": 4, "reward_challenge_power_pair": 4,
    "reward_challenge_its_a_numbers_game": 4,
    "vote": 2,
}

# Cards a bot will consider playing on its turn, in priority order.
_PLAYABLE_PRIORITY = [
    "camp_raid", "the_spy_shack", "knowledge_is_power",
    "lets_form_an_alliance",
    "reward_challenge_do_or_die", "reward_challenge_power_pair",
    "reward_challenge_its_a_numbers_game",
    "challenge_lowest_score_loses", "challenge_pull_or_steal",
    "challenge_1_now_or_2_later", "challenge_highest_bidder",
    # never: challenge_hide_n_seek (not available digitally),
    # tribal advantages + votes (held for tribal), sorry_for_you (reactive)
]

PLAY_CHANCE = 0.75  # a bot holds its cards some turns, like a person would


# ────────────────────────────────── helpers ──────────────────────────────────

def is_bot(game, pid):
    return bool(game.get("players", {}).get(pid, {}).get("isBot"))


def has_human(game):
    """Bots only play while at least one human is in the game (eliminated
    humans still count — they're watching the story end)."""
    return any(not p.get("isBot") for p in game.get("players", {}).values())


def game_has_bot(game):
    return any(p.get("isBot") for p in game.get("players", {}).values())


def _alive(game):
    return [pid for pid in game.get("turnOrder", [])
            if not game["players"][pid].get("isEliminated")]


def _hand(game, pid):
    return game["players"][pid].get("hand") or []


def _hand_count(game, pid):
    return len(_hand(game, pid))


def _card_value(card):
    return CARD_VALUE.get(card.get("type"), 3)


def _biggest_threat(game, bot_id, exclude=()):
    """The player a bot worries about: most cards in hand. Deterministic
    tiebreak so tests are stable."""
    candidates = [p for p in _alive(game)
                  if p != bot_id and p not in exclude
                  and p != game.get("necklaceHolder")]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: (-_hand_count(game, p), p))[0]


def _steal_target(game, bot_id):
    """Steal from whoever holds the most cards; anyone alive if all empty."""
    others = [p for p in _alive(game) if p != bot_id]
    if not others:
        return None
    return sorted(others, key=lambda p: (-_hand_count(game, p), p))[0]


def _find_card(game, pid, card_type):
    for i, card in enumerate(_hand(game, pid)):
        if card.get("type") == card_type:
            return i
    return None


def _vote_blocked(game, pid):
    """True if Block A Vote / Steal A Vote shut this player out of the box."""
    return bool(game.get("players", {}).get(pid, {}).get("voteBanned"))


def _act(method, delay_class="normal", **kwargs):
    """An action plan: which GameState method to call and with what."""
    return {"method": method, "kwargs": kwargs, "delay_class": delay_class}


# ─────────────────────────── decision: card plays ────────────────────────────

def _choose_card_play(game, bot_id, rng):
    """Pick at most one card to play this turn. Returns (cardIdx, params) or None."""
    alive_others = [p for p in _alive(game) if p != bot_id]
    if not alive_others:
        return None

    hand = _hand(game, bot_id)
    by_type = {}
    for idx, card in enumerate(hand):
        by_type.setdefault(card.get("type"), idx)

    for card_type in _PLAYABLE_PRIORITY:
        idx = by_type.get(card_type)
        if idx is None:
            continue

        if card_type == "camp_raid":
            # It's a trap now: pick the card leader who isn't already marked
            candidates = [p for p in _alive(game) if p != bot_id
                          and not game["players"][p].get("campRaidedBy")]
            if candidates:
                target = sorted(candidates,
                                key=lambda p: (-_hand_count(game, p), p))[0]
                return idx, {"targetId": target}

        elif card_type == "the_spy_shack":
            target = _biggest_threat(game, bot_id)
            if target and _hand_count(game, target) >= 1:
                victim_hand = _hand(game, target)
                take = max(range(len(victim_hand)),
                           key=lambda i: _card_value(victim_hand[i]))
                return idx, {"targetId": target, "takeIndex": take}

        elif card_type == "knowledge_is_power":
            target = _biggest_threat(game, bot_id)
            if target and _hand_count(game, target) >= 1:
                # Statistical guess, no peeking: the commonest strong holdings
                guess = rng.choice(["sorry_for_you", "extra_vote", "vote"])
                return idx, {"targetId": target, "cardType": guess}

        elif card_type == "lets_form_an_alliance":
            if len(alive_others) >= 2:
                victim = _biggest_threat(game, bot_id)
                allies = [p for p in alive_others if p != victim]
                if victim and allies:
                    return idx, {"allyId": rng.choice(sorted(allies)),
                                 "victimId": victim}

        elif card_type == "reward_challenge_do_or_die":
            target = _biggest_threat(game, bot_id)
            if target:
                return idx, {"targetId": target,
                             "choice": rng.choice(["rock", "paper", "scissors"])}

        elif card_type == "reward_challenge_power_pair":
            if len(alive_others) >= 2:
                picks = sorted(alive_others,
                               key=lambda p: (-_hand_count(game, p), p))[:2]
                return idx, {"targetIds": picks}

        elif card_type == "reward_challenge_its_a_numbers_game":
            return idx, {}

        elif card_type.startswith("challenge_"):
            if game.get("expansion") and not game.get("challenge") \
                    and len(_alive(game)) >= 2:
                return idx, {}

    return None


# ───────────────────────── decision: the main brain ──────────────────────────

def next_action(game, phase_age=None, turn_memory=None, rng=None):
    """
    The single next bot action for this game state, or None.

    Args:
        game: full server-side game dict
        phase_age: fn(key) -> seconds the game has been in that sub-phase
                   (None = treat every window as already elapsed)
        turn_memory: mutable dict the caller preserves between steps; used to
                    remember play/draw progress within a bot's turn
        rng: random.Random for seedable tests
    """
    rng = rng or random
    age = phase_age or (lambda key: 1e9)
    mem = turn_memory if turn_memory is not None else {}

    if not has_human(game) or not game_has_bot(game):
        return None

    phase = game.get("phase")
    if phase in ("lobby", "finished"):
        return None

    # ── Reactive theft window (Sorry For You) — outranks everything: the gate
    #    freezes the game until the victim answers ──
    theft = game.get("pending_theft")
    if theft and theft.get("reactive_window_open"):
        target = theft.get("targetId")
        if target and is_bot(game, target):
            idx = _find_card(game, target, "sorry_for_you")
            if idx is not None:
                return _act("handle_reactive_card_play", playerId=target,
                            cardIdx=idx)
            return _act("complete_pending_theft")
        return None  # a human decides

    # ── Sorry For You penalty: raiders choose what they give up ──
    # Placed above everything else it could collide with, for the same reason
    # the theft gate is: the table is frozen until it is paid, so nothing else
    # can legally happen anyway.
    pd = game.get("pending_discards")
    if pd and pd.get("awaiting"):
        for pid in pd["awaiting"]:
            if not is_bot(game, pid):
                continue
            hand = _hand(game, pid)
            givable = [i for i, c in enumerate(hand) if c.get("type") != "vote"]
            if givable:
                # Give up the cheapest thing — the same rule the bot already
                # applies when a Reward Challenge forces it to hand a card over.
                return _act("choose_penalty_discard", playerId=pid,
                            cardIdx=min(givable, key=lambda i: _card_value(hand[i])))
        return None  # a human owes the penalty

    # ── Reward Challenge interaction (blocks everything else) ──
    it = game.get("interaction")
    if it:
        if it.get("phase") == "picking":
            for pid in it.get("awaiting", []):
                if is_bot(game, pid):
                    kind = it.get("type")
                    if kind == "do_or_die":
                        value = rng.choice(["rock", "paper", "scissors"])
                    elif kind == "power_pair":
                        value = rng.randint(1, 3)
                    else:
                        value = rng.randint(1, 5)
                    return _act("interaction_action", playerId=pid,
                                action="pick", value=value)
        elif it.get("phase") == "give":
            for pid in it.get("awaiting", []):
                if is_bot(game, pid):
                    hand = _hand(game, pid)
                    # The Vote Card can't be handed over — offering it would be
                    # refused and the bot would re-offer it forever.
                    givable = [i for i, c in enumerate(hand)
                               if c.get("type") != "vote"]
                    if givable:
                        give = min(givable, key=lambda i: _card_value(hand[i]))
                        return _act("interaction_action", playerId=pid,
                                    action="give", value=give)
        elif it.get("phase") == "choose_victim":
            winner = it.get("winnerId")
            if winner and is_bot(game, winner):
                victim = _biggest_threat(game, winner)
                if victim:
                    return _act("interaction_action", playerId=winner,
                                action="steal_from", value=victim)
        elif it.get("phase") == "complete":
            initiator = it.get("initiatorId")
            if initiator and is_bot(game, initiator):
                return _act("interaction_action", playerId=initiator,
                            action="dismiss", value=None)
        return None  # a human's move — wait

    # ── Rocks Challenge ──
    ch = game.get("challenge")
    if ch:
        if ch.get("phase") == "complete":
            winner = ch.get("winnerId")
            if winner and is_bot(game, winner):
                return _act("challenge_action", playerId=winner,
                            action="dismiss", value=None)
            if not winner:
                # No winner recorded (edge case) — the card player clears it
                cp = ch.get("playedBy") or ch.get("initiatorId")
                if cp and is_bot(game, cp):
                    return _act("challenge_action", playerId=cp,
                                action="dismiss", value=None)
            return None
        cp = ch.get("currentPlayerId")
        if not cp or not is_bot(game, cp):
            return None
        actions = ch.get("actions") or []
        if not actions:
            return None
        action, value = actions[0], None
        if action == "bid":
            nxt = ch.get("currentBid", 0) + 1
            if nxt > ch.get("maxBid", nxt) and "pass" in actions:
                action = "pass"
            else:
                value = nxt
        elif action == "pull" and ch.get("type") == "lowest_score_loses":
            # Earlier players may have emptied the bag. The Guide: "When you get
            # the bag it might be empty - that's fine, just pretend to take some
            # Rocks and pass the bag to the next player." Asking for more than
            # the bag holds is refused, and a bot that keeps asking wedges the
            # whole game, so clamp to what is actually left.
            bag = ch.get("bag") or {}
            left = bag.get("grey", 0) + bag.get("purple", 0)
            ceiling = ch.get("maxPull")
            if isinstance(ceiling, int):
                left = min(left, ceiling)
            value = rng.randint(0, max(0, min(2, left)))
        elif action == "steal":
            targets = ch.get("stealTargets") or []
            if targets and rng.random() < steal_chance(game):
                value = targets[0]
            else:
                action = "pull" if "pull" in actions else action
        return _act("challenge_action", playerId=cp, action=action, value=value)

    # ── Tribal Council ──
    if phase == "tribal_council":
        return _tribal_action(game, age, rng)

    # ── Final Tribal ──
    if phase in ("final", "final_tribal"):
        return _final_action(game, age, rng)

    # ── A normal turn ──
    if phase == "playing":
        return _turn_action(game, mem, rng)

    return None


def _turn_action(game, mem, rng):
    order = game.get("turnOrder") or []
    if not order:
        return None
    current = order[game.get("currentTurnIndex", 0) % len(order)]
    if not is_bot(game, current):
        return None
    player = game["players"][current]

    # The server's own turn flags drive the whole sequence now: one steal,
    # at most one play (the server marks hasPlayed), one draw, end.
    if not player.get("hasStolen"):
        target = _steal_target(game, current)
        if target is None:
            return _act("advance_turn")
        return _act("steal_card", thiefId=current, targetId=target)

    if player.get("hasDrawn"):
        # Shouldn't happen — the draw ends the turn on its own now — but if a
        # deferred advance ever leaves this state, end the turn rather than loop.
        return _act("advance_turn")

    if not player.get("hasPlayed") and rng.random() < play_chance(game):
        play = _choose_card_play(game, current, rng)
        if play:
            idx, params = play
            return _act("play_card", playerId=current, cardIdx=idx,
                        params=params)

    return _act("draw_card", playerId=current)


def _tribal_action(game, age, rng):
    w = windows_for(game)
    cv = game.get("currentVote") or {}
    vph = cv.get("phase", "announcement")
    leader = cv.get("councilLeaderId")
    leader_is_bot = leader and is_bot(game, leader)
    alive = _alive(game)

    if vph == "announcement":
        if leader_is_bot and age(("tribal", "announcement")) >= w["announcement"]:
            return _act("advance_tribal_phase", phase="advantage_play",
                        playerId=leader)
        return None

    if vph == "advantage_play":
        if leader_is_bot and age(("tribal", "advantage_play")) >= w["advantage"]:
            return _act("advance_tribal_phase", phase="discussion",
                        playerId=leader)
        return None

    if vph == "discussion":
        if leader_is_bot and age(("tribal", "discussion")) >= w["discussion"]:
            return _act("advance_tribal_phase", phase="voting",
                        playerId=leader)
        return None

    if vph == "voting":
        votes = cv.get("votes") or {}
        # Block A Vote takes its target out of the Voting Box: the server refuses
        # their ballot, so a bot must neither try to cast one nor wait for it.
        expected = [pid for pid in alive if not _vote_blocked(game, pid)]
        for pid in expected:
            if pid in votes or not is_bot(game, pid):
                continue
            mandatory = max(0, game["players"][pid].get("mandatoryVotes", 1))
            if mandatory == 0:
                return _act("cast_vote", voterId=pid, votesData=[])
            target = _biggest_threat(game, pid)
            if target is None:
                return _act("cast_vote", voterId=pid, votesData=[])
            return _act("cast_vote", voterId=pid,
                        votesData=[{"targetId": target, "votes": mandatory}])
        # Everyone (humans included) must be in before a bot leader reveals
        if leader_is_bot and all(pid in votes for pid in expected):
            # The box is full, so the idol window opens — always. This used to
            # peek at human hands (_human_idol_holders) to decide whether the
            # window was worth opening, which was both a read of information a
            # Council Leader is not entitled to and a way for the window to
            # never appear. The window is now mandatory for everyone.
            return _act("advance_tribal_phase", phase="immunity",
                        playerId=leader)
        return None

    if vph == "immunity":
        # An idol is on the table awaiting its answer. This outranks everything
        # else in the phase, including the Leader's reveal: a bot that stays
        # quiet here holds the ceremony open for the whole table, and nothing
        # would ever time it out.
        window = game.get("pending_nullifier")
        if window and window.get("reactive_window_open"):
            answered = set(window.get("_answered") or [])
            protected = window.get("targetId")
            for pid in window.get("_responderIds") or []:
                if pid in answered or not is_bot(game, pid):
                    continue
                if game["players"].get(pid, {}).get("isEliminated"):
                    continue
                # Spend it on a real threat, hold it otherwise — a nullifier
                # burned on a harmless shield is a wasted card.
                if protected and protected != pid \
                        and protected == _biggest_threat(game, pid):
                    return _act("block_immunity", playerId=pid, targetId=protected)
                return _act("decline_nullifier", playerId=pid)
            # Every bot has spoken; a human still owes an answer.
            if any(pid not in answered and not is_bot(game, pid)
                   for pid in (window.get("_responderIds") or [])):
                return None

        # The idol window is open — threatened bots respond
        hand_leader = _biggest_threat(game, "")   # the table's card leader
        for pid in alive:
            if not is_bot(game, pid) or pid != hand_leader:
                continue
            # One idol per player per council — a bot holding a second one must
            # not keep offering it to a server that will refuse every time.
            if game["players"][pid].get("immunityPlayed"):
                continue
            if _find_card(game, pid, "immunity_idol") is not None:
                return _act("play_immunity", playerId=pid, targetId=pid)
        if leader_is_bot and age(("tribal", "immunity")) >= w["immunity"]:
            # reveal_votes tallies from the immunity phase; merely advancing the
            # phase to "reveal" would leave the box unopened and wedge tribal.
            return _act("reveal_votes")
        return None

    # reveal / results: tie-break, then close the ceremony
    if cv.get("tieBreakNeeded") and leader_is_bot:
        tied = cv.get("tiedPlayers") or []
        if tied:
            pick = sorted(tied, key=lambda p: (-_hand_count(game, p), p))[0]
            return _act("tie_break", leaderId=leader, chosenId=pick)
    if leader_is_bot and age(("tribal", vph)) >= w["reveal"]:
        return _act("complete_tribal")
    return None


def _final_action(game, age, rng):
    w = windows_for(game)
    ft = game.get("finalTribal") or {}
    fph = ft.get("phase", "questions")
    leader = ft.get("leader")
    leader_is_bot = leader and is_bot(game, leader)
    jury = ft.get("jury") or []
    finalists = ft.get("finalists") or []

    if fph == "questions":
        # Statements happen out loud at the table; a bot leader moves the
        # ceremony along once the window has passed.
        if leader_is_bot and age(("final", "questions")) >= w["final_questions"]:
            return _act("advance_final_phase", phase="voting")
        return None

    if fph == "deliberation":
        # Fingers go up here (rules): jury bots raise theirs, and a bot leader
        # proceeds once every finger is raised (or the window runs out).
        ready = ft.get("juryReady") or []
        for pid in jury:
            if pid not in ready and is_bot(game, pid):
                return _act("signal_jury_ready", juryMemberId=pid)
        all_ready = all(pid in ready for pid in jury)
        if leader_is_bot and (all_ready or age(("final", "deliberation")) >= w["final_questions"]):
            return _act("advance_final_phase", phase="voting")
        return None

    if fph == "voting":
        votes = ft.get("votes") or {}
        for pid in jury:
            if pid not in votes and is_bot(game, pid) and finalists:
                # The jury respects the biggest game: most cards wins the vote
                pick = sorted(finalists,
                              key=lambda p: (-_hand_count(game, p), p))[0]
                return _act("cast_final_vote", juryMemberId=pid, finalistId=pick)
        return None  # engine auto-advances to reveal when all votes are in

    if fph == "reveal":
        if ft.get("tieBreakNeeded") and leader_is_bot and finalists:
            return _act("break_final_tie", leaderId=leader,
                        chosenWinner=rng.choice(sorted(finalists)))
        return None

    return None


# ───────────────────────────── pacing windows ────────────────────────────────

def _base_delay():
    try:
        return max(0.0, float(os.environ.get("SURVIVOR_BOT_DELAY", "1.6")))
    except ValueError:
        return 1.6


def _windows(base):
    """Ceremony pacing scales with the action delay — zero delay, zero waits."""
    scale = base / 1.6 if base else 0.0
    return {
        "announcement": 5.0 * scale,
        "advantage": 8.0 * scale,
        "discussion": 8.0 * scale,
        "immunity": 8.0 * scale,
        "reveal": 4.0 * scale,
        "final_questions": 20.0 * scale,
    }


BASE_DELAY = _base_delay()

# How long past a timer's due moment we still trust it to fire. Beyond this,
# poke() assumes the scheduler lost it and re-arms.
TIMER_GRACE = 10.0
WINDOWS = _windows(BASE_DELAY)

# Refusal circuit breaker: transient refusals (a reactive window mid-close)
# clear within a tick or two, so a long unbroken run means the bot is stuck on
# something no retry will fix. Far past transient, well short of forever.
REFUSAL_BREAKER_STRIKES = 30
REFUSAL_BREAKER_COOLDOWN = 120.0  # seconds

# ── Per-game settings (game["settings"], set at creation / by the Leader) ──
PACE_DELAY = {"chill": 1.8, "normal": 1.0, "fast": 0.4}
TRIBAL_WINDOW = {"normal": 1.0, "relaxed": 2.0, "tv": 3.5}
STYLE_PLAY = {"chill": PLAY_CHANCE * 0.5, "normal": PLAY_CHANCE, "cutthroat": 0.95}
STYLE_STEAL = {"chill": 0.25, "normal": 0.5, "cutthroat": 0.8}
# With a live human at the table, the advantage/discussion windows keep a
# floor (seconds, scaled by the tribal multiplier) so a bot Council Leader
# can't race past the one moment a human may play I'm The Leader Now or an
# idol. Bot-only games stay quick.
HUMAN_WINDOW_FLOORS = {"advantage": 12.0, "discussion": 10.0}
IMMUNITY_WINDOW_FLOOR = 12.0  # seconds — only when a human holds an idol/nullifier


def _setting(game, key):
    return (game.get("settings") or {}).get(key, "normal")


def delay_mult(game):
    return PACE_DELAY.get(_setting(game, "botPace"), 1.0)


def window_mult(game):
    return TRIBAL_WINDOW.get(_setting(game, "tribalPace"), 1.0)


def play_chance(game):
    return STYLE_PLAY.get(_setting(game, "botStyle"), PLAY_CHANCE)


def steal_chance(game):
    return STYLE_STEAL.get(_setting(game, "botStyle"), 0.5)


def windows_for(game):
    """Ceremony windows for THIS game: base × tribalPace, with human floors."""
    if not BASE_DELAY:
        return dict(WINDOWS)   # test env: everything collapses to zero
    mult = window_mult(game)
    w = {k: v * mult for k, v in WINDOWS.items()}
    humans = [p for p in game.get("players", {}).values()
              if not p.get("isBot") and not p.get("isEliminated")]
    if humans:
        for k, floor in HUMAN_WINDOW_FLOORS.items():
            w[k] = max(w[k], floor * mult)
        # The idol window gets its full pause whenever a human is at the table,
        # never only when one is holding an idol. Timing the window off what is
        # in people's hands leaks the very thing the window exists to keep
        # secret: a table that learns "the long pause means somebody has an
        # idol" has been told, by the pacing, exactly what the Survival Guide
        # asks the Leader to find out by asking.
        w["immunity"] = max(w["immunity"], IMMUNITY_WINDOW_FLOOR * mult)
    return w


# ─────────────────────────────── the runner ──────────────────────────────────

class BotRunner:
    """
    Executes bot decisions against a GameState.

    Production: ``attach(spawn_later)`` wires a gevent-style scheduler and
    ``poke(gid)`` queues one step after a humanlike delay. Tests skip attach
    and call ``step(gid)`` in a loop — fully synchronous, no clock.
    """

    def __init__(self, game_state, broadcast=None, rng=None):
        self.gs = game_state
        self.broadcast = broadcast or (lambda gid, action: None)
        self.rng = rng or random
        self._spawn_later = None
        self._scheduled = {}   # gid -> when the pending timer should have fired
        self._phase_seen = {}   # (gid, key) -> first-seen timestamp
        self._turn_mem = {}     # gid -> per-bot turn progress
        self._refusals = {}     # gid -> consecutive refused actions
        self._cooldown = {}     # gid -> timestamp until which bots sit out

    def attach(self, spawn_later):
        """spawn_later(seconds, fn, *args) — e.g. a gevent spawn_later wrapper."""
        self._spawn_later = spawn_later

    # ── scheduling ──

    def poke(self, gid, delay=None):
        """Something changed in this game — have the bots look at it soon."""
        if self._spawn_later is None:
            return
        # A pending timer normally blocks double-scheduling — but timers can
        # be lost (a greenlet dying under I/O stalls never fires _tick). Once
        # one is overdue past its grace, treat it as lost and schedule anew;
        # otherwise the heartbeat can never revive the game. Observed: a bot's
        # rocks pull wedged a live table for five hours this way.
        now = time.time()
        due = self._scheduled.get(gid)
        if due is not None and now < due + TIMER_GRACE:
            return
        game = self.gs.games.get(gid)
        if not game or not game_has_bot(game) or not has_human(game):
            return
        if delay is None:
            base = BASE_DELAY * delay_mult(game)
            delay = base * (0.7 + 0.6 * self.rng.random()) if base else 0.01
        self._scheduled[gid] = now + delay
        self._spawn_later(delay, self._tick, gid)

    def heartbeat(self):
        """Catch-all: look at every bot game. Called on a timer by the server."""
        for gid, game in list(self.gs.games.items()):
            if game_has_bot(game) and has_human(game):
                self.poke(gid)

    def _tick(self, gid):
        self._scheduled.pop(gid, None)
        try:
            acted = self.step(gid)
        except Exception:
            logger.exception(f"Bot step failed for game {gid}")
            return
        if acted:
            self.poke(gid)

    # ── acting ──

    def _phase_age(self, gid):
        now = time.time()

        def age(key):
            full = (gid, key)
            if full not in self._phase_seen:
                # First sighting of this sub-phase — clear stale siblings
                stale = [k for k in self._phase_seen
                         if k[0] == gid and k[1][0] == key[0] and k != full]
                for k in stale:
                    self._phase_seen.pop(k, None)
                self._phase_seen[full] = now
            return now - self._phase_seen[full]
        return age

    def step(self, gid):
        """Execute at most one bot action. Returns True if something happened."""
        game = self.gs.games.get(gid)
        if not game:
            self._turn_mem.pop(gid, None)
            return False

        # Circuit breaker: a bot whose action is refused over and over is stuck
        # on something no retry will fix (a wedged Challenge burned a live game
        # at ~1 refusal per 2s for hours). Sit the game out for a while instead
        # of hammering; the next heartbeat after the cooldown tries again.
        if self._cooldown.get(gid, 0) > time.time():
            return False

        plan = next_action(
            game,
            phase_age=self._phase_age(gid),
            turn_memory=self._turn_mem.setdefault(gid, {}),
            rng=self.rng,
        )
        if not plan:
            return False

        method = plan["method"]
        kwargs = plan["kwargs"]
        try:
            if method == "handle_reactive_card_play":
                result = self.gs.handle_reactive_card_play(
                    gid, kwargs["playerId"], kwargs["cardIdx"], {})
            else:
                result = getattr(self.gs, method)(gid, **kwargs)
        except Exception:
            logger.exception(f"Bot action {method}({kwargs}) crashed in {gid}")
            return False

        ok = result.get("success", True) if isinstance(result, dict) else bool(result)
        if ok and isinstance(result, dict) and result.get("message"):
            log_list = game.setdefault("eventLog", [])
            # Prefer the redacted twin — the full message may name hidden cards
            log_msg = result.get("log_message") or result["message"]
            log_list.append({"t": time.time(), "msg": str(log_msg)[:200]})
            del log_list[:-120]
        if ok:
            self._refusals.pop(gid, None)
        else:
            message = result.get("message") if isinstance(result, dict) else result
            logger.warning(f"Bot action {method}({kwargs}) refused in {gid}: {message}")
            strikes = self._refusals.get(gid, 0) + 1
            self._refusals[gid] = strikes
            if strikes >= REFUSAL_BREAKER_STRIKES:
                self._refusals[gid] = 0
                self._cooldown[gid] = time.time() + REFUSAL_BREAKER_COOLDOWN
                logger.warning(
                    f"Bots in {gid} refused {strikes} times in a row — "
                    f"cooling down for {REFUSAL_BREAKER_COOLDOWN}s")
        try:
            self.broadcast(gid, method)
        except Exception:
            logger.exception(f"Bot broadcast failed for {gid}")
        # A refusal changed nothing — returning False stops the re-poke loop
        # and leaves retries to the heartbeat.
        return ok
