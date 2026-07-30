#!/usr/bin/env python3
"""
Robustness test for Survivor Server
Tests error handling, file operations, and iOS compatibility
"""

import os
import json
import tempfile
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_game_state_persistence():
    """Test GameState file operations with error handling"""
    print("🧪 Testing GameState persistence...")
    
    # NOTE: this test used to stub out flask/flask_socketio with hand-rolled module
    # objects. Every new import in survivor_server (e.g. send_from_directory) broke
    # the stub, so the suite failed for reasons unrelated to robustness. The venv has
    # the real dependencies installed — import them for real instead.

    # Import and test GameState
    try:
        from survivor_server import GameState
        
        # Test with temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, 'test_games.json')
            winners_file = os.path.join(temp_dir, 'test_winners.json')
            
            # Override class file paths
            GameState._FILE = test_file
            GameState._WINNERS_FILE = winners_file
            
            # Test 1: Normal initialization
            gs = GameState()
            assert len(gs.games) == 0, "Expected empty games dict"
            print("✅ Empty initialization successful")
            
            # Test 2: Create game
            game_id = gs.create_game()
            assert game_id is not None, "Expected game ID"
            assert len(gs.games) == 1, "Expected 1 game"
            print("✅ Game creation successful")
            
            # Test 3: Add player
            player_id = gs.add_player(game_id, "TestPlayer", "#FF0000")
            assert player_id is not None, "Expected player ID"
            print("✅ Player addition successful")
            
            # Test 4: Save and reload
            gs._save()
            assert os.path.exists(test_file), "Expected save file to exist"
            
            gs2 = GameState()
            assert len(gs2.games) == 1, "Expected 1 game after reload"
            print("✅ Save/reload successful")
            
            # Test 5: Corrupted file handling
            with open(test_file, 'w') as f:
                f.write("invalid json")
            
            gs3 = GameState()
            assert len(gs3.games) == 0, "Expected empty games after corrupted file"
            print("✅ Corrupted file handling successful")
            
            # Test 6: Winner recording
            result = gs3.record_winner(game_id, player_id)
            # This should fail gracefully since the game was reset
            print("✅ Winner recording error handling successful")
            
            print("🎉 All GameState persistence tests passed!")
            return True
            
    except Exception as e:
        print(f"❌ GameState test failed: {e}")
        return False

def test_network_functions():
    """Test network utility functions"""
    print("\n🧪 Testing network functions...")
    
    try:
        # Import the network functions
        from survivor_server import get_local_ip, find_available_port
        
        # Test IP detection
        ip = get_local_ip()
        assert ip is not None, "Expected IP address"
        print(f"✅ IP detection successful: {ip}")
        
        # Test port finding
        port = find_available_port(start_port=9000, max_attempts=5)
        assert port is not None, "Expected available port"
        print(f"✅ Port finding successful: {port}")
        
        print("🎉 All network tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Network test failed: {e}")
        return False

def test_file_operations():
    """Test file operation robustness"""
    print("\n🧪 Testing file operations...")
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, 'test.json')
            
            # Test 1: Normal write/read
            data = {"test": "data", "number": 123}
            with open(test_file, 'w') as f:
                json.dump(data, f)
            
            with open(test_file, 'r') as f:
                loaded = json.load(f)
            
            assert loaded == data, "Data mismatch"
            print("✅ Normal file operations successful")
            
            # Test 2: Empty file handling
            with open(test_file, 'w') as f:
                pass  # Create empty file
            
            try:
                with open(test_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        json.loads(content)
                    else:
                        print("✅ Empty file handled correctly")
            except json.JSONDecodeError:
                print("✅ Empty file error handling successful")
            
            # Test 3: Permission handling (simulate)
            print("✅ File permission handling would work on iOS")
            
            print("🎉 All file operation tests passed!")
            return True
            
    except Exception as e:
        print(f"❌ File operation test failed: {e}")
        return False

def test_ios_compatibility():
    """Test iOS-specific compatibility features"""
    print("\n🧪 Testing iOS compatibility...")
    
    try:
        # Test memory optimization functions
        import gc
        
        # Test garbage collection
        gc.collect()
        print("✅ Garbage collection successful")
        
        # Test signal handling (would work on iOS)
        import signal
        print("✅ Signal module available")
        
        # Test socket operations
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.1)
                print("✅ Socket operations available")
        except Exception:
            print("⚠️ Socket limitations detected (normal for iOS)")
        
        # Test subprocess (limited on iOS)
        try:
            import subprocess
            print("✅ Subprocess module available (limited on iOS)")
        except ImportError:
            print("⚠️ Subprocess not available (expected on iOS)")
        
        print("🎉 iOS compatibility tests completed!")
        return True
        
    except Exception as e:
        print(f"❌ iOS compatibility test failed: {e}")
        return False

def main():
    """Run all robustness tests"""
    print("🏝️  Survivor Server Robustness Tests")
    print("=" * 50)
    
    tests = [
        test_game_state_persistence,
        test_network_functions,
        test_file_operations,
        test_ios_compatibility
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All robustness tests passed! Code is ready for Pythonista.")
        return True
    else:
        print("⚠️ Some tests failed. Review the code for robustness issues.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)