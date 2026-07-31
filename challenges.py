"""
Survivor: Let's Go To Rocks — Challenge engine (combined mode)

Implements the 5 Orange Challenge Cards from the 2025 expansion as digital state
machines, following the official Challenge Survival Guide.

Combined-mode framework (from the Survival Guide, "PLAYING WITH SURVIVOR: THE
TRIBE HAS SPOKEN"):

  · Add the 5 Orange Challenge Cards to the Action Card deck. They are drawn and
    held like any other Action Card and played on your turn.
  · "Anytime you see the line 'The player who drew this Challenge Card...' replace
    it with 'The player who played this Challenge Card...'"
  · "If both of your Survivor Character Cards have been voted out you can't take
    part in Challenges."
  · Winning a Challenge → put on the Immunity Idol Necklace. While wearing it,
    players can't vote for you at the next Tribal Council. When that Tribal
    Council ends, the Necklace returns to the middle of the table.
  · If someone is already wearing the Necklace when you win, you instead take
    3 random cards from anywhere in the Draw Pile (never Tribal Council cards).

State lives at ``game["challenge"]``. Keys prefixed with ``_`` hold hidden
information (secret rock pulls) and are stripped before the state is sent to
clients.
"""

import logging
import random
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Safety valve: Pull Or Steal allows steal-chains that could in principle cycle.
MAX_CHALLENGE_ACTIONS = 300

CHALLENGE_DEFINITIONS = {
    "challenge_highest_bidder": {
        "key": "highest_bidder",
        "name": "Highest Bidder",
        "goal": "Be the highest bidder, but don't pull the Purple Rock out of the bag.",
        "digital": True,
    },
    "challenge_1_now_or_2_later": {
        "key": "one_now_or_two_later",
        "name": "1 Now or 2 Later",
        "goal": "Don't pull the Purple Rock out of the bag.",
        "digital": True,
    },
    "challenge_lowest_score_loses": {
        "key": "lowest_score_loses",
        "name": "Lowest Score Loses",
        "goal": "Be the last player standing. Grey Rocks are +1, Purple Rocks are -2.",
        "digital": True,
    },
    "challenge_pull_or_steal": {
        "key": "pull_or_steal",
        "name": "Pull or Steal",
        "goal": "End the Challenge holding the Purple Rock.",
        "digital": True,
    },
    "challenge_hide_n_seek": {
        "key": "hide_n_seek",
        "name": "Hide 'n' Seek",
        "goal": "As the Observer, find the Purple Rocks — everyone else hides them.",
        "digital": False,
        "unavailable_reason": (
            "Hide 'n' Seek is a physical sleight-of-hand Challenge: players palm two "
            "Purple Rocks and bluff-pass them around the table while an Observer watches "
            "hands. There is no honest digital equivalent — the whole game is the physical "
            "tell. The card is discarded with no effect."
        ),
    },
}

# Pull Or Steal setup table from the Challenge Survival Guide:
#   Players    3  4  5  6
#   Grey Rocks 2  3  4  5
# i.e. one rock per player: (players - 1) grey + 1 purple.
def _pull_or_steal_grey(player_count: int) -> int:
    return max(1, player_count - 1)


