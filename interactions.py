"""
Reward Challenge interactions — real multiplayer input for the three cards whose
mini-games were previously simulated by server dice rolls.

Official Survival Guide texts these implement:

  REWARD CHALLENGE: DO OR DIE (3 cards)
    "This is a game of trust. Pick any player to play a single game of Rock Paper
    Scissors against. If you tie, you each swap 1 card of your choice. BUT if
    either player wins, they steal 2 random cards from the loser."

  REWARD CHALLENGE: POWER PAIR (3 cards)
    "Pick 2 other players. On the count of three, all 3 players (including you)
    hold out 1, 2, or 3 fingers. If EXACTLY 2 players show the same number of
    fingers, they each steal 1 random card from the 3rd. If ALL players show the
    same number, each player discards 1. If everyone shows a different number of
    fingers, play again."

  REWARD CHALLENGE: IT'S A NUMBERS GAME (3 cards)
    "On the count of three, all players (including you) will show 1-5 fingers.
    The player who shows the lowest UNIQUE number gets to steal 2 random cards
    from any player. If necessary, repeat until there's a single winner."

The whole point of these cards is bluffing between humans, so every pick comes
from a real player. State lives at ``game["interaction"]``; keys prefixed with
``_`` hold secret picks and are stripped before state leaves the server (same
convention as the Rocks challenge engine).
"""

import logging

from rules_engine import request_take, takeable_indices
import random
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# A table of humans converges fast; the cap only guards a pathological loop.
MAX_ROUNDS = 30

RPS_THROWS = ("rock", "paper", "scissors")
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

INTERACTION_NAMES = {
    "do_or_die": "Do Or Die",
    "power_pair": "Power Pair",
    "numbers_game": "It's A Numbers Game",
}


