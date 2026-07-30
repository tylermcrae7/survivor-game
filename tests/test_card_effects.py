#!/usr/bin/env python3
"""
Card Effect Validation Tests

Covers every card that actually exists in survivor_cards.json — the 17 official
card types from Survivor: The Tribe Has Spoken, the 4 house cards that only appear
in the extended deck, and the 5 Orange Challenge Cards from Let's Go To Rocks.

Card behaviour is checked against the official Survival Guide wording.
"""

import unittest
import tempfile
import os
import sys
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState
from rules_engine import NON_OFFICIAL_CARD_TYPES, CHALLENGE_CARD_TYPES


class CardEffectTestBase(unittest.TestCase):
    """Shared 4-player game fixture with deterministic hands."""

    PLAYER_COUNT = 4
    DECK_MODE = "official"
    EXPANSION = False

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.game_id = self.gs.create_game(deckMode=self.DECK_MODE, expansion=self.EXPANSION)

        colors = ["red", "blue", "green", "yellow", "orange", "purple"]
        self.player_ids = [
            self.gs.add_player(self.game_id, f"Player{i + 1}", colors[i])
            for i in range(self.PLAYER_COUNT)
        ]

        self.gs.start_full_game(self.game_id)
        self.game = self.gs.games[self.game_id]

        # Deterministic hands — opening deals are random, which makes hand-size and
        # vote-economy assertions flaky.
        for player in self.game["players"].values():
            player["hand"] = [
                {"type": "the_spy_shack"},
                {"type": "camp_raid"},
                {"type": "inheritance"},
                {"type": "vote"},
            ]
        self.gs.rules_engine.sync_vote_counters(self.game)

        # Put the turn on player 1, past the mandatory steal
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(self.player_ids[0])
        for player in self.game["players"].values():
            player["hasStolen"] = True

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── helpers ──

    def hand(self, player_id):
        return self.game["players"][player_id]["hand"]

    def hand_types(self, player_id):
        return [c.get("type") for c in self.hand(player_id)]

    def give(self, player_id, card_type):
        """Put a card in a player's hand and return its index."""
        self.hand(player_id).append({"type": card_type})
        self.gs.rules_engine.sync_vote_counters(self.game)
        return len(self.hand(player_id)) - 1

    def find_card_index(self, player_id, card_type):
        for i, card in enumerate(self.hand(player_id)):
            if card.get("type") == card_type:
                return i
        return -1

    def play(self, player_id, card_type, **params):
        idx = self.find_card_index(player_id, card_type)
        self.assertGreaterEqual(idx, 0, f"{card_type} not in hand")
        return self.gs.play_card(self.game_id, player_id, idx, params or None)


class TestCardRegistry(CardEffectTestBase):
    """The card registry itself: counts, categories, required fields."""

    def test_card_registry_official_counts(self):
        """The official box is 67 Action Cards; the house deck adds exactly 7."""
        cards = self.gs.rules_engine.get_all_card_definitions()

        official_total = sum(
            c["count"] for t, c in cards.items()
            if t not in NON_OFFICIAL_CARD_TYPES and c["category"] != "challenge"
        )
        self.assertEqual(official_total, 67)

        house_total = sum(c["count"] for t, c in cards.items() if t in NON_OFFICIAL_CARD_TYPES)
        self.assertEqual(house_total, 7)

        challenge_total = sum(c["count"] for c in cards.values() if c["category"] == "challenge")
        self.assertEqual(challenge_total, 5)

    def test_official_tribal_and_vote_card_counts(self):
        """9 Tribal Council Cards and 6 Vote Cards, per the rules sheet contents."""
        cards = self.gs.rules_engine.get_all_card_definitions()
        tribal = sum(c["count"] for c in cards.values() if c["category"] == "tribal_council")
        self.assertEqual(tribal, 9)
        self.assertEqual(cards["vote"]["count"], 6)
        self.assertEqual(cards["extra_vote"]["count"], 7)

    def test_every_card_has_required_fields(self):
        cards = self.gs.rules_engine.get_all_card_definitions()
        required = ["type", "category", "name", "description", "playable_phases",
                    "requires_target", "reactive_only", "count"]
        for card_type, card in cards.items():
            for field in required:
                self.assertIn(field, card, f"{card_type} missing {field}")
            self.assertTrue(card["name"], f"{card_type} has an empty name")
            self.assertTrue(card["description"], f"{card_type} has an empty description")
            self.assertIsInstance(card["playable_phases"], list)

    def test_get_complete_card(self):
        card = self.gs.get_complete_card("camp_raid")
        self.assertEqual(card["type"], "camp_raid")
        self.assertEqual(card["category"], "action")
        self.assertTrue(card["requires_target"])
        self.assertIsNone(self.gs.get_complete_card("no_such_card"))

    def test_house_cards_excluded_from_official_deck(self):
        official = self.gs.rules_engine.create_deck(4, deck_mode="official")
        extended = self.gs.rules_engine.create_deck(4, deck_mode="extended")

        for card_type in NON_OFFICIAL_CARD_TYPES:
            self.assertNotIn(card_type, [c["type"] for c in official],
                             f"{card_type} is a house card and must not be in the official deck")
            self.assertIn(card_type, [c["type"] for c in extended])

    def test_challenge_cards_only_with_expansion(self):
        without = self.gs.rules_engine.create_deck(4, expansion=False)
        with_exp = self.gs.rules_engine.create_deck(4, expansion=True)

        for card_type in CHALLENGE_CARD_TYPES:
            self.assertNotIn(card_type, [c["type"] for c in without])
            self.assertIn(card_type, [c["type"] for c in with_exp])


