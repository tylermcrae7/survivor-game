#!/usr/bin/env python3
"""Task A1: a private socket room per player.

`on_join` optionally joins `f"{gid}::{pid}"` alongside the game room, so the
server can narrate to one phone (`emit_private_event`) without the whole
table hearing it. This is a UX channel, not a security boundary — see the
comment in `on_join` — so these tests pin the shape (who gets a room, who
doesn't) rather than any claim of secrecy.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import survivor_server


class PrivateChannelTest(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(self.original_cwd, 'survivor_cards.json'), self.tmp)
        os.chdir(self.tmp)
        survivor_server.game_state = survivor_server.GameState()
        survivor_server.app.config['TESTING'] = True
        self.gs = survivor_server.game_state

        self.gid = self.gs.create_game()
        self.pid_a = self.gs.add_player(self.gid, "Ana")
        self.pid_b = self.gs.add_player(self.gid, "Ben")

        # A second game, so a real playerId from elsewhere is still a
        # stranger to `self.gid`.
        self.gid2 = self.gs.create_game()
        self.pid_c = self.gs.add_player(self.gid2, "Cam")

        self._clients = []

    def tearDown(self):
        for client in self._clients:
            if client.is_connected():
                client.disconnect()
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self):
        client = survivor_server.socketio.test_client(survivor_server.app)
        self._clients.append(client)
        return client

    def _join(self, client, gid, pid=None):
        payload = {"gameId": gid}
        if pid is not None:
            payload["playerId"] = pid
        client.emit('join', payload)

    def _game_events(self, received):
        return [p for p in received if p['name'] == 'game_event']

    def _errors(self, received):
        return [p for p in received if p['name'] == 'error']

    # ── a private event reaches only the addressed client ──────────────

    def test_private_event_reaches_only_its_own_client(self):
        client_a = self._client()
        client_b = self._client()
        self._join(client_a, self.gid, self.pid_a)
        self._join(client_b, self.gid, self.pid_b)
        client_a.get_received()  # discard the join's state_update
        client_b.get_received()

        survivor_server.emit_private_event(self.gid, self.pid_a, 'robbed',
                                            {"message": "psst, just for you"})

        events_a = self._game_events(client_a.get_received())
        events_b = self._game_events(client_b.get_received())
        self.assertEqual(len(events_a), 1)
        self.assertEqual(events_a[0]['args'][0]['type'], 'robbed')
        self.assertEqual(events_a[0]['args'][0]['message'], 'psst, just for you')
        # Same envelope as emit_game_event — no new decoder shape needed.
        self.assertIn('timestamp', events_a[0]['args'][0])
        self.assertEqual(events_b, [], "the other player must hear nothing")

    def test_two_devices_on_one_player_id_both_receive(self):
        """Correct, not a bug: the room is per-player, not per-connection."""
        client_1 = self._client()
        client_2 = self._client()
        self._join(client_1, self.gid, self.pid_a)
        self._join(client_2, self.gid, self.pid_a)
        client_1.get_received()
        client_2.get_received()

        survivor_server.emit_private_event(self.gid, self.pid_a, 'robbed', {})

        self.assertEqual(len(self._game_events(client_1.get_received())), 1)
        self.assertEqual(len(self._game_events(client_2.get_received())), 1)

    # ── missing/unknown playerId still joins the game room, no error ───

    def test_missing_player_id_still_joins_the_game_room(self):
        client = self._client()
        self._join(client, self.gid)  # no playerId key at all
        received = client.get_received()
        self.assertEqual(self._errors(received), [])
        self.assertTrue(any(p['name'] == 'state_update' for p in received))

        # Proof it's really in the game room: a broadcast reaches it.
        survivor_server.emit_game_event(self.gid, 'ping', {})
        self.assertTrue(any(p['args'][0]['type'] == 'ping'
                            for p in self._game_events(client.get_received())))

    def test_unknown_player_id_still_joins_the_game_room_without_raising(self):
        client = self._client()
        self._join(client, self.gid, "not-a-real-player-id")
        received = client.get_received()
        self.assertEqual(self._errors(received), [])
        self.assertTrue(any(p['name'] == 'state_update' for p in received))

        # The game room still works...
        survivor_server.emit_game_event(self.gid, 'ping', {})
        self.assertTrue(any(p['args'][0]['type'] == 'ping'
                            for p in self._game_events(client.get_received())))

        # ...but no private room exists for a playerId nobody recognised.
        survivor_server.emit_private_event(self.gid, "not-a-real-player-id",
                                            'robbed', {})
        self.assertEqual(self._game_events(client.get_received()), [])

    # ── a pid from a different game is refused the private room ────────

    def test_a_player_id_from_a_different_game_gets_no_private_room(self):
        client = self._client()
        # pid_c is a genuine playerId — just not a player of self.gid.
        self._join(client, self.gid, self.pid_c)
        client.get_received()

        survivor_server.emit_private_event(self.gid, self.pid_c, 'robbed',
                                            {"message": "leak?"})
        self.assertEqual(self._game_events(client.get_received()), [])

        # The game room join was unaffected by the rejected private room.
        survivor_server.emit_game_event(self.gid, 'ping', {})
        self.assertTrue(any(p['args'][0]['type'] == 'ping'
                            for p in self._game_events(client.get_received())))

    # ── emitting to a bot's room is a harmless no-op ────────────────────

    def test_emitting_to_a_player_nobody_joined_for_does_not_raise(self):
        survivor_server.emit_private_event(self.gid, self.pid_a, 'robbed', {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
