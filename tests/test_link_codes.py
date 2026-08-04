#!/usr/bin/env python3
"""
Linking a Discord account without typing a snowflake.

The old way was to read an 18-digit number off Discord and type it into
Settings, which the app had to warn you about: "A Discord user ID is a long run
of digits — usually 18." The new way is a code you can say out loud.

Three parties, and the security of the thing rests on which one knows what:
the phone knows the code, Discord knows who ran the command, and only the
server sees both. A username is never involved — people change those, and
display names were never unique.

What these tests care about is the failure side. A code that outlives its
usefulness, one that can be claimed twice, or an error message that tells a
guesser they got close are all quiet ways to hand somebody else's voice to the
wrong account.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from link_codes import (LinkCodes, WORDS, CODE_TTL_SECONDS, CLAIM_TTL_SECONDS,
                        MAX_OUTSTANDING, _CLAIM_ATTEMPT_LIMIT)

ALICE = "111111111111111111"
BOB = "222222222222222222"


class MintingTest(unittest.TestCase):
    def setUp(self):
        self.codes = LinkCodes()

    def test_a_code_is_something_a_person_can_read_aloud(self):
        code = self.codes.mint()
        word, _, digits = code.partition("-")
        self.assertIn(word, WORDS)
        self.assertEqual(len(digits), 3)
        self.assertTrue(digits.isdigit())

    def test_every_code_is_distinct_while_it_lives(self):
        minted = {self.codes.mint() for _ in range(150)}
        self.assertEqual(len(minted), 150)

    def test_minting_stops_rather_than_growing_without_limit(self):
        for _ in range(MAX_OUTSTANDING):
            self.assertIsNotNone(self.codes.mint())
        self.assertIsNone(self.codes.mint(), "the ceiling has to actually hold")

    def test_expired_codes_make_room_for_new_ones(self):
        for _ in range(MAX_OUTSTANDING):
            self.codes.mint(now=0.0)
        self.assertIsNotNone(self.codes.mint(now=CODE_TTL_SECONDS + 1))


class ClaimingTest(unittest.TestCase):
    def setUp(self):
        self.codes = LinkCodes()
        self.code = self.codes.mint(now=0.0)

    def test_the_happy_path(self):
        ok, _ = self.codes.claim(self.code, ALICE, now=1.0)
        self.assertTrue(ok)
        self.assertEqual(self.codes.status(self.code, now=2.0),
                         {"claimed": True, "discordUserId": ALICE})

    def test_the_phone_sees_nothing_until_somebody_runs_the_command(self):
        self.assertEqual(self.codes.status(self.code, now=1.0),
                         {"claimed": False, "discordUserId": None})

    def test_a_claim_is_collected_exactly_once(self):
        """Or a second device polling the same code learns the answer too."""
        self.codes.claim(self.code, ALICE, now=1.0)
        self.assertTrue(self.codes.status(self.code, now=2.0)["claimed"])
        self.assertIsNone(self.codes.status(self.code, now=3.0),
                          "the code dies the moment its answer is read")

    def test_a_code_cannot_be_claimed_twice(self):
        self.assertTrue(self.codes.claim(self.code, ALICE, now=1.0)[0])
        ok, _ = self.codes.claim(self.code, BOB, now=2.0)
        self.assertFalse(ok, "the first Discord account keeps it")
        self.assertEqual(self.codes.status(self.code, now=3.0)["discordUserId"],
                         ALICE)

    def test_an_expired_code_is_gone_not_merely_unclaimed(self):
        state = self.codes.status(self.code, now=CODE_TTL_SECONDS + 1)
        self.assertIsNone(state, "the phone must be told to ask again")
        ok, _ = self.codes.claim(self.code, ALICE, now=CODE_TTL_SECONDS + 2)
        self.assertFalse(ok)

    def test_a_claim_nobody_collects_does_not_sit_there_forever(self):
        """An uncollected claim is an answer waiting for a phone that left."""
        self.codes.claim(self.code, ALICE, now=1.0)
        self.assertIsNone(self.codes.status(self.code, now=CLAIM_TTL_SECONDS + 2))

    def test_an_unknown_code_is_refused(self):
        ok, _ = self.codes.claim("PALM-000", ALICE, now=1.0)
        self.assertFalse(ok)

    def test_a_used_code_and_a_wrong_one_answer_identically(self):
        """Otherwise a wrong guess becomes a probe for near misses."""
        self.codes.claim(self.code, ALICE, now=1.0)
        _, used = self.codes.claim(self.code, BOB, now=2.0)
        _, wrong = self.codes.claim("PALM-000", BOB, now=2.0)
        self.assertEqual(used, wrong)

    def test_something_that_is_not_a_discord_id_is_refused(self):
        for junk in (None, "", "not-a-number", 12345, "111 111"):
            with self.subTest(value=junk):
                self.assertFalse(self.codes.claim(self.code, junk, now=1.0)[0])
        self.assertFalse(self.codes.status(self.code, now=2.0)["claimed"],
                         "and none of that consumed the code")

    def test_the_code_survives_being_typed_by_a_human(self):
        """Lowercase, spaces, a lost hyphen, an autocorrected em dash."""
        shapes = {
            "lowercase":   lambda c: c.lower(),
            "spaced":      lambda c: c.replace("-", " "),
            "no hyphen":   lambda c: c.replace("-", ""),
            "em dash":     lambda c: c.replace("-", "\u2014"),
            "padded":      lambda c: f"  {c}  ",
        }
        for label, shape in shapes.items():
            with self.subTest(shape=label):
                codes = LinkCodes()
                code = codes.mint(now=0.0)
                self.assertTrue(codes.claim(shape(code), ALICE, now=1.0)[0],
                                f"{shape(code)!r} should be accepted")


class GuessingTest(unittest.TestCase):
    """Somebody in the Discord server trying codes until one lands."""

    def setUp(self):
        self.codes = LinkCodes()

    def test_wrong_guesses_run_out(self):
        for i in range(_CLAIM_ATTEMPT_LIMIT):
            ok, _ = self.codes.claim("PALM-000", BOB, now=float(i))
            self.assertFalse(ok)
        _, message = self.codes.claim("PALM-001", BOB, now=10.0)
        self.assertIn("Too many", message)

    def test_the_budget_is_per_account_not_for_everyone(self):
        for i in range(_CLAIM_ATTEMPT_LIMIT):
            self.codes.claim("PALM-000", BOB, now=float(i))
        code = self.codes.mint(now=10.0)
        self.assertTrue(self.codes.claim(code, ALICE, now=11.0)[0],
                        "one guesser must not lock out the table")

    def test_a_throttled_guesser_cannot_take_a_live_code(self):
        code = self.codes.mint(now=0.0)
        for i in range(_CLAIM_ATTEMPT_LIMIT):
            self.codes.claim("PALM-000", BOB, now=float(i))
        self.assertFalse(self.codes.claim(code, BOB, now=10.0)[0])
        self.assertFalse(self.codes.status(code, now=11.0)["claimed"])

    def test_succeeding_does_not_cost_budget(self):
        """Linking a second phone must not be punished for the first."""
        for _ in range(_CLAIM_ATTEMPT_LIMIT + 2):
            code = self.codes.mint(now=0.0)
            self.assertTrue(self.codes.claim(code, ALICE, now=1.0)[0])
            self.codes.status(code, now=2.0)


class HttpDoorTest(unittest.TestCase):
    """The three routes, as the phone and the bot actually call them."""

    def setUp(self):
        import survivor_server
        self.server = survivor_server
        survivor_server.link_codes = LinkCodes()
        self.client = survivor_server.app.test_client()

    def post(self, path, payload):
        return self.client.post(path, json=payload)

    def test_start_claim_status_end_to_end(self):
        started = self.post('/api/discord/link/start', {}).get_json()
        self.assertTrue(started["success"])
        code = started["code"]
        self.assertGreater(started["expiresInSeconds"], 0)

        pending = self.post('/api/discord/link/status', {"code": code}).get_json()
        self.assertFalse(pending["claimed"])

        claimed = self.post('/api/discord/link/claim',
                            {"code": code, "discordUserId": ALICE})
        self.assertEqual(claimed.status_code, 200)

        done = self.post('/api/discord/link/status', {"code": code}).get_json()
        self.assertTrue(done["claimed"])
        self.assertEqual(done["discordUserId"], ALICE)

    def test_polling_an_expired_code_says_so_rather_than_hanging(self):
        response = self.post('/api/discord/link/status', {"code": "PALM-000"})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.get_json()["expired"])

    def test_a_bad_claim_is_a_400_with_something_to_read(self):
        response = self.post('/api/discord/link/claim',
                             {"code": "PALM-000", "discordUserId": ALICE})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["message"])

    def test_cancelling_frees_the_code(self):
        code = self.post('/api/discord/link/start', {}).get_json()["code"]
        self.post('/api/discord/link/cancel', {"code": code})
        self.assertEqual(
            self.post('/api/discord/link/status', {"code": code}).status_code, 404)

    def test_the_claim_door_cannot_reach_a_game(self):
        """The bot's one write must stay the only thing it can write."""
        response = self.post('/api/discord/link/claim',
                             {"code": "PALM-000", "discordUserId": ALICE,
                              "gameId": "anything", "phase": "finished"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("phase", response.get_json())


if __name__ == '__main__':
    unittest.main(verbosity=2)