class TestTurnActionCards(CardEffectTestBase):
    """Action cards played on your turn."""

    def test_basic_steal(self):
        thief, victim = self.player_ids[0], self.player_ids[1]
        self.game["players"][thief]["hasStolen"] = False
        # Sorry For You would open a reactive window instead of resolving immediately
        self.hand(victim)[:] = [{"type": "camp_raid"}, {"type": "vote"}]

        before_thief = len(self.hand(thief))
        before_victim = len(self.hand(victim))

        result = self.gs.steal_card(self.game_id, thief, victim)
        self.assertTrue(result["success"], result.get("message"))

        self.assertEqual(len(self.hand(thief)), before_thief + 1)
        self.assertEqual(len(self.hand(victim)), before_victim - 1)
        self.assertTrue(self.game["players"][thief]["hasStolen"])

    def test_camp_raid_marks_target_for_their_next_draw(self):
        """
        Survival Guide: "Place this card face up in front of any player. you take the
        next card they draw at the end of their turn."
        """
        raider, victim = self.player_ids[0], self.player_ids[1]
        # Distinct victim hand so stolen cards can't be confused with the played one
        self.hand(victim)[:] = [{"type": "immunity_idol"}, {"type": "immunity_idol"}]

        result = self.play(raider, "camp_raid", targetId=victim)
        self.assertTrue(result["success"], result.get("message"))
        self.assertNotIn("camp_raid", self.hand_types(raider))
        # Nothing moves at play time — the trap sits face up on the victim
        self.assertEqual(len(self.hand(victim)), 2)
        self.assertEqual(self.game["players"][victim].get("campRaidedBy"), raider)

        # A second Camp Raid can't stack on the same player
        second = self.player_ids[2]
        self.give(second, "camp_raid")
        self.game["turnOrder"] = self.game.get("turnOrder") or self.player_ids
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(second)
        self.game["players"][second]["hasStolen"] = True
        result = self.play(second, "camp_raid", targetId=victim)
        self.assertFalse(result["success"])
        self.assertIn("already has", result.get("message", ""))

        # The trap springs on the victim's next draw: the drawn card transfers
        self.game["turnOrder"] = self.game.get("turnOrder") or self.player_ids
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(victim)
        self.game["players"][victim]["hasStolen"] = True
        self.game["players"][victim]["hasDrawn"] = False
        self.game["deck"] = [{"type": "vote"}]
        raider_before = len(self.hand(raider))
        result = self.gs.draw_card(self.game_id, playerId=victim)
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(len(self.hand(raider)), raider_before + 1)
        self.assertIn("vote", self.hand_types(raider))
        self.assertIsNone(self.game["players"][victim].get("campRaidedBy"))

    def test_the_spy_shack_looks_and_takes_one(self):
        """Survival Guide: "Look at any player's cards and take one." """
        spy, victim = self.player_ids[0], self.player_ids[1]
        # Distinct victim hand so the taken card can't be confused with the played one
        self.hand(victim)[:] = [{"type": "immunity_idol"}, {"type": "knowledge_is_power"}]
        taken_type = self.hand(victim)[0]["type"]
        victim_before = len(self.hand(victim))

        result = self.play(spy, "the_spy_shack", targetId=victim, takeIndex=0)
        self.assertTrue(result["success"], result.get("message"))
        self.assertNotIn("the_spy_shack", self.hand_types(spy))
        self.assertIn(taken_type, self.hand_types(spy))
        self.assertEqual(len(self.hand(victim)), victim_before - 1)

        # Without naming the card to take, the play is rejected pre-consumption
        self.give(spy, "the_spy_shack")
        self.game["players"][spy]["hasPlayed"] = False
        result = self.play(spy, "the_spy_shack", targetId=victim)
        self.assertFalse(result["success"])
        self.assertIn("the_spy_shack", self.hand_types(spy))

    def test_knowledge_is_power_takes_a_named_card(self):
        """Survival Guide: "Ask any player for a card by name. If they have it, they must give you 1." """
        asker, victim = self.player_ids[0], self.player_ids[1]
        self.give(asker, "knowledge_is_power")
        self.hand(victim)[:] = [{"type": "immunity_idol"}, {"type": "vote"}]

        result = self.play(asker, "knowledge_is_power", targetId=victim, cardType="immunity_idol")
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn("immunity_idol", self.hand_types(asker))
        self.assertNotIn("immunity_idol", self.hand_types(victim))

        # Asking for something they don't have takes nothing (fresh turn —
        # the official rule allows only one play per turn)
        self.give(asker, "knowledge_is_power")
        self.game["players"][asker]["hasPlayed"] = False
        result = self.play(asker, "knowledge_is_power", targetId=victim, cardType="camp_raid")
        self.assertTrue(result["success"])
        self.assertIn("does not have", result["message"])

    def test_lets_form_an_alliance_steals_one_card_each(self):
        """You and your partner EACH steal 1 card from the victim."""
        player, ally, victim = self.player_ids[0], self.player_ids[1], self.player_ids[2]
        self.give(player, "lets_form_an_alliance")

        before_player = len(self.hand(player))
        before_ally = len(self.hand(ally))
        before_victim = len(self.hand(victim))

        result = self.play(player, "lets_form_an_alliance", allyId=ally, victimId=victim)
        self.assertTrue(result["success"], result.get("message"))

        # player: +1 stolen, -1 played alliance card
        self.assertEqual(len(self.hand(player)), before_player)
        self.assertEqual(len(self.hand(ally)), before_ally + 1)
        self.assertEqual(len(self.hand(victim)), before_victim - 2)

    def test_inheritance_marks_a_target_and_transfers_on_elimination(self):
        """
        Survival Guide: inheritance pays out "When that player is eliminated from the
        game (by having both of their Survivor Character Cards turned over)".
        """
        heir, doomed = self.player_ids[0], self.player_ids[1]

        result = self.play(heir, "inheritance", targetId=doomed)
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.game["players"][heir]["inheritanceTarget"], doomed)

        doomed_hand = list(self.hand(doomed))
        heir_before = len(self.hand(heir))

        messages = self.gs.rules_engine.process_elimination_inheritance(self.game, doomed)
        self.assertTrue(messages)
        self.assertEqual(len(self.hand(heir)), heir_before + len(doomed_hand))
        self.assertEqual(self.hand(doomed), [])
        self.assertIsNone(self.game["players"][heir]["inheritanceTarget"])

    def test_inheritance_does_not_fire_on_a_non_elimination_vote_out(self):
        """A vote-out that only flips one card must NOT pay out the inheritance."""
        heir, doomed = self.player_ids[0], self.player_ids[1]
        self.play(heir, "inheritance", targetId=doomed)

        heir_before = list(self.hand(heir))
        doomed_before = list(self.hand(doomed))

        # Run a tribal that votes `doomed` out once (2 cards -> 1, still in the game)
        self.gs._trigger_tribal_council(self.game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        for voter in self.player_ids:
            target = doomed if voter != doomed else heir
            self.gs.cast_vote(self.game_id, voter, [{"targetId": target, "votes": 1}])
        self.gs.reveal_votes(self.game_id)
        self.gs.complete_tribal(self.game_id)

        self.assertEqual(self.game["players"][doomed]["characterCards"], 1)
        self.assertFalse(self.game["players"][doomed]["isEliminated"])
        # Hands unchanged except for the Vote Card spent and returned
        self.assertEqual(len(self.hand(doomed)), len(doomed_before))
        self.assertEqual(len(self.hand(heir)), len(heir_before))
        self.assertEqual(self.game["players"][heir]["inheritanceTarget"], doomed)

    def test_reward_challenge_do_or_die_starts_a_real_duel(self):
        """The opponent throws for themselves — the server never rolls for them."""
        player = self.player_ids[0]
        self.give(player, "reward_challenge_do_or_die")
        result = self.play(player, "reward_challenge_do_or_die",
                           targetId=self.player_ids[1], choice="rock")
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["interaction_started"])

        interaction = self.game["interaction"]
        self.assertEqual(interaction["type"], "do_or_die")
        self.assertEqual(interaction["awaiting"], [self.player_ids[1]])

    def test_reward_challenge_power_pair_needs_two_picked_players(self):
        player = self.player_ids[0]
        self.give(player, "reward_challenge_power_pair")

        # Official: "Pick 2 other players" — playing blind is rejected, card kept
        result = self.play(player, "reward_challenge_power_pair")
        self.assertFalse(result["success"])
        self.assertIn("reward_challenge_power_pair", self.hand_types(player))

        result = self.play(player, "reward_challenge_power_pair",
                           targetIds=[self.player_ids[1], self.player_ids[2]])
        self.assertTrue(result["success"], result.get("message"))
        interaction = self.game["interaction"]
        self.assertEqual(interaction["type"], "power_pair")
        self.assertEqual(len(interaction["participants"]), 3)

    def test_reward_challenge_its_a_numbers_game_includes_everyone(self):
        player = self.player_ids[0]
        self.give(player, "reward_challenge_its_a_numbers_game")
        result = self.play(player, "reward_challenge_its_a_numbers_game")
        self.assertTrue(result["success"], result.get("message"))
        interaction = self.game["interaction"]
        self.assertEqual(interaction["type"], "numbers_game")
        self.assertCountEqual(interaction["participants"], self.player_ids)


