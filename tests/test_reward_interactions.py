#!/usr/bin/env python3
"""
Reward Challenge interaction tests — Do Or Die, Power Pair, It's A Numbers Game.

These three cards are bluffing contests, so every pick must come from a real
player. Each case here is checked against the official Survival Guide text
(quoted in interactions.py).
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState


class InteractionTestBase(unittest.TestCase):
    PLAYER_COUNT = 4

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.game_id = self.gs.create_game()
        colors = ["red", "blue", "green", "yellow", "orange", "purple"]
        self.pids = [
            self.gs.add_player(self.game_id, f"Player{i + 1}", colors[i])
            for i in range(self.PLAYER_COUNT)
        ]
        self.gs.start_full_game(self.game_id)
        self.game = self.gs.games[self.game_id]

        # Deterministic hands, everyone past the mandatory steal
        for player in self.game["players"].values():
            player["hand"] = [
                {"type": "camp_raid"}, {"type": "inheritance"},
                {"type": "the_spy_shack"}, {"type": "vote"},
            ]
            player["hasStolen"] = True
        self.gs.rules_engine.sync_vote_counters(self.game)

        self.me = self.pids[0]
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(self.me)

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── helpers ──

    def hand(self, pid):
        return self.game["players"][pid]["hand"]

    def give_card(self, pid, card_type):
        self.hand(pid).append({"type": card_type})
        return len(self.hand(pid)) - 1

    def play(self, pid, card_type, **params):
        idx = next(i for i, c in enumerate(self.hand(pid)) if c["type"] == card_type)
        return self.gs.play_card(self.game_id, pid, idx, params or None)

    def act(self, pid, action, value=None):
        return self.gs.interaction_action(self.game_id, playerId=pid, action=action, value=value)


class TestDoOrDie(InteractionTestBase):
    """"Pick any player... If you tie, you each swap 1 card of your choice.
    BUT if either player wins, they steal 2 random cards from the loser." """

    def start(self, choice="rock", opponent=None):
        opponent = opponent or self.pids[1]
        self.give_card(self.me, "reward_challenge_do_or_die")
        result = self.play(self.me, "reward_challenge_do_or_die",
                           targetId=opponent, choice=choice)
        self.assertTrue(result["success"], result.get("message"))
        self.assertTrue(result["interaction_started"])
        return opponent

    def test_play_without_a_throw_keeps_the_card(self):
        self.give_card(self.me, "reward_challenge_do_or_die")
        result = self.play(self.me, "reward_challenge_do_or_die", targetId=self.pids[1])
        self.assertFalse(result["success"])
        self.assertIn("secret throw", result["message"])
        self.assertIn("reward_challenge_do_or_die",
                      [c["type"] for c in self.hand(self.me)])

    def test_opponent_makes_a_real_throw_and_winner_steals_two(self):
        opponent = self.start(choice="rock")
        it = self.game["interaction"]
        self.assertEqual(it["awaiting"], [opponent], "only the opponent still owes a throw")
        self.assertNotIn("_picks", self.gs.get_game_state(self.game_id)["interaction"],
                         "the initiator's throw must stay secret")

        my_before = len(self.hand(self.me))
        opp_before = len(self.hand(opponent))

        result = self.act(opponent, "pick", "scissors")   # rock beats scissors
        self.assertTrue(result["success"], result.get("message"))

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "complete")
        self.assertEqual(it["picks"], {self.me: "rock", opponent: "scissors"})
        self.assertEqual(len(self.hand(self.me)), my_before + 2)
        self.assertEqual(len(self.hand(opponent)), opp_before - 2)

    def test_loser_can_be_the_initiator(self):
        opponent = self.start(choice="paper")
        my_before = len(self.hand(self.me))
        self.act(opponent, "pick", "scissors")            # scissors beats paper
        self.assertEqual(len(self.hand(self.me)), my_before - 2)

    def test_tie_swaps_a_card_of_each_players_choice(self):
        opponent = self.start(choice="rock")
        self.act(opponent, "pick", "rock")

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "give")
        self.assertEqual(it["giveReason"], "swap")
        self.assertCountEqual(it["awaiting"], [self.me, opponent])

        # I give my camp_raid (index 0); they give their inheritance (index 1)
        my_gave = self.hand(self.me)[0]["type"]
        their_gave = self.hand(opponent)[1]["type"]
        self.assertTrue(self.act(self.me, "give", 0)["success"])
        self.assertEqual(self.game["interaction"]["awaiting"], [opponent])
        self.assertTrue(self.act(opponent, "give", 1)["success"])

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "complete")
        self.assertIn(their_gave, [c["type"] for c in self.hand(self.me)])
        self.assertIn(my_gave, [c["type"] for c in self.hand(opponent)])

    def test_outsiders_cannot_pick(self):
        self.start()
        result = self.act(self.pids[2], "pick", "rock")
        self.assertFalse(result["success"])
        self.assertIn("not part of", result["message"])

    def test_turn_actions_blocked_until_resolved(self):
        self.start()
        draw = self.gs.draw_card(self.game_id, self.me)
        self.assertFalse(draw["success"])
        self.assertIn("Do Or Die", draw["message"])

        advance = self.gs.advance_turn(self.game_id)
        self.assertFalse(advance["success"])

    def test_advance_turn_clears_a_completed_interaction(self):
        opponent = self.start(choice="rock")
        self.act(opponent, "pick", "scissors")
        self.assertEqual(self.game["interaction"]["phase"], "complete")

        self.gs.draw_card(self.game_id, self.me)
        result = self.gs.advance_turn(self.game_id)
        self.assertTrue(result["success"], result.get("message"))
        self.assertIsNone(self.game["interaction"])


