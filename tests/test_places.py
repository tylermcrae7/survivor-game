#!/usr/bin/env python3
"""
Places — where each castaway is standing, and the voice plan a Discord bot polls.

Four places exist (Camp Fire, The Beach, The Water Well, Tribal Council). Camp is
open during play so alliances can happen away from the fire; Tribal Council drags
everyone into one spot whether they want to be there or not.

The property these tests exist to protect is **derive, don't hook**: a player
record stores only the place a player *chose*, and the place they are actually
standing in is recomputed from the phase on every read. No phase transition —
and there are about nine lines that assign one — has to remember to move anybody.
Break that and the failure mode is subtle and awful: someone shows up at the
Beach during a Tribal Council they're being voted out of.

The Discord bot is an observer. Every assertion here holds with no bot on earth
connected.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from places import (PLACES, PLACE_KEYS, PLACE_LABELS, DEFAULT_PLACE,
                    place_policy, effective_place, voice_plan,
                    validate_discord_user_id)
from survivor_server import GameState


class PlacesTestBase(unittest.TestCase):
    """A started game: two humans and one computer player."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)

        self.gs = GameState()
        self.game_id = self.gs.create_game()
        self.tyler = self.gs.add_player(self.game_id, "TDawg", "#FF6B6B")
        self.ada = self.gs.add_player(self.game_id, "Ada", "#4ECDC4")
        added = self.gs.add_bot(self.game_id)
        self.assertTrue(added["success"], added.get("message"))
        self.bot = added["playerId"]
        self.gs.start_full_game(self.game_id)
        self.game = self.gs.games[self.game_id]

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def state(self):
        return self.gs.get_game_state(self.game_id)

    def place_of(self, pid):
        """Where the client is told this player is standing."""
        return self.state()["players"][pid]["place"]


class TestPlacePolicy(PlacesTestBase):
    """The phase decides what's open, and whether anyone may move at all."""

    def test_the_five_places_are_the_contract(self):
        self.assertEqual(PLACE_KEYS,
                         ("camp_fire", "the_beach", "the_water_well",
                          "tribal_council", "exile_island"))
        self.assertEqual([p["label"] for p in PLACES],
                         ["Camp Fire", "The Beach", "The Water Well",
                          "Tribal Council", "Exile Island"])

    def test_policy_for_every_verified_phase(self):
        expected = {
            "lobby":          {"open": ["camp_fire"], "forced": "camp_fire"},
            "playing":        {"open": ["camp_fire", "the_beach", "the_water_well"],
                               "forced": None},
            "tribal_council": {"open": ["tribal_council"], "forced": "tribal_council"},
            "final_tribal":   {"open": ["tribal_council"], "forced": "tribal_council"},
            "finished":       {"open": ["camp_fire"], "forced": "camp_fire"},
        }
        for phase, policy in expected.items():
            with self.subTest(phase=phase):
                self.assertEqual(place_policy({"phase": phase}), policy)

    def test_unknown_phase_falls_back_to_the_fire(self):
        """A phase nobody anticipated (the legacy "final", or one added next year)
        must still leave every player somewhere real."""
        for phase in ("final", "something_new", None, "", 42):
            with self.subTest(phase=phase):
                self.assertEqual(place_policy({"phase": phase}),
                                 {"open": ["camp_fire"], "forced": "camp_fire"})

    def test_policy_is_a_copy_callers_cannot_corrupt(self):
        policy = place_policy({"phase": "playing"})
        policy["open"].append("the_secret_cave")
        self.assertEqual(place_policy({"phase": "playing"})["open"],
                         ["camp_fire", "the_beach", "the_water_well"])

    def test_game_state_publishes_the_policy(self):
        self.assertEqual(self.state()["placePolicy"],
                         {"open": ["camp_fire", "the_beach", "the_water_well"],
                          "forced": None})