class TestCardValidation(CardEffectTestBase):
    """Phase gating, target requirements, and cards that can't be played at all."""

    def test_sorry_for_you_cannot_be_played_proactively(self):
        player = self.player_ids[0]
        self.give(player, "sorry_for_you")
        result = self.play(player, "sorry_for_you")
        self.assertFalse(result["success"])
        self.assertIn("reactive", result["message"].lower())

    def test_vote_cards_cannot_be_played_from_hand(self):
        player = self.player_ids[0]
        for card_type in ("vote", "extra_vote"):
            self.give(player, card_type)
            result = self.play(player, card_type)
            self.assertFalse(result["success"], card_type)
            self.assertIn("spent when you vote", result["message"])

    def test_tribal_advantage_not_playable_during_a_turn(self):
        player = self.player_ids[0]
        self.give(player, "control_the_vote")
        result = self.play(player, "control_the_vote", targetId=self.player_ids[1])
        self.assertFalse(result["success"])
        self.assertIn("control_the_vote", self.hand_types(player))

    def test_target_requirement_validation(self):
        player = self.player_ids[0]

        # No target
        result = self.play(player, "camp_raid")
        self.assertFalse(result["success"])
        self.assertIn("camp_raid", self.hand_types(player))

        # Invalid target
        result = self.play(player, "camp_raid", targetId="not-a-player")
        self.assertFalse(result["success"])
        self.assertIn("camp_raid", self.hand_types(player))

        # Valid target
        result = self.play(player, "camp_raid", targetId=self.player_ids[1])
        self.assertTrue(result["success"], result.get("message"))

    def test_cards_cannot_be_played_before_stealing(self):
        player = self.player_ids[0]
        self.game["players"][player]["hasStolen"] = False
        result = self.play(player, "the_spy_shack", targetId=self.player_ids[1])
        self.assertFalse(result["success"])

    def test_eliminated_players_cannot_play_cards(self):
        player = self.player_ids[0]
        self.game["players"][player]["isEliminated"] = True
        result = self.play(player, "the_spy_shack", targetId=self.player_ids[1])
        self.assertFalse(result["success"])
        self.assertIn("Eliminated", result["message"])