class TestPowerPair(InteractionTestBase):
    """"Pick 2 other players... exactly 2 match -> steal from the 3rd;
    all match -> each discards 1; all differ -> play again." """

    def start(self, a=None, b=None):
        a, b = a or self.pids[1], b or self.pids[2]
        self.give_card(self.me, "reward_challenge_power_pair")
        result = self.play(self.me, "reward_challenge_power_pair", targetIds=[a, b])
        self.assertTrue(result["success"], result.get("message"))
        return a, b

    def test_requires_two_distinct_other_players(self):
        self.give_card(self.me, "reward_challenge_power_pair")
        result = self.play(self.me, "reward_challenge_power_pair")
        self.assertFalse(result["success"])

        result = self.play(self.me, "reward_challenge_power_pair",
                           targetIds=[self.pids[1], self.pids[1]])
        self.assertFalse(result["success"])

        result = self.play(self.me, "reward_challenge_power_pair",
                           targetIds=[self.me, self.pids[1]])
        self.assertFalse(result["success"])
        self.assertIn("reward_challenge_power_pair",
                      [c["type"] for c in self.hand(self.me)], "card must survive bad params")

    def test_all_three_pick_secretly(self):
        a, b = self.start()
        it = self.game["interaction"]
        self.assertCountEqual(it["participants"], [self.me, a, b])
        self.assertCountEqual(it["awaiting"], [self.me, a, b])

        self.act(self.me, "pick", 2)
        public = self.gs.get_game_state(self.game_id)["interaction"]
        self.assertNotIn("_picks", public)
        self.assertEqual(public["picks"], {}, "no reveal until everyone has thrown")

    def test_exactly_two_matching_steal_from_the_third(self):
        a, b = self.start()
        self.act(self.me, "pick", 2)
        self.act(a, "pick", 2)
        odd_before = len(self.hand(b))
        me_before = len(self.hand(self.me))
        self.act(b, "pick", 3)

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "complete")
        self.assertEqual(len(self.hand(b)), odd_before - 2, "the odd one out loses a card to each")
        self.assertEqual(len(self.hand(self.me)), me_before + 1)

    def test_all_matching_means_everyone_discards_a_chosen_card(self):
        a, b = self.start()
        for pid in (self.me, a, b):
            self.act(pid, "pick", 1)

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "give")
        self.assertEqual(it["giveReason"], "discard")
        self.assertCountEqual(it["awaiting"], [self.me, a, b])

        sizes = {p: len(self.hand(p)) for p in (self.me, a, b)}
        for pid in (self.me, a, b):
            self.assertTrue(self.act(pid, "give", 0)["success"])

        self.assertEqual(self.game["interaction"]["phase"], "complete")
        for pid in (self.me, a, b):
            self.assertEqual(len(self.hand(pid)), sizes[pid] - 1)

    def test_all_different_replays_the_round(self):
        a, b = self.start()
        self.act(self.me, "pick", 1)
        self.act(a, "pick", 2)
        self.act(b, "pick", 3)

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "picking")
        self.assertEqual(it["round"], 2)
        self.assertCountEqual(it["awaiting"], [self.me, a, b])
        self.assertEqual(it["lastRound"]["picks"][self.me], 1, "previous round is revealed")

    def test_fingers_must_be_one_to_three(self):
        self.start()
        self.assertFalse(self.act(self.me, "pick", 4)["success"])
        self.assertFalse(self.act(self.me, "pick", 0)["success"])
        self.assertFalse(self.act(self.me, "pick", "banana")["success"])
        self.assertTrue(self.act(self.me, "pick", 3)["success"])
        self.assertFalse(self.act(self.me, "pick", 2)["success"], "no changing your throw")


