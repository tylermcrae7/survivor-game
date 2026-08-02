#!/usr/bin/env python3
"""
Narrator event tests — the server's running commentary.

The server broadcasts a `game_event` per notable action, and it is the only
thing that can tell a player *why* their hand just changed. Four of these
events could never fire at all, and a fifth always named the thief "Unknown":

  · `elimination`  — the before/after diff compared a shallow copy's `players`
                     dict against itself, so the set difference was always empty
  · `game_start`   — keyed on an action name ('start_game') that does not exist
  · `winner`       — `record_winner` short-circuits into the reset branch and
                     never reaches the narrator at all
  · `steal.thief`  — read `playerId`; the route requires `thiefId`
  · `steal`        — fired even when the raid moved no cards

Each test below is the one that would have caught one of those.
"""

import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import survivor_server


@contextmanager
def captured_events():
    """Collect every emit_game_event payload for the duration of the block."""
    seen = []
    real = survivor_server.socketio.emit

    def spy(event, data=None, *args, **kwargs):
        if event == 'game_event':
            seen.append(data)
        return real(event, data, *args, **kwargs)

    survivor_server.socketio.emit = spy
    try:
        yield seen
    finally:
        survivor_server.socketio.emit = real


def of_type(events, kind):
    return [e for e in events if e.get('type') == kind]


class NarratorEventTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        survivor_server.game_state = survivor_server.GameState()
        survivor_server.app.config['TESTING'] = True
        self.client = survivor_server.app.test_client()
        self.gs = survivor_server.game_state

        self.gid = self.gs.create_game()
        self.players = [self.gs.add_player(self.gid, name, color)
                        for name, color in [("Ana", "#FF6B6B"), ("Ben", "#4ECDC4"),
                                            ("Cam", "#45B7D1"), ("Dee", "#F9844A")]]

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, path, payload):
        return self.client.post(path, json=payload).get_json()

    # ── game_start ────────────────────────────────────────────────────────

    def test_starting_the_game_announces_the_tribe(self):
        with captured_events() as events:
            self.post('/api/game/start_full', {"gameId": self.gid})
        starts = of_type(events, 'game_start')
        self.assertEqual(len(starts), 1, "starting a game must narrate exactly once")
        self.assertEqual(starts[0]['count'], 4)

    # ── steal ─────────────────────────────────────────────────────────────

    def test_a_steal_names_the_thief_not_unknown(self):
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        thief = game['turnOrder'][0]
        victim = next(p for p in game['turnOrder'] if p != thief)
        # A plain hand on both sides: something to take, no Sorry For You.
        game['players'][victim]['hand'] = [{"type": "camp_raid"}, {"type": "vote"}]
        game['players'][thief]['hand'] = [{"type": "vote"}]

        with captured_events() as events:
            self.post('/api/turn/steal',
                      {"gameId": self.gid, "thiefId": thief, "targetId": victim})

        steals = of_type(events, 'steal')
        self.assertEqual(len(steals), 1)
        self.assertEqual(steals[0]['thief'], game['players'][thief]['name'])
        self.assertEqual(steals[0]['victim'], game['players'][victim]['name'])
        self.assertNotEqual(steals[0]['thief'], 'Unknown')
        # IDs ride along: two players may share a display name, and only the
        # colour is unique — a client cannot match a name back to a seat.
        self.assertEqual(steals[0]['thiefId'], thief)
        self.assertEqual(steals[0]['victimId'], victim)

    def test_a_raid_that_takes_nothing_is_not_narrated_as_a_theft(self):
        """A Vote-Card-only hand yields success, but no card moves."""
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        thief = game['turnOrder'][0]
        victim = next(p for p in game['turnOrder'] if p != thief)
        game['players'][victim]['hand'] = [{"type": "vote"}]

        with captured_events() as events:
            self.post('/api/turn/steal',
                      {"gameId": self.gid, "thiefId": thief, "targetId": victim})

        self.assertEqual(of_type(events, 'steal'), [],
                         "nothing left their hand, so nothing may be narrated")

    def test_a_pending_sorry_for_you_window_is_not_narrated_as_a_theft(self):
        """The raid may still be cancelled outright — narrating it would lie."""
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        thief = game['turnOrder'][0]
        victim = next(p for p in game['turnOrder'] if p != thief)
        game['players'][victim]['hand'] = [{"type": "sorry_for_you"}, {"type": "camp_raid"}]

        with captured_events() as events:
            self.post('/api/turn/steal',
                      {"gameId": self.gid, "thiefId": thief, "targetId": victim})

        self.assertTrue(game.get('pending_theft'), "the window should be open")
        self.assertEqual(of_type(events, 'steal'), [],
                         "a held theft is not a theft yet")

    # ── elimination ───────────────────────────────────────────────────────

    def test_a_true_elimination_is_announced(self):
        """The shallow-copy diff meant this never fired even once."""
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        doomed = game['turnOrder'][1]
        # On their last Character Card, so the vote-out ends their game.
        game['players'][doomed]['characterCards'] = 1

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.gid, "elimination")
        for voter in game['turnOrder']:
            target = doomed if voter != doomed else game['turnOrder'][0]
            # A Goodwill Gamble in hand makes the ballot mandatory-2, and a
            # short ballot is refused outright — which leaves the box unfull
            # and the reveal permanently waiting.
            votes = max(1, game['players'][voter].get('mandatoryVotes', 1))
            self.gs.cast_vote(self.gid, voter, [{"targetId": target, "votes": votes}])
        self.gs.reveal_votes(self.gid)   # seals the box
        self.gs.reveal_votes(self.gid)   # tallies

        with captured_events() as events:
            self.post('/api/tribal/complete',
                      {"gameId": self.gid,
                       "playerId": game['currentVote'].get('councilLeaderId')})

        eliminations = of_type(events, 'elimination')
        self.assertTrue(eliminations, "a snuffed torch must be announced")
        self.assertIn(doomed, [e['playerId'] for e in eliminations])
        self.assertEqual(eliminations[0]['player'], game['players'][doomed]['name'])

    def test_surviving_a_vote_out_is_not_an_elimination(self):
        """Two Character Cards means the tribe spoke, but you are still here."""
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        doomed = game['turnOrder'][1]
        game['players'][doomed]['characterCards'] = 2

        self.gs._trigger_tribal_council(game, "single")
        self.gs.start_voting(self.gid, "elimination")
        for voter in game['turnOrder']:
            target = doomed if voter != doomed else game['turnOrder'][0]
            # A Goodwill Gamble in hand makes the ballot mandatory-2, and a
            # short ballot is refused outright — which leaves the box unfull
            # and the reveal permanently waiting.
            votes = max(1, game['players'][voter].get('mandatoryVotes', 1))
            self.gs.cast_vote(self.gid, voter, [{"targetId": target, "votes": votes}])
        self.gs.reveal_votes(self.gid)
        self.gs.reveal_votes(self.gid)

        with captured_events() as events:
            self.post('/api/tribal/complete',
                      {"gameId": self.gid,
                       "playerId": game['currentVote'].get('councilLeaderId')})

        self.assertEqual(of_type(events, 'elimination'), [])

    # ── card_played ───────────────────────────────────────────────────────

    def test_a_played_card_is_named(self):
        """It used to be the literal string 'a card', always."""
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        actor = game['turnOrder'][0]
        victim = next(p for p in game['turnOrder'] if p != actor)
        game['players'][actor]['hasStolen'] = True
        game['players'][actor]['hand'] = [{"type": "camp_raid"}]
        game['players'][victim]['hand'] = [{"type": "vote"}]

        with captured_events() as events:
            self.post('/api/turn/play_card',
                      {"gameId": self.gid, "playerId": actor,
                       "cardIdx": 0, "params": {"targetId": victim}})

        plays = of_type(events, 'card_played')
        self.assertTrue(plays)
        self.assertEqual(plays[0]['card'], "Camp Raid")
        self.assertNotEqual(plays[0]['card'], "a card")

    def test_a_peeked_card_never_reaches_the_narrator(self):
        """The Spy Shack shows YOU a hand. The room must not be told."""
        self.gs.start_full_game(self.gid)
        game = self.gs.games[self.gid]
        actor = game['turnOrder'][0]
        victim = next(p for p in game['turnOrder'] if p != actor)
        game['players'][actor]['hasStolen'] = True
        game['players'][actor]['hand'] = [{"type": "the_spy_shack"}]
        game['players'][victim]['hand'] = [{"type": "immunity_idol"}, {"type": "vote"}]

        with captured_events() as events:
            self.post('/api/turn/play_card',
                      {"gameId": self.gid, "playerId": actor, "cardIdx": 0,
                       "params": {"targetId": victim, "takeIndex": 0}})

        blob = repr(events)
        self.assertNotIn("Immunity Idol", blob,
                         "a peeked card must never be broadcast to the room")
        plays = of_type(events, 'card_played')
        if plays:
            self.assertEqual(plays[0]['card'], "The Spy Shack")


if __name__ == '__main__':
    unittest.main(verbosity=2)