class TestTribalCouncilCards(CardEffectTestBase):
    """Immunity idols, nullifiers and tribal advantages."""

    DECK_MODE = "extended"  # idol_nullifier is a house card

    def test_immunity_idol_negates_votes(self):
        protected = self.player_ids[0]
        self.gs._trigger_tribal_council(self.game, "single")
        self.give(protected, "immunity_idol")

        result = self.gs.play_immunity(self.game_id, playerId=protected)
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(self.game["players"][protected]["immunityIdolProtection"])
        self.assertNotIn("immunity_idol", self.hand_types(protected))

    def test_immunity_idol_can_protect_another_player(self):
        player, ally = self.player_ids[0], self.player_ids[1]
        self.gs._trigger_tribal_council(self.game, "single")
        self.give(player, "immunity_idol")

        result = self.gs.play_immunity(self.game_id, playerId=player, targetId=ally)
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(self.game["players"][ally]["immunityIdolProtection"])
        self.assertFalse(self.game["players"][player].get("immunityIdolProtection", False))

    def test_idol_nullifier_cancels_protection(self):
        protected, nullifier = self.player_ids[0], self.player_ids[1]
        self.gs._trigger_tribal_council(self.game, "single")
        self.game["players"][protected]["immunityIdolProtection"] = True
        self.give(nullifier, "idol_nullifier")

        result = self.gs.block_immunity(self.game_id, playerId=nullifier, targetId=protected)
        self.assertTrue(result["success"], result.get("message"))
        self.assertFalse(self.game["players"][protected]["immunityIdolProtection"])
        self.assertTrue(self.game["players"][protected]["idolNullified"])
        self.assertNotIn("idol_nullifier", self.hand_types(nullifier))

    def test_idol_nullifier_requires_a_protected_target(self):
        protected, nullifier = self.player_ids[0], self.player_ids[1]
        self.gs._trigger_tribal_council(self.game, "single")
        self.give(nullifier, "idol_nullifier")

        result = self.gs.block_immunity(self.game_id, playerId=nullifier, targetId=protected)
        self.assertFalse(result["success"])
        self.assertIn("does not have immunity protection", result["message"])

    def test_im_the_leader_now_takes_the_gavel(self):
        player = self.player_ids[1]
        self.gs._trigger_tribal_council(self.game, "single", drawer_id=self.player_ids[0])
        self.assertEqual(self.game["currentVote"]["councilLeaderId"], self.player_ids[0])

        self.gs.advance_tribal_phase(self.game_id, "advantage_play")
        self.give(player, "im_the_leader_now")

        result = self.gs.play_tribal_advantage(self.game_id, player, "im_the_leader_now")
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.game["currentVote"]["councilLeaderId"], player)


