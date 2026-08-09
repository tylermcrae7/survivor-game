#!/usr/bin/env python3
"""Task B2: Universal Links — the AASA file a tapped https:// link needs to
open the app instead of Safari.

Served from an explicit Flask route (not static-file serving) so the
Content-Type and status are guaranteed, at both the well-known and the
legacy bare path, and — the point most likely to regress silently — even
when the access gate is up. Apple's fetcher carries no cookie.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import survivor_server

EXPECTED_CONTENT = {
    "applinks": {
        "details": [{
            "appIDs": ["M5H3893R7A.mctech.SurvivorGame"],
            "components": [{"/": "/join/*"}, {"/": "/", "?": {"join": "*"}}],
        }]
    }
}


class AASARouteTest(unittest.TestCase):
    def setUp(self):
        survivor_server.app.config['TESTING'] = True
        self.client = survivor_server.app.test_client()

    def _assert_ok_json(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response.content_type)
        return response.get_json()

    def test_well_known_path(self):
        body = self._assert_ok_json(
            self.client.get('/.well-known/apple-app-site-association'))
        self.assertEqual(body, EXPECTED_CONTENT)

    def test_bare_legacy_path(self):
        body = self._assert_ok_json(
            self.client.get('/apple-app-site-association'))
        self.assertEqual(body, EXPECTED_CONTENT)

    def test_app_id_present(self):
        body = self.client.get('/.well-known/apple-app-site-association').get_json()
        self.assertIn('M5H3893R7A.mctech.SurvivorGame',
                      body['applinks']['details'][0]['appIDs'])

    def test_no_redirect(self):
        response = self.client.get('/.well-known/apple-app-site-association',
                                   follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(response.status_code, (301, 302, 307, 308))


class AASASurvivesTheAccessGateTest(unittest.TestCase):
    """A future gate change that swallows this file must fail a test, not
    surface months later as "links stopped opening the app" — see Task B2."""

    def setUp(self):
        survivor_server.app.config['TESTING'] = True
        self.client = survivor_server.app.test_client()
        self.original_code = survivor_server.ACCESS_CODE

    def tearDown(self):
        survivor_server.ACCESS_CODE = self.original_code

    def test_served_with_the_gate_up_and_no_cookie(self):
        survivor_server.ACCESS_CODE = 'test-gate-code-1234'
        self.assertTrue(survivor_server.gate_enabled())

        # The gate really is up: an ordinary API call is refused without it.
        gated = self.client.get('/api/cards')
        self.assertEqual(gated.status_code, 401)

        # The AASA route is exempt regardless — it isn't under /api/.
        response = self.client.get('/.well-known/apple-app-site-association')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response.content_type)
        self.assertEqual(response.get_json(), EXPECTED_CONTENT)

        # Same for the bare legacy path.
        response2 = self.client.get('/apple-app-site-association')
        self.assertEqual(response2.status_code, 200)


class JoinLinkRouteTest(unittest.TestCase):
    """A shared /join/CODE link must land a browser on the join form.

    Two stacked traps: Flask's built-in static route (static_url_path="")
    outranks the /<path:path> SPA fallback, so the path 404'd raw; and the
    shell's RELATIVE script srcs mean serving it AT /join/ breaks every
    script load (/join/game.js comes back as HTML). The route therefore
    REDIRECTS to /?join=CODE, which applyJoinLink already handles. A phone
    with the app installed never loads this URL — Universal Link matching
    is offline against the AASA components."""

    def setUp(self):
        survivor_server.app.config['TESTING'] = True
        self.client = survivor_server.app.test_client()

    def test_join_path_redirects_to_the_query_form(self):
        response = self.client.get('/join/ABC12345', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/?join=ABC12345')

    def test_join_path_lands_on_the_app_shell(self):
        response = self.client.get('/join/ABC12345', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.content_type)

    def test_join_path_survives_the_gate(self):
        original = survivor_server.ACCESS_CODE
        try:
            survivor_server.ACCESS_CODE = 'test-gate-code-1234'
            response = self.client.get('/join/ABC12345', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('text/html', response.content_type)
        finally:
            survivor_server.ACCESS_CODE = original


class AASAFileOnDiskTest(unittest.TestCase):
    """The physical copy under client/dist stays in sync with the route —
    `_write_aasa_file` heals it from the same constant on every import."""

    def test_file_matches_the_route_content(self):
        path = os.path.join(survivor_server.STATIC_DIR, '.well-known',
                            'apple-app-site-association')
        self.assertTrue(os.path.exists(path), path)
        with open(path) as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk, EXPECTED_CONTENT)
        self.assertEqual(on_disk, survivor_server.AASA_CONTENT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
