#!/usr/bin/env python3
"""
Survivor: Let's Go To Rocks — combined-mode expansion tests

Covers the Immunity Idol Necklace framework and all four digitally-playable
Challenges, against the official Challenge Survival Guide.
"""

import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState
from challenges import CHALLENGE_DEFINITIONS, challenge_engine


class RocksTestBase(unittest.TestCase):
    PLAYER_COUNT = 4

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.game_id = self.gs.create_game(deckMode="official", expansion=True)
        colors = ["red", "blue", "green", "yellow", "orange", "purple"]
        self.player_ids = [
            self.gs.add_player(self.game_id, f"Player{i + 1}", colors[i])
            for i in range(self.PLAYER_COUNT)
        ]
        self.gs.start_full_game(self.game_id)
        self.game = self.gs.games[self.game_id]

        for player in self.game["players"].values():
            player["hand"] = [{"type": "camp_raid"}, {"type": "vote"}]
            player["hasStolen"] = True
        self.gs.rules_engine.sync_vote_counters(self.game)

        self.starter = self.player_ids[0]
        self.game["currentTurnIndex"] = self.game["turnOrder"].index(self.starter)

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── helpers ──

    def start_challenge(self, card_type, starter=None):
        starter = starter or self.starter
        self.game["players"][starter]["hand"].append({"type": card_type})
        idx = len(self.game["players"][starter]["hand"]) - 1
        result = self.gs.play_card(self.game_id, starter, idx)
        self.assertTrue(result["success"], result.get("message"))
        return result

    def act(self, action, value=None, player=None):
        challenge = self.game["challenge"]
        player = player or challenge["currentPlayerId"]
        return self.gs.challenge_action(self.game_id, playerId=player,
                                       action=action, value=value)

    def play_out(self, chooser=None, max_steps=400):
        """
        Drive the active challenge to completion, choosing legal actions.
        `chooser(challenge)` may return (action, value); otherwise the first legal
        action is taken with a sensible value.
        """
        steps = 0
        while self.game.get("challenge") and self.game["challenge"]["phase"] != "complete":
            steps += 1
            self.assertLess(steps, max_steps, "challenge failed to terminate")
            challenge = self.game["challenge"]
            choice = chooser(challenge) if chooser else None
            if choice:
                action, value = choice
            else:
                action = challenge["actions"][0]
                value = None
                if action == "bid":
                    next_bid = challenge["currentBid"] + 1
                    if next_bid > challenge.get("maxBid", next_bid) and "pass" in challenge["actions"]:
                        action, value = "pass", None
                    else:
                        value = next_bid
                elif action == "pull" and challenge["type"] == "lowest_score_loses":
                    value = 1
                elif action == "steal":
                    value = challenge["stealTargets"][0]
            result = self.act(action, value)
            self.assertTrue(result["success"], result.get("message"))
        return self.game["challenge"]