class TestMoving(PlacesTestBase):
    """Walking around camp, and being told you can't."""

    def test_everyone_starts_at_the_camp_fire(self):
        for pid in (self.tyler, self.ada, self.bot):
            with self.subTest(player=pid):
                self.assertEqual(self.place_of(pid), DEFAULT_PLACE)
                self.assertEqual(self.place_of(pid), "camp_fire")

    def test_a_player_who_never_had_a_place_still_reads_as_camp_fire(self):
        """Games saved before this feature existed load without placeChoice."""
        del self.game["players"][self.tyler]["placeChoice"]
        self.assertEqual(self.place_of(self.tyler), "camp_fire")

    def test_moving_to_a_side_place_while_playing(self):
        result = self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.place_of(self.tyler), "the_beach")
        # ...and nobody else moved with them
        self.assertEqual(self.place_of(self.ada), "camp_fire")

    def test_every_camp_place_is_reachable(self):
        for key in ("the_beach", "the_water_well", "camp_fire"):
            with self.subTest(place=key):
                self.assertTrue(self.gs.move_place(self.game_id, playerId=self.tyler,
                                                   place=key)["success"])
                self.assertEqual(self.place_of(self.tyler), key)

    def test_tribal_council_is_not_somewhere_you_can_walk_to(self):
        """It's open only when the phase says so, and then it's compulsory."""
        result = self.gs.move_place(self.game_id, playerId=self.tyler,
                                    place="tribal_council")
        self.assertFalse(result["success"])
        self.assertEqual(self.place_of(self.tyler), "camp_fire")

    def test_moving_during_tribal_council_is_refused(self):
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        result = self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.assertFalse(result["success"])
        self.assertIn("Tribal Council", result["message"])
        self.assertEqual(self.place_of(self.tyler), "tribal_council")

    def test_moving_in_the_lobby_is_refused(self):
        lobby = self.gs.create_game()
        pid = self.gs.add_player(lobby, "Newcomer", "#F9C74F")
        result = self.gs.move_place(lobby, playerId=pid, place="the_beach")
        self.assertFalse(result["success"])

    def test_nonsense_places_are_refused(self):
        for junk in ("the_secret_cave", "", None, 7, "CAMP_FIRE"):
            with self.subTest(place=junk):
                result = self.gs.move_place(self.game_id, playerId=self.tyler, place=junk)
                self.assertFalse(result["success"])
        self.assertEqual(self.place_of(self.tyler), "camp_fire")

    def test_unknown_game_and_player_are_refused(self):
        self.assertFalse(self.gs.move_place("nosuchgame", playerId=self.tyler,
                                            place="the_beach")["success"])
        self.assertFalse(self.gs.move_place(self.game_id, playerId="nosuchplayer",
                                            place="the_beach")["success"])

    def test_a_refused_move_changes_nothing_on_disk(self):
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_secret_cave")
        self.assertEqual(self.game["players"][self.tyler]["placeChoice"], "the_beach")


