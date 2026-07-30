#!/usr/bin/env python3
"""
Comprehensive Rules Engine Tests for Survivor App

Tests the core rules engine functionality including:
1. Card effect dispatch system
2. Phase validation logic  
3. Deck construction with proper tribal card counts
4. Card registry loading and validation
5. Rules enforcement and error handling
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import shutil
import json
from unittest.mock import patch, mock_open

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import SurvivorRulesEngine

class TestRulesEngineComprehensive(unittest.TestCase):
    """Comprehensive tests for the SurvivorRulesEngine"""

    def setUp(self):
        """Set up test environment with clean temporary directory"""
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
    def tearDown(self):
        """Clean up test environment"""
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_rules_engine_initialization(self):
        """Test that rules engine initializes correctly"""
        engine = SurvivorRulesEngine()
        
        # Should have card definitions loaded
        self.assertIsNotNone(engine.card_definitions)
        self.assertIn('cards', engine.card_definitions)
        self.assertIn('validation', engine.card_definitions)
        
        # Should have effect registry set up
        self.assertIsNotNone(engine.card_effects_registry)
        self.assertIsInstance(engine.card_effects_registry, dict)
    
    def test_card_registry_loading_success(self):
        """Test successful loading of card registry from JSON file"""
        # Create a mock card file
        mock_cards = {
            "cards": {
                "test_card": {
                    "type": "test_card",
                    "category": "action",
                    "name": "Test Card",
                    "description": "A test card",
                    "playable_phases": ["turn_play"],
                    "requires_target": False,
                    "requires_multiple_targets": False,
                    "requires_confirmation": False,
                    "reactive_only": False,
                    "count": 1
                }
            },
            "validation": {
                "total_expected_cards": 1,
                "required_fields": [
                    "type", "category", "name", "description", "playable_phases",
                    "requires_target", "requires_multiple_targets", "requires_confirmation",
                    "reactive_only", "count"
                ]
            }
        }
        
        # Write mock file
        with open("test_cards.json", "w") as f:
            json.dump(mock_cards, f)
        
        # Initialize engine with test file
        engine = SurvivorRulesEngine("test_cards.json")
        
        # Verify loading
        self.assertEqual(engine.card_definitions, mock_cards)
        card_def = engine.get_card_definition("test_card")
        self.assertIsNotNone(card_def)
        self.assertEqual(card_def["name"], "Test Card")
    
    def test_card_registry_loading_fallback_on_missing_file(self):
        """Test fallback to default cards when JSON file is missing"""
        engine = SurvivorRulesEngine("nonexistent_file.json")
        
        # Should still have card definitions (fallback)
        self.assertIsNotNone(engine.card_definitions)
        self.assertIn('cards', engine.card_definitions)
        
        # The fallback registry is deliberately empty — for a rules-fidelity game a
        # silently-wrong deck is worse than an obviously-empty one. What matters is
        # that the engine degrades gracefully instead of raising.
        cards = engine.get_all_card_definitions()
        self.assertIsInstance(cards, dict)
        self.assertEqual(engine.create_deck(4), [])
    
    def test_card_registry_loading_fallback_on_invalid_json(self):
        """Test fallback when JSON file is malformed"""
        # Create invalid JSON file
        with open("invalid_cards.json", "w") as f:
            f.write("{ invalid json content }")
        
        engine = SurvivorRulesEngine("invalid_cards.json")
        
        # Should still work with fallback
        self.assertIsNotNone(engine.card_definitions)
        self.assertIn('cards', engine.card_definitions)
    
    def test_card_validation_missing_required_fields(self):
        """Test that card validation catches missing required fields"""
        # Create cards missing required fields
        invalid_cards = {
            "cards": {
                "incomplete_card": {
                    "type": "incomplete_card",
                    "name": "Incomplete Card"
                    # Missing many required fields
                }
            },
            "validation": {
                "total_expected_cards": 1,
                "required_fields": [
                    "type", "category", "name", "description", "playable_phases",
                    "requires_target", "requires_multiple_targets", "requires_confirmation",
                    "reactive_only", "count"
                ]
            }
        }
        
        with open("invalid_structure.json", "w") as f:
            json.dump(invalid_cards, f)
        
        # Should fall back to default cards due to validation failure
        engine = SurvivorRulesEngine("invalid_structure.json")
        
        # Should have fallback cards, not the invalid ones
        self.assertIsNotNone(engine.card_definitions)
        card_def = engine.get_card_definition("incomplete_card")
        self.assertIsNone(card_def)  # Should not have invalid card
    
    def test_deck_construction_algorithm(self):
        """Test the deck construction algorithm with various player counts"""
        engine = SurvivorRulesEngine()
        
        # Test all supported player counts
        for player_count in [3, 4, 5, 6]:
            with self.subTest(player_count=player_count):
                deck = engine.create_deck(player_count)
                
                # Should return a non-empty list
                self.assertIsInstance(deck, list)
                self.assertGreater(len(deck), 0)
                
                # Deck cards are stored compactly ({"type": ...}); metadata comes
                # from resolve_card against the registry.
                for card in deck:
                    self.assertIsInstance(card, dict)
                    self.assertIn("type", card)

                for card in engine.resolve_cards(deck):
                    self.assertIn("category", card)
                    self.assertIn("name", card)
                    self.assertIn("description", card)
    
    def test_tribal_card_count_algorithm(self):
        """Test the tribal council card count algorithm"""
        engine = SurvivorRulesEngine()
        
        # Test the internal tribal card creation method
        # The official rules table (Setup step 4)
        test_cases = [
            (3, {"single": 4, "double": 0}),
            (4, {"single": 2, "double": 2}),
            (5, {"single": 2, "double": 3}),
            (6, {"single": 0, "double": 5})
        ]
        
        for player_count, expected in test_cases:
            with self.subTest(player_count=player_count):
                tribal_cards = engine._create_tribal_council_cards(player_count)
                
                # Count card types
                single_count = sum(1 for card in tribal_cards 
                                 if card["type"] == "tribal_council_single")
                double_count = sum(1 for card in tribal_cards 
                                 if card["type"] == "tribal_council_double")
                
                self.assertEqual(single_count, expected["single"],
                    f"Wrong single count for {player_count} players")
                self.assertEqual(double_count, expected["double"],
                    f"Wrong double count for {player_count} players")
    
    def test_card_effect_dispatch_system(self):
        """Test that card effect dispatch system is properly set up"""
        engine = SurvivorRulesEngine()
        
        # Should have effect registry
        self.assertIsInstance(engine.card_effects_registry, dict)
        
        # Should have some registered effects
        self.assertGreater(len(engine.card_effects_registry), 0)
        
        # Test getting effect functions
        all_cards = engine.get_all_card_definitions()
        
        for card_type, card_data in all_cards.items():
            # Should be able to get effect function (even if it's a default)
            effect_func = engine.card_effects_registry.get(card_type)
            
            # Effect function should be callable
            if effect_func is not None:
                self.assertTrue(callable(effect_func),
                    f"Effect for {card_type} should be callable")
    
    def test_phase_validation_logic(self):
        """Test phase validation logic for different card types"""
        engine = SurvivorRulesEngine()
        
        # Test some known phase combinations
        phase_tests = [
            # (card_type, valid_phases, invalid_phases)
            ("the_spy_shack", ["turn_play"], ["turn_steal", "tribal_voting"]),
            ("control_the_vote", ["tribal_discussion"], ["turn_play", "turn_steal"]),
            ("immunity_idol", ["tribal_immunity"], ["turn_play", "tribal_voting"]),
            ("sorry_for_you", ["reactive_theft"], ["turn_play", "tribal_discussion"])
        ]
        
        for card_type, valid_phases, invalid_phases in phase_tests:
            card_def = engine.get_card_definition(card_type)
            
            if card_def:  # Skip if card not found (may not be in fallback)
                with self.subTest(card_type=card_type):
                    playable_phases = card_def.get("playable_phases", [])
                    
                    # Valid phases should be in playable_phases
                    for phase in valid_phases:
                        self.assertIn(phase, playable_phases,
                            f"{card_type} should be playable in {phase}")
                    
                    # Invalid phases should NOT be in playable_phases
                    for phase in invalid_phases:
                        self.assertNotIn(phase, playable_phases,
                            f"{card_type} should NOT be playable in {phase}")
    
    def test_card_definition_completeness(self):
        """Test that all card definitions have complete required fields"""
        engine = SurvivorRulesEngine()
        all_cards = engine.get_all_card_definitions()
        
        required_fields = [
            "type", "category", "name", "description", "playable_phases",
            "requires_target", "requires_multiple_targets", "requires_confirmation",
            "reactive_only", "count"
        ]
        
        for card_type, card_data in all_cards.items():
            with self.subTest(card_type=card_type):
                for field in required_fields:
                    self.assertIn(field, card_data,
                        f"Card {card_type} missing required field: {field}")
                    
                # Validate field types
                self.assertIsInstance(card_data["playable_phases"], list,
                    f"{card_type}: playable_phases should be list")
                self.assertIsInstance(card_data["requires_target"], bool,
                    f"{card_type}: requires_target should be bool")
                self.assertIsInstance(card_data["requires_multiple_targets"], bool,
                    f"{card_type}: requires_multiple_targets should be bool")
                self.assertIsInstance(card_data["requires_confirmation"], bool,
                    f"{card_type}: requires_confirmation should be bool")
                self.assertIsInstance(card_data["reactive_only"], bool,
                    f"{card_type}: reactive_only should be bool")
                self.assertIsInstance(card_data["count"], int,
                    f"{card_type}: count should be int")
                
                # Validate count is positive
                self.assertGreater(card_data["count"], 0,
                    f"{card_type}: count should be positive")
    
    def test_valid_categories_enforcement(self):
        """Test that only valid card categories are used"""
        engine = SurvivorRulesEngine()
        all_cards = engine.get_all_card_definitions()
        
        valid_categories = {"vote", "tribal_advantage", "action", "tribal_council", "challenge"}
        
        for card_type, card_data in all_cards.items():
            with self.subTest(card_type=card_type):
                category = card_data.get("category")
                self.assertIn(category, valid_categories,
                    f"Card {card_type} has invalid category: {category}")
    
    def test_valid_phases_enforcement(self):
        """Test that only valid game phases are used in card definitions"""
        engine = SurvivorRulesEngine()
        all_cards = engine.get_all_card_definitions()
        
        # Import valid phases from rules engine
        from rules_engine import VALID_TURN_PHASES
        
        for card_type, card_data in all_cards.items():
            with self.subTest(card_type=card_type):
                playable_phases = card_data.get("playable_phases", [])
                
                for phase in playable_phases:
                    self.assertIn(phase, VALID_TURN_PHASES,
                        f"Card {card_type} has invalid phase: {phase}")
    
    def test_rules_engine_error_handling(self):
        """Test that rules engine handles errors gracefully"""
        # Test with completely invalid initialization
        with patch('builtins.open', mock_open(read_data="invalid")):
            engine = SurvivorRulesEngine("fake_file.json")
            
            # Should still function with fallback
            self.assertIsNotNone(engine.card_definitions)
            
            # Should be able to create decks without raising (empty on fallback)
            deck = engine.create_deck(4)
            self.assertIsInstance(deck, list)
    
    def test_card_insertion_algorithm(self):
        """Test the tribal card insertion algorithm"""
        engine = SurvivorRulesEngine()
        
        # Create a test deck with known cards
        test_deck = [
            {"type": f"test_card_{i}", "category": "action"} 
            for i in range(20)
        ]
        
        # Create tribal cards to insert
        tribal_cards = [
            {"type": "tribal_council_single", "category": "tribal_council"},
            {"type": "tribal_council_double", "category": "tribal_council"}
        ]
        
        # Test insertion
        result_deck = engine._insert_tribal_cards(test_deck, tribal_cards)
        
        # Should have all original cards plus tribal cards
        self.assertEqual(len(result_deck), len(test_deck) + len(tribal_cards))
        
        # Should contain all tribal cards
        tribal_types = [card["type"] for card in result_deck 
                       if card["category"] == "tribal_council"]
        expected_tribal_types = [card["type"] for card in tribal_cards]
        
        for expected_type in expected_tribal_types:
            self.assertIn(expected_type, tribal_types)
        
        # Tribal cards should be distributed (not all at end)
        tribal_positions = [i for i, card in enumerate(result_deck) 
                           if card["category"] == "tribal_council"]
        
        if len(tribal_positions) > 1:
            # Should have some spacing between tribal cards
            max_spacing = max(tribal_positions[i+1] - tribal_positions[i] 
                            for i in range(len(tribal_positions)-1))
            self.assertGreater(max_spacing, 1, 
                "Tribal cards should be distributed through deck")

if __name__ == '__main__':
    print("Running Comprehensive Rules Engine Tests...")
    unittest.main(verbosity=2)