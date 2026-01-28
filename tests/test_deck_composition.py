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
        
        # Official rules table - per-player tribal council card counts
        # Based on survivor_rules.md and official PDF specifications
        self.expected_tribal_counts = {
            3: {"single": 2, "double": 0},   # 2 single, 0 double
            4: {"single": 2, "double": 1},   # 2 single, 1 double  
            5: {"single": 3, "double": 1},   # 3 single, 1 double
            6: {"single": 3, "double": 2}    # 3 single, 2 double
        }
        
        # Expected action card counts (from official card database)
        # 69 total official cards: 6 Vote + 7 Extra Vote + 12 Tribal Advantages + 35 Actions + 9 Tribal Council
        # Action cards = Total - Vote - Extra Vote - Tribal Council
        # 35 Action cards + 12 Tribal Advantages = 47 non-vote cards distributed to players
        self.expected_action_cards = 47  # Action + Tribal Advantage cards given to players
        
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
    
    def _test_player_count_deck_composition(self, player_count):
        """Test deck composition for specific player count"""
        # Create deck using rules engine
        deck = self.gs.rules_engine.create_deck(player_count)
        
        # Count card types
        card_counts = Counter(card["type"] for card in deck)
        category_counts = Counter(card["category"] for card in deck)
        
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
        tribal_council_cards = [card for card in deck if card["category"] == "tribal_council"]
        self.assertEqual(len(tribal_council_cards), expected_total_tribal,
            f"Player count {player_count}: Tribal council category count mismatch")
        
        # Verify minimum deck size (action cards + tribal cards)
        # Should have all action cards plus the calculated tribal cards
        expected_min_deck_size = self.expected_action_cards + expected_total_tribal
        
        self.assertGreaterEqual(len(deck), expected_min_deck_size,
            f"Player count {player_count}: Deck too small. Expected at least {expected_min_deck_size}, got {len(deck)}")
        
        # Verify deck contains valid categories only
        valid_categories = {"vote", "tribal_advantage", "action", "tribal_council"}
        for category in category_counts:
            self.assertIn(category, valid_categories,
                f"Player count {player_count}: Invalid card category '{category}' found in deck")
        
        # Verify no empty cards or malformed entries
        for i, card in enumerate(deck):
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
                tribal_positions = []
                for i, card in enumerate(deck):
                    if card["category"] == "tribal_council":
                        tribal_positions.append(i)
                
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
        """Test that invalid player counts are handled gracefully"""
        # Test edge cases
        invalid_counts = [0, 1, 2, 7, 8, 10, -1]
        
        for count in invalid_counts:
            with self.subTest(player_count=count):
                # Should not crash, should return some reasonable default
                try:
                    deck = self.gs.rules_engine.create_deck(count)
                    # Should return some deck (likely default for 4 players)
                    self.assertGreater(len(deck), 0, f"Should return non-empty deck for count {count}")
                except Exception as e:
                    # If it raises exception, should be a reasonable error
                    self.assertIn("player", str(e).lower(), 
                        f"Exception for count {count} should mention players: {e}")
    
    def test_tribal_council_card_properties(self):
        """Test that tribal council cards have correct properties"""
        for player_count in [3, 4, 5, 6]:
            with self.subTest(player_count=player_count):
                deck = self.gs.rules_engine.create_deck(player_count)
                
                # Find all tribal council cards
                tribal_cards = [card for card in deck if card["category"] == "tribal_council"]
                
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
            (3, 2, 0, 2),  # 3 players: 2 single, 0 double, 2 total
            (4, 2, 1, 3),  # 4 players: 2 single, 1 double, 3 total  
            (5, 3, 1, 4),  # 5 players: 3 single, 1 double, 4 total
            (6, 3, 2, 5),  # 6 players: 3 single, 2 double, 5 total
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

if __name__ == '__main__':
    print("Running Deck Composition Tests...")
    unittest.main(verbosity=2)