class TestChallengeCards(CardEffectTestBase):
    """Let's Go To Rocks Orange Challenge Cards (combined mode)."""

    EXPANSION = True

    def test_playing_a_challenge_card_starts_a_challenge(self):
        player = self.player_ids[0]
        self.give(player, "challenge_highest_bidder")

        result = self.play(player, "challenge_highest_bidder")
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["challenge_started"])

        challenge = self.game["challenge"]
        self.assertEqual(challenge["type"], "highest_bidder")
        self.assertEqual(challenge["bag"], {"grey": 10, "purple": 1})
        self.assertEqual(challenge["currentPlayerId"], player)
        self.assertEqual(challenge["actions"], ["bid"])

    def test_hide_n_seek_is_unavailable_digitally(self):
        player = self.player_ids[0]
        self.give(player, "challenge_hide_n_seek")

        result = self.play(player, "challenge_hide_n_seek")
        self.assertTrue(result["success"], result.get("message"))
        self.assertFalse(result["challenge_started"])
        self.assertIn("sleight-of-hand", result["message"])
        self.assertIsNone(self.game.get("challenge"))

    def test_challenge_blocks_other_turn_actions(self):
        player = self.player_ids[0]
        self.give(player, "challenge_pull_or_steal")
        self.play(player, "challenge_pull_or_steal")

        draw = self.gs.draw_card(self.game_id, player)
        self.assertFalse(draw["success"])
        self.assertIn("Resolve the active Challenge", draw["message"])

        advance = self.gs.advance_turn(self.game_id)
        self.assertFalse(advance["success"])

    def test_challenge_cards_rejected_without_expansion(self):
        gs = GameState()
        game_id = gs.create_game(expansion=False)
        for i in range(3):
            gs.add_player(game_id, f"P{i}", f"c{i}")
        gs.start_full_game(game_id)
        game = gs.games[game_id]

        player = game["turnOrder"][game["currentTurnIndex"]]
        game["players"][player]["hasStolen"] = True
        game["players"][player]["hand"].append({"type": "challenge_highest_bidder"})
        idx = len(game["players"][player]["hand"]) - 1

        result = gs.play_card(game_id, player, idx)
        self.assertFalse(result["success"])
        self.assertIn("expansion", result["message"])