class TestNumbersGame(InteractionTestBase):
    """"All players (including you) show 1-5 fingers. The lowest UNIQUE number
    steals 2 random cards from any player. Repeat until a single winner." """

    def start(self):
        self.give_card(self.me, "reward_challenge_its_a_numbers_game")
        result = self.play(self.me, "reward_challenge_its_a_numbers_game")
        self.assertTrue(result["success"], result.get("message"))

    def test_every_living_player_participates(self):
        self.game["players"][self.pids[3]]["characterCards"] = 0
        self.game["players"][self.pids[3]]["isEliminated"] = True
        self.start()
        it = self.game["interaction"]
        self.assertCountEqual(it["participants"], self.pids[:3])
        self.assertNotIn(self.pids[3], it["participants"])

    def test_lowest_unique_wins_and_chooses_a_victim(self):
        self.start()
        picks = {self.pids[0]: 2, self.pids[1]: 2, self.pids[2]: 3, self.pids[3]: 5}
        for pid, n in picks.items():
            self.act(pid, "pick", n)

        it = self.game["interaction"]
        # 2 is duplicated; 3 is the lowest unique
        self.assertEqual(it["phase"], "choose_victim")
        self.assertEqual(it["winnerId"], self.pids[2])
        self.assertEqual(it["awaiting"], [self.pids[2]])

        # Only the winner picks, and not themself
        self.assertFalse(self.act(self.pids[0], "steal_from", self.pids[1])["success"])
        self.assertFalse(self.act(self.pids[2], "steal_from", self.pids[2])["success"])

        victim_before = len(self.hand(self.pids[0]))
        winner_before = len(self.hand(self.pids[2]))
        result = self.act(self.pids[2], "steal_from", self.pids[0])
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.game["interaction"]["phase"], "complete")
        self.assertEqual(len(self.hand(self.pids[0])), victim_before - 2)
        self.assertEqual(len(self.hand(self.pids[2])), winner_before + 2)

    def test_no_unique_number_replays(self):
        self.start()
        for pid in self.pids[:2]:
            self.act(pid, "pick", 2)
        for pid in self.pids[2:]:
            self.act(pid, "pick", 4)

        it = self.game["interaction"]
        self.assertEqual(it["phase"], "picking")
        self.assertEqual(it["round"], 2)
        self.assertCountEqual(it["awaiting"], self.pids)

    def test_needs_at_least_two_players(self):
        for pid in self.pids[1:]:
            self.game["players"][pid]["characterCards"] = 0
            self.game["players"][pid]["isEliminated"] = True
        self.give_card(self.me, "reward_challenge_its_a_numbers_game")
        result = self.play(self.me, "reward_challenge_its_a_numbers_game")
        self.assertFalse(result["success"])
        self.assertIn("at least 2", result["message"])