class TestDeriveDontHook(PlacesTestBase):
    """
    The point of the whole design: no phase transition moves anybody, because
    the phase is consulted at read time. These are the tests that would catch a
    future refactor that "helpfully" starts writing places on transitions.
    """

    def test_a_side_place_reads_as_tribal_council_when_the_phase_flips(self):
        self.assertTrue(self.gs.move_place(self.game_id, playerId=self.tyler,
                                           place="the_beach")["success"])
        self.assertTrue(self.gs.move_place(self.game_id, playerId=self.ada,
                                           place="the_water_well")["success"])

        # A real transition, through the real code path, with no places hook.
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)

        for pid in (self.tyler, self.ada, self.bot):
            with self.subTest(player=pid):
                self.assertEqual(self.place_of(pid), "tribal_council")
        self.assertEqual(self.state()["placePolicy"],
                         {"open": ["tribal_council"], "forced": "tribal_council"})

    def test_the_choice_survives_the_council_and_camp_reopens_to_it(self):
        """You were at the Beach before the torches were lit; you're back at the
        Beach when camp reopens. Nothing had to remember that for you."""
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        self.assertEqual(self.place_of(self.tyler), "tribal_council")

        self.gs.reset_tribal_council(self.game_id)
        self.assertEqual(self.game["phase"], "playing")
        self.assertEqual(self.place_of(self.tyler), "the_beach")

    def test_no_transition_ever_rewrites_the_stored_choice(self):
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_water_well")
        for phase in ("tribal_council", "final_tribal", "finished", "lobby",
                      "playing", "final"):
            with self.subTest(phase=phase):
                self.game["phase"] = phase
                self.state()  # a read must never mutate the stored choice
                self.assertEqual(self.game["players"][self.tyler]["placeChoice"],
                                 "the_water_well")

    def test_the_effective_place_is_always_open_under_the_policy(self):
        """Whatever the phase, whatever the stale choice, nobody is ever
        standing somewhere the policy doesn't allow."""
        for stored in list(PLACE_KEYS) + ["the_secret_cave", None, 7]:
            for phase in ("lobby", "playing", "tribal_council", "final_tribal",
                          "finished", "final", "brand_new_phase"):
                with self.subTest(stored=stored, phase=phase):
                    game = {"phase": phase}
                    player = {"placeChoice": stored}
                    policy = place_policy(game)
                    where = effective_place(game, player)
                    self.assertIn(where, policy["open"])
                    if policy["forced"]:
                        self.assertEqual(where, policy["forced"])

    def test_final_tribal_also_forces_everyone_together(self):
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.game["phase"] = "final_tribal"
        self.assertEqual(self.place_of(self.tyler), "tribal_council")

    def test_a_finished_season_puts_everyone_back_at_the_fire(self):
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.game["phase"] = "finished"
        self.assertEqual(self.place_of(self.tyler), "camp_fire")


class TestVoicePlan(PlacesTestBase):
    """The bot's poll payload."""

    def test_shape_matches_the_published_contract(self):
        plan = voice_plan(self.game)
        self.assertEqual(set(plan), {"gameId", "phase", "version", "policy", "places"})
        self.assertEqual(plan["gameId"], self.game_id)
        self.assertEqual(plan["phase"], "playing")
        self.assertEqual(plan["policy"], place_policy(self.game))
        self.assertEqual(len(plan["version"]), 12)
        for place in plan["places"]:
            self.assertEqual(set(place), {"key", "label", "players"})
            for player in place["players"]:
                self.assertEqual(set(player),
                                 {"playerId", "name", "discordUserId", "eliminated"})

    def test_every_place_appears_even_when_empty(self):
        plan = voice_plan(self.game)
        self.assertEqual([p["key"] for p in plan["places"]], list(PLACE_KEYS))
        self.assertEqual([p["label"] for p in plan["places"]],
                         [PLACE_LABELS[k] for k in PLACE_KEYS])
        empty = [p["key"] for p in plan["places"] if not p["players"]]
        self.assertIn("the_beach", empty)
        self.assertIn("tribal_council", empty)

    def test_computer_players_are_left_out_entirely(self):
        """A bot has no Discord presence to move."""
        listed = {pl["playerId"] for place in voice_plan(self.game)["places"]
                  for pl in place["players"]}
        self.assertEqual(listed, {self.tyler, self.ada})
        self.assertNotIn(self.bot, listed)

    def test_it_reports_who_is_where(self):
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        by_key = {p["key"]: p for p in voice_plan(self.game)["places"]}
        self.assertEqual([pl["name"] for pl in by_key["the_beach"]["players"]], ["TDawg"])
        self.assertEqual([pl["name"] for pl in by_key["camp_fire"]["players"]], ["Ada"])

    def test_the_plan_follows_the_phase_with_no_hooks(self):
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        by_key = {p["key"]: p for p in voice_plan(self.game)["places"]}
        self.assertEqual(len(by_key["tribal_council"]["players"]), 2)
        self.assertEqual(by_key["the_beach"]["players"], [])

    def test_version_is_stable_when_nothing_changes(self):
        first = voice_plan(self.game)["version"]
        self.assertEqual(voice_plan(self.game)["version"], first)
        # Churn that the bot must not react to: a card drawn, a turn ended.
        self.game["currentTurnIndex"] = (self.game["currentTurnIndex"] + 1) % 3
        self.game["lastActivity"] = self.game["lastActivity"] + 60
        self.assertEqual(voice_plan(self.game)["version"], first)

    def test_version_changes_when_a_player_moves(self):
        before = voice_plan(self.game)["version"]
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        after = voice_plan(self.game)["version"]
        self.assertNotEqual(before, after)
        # ...and moving back returns to the original hash
        self.gs.move_place(self.game_id, playerId=self.tyler, place="camp_fire")
        self.assertEqual(voice_plan(self.game)["version"], before)

    def test_version_changes_when_the_phase_forces_a_regroup(self):
        before = voice_plan(self.game)["version"]
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        self.assertNotEqual(voice_plan(self.game)["version"], before)

    def test_version_changes_when_a_discord_link_appears(self):
        before = voice_plan(self.game)["version"]
        self.game["players"][self.ada]["discordUserId"] = "123456789012345678"
        self.assertNotEqual(voice_plan(self.game)["version"], before)

    def test_the_plan_is_json_serializable(self):
        json.dumps(voice_plan(self.game))


