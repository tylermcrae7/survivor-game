#!/usr/bin/env python3
"""
Inheritance — the printed card.

  INHERITANCE (6 CARDS, 1 OF EACH COLOR)
  Each Inheritance Card targets a different color player. When that player is
  eliminated from the game (by having both of their Survivor Character Cards
  turned over), you can IMMEDIATELY play this card. You get all of the cards in
  their hand instead of their cards going in the Discard Pile.

  Tip: It can be useful to have the Inheritance for a player that isn't in the
  game. You can discard it if someone plays a Sorry For You against you!

What shipped before was a digital adaptation: one card, played on your turn to
mark anyone you liked, which then fired automatically and was never spent.
Three things were wrong with that — the binding, the timing, and the fact that
the card cost nothing.

One deviation remains, deliberately. The card says you *may* play it; here it
fires on its own. Declining a whole hand for the price of a card you are
holding anyway is a choice nobody makes, and buying it would mean pausing an
elimination mid-council on an answer that might never come — which freezes the
endgame for everyone. That trade is not worth a decision nobody takes.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seats
from rules_engine import SurvivorRulesEngine
from survivor_server import GameState


def hand_types(game, pid):
    return [c.get("type") for c in game["players"][pid]["hand"]]


class InheritanceCardTest(unittest.TestCase):
    def test_there_is_one_card_per_colour(self):
        rules = SurvivorRulesEngine()
        defs = rules.get_all_card_definitions()
        for key in seats.SEAT_KEYS:
            card = defs.get(f"inheritance_{key}")
            self.assertIsNotNone(card, f"no Inheritance card for {key}")
            self.assertEqual(card["count"], 1, "1 of each colour, never more")

    def test_the_deck_holds_exactly_six(self):
        rules = SurvivorRulesEngine()
        deck = rules.create_action_deck()
        found = [c["type"] for c in deck if c["type"].startswith("inheritance_")]
        self.assertEqual(len(found), 6)
        self.assertEqual(len(set(found)), 6, "one of each colour")

    def test_no_inheritance_card_can_be_played_by_hand(self):
        """It answers an elimination; it is not a move you make."""
        rules = SurvivorRulesEngine()
        defs = rules.get_all_card_definitions()
        for key in seats.SEAT_KEYS:
            self.assertEqual(defs[f"inheritance_{key}"]["playable_phases"], [])


class InheritanceEstateTest(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        self.gs = GameState()
        self.gid = self.gs.create_game()
        self.ids = [self.gs.add_player(self.gid, n) for n in ("Ana", "Ben", "Cam", "Dee")]
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seat(self, pid):
        return seats.seat_of(self.game["players"][pid])

    def test_the_matching_colour_takes_the_whole_hand(self):
        heir, dead = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(dead)}"
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": "vote"}, {"type": card}]
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"},
                                              {"type": "the_spy_shack"}]

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertTrue(messages)
        self.assertEqual(sorted(hand_types(self.game, heir)),
                         ["camp_raid", "the_spy_shack", "vote"])
        self.assertEqual(self.game["players"][dead]["hand"], [])

    def test_the_card_is_spent_when_it_fires(self):
        """It goes face up on the Discard Pile like anything else played."""
        heir, dead = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(dead)}"
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": card}]
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"}]

        self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertNotIn(card, hand_types(self.game, heir))
        self.assertIn(card, [c.get("type") for c in self.game["discard"]])

    def test_another_colour_inherits_nothing_and_keeps_its_card(self):
        heir, dead = self.ids[0], self.ids[1]
        wrong = next(k for k in seats.SEAT_KEYS if k != self.seat(dead))
        # Everyone else empty, or a dealt card of the right colour decides it.
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": f"inheritance_{wrong}"}]
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"}]

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertFalse(messages)
        self.assertEqual(hand_types(self.game, heir), [f"inheritance_{wrong}"])
        self.assertEqual(hand_types(self.game, dead), ["camp_raid"],
                         "the estate is untouched and goes to the discard")

    def test_a_card_for_a_colour_nobody_is_playing_never_fires(self):
        """Deliberate dead weight — and the Guide says to use it as chaff."""
        game = self.gs.games[self.gid]
        taken = {seats.seat_of(p) for p in game["players"].values()}
        absent = next(k for k in seats.SEAT_KEYS if k not in taken)
        heir, dead = self.ids[0], self.ids[1]
        # The shuffled setup hand may otherwise give another player the card
        # matching `dead`, causing a legitimate but unrelated inheritance.
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": f"inheritance_{absent}"}]
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"}]

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertFalse(messages)
        self.assertEqual(hand_types(self.game, heir), [f"inheritance_{absent}"])

    def test_the_dead_players_ballot_goes_back_to_the_box(self):
        """Or the heir votes twice at every council from then on."""
        heir, dead = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(dead)}"
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": "vote"}, {"type": card}]
        self.game["players"][dead]["hand"] = [{"type": "vote"},
                                              {"type": "goodwill_gamble"},
                                              {"type": "camp_raid"}]

        self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        heir_hand = hand_types(self.game, heir)
        self.assertEqual(heir_hand.count("vote"), 1)
        self.assertNotIn("goodwill_gamble", heir_hand)
        self.assertIn("camp_raid", heir_hand)

    def test_an_eliminated_player_cannot_inherit(self):
        heir, dead = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(dead)}"
        # Isolate the eliminated heir. A random setup hand belonging to a
        # different living player can contain the same colour-bound card and
        # should not make this test fail for doing exactly what the rules say.
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": card}]
        self.game["players"][heir]["isEliminated"] = True
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"}]

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertFalse(messages)
        self.assertEqual(hand_types(self.game, dead), ["camp_raid"])

    def test_an_empty_estate_leaves_the_card_unspent(self):
        heir, dead = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(dead)}"
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": card}]
        self.game["players"][dead]["hand"] = [{"type": "vote"}]   # ballot only

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertFalse(messages)
        self.assertIn(card, hand_types(self.game, heir),
                      "nothing was inherited, so nothing was paid")

    def test_a_seatless_legacy_player_is_inherited_from_by_nobody(self):
        """An old save whose colour cannot be placed binds to no card."""
        heir, dead = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(dead)}"
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        self.game["players"][heir]["hand"] = [{"type": card}]
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"}]
        # Unplaceable colour, as a pre-seats record would be.
        del self.game["players"][dead]["seat"]
        self.game["players"][dead]["color"] = "#96CEB4"

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertFalse(messages)
        self.assertEqual(hand_types(self.game, dead), ["camp_raid"])

    def test_the_estate_arrives_through_a_real_elimination(self):
        """End to end, through complete_tribal rather than the helper."""
        game = self.game
        heir, doomed = self.ids[0], self.ids[1]
        card = f"inheritance_{self.seat(doomed)}"
        game["players"][doomed]["characterCards"] = 1
        game["players"][heir]["hand"] = [{"type": "vote"}, {"type": card}]
        game["players"][doomed]["hand"] = [{"type": "vote"}, {"type": "camp_raid"}]
        for pid in self.ids[2:]:
            game["players"][pid]["hand"] = [{"type": "vote"}]
        self.gs.rules_engine.sync_vote_counters(game)

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.gid, "elimination")
        for voter in self.ids:
            target = doomed if voter != doomed else heir
            votes = max(1, game["players"][voter].get("mandatoryVotes", 1))
            self.gs.cast_vote(self.gid, voter, [{"targetId": target, "votes": votes}])
        self.gs.reveal_votes(self.gid)      # seals the box
        self.gs.reveal_votes(self.gid)      # tallies
        self.gs.complete_tribal(self.gid,
                                playerId=game["currentVote"].get("councilLeaderId"))

        self.assertTrue(game["players"][doomed]["isEliminated"])
        self.assertIn("camp_raid", hand_types(game, heir),
                      "the estate reached the heir, not the discard")
        self.assertNotIn(card, hand_types(game, heir), "and the card was spent")


class LegacyInheritanceHealsOnLoadTest(unittest.TestCase):
    """A game already in flight when the card changed.

    Six copies of a type the catalogue no longer has is not a cosmetic
    problem: they cannot be played, they cannot fire on an elimination, and
    they are about an eighth of the draw pile.
    """

    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        self.gs = GameState()
        self.gid = self.gs.create_game()
        self.ids = [self.gs.add_player(self.gid, n) for n in ("Ana", "Ben", "Cam", "Dee")]
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_legacy(self):
        """Rewind the game to the pre-colour card: six bare `inheritance`."""
        from rules_engine import _iter_game_cards
        for card in _iter_game_cards(self.game):
            if card.get("type", "").startswith("inheritance"):
                card["type"] = "inheritance"

    def all_inheritance(self):
        from rules_engine import _iter_game_cards
        return [c["type"] for c in _iter_game_cards(self.game)
                if c.get("type", "").startswith("inheritance")]

    def test_every_legacy_copy_gains_a_colour(self):
        from rules_engine import ensure_seat_bound_inheritance
        self._make_legacy()
        self.assertEqual(self.all_inheritance(), ["inheritance"] * 6)

        self.assertEqual(ensure_seat_bound_inheritance(self.game), 6)

        bound = self.all_inheritance()
        self.assertNotIn("inheritance", bound, "no legacy copy is left behind")
        self.assertEqual(sorted(bound),
                         sorted(f"inheritance_{k}" for k in seats.SEAT_KEYS),
                         "one of each colour, exactly as printed")

    def test_it_is_idempotent_and_never_duplicates_a_colour(self):
        from rules_engine import ensure_seat_bound_inheritance
        self._make_legacy()
        ensure_seat_bound_inheritance(self.game)
        first = sorted(self.all_inheritance())

        self.assertEqual(ensure_seat_bound_inheritance(self.game), 0)
        self.assertEqual(sorted(self.all_inheritance()), first)

    def test_a_half_migrated_game_keeps_the_colours_it_has(self):
        """A colour already dealt must not be minted a second time."""
        from rules_engine import _iter_game_cards, ensure_seat_bound_inheritance
        self._make_legacy()
        # One card already made the jump; five are still legacy.
        legacy = [c for c in _iter_game_cards(self.game)
                  if c.get("type") == "inheritance"]
        legacy[0]["type"] = "inheritance_red"

        ensure_seat_bound_inheritance(self.game)

        bound = self.all_inheritance()
        self.assertEqual(bound.count("inheritance_red"), 1, "red is not duplicated")
        self.assertEqual(sorted(bound),
                         sorted(f"inheritance_{k}" for k in seats.SEAT_KEYS))

    def test_uids_survive_the_relabel(self):
        """Relabelling in place, not rebuilding — a new dict would orphan a
        card mid-hand and hand SwiftUI two rows with the same identity."""
        from rules_engine import _iter_game_cards, ensure_seat_bound_inheritance
        self._make_legacy()
        before = {c["uid"] for c in _iter_game_cards(self.game)
                  if c.get("type") == "inheritance"}

        ensure_seat_bound_inheritance(self.game)

        after = {c["uid"] for c in _iter_game_cards(self.game)
                 if c.get("type", "").startswith("inheritance_")}
        self.assertEqual(before, after)

    def test_the_healed_card_actually_fires(self):
        """The point of the exercise: it inherits an estate afterwards."""
        from rules_engine import _iter_game_cards, ensure_seat_bound_inheritance
        self._make_legacy()
        ensure_seat_bound_inheritance(self.game)

        heir, dead = self.ids[0], self.ids[1]
        seat = seats.seat_of(self.game["players"][dead])
        for pid in self.ids:
            self.game["players"][pid]["hand"] = []
        # Take the healed card for that colour out of wherever it landed.
        card = next(c for c in _iter_game_cards(self.game)
                    if c.get("type") == f"inheritance_{seat}")
        self.game["players"][heir]["hand"] = [dict(card)]
        self.game["players"][dead]["hand"] = [{"type": "camp_raid"}]

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        self.assertTrue(messages)
        self.assertIn("camp_raid", hand_types(self.game, heir))


if __name__ == '__main__':
    unittest.main(verbosity=2)