class TestSpyShack(InteractionTestBase):
    """"Look at any player's cards and take one." """

    def test_takes_the_chosen_card(self):
        victim = self.pids[1]
        self.hand(victim)[:] = [{"type": "immunity_idol"}, {"type": "camp_raid"}, {"type": "vote"}]
        self.give_card(self.me, "the_spy_shack")

        result = self.play(self.me, "the_spy_shack", targetId=victim, takeIndex=0)
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn("took", result["message"])

        self.assertIn("immunity_idol", [c["type"] for c in self.hand(self.me)])
        self.assertNotIn("immunity_idol", [c["type"] for c in self.hand(victim)])
        self.assertEqual(len(self.hand(victim)), 2)

    def test_missing_take_index_keeps_the_card(self):
        victim = self.pids[1]
        self.give_card(self.me, "the_spy_shack")
        result = self.play(self.me, "the_spy_shack", targetId=victim)
        self.assertFalse(result["success"])
        self.assertIn("takeIndex", result["message"])
        self.assertIn("the_spy_shack", [c["type"] for c in self.hand(self.me)])

    def test_out_of_range_take_index_rejected(self):
        victim = self.pids[1]
        self.give_card(self.me, "the_spy_shack")
        result = self.play(self.me, "the_spy_shack", targetId=victim, takeIndex=99)
        self.assertFalse(result["success"])

    def test_cannot_take_the_vote_card(self):
        """
        The Vote Card is not part of the hand The Spy Shack rifles through — it is
        dealt outside the deck and returned each Tribal. Only Control The Vote
        ("take any player's Vote Card") reaches it, so the vote economy is
        untouched here even though the spy got to look at everything.
        """
        victim = self.pids[1]
        vote_index = next(i for i, c in enumerate(self.hand(victim)) if c["type"] == "vote")
        victim_votes_before = self.game["players"][victim]["voteCards"]
        my_votes_before = self.game["players"][self.me]["voteCards"]
        self.give_card(self.me, "the_spy_shack")

        result = self.play(self.me, "the_spy_shack", targetId=victim, takeIndex=vote_index)
        self.assertTrue(result["success"], result.get("message"))
        self.assertIn("Vote Card", result["message"])

        self.assertEqual(self.game["players"][victim]["voteCards"], victim_votes_before)
        self.assertEqual(self.game["players"][self.me]["voteCards"], my_votes_before)
        self.assertIn("vote", [c["type"] for c in self.hand(victim)])


