#!/usr/bin/env python3
"""
Eight-player tie-break cascade battery (Part B of the eight-player expansion
plan, docs/superpowers/plans/2026-08-05-eight-player-expansion.md).

TESTS ONLY — the tie-break cascade (``resolve_tribal_eliminations``,
``elimination_ladder``, ``_apply_three_left_rule``, ``tie_break``, and the
Final Tribal jury tie) is verified N-agnostic by reading the source: every
branch works off ``alive``/``counts``/``needed``, and none of it special-cases
a player count. This file pins that behaviour at eight players so a future
refactor can't quietly break it there first. No production code is touched.

Mirrors the fixture idioms of tests/test_tie_break_cascade.py exactly — same
``resolve()``/``alive()`` helpers, same ``_tally()`` two-call idol-window
dance — scaled to an 8-player table.

Every case cites the exact line(s) of docs/survivor_rules.md it pins:

  B1  line 149  — 3+ tied for most at a Double: Leader picks 2 of them.
  B2  line 151  — 1 clear first + 2+ tied for second: first goes automatically,
                  Leader picks the other.
  B3  line 150  — exactly 2 tied for most at a Double: both go, no choice.
  B4  lines 157-159 — unclear ladder: non-immune-with-votes, then
                  non-immune-no-votes, then Immunity Idol/Necklace players.
  B5  lines 157-159 — same ladder, exercised until it must fall through to
                  the idol/Necklace tier.
  B6  line 152  — 3 players left, a Double would drop the table to 1: Leader
                  picks 1, Final Tribal begins immediately.
  B7  line 188  — Final Tribal Council: a tied jury vote is broken by the
                  Council Leader (the most recently eliminated juror).
  B8  line 161  — "unclear... after just the first player is voted out": no
                  votes at all for the second slot is not a second-place tie.

NOTE ON B5's 8-alive framing: with a Double Elimination's need capped at 2,
exactly two exposed (non-immune) players among eight is *always* enough for
tier 2 to supply both vote-outs outright — the idol/Necklace tier is
mathematically unreachable through a single real council at that need. B5
pins the real, production-exercised outcome for that setup (both exposed
players go automatically, the 6 protected players untouched) AND pins the
underlying ``elimination_ladder`` ordering directly (idol/Necklace players
strictly after every non-immune player) by asking it for more candidates
than tiers 1+2 can supply — the same ordering ``tie_break``'s ladder refill
(survivor_server.py ~1519-1537) relies on whenever a real council does run
dry.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from survivor_server import GameState
from places import DEFAULT_PLACE


def _tally(gs, gid):
    """Run the council to the tally, through the mandatory idol window.

    "Immunity Idol ... can only be played AFTER all players have voted, but
    BEFORE votes are tallied." So the Leader's first reveal seals the Voting
    Box and calls for idols; a second one opens it.
    """
    result = gs.reveal_votes(gid)
    if isinstance(result, dict) and result.get("idolWindowOpened"):
        result = gs.reveal_votes(gid)
    return result


class TieBreakEightPlayerTest(unittest.TestCase):
    PLAYER_COUNT = 8

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.engine = self.gs.rules_engine
        self.game_id = self.gs.create_game()
        self.game = self.gs.games[self.game_id]

        # Eight players, built directly into the game dict rather than
        # through add_player()/seats.assign() — both are capped at 6 seats
        # as of this writing (a parallel branch of the eight-player
        # expansion plan raises the cap; seats.py has only 6 seat keys
        # until its own parallel task lands two more). The cascade
        # functions under test only ever read game["players"] entries for
        # characterCards/isEliminated/name, so a hand-built roster in
        # add_player()'s exact shape exercises precisely the same code
        # paths without depending on either landing first.
        colors = ["red", "teal", "blue", "orange", "green", "yellow", "purple", "pink"]
        self.pids = []
        for i in range(self.PLAYER_COUNT):
            pid = f"p{i + 1}"
            self.game["players"][pid] = {
                "id": pid, "name": f"Player{i + 1}",
                "color": colors[i], "seat": None, "hand": [],
                "isEliminated": False, "hasStolen": False, "hasPlayed": False,
                "hasDrawn": False, "hasVoted": False, "extraVotes": 0,
                "characterCards": 2, "isActive": True,
                "isCouncilLeader": (i == 0),
                "immunityPlayed": False,
                "placeChoice": DEFAULT_PLACE,
                "discordUserId": None,
            }
            self.game["turnOrder"].append(pid)
            self.pids.append(pid)
        self.game["currentVote"]["councilLeaderId"] = self.pids[0]

        # Deterministic hands: a randomly-dealt Goodwill Gamble would change
        # how many votes a player is required to cast.
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

    # ══════════════════ B1 — four-way tie at a double ══════════════════

    def test_b1_four_way_tie_at_a_double(self):
        """
        rules_survivor.md:149 "If 3 or more players are tied with the most
        votes, the Tribal Council Leader gets to decide which 2 of the tied
        players are voted out." — 8 alive, votes 2/2/2/2 at a Double.
        """
        a, b, c, d = self.pids[0], self.pids[1], self.pids[2], self.pids[3]
        outcome = self.resolve({a: 2, b: 2, c: 2, d: 2}, elimination_type="double")

        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [a, b, c, d])
        self.assertEqual(outcome["eliminationsNeeded"], 2)
        self.assertEqual(outcome["eliminated"], [])

        # End-to-end: the Leader picks exactly 2 of the 4 tied players in one
        # enhanced_tie_break/tie_break call.
        leader = self.pids[7]
        self.gs._trigger_tribal_council(self.game, "double", drawer_id=leader)
        current_vote = self.game["currentVote"]
        current_vote["phase"] = "voting"
        current_vote["votes"] = {
            a: {c: 1}, b: {d: 1}, c: {a: 1}, d: {b: 1},
            self.pids[4]: {a: 1}, self.pids[5]: {b: 1}, self.pids[6]: {c: 1},
            leader: {d: 1},
        }
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        self.assertTrue(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["tiedPlayers"], [a, b, c, d])
        self.assertEqual(current_vote["eliminationsNeeded"], 2)

        result = self.gs.tie_break(self.game_id, leaderId=leader, chosenIds=[a, c])
        self.assertTrue(result["success"], result.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["eliminated"], [a, c])

    # ══════════════════ B2 — clear first, three-way second tie ══════════════════

    def test_b2_clear_first_three_way_second_tie(self):
        """
        rules_survivor.md:151 "If 1 player gets the most votes, and 2 or more
        are tied with the second most, the player with the most votes is
        voted out first. Then, the Tribal Council Leader decides which of
        the tied players is also voted out." — 8 alive, votes 3/1/1/1.
        """
        a, b, c, d = self.pids[0], self.pids[1], self.pids[2], self.pids[3]
        outcome = self.resolve({a: 3, b: 1, c: 1, d: 1}, elimination_type="double")

        self.assertEqual(outcome["eliminated"], [a])
        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["tiedPlayers"], [b, c, d])
        self.assertEqual(outcome["eliminationsNeeded"], 2)

        # End-to-end: a single chosenId completes the council.
        leader = self.pids[7]
        self.gs._trigger_tribal_council(self.game, "double", drawer_id=leader)
        current_vote = self.game["currentVote"]
        current_vote["phase"] = "voting"
        current_vote["votes"] = {
            self.pids[4]: {a: 1}, self.pids[5]: {a: 1}, self.pids[6]: {a: 1},
            leader: {b: 1}, a: {c: 1}, b: {d: 1}, c: {}, d: {},
        }
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        self.assertEqual(current_vote["eliminated"], [a])
        self.assertTrue(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["tiedPlayers"], [b, c, d])

        result = self.gs.tie_break(self.game_id, leaderId=leader, chosenId=b)
        self.assertTrue(result["success"], result.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["eliminated"], [a, b])

        done = self.gs.complete_tribal(self.game_id)
        self.assertTrue(done["success"], done.get("message"))
        self.assertCountEqual(done["votedOut"], [a, b])

    # ══════════════════ B3 — ties exactly matching the need ══════════════════

    def test_b3_ties_exactly_matching_the_need(self):
        """
        rules_survivor.md:150 "If 2 players are tied with the most votes,
        both are voted out." — no Leader choice at all — with the other six
        of the eight players at the table getting zero votes.
        """
        a, b = self.pids[0], self.pids[1]
        outcome = self.resolve({a: 3, b: 3}, elimination_type="double")

        self.assertFalse(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["eliminated"], [a, b])
        self.assertEqual(outcome["tiedPlayers"], [])

        # End-to-end: no tie_break call is needed at all — reveal_votes alone
        # settles it, and complete_tribal can run immediately after.
        leader = self.pids[7]
        self.gs._trigger_tribal_council(self.game, "double", drawer_id=leader)
        current_vote = self.game["currentVote"]
        current_vote["phase"] = "voting"
        current_vote["votes"] = {
            self.pids[2]: {a: 1}, self.pids[3]: {a: 1}, self.pids[4]: {a: 1},
            self.pids[5]: {b: 1}, self.pids[6]: {b: 1}, leader: {b: 1},
            a: {}, b: {},
        }
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["eliminated"], [a, b])

        done = self.gs.complete_tribal(self.game_id)
        self.assertTrue(done["success"], done.get("message"))
        self.assertCountEqual(done["votedOut"], [a, b])

    # ══════════════════ B4 — the ladder under idol pressure ══════════════════

    def test_b4_ladder_under_idol_pressure(self):
        """
        rules_survivor.md:157-159 — 3 players play Immunity Idols (their
        votes are negated) and nobody else gets any votes at all. The
        unclear-who-is-voted-out ladder's tier 2 (non-immune, no votes) has
        5 candidates for a Double's 2 needed, so the idol players are never
        even reached, and never appear in tiedPlayers.
        """
        idol_pids = self.pids[5:8]     # 3 idol players
        exposed_pids = self.pids[0:5]  # 5 non-immune players, no votes

        outcome = self.resolve({}, elimination_type="double",
                                protected=idol_pids, idols=idol_pids)

        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertEqual(outcome["eliminationsNeeded"], 2)
        self.assertCountEqual(outcome["tiedPlayers"], exposed_pids)
        for pid in idol_pids:
            self.assertNotIn(pid, outcome["tiedPlayers"])

        # The full ladder, in order: idol players appear ONLY after every
        # non-immune player, regardless of how many are actually needed.
        full_ladder = self.engine.elimination_ladder(
            self.game, {}, protected_players=idol_pids, idol_players=idol_pids,
            picks_needed=self.PLAYER_COUNT)
        self.assertEqual(full_ladder[:5], exposed_pids)
        self.assertEqual(full_ladder[5:], idol_pids)

    # ══════════════════ B5 — ladder exhaustion ══════════════════

    def test_b5_ladder_exhaustion_idol_players_choosable_last(self):
        """
        rules_survivor.md:157-159 — 6 of 8 players are protected (Immunity
        Idol or Necklace); only 2 are exposed. Tier 2 alone (the 2 exposed
        players) exactly covers a Double's need, so the outcome is forced
        with no Leader choice and the 6 protected players go untouched —
        that IS the "last resort" rule doing its job. Asking the ladder
        directly for more candidates than tiers 1+2 can supply shows it
        falls through to the idol/Necklace tier only after both exposed
        players, which is the exact fallback tie_break()'s ladder refill
        (survivor_server.py ~1519-1537) depends on whenever a real council
        does run dry.
        """
        protected_pids = self.pids[2:8]  # 6 idol/Necklace-protected players
        exposed_pids = self.pids[0:2]    # 2 fully exposed players

        outcome = self.resolve({}, elimination_type="double",
                                protected=protected_pids, idols=protected_pids)
        self.assertFalse(outcome["tieBreakNeeded"])
        self.assertCountEqual(outcome["eliminated"], exposed_pids)
        for pid in protected_pids:
            self.assertNotIn(pid, outcome["eliminated"])

        full_ladder = self.engine.elimination_ladder(
            self.game, {}, protected_players=protected_pids,
            idol_players=protected_pids, picks_needed=self.PLAYER_COUNT)
        self.assertEqual(full_ladder[:2], exposed_pids)
        self.assertEqual(full_ladder[2:], protected_pids)
        for exposed in exposed_pids:
            for protected in protected_pids:
                self.assertLess(full_ladder.index(exposed), full_ladder.index(protected),
                                 "an idol/Necklace player must never rank ahead of "
                                 "an exposed player on the ladder")

    # ══════════════════ B6 — the three-left rule keys on 3 alive ══════════════════

    def test_b6_three_left_rule_keys_on_three_alive_not_table_size(self):
        """
        rules_survivor.md:152 "If there are only 3 players left and 2
        players would be eliminated at the same time (leaving you with only
        1 player left in the game), the Tribal Council Leader decides which
        of the tied players is eliminated. Immediately begin The Final
        Tribal Council." — an 8-seat table reduced to 3 alive still applies
        the rule; it keys on len(alive) == 3, never on how many seats the
        table started with.
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

    # ══════════════════ B7 — even jury splits ══════════════════

    def test_b7_even_jury_split_at_the_final_two(self):
        """
        rules_survivor.md:188 "If both players in the final two get the same
        number of votes, the Final Tribal Council Leader breaks the tie by
        choosing the winner." Rule 169: "The player most recently eliminated
        is a member of the Jury AND the Final Tribal Council Leader." — an
        8-player game reaching the final 2 leaves a 6-member jury; a 3-3
        split is broken by the most recently eliminated juror.

        See survivor_server.py:2088-2122 (_determine_final_winner) for the
        tally, and :2048-2067 (_start_final_tribal_council) for how
        jury[-1] becomes the Leader.
        """
        jury = self.pids[:6]       # eliminated in this order; jury[-1] most recent
        finalists = self.pids[6:]  # the final two
        x, y = finalists

        self.game["jury"] = list(jury)
        self.gs._start_final_tribal_council(self.game, finalists)

        final_tribal = self.game["finalTribal"]
        self.assertEqual(final_tribal["leader"], jury[-1],
                          "the most recently eliminated juror is the Leader")
        self.assertCountEqual(final_tribal["jury"], jury)
        self.assertCountEqual(final_tribal["finalists"], finalists)

        final_tribal["phase"] = "voting"
        for juror in jury[:3]:
            self.assertTrue(self.gs.cast_final_vote(
                self.game_id, juryMemberId=juror, finalistId=x))
        for juror in jury[3:5]:
            self.assertTrue(self.gs.cast_final_vote(
                self.game_id, juryMemberId=juror, finalistId=y))
        # The 6th and final vote auto-advances the phase and tallies.
        self.assertTrue(self.gs.cast_final_vote(
            self.game_id, juryMemberId=jury[5], finalistId=y))

        self.assertEqual(final_tribal["phase"], "reveal")
        self.assertEqual(final_tribal["voteCounts"], {x: 3, y: 3})
        self.assertTrue(final_tribal["tieBreakNeeded"])
        self.assertCountEqual(final_tribal["tiedFinalists"], [x, y])
        self.assertNotIn("winner", final_tribal)

        # Only the Leader (jury[-1]) may break the tie.
        bad = self.gs.break_final_tie(self.game_id, leaderId=jury[0], winnerId=x)
        self.assertFalse(bad)
        self.assertTrue(final_tribal["tieBreakNeeded"], "a non-Leader must not resolve it")

        good = self.gs.break_final_tie(self.game_id, leaderId=jury[-1], winnerId=x)
        self.assertTrue(good)
        self.assertEqual(final_tribal["winner"], x)
        self.assertFalse(final_tribal["tieBreakNeeded"])
        self.assertEqual(self.game["phase"], "finished")
        self.assertEqual(self.game["winner"], x)

    # ══════════════════ B8 — second-place tie where second place is zero ══════════════════

    def test_b8_second_place_tie_where_second_place_is_zero(self):
        """
        rules_survivor.md:161 "This could happen ... at a Double Elimination
        Tribal Council after just the first player is voted out." — one
        player gets all the votes (3), everyone else gets none. The second
        vote-out is NOT a second-place tie (nobody tied for anything) — it
        falls straight to the unclear-who-is-voted-out ladder's no-votes
        tier, which is every other living player.
        """
        a = self.pids[0]
        outcome = self.resolve({a: 3}, elimination_type="double")

        self.assertEqual(outcome["eliminated"], [a])
        self.assertTrue(outcome["tieBreakNeeded"])
        self.assertNotIn(a, outcome["tiedPlayers"])
        self.assertCountEqual(outcome["tiedPlayers"], self.pids[1:])
        self.assertEqual(outcome["eliminationsNeeded"], 2)

        # End-to-end: the Leader completes the second vote-out from the ladder.
        leader = self.pids[7]
        self.gs._trigger_tribal_council(self.game, "double", drawer_id=leader)
        current_vote = self.game["currentVote"]
        current_vote["phase"] = "voting"
        current_vote["votes"] = {
            a: {},
            self.pids[1]: {a: 1}, self.pids[2]: {a: 1}, self.pids[3]: {a: 1},
            self.pids[4]: {}, self.pids[5]: {}, self.pids[6]: {}, leader: {},
        }
        reveal = _tally(self.gs, self.game_id)
        self.assertTrue(reveal["success"], reveal.get("message"))
        self.assertEqual(current_vote["eliminated"], [a])
        self.assertTrue(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["tiedPlayers"], self.pids[1:])

        result = self.gs.tie_break(self.game_id, leaderId=leader, chosenId=self.pids[3])
        self.assertTrue(result["success"], result.get("message"))
        self.assertFalse(current_vote["tieBreakNeeded"])
        self.assertCountEqual(current_vote["eliminated"], [a, self.pids[3]])

        done = self.gs.complete_tribal(self.game_id)
        self.assertTrue(done["success"], done.get("message"))
        self.assertCountEqual(done["votedOut"], [a, self.pids[3]])


if __name__ == '__main__':
    print("⚖️  Testing tie-break cascade at an eight-player table")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TieBreakEightPlayerTest)
    result = unittest.TextTestRunner(verbosity=2, buffer=True).run(suite)

    print(f"\n📋 Eight-Player Tie-break Test Summary:")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    for test, _ in result.failures:
        print(f"  FAIL: {test}")
    for test, _ in result.errors:
        print(f"  ERROR: {test}")

    success = not result.failures and not result.errors
    print(f"\n🎉 All eight-player tie-break tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