class InteractionEngine:
    """Drives the three simultaneous-input Reward Challenges."""

    # ───────────────────────────── helpers ─────────────────────────────

    @staticmethod
    def _name(game: Dict[str, Any], pid: str) -> str:
        return game.get("players", {}).get(pid, {}).get("name", pid)

    @staticmethod
    def _log(it: Dict[str, Any], message: str) -> None:
        it.setdefault("log", []).append(message)
        if len(it["log"]) > 40:
            it["log"] = it["log"][-40:]

    @staticmethod
    def _steal_random(game: Dict[str, Any], thief_id: str, victim_id: str, count: int) -> int:
        """Move up to ``count`` random cards from victim to thief. Returns moved."""
        thief = game["players"][thief_id]
        victim = game["players"][victim_id]
        moved = 0
        for _ in range(count):
            hand = victim.get("hand") or []
            reachable = takeable_indices(hand)
            if not reachable:
                break
            card = hand.pop(random.choice(reachable))
            thief.setdefault("hand", []).append(card)
            moved += 1
        return moved

    def _finish(self, game: Dict[str, Any], it: Dict[str, Any], summary: str) -> Dict[str, Any]:
        it["phase"] = "complete"
        it["awaiting"] = []
        it["prompt"] = summary
        self._log(it, summary)
        return {"success": True, "message": summary}

    # ───────────────────────────── start ─────────────────────────────

    def start(self, game: Dict[str, Any], initiator_id: str, kind: str,
              params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create the interaction. Assumes the play was already validated."""
        params = params or {}
        players = game.get("players", {})
        init_name = self._name(game, initiator_id)

        it: Dict[str, Any] = {
            "type": kind,
            "name": INTERACTION_NAMES.get(kind, kind),
            "initiatorId": initiator_id,
            "round": 1,
            "phase": "picking",
            "awaiting": [],
            "picks": {},          # revealed only when a round resolves
            "_picks": {},         # secret while picking
            "lastRound": None,
            "log": [],
        }

        if kind == "do_or_die":
            target_id = params.get("targetId")
            it["participants"] = [initiator_id, target_id]
            # The initiator threw secretly when they played the card
            it["_picks"] = {initiator_id: params.get("choice")}
            it["awaiting"] = [target_id]
            it["prompt"] = (
                f"{init_name} challenges {self._name(game, target_id)} to "
                "Rock · Paper · Scissors!"
            )
            self._log(it, f"{init_name} has made their throw.")

        elif kind == "power_pair":
            target_ids = list(params.get("targetIds") or [])
            it["participants"] = [initiator_id] + target_ids
            it["awaiting"] = list(it["participants"])
            it["prompt"] = (
                f"{init_name} calls a Power Pair with "
                f"{' and '.join(self._name(game, p) for p in target_ids)} — "
                "on the count of three, show 1, 2 or 3 fingers!"
            )

        elif kind == "numbers_game":
            alive = [p for p in game.get("turnOrder", [])
                     if not players.get(p, {}).get("isEliminated", False)]
            it["participants"] = alive
            it["awaiting"] = list(alive)
            it["prompt"] = (
                f"{init_name} starts a Numbers Game — everyone show 1-5 fingers. "
                "Lowest UNIQUE number wins!"
            )

        else:
            return {"success": False, "message": f"Unknown interaction: {kind}"}

        self._log(it, it["prompt"])
        game["interaction"] = it
        return {"success": True, "message": it["prompt"]}

    # ───────────────────────────── actions ─────────────────────────────

    def act(self, game: Dict[str, Any], player_id: str, action: str,
            value: Any = None) -> Dict[str, Any]:
        it = game.get("interaction")
        if not it:
            return {"success": False, "message": "No Reward Challenge is in progress"}

        if action == "dismiss":
            if it.get("phase") != "complete":
                return {"success": False, "message": "The Reward Challenge is still in progress"}
            game["interaction"] = None
            return {"success": True, "message": "Reward Challenge cleared"}

        if it.get("phase") == "complete":
            return {"success": False, "message": "This Reward Challenge is already resolved"}

        if player_id not in it.get("participants", []):
            return {"success": False, "message": "You are not part of this Reward Challenge"}

        handler = {
            "pick": self._act_pick,
            "give": self._act_give,
            "steal_from": self._act_steal_from,
        }.get(action)
        if not handler:
            return {"success": False, "message": f"Unknown Reward Challenge action: {action}"}
        return handler(game, it, player_id, value)

    # ── phase: picking (secret simultaneous throws / fingers) ──

    def _act_pick(self, game: Dict[str, Any], it: Dict[str, Any],
                  player_id: str, value: Any) -> Dict[str, Any]:
        if it["phase"] != "picking":
            return {"success": False, "message": "Picking is over for this round"}
        if player_id not in it["awaiting"]:
            return {"success": False, "message": "You have already made your pick"}

        kind = it["type"]
        if kind == "do_or_die":
            if value not in RPS_THROWS:
                return {"success": False, "message": "Throw rock, paper or scissors"}
        else:
            top = 3 if kind == "power_pair" else 5
            try:
                value = int(value)
            except (TypeError, ValueError):
                return {"success": False, "message": f"Show between 1 and {top} fingers"}
            if not 1 <= value <= top:
                return {"success": False, "message": f"Show between 1 and {top} fingers"}

        it["_picks"][player_id] = value
        it["awaiting"] = [p for p in it["awaiting"] if p != player_id]
        self._log(it, f"{self._name(game, player_id)} is ready.")

        if it["awaiting"]:
            names = ", ".join(self._name(game, p) for p in it["awaiting"])
            it["prompt"] = f"Waiting on {names}…"
            return {"success": True, "message": "Your pick is in — waiting for the others"}

        return self._resolve_picks(game, it)

    def _resolve_picks(self, game: Dict[str, Any], it: Dict[str, Any]) -> Dict[str, Any]:
        picks = dict(it["_picks"])
        it["picks"] = picks               # the reveal
        it["_picks"] = {}
        resolver = {
            "do_or_die": self._resolve_do_or_die,
            "power_pair": self._resolve_power_pair,
            "numbers_game": self._resolve_numbers_game,
        }[it["type"]]
        return resolver(game, it, picks)

    def _next_round(self, game: Dict[str, Any], it: Dict[str, Any],
                    reason: str) -> Dict[str, Any]:
        it["lastRound"] = {"round": it["round"], "picks": dict(it["picks"]), "outcome": reason}
        self._log(it, reason)
        if it["round"] >= MAX_ROUNDS:
            return self._finish(game, it, f"{it['name']} fizzles out after {MAX_ROUNDS} rounds — no effect.")
        it["round"] += 1
        it["picks"] = {}
        it["awaiting"] = list(it["participants"])
        it["phase"] = "picking"
        it["prompt"] = f"{reason} Round {it['round']} — pick again!"
        return {"success": True, "message": it["prompt"]}

    # ── Do Or Die resolution ──

    def _resolve_do_or_die(self, game: Dict[str, Any], it: Dict[str, Any],
                           picks: Dict[str, str]) -> Dict[str, Any]:
        a, b = it["participants"]
        throw_a, throw_b = picks[a], picks[b]
        name_a, name_b = self._name(game, a), self._name(game, b)
        self._log(it, f"Reveal — {name_a}: {throw_a}, {name_b}: {throw_b}.")

        if throw_a == throw_b:
            # "If you tie, you each swap 1 card of your choice."
            it["lastRound"] = {"round": it["round"], "picks": picks, "outcome": "tie"}
            givers = [p for p in (a, b)
                      if takeable_indices(game["players"][p].get("hand"))]
            if not givers:
                return self._finish(game, it, f"A tie — but neither player has a card to swap.")
            it["phase"] = "give"
            it["giveReason"] = "swap"
            it["_gives"] = {}
            it["awaiting"] = givers
            it["prompt"] = "A tie! Each player chooses 1 card to swap."
            self._log(it, it["prompt"])
            return {"success": True, "message": it["prompt"]}

        winner = a if RPS_BEATS[throw_a] == throw_b else b
        loser = b if winner == a else a
        it["lastRound"] = {"round": it["round"], "picks": picks, "outcome": f"{winner} wins"}
        # The Guide names Do Or Die as Sorry-For-You-able — route through the gate
        pending, take = request_take(
            game, [winner], loser, "Do Or Die",
            {"kind": "random_each", "takes": [{"thiefId": winner, "count": 2}]})
        # The summary becomes the shared prompt AND the shared log — it must not
        # confirm what the loser is holding. The holder's own phone gets the
        # Sorry For You choice from the reactive window itself.
        outcome = (f"the raid hangs in the air — {self._name(game, loser)} may have an answer"
                   if pending else take.get("message", ""))
        return self._finish(
            game, it,
            f"{self._name(game, winner)} wins {picks[winner]} over {picks[loser]} — {outcome}"
        )

    # ── Power Pair resolution ──

    def _resolve_power_pair(self, game: Dict[str, Any], it: Dict[str, Any],
                            picks: Dict[str, int]) -> Dict[str, Any]:
        reveal = ", ".join(f"{self._name(game, p)}: {n}" for p, n in picks.items())
        self._log(it, f"Reveal — {reveal}.")
        values = list(picks.values())

        if len(set(values)) == 3:
            return self._next_round(game, it, "All different — play again!")

        if len(set(values)) == 1:
            # "If ALL players show the same number, each player discards 1."
            it["lastRound"] = {"round": it["round"], "picks": picks, "outcome": "all matched"}
            givers = [p for p in it["participants"]
                      if takeable_indices(game["players"][p].get("hand"))]
            if not givers:
                return self._finish(game, it, "All matched — but nobody has a card to discard.")
            it["phase"] = "give"
            it["giveReason"] = "discard"
            it["_gives"] = {}
            it["awaiting"] = givers
            it["prompt"] = "All three matched! Each player chooses 1 card to discard."
            self._log(it, it["prompt"])
            return {"success": True, "message": it["prompt"]}

        # Exactly two match: they each steal 1 random card from the third
        pair_value = next(v for v in values if values.count(v) == 2)
        pair = [p for p, v in picks.items() if v == pair_value]
        odd_one = next(p for p, v in picks.items() if v != pair_value)
        pending, take = request_take(
            game, pair, odd_one, "Power Pair",
            {"kind": "random_each",
             "takes": [{"thiefId": t, "count": 1} for t in pair]})
        taken = [] if pending else [take.get("message", "")]
        it["lastRound"] = {"round": it["round"], "picks": picks, "outcome": "pair"}
        pair_names = " and ".join(self._name(game, p) for p in pair)
        if pending:
            # Shared copy must not confirm the odd one out is holding Sorry For
            # You — the reactive window tells THEM; the table only learns the
            # raid is hanging.
            outcome = (f"{pair_names} matched on {pair_value} — but the raid hangs "
                       f"in the air; {self._name(game, odd_one)} may have an answer")
        elif taken:
            outcome = (f"{pair_names} matched on {pair_value} — they each steal a card from "
                       f"{self._name(game, odd_one)}!")
        else:
            outcome = f"{pair_names} matched on {pair_value}, but {self._name(game, odd_one)} had no cards to take."
        return self._finish(game, it, outcome)

    # ── Numbers Game resolution ──

    def _resolve_numbers_game(self, game: Dict[str, Any], it: Dict[str, Any],
                              picks: Dict[str, int]) -> Dict[str, Any]:
        reveal = ", ".join(f"{self._name(game, p)}: {n}" for p, n in picks.items())
        self._log(it, f"Reveal — {reveal}.")

        counts: Dict[int, int] = {}
        for n in picks.values():
            counts[n] = counts.get(n, 0) + 1
        unique = [n for n, c in counts.items() if c == 1]

        if not unique:
            return self._next_round(game, it, "No unique number — everyone matched someone.")

        lowest = min(unique)
        winner = next(p for p, n in picks.items() if n == lowest)
        it["lastRound"] = {"round": it["round"], "picks": picks, "outcome": f"{winner} wins"}
        it["winnerId"] = winner
        it["phase"] = "choose_victim"
        it["awaiting"] = [winner]
        it["prompt"] = (
            f"{self._name(game, winner)} showed the lowest unique number ({lowest}) — "
            "they steal 2 random cards from any player!"
        )
        self._log(it, it["prompt"])
        return {"success": True, "message": it["prompt"]}

    def _act_steal_from(self, game: Dict[str, Any], it: Dict[str, Any],
                        player_id: str, value: Any) -> Dict[str, Any]:
        if it["phase"] != "choose_victim":
            return {"success": False, "message": "There is no victim to choose right now"}
        if player_id != it.get("winnerId"):
            return {"success": False, "message": "Only the winner chooses who to steal from"}

        victim_id = value.get("targetId") if isinstance(value, dict) else value
        players = game.get("players", {})
        if (not isinstance(victim_id, str) or victim_id not in players
                or victim_id == player_id
                or players[victim_id].get("isEliminated", False)):
            return {"success": False, "message": "Choose another player still in the game"}

        pending, take = request_take(
            game, [player_id], victim_id, "It's A Numbers Game",
            {"kind": "random_each", "takes": [{"thiefId": player_id, "count": 2}]})
        # Non-confirming shared copy — see _resolve_do_or_die.
        outcome = (f"the raid hangs in the air — {self._name(game, victim_id)} may have an answer"
                   if pending else take.get("message", ""))
        return self._finish(game, it, outcome)

    # ── phase: give (tie swap / all-match discard — a card of YOUR choice) ──

    def _act_give(self, game: Dict[str, Any], it: Dict[str, Any],
                  player_id: str, value: Any) -> Dict[str, Any]:
        if it["phase"] != "give":
            return {"success": False, "message": "Nobody is giving cards right now"}
        if player_id not in it["awaiting"]:
            return {"success": False, "message": "You have already chosen a card"}

        hand = game["players"][player_id].get("hand") or []
        try:
            idx = int(value)
        except (TypeError, ValueError):
            return {"success": False, "message": "Choose a card from your hand"}
        if not 0 <= idx < len(hand):
            return {"success": False, "message": "Choose a card from your hand"}
        if idx not in takeable_indices(hand):
            return {"success": False,
                    "message": "Your Vote Card isn't yours to hand over — choose another card"}

        it.setdefault("_gives", {})[player_id] = idx
        it["awaiting"] = [p for p in it["awaiting"] if p != player_id]
        self._log(it, f"{self._name(game, player_id)} has chosen a card.")

        if it["awaiting"]:
            names = ", ".join(self._name(game, p) for p in it["awaiting"])
            it["prompt"] = f"Waiting on {names} to choose a card…"
            return {"success": True, "message": "Card chosen — waiting for the others"}

        return self._resolve_gives(game, it)

    def _resolve_gives(self, game: Dict[str, Any], it: Dict[str, Any]) -> Dict[str, Any]:
        gives = it.pop("_gives", {})

        # Pull every chosen card out first so simultaneous swaps can't collide
        pulled: Dict[str, Dict[str, Any]] = {}
        for pid, idx in gives.items():
            hand = game["players"][pid].get("hand") or []
            if 0 <= idx < len(hand):
                pulled[pid] = hand.pop(idx)

        if it.get("giveReason") == "swap":
            a, b = it["participants"]
            if a in pulled:
                game["players"][b].setdefault("hand", []).append(pulled[a])
            if b in pulled:
                game["players"][a].setdefault("hand", []).append(pulled[b])
            return self._finish(
                game, it,
                f"The swap is made — {self._name(game, a)} and {self._name(game, b)} "
                "exchange the cards they chose."
            )

        # discard: the pulled cards go face up on the Discard Pile
        game.setdefault("discard", []).extend(pulled.values())
        names = ", ".join(self._name(game, p) for p in pulled) or "nobody"
        return self._finish(game, it, f"Cards discarded by {names}.")


# Module-level singleton — the engine holds no per-game state.
interaction_engine = InteractionEngine()
