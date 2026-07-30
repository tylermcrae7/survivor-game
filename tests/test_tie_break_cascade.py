#!/usr/bin/env python3
"""
Tie-break and double-elimination cascade tests (F9)

Every case here comes straight from the "Ties" and "Unclear Who Is Voted Out?"
sections of the official rules:

  Single Elimination
    · The Tribal Council Leader gets to decide which of the tied players is voted out.

  Double Elimination
    · If 3 or more players are tied with the most votes, the Leader decides which 2
      of the tied players are voted out.
    · If 2 players are tied with the most votes, both are voted out.
    · If 1 player gets the most votes, and 2 or more are tied with the second most,
      the player with the most votes is voted out first. Then the Leader decides
      which of the tied players is also voted out.
    · If there are only 3 players left and 2 would be eliminated at the same time
      (leaving only 1 player), the Leader decides which is eliminated. Immediately
      begin The Final Tribal Council.

  Unclear who is voted out?
    · First, always choose from the (non-immune) players who got votes. If there
      aren't any... choose from the (non-immune) players who got no votes. Finally,
      if there's not enough of them... choose from the players who played Idols.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState


class TieBreakCascadeTest(unittest.TestCase):
    PLAYER_COUNT = 5

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.engine = self.gs.rules_engine
        self.game_id = self.gs.create_game()
        colors = ["red", "blue", "green", "yellow", "orange", "purple"]
        self.pids = [
            self.gs.add_player(self.game_id, f"Player{i + 1}", colors[i])
            for i in range(self.PLAYER_COUNT)
        ]
        self.gs.start_full_game(self.game_id)
        self.game = self.gs.games[self.game_id]

        # Deterministic hands: a randomly-dealt Goodwill Gamble would change how many
        # votes a player is required to cast.
        for player in self.game["players"].values():
            player["hand"] = [{"type": "camp_raid"}, {"type": "vote"}]
        self.engine.sync_vote_counters(self.game)

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def resolve(self, votes, elimination_type="single", protected=(), idols=()):
        return self.engine.resolve_tribal_eliminations(
            self.game, votes, protected_players=set(protected),
            idol_players=set(idols), elimination_type=elimination_type)

    def alive(self, *pids):
        """Keep only the named players in the game."""
        keep = set(pids)
        for pid, player in self.game["players"].items():
            if pid not in keep:
                player["characterCards"] = 0
                player["isEliminated"] = True

    # ══════════════════ single elimination ══════════════════

    def test_single_clear_majority(self):
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        outcome = self.resolve({a: 3, b: 1, c: 1})

        self.assertEqual(outcome["eliminated"], [a])
        self.assertFalse(outcome["tieBreakNeeded"])
        self.assertEqual(outcome["eliminationsNeeded"], 1)

    def test_single_tie_goes_to_the_leader(self):
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        outcome = self.resolve({a: 2, b: 2, c: 1})

        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [a, b])
        self.assertEqual(outcome["eliminated"], [])

    # ══════════════════ double elimination ══════════════════

    def test_double_two_tied_for_most_both_go_out(self):
        """"If 2 players are tied with the most votes, both are voted out." """
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        outcome = self.resolve({a: 2, b: 2, c: 1}, elimination_type="double")

        self.assertFalse(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["eliminated"], [a, b])

    def test_double_three_tied_for_most_leader_picks_two(self):
        """"If 3 or more players are tied with the most votes, the Leader decides which 2." """
        a, b, c, d = self.pids[0], self.pids[1], self.pids[2], self.pids[3]
        outcome = self.resolve({a: 2, b: 2, c: 2, d: 1}, elimination_type="double")

        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [a, b, c])
        self.assertEqual(outcome["eliminated"], [])
        self.assertEqual(outcome["eliminationsNeeded"], 2)

    def test_double_clear_first_and_clear_second_both_go_out(self):
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        outcome = self.resolve({a: 3, b: 2, c: 1}, elimination_type="double")

        self.assertFalse(outcome["tieBreakNeeded"])
        self.assertEqual(outcome["eliminated"], [a, b])

    def test_double_clear_first_then_tie_for_second(self):
        """
        "If 1 player gets the most votes, and 2 or more are tied with the second most,
        the player with the most votes is voted out first. Then the Tribal Council
        Leader decides which of the tied players is also voted out."
        """
        a, b, c, d = self.pids[0], self.pids[1], self.pids[2], self.pids[3]
        outcome = self.resolve({a: 3, b: 1, c: 1, d: 1}, elimination_type="double")

        self.assertEqual(outcome["eliminated"], [a])
        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [b, c, d])
        self.assertEqual(outcome["eliminationsNeeded"], 2)

    def test_double_only_one_player_got_votes(self):
        """The second vote-out falls to the unclear-who-is-voted-out ladder."""
        a = self.pids[0]
        outcome = self.resolve({a: 2}, elimination_type="double")

        self.assertEqual(outcome["eliminated"], [a])
        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertNotIn(a, outcome["tiedPlayers"])
        self.assertCountEqual(outcome["tiedPlayers"], self.pids[1:])

    # ══════════════════ never leave a single player ══════════════════

    def test_double_at_three_players_on_last_cards_reduces_to_one(self):
        """
        "If there are only 3 players left and 2 players would be eliminated at the
        same time (leaving you with only 1 player left in the game), the Tribal
        Council Leader decides which of the tied players is eliminated."
        """
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        self.alive(a, b, c)
        for pid in (a, b, c):
            self.game["players"][pid]["characterCards"] = 1

        outcome = self.resolve({a: 1, b: 1, c: 1}, elimination_type="double")

        self.assertEqual(outcome["eliminationsNeeded"], 1)
        self.assertTrue(outcome["finalTribalAfter"])
        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [a, b, c])

    def test_double_at_three_players_with_spare_cards_still_eliminates_two(self):
        """With 2 character cards each, a double elim doesn't threaten the count."""
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        self.alive(a, b, c)

        outcome = self.resolve({a: 2, b: 2, c: 1}, elimination_type="double")

        self.assertEqual(outcome["eliminationsNeeded"], 2)
        self.assertFalse(outcome["finalTribalAfter"])
        self.assertCountEqual(outcome["eliminated"], [a, b])

    # ══════════════════ unclear who is voted out ══════════════════

    def test_ladder_prefers_non_immune_players_with_votes(self):
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        # a and b tied; c has no votes and must not be a candidate
        outcome = self.resolve({a: 1, b: 1})

        self.assertCountEqual(outcome["tiedPlayers"], [a, b])
        self.assertNotIn(c, outcome["tiedPlayers"])

    def test_ladder_falls_back_to_players_without_votes(self):
        idol_player = self.pids[0]
        outcome = self.resolve({}, protected=[idol_player], idols=[idol_player])

        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertNotIn(idol_player, outcome["tiedPlayers"])
        self.assertCountEqual(outcome["tiedPlayers"], self.pids[1:])

    def test_ladder_reaches_idol_players_only_as_a_last_resort(self):
        a, b = self.pids[0], self.pids[1]
        self.alive(a, b)
        outcome = self.resolve({}, protected=[a, b], idols=[a, b])

        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [a, b])

    def test_forced_outcome_when_the_ladder_has_exactly_enough(self):
        a, b = self.pids[0], self.pids[1]
        self.alive(a, b, self.pids[2])
        # Two idol players plus one non-immune with no votes -> forced choice of 1
        outcome = self.resolve({}, protected=[a, b], idols=[a, b])

        self.assertFalse(outcome["tieBreakNeeded"])
        self.assertEqual(outcome["eliminated"], [self.pids[2]])

    # ══════════════════ end-to-end through the server ══════════════════

    def test_leader_breaks_a_single_elimination_tie_end_to_end(self):
        a, b = self.pids[0], self.pids[1]
        self.gs._trigger_tribal_council(self.game, "single", drawer_id=self.pids[4])
        self.gs.start_voting(self.game_id, "elimination")

        # 2 votes for a, 2 for b, and b's own vote for a... arranged as a clean 2-2
        ballots = {self.pids[0]: b, self.pids[1]: a, self.pids[2]: a, self.pids[3]: b,
                   self.pids[4]: self.pids[2]}
        for voter, target in ballots.items():
            res = self.gs.cast_vote(self.game_id, voter, [{"targetId": target, "votes": 1}])
            self.assertTrue(res["success"], res.get("message"))

        reveal = self.gs.reveal_votes(self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        current_vote = self.game["currentVote"]
        self.assertTrue(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["tiedPlayers"], [a, b])

        # Only the Council Leader may break it
        bad = self.gs.tie_break(self.game_id, leaderId=self.pids[0], chosenId=a)
        self.assertFalse(bad["success"])
        self.assertIn("Only the tribal council leader", bad["message"])

        # ...and only among the tied players
        bad = self.gs.tie_break(self.game_id, leaderId=self.pids[4], chosenId=self.pids[3])
        self.assertFalse(bad["success"])

        good = self.gs.tie_break(self.game_id, leaderId=self.pids[4], chosenId=a)
        self.assertTrue(good["success"], good.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertEqual(current_vote["eliminated"], [a])

        done = self.gs.complete_tribal(self.game_id)
        self.assertTrue(done["success"], done.get("message"))
        self.assertEqual(self.game["players"][a]["characterCards"], 1)

    def test_leader_picks_two_across_two_calls(self):
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        leader = self.pids[4]
        self.gs._trigger_tribal_council(self.game, "double", drawer_id=leader)
        current_vote = self.game["currentVote"]

        # Hand-set a 3-way tie for most votes
        current_vote["phase"] = "voting"
        # Full Voting Box: everyone appears (b and c pass with empty ballots)
        current_vote["votes"] = {
            self.pids[3]: {a: 1},
            leader: {b: 1},
            a: {c: 1},
            b: {}, c: {},
        }
        reveal = self.gs.reveal_votes(self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        self.assertTrue(current_vote["tieBreakNeeded"])
        self.assertEqual(current_vote["eliminationsNeeded"], 2)

        first = self.gs.tie_break(self.game_id, leaderId=leader, chosenId=a)
        self.assertTrue(first["success"], first.get("message"))
        self.assertTrue(current_vote["tieBreakNeeded"], "one more pick still owed")
        self.assertEqual(first["picksRemaining"], 1)

        second = self.gs.tie_break(self.game_id, leaderId=leader, chosenId=b)
        self.assertTrue(second["success"], second.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["eliminated"], [a, b])

    def test_enhanced_tie_break_accepts_both_picks_at_once(self):
        a, b, c = self.pids[0], self.pids[1], self.pids[2]
        leader = self.pids[4]
        self.gs._trigger_tribal_council(self.game, "double", drawer_id=leader)
        current_vote = self.game["currentVote"]
        current_vote["phase"] = "voting"
        # Full Voting Box: everyone appears (b and c pass with empty ballots)
        current_vote["votes"] = {
            self.pids[3]: {a: 1},
            leader: {b: 1},
            a: {c: 1},
            b: {}, c: {},
        }
        self.gs.reveal_votes(self.game_id)

        result = self.gs.enhanced_tie_break(self.game_id, leaderId=leader, chosenIds=[a, c])
        self.assertTrue(result["success"], result.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["eliminated"], [a, c])


if __name__ == '__main__':
    print("⚖️  Testing tie-break & double-elimination cascade")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TieBreakCascadeTest)
    result = unittest.TextTestRunner(verbosity=2, buffer=True).run(suite)

    print(f"\n📋 Tie-break Test Summary:")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    for test, _ in result.failures:
        print(f"  FAIL: {test}")
    for test, _ in result.errors:
        print(f"  ERROR: {test}")

    success = not result.failures and not result.errors
    print(f"\n🎉 All tie-break cascade tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