class TestDiscordUserId(PlacesTestBase):
    """Snowflakes ride along on the player record; nothing depends on them."""

    def test_validator_accepts_a_snowflake(self):
        self.assertEqual(validate_discord_user_id("123456789012345678"),
                         ("123456789012345678", None))
        self.assertEqual(validate_discord_user_id("  123456789012345678  "),
                         ("123456789012345678", None))

    def test_validator_treats_absent_and_empty_as_unlinked(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(validate_discord_user_id(value), (None, None))

    def test_validator_refuses_nonsense(self):
        for junk in ("not-a-snowflake", "12345", "1234567890123456789012345678",
                     "12345678901234567x", "<@123456789012345678>"):
            with self.subTest(value=junk):
                value, error = validate_discord_user_id(junk)
                self.assertIsNone(value)
                self.assertTrue(error)

    def test_validator_refuses_numbers(self):
        """A JS client that sent this unquoted already lost digits to float
        precision — better to refuse it than to store a wrong id."""
        value, error = validate_discord_user_id(123456789012345678)
        self.assertIsNone(value)
        self.assertTrue(error)

    def test_players_default_to_no_discord_link(self):
        state = self.state()
        for pid in (self.tyler, self.ada, self.bot):
            with self.subTest(player=pid):
                self.assertIsNone(state["players"][pid]["discordUserId"])

    def test_legacy_players_report_null_rather_than_missing(self):
        del self.game["players"][self.tyler]["discordUserId"]
        self.assertIsNone(self.state()["players"][self.tyler]["discordUserId"])

    def test_add_player_stores_the_link(self):
        lobby = self.gs.create_game()
        pid = self.gs.add_player(lobby, "Linked", "#90BE6D",
                                 discordUserId="123456789012345678")
        self.assertEqual(self.gs.games[lobby]["players"][pid]["discordUserId"],
                         "123456789012345678")

    def test_computer_players_never_get_one(self):
        self.assertIsNone(self.game["players"][self.bot]["discordUserId"])


class TestPlaceRoutes(unittest.TestCase):
    """The HTTP surface the phones and the bot actually call."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        import survivor_server
        cls.server = survivor_server
        cls.server.game_state = survivor_server.GameState()
        cls.server.app.config['TESTING'] = True
        cls.client = cls.server.app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def new_game(self, players=("TDawg", "Ada", "Wren"), discord=None):
        gid = self.client.post('/api/game/create', json={}).get_json()['gameId']
        ids = []
        for name in players:
            body = {'gameId': gid, 'name': name}
            if discord and name in discord:
                body['discordUserId'] = discord[name]
            response = self.client.post('/api/player/join', json=body)
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
            ids.append(response.get_json()['playerId'])
        self.client.post('/api/game/start_full', json={'gameId': gid,
                                                       'playerId': ids[0]})
        return gid, ids

    def test_move_returns_the_full_game_state(self):
        gid, (tyler, ada, wren) = self.new_game()
        response = self.client.post('/api/place/move',
                                    json={'gameId': gid, 'playerId': tyler,
                                          'place': 'the_beach'})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body['success'])
        self.assertEqual(body['gameState']['players'][tyler]['place'], 'the_beach')
        self.assertEqual(body['gameState']['players'][ada]['place'], 'camp_fire')
        self.assertEqual(body['gameState']['placePolicy']['forced'], None)

    def test_move_rejections_carry_a_message(self):
        gid, (tyler, _, _) = self.new_game()
        response = self.client.post('/api/place/move',
                                    json={'gameId': gid, 'playerId': tyler,
                                          'place': 'the_secret_cave'})
        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertFalse(body['success'])
        self.assertTrue(body['message'])

        response = self.client.post('/api/place/move',
                                    json={'gameId': 'nosuchgame', 'playerId': tyler,
                                          'place': 'the_beach'})
        self.assertEqual(response.status_code, 404)

        response = self.client.post('/api/place/move', json={'gameId': gid})
        self.assertEqual(response.status_code, 400)

    def test_move_during_tribal_council_is_refused_over_http(self):
        gid, (tyler, _, _) = self.new_game()
        game = self.server.game_state.games[gid]
        self.server.game_state._trigger_tribal_council(game, drawer_id=tyler)
        response = self.client.post('/api/place/move',
                                    json={'gameId': gid, 'playerId': tyler,
                                          'place': 'the_beach'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['success'])

    def test_moving_around_never_floods_the_history_panel(self):
        """Movement is free and unlimited; the 120-entry event log is not."""
        gid, (tyler, _, _) = self.new_game()
        before = len(self.server.game_state.games[gid].get('eventLog', []))
        for place in ('the_beach', 'the_water_well') * 5:
            self.client.post('/api/place/move',
                             json={'gameId': gid, 'playerId': tyler, 'place': place})
        self.assertEqual(len(self.server.game_state.games[gid].get('eventLog', [])),
                         before)

    def test_voice_plan_endpoint(self):
        gid, (tyler, ada, wren) = self.new_game()
        self.client.post('/api/place/move',
                         json={'gameId': gid, 'playerId': tyler, 'place': 'the_beach'})
        response = self.client.get(f'/api/voice/plan/{gid}')
        self.assertEqual(response.status_code, 200)
        plan = response.get_json()
        self.assertEqual(plan['gameId'], gid)
        self.assertEqual(plan['phase'], 'playing')
        self.assertEqual([p['key'] for p in plan['places']], list(PLACE_KEYS))
        by_key = {p['key']: p for p in plan['places']}
        self.assertEqual([pl['playerId'] for pl in by_key['the_beach']['players']],
                         [tyler])
        self.assertEqual({pl['playerId'] for pl in by_key['camp_fire']['players']},
                         {ada, wren})

    def test_voice_plan_version_is_the_cheap_poll(self):
        gid, (tyler, _, _) = self.new_game()
        first = self.client.get(f'/api/voice/plan/{gid}').get_json()['version']
        self.assertEqual(self.client.get(f'/api/voice/plan/{gid}').get_json()['version'],
                         first)
        self.client.post('/api/place/move',
                         json={'gameId': gid, 'playerId': tyler, 'place': 'the_beach'})
        self.assertNotEqual(
            self.client.get(f'/api/voice/plan/{gid}').get_json()['version'], first)

    def test_voice_plan_excludes_bots_over_http(self):
        gid = self.client.post('/api/game/create', json={}).get_json()['gameId']
        human = self.client.post('/api/player/join',
                                 json={'gameId': gid, 'name': 'TDawg'}).get_json()['playerId']
        for _ in range(2):
            self.client.post('/api/player/add_bot', json={'gameId': gid,
                                                          'playerId': human})
        self.client.post('/api/game/start_full', json={'gameId': gid,
                                                       'playerId': human})
        plan = self.client.get(f'/api/voice/plan/{gid}').get_json()
        listed = [pl['playerId'] for place in plan['places'] for pl in place['players']]
        self.assertEqual(listed, [human])

    def test_voice_plan_for_an_unknown_game(self):
        response = self.client.get('/api/voice/plan/nosuchgame')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()['success'])

    def test_voice_plan_is_never_cached(self):
        gid, _ = self.new_game()
        response = self.client.get(f'/api/voice/plan/{gid}')
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))

    def test_discord_id_round_trips_from_join_into_game_state(self):
        gid, (tyler, ada, _) = self.new_game(discord={'TDawg': '123456789012345678'})
        state = self.client.get(f'/api/game/{gid}/state').get_json()
        self.assertEqual(state['players'][tyler]['discordUserId'], '123456789012345678')
        self.assertIsNone(state['players'][ada]['discordUserId'])
        # ...and out to the bot
        plan = self.client.get(f'/api/voice/plan/{gid}').get_json()
        linked = {pl['name']: pl['discordUserId']
                  for place in plan['places'] for pl in place['players']}
        self.assertEqual(linked['TDawg'], '123456789012345678')
        self.assertIsNone(linked['Ada'])

    def test_join_survives_a_junk_discord_id(self):
        """The link is a convenience for a voice bot. Mistyping it must not
        cost you your seat at the fire — it is reported, ignored, and the
        game goes on."""
        gid = self.client.post('/api/game/create', json={}).get_json()['gameId']
        response = self.client.post('/api/player/join',
                                    json={'gameId': gid, 'name': 'TDawg',
                                          'discordUserId': 'not-a-snowflake'})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body['success'])
        self.assertTrue(body.get('discordLinkWarning'),
                        "the client still needs to know it didn't stick")
        pid = body['playerId']
        self.assertIsNone(
            self.server.game_state.games[gid]['players'][pid]['discordUserId'],
            "garbage must never be stored as a link")

    def test_join_response_already_carries_places(self):
        gid = self.client.post('/api/game/create', json={}).get_json()['gameId']
        body = self.client.post('/api/player/join',
                                json={'gameId': gid, 'name': 'TDawg'}).get_json()
        pid = body['playerId']
        self.assertEqual(body['gameState']['players'][pid]['place'], 'camp_fire')
        self.assertEqual(body['gameState']['placePolicy'],
                         {'open': ['camp_fire'], 'forced': 'camp_fire'})

    def test_rejoin_carries_places_and_can_attach_a_discord_id(self):
        gid, (tyler, _, _) = self.new_game()
        self.client.post('/api/place/move',
                         json={'gameId': gid, 'playerId': tyler, 'place': 'the_beach'})
        response = self.client.post('/api/player/rejoin',
                                    json={'gameId': gid, 'playerId': tyler,
                                          'discordUserId': '987654321098765432'})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['gameState']['players'][tyler]['place'], 'the_beach')
        self.assertEqual(body['gameState']['players'][tyler]['discordUserId'],
                         '987654321098765432')

        # A later rejoin with no id must not unlink them
        body = self.client.post('/api/player/rejoin',
                                json={'gameId': gid, 'playerId': tyler}).get_json()
        self.assertEqual(body['gameState']['players'][tyler]['discordUserId'],
                         '987654321098765432')

    def test_rejoin_survives_a_junk_discord_id(self):
        """Same rule on the way back in: a bad link is never a locked door."""
        gid, (tyler, _, _) = self.new_game()
        response = self.client.post('/api/player/rejoin',
                                    json={'gameId': gid, 'playerId': tyler,
                                          'discordUserId': 'not-a-snowflake'})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body['success'])
        self.assertTrue(body.get('discordLinkWarning'))
        self.assertIsNone(
            self.server.game_state.games[gid]['players'][tyler]['discordUserId'])


if __name__ == '__main__':
    unittest.main(verbosity=2)


class TestBreakoutsDuringDiscussion(PlacesTestBase):
    """Tribal Council is not one room for its whole length.

    Discussion is when the scheming happens: the tribe breaks up, pairs wander
    off, and then everyone is called back to vote. Camp reopens for that one
    sub-phase — and shuts again the instant the ballot starts, which is the
    half that matters. A breakout that outlived the discussion would let two
    players agree on a name while the box is open.
    """

    def open_discussion(self):
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        self.game["currentVote"]["phase"] = "discussion"

    def subphase(self, name):
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        self.game["currentVote"]["phase"] = name

    def test_the_camp_reopens_for_discussion(self):
        self.open_discussion()
        policy = place_policy(self.game)
        self.assertIsNone(policy["forced"], "nobody is pinned during discussion")
        self.assertEqual(policy["open"],
                         ["camp_fire", "the_beach", "the_water_well"])

    def test_you_can_actually_walk_off_during_discussion(self):
        self.open_discussion()
        result = self.gs.move_place(self.game_id, playerId=self.tyler,
                                    place="the_water_well")
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.place_of(self.tyler), "the_water_well")

    def test_every_other_subphase_still_holds_the_tribe_together(self):
        for name in ("announcement", "advantage_play", "voting",
                     "immunity", "reveal"):
            with self.subTest(subphase=name):
                self.subphase(name)
                self.assertEqual(place_policy(self.game)["forced"], "tribal_council")
                refused = self.gs.move_place(self.game_id, playerId=self.tyler,
                                             place="the_beach")
                self.assertFalse(refused["success"])

    def test_the_walk_back_is_automatic_when_voting_starts(self):
        """Derive, don't hook: no transition has to remember to call anyone in."""
        self.open_discussion()
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.assertEqual(self.place_of(self.tyler), "the_beach")

        self.game["currentVote"]["phase"] = "voting"

        self.assertEqual(self.place_of(self.tyler), "tribal_council")

    def test_and_the_choice_is_still_there_at_the_next_discussion(self):
        self.open_discussion()
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        self.game["currentVote"]["phase"] = "voting"
        self.game["currentVote"]["phase"] = "discussion"
        self.assertEqual(self.place_of(self.tyler), "the_beach")

    def test_the_voice_plan_scatters_and_regroups_with_it(self):
        self.open_discussion()
        self.gs.move_place(self.game_id, playerId=self.tyler, place="the_beach")
        beach = next(p for p in voice_plan(self.game)["places"]
                     if p["key"] == "the_beach")
        self.assertEqual([p["playerId"] for p in beach["players"]], [self.tyler])

        self.game["currentVote"]["phase"] = "voting"
        council = next(p for p in voice_plan(self.game)["places"]
                       if p["key"] == "tribal_council")
        self.assertIn(self.tyler, [p["playerId"] for p in council["players"]])

    def test_the_plan_version_moves_when_the_council_reopens_camp(self):
        """Or the Discord bot never unlocks the rooms it needs to."""
        self.subphase("announcement")
        closed = voice_plan(self.game)["version"]
        self.game["currentVote"]["phase"] = "discussion"
        self.assertNotEqual(voice_plan(self.game)["version"], closed)


class TestExileIsland(PlacesTestBase):
    """A torch that is out goes to Exile Island and stays there.

    The room exists so the snuffed have each other to talk to rather than
    watching the rest of a season in silence — and so they are demonstrably
    not in the room where the living are deciding who goes next. They come
    back for the Final Tribal Council, which is the reunion.
    """

    def snuff(self, pid):
        self.game["players"][pid]["isEliminated"] = True
        self.game["players"][pid]["characterCards"] = 0

    def test_a_snuffed_player_is_exiled_during_play(self):
        self.snuff(self.ada)
        policy = place_policy(self.game, self.game["players"][self.ada])
        self.assertEqual(policy["forced"], "exile_island")
        self.assertEqual(policy["open"], ["exile_island"])

    def test_the_living_are_unaffected(self):
        self.snuff(self.ada)
        policy = place_policy(self.game, self.game["players"][self.tyler])
        self.assertIsNone(policy["forced"])
        self.assertEqual(len(policy["open"]), 3)

    def test_they_cannot_walk_off_and_are_told_why(self):
        self.snuff(self.ada)
        result = self.gs.move_place(self.game_id, playerId=self.ada,
                                    place="the_beach")
        self.assertFalse(result["success"])
        self.assertIn("torch is out", result["message"])
        self.assertEqual(self.place_of(self.ada), "exile_island")

    def test_being_snuffed_exiles_them_from_wherever_they_were(self):
        self.gs.move_place(self.game_id, playerId=self.ada, place="the_water_well")
        self.assertEqual(self.place_of(self.ada), "the_water_well")

        self.snuff(self.ada)

        self.assertEqual(self.place_of(self.ada), "exile_island")

    def test_they_are_barred_from_the_councils_breakout_too(self):
        """The whole point of the request."""
        self.snuff(self.ada)
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        self.game["currentVote"]["phase"] = "discussion"

        self.assertTrue(self.gs.move_place(self.game_id, playerId=self.tyler,
                                           place="the_beach")["success"])
        self.assertFalse(self.gs.move_place(self.game_id, playerId=self.ada,
                                            place="the_beach")["success"])
        self.assertEqual(self.place_of(self.ada), "exile_island")

    def test_exile_outlasts_the_councils_that_follow(self):
        """The living are called together; the exiled are not called back."""
        self.snuff(self.ada)
        self.gs._trigger_tribal_council(self.game, drawer_id=self.tyler)
        for subphase in ("announcement", "discussion", "voting", "reveal"):
            with self.subTest(subphase=subphase):
                self.game["currentVote"]["phase"] = subphase
                self.assertEqual(self.place_of(self.tyler), "tribal_council"
                                 if subphase != "discussion" else "camp_fire")
                self.assertEqual(self.place_of(self.ada), "exile_island")

    def test_the_final_tribal_council_brings_everyone_back_together(self):
        """The one reunion: the jury and the finalists in one room."""
        self.snuff(self.ada)
        self.game["phase"] = "final_tribal"
        self.assertEqual(self.place_of(self.ada), "tribal_council")
        self.assertEqual(self.place_of(self.tyler), "tribal_council")
        policy = place_policy(self.game, self.game["players"][self.ada])
        self.assertEqual(policy["forced"], "tribal_council")

    def test_and_a_finished_season_puts_the_whole_cast_at_the_fire(self):
        self.snuff(self.ada)
        self.game["phase"] = "finished"
        self.assertEqual(self.place_of(self.ada), "camp_fire")
        self.assertEqual(self.place_of(self.tyler), "camp_fire")

    def test_the_state_carries_each_players_own_policy(self):
        self.snuff(self.ada)
        state = self.state()
        self.assertEqual(state["players"][self.ada]["placePolicy"]["forced"],
                         "exile_island")
        self.assertIsNone(state["players"][self.tyler]["placePolicy"]["forced"])
        self.assertIsNone(state["placePolicy"]["forced"],
                          "the table's policy is still the table's")

    def test_the_voice_plan_marks_them_so_the_bot_can_bar_the_door(self):
        """Moving a ghost home is a one-off; the bot needs to lock them out."""
        self.snuff(self.ada)
        plan = voice_plan(self.game)
        exile = next(p for p in plan["places"] if p["key"] == "exile_island")
        entry = next(p for p in exile["players"] if p["playerId"] == self.ada)
        self.assertTrue(entry["eliminated"])
        fire = next(p for p in plan["places"] if p["key"] == "camp_fire")
        living = next(p for p in fire["players"] if p["playerId"] == self.tyler)
        self.assertFalse(living["eliminated"])

    def test_the_plan_version_moves_when_a_torch_goes_out(self):
        before = voice_plan(self.game)["version"]
        self.snuff(self.ada)
        self.assertNotEqual(voice_plan(self.game)["version"], before)