class TestNecklace(RocksTestBase):
    """Immunity Idol Necklace behaviour."""

    def test_challenge_winner_wears_the_necklace(self):
        self.start_challenge("challenge_highest_bidder")
        challenge = self.play_out()

        self.assertIsNotNone(challenge["winnerId"])
        self.assertEqual(self.game["necklaceHolder"], challenge["winnerId"])

    def test_necklace_wearer_cannot_be_voted_for(self):
        wearer = self.player_ids[1]
        self.game["necklaceHolder"] = wearer

        self.gs._trigger_tribal_council(self.game, "single")
        self.gs.start_voting(self.game_id, "elimination")

        result = self.gs.cast_vote(self.game_id, self.player_ids[0],
                                   [{"targetId": wearer, "votes": 1}])
        self.assertFalse(result["success"])
        self.assertIn("Immunity Idol Necklace", result["message"])

    def test_necklace_returns_to_the_table_when_tribal_ends(self):
        wearer = self.player_ids[1]
        target = self.player_ids[2]
        self.game["necklaceHolder"] = wearer

        self.gs._trigger_tribal_council(self.game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        for voter in self.player_ids:
            vote_for = target if voter != target else self.player_ids[0]
            self.gs.cast_vote(self.game_id, voter, [{"targetId": vote_for, "votes": 1}])
        self.gs.reveal_votes(self.game_id)
        result = self.gs.complete_tribal(self.game_id)

        self.assertTrue(result["success"], result.get("message"))
        self.assertIsNone(self.game["necklaceHolder"])

    def test_necklace_wearer_is_only_a_last_resort_tie_break_pick(self):
        """
        The "unclear who is voted out" ladder is: non-immune players with votes, then
        non-immune players without votes, and only then immune players. The Necklace
        wearer counts as immune, so they are excluded while anyone else is available.
        """
        wearer = self.player_ids[1]
        self.game["necklaceHolder"] = wearer

        self.gs._trigger_tribal_council(self.game, "single")
        self.gs.start_voting(self.game_id, "elimination")
        # Simulate a tribal where nobody ended up with votes — every living
        # player passed the box (it must reach everyone before the tally)
        self.game["currentVote"]["votes"] = {
            pid: {} for pid, p in self.game["players"].items()
            if not p.get("isEliminated", False)
        }
        self.gs.reveal_votes(self.game_id)

        current_vote = self.game["currentVote"]
        self.assertTrue(current_vote["tieBreakNeeded"])
        self.assertNotIn(wearer, current_vote["tiedPlayers"],
                         "the wearer is safe while non-immune players are available")
        self.assertEqual(sorted(current_vote["tiedPlayers"]),
                         sorted(p for p in self.player_ids if p != wearer))

    def test_necklace_wearer_is_choosable_when_nobody_else_is_left(self):
        """"...if there's not enough of them, choose from the players who played Idols." """
        wearer = self.player_ids[1]
        self.game["necklaceHolder"] = wearer
        for pid in self.player_ids:
            if pid != wearer:
                self.game["players"][pid]["characterCards"] = 0
                self.game["players"][pid]["isEliminated"] = True

        outcome = self.gs.rules_engine.resolve_tribal_eliminations(
            self.game, {}, protected_players={wearer}, idol_players={wearer},
            elimination_type="single")

        # With only the wearer left in the game there is nothing left to resolve
        self.assertEqual(outcome["eliminationsNeeded"], 0)

        # But if a second non-immune player exists and is also immune, the ladder
        # reaches the last resort tier.
        self.game["players"][self.player_ids[2]]["characterCards"] = 1
        self.game["players"][self.player_ids[2]]["isEliminated"] = False
        outcome = self.gs.rules_engine.resolve_tribal_eliminations(
            self.game, {},
            protected_players={wearer, self.player_ids[2]},
            idol_players={wearer, self.player_ids[2]},
            elimination_type="single")
        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [wearer, self.player_ids[2]])

    def test_second_win_while_necklace_worn_draws_three_cards(self):
        """
        "If someone is already wearing the Immunity Idol Necklace when you win a
        Challenge, you instead get to take 3 random cards from anywhere in the Draw
        Pile. You CAN'T take Tribal Council cards."
        """
        self.game["necklaceHolder"] = self.player_ids[3]

        self.start_challenge("challenge_highest_bidder")
        challenge = self.play_out()
        winner = challenge["winnerId"]

        # Necklace stays with the original wearer
        self.assertEqual(self.game["necklaceHolder"], self.player_ids[3])
        self.assertIn("3 random cards", challenge["log"][-1])

        # Winner drew 3 non-tribal cards
        hand_types = [c["type"] for c in self.game["players"][winner]["hand"]]
        self.assertFalse([t for t in hand_types if t.startswith("tribal_council")])


