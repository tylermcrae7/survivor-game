#!/usr/bin/env python3
"""
Access gate tests — the shared "island code" that protects the public tunnel.

The gate is entirely env-driven: SURVIVOR_ACCESS_CODE set means every /api/*
call and socket connection needs the signed cookie from POST /api/access;
unset means LAN/dev/test play is completely unaffected.
"""

import importlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_app(access_code):
    """(Re)import survivor_server with the gate env var set/unset."""
    if access_code is None:
        os.environ.pop('SURVIVOR_ACCESS_CODE', None)
    else:
        os.environ['SURVIVOR_ACCESS_CODE'] = access_code

    import survivor_server
    importlib.reload(survivor_server)
    survivor_server.game_state = survivor_server.GameState()
    survivor_server.app.config['TESTING'] = True
    return survivor_server


class GateDisabledTest(unittest.TestCase):
    """No env var -> no gate. LAN play, dev and the rest of the suite rely on this."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        cls.server = make_app(None)
        cls.client = cls.server.app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_api_open_without_cookie(self):
        response = self.client.get('/api/cards')
        self.assertEqual(response.status_code, 200)

        response = self.client.post('/api/game/create', json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])

    def test_check_reports_ungated(self):
        data = self.client.get('/api/access/check').get_json()
        self.assertFalse(data['gated'])
        self.assertTrue(data['ok'])

    def test_access_post_is_a_noop(self):
        response = self.client.post('/api/access', json={'code': 'anything'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])


class GateEnabledTest(unittest.TestCase):
    CODE = 'torch-idol-8352'

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        cls.server = make_app(cls.CODE)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop('SURVIVOR_ACCESS_CODE', None)

    def setUp(self):
        self.client = self.server.app.test_client()
        self.server._access_attempts.clear()

    def unlock(self, client=None, code=None):
        client = client or self.client
        return client.post('/api/access', json={'code': code or self.CODE})

    # ── enforcement ──

    def test_api_calls_401_without_the_cookie(self):
        for path, method, body in [
            ('/api/cards', 'GET', None),
            ('/api/game/create', 'POST', {}),
            ('/api/winners', 'GET', None),
            ('/api/game/deadbeef/state', 'GET', None),
            # The Discord bot's poll endpoint is no more public than the rest
            ('/api/voice/plan/deadbeef', 'GET', None),
            ('/api/place/move', 'POST', {}),
        ]:
            response = (self.client.get(path) if method == 'GET'
                        else self.client.post(path, json=body))
            self.assertEqual(response.status_code, 401, path)
            data = response.get_json()
            self.assertTrue(data.get('gated'), path)

    def test_pages_and_assets_stay_fetchable(self):
        # The app shell holds no game data; the client renders its own gate.
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/styles.css')
        self.assertEqual(response.status_code, 200)

    def test_ping_and_gate_endpoints_are_exempt(self):
        self.assertEqual(self.client.get('/api/ping').status_code, 200)
        self.assertEqual(self.client.get('/api/access/check').status_code, 200)

    def test_check_reports_gated_and_not_ok(self):
        data = self.client.get('/api/access/check').get_json()
        self.assertTrue(data['gated'])
        self.assertFalse(data['ok'])

    # ── unlocking ──

    def test_wrong_code_rejected(self):
        response = self.unlock(code='wrong-code-0000')
        self.assertEqual(response.status_code, 403)
        # ...and the API stays shut
        self.assertEqual(self.client.get('/api/cards').status_code, 401)

    def test_correct_code_sets_cookie_and_opens_the_api(self):
        response = self.unlock()
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.server.ACCESS_COOKIE, response.headers.get('Set-Cookie', ''))

        # The test client carries cookies forward automatically
        self.assertEqual(self.client.get('/api/cards').status_code, 200)
        create = self.client.post('/api/game/create', json={})
        self.assertEqual(create.status_code, 200)

        data = self.client.get('/api/access/check').get_json()
        self.assertTrue(data['gated'])
        self.assertTrue(data['ok'])

    def test_code_comparison_is_case_insensitive(self):
        response = self.unlock(code=self.CODE.upper())
        self.assertEqual(response.status_code, 200)

    def test_forged_cookie_rejected(self):
        self.client.set_cookie(self.server.ACCESS_COOKIE, 'a' * 64)
        self.assertEqual(self.client.get('/api/cards').status_code, 401)

    def test_changing_the_code_revokes_old_cookies(self):
        self.unlock()
        self.assertEqual(self.client.get('/api/cards').status_code, 200)

        original = self.server.ACCESS_CODE
        try:
            self.server.ACCESS_CODE = 'brand-new-code-1234'
            self.assertEqual(self.client.get('/api/cards').status_code, 401,
                             "old cookies must die when the code changes")
        finally:
            self.server.ACCESS_CODE = original

    # ── brute force ──

    def test_rate_limit_kicks_in(self):
        for _ in range(self.server._ACCESS_ATTEMPT_LIMIT):
            self.unlock(code='nope')
        response = self.unlock(code='nope')
        self.assertEqual(response.status_code, 429)

        # ...even for the RIGHT code, once the budget is burned
        response = self.unlock()
        self.assertEqual(response.status_code, 429)

    def test_rate_limit_is_per_ip(self):
        for _ in range(self.server._ACCESS_ATTEMPT_LIMIT + 1):
            self.client.post('/api/access', json={'code': 'nope'},
                             headers={'CF-Connecting-IP': '198.51.100.7'})
        response = self.client.post('/api/access', json={'code': self.CODE},
                                    headers={'CF-Connecting-IP': '203.0.113.9'})
        self.assertEqual(response.status_code, 200,
                         "a different visitor must not inherit the attacker's limit")


if __name__ == '__main__':
    print("🔐 Testing the access gate")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    # Order matters: the reload in GateEnabledTest must run after the
    # disabled-mode assertions have finished with the module.
    suite.addTests(loader.loadTestsFromTestCase(GateDisabledTest))
    suite.addTests(loader.loadTestsFromTestCase(GateEnabledTest))

    result = unittest.TextTestRunner(verbosity=2, buffer=True).run(suite)

    print(f"\n📋 Access Gate Test Summary:")
    print(f"✅ Tests Run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"⚠️  Errors: {len(result.errors)}")
    for test, _ in result.failures:
        print(f"  FAIL: {test}")
    for test, _ in result.errors:
        print(f"  ERROR: {test}")

    success = not result.failures and not result.errors
    print(f"\n🎉 All access gate tests {'PASSED' if success else 'FAILED'}!")
    sys.exit(0 if success else 1)