class TestReactiveCardMechanics(CardEffectTestBase):
    """Sorry For You — the reactive theft interrupt."""

    def test_theft_with_no_reactive_cards_resolves_immediately(self):
        thief, target = self.player_ids[0], self.player_ids[1]
        self.game["players"][thief]["hasStolen"] = False
        self.hand(target)[:] = [{"type": "vote"}, {"type": "the_spy_shack"}]

        result = self.gs.steal_card(self.game_id, thief, target)
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(len(result["stolen_cards"]), 1)
        self.assertNotIn("reactive_window", result)
        self.assertNotIn("pending_theft", self.game)

    def test_theft_opens_a_reactive_window(self):
        thief, target = self.player_ids[0], self.player_ids[1]
        self.game["players"][thief]["hasStolen"] = False
        self.hand(target)[:] = [
            {"type": "sorry_for_you"},
            {"type": "sorry_for_you"},
            {"type": "vote"},
        ]

        result = self.gs.steal_card(self.game_id, thief, target)
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["reactive_window"])
        self.assertEqual(len(result["reactive_cards"]), 2)

        pending = self.game["pending_theft"]
        self.assertEqual(pending["thiefId"], thief)
        self.assertEqual(pending["targetId"], target)

        # The thief hasn't stolen anything yet
        self.assertFalse(self.game["players"][thief]["hasStolen"])

    def test_sorry_for_you_blocks_the_theft_and_forces_a_discard(self):
        """
        Survival Guide: "they get nothing from you and must discard 1 card
        (regardless of how many cards you owe them)."
        """
        thief, target = self.player_ids[0], self.player_ids[1]
        self.game["players"][thief]["hasStolen"] = False
        self.hand(target)[:] = [{"type": "sorry_for_you"}, {"type": "vote"}]
        self.hand(thief)[:] = [{"type": "vote"}, {"type": "camp_raid"}]

        self.gs.steal_card(self.game_id, thief, target)

        result = self.gs.handle_reactive_card_play(self.game_id, target, 0, {})
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["reactive_interrupt"])
        self.assertIn("Sorry for you", result["message"])

        # Target spent the Sorry For You card; thief lost one card and their steal
        self.assertEqual(self.hand_types(target), ["vote"])
        self.assertEqual(len(self.hand(thief)), 1)
        self.assertTrue(self.game["players"][thief]["hasStolen"])
        self.assertNotIn("pending_theft", self.game)

    def test_declining_to_react_completes_the_theft(self):
        thief, target = self.player_ids[0], self.player_ids[1]
        self.game["players"][thief]["hasStolen"] = False
        self.hand(target)[:] = [{"type": "sorry_for_you"}, {"type": "vote"}]

        self.gs.steal_card(self.game_id, thief, target)
        result = self.gs.complete_pending_theft(self.game_id)

        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(len(self.hand(target)), 1)
        self.assertTrue(self.game["players"][thief]["hasStolen"])
        self.assertNotIn("pending_theft", self.game)

    def test_only_the_theft_target_can_react(self):
        thief, target, bystander = self.player_ids[0], self.player_ids[1], self.player_ids[2]
        self.game["players"][thief]["hasStolen"] = False
        self.hand(target)[:] = [{"type": "sorry_for_you"}, {"type": "vote"}]
        self.hand(bystander)[:] = [{"type": "sorry_for_you"}]

        self.gs.steal_card(self.game_id, thief, target)
        result = self.gs.handle_reactive_card_play(self.game_id, bystander, 0, {})
        self.assertFalse(result["success"])
        self.assertIn("Only the theft target", result["message"])


if __name__ == '__main__':
    print("🧪 Testing Card Effects & Validation (Including Reactive Cards)")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_class in (TestCardRegistry, TestTurnActionCards, TestCardValidation,
                       TestTribalCouncilCards, TestChallengeCards,
                       TestReactiveCardMechanics):
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)

    print(f"\n📋 Card Effects Test Summary:")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")

    for test, _ in result.failures:
        print(f"  FAIL: {test}")
    for test, _ in result.errors:
        print(f"  ERROR: {test}")

    success = not result.failures and not result.errors
    print(f"\n🎉 All card effect & reactive card tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
