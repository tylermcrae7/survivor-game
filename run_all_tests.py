#!/usr/bin/env python3
"""
Test Runner for Survivor iOS App
Runs all available test suites and provides a summary report
"""

import subprocess
import sys
import time

def run_test_file(test_file, description):
    """Run a test file and return results"""
    print(f"\n{'='*60}")
    print(f"Running {description}")
    print(f"File: {test_file}")
    print('='*60)
    
    start_time = time.time()
    
    try:
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        success = result.returncode == 0
        return {
            'file': test_file,
            'description': description,
            'success': success,
            'duration': duration,
            'return_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        
    except Exception as e:
        print(f"ERROR running {test_file}: {e}")
        return {
            'file': test_file,
            'description': description,
            'success': False,
            'duration': 0,
            'error': str(e)
        }

def main():
    print("🧪 Survivor iOS App - Test Suite Runner")
    print(f"Python: {sys.version}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Define all test files (now in tests/ directory)
    test_suites = [
        {
            'file': 'tests/test_gamestate_units.py', 
            'description': 'GameState Unit Tests (38 tests)'
        },
        {
            'file': 'tests/test_integration_turns.py',
            'description': 'Turn-Based Integration Tests (9 tests)'
        },
        {
            'file': 'tests/test_tribal_council.py',
            'description': 'Tribal Council Flow & Phase Transition Tests (15 tests)'
        },
        {
            'file': 'tests/test_card_effects.py',
            'description': 'Card Effects & Reactive Card Tests (20+ tests)'
        },
        {
            'file': 'tests/test_robustness.py',
            'description': 'Robustness & iOS Compatibility Tests'
        },
        {
            'file': 'tests/test_edge_cases.py',
            'description': 'Comprehensive Edge Case & Real-World Failure Tests (25+ tests)'
        },
        {
            'file': 'tests/test_phase_enforcement.py',
            'description': 'Negative Phase Enforcement Tests (12+ tests)'
        },
        {
            'file': 'tests/test_deck_composition.py',
            'description': 'Deck Composition Tests for All Player Counts (15+ tests)'
        },
        {
            'file': 'tests/test_tribal_triggers.py',
            'description': 'Tribal Council Trigger Tests (10+ tests)'
        },
        {
            'file': 'tests/test_rules_engine_comprehensive.py',
            'description': 'Comprehensive Rules Engine Tests (15+ tests)'
        },
        {
            'file': 'tests/test_error_handling.py',
            'description': 'Error Handling Tests'
        },
        {
            'file': 'tests/test_rules_engine.py',
            'description': 'Basic Rules Engine Tests'
        },
        {
            'file': 'tests/test_optimization_fixes.py',
            'description': 'Optimization Fixes Tests'
        },
        {
            'file': 'tests/test_critical_bug_fixes.py',
            'description': 'Critical Bug Fixes Tests'
        },
        {
            'file': 'tests/test_targeted_optimization_fixes.py',
            'description': 'Targeted Optimization Fixes Tests'
        },
        {
            'file': 'tests/test_tie_break_cascade.py',
            'description': 'Tie-Break & Double-Elimination Cascade Tests (16 tests)'
        },
        {
            'file': 'tests/test_rocks_expansion.py',
            'description': "Let's Go To Rocks Expansion Tests — necklace + 4 challenges (31 tests)"
        },
        {
            'file': 'tests/test_reward_interactions.py',
            'description': 'Reward Challenge Interactions — Do Or Die / Power Pair / Numbers Game / Spy Shack (25 tests)'
        },
        {
            'file': 'tests/test_access_gate.py',
            'description': 'Access Gate Tests — shared island code for the public tunnel (14 tests)'
        },
        {
            'file': 'tests/test_rules_enforcement.py',
            'description': 'Rules Enforcement — turn discipline, Camp Raid trap, universal Sorry For You gate'
        },
        {
            'file': 'tests/ui/test_ui_rules_checklist.py',
            'description': 'UI Rules Verification — the browser-side twin of the compliance checklist (39 checks, 2 real browsers)'
        },
        {
            'file': 'tests/test_bots.py',
            'description': 'Computer Players — lifecycle, Hall of Fame guard, decisions, full bot games to completion'
        },
        {
            'file': 'tests/test_game_settings.py',
            'description': 'Per-Game Settings — bot pace/style, tribal windows with human floors, Leader control'
        },
        {
            'file': 'tests/test_push_notifications.py',
            'description': 'Turn Notifications — VAPID keys, subscriptions, turn/tribal sends, graceful failure'
        },
        {
            'file': 'tests/test_places.py',
            'description': 'Places — derived camp locations, movement policy, voice plan for the Discord bot (53 tests)'
        },
        {
            'file': 'tests/test_link_codes.py',
            'description': 'Discord link codes — one-time, single-use, and useless to a guesser'
        },
        {
            'file': 'tests/test_seats.py',
            'description': 'Seats — six fixed colours, derived for old saves, never guessed'
        },
        {
            'file': 'tests/test_inheritance.py',
            'description': 'Inheritance — colour-bound, spent when it fires, dead weight when the colour is absent'
        },
        {
            'file': 'tests/test_card_identity.py',
            'description': 'Card identity — every card knows which card it is, through every move and the reshuffle'
        },
        {
            'file': 'tests/test_penalty_discard.py',
            'description': 'Sorry For You penalty — the raider chooses what they give up, and the table can never freeze on it'
        },
        {
            'file': 'tests/test_nullifier_window.py',
            'description': 'Idol Nullifier — the reactive window an idol opens, and every way it must not wedge a council'
        },
        {
            'file': 'tests/test_narrator_events.py',
            'description': 'Narrator events — the commentary actually fires, names the right people, and leaks no peeked cards'
        },
        {
            'file': 'tests/test_steal_alerts.py',
            'description': 'Steal alerts — every card movement leaves a record, and no alert leaks a card identity'
        },
        {
            'file': 'tests/test_theft_window.py',
            'description': 'Sorry For You window — victim-only decline, the timeout, and the council that must not eat a won steal'
        },
        {
            'file': 'tests/test_card_conservation.py',
            'description': 'Card conservation — every steal moves exactly the cards it claims, and mints none'
        },
        {
            'file': 'tests/test_tie_break_eight_players.py',
            'description': 'Tie-breakers at eight — the official cascade pinned rule-by-rule at a full table'
        }
    ]
    
    results = []
    total_start = time.time()
    
    # Run each test suite
    for test_suite in test_suites:
        result = run_test_file(test_suite['file'], test_suite['description'])
        results.append(result)
    
    total_end = time.time()
    total_duration = total_end - total_start
    
    # Generate summary report
    print(f"\n{'='*60}")
    print("TEST SUMMARY REPORT")
    print('='*60)
    
    passed = sum(1 for r in results if r['success'])
    failed = len(results) - passed
    
    print(f"Total Test Suites: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total Duration: {total_duration:.2f}s")
    print()
    
    for result in results:
        status = "✅ PASSED" if result['success'] else "❌ FAILED"
        duration = result.get('duration', 0)
        print(f"{status} {result['file']} ({duration:.2f}s)")
        if not result['success']:
            if 'error' in result:
                print(f"   Error: {result['error']}")
            elif result.get('return_code') != 0:
                print(f"   Return code: {result['return_code']}")
    
    print()
    
    if failed == 0:
        print("🎉 All test suites passed successfully!")
        print("\n📋 Consolidated Test Coverage Summary:")
        print("✅ GameState Unit Tests: Game creation, player management, persistence")
        print("✅ Turn-Based Integration: Complete turn sequences, multi-player rotation") 
        print("✅ Tribal Council Flow: All phases, voting mechanics, elimination")
        print("✅ Card Effects: every registry card type + reactive card mechanics")
        print("✅ Robustness: Error handling, file operations, iOS compatibility")
        print("✅ Edge Cases: Real-world failures, data corruption, network issues")
        print("✅ Phase Enforcement: Negative tests, wrong phase rejections")
        print("✅ Deck Composition: All player counts (3-6), tribal card rules")
        print("✅ Tribal Triggers: Automatic tribal council triggering")
        print("✅ Rules Engine: Card validation, phase logic, dispatch system")
        print("✅ Tie-Break Cascade: official double-elim rules + unclear-vote ladder")
        print("✅ Rocks Expansion: Immunity Idol Necklace + 4 playable challenges")
        print("\n📊 Total Test Count: ~200 comprehensive tests across all game systems")
        
        return 0
    else:
        print(f"❌ {failed} test suite(s) failed. See details above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())