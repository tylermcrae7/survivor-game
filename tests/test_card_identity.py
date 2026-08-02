#!/usr/bin/env python3
"""
Card identity.

A card used to be `{"type": "vote"}` and nothing else, so two Vote Cards in one
hand were literally the same dictionary — indistinguishable, not merely similar.
Nothing could say "this card", only "a card of this type": no reordering a hand,
no animating a specific card between players, and a Camp Raid hunting for the
card you had just drawn could only find the first one that matched.

Every failure mode here is silent. A card that loses its uid does not throw;
it turns up hours later as a hand where SwiftUI thinks two rows are the same
row. So these tests care mostly about the paths that *rebuild* a card instead
of moving it, and about the discard — which is reshuffled into the Draw Pile
when it empties, laundering anything wrong there straight back into a hand.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rules_engine import ensure_card_uids, new_card
from survivor_server import GameState


def all_uids(game):
    uids = []
    for player in game["players"].values():
        uids += [c.get("uid") for c in (player.get("hand") or [])]
    for pile in ("deck", "discard"):
        uids += [c.get("uid") for c in (game.get(pile) or [])]
    return uids


class CardIdentityTest(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        self.gs = GameState()
        self.gid = self.gs.create_game()
        self.ids = [self.gs.add_player(self.gid, n, c) for n, c in
                    [("Ana", "#FF6B6B"), ("Ben", "#4ECDC4"),
                     ("Cam", "#45B7D1"), ("Dee", "#F9844A")]]
        self.gs.start_full_game(self.gid)
        self.game = self.gs.games[self.gid]

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── every card has one, and no two share ──────────────────────────────

    def test_a_dealt_game_gives_every_card_its_own_identity(self):
        uids = all_uids(self.game)
        self.assertTrue(uids, "a started game must hold cards")
        self.assertTrue(all(uids), "every card carries a uid")
        self.assertEqual(len(uids), len(set(uids)),
                         "uids are unique across hands, deck and discard")

    def test_two_vote_cards_in_one_hand_are_distinguishable(self):
        """The case that motivated all of this."""
        pid = self.ids[0]
        self.game["players"][pid]["hand"] = [new_card("vote"), new_card("vote")]
        a, b = self.game["players"][pid]["hand"]
        self.assertNotEqual(a["uid"], b["uid"])
        self.assertNotEqual(a, b)

    # ── moving a card must not change what it is ──────────────────────────

    def test_a_stolen_card_keeps_its_identity(self):
        thief, victim = self.game["turnOrder"][0], self.game["turnOrder"][1]
        self.game["players"][victim]["hand"] = [new_card("camp_raid"), new_card("vote")]
        self.game["players"][thief]["hand"] = [new_card("vote")]
        self.gs.rules_engine.sync_vote_counters(self.game)
        target_uid = self.game["players"][victim]["hand"][0]["uid"]

        self.gs.steal_card(self.gid, thiefId=thief, targetId=victim)

        thief_uids = [c["uid"] for c in self.game["players"][thief]["hand"]]
        victim_uids = [c["uid"] for c in self.game["players"][victim]["hand"]]
        self.assertIn(target_uid, thief_uids)
        self.assertNotIn(target_uid, victim_uids)

    def test_inheritance_moves_cards_rather_than_copying_them(self):
        """A deep copy here would put one uid in two hands at once."""
        import seats
        heir, dead = self.ids[0], self.ids[1]
        seat = seats.seat_of(self.game["players"][dead])
        self.game["players"][dead]["hand"] = [new_card("camp_raid"), new_card("the_spy_shack")]
        self.game["players"][heir]["hand"] = [new_card("vote"),
                                              new_card(f"inheritance_{seat}")]
        estate = {c["uid"] for c in self.game["players"][dead]["hand"]}

        self.gs.rules_engine.process_elimination_inheritance(self.game, dead)

        heir_uids = {c["uid"] for c in self.game["players"][heir]["hand"]}
        self.assertTrue(estate <= heir_uids, "the heir receives the estate")
        self.assertEqual(self.game["players"][dead]["hand"], [],
                         "and the dead player keeps none of it")
        uids = all_uids(self.game)
        self.assertEqual(len(uids), len(set(uids)), "no uid may exist twice")

    def test_a_played_card_carries_its_identity_to_the_discard(self):
        actor = self.game["turnOrder"][0]
        self.game["players"][actor]["hasStolen"] = True
        self.game["players"][actor]["hand"] = [new_card("camp_raid")]
        victim = self.game["turnOrder"][1]
        self.game["players"][victim]["hand"] = [new_card("vote")]
        self.gs.rules_engine.sync_vote_counters(self.game)
        played_uid = self.game["players"][actor]["hand"][0]["uid"]

        self.gs.play_card(self.gid, playerId=actor, cardIdx=0, params={"targetId": victim})

        self.assertIn(played_uid, [c.get("uid") for c in self.game["discard"]])

    def test_a_failed_play_puts_the_same_card_back(self):
        actor = self.game["turnOrder"][0]
        self.game["players"][actor]["hasStolen"] = True
        self.game["players"][actor]["hand"] = [new_card("camp_raid"), new_card("vote")]
        self.gs.rules_engine.sync_vote_counters(self.game)
        before = [c["uid"] for c in self.game["players"][actor]["hand"]]

        # No target: the effect is refused and the card must return intact.
        self.gs.play_card(self.gid, playerId=actor, cardIdx=0)

        after = [c["uid"] for c in self.game["players"][actor]["hand"]]
        self.assertEqual(before, after, "a refused play must not disturb the hand")

    # ── the reshuffle, which launders anything wrong ──────────────────────

    def test_the_discard_never_holds_a_card_without_an_identity(self):
        """The discard becomes the Draw Pile, which becomes people's hands.

        Every synthesised discard used to build a fresh `{"type": ...}` twin,
        so a played card, a spent Sorry For You, a spent Tribal Council Card and
        a played tribal advantage all entered the pile anonymous — and came back
        out, much later, into a hand.
        """
        actor = self.game["turnOrder"][0]
        self.game["players"][actor]["hasStolen"] = True
        self.game["players"][actor]["hand"] = [new_card("camp_raid")]
        self.game["players"][self.game["turnOrder"][1]]["hand"] = [new_card("vote")]
        self.gs.rules_engine.sync_vote_counters(self.game)
        self.gs.play_card(self.gid, playerId=actor, cardIdx=0,
                          params={"targetId": self.game["turnOrder"][1]})

        self.assertTrue(self.game["discard"], "something should be on the pile")
        for card in self.game["discard"]:
            self.assertTrue(card.get("uid"), f"anonymous card in the discard: {card}")

    def test_a_completed_council_leaves_no_anonymous_cards(self):
        game = self.game
        doomed = game["turnOrder"][1]
        game["players"][doomed]["characterCards"] = 1
        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.gid, "elimination")
        for voter in game["turnOrder"]:
            target = doomed if voter != doomed else game["turnOrder"][0]
            votes = max(1, game["players"][voter].get("mandatoryVotes", 1))
            self.gs.cast_vote(self.gid, voter, [{"targetId": target, "votes": votes}])
        self.gs.reveal_votes(self.gid)
        self.gs.reveal_votes(self.gid)
        self.gs.complete_tribal(
            self.gid, playerId=game["currentVote"].get("councilLeaderId"))

        for card in (game.get("discard") or []):
            self.assertTrue(card.get("uid"), f"anonymous card in the discard: {card}")
        uids = all_uids(game)
        self.assertEqual(len(uids), len(set(uids)))

    # ── the safety net ────────────────────────────────────────────────────

    def test_a_saved_game_from_before_uids_is_healed_on_load(self):
        for player in self.game["players"].values():
            for card in player.get("hand") or []:
                card.pop("uid", None)
        for card in (self.game.get("deck") or []):
            card.pop("uid", None)
        self.gs._save(self.gid)

        reloaded = GameState()
        healed = reloaded.games[self.gid]
        uids = all_uids(healed)
        self.assertTrue(all(uids), "every legacy card gains an identity")
        self.assertEqual(len(uids), len(set(uids)))

    def test_the_backfill_is_idempotent(self):
        before = all_uids(self.game)
        self.assertEqual(ensure_card_uids(self.game), 0, "nothing left to mint")
        self.assertEqual(all_uids(self.game), before, "and nothing was disturbed")

    def test_no_card_ever_reaches_a_client_anonymous(self):
        """The last line of defence, for hands injected directly."""
        pid = self.ids[0]
        self.game["players"][pid]["hand"] = [{"type": "vote"}, {"type": "camp_raid"}]

        state = self.gs.get_game_state(self.gid)

        for card in state["players"][pid]["hand"]:
            self.assertTrue(card.get("uid"))
        # Stable across reads — a uid that changed per broadcast would be no
        # identity at all.
        again = self.gs.get_game_state(self.gid)
        self.assertEqual([c["uid"] for c in state["players"][pid]["hand"]],
                         [c["uid"] for c in again["players"][pid]["hand"]])

    def test_the_test_hooks_mint_identities_too(self):
        pid = self.ids[0]
        import survivor_server
        survivor_server.game_state = self.gs
        survivor_server.app.config['TESTING'] = True
        client = survivor_server.app.test_client()
        res = client.post('/api/test/set_hand',
                          json={"gameId": self.gid, "playerId": pid,
                                "hand": ["vote", "camp_raid"]})
        if res.status_code == 404:
            self.skipTest("test hooks are not enabled in this process")
        for card in self.game["players"][pid]["hand"]:
            self.assertTrue(card.get("uid"))


if __name__ == '__main__':
    unittest.main(verbosity=2)
