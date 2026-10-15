#!/usr/bin/env python3
"""
HTTP-layer hardening — regressions from the 2026-10-15 code review.

The service worker that never changed between deploys, the HttpOnly cookie
"Forget this island" could not forget, client-IP headers trusted from anyone,
a Discord link-code claim budget keyed on an id the caller picks, ids that
weren't strings reaching the game methods, and a pace gate that pre-empted
its own rule.
"""

import importlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_app():
    os.environ.pop('SURVIVOR_ACCESS_CODE', None)
    os.environ.pop('SURVIVOR_REVIEW_ACCESS_CODE', None)
    import survivor_server
    importlib.reload(survivor_server)
    survivor_server.game_state = survivor_server.GameState()
    survivor_server.app.config['TESTING'] = True
    return survivor_server


class HttpHardeningTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        cls.server = make_app()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.client = self.server.app.test_client()

    def new_game(self, humans=3):
        gid = self.client.post('/api/game/create', json={}).get_json()['gameId']
        pids = []
        for i, color in enumerate(["red", "blue", "green", "yellow"][:humans]):
            r = self.client.post('/api/player/join',
                                 json={'gameId': gid, 'name': f'Player{i}',
                                       'color': color}).get_json()
            self.assertTrue(r['success'], r)
            pids.append(r['playerId'])
        return gid, pids

    # ── the service worker changes with every client build ──

    def test_sw_is_stamped_with_the_build_and_revalidated(self):
        r = self.client.get('/sw.js')
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertNotIn('__BUILD__', body)
        self.assertIn(self.server.CLIENT_BUILD, body)
        self.assertEqual(r.headers.get('Cache-Control'), 'no-cache')
        self.assertIn('javascript', r.headers.get('Content-Type', ''))

    def test_the_shell_is_revalidated(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get('Cache-Control'), 'no-cache')

    def test_ping_reports_the_build_and_nothing_about_games(self):
        data = self.client.get('/api/ping').get_json()
        self.assertEqual(data['build'], self.server.CLIENT_BUILD)
        self.assertNotIn('server_info', data)

    # ── access ──

    def test_forget_clears_the_access_cookie(self):
        r = self.client.post('/api/access/forget')
        self.assertEqual(r.status_code, 200)
        cookies = r.headers.getlist('Set-Cookie')
        self.assertTrue(any(c.startswith(f'{self.server.ACCESS_COOKIE}=;') for c in cookies),
                        cookies)

    def test_forwarded_ip_headers_are_trusted_only_from_loopback(self):
        app = self.server.app
        with app.test_request_context('/', headers={'CF-Connecting-IP': '203.0.113.9'},
                                      environ_base={'REMOTE_ADDR': '127.0.0.1'}):
            self.assertEqual(self.server._client_ip(), '203.0.113.9')
        with app.test_request_context('/', headers={'CF-Connecting-IP': '203.0.113.9'},
                                      environ_base={'REMOTE_ADDR': '192.168.1.40'}):
            self.assertEqual(self.server._client_ip(), '192.168.1.40')

    def test_a_full_throttle_map_keeps_its_throttled_entries(self):
        import time
        bucket = {f'ip{i}': [time.time() - 3600] for i in range(self.server._RATE_BUCKET_MAX)}
        bucket['guesser'] = [time.time()] * 10
        bucket['one-more'] = [time.time()]
        self.server._prune_bucket(bucket, time.time(), 60.0)
        self.assertIn('guesser', bucket)
        self.assertLessEqual(len(bucket), self.server._RATE_BUCKET_MAX)

    # ── Discord link-code claims can't be swept ──

    def test_rotating_the_discord_id_does_not_reset_the_claim_budget(self):
        self.server._claim_failures.clear()
        self.server._claim_failures_global.clear()
        statuses = []
        for i in range(self.server._CLAIM_FAIL_PER_IP + 2):
            r = self.client.post('/api/discord/link/claim',
                                 json={'code': f'NOPE-{i:03d}', 'discordUserId': str(10_000 + i)})
            statuses.append(r.status_code)
        self.assertEqual(statuses[-1], 429, statuses)
        self.server._claim_failures.clear()
        self.server._claim_failures_global.clear()

    # ── handle(): ids are strings ──

    def test_a_list_where_an_id_belongs_is_refused_cleanly(self):
        gid, pids = self.new_game()
        r = self.client.post('/api/turn/play_card',
                             json={'gameId': gid, 'playerId': [pids[0]], 'cardIdx': 0})
        self.assertEqual(r.status_code, 400)
        self.assertIn('playerId', r.get_json()['message'])

    def test_a_crash_does_not_echo_internals(self):
        gid, pids = self.new_game()
        original = self.server.game_state.rename_player

        def boom(*a, **k):
            raise RuntimeError("secret internals at /Users/someone")
        self.server.game_state.rename_player = boom
        try:
            r = self.client.post('/api/player/rename',
                                 json={'gameId': gid, 'playerId': pids[0], 'newName': 'Zed'})
        finally:
            self.server.game_state.rename_player = original
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('secret', r.get_json()['message'])

    # ── the story so far is current for everyone ──

    def test_the_broadcast_state_already_holds_the_new_log_line(self):
        gid, pids = self.new_game()
        sent = []
        original = self.server.socketio.emit

        def capture(event, data=None, *a, **k):
            if event == 'state_update':
                sent.append(data)
        self.server.socketio.emit = capture
        try:
            r = self.client.post('/api/game/start_full',
                                 json={'gameId': gid, 'playerId': pids[0]}).get_json()
        finally:
            self.server.socketio.emit = original
        self.assertTrue(r['success'], r)
        self.assertTrue(sent)
        logged = [e['msg'] for e in sent[-1].get('eventLog', [])]
        self.assertTrue(any('started' in m.lower() for m in logged), logged)

    # ── pace: any human may set it while a bot leads ──

    def test_humans_can_set_the_pace_under_a_bot_leader(self):
        gid, pids = self.new_game(humans=2)
        bot = self.client.post('/api/player/add_bot', json={'gameId': gid}).get_json()
        self.assertTrue(bot['success'], bot)
        game = self.server.game_state.games[gid]
        bot_id = next(p for p, pl in game['players'].items() if pl.get('isBot'))
        self.client.post('/api/game/start_full', json={'gameId': gid, 'playerId': pids[0]})
        self.server.game_state._trigger_tribal_council(game, 'single', drawer_id=bot_id)

        r = self.client.post('/api/game/update_settings',
                             json={'gameId': gid, 'playerId': pids[1],
                                   'settings': {'tribalPace': 'relaxed'}})
        self.assertEqual(r.status_code, 200, r.get_json())

    # ── the voice bot is pointed at tonight's game ──

    def test_voice_active_puts_the_live_recent_game_first(self):
        import time
        games = self.server.game_state.games
        old_gid, old_pids = self.new_game()
        new_gid, new_pids = self.new_game()
        for gid, pids, age in ((old_gid, old_pids, 3600), (new_gid, new_pids, 60)):
            games[gid]['players'][pids[0]]['discordUserId'] = '123456789'
            games[gid]['phase'] = 'playing'
            games[gid]['lastActivity'] = time.time() - age
        # An id that sorts first must not win on the id alone
        listed = [g['gameId'] for g in
                  self.client.get('/api/voice/active').get_json()['games']]
        self.assertLess(listed.index(new_gid), listed.index(old_gid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
