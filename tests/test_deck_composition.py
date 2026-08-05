#!/usr/bin/env python3
"""
Deck Composition Tests for Survivor App

Tests deck construction for all player counts (3-6) to ensure:
1. Correct tribal council card counts per official rules
2. Proper deck size calculations
3. Card distribution and shuffling
4. Rules compliance for different game sizes
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import shutil
from collections import Counter

from survivor_server import GameState

class TestDeckComposition(unittest.TestCase):
    """Test deck composition for all supported player counts"""

    def setUp(self):
        """Set up test environment with clean temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        self.gs = GameState()
        
        # Official rules table (Survivor: The Tribe Has Spoken, Setup step 4)
        #   Players | Single Elimination | Double Elimination
        #      3    |         4          |         0
        #      4    |         2          |         2
        #      5    |         2          |         3
        #      6    |         0          |         5
        self.expected_tribal_counts = {
            3: {"single": 4, "double": 0},
            4: {"single": 2, "double": 2},
            5: {"single": 2, "double": 3},
            6: {"single": 0, "double": 5},
            7: {"single": 0, "double": 6},
            8: {"single": 0, "double": 7},
        }

        # The official box holds 67 Action Cards. Setup removes the 9 Tribal Council
        # Cards and the 6 Vote Cards (1 dealt per player, extras put away), leaving
        # 52 cards in the Draw Pile before the Tribal Council Cards are shuffled back in.
        # 7-8 players restore the ~6.5 turns/player pacing with a supply pack
        # (Task A3): action_total(N) = ceil(6.5*N) + 3N - tribal_count(N).
        self.expected_action_cards = 52
        self.expected_action_cards_by_count = {
            3: 52, 4: 52, 5: 52, 6: 52, 7: 61, 8: 69,
        }
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_deck_composition_3_players(self):
        """Test deck composition for 3-player game"""
        self._test_player_count_deck_composition(3)
    
    def test_deck_composition_4_players(self):
        """Test deck composition for 4-player game"""
        self._test_player_count_deck_composition(4)
    
    def test_deck_composition_5_players(self):
        """Test deck composition for 5-player game"""
        self._test_player_count_deck_composition(5)
    
    def test_deck_composition_6_players(self):
        """Test deck composition for 6-player game"""
        self._test_player_count_deck_composition(6)

    def test_deck_composition_7_players(self):
        """Test deck composition for 7-player game (Task A3 pacing target)"""
        self._test_player_count_deck_composition(7)

    def test_deck_composition_8_players(self):
        """Test deck composition for 8-player game (Task A3 pacing target)"""
        self._test_player_count_deck_composition(8)

    def _test_player_count_deck_composition(self, player_count):
        """Test deck composition for specific player count"""
        # Create deck using rules engine
        deck = self.gs.rules_engine.create_deck(player_count)
        
        # The deck stores compact cards ({"type": ...}); resolve for metadata checks.
        resolved = self.gs.rules_engine.resolve_cards(deck)

        card_counts = Counter(card["type"] for card in deck)
        category_counts = Counter(card["category"] for card in resolved)
        
        # Get expected tribal counts for this player count
        expected = self.expected_tribal_counts[player_count]
        
        # Verify tribal council card counts match official rules
        actual_single = card_counts.get("tribal_council_single", 0)
        actual_double = card_counts.get("tribal_council_double", 0)
        
        self.assertEqual(actual_single, expected["single"],
            f"Player count {player_count}: Expected {expected['single']} single tribal cards, got {actual_single}")
        
        self.assertEqual(actual_double, expected["double"], 
            f"Player count {player_count}: Expected {expected['double']} double tribal cards, got {actual_double}")
        
        # Verify total tribal council cards
        total_tribal = actual_single + actual_double
        expected_total_tribal = expected["single"] + expected["double"]
        
        self.assertEqual(total_tribal, expected_total_tribal,
            f"Player count {player_count}: Expected {expected_total_tribal} total tribal cards, got {total_tribal}")
        
        # Verify tribal council cards have correct category
        tribal_council_cards = [card for card in resolved if card["category"] == "tribal_council"]
        self.assertEqual(len(tribal_council_cards), expected_total_tribal,
            f"Player count {player_count}: Tribal council category count mismatch")
        
        # Verify minimum deck size (action cards + tribal cards)
        # Should have all action cards plus the calculated tribal cards
        expected_deck_size = (self.expected_action_cards_by_count[player_count]
                               + expected_total_tribal)

        self.assertEqual(len(deck), expected_deck_size,
            f"Player count {player_count}: Expected {expected_deck_size} cards, got {len(deck)}")

        # No Vote Cards may remain in the Draw Pile after setup
        self.assertEqual(card_counts.get("vote", 0), 0,
            f"Player count {player_count}: Vote Cards must be removed from the deck")
        
        # Verify deck contains valid categories only
        valid_categories = {"vote", "tribal_advantage", "action", "tribal_council", "challenge"}
        for category in category_counts:
            self.assertIn(category, valid_categories,
                f"Player count {player_count}: Invalid card category '{category}' found in deck")
        
        # Verify no empty cards or malformed entries
        for i, card in enumerate(resolved):
            self.assertIn("type", card, f"Card {i} missing 'type' field")
            self.assertIn("category", card, f"Card {i} missing 'category' field")
            self.assertIn("name", card, f"Card {i} missing 'name' field")
            self.assertIn("description", card, f"Card {i} missing 'description' field")
            
            self.assertTrue(card["type"], f"Card {i} has empty type")
            self.assertTrue(card["name"], f"Card {i} has empty name")
            self.assertTrue(card["description"], f"Card {i} has empty description")
    
    def test_tribal_card_distribution_through_deck(self):
        """Test that tribal council cards are distributed throughout the deck (not clustered)"""
        for player_count in [3, 4, 5, 6]:
            with self.subTest(player_count=player_count):
                deck = self.gs.rules_engine.create_deck(player_count)
                
                # Find positions of tribal council cards
                tribal_positions = [
                    i for i, card in enumerate(deck)
                    if str(card.get("type", "")).startswith("tribal_council")
                ]
                
                # Should have expected number of tribal cards
                expected = self.expected_tribal_counts[player_count]
                expected_total = expected["single"] + expected["double"]
                
                self.assertEqual(len(tribal_positions), expected_total,
                    f"Player count {player_count}: Wrong number of tribal cards in deck")
                
                if expected_total > 1:
                    # Cards should not all be clustered together
                    # Check that there's reasonable spacing between tribal cards
                    min_spacing = len(deck) // (expected_total + 1)  # Rough minimum spacing
                    
                    for i in range(len(tribal_positions) - 1):
                        spacing = tribal_positions[i + 1] - tribal_positions[i]
                        self.assertGreater(spacing, 1,
                            f"Player count {player_count}: Tribal cards too close together at positions {tribal_positions}")
    
    def test_deck_shuffling_randomness(self):
        """Test that deck creation produces different orderings (shuffling works)"""
        player_count = 4
        
        # Generate multiple decks
        decks = [self.gs.rules_engine.create_deck(player_count) for _ in range(5)]
        
        # Convert to card type sequences for comparison
        sequences = [tuple(card["type"] for card in deck) for deck in decks]
        
        # Should have some variation in ordering (not all identical)
        unique_sequences = set(sequences)
        self.assertGreater(len(unique_sequences), 1, 
            "Deck shuffling should produce different orderings")
        
        # All decks should have same composition (just different order)
        first_deck_counts = Counter(card["type"] for card in decks[0])
        for i, deck in enumerate(decks[1:], 1):
            deck_counts = Counter(card["type"] for card in deck)
            self.assertEqual(first_deck_counts, deck_counts,
                f"Deck {i} has different composition than first deck")
    
    def test_invalid_player_counts(self):
        """Counts outside the supported 3-8 range must raise, loudly.

        The old fallback quietly dealt the 4-player tribal set for any
        unrecognised count — an 8-player game got 6 flips against the 12 it
        needed and limped along on the emergency reshuffle. Task A1 removed
        that silent default: out-of-range is a caller bug, and it says so.
        """
        invalid_counts = [0, 1, 2, 9, 10, -1]

        for count in invalid_counts:
            with self.subTest(player_count=count):
                with self.assertRaises(ValueError) as ctx:
                    self.gs.rules_engine.create_deck(count)
                self.assertIn("player", str(ctx.exception).lower(),
                    f"Exception for count {count} should mention players: {ctx.exception}")
    
    def test_tribal_council_card_properties(self):
        """Test that tribal council cards have correct properties"""
        for player_count in [3, 4, 5, 6]:
            with self.subTest(player_count=player_count):
                deck = self.gs.rules_engine.create_deck(player_count)
                
                # Find all tribal council cards (these carry full metadata in the deck)
                tribal_cards = [card for card in deck
                                if str(card.get("type", "")).startswith("tribal_council")]
                
                for card in tribal_cards:
                    # Should have elimination type
                    self.assertIn("elimination_type", card,
                        f"Tribal card {card['type']} missing elimination_type")
                    
                    # Elimination type should match card type
                    if card["type"] == "tribal_council_single":
                        self.assertEqual(card["elimination_type"], "single")
                    elif card["type"] == "tribal_council_double": 
                        self.assertEqual(card["elimination_type"], "double")
                    else:
                        self.fail(f"Unknown tribal council card type: {card['type']}")
                    
                    # Should have proper name and description
                    self.assertTrue(card["name"], f"Tribal card {card['type']} has empty name")
                    self.assertTrue(card["description"], f"Tribal card {card['type']} has empty description")
    
    def test_comprehensive_player_count_matrix(self):
        """Comprehensive test of the player count to tribal card mapping"""
        # Test the exact mapping from rules
        test_matrix = [
            (3, 4, 0, 4),  # 3 players: 4 single, 0 double, 4 total
            (4, 2, 2, 4),  # 4 players: 2 single, 2 double, 4 total
            (5, 2, 3, 5),  # 5 players: 2 single, 3 double, 5 total
            (6, 0, 5, 5),  # 6 players: 0 single, 5 double, 5 total
            (7, 0, 6, 6),  # extension: all doubles, 12 flips = 2(7-2)+2
            (8, 0, 7, 7),  # extension: all doubles, 14 flips = 2(8-2)+2
        ]
        
        for player_count, exp_single, exp_double, exp_total in test_matrix:
            with self.subTest(players=player_count):
                deck = self.gs.rules_engine.create_deck(player_count)
                
                single_count = sum(1 for card in deck if card["type"] == "tribal_council_single")
                double_count = sum(1 for card in deck if card["type"] == "tribal_council_double")
                total_tribal = single_count + double_count
                
                self.assertEqual(single_count, exp_single,
                    f"{player_count} players: Expected {exp_single} single, got {single_count}")
                self.assertEqual(double_count, exp_double, 
                    f"{player_count} players: Expected {exp_double} double, got {double_count}")
                self.assertEqual(total_tribal, exp_total,
                    f"{player_count} players: Expected {exp_total} total tribal, got {total_tribal}")

    def test_flip_supply_always_exceeds_need_by_exactly_two(self):
        """2 lives x (N-2) players out, +2 spare flips for idol saves —
        the margin the official table keeps at every count."""
        for n in range(3, 9):
            with self.subTest(players=n):
                cards = self.gs.rules_engine._create_tribal_council_cards(n)
                flips = sum(2 if c["elimination_type"] == "double" else 1
                            for c in cards)
                self.assertEqual(flips, 2 * (n - 2) + 2)

    # ── Task A0: Grant Immunity leaves the island ──────────────────────────

    # ── Task A3: The deck grows with the table ──────────────────────────────

    def test_seven_and_eight_player_decks_hit_the_pacing_target(self):
        for n, target in ((7, 61), (8, 69)):
            with self.subTest(players=n):
                deck = self.gs.rules_engine.create_action_deck(player_count=n)
                self.assertEqual(len(deck), target)

    def test_three_to_six_player_decks_are_untouched(self):
        """The official 52-card pile, bit for bit — no new-seat Inheritance,
        no supply pack, exactly what the box prints."""
        for n in range(3, 7):
            with self.subTest(players=n):
                deck = self.gs.rules_engine.create_action_deck(player_count=n)
                types = [c["type"] for c in deck]
                self.assertEqual(len(deck), 52)
                self.assertNotIn("inheritance_purple", types)
                self.assertNotIn("inheritance_pink", types)

    def test_a_deck_with_no_player_count_is_also_untouched(self):
        """Existing callers pass no player_count — default must preserve
        today's behaviour exactly."""
        deck = self.gs.rules_engine.create_action_deck()
        types = [c["type"] for c in deck]
        self.assertEqual(len(deck), 52)
        self.assertNotIn("inheritance_purple", types)
        self.assertNotIn("inheritance_pink", types)

    def test_the_supply_pack_never_duplicates_power(self):
        deck = self.gs.rules_engine.create_action_deck(player_count=8)
        counts = Counter(c["type"] for c in deck)
        base = {t: d.get("count", 0)
                for t, d in self.gs.rules_engine.card_definitions["cards"].items()}
        for scarce in ("immunity_idol", "inheritance_red", "inheritance_purple",
                       "sorry_for_you"):
            self.assertLessEqual(counts.get(scarce, 0), base.get(scarce, 1),
                                 f"{scarce} must stay as scarce as the box made it")

    def test_the_supply_pack_is_deterministic(self):
        a = sorted(c["type"] for c in self.gs.rules_engine.create_action_deck(player_count=8))
        b = sorted(c["type"] for c in self.gs.rules_engine.create_action_deck(player_count=8))
        self.assertEqual(a, b, "same table, same composition — only the shuffle varies")

    def test_seven_and_eight_player_decks_include_the_new_seat_inheritance(self):
        for n in (7, 8):
            with self.subTest(players=n):
                deck = self.gs.rules_engine.create_action_deck(player_count=n)
                types = [c["type"] for c in deck]
                self.assertIn("inheritance_purple", types)
                self.assertIn("inheritance_pink", types)
                self.assertEqual(types.count("inheritance_purple"), 1)
                self.assertEqual(types.count("inheritance_pink"), 1)

    def test_extended_and_expansion_modes_also_hit_the_pacing_target_at_eight(self):
        """The supply pack self-adjusts to whatever mode the game chose —
        the target is fixed, the pack just fills whatever gap is left."""
        for deck_mode in ("official", "extended"):
            for expansion in (False, True):
                with self.subTest(deck_mode=deck_mode, expansion=expansion):
                    deck = self.gs.rules_engine.create_action_deck(
                        deck_mode=deck_mode, expansion=expansion, player_count=8)
                    self.assertEqual(len(deck), 69)

    def test_grant_immunity_is_gone_from_every_new_deck(self):
        for mode in ("official", "extended"):
            with self.subTest(mode=mode):
                deck = self.gs.rules_engine.create_action_deck(deck_mode=mode)
                self.assertNotIn("grant_immunity", [c["type"] for c in deck])

    def test_extended_mode_adds_exactly_six_house_cards(self):
        official = len(self.gs.rules_engine.create_action_deck(deck_mode="official"))
        extended = len(self.gs.rules_engine.create_action_deck(deck_mode="extended"))
        self.assertEqual(extended - official, 6)

if __name__ == '__main__':
    print("Running Deck Composition Tests...")
    unittest.main(verbosity=2)