class TestRewardOutcomeRedaction(InteractionTestBase):
    """
    A Reward Challenge outcome becomes the shared prompt, the interaction log,
    and the event log on every phone. When the take is held at the Sorry For
    You gate, that shared copy must not confirm what the target is holding —
    the table learns only that the raid is hanging; the holder's own device
    gets the reactive choice from the pending_theft window itself.
    """

    def assert_outcome_stays_silent(self, result, holder_name):
        it = self.game["interaction"]
        self.assertEqual(it["phase"], "complete")
        self.assertNotIn("Sorry For You", it["prompt"])
        for line in it["log"]:
            self.assertNotIn("Sorry For You", line)
        self.assertNotIn("Sorry For You", result.get("message", ""))
        self.assertNotIn("Sorry For You", result.get("log_message") or "")
        # The table still learns who everyone is waiting on…
        self.assertIn(holder_name, it["prompt"])
        self.assertIn("hangs in the air", it["prompt"])
        # …and the reactive window really did open for the holder
        pending = self.game.get("pending_theft") or {}
        self.assertTrue(pending.get("reactive_window_open"))

    def test_do_or_die_does_not_announce_the_losers_answer(self):
        opponent = self.pids[1]
        self.hand(opponent).append({"type": "sorry_for_you"})
        self.give_card(self.me, "reward_challenge_do_or_die")
        self.play(self.me, "reward_challenge_do_or_die",
                  targetId=opponent, choice="rock")

        result = self.act(opponent, "pick", "scissors")   # rock wins, take gated
        self.assertTrue(result["success"], result.get("message"))
        self.assert_outcome_stays_silent(result, "Player2")

    def test_power_pair_does_not_announce_the_odd_ones_answer(self):
        a, b = self.pids[1], self.pids[2]
        self.hand(b).append({"type": "sorry_for_you"})
        self.give_card(self.me, "reward_challenge_power_pair")
        self.play(self.me, "reward_challenge_power_pair", targetIds=[a, b])

        self.act(self.me, "pick", 2)
        self.act(a, "pick", 2)
        result = self.act(b, "pick", 3)                   # b is the odd one out
        self.assertTrue(result["success"], result.get("message"))
        self.assert_outcome_stays_silent(result, "Player3")

    def test_numbers_game_does_not_announce_the_victims_answer(self):
        victim = self.pids[0]
        self.hand(victim).append({"type": "sorry_for_you"})
        self.give_card(self.me, "reward_challenge_its_a_numbers_game")
        self.play(self.me, "reward_challenge_its_a_numbers_game")

        picks = {self.pids[0]: 2, self.pids[1]: 2, self.pids[2]: 3, self.pids[3]: 5}
        for pid, n in picks.items():
            self.act(pid, "pick", n)                      # pids[2] wins with 3
        result = self.act(self.pids[2], "steal_from", victim)
        self.assertTrue(result["success"], result.get("message"))
        self.assert_outcome_stays_silent(result, "Player1")


class TestInteractionHygiene(InteractionTestBase):
    def test_only_one_interaction_at_a_time(self):
        self.give_card(self.me, "reward_challenge_do_or_die")
        self.play(self.me, "reward_challenge_do_or_die", targetId=self.pids[1], choice="rock")

        self.give_card(self.me, "reward_challenge_its_a_numbers_game")
        result = self.play(self.me, "reward_challenge_its_a_numbers_game")
        self.assertFalse(result["success"])

    def test_secret_picks_never_reach_clients(self):
        self.give_card(self.me, "reward_challenge_its_a_numbers_game")
        self.play(self.me, "reward_challenge_its_a_numbers_game")
        self.act(self.me, "pick", 3)

        public = self.gs.get_game_state(self.game_id)["interaction"]
        self.assertFalse([k for k in public if k.startswith("_")])
        self.assertEqual(public["picks"], {})
        self.assertNotIn(self.me, public["awaiting"], "who has acted is public")

    def test_dismiss_requires_completion(self):
        self.give_card(self.me, "reward_challenge_do_or_die")
        self.play(self.me, "reward_challenge_do_or_die", targetId=self.pids[1], choice="rock")
        result = self.act(self.me, "dismiss")
        self.assertFalse(result["success"])

        self.act(self.pids[1], "pick", "scissors")
        result = self.act(self.me, "dismiss")
        self.assertTrue(result["success"], result.get("message"))
        self.assertIsNone(self.game["interaction"])

    def test_reset_game_clears_interactions(self):
        self.give_card(self.me, "reward_challenge_do_or_die")
        self.play(self.me, "reward_challenge_do_or_die", targetId=self.pids[1], choice="rock")
        self.gs.reset_game(self.game_id)
        self.assertIsNone(self.game["interaction"])


if __name__ == '__main__':
    print("🎲 Testing Reward Challenge interactions (official rules)")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_class in (TestDoOrDie, TestPowerPair, TestNumbersGame,
                       TestSpyShack, TestRewardOutcomeRedaction,
                       TestInteractionHygiene):
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    result = unittest.TextTestRunner(verbosity=2, buffer=True).run(suite)

    print(f"\n📋 Reward Interaction Test Summary:")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    for test, _ in result.failures:
        print(f"  FAIL: {test}")
    for test, _ in result.errors:
        print(f"  ERROR: {test}")

    success = not result.failures and not result.errors
    print(f"\n🎉 All reward interaction tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