class ChallengeEngine:
    """Drives the 4 digitally-playable Rocks Challenges."""

    # ───────────────────────────── helpers ─────────────────────────────

    @staticmethod
    def definition(card_type: str) -> Optional[Dict[str, Any]]:
        return CHALLENGE_DEFINITIONS.get(card_type)

    @staticmethod
    def participants(game: Dict[str, Any], starter_id: str) -> List[str]:
        """
        Seat order for a Challenge, starting with the player who played the card.

        Combined-mode rule: eliminated players can't take part in Challenges.
        """
        turn_order = [pid for pid in game.get("turnOrder", []) if pid in game.get("players", {})]
        if starter_id not in turn_order:
            turn_order = list(game.get("players", {}).keys())
        if starter_id in turn_order:
            start = turn_order.index(starter_id)
            turn_order = turn_order[start:] + turn_order[:start]
        return [
            pid for pid in turn_order
            if not game["players"][pid].get("isEliminated", False)
        ]

    @staticmethod
    def _active(ch: Dict[str, Any]) -> List[str]:
        return [pid for pid in ch["order"] if pid not in ch["knockedOut"]]

    @staticmethod
    def _next_active(ch: Dict[str, Any], from_pid: str, skip=()) -> Optional[str]:
        """Next player to the left of ``from_pid`` who is still in the Challenge."""
        order = ch["order"]
        if from_pid not in order:
            candidates = [p for p in ChallengeEngine._active(ch) if p not in skip]
            return candidates[0] if candidates else None
        start = order.index(from_pid)
        for step in range(1, len(order) + 1):
            pid = order[(start + step) % len(order)]
            if pid in ch["knockedOut"] or pid in skip:
                continue
            return pid
        return None

    @staticmethod
    def _bag_size(ch: Dict[str, Any]) -> int:
        return ch["bag"]["grey"] + ch["bag"]["purple"]

    @staticmethod
    def _draw_rock(ch: Dict[str, Any]) -> Optional[str]:
        """Pull one random rock out of the bag."""
        bag = ch["bag"]
        pool = ["grey"] * bag["grey"] + ["purple"] * bag["purple"]
        if not pool:
            return None
        rock = random.choice(pool)
        bag[rock] -= 1
        return rock

    @staticmethod
    def _log(ch: Dict[str, Any], message: str) -> None:
        ch.setdefault("log", []).append(message)
        # Keep the log bounded — the UI only ever shows the tail.
        if len(ch["log"]) > 60:
            ch["log"] = ch["log"][-60:]

    @staticmethod
    def _name(game: Dict[str, Any], pid: str) -> str:
        return game.get("players", {}).get(pid, {}).get("name", pid)

    # ───────────────────────────── start ─────────────────────────────

    def start(self, game: Dict[str, Any], starter_id: str, card_type: str) -> Dict[str, Any]:
        """Start a Challenge. Returns {'success', 'message', ...}."""
        definition = self.definition(card_type)
        if not definition:
            return {"success": False, "message": f"Unknown Challenge Card: {card_type}"}

        if not definition["digital"]:
            return {
                "success": True,
                "unavailable": True,
                "message": f"{definition['name']} — {definition['unavailable_reason']}",
            }

        order = self.participants(game, starter_id)
        if len(order) < 2:
            return {"success": False, "message": "A Challenge needs at least 2 players still in the game"}

        ch: Dict[str, Any] = {
            "cardType": card_type,
            "type": definition["key"],
            "name": definition["name"],
            "goal": definition["goal"],
            "starterId": starter_id,
            "order": order,
            "knockedOut": [],
            "round": 1,
            "actionCount": 0,
            "winnerId": None,
            "log": [],
            "bag": {"grey": 0, "purple": 0},
        }

        starter = self._name(game, starter_id)
        self._log(ch, f"{starter} played {definition['name']}!")

        builder = getattr(self, f"_start_{definition['key']}")
        builder(game, ch)
        game["challenge"] = ch
        return {"success": True, "message": f"{definition['name']} has begun — {ch.get('prompt', '')}".strip()}

    # ───────────────────────────── action dispatch ─────────────────────────────

    def action(self, game: Dict[str, Any], player_id: str, action: str,
               value: Any = None) -> Dict[str, Any]:
        """Apply a player action to the active Challenge."""
        ch = game.get("challenge")
        if not ch:
            return {"success": False, "message": "No Challenge is in progress"}
        if ch.get("phase") == "complete":
            return {"success": False, "message": "This Challenge is already finished"}

        if player_id not in ch["order"]:
            return {"success": False, "message": "You are not taking part in this Challenge"}
        if player_id in ch["knockedOut"]:
            return {"success": False, "message": "You are knocked out of this Challenge"}
        if ch.get("currentPlayerId") and player_id != ch["currentPlayerId"]:
            return {
                "success": False,
                "message": f"It's {self._name(game, ch['currentPlayerId'])}'s turn in this Challenge",
            }
        if action not in ch.get("actions", []):
            allowed = ", ".join(ch.get("actions", [])) or "none"
            return {"success": False, "message": f"'{action}' is not allowed right now (allowed: {allowed})"}

        if ch.get("actionCount", 0) >= MAX_CHALLENGE_ACTIONS:
            return {"success": False, "message": "Challenge action limit reached — reset the Challenge"}

        handler = getattr(self, f"_action_{ch['type']}")
        result = handler(game, ch, player_id, action, value)

        # Only a move that actually advanced the Challenge counts against the cap.
        # Counting refusals too meant a client retrying one illegal move burned the
        # whole budget and poisoned the Challenge permanently, turning a transient
        # bug into an unrecoverable game (seen live: a bot asked to pull from an
        # empty bag ~6600 times, and the Challenge stayed dead after the bot was
        # fixed). The cap still stops a genuine runaway of successful actions.
        if result.get("success"):
            ch["actionCount"] = ch.get("actionCount", 0) + 1
        return result

    def _finish(self, game: Dict[str, Any], ch: Dict[str, Any], winner_id: str,
                message: str) -> Dict[str, Any]:
        ch["phase"] = "complete"
        ch["winnerId"] = winner_id
        ch["currentPlayerId"] = None
        ch["actions"] = []
        ch["prompt"] = f"{self._name(game, winner_id)} won the Challenge!"
        self._log(ch, ch["prompt"])
        return {"success": True, "message": message, "challengeWon": winner_id}

    # ═════════════════════════ HIGHEST BIDDER ═════════════════════════
    # Setup: 10 Grey Rocks and 1 Purple Rock in the bag.

    def _start_highest_bidder(self, game: Dict[str, Any], ch: Dict[str, Any]) -> None:
        ch["bag"] = {"grey": 10, "purple": 1}
        self._begin_bidding(game, ch, ch["starterId"])

    def _begin_bidding(self, game: Dict[str, Any], ch: Dict[str, Any], first_bidder: str) -> None:
        ch["phase"] = "bidding"
        ch["currentBid"] = 0
        ch["highBidderId"] = None
        ch["passed"] = []
        ch["pulled"] = {"grey": 0, "purple": 0}
        ch["pullsRemaining"] = 0
        ch["roundFirstBidderId"] = first_bidder
        ch["currentPlayerId"] = first_bidder
        ch["actions"] = ["bid"]  # "The first player each round MUST make a bid."
        ch["maxBid"] = self._bag_size(ch)
        ch["prompt"] = (
            f"{self._name(game, first_bidder)} must open the bidding "
            f"(1–{ch['maxBid']} rocks)."
        )

    def _bidding_eligible(self, ch: Dict[str, Any]) -> List[str]:
        return [p for p in self._active(ch) if p not in ch["passed"]]

    def _action_highest_bidder(self, game: Dict[str, Any], ch: Dict[str, Any],
                              player_id: str, action: str, value: Any) -> Dict[str, Any]:
        if ch["phase"] == "bidding":
            if action == "bid":
                try:
                    bid = int(value)
                except (TypeError, ValueError):
                    return {"success": False, "message": "A bid must be a whole number of rocks"}
                if bid <= ch["currentBid"]:
                    return {"success": False, "message": f"Your bid must be higher than {ch['currentBid']}"}
                if bid > self._bag_size(ch):
                    return {"success": False, "message": f"There are only {self._bag_size(ch)} rocks in the bag"}

                ch["currentBid"] = bid
                ch["highBidderId"] = player_id
                self._log(ch, f"{self._name(game, player_id)} bids {bid}.")

            else:  # pass
                if ch["currentBid"] == 0:
                    return {"success": False, "message": "The first bidder each round must make a bid"}
                ch["passed"].append(player_id)
                self._log(ch, f"{self._name(game, player_id)} passes.")

            # Move to the next player who can still bid
            remaining = self._bidding_eligible(ch)
            if len(remaining) <= 1:
                bidder = ch["highBidderId"] or (remaining[0] if remaining else None)
                if not bidder:
                    self._begin_bidding(game, ch, ch["roundFirstBidderId"])
                    return {"success": True, "message": "Nobody bid — bidding restarts"}
                ch["phase"] = "pulling"
                ch["currentPlayerId"] = bidder
                ch["pullsRemaining"] = ch["currentBid"]
                ch["actions"] = ["pull"]
                ch["prompt"] = (
                    f"{self._name(game, bidder)} won the bidding at {ch['currentBid']} — "
                    f"pull {ch['pullsRemaining']} rock(s), one at a time."
                )
                self._log(ch, ch["prompt"])
                return {"success": True, "message": ch["prompt"]}

            nxt = self._next_active(ch, player_id, skip=tuple(ch["passed"]))
            ch["currentPlayerId"] = nxt
            ch["actions"] = ["bid", "pass"]
            ch["prompt"] = (
                f"{self._name(game, nxt)}: bid more than {ch['currentBid']} or pass."
            )
            return {"success": True, "message": ch["prompt"]}

        # ── pulling ──
        rock = self._draw_rock(ch)
        if rock is None:
            return {"success": False, "message": "The bag is empty"}
        ch["pulled"][rock] += 1
        ch["pullsRemaining"] -= 1

        if rock == "purple":
            self._log(ch, f"{self._name(game, player_id)} pulled the PURPLE ROCK and is knocked out!")
            ch["knockedOut"].append(player_id)
            active = self._active(ch)
            if len(active) == 1:
                return self._finish(game, ch, active[0],
                                    f"{self._name(game, active[0])} is the last player standing and wins the Challenge!")
            # All rocks back in the bag; next player to the left opens the bidding.
            ch["bag"] = {"grey": 10, "purple": 1}
            ch["round"] += 1
            nxt = self._next_active(ch, player_id)
            self._begin_bidding(game, ch, nxt)
            return {"success": True, "message": f"{self._name(game, player_id)} pulled the Purple Rock — knocked out!"}

        self._log(ch, f"{self._name(game, player_id)} pulled a grey rock ({ch['pullsRemaining']} to go).")
        if ch["pullsRemaining"] <= 0:
            return self._finish(game, ch, player_id,
                                f"{self._name(game, player_id)} pulled {ch['currentBid']} rocks without the Purple Rock and wins the Challenge!")

        ch["prompt"] = f"{self._name(game, player_id)}: {ch['pullsRemaining']} rock(s) left to pull."
        return {"success": True, "message": ch["prompt"]}

    # ═════════════════════════ 1 NOW OR 2 LATER ═════════════════════════
    # Setup: 5 Grey Rocks and 1 Purple Rock in the bag.

    def _start_one_now_or_two_later(self, game: Dict[str, Any], ch: Dict[str, Any]) -> None:
        ch["mustPullTwo"] = []
        ch["table"] = {"grey": 0, "purple": 0}
        self._begin_one_now_round(game, ch, ch["starterId"])

    def _begin_one_now_round(self, game: Dict[str, Any], ch: Dict[str, Any], first: str) -> None:
        ch["phase"] = "choosing"
        ch["bag"] = {"grey": 5, "purple": 1}
        ch["table"] = {"grey": 0, "purple": 0}
        # "This begins the next round and all players can choose to pull or pass
        #  (even if they passed on their last turn)."
        ch["mustPullTwo"] = []
        ch["currentPlayerId"] = first
        ch["actions"] = ["pull", "pass"]
        ch["prompt"] = f"{self._name(game, first)}: pull 1 rock, or pass (then you must pull 2 next time)."

    def _action_one_now_or_two_later(self, game: Dict[str, Any], ch: Dict[str, Any],
                                    player_id: str, action: str, value: Any) -> Dict[str, Any]:
        name = self._name(game, player_id)

        if action == "pass":
            if player_id in ch["mustPullTwo"]:
                return {"success": False, "message": "You passed last time — you must pull 2 rocks and can't pass"}
            ch["mustPullTwo"].append(player_id)
            self._log(ch, f"{name} passes — next time they must pull 2 rocks.")
        else:
            count = 2 if player_id in ch["mustPullTwo"] else 1
            if player_id in ch["mustPullTwo"]:
                ch["mustPullTwo"].remove(player_id)

            pulled = []
            for _ in range(count):
                rock = self._draw_rock(ch)
                if rock is None:
                    break
                pulled.append(rock)
                ch["table"][rock] += 1

            if not pulled:
                # Defensive: the bag can't normally empty before the Purple Rock
                # is pulled, but never wedge the Challenge if it does.
                ch["round"] += 1
                self._begin_one_now_round(game, ch, player_id)
                return {"success": True, "message": "The bag was empty — the round restarts"}

            self._log(ch, f"{name} pulled {len(pulled)} rock(s): {', '.join(pulled)}.")

            if "purple" in pulled:
                ch["knockedOut"].append(player_id)
                self._log(ch, f"{name} pulled the PURPLE ROCK and is knocked out! The round is over.")
                active = self._active(ch)
                if len(active) == 1:
                    return self._finish(game, ch, active[0],
                                        f"{self._name(game, active[0])} is the last player standing and wins the Challenge!")
                ch["round"] += 1
                nxt = self._next_active(ch, player_id)
                self._begin_one_now_round(game, ch, nxt)
                return {"success": True, "message": f"{name} pulled the Purple Rock — knocked out!"}

        nxt = self._next_active(ch, player_id)
        ch["currentPlayerId"] = nxt
        ch["actions"] = ["pull"] if nxt in ch["mustPullTwo"] else ["pull", "pass"]
        must = " (must pull 2)" if nxt in ch["mustPullTwo"] else ""
        ch["prompt"] = f"{self._name(game, nxt)}: pull or pass{must}."
        return {"success": True, "message": ch["prompt"]}

    # ═════════════════════════ LOWEST SCORE LOSES ═════════════════════════
    # Setup: 5 Grey Rocks and 3 Purple Rocks in the bag. Grey +1, Purple -2.

    def _start_lowest_score_loses(self, game: Dict[str, Any], ch: Dict[str, Any]) -> None:
        self._begin_lowest_score_round(game, ch, ch["starterId"])

    def _begin_lowest_score_round(self, game: Dict[str, Any], ch: Dict[str, Any], first: str) -> None:
        ch["phase"] = "pulling"
        ch["bag"] = {"grey": 5, "purple": 3}
        active = self._active(ch)
        # The bag passes to the left, starting with `first`.
        if first in active:
            start = active.index(first)
            ch["pending"] = active[start:] + active[:start]
        else:
            ch["pending"] = active
        ch["_secretPulls"] = {}
        ch["pulls"] = {}
        ch["scores"] = {}
        ch["roundFirstId"] = ch["pending"][0]
        ch["currentPlayerId"] = ch["pending"][0]
        ch["actions"] = ["pull"]
        ch["maxPull"] = self._bag_size(ch)
        ch["prompt"] = (
            f"{self._name(game, ch['pending'][0])}: secretly pull 0–{ch['maxPull']} rocks "
            "from the bag (grey +1, purple -2)."
        )

    def _action_lowest_score_loses(self, game: Dict[str, Any], ch: Dict[str, Any],
                                  player_id: str, action: str, value: Any) -> Dict[str, Any]:
        try:
            count = int(value if value is not None else 0)
        except (TypeError, ValueError):
            return {"success": False, "message": "Choose how many rocks to pull (a whole number)"}
        if count < 0:
            return {"success": False, "message": "You can't pull a negative number of rocks"}
        available = self._bag_size(ch)
        if available == 0:
            # "When you get the bag it might be empty - that's fine, just pretend
            # to take some Rocks and pass the bag to the next player." An empty
            # bag is a real position, not a client error: take the turn as a pull
            # of nothing rather than refusing and stalling whoever is holding it.
            count = 0
        elif count > available:
            return {"success": False, "message": f"There are only {available} rocks left in the bag"}

        grabbed = {"grey": 0, "purple": 0}
        for _ in range(count):
            rock = self._draw_rock(ch)
            if rock is None:
                break
            grabbed[rock] += 1
        ch["_secretPulls"][player_id] = grabbed
        self._log(ch, f"{self._name(game, player_id)} secretly took {count} rock(s).")

        ch["pending"] = [p for p in ch["pending"] if p != player_id]
        if ch["pending"]:
            nxt = ch["pending"][0]
            ch["currentPlayerId"] = nxt
            ch["maxPull"] = self._bag_size(ch)
            ch["prompt"] = (
                f"{self._name(game, nxt)}: secretly pull 0–{ch['maxPull']} rocks from the bag."
            )
            return {"success": True, "message": f"{self._name(game, player_id)} has taken their rocks."}

        # ── Everyone has pulled: reveal and score ──
        pulls = ch.pop("_secretPulls", {})
        ch["pulls"] = pulls
        scores = {pid: g["grey"] - 2 * g["purple"] for pid, g in pulls.items()}
        ch["scores"] = scores
        active = self._active(ch)
        lowest = min(scores.values())
        losers = [pid for pid in active if scores.get(pid, 0) == lowest]

        summary = ", ".join(
            f"{self._name(game, pid)} {scores[pid]:+d}" for pid in active if pid in scores
        )
        self._log(ch, f"Reveal — {summary}.")

        redo = len(losers) >= len(active)
        ch["lastRound"] = {
            "round": ch["round"],
            "pulls": pulls,
            "scores": scores,
            "knockedOut": [] if redo else losers,
            "redo": redo,
        }

        if redo:
            self._log(ch, "Everyone tied for the lowest score — redo this round!")
            ch["round"] += 1
            self._begin_lowest_score_round(game, ch, ch.get("roundFirstId") or active[0])
            return {"success": True, "message": "All remaining players tied for lowest — redoing the round"}

        for pid in losers:
            ch["knockedOut"].append(pid)
        self._log(ch, "Knocked out: " + ", ".join(self._name(game, p) for p in losers))

        remaining = self._active(ch)
        if len(remaining) == 1:
            return self._finish(game, ch, remaining[0],
                                f"{self._name(game, remaining[0])} is the last player standing and wins the Challenge!")

        # "The player with the bag in front of them goes first in the next round."
        # After a full round that is the player who took the last turn.
        ch["round"] += 1
        next_first = player_id if player_id in remaining else self._next_active(ch, player_id)
        self._begin_lowest_score_round(game, ch, next_first)
        return {"success": True, "message": "Lowest score knocked out — next round begins"}

    # ═════════════════════════ PULL OR STEAL ═════════════════════════
    # Setup: 1 Purple Rock + (players - 1) Grey Rocks.

    def _start_pull_or_steal(self, game: Dict[str, Any], ch: Dict[str, Any]) -> None:
        ch["bag"] = {"grey": _pull_or_steal_grey(len(ch["order"])), "purple": 1}
        ch["numbers"] = {pid: i + 1 for i, pid in enumerate(ch["order"])}
        ch["_rocks"] = {}
        ch["rocks"] = {}
        ch["holders"] = []
        ch["phase"] = "choosing"
        ch["currentPlayerId"] = ch["order"][0]
        ch["actions"] = ["pull"]  # "Player 1 MUST pull a Rock."
        ch["prompt"] = f"{self._name(game, ch['order'][0])} is Player 1 and must pull a rock."

    def _pull_or_steal_set_turn(self, game: Dict[str, Any], ch: Dict[str, Any], pid: str) -> None:
        ch["currentPlayerId"] = pid
        my_number = ch["numbers"][pid]
        can_steal = [
            other for other, num in ch["numbers"].items()
            if num < my_number and other in ch["_rocks"] and other not in ch["knockedOut"]
        ]
        ch["actions"] = ["pull"] + (["steal"] if can_steal else [])
        ch["stealTargets"] = can_steal
        if can_steal:
            names = ", ".join(self._name(game, p) for p in can_steal)
            ch["prompt"] = f"{self._name(game, pid)}: pull a rock from the bag, or steal from {names}."
        else:
            ch["prompt"] = f"{self._name(game, pid)}: pull a rock from the bag."

    def _action_pull_or_steal(self, game: Dict[str, Any], ch: Dict[str, Any],
                             player_id: str, action: str, value: Any) -> Dict[str, Any]:
        if player_id in ch["_rocks"]:
            return {"success": False, "message": "You already have a rock"}

        if action == "steal":
            target = value.get("targetId") if isinstance(value, dict) else value
            if not target or not isinstance(target, str):
                return {"success": False, "message": "Choose a player to steal from"}
            if target not in ch.get("stealTargets", []):
                return {"success": False, "message": "You can only steal from a player with a lower number who has a rock"}
            ch["_rocks"][player_id] = ch["_rocks"].pop(target)
            self._log(ch, f"{self._name(game, player_id)} stole {self._name(game, target)}'s rock!")
            # "Then pass the bag to the player you stole from so they can take the next turn."
            self._pull_or_steal_set_turn(game, ch, target)
            return {"success": True, "message": ch["prompt"]}

        rock = self._draw_rock(ch)
        if rock is None:
            return {"success": False, "message": "The bag is empty"}
        ch["_rocks"][player_id] = rock
        self._log(ch, f"{self._name(game, player_id)} pulled a rock from the bag.")

        without = [p for p in self._active(ch) if p not in ch["_rocks"]]
        if not without:
            rocks = ch.pop("_rocks", {})
            ch["rocks"] = rocks
            ch["phase"] = "revealing"
            reveal = ", ".join(f"{self._name(game, p)}: {r}" for p, r in rocks.items())
            self._log(ch, f"Reveal — {reveal}.")
            winner = next((p for p, r in rocks.items() if r == "purple"), None)
            if winner:
                return self._finish(game, ch, winner,
                                    f"{self._name(game, winner)} revealed the Purple Rock and wins the Challenge!")
            # Should be unreachable (the Purple Rock is always in the bag).
            ch["phase"] = "complete"
            ch["actions"] = []
            ch["currentPlayerId"] = None
            return {"success": True, "message": "No one held the Purple Rock — the Challenge ends with no winner"}

        nxt = self._next_active(ch, player_id, skip=tuple(ch["_rocks"].keys()))
        if nxt is None:
            nxt = without[0]
        self._pull_or_steal_set_turn(game, ch, nxt)
        return {"success": True, "message": ch["prompt"]}


# Module-level singleton — the engine holds no per-game state.
challenge_engine = ChallengeEngine()
