#!/usr/bin/env python3
"""Card conservation: a steal moves exactly N cards, and mints none.

For every path that takes cards, assert three things: the victim's hand
shrank by N, the thief's grew by N, and the total number of cards in the
game (hands + deck + discard) did not change.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules_engine import (execute_take_spec, new_card, SurvivorRulesEngine)
from interactions import interaction_engine


def _game(hands, deck=0, discard=0):
    return {
        "players": {
            pid: {"name": pid.capitalize(), "hand": [new_card(t) for t in types],
                  "isEliminated": False}
            for pid, types in hands.items()
        },
        "deck": [new_card("extra_vote") for _ in range(deck)],
        "discard": [new_card("camp_raid") for _ in range(discard)],
        "turnOrder": list(hands.keys()), "currentTurnIndex": 0,
        "phase": "playing",
    }


def _census(game):
    return (sum(len(p.get("hand") or []) for p in game["players"].values())
            + len(game.get("deck") or []) + len(game.get("discard") or []))


def _hand(game, pid):
    return len(game["players"][pid].get("hand") or [])


class ConservationCase(unittest.TestCase):
    def assertMoved(self, game, action, thief, victim, n):
        """Run action(), then assert thief +n, victim -n, census equal."""
        before_thief, before_victim = _hand(game, thief), _hand(game, victim)
        census = _census(game)
        action()
        self.assertEqual(_hand(game, thief), before_thief + n, "thief's gain")
        self.assertEqual(_hand(game, victim), before_victim - n, "victim's loss")
        self.assertEqual(_census(game), census, "cards minted or destroyed")


class TakeSpecConservationTest(ConservationCase):
    def test_random_each_two_cards(self):
        game = _game({"a": ["vote"], "b": ["vote", "extra_vote", "camp_raid", "the_spy_shack"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                             "takes": [{"thiefId": "a", "count": 2}]}),
            thief="a", victim="b", n=2)

    def test_random_each_never_takes_the_vote_card(self):
        game = _game({"a": [], "b": ["vote", "extra_vote"]})
        execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 2}]})
        self.assertEqual([c["type"] for c in game["players"]["b"]["hand"]], ["vote"])
        self.assertEqual(_hand(game, "a"), 1)

    def test_pair_takes_one_each(self):
        game = _game({"a": [], "b": [], "c": ["extra_vote", "camp_raid", "vote"]})
        before = _census(game)
        execute_take_spec(game, {"victimId": "c", "kind": "random_each",
                                 "takes": [{"thiefId": "a", "count": 1},
                                           {"thiefId": "b", "count": 1}]})
        self.assertEqual((_hand(game, "a"), _hand(game, "b"), _hand(game, "c")),
                         (1, 1, 1))
        self.assertEqual(_census(game), before)

    def test_index_take(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "index",
                                             "thiefId": "a", "index": 1}),
            thief="a", victim="b", n=1)

    def test_by_type_take(self):
        game = _game({"a": [], "b": ["extra_vote", "camp_raid"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "by_type",
                                             "thiefId": "a", "cardType": "camp_raid"}),
            thief="a", victim="b", n=1)

    def test_vote_card_take(self):
        game = _game({"a": [], "b": ["vote", "extra_vote"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "vote_card",
                                             "thiefId": "a"}),
            thief="a", victim="b", n=1)

    def test_short_hand_takes_what_exists(self):
        """Asked for 2, victim has 1 takeable: exactly 1 moves, none invented."""
        game = _game({"a": [], "b": ["vote", "extra_vote"]})
        self.assertMoved(
            game,
            lambda: execute_take_spec(game, {"victimId": "b", "kind": "random_each",
                                             "takes": [{"thiefId": "a", "count": 2}]}),
            thief="a", victim="b", n=1)


class TurnStealConservationTest(ConservationCase):
    def test_plain_steal_moves_one(self):
        engine = SurvivorRulesEngine()
        game = _game({"a": ["vote"], "b": ["vote", "extra_vote", "camp_raid"]})
        self.assertMoved(game, lambda: engine.execute_theft(game, "a", "b"),
                         thief="a", victim="b", n=1)


class DoOrDieEndToEndConservationTest(ConservationCase):
    """The reported bug, end to end: win RPS, get exactly 2 of the loser's cards."""
    def test_winner_gets_two_loser_loses_two(self):
        game = _game({"a": ["vote"], "b": ["vote", "extra_vote", "camp_raid", "the_spy_shack"]})
        interaction_engine.start(game, "a", "do_or_die",
                                 {"targetId": "b", "choice": "rock"})
        self.assertMoved(
            game,
            lambda: interaction_engine.act(game, "b", "pick", "scissors"),
            thief="a", victim="b", n=2)

    def test_tie_swap_conserves_hand_sizes(self):
        game = _game({"a": ["vote", "extra_vote"], "b": ["vote", "camp_raid"]})
        interaction_engine.start(game, "a", "do_or_die",
                                 {"targetId": "b", "choice": "rock"})
        interaction_engine.act(game, "b", "pick", "rock")   # tie -> give phase
        before = _census(game)
        interaction_engine.act(game, "a", "give", 1)
        interaction_engine.act(game, "b", "give", 1)
        self.assertEqual(_hand(game, "a"), 2)
        self.assertEqual(_hand(game, "b"), 2)
        self.assertEqual(_census(game), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
