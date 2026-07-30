#!/usr/bin/env python3
"""
Test script for the rules engine integration
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('=== COMPREHENSIVE RULES ENGINE TEST ===')
print()

# Run in a throwaway directory so the real games.json is never touched
import tempfile
os.chdir(tempfile.mkdtemp())

# Test 1: Rules Engine Standalone
from rules_engine import SurvivorRulesEngine, NON_OFFICIAL_CARD_TYPES
rules = SurvivorRulesEngine()
card_count = len(rules.card_definitions['cards'])
assert card_count > 0, 'card registry failed to load'
official_cards = sum(
    c['count'] for t, c in rules.get_all_card_definitions().items()
    if t not in NON_OFFICIAL_CARD_TYPES and c['category'] != 'challenge'
)
assert official_cards == 67, f'official deck should be 67 cards, got {official_cards}'
print(f'✅ Rules engine loaded {card_count} card types ({official_cards} official cards)')

# Test 2: Deck Creation
deck = rules.create_deck(4)
resolved = rules.resolve_cards(deck)
tribal_cards = [c for c in resolved if c.get('category') == 'tribal_council']
action_cards = [c for c in resolved if c.get('category') != 'tribal_council']
assert len(tribal_cards) == 4, f'4 players should get 4 tribal cards, got {len(tribal_cards)}'
assert len(action_cards) == 52, f'official draw pile is 52 action cards, got {len(action_cards)}'
assert not [c for c in deck if c.get('type') == 'vote'], 'no Vote Cards belong in the deck'
print(f'✅ Deck created: {len(deck)} cards ({len(action_cards)} action + {len(tribal_cards)} tribal)')

# Test 3: Card Validation
extra_vote_card = rules.get_card_definition('extra_vote')
assert extra_vote_card and extra_vote_card['playable_phases'] == ['tribal_voting']
print(f'✅ Card definition loaded: {extra_vote_card["name"]} - {extra_vote_card["description"][:50]}...')

# Test 4: Card effects — every registry card type resolves and dispatches
missing = [
    t for t, c in rules.get_all_card_definitions().items()
    if c['category'] not in ('vote', 'tribal_council') and t not in rules.card_effects_registry
]
assert not missing, f'card types with no effect implementation: {missing}'
print(f'✅ Effect registry covers all {len(rules.card_effects_registry)} playable card types')

# Test 5: Server Integration
import survivor_server
gs = survivor_server.GameState()
game_id = gs.create_game()
player_id = gs.add_player(game_id, 'TestPlayer')
assert player_id, 'add_player should return a player id'
print(f'✅ Server integration: Game {game_id} created with player {player_id[:8]}...')

# Test 6: API Compatibility
cards_data = gs.rules_engine.card_definitions
assert 'cards' in cards_data and 'validation' in cards_data
print(f'✅ API compatibility: Card data structure intact with {len(cards_data["cards"])} cards')

print()
print('🎉 ALL TESTS PASSED - Rules engine successfully implemented!')
print()
print('Rules Engine Architecture Summary:')
print('- Card registry: Official 67-card set (+7 house cards, +5 Rocks challenges)')
print('- Effect dispatch: every card type in the registry has an implementation')
print('- Deck construction: Dynamic tribal card insertion based on player count')
print('- Phase validation: Complete turn and tribal council phase logic')
print('- Server integration: Clean separation between rules and infrastructure')

# This script is a straight-line smoke test: any failed expectation raises, and the
# exit code below is what run_all_tests.py checks.
sys.exit(0)