class TestHighestBidder(RocksTestBase):
    """Setup: 10 Grey Rocks and 1 Purple Rock in the bag."""

    def test_setup_and_first_bidder_must_bid(self):
        self.start_challenge("challenge_highest_bidder")
        challenge = self.game["challenge"]

        self.assertEqual(challenge["bag"], {"grey": 10, "purple": 1})
        self.assertEqual(challenge["currentPlayerId"], self.starter)
        self.assertEqual(challenge["actions"], ["bid"])

        # "The first player each round MUST make a bid."
        result = self.act("pass")
        self.assertFalse(result["success"])
        self.assertIn("not allowed", result["message"])

    def test_bids_must_escalate(self):
        self.start_challenge("challenge_highest_bidder")
        self.assertTrue(self.act("bid", 3)["success"])

        result = self.act("bid", 3)
        self.assertFalse(result["success"])
        self.assertIn("higher than 3", result["message"])
        self.assertTrue(self.act("bid", 4)["success"])

    def test_cannot_bid_more_rocks_than_the_bag_holds(self):
        self.start_challenge("challenge_highest_bidder")
        result = self.act("bid", 12)
        self.assertFalse(result["success"])
        self.assertIn("only 11 rocks", result["message"])

    def test_last_bidder_standing_pulls_their_bid(self):
        self.start_challenge("challenge_highest_bidder")
        self.act("bid", 1)
        for _ in range(self.PLAYER_COUNT - 1):
            self.act("pass")

        challenge = self.game["challenge"]
        self.assertEqual(challenge["phase"], "pulling")
        self.assertEqual(challenge["currentPlayerId"], self.starter)
        self.assertEqual(challenge["pullsRemaining"], 1)
        self.assertEqual(challenge["actions"], ["pull"])

    def test_surviving_your_bid_wins_the_challenge(self):
        random.seed(4)
        self.start_challenge("challenge_highest_bidder")
        self.act("bid", 1)
        for _ in range(self.PLAYER_COUNT - 1):
            self.act("pass")

        # 10 of 11 rocks are grey; retry until a bid of 1 survives
        for _ in range(40):
            challenge = self.game["challenge"]
            if challenge["phase"] == "complete":
                break
            if challenge["phase"] == "bidding":
                self.act("bid", 1)
                for _ in range(len(challenge["order"]) - len(challenge["knockedOut"]) - 1):
                    if self.game["challenge"]["phase"] != "bidding":
                        break
                    self.act("pass")
                continue
            self.act("pull")

        challenge = self.game["challenge"]
        self.assertEqual(challenge["phase"], "complete")
        self.assertIsNotNone(challenge["winnerId"])

    def test_challenge_always_produces_exactly_one_winner(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                self.setUp()
                random.seed(seed)
                self.start_challenge("challenge_highest_bidder")
                challenge = self.play_out()
                self.assertEqual(challenge["phase"], "complete")
                self.assertIsNotNone(challenge["winnerId"])
                self.assertNotIn(challenge["winnerId"], challenge["knockedOut"])


class TestOneNowOrTwoLater(RocksTestBase):
    """Setup: 5 Grey Rocks and 1 Purple Rock in the bag."""

    def test_setup(self):
        self.start_challenge("challenge_1_now_or_2_later")
        challenge = self.game["challenge"]
        self.assertEqual(challenge["bag"], {"grey": 5, "purple": 1})
        self.assertEqual(sorted(challenge["actions"]), ["pass", "pull"])

    def test_passing_forces_two_pulls_next_time(self):
        self.start_challenge("challenge_1_now_or_2_later")
        first = self.game["challenge"]["currentPlayerId"]

        self.assertTrue(self.act("pass")["success"])
        self.assertIn(first, self.game["challenge"]["mustPullTwo"])

        # Everyone else passes; the bag comes back around to `first`
        for _ in range(self.PLAYER_COUNT - 1):
            self.act("pass")

        challenge = self.game["challenge"]
        self.assertEqual(challenge["currentPlayerId"], first)
        self.assertEqual(challenge["actions"], ["pull"], "a forced puller can't pass")

        result = self.act("pass")
        self.assertFalse(result["success"])

    def test_pulled_grey_rocks_stay_on_the_table(self):
        random.seed(1)
        self.start_challenge("challenge_1_now_or_2_later")
        before = self.game["challenge"]["bag"]["grey"] + self.game["challenge"]["bag"]["purple"]
        self.act("pull")
        challenge = self.game["challenge"]
        after = challenge["bag"]["grey"] + challenge["bag"]["purple"]
        if challenge["round"] == 1:  # no purple pulled, so no reset
            self.assertEqual(after, before - 1)
            self.assertEqual(challenge["table"]["grey"], 1)

    def test_purple_rock_knocks_you_out_and_resets_the_round(self):
        self.start_challenge("challenge_1_now_or_2_later")
        # Rig the bag down to the Purple Rock only
        self.game["challenge"]["bag"] = {"grey": 0, "purple": 1}
        victim = self.game["challenge"]["currentPlayerId"]

        result = self.act("pull")
        self.assertTrue(result["success"], result.get("message"))

        challenge = self.game["challenge"]
        self.assertIn(victim, challenge["knockedOut"])
        self.assertEqual(challenge["round"], 2)
        self.assertEqual(challenge["bag"], {"grey": 5, "purple": 1}, "all rocks return to the bag")
        self.assertEqual(challenge["mustPullTwo"], [], "everyone may pull or pass again")
        self.assertNotEqual(challenge["currentPlayerId"], victim)

    def test_last_player_standing_wins(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                self.setUp()
                random.seed(seed)
                self.start_challenge("challenge_1_now_or_2_later")
                challenge = self.play_out()
                self.assertEqual(challenge["phase"], "complete")
                self.assertEqual(len(challenge["knockedOut"]), self.PLAYER_COUNT - 1)
                self.assertNotIn(challenge["winnerId"], challenge["knockedOut"])


class TestLowestScoreLoses(RocksTestBase):
    """Setup: 5 Grey Rocks (+1) and 3 Purple Rocks (-2) in the bag."""

    def test_setup(self):
        self.start_challenge("challenge_lowest_score_loses")
        challenge = self.game["challenge"]
        self.assertEqual(challenge["bag"], {"grey": 5, "purple": 3})
        self.assertEqual(challenge["maxPull"], 8)

    def test_pulls_are_secret_until_the_reveal(self):
        self.start_challenge("challenge_lowest_score_loses")
        self.act("pull", 2)

        # The server keeps secret pulls under a _-prefixed key and strips them
        # from anything a client can see.
        self.assertIn("_secretPulls", self.game["challenge"])
        client_state = self.gs.get_game_state(self.game_id)
        self.assertNotIn("_secretPulls", client_state["challenge"])
        self.assertEqual(client_state["challenge"]["pulls"], {})

    def test_cannot_pull_more_rocks_than_remain(self):
        self.start_challenge("challenge_lowest_score_loses")
        result = self.act("pull", 9)
        self.assertFalse(result["success"])
        self.assertIn("only 8 rocks", result["message"])

        result = self.act("pull", -1)
        self.assertFalse(result["success"])

    def test_an_empty_bag_still_lets_the_turn_pass(self):
        """
        Rocks Guide: "When you get the bag it might be empty - that's fine, just
        pretend to take some Rocks and pass the bag to the next player."

        The first player is allowed to take all 8, so every later seat can meet an
        empty bag. Refusing their turn there strands whoever is holding the bag —
        which is what wedged bot games.
        """
        self.start_challenge("challenge_lowest_score_loses")
        order = list(self.game["challenge"]["pending"])
        self.assertGreaterEqual(len(order), 3)

        # The opener empties the bag entirely
        self.act("pull", 8, player=order[0])
        self.assertEqual(self.game["challenge"]["bag"], {"grey": 0, "purple": 0})
        self.assertEqual(self.game["challenge"]["maxPull"], 0)

        # The next seat still gets to take their turn, even asking for rocks
        # that aren't there — it resolves as a pull of nothing.
        result = self.act("pull", 2, player=order[1])
        self.assertTrue(result["success"], result.get("message"))
        self.assertNotEqual(self.game["challenge"]["currentPlayerId"], order[1])

        # And the round still reaches a reveal rather than stalling
        for pid in order[2:]:
            self.act("pull", 1, player=pid)
        self.assertIn("lastRound", self.game["challenge"])

    def test_bot_never_asks_for_rocks_an_empty_bag_cannot_give(self):
        """The bot's pull must be legal at an empty bag or it retries forever."""
        import random as _random
        from bots import next_action

        self.start_challenge("challenge_lowest_score_loses")
        order = list(self.game["challenge"]["pending"])
        self.act("pull", 8, player=order[0])

        challenge = self.game["challenge"]
        # Hand the empty bag to a bot seat
        bot_id = challenge["pending"][0]
        self.game["players"][bot_id]["isBot"] = True
        challenge["currentPlayerId"] = bot_id
        for seed in range(25):
            action = next_action(self.game, 0.0, _random.Random(seed))
            self.assertIsNotNone(action)
            self.assertEqual(action["kwargs"]["action"], "pull")
            self.assertEqual(action["kwargs"]["value"], 0,
                             "an empty bag can only yield a pull of 0")

    def test_scoring_and_knockout(self):
        self.start_challenge("challenge_lowest_score_loses")
        challenge = self.game["challenge"]

        # Everyone takes 0 rocks except the last player, who takes 1
        order = list(challenge["pending"])
        for pid in order[:-1]:
            self.act("pull", 0, player=pid)
        # Force a grey rock for the final player so they clearly score highest
        self.game["challenge"]["bag"] = {"grey": 1, "purple": 0}
        self.act("pull", 1, player=order[-1])

        last_round = self.game["challenge"]["lastRound"]
        self.assertEqual(last_round["scores"][order[-1]], 1)
        self.assertFalse(last_round["redo"])
        # Everyone who scored 0 is knocked out
        self.assertEqual(sorted(last_round["knockedOut"]), sorted(order[:-1]))

    def test_all_tied_lowest_redoes_the_round(self):
        self.start_challenge("challenge_lowest_score_loses")
        order = list(self.game["challenge"]["pending"])
        for pid in order:
            self.act("pull", 0, player=pid)

        challenge = self.game["challenge"]
        self.assertTrue(challenge["lastRound"]["redo"])
        self.assertEqual(challenge["knockedOut"], [])
        self.assertEqual(challenge["round"], 2)
        self.assertEqual(challenge["bag"], {"grey": 5, "purple": 3})

    def test_last_player_standing_wins(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                self.setUp()
                random.seed(seed)
                self.start_challenge("challenge_lowest_score_loses")
                challenge = self.play_out(
                    chooser=lambda ch: ("pull", random.randint(0, min(3, ch["maxPull"]))))
                self.assertEqual(challenge["phase"], "complete")
                self.assertNotIn(challenge["winnerId"], challenge["knockedOut"])


class TestPullOrSteal(RocksTestBase):
    """Setup: 1 Purple Rock + (players - 1) Grey Rocks — one rock per player."""

    def test_setup_matches_the_player_count_table(self):
        for count, grey in ((3, 2), (4, 3), (5, 4), (6, 5)):
            with self.subTest(players=count):
                self.PLAYER_COUNT = count
                self.setUp()
                self.start_challenge("challenge_pull_or_steal")
                challenge = self.game["challenge"]
                self.assertEqual(challenge["bag"], {"grey": grey, "purple": 1})
                self.assertEqual(len(challenge["numbers"]), count)
        self.PLAYER_COUNT = 4

    def test_player_one_must_pull(self):
        self.start_challenge("challenge_pull_or_steal")
        challenge = self.game["challenge"]
        self.assertEqual(challenge["numbers"][self.starter], 1)
        self.assertEqual(challenge["actions"], ["pull"])

        result = self.act("steal", self.player_ids[1])
        self.assertFalse(result["success"])

    def test_stealing_takes_a_lower_numbered_players_rock(self):
        self.start_challenge("challenge_pull_or_steal")
        challenge = self.game["challenge"]
        order = challenge["order"]

        self.act("pull", player=order[0])           # Player 1 pulls
        self.assertEqual(self.game["challenge"]["currentPlayerId"], order[1])
        self.assertIn("steal", self.game["challenge"]["actions"])
        self.assertEqual(self.game["challenge"]["stealTargets"], [order[0]])

        self.act("steal", order[0], player=order[1])

        challenge = self.game["challenge"]
        # The victim loses their rock and takes the next turn with the bag
        self.assertEqual(challenge["currentPlayerId"], order[0])
        self.assertNotIn(order[0], challenge.get("rocks", {}))

    def test_purple_rock_holder_wins_at_the_reveal(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                self.setUp()
                random.seed(seed)
                self.start_challenge("challenge_pull_or_steal")
                challenge = self.play_out(chooser=lambda ch: ("pull", None))

                self.assertEqual(challenge["phase"], "complete")
                self.assertEqual(challenge["rocks"][challenge["winnerId"]], "purple")
                self.assertEqual(len(challenge["rocks"]), self.PLAYER_COUNT)


class TestHideNSeekStub(RocksTestBase):
    def test_hide_n_seek_explains_why_it_is_unavailable(self):
        definition = CHALLENGE_DEFINITIONS["challenge_hide_n_seek"]
        self.assertFalse(definition["digital"])

        result = self.start_challenge("challenge_hide_n_seek")
        self.assertIn("sleight-of-hand", result["message"])
        self.assertFalse(result["challenge_started"])
        self.assertIsNone(self.game.get("challenge"))

        # The card is still discarded — it doesn't clog the hand
        self.assertNotIn("challenge_hide_n_seek",
                         [c["type"] for c in self.game["players"][self.starter]["hand"]])


class TestChallengeParticipation(RocksTestBase):
    """Combined mode: eliminated players can't take part in Challenges."""

    def test_eliminated_players_are_excluded(self):
        eliminated = self.player_ids[3]
        self.game["players"][eliminated]["characterCards"] = 0
        self.game["players"][eliminated]["isEliminated"] = True

        self.start_challenge("challenge_pull_or_steal")
        challenge = self.game["challenge"]

        self.assertNotIn(eliminated, challenge["order"])
        self.assertEqual(len(challenge["order"]), self.PLAYER_COUNT - 1)
        # One rock per participant
        self.assertEqual(challenge["bag"]["grey"] + challenge["bag"]["purple"],
                         self.PLAYER_COUNT - 1)

    def test_non_participants_cannot_act(self):
        self.start_challenge("challenge_pull_or_steal")
        outsider = self.player_ids[2]
        result = self.gs.challenge_action(self.game_id, playerId=outsider, action="pull")
        self.assertFalse(result["success"])
        self.assertIn("turn", result["message"])

    def test_a_challenge_needs_at_least_two_players(self):
        for pid in self.player_ids[1:]:
            self.game["players"][pid]["characterCards"] = 0
            self.game["players"][pid]["isEliminated"] = True

        self.game["players"][self.starter]["hand"].append({"type": "challenge_pull_or_steal"})
        idx = len(self.game["players"][self.starter]["hand"]) - 1
        result = self.gs.play_card(self.game_id, self.starter, idx)
        self.assertFalse(result["success"])
        self.assertIn("at least 2 players", result["message"])


if __name__ == '__main__':
    print("🪨 Testing Survivor: Let's Go To Rocks (combined mode)")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for test_class in (TestNecklace, TestHighestBidder, TestOneNowOrTwoLater,
                       TestLowestScoreLoses, TestPullOrSteal, TestHideNSeekStub,
                       TestChallengeParticipation):
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    result = unittest.TextTestRunner(verbosity=2, buffer=True).run(suite)

    print(f"\n📋 Rocks Expansion Test Summary:")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    for test, _ in result.failures:
        print(f"  FAIL: {test}")
    for test, _ in result.errors:
        print(f"  ERROR: {test}")

    success = not result.failures and not result.errors
    print(f"\n🎉 All Rocks expansion tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
