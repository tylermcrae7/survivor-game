#!/usr/bin/env python3

"""
UI rules-verification suite — the browser-side twin of
docs/rules-compliance-checklist.html.

Where the server suites prove the RULES are enforced, this suite proves the
INTERFACE presents and honors them: what's tappable, what's locked, what each
player can and cannot see, and that the official ceremony flows through real
screens. It drives two real browser contexts (two phones at the fire) plus a
computer player against a scratch server, using env-gated test hooks
(SURVIVOR_TEST_HOOKS=1) to stage deterministic hands.

Run:  .venv/bin/python tests/ui/test_ui_rules_checklist.py
Needs: pip install playwright && playwright install chromium
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORT = 8097
BASE = f"http://localhost:{PORT}"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP: playwright not installed (pip install playwright)")
    sys.exit(0)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {str(detail)[:90]}" if detail else ""))


def api(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {}


def state(gid):
    return api(f"/api/game/{gid}/state")


def wait_for(fn, timeout=12, interval=0.25, desc="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(interval)
    return None


def jsclick(page, sel, text=None):
    """Click the first element matching sel (optionally containing text) via JS —
    the app's transient loading overlay makes strict hit-testing flaky."""
    return page.evaluate(
        """([sel, text]) => {
            const els = [...document.querySelectorAll(sel)];
            const el = text ? els.find(e => e.textContent.includes(text)) : els[0];
            if (!el) return false;
            el.click();
            return true;
        }""", [sel, text])


def jsfill(page, sel, value):
    page.evaluate(
        """([sel, value]) => {
            const el = document.querySelector(sel);
            if (el) { el.value = value; el.dispatchEvent(new Event('input')); }
        }""", [sel, value])


def pointer_tap(page, sel, text=None):
    """Dispatch a real pointerup (vote targets listen for pointerup, not click)."""
    return page.evaluate(
        """([sel, text]) => {
            const els = [...document.querySelectorAll(sel)];
            const el = text ? els.find(e => e.textContent.includes(text)) : els[0];
            if (!el) return false;
            el.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
            el.click();
            return true;
        }""", [sel, text])


def ui_vote(page, gid, voter_id, target_text):
    """Tap a vote-target until the ballot registers (renders can race taps)."""
    for _ in range(6):
        cv = (state(gid).get("currentVote") or {})
        if voter_id in (cv.get("votes") or {}):
            return True
        wait_for(lambda: page.locator('.vote-target').count() >= 1, 6)
        pointer_tap(page, '.vote-target', target_text)
        time.sleep(0.7)
    print(f"   [ui_vote] ballot never registered: screen={active_screen(page)}")
    return voter_id in ((state(gid).get("currentVote") or {}).get("votes") or {})


def toast_text(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('#toastContainer > *, .toast')]"
        ".map(t => t.textContent.trim()).join(' | ')")


def active_screen(page):
    return page.evaluate("() => document.querySelector('.screen.active')?.id")


def guidance(page):
    return page.evaluate(
        "() => document.getElementById('phaseGuidance')?.textContent"
        ".replace(/\\s+/g,' ').trim() || ''")


def narrator_entries(page):
    """Newest-first list of the narrator's typed-out history lines — the DOM
    a game_event narration actually lands in once bindEvents() hears it."""
    return page.evaluate(
        "() => [...document.querySelectorAll("
        "'#narratorHistory .narrator-history-entry .history-message')]"
        ".map(e => e.textContent)")


def main():
    # ── Scratch server in an isolated working directory ──
    workdir = tempfile.mkdtemp()
    env = {**os.environ, "PORT": str(PORT), "SURVIVOR_BOT_DELAY": "0.2",
           "SURVIVOR_TEST_HOOKS": "1"}
    server = subprocess.Popen(
        [os.path.join(REPO, ".venv/bin/python"),
         os.path.join(REPO, "survivor_server.py")],
        cwd=workdir, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_for(lambda: api("/api/ping").get("success"), 20,
                        desc="server up"), "scratch server did not start"
        run_checks()
    finally:
        server.terminate()

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"=== {passed}/{len(results)} UI checks passed ===")
    if passed != len(results):
        for name, ok, detail in results:
            if not ok:
                print(f"  ✗ {name} — {detail}")
        sys.exit(1)


def run_checks():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ana_ctx = browser.new_context(viewport={"width": 390, "height": 844})
        ben_ctx = browser.new_context(viewport={"width": 390, "height": 844})
        ana = ana_ctx.new_page()
        ben = ben_ctx.new_page()
        ana.goto(BASE)
        ben.goto(BASE)
        ana.wait_for_selector('[data-action="createGame"]')

        # ══════════════ U1 · Lobby rules ══════════════
        # "Light the Fire" only reveals the confirm panel now (W1: a click used
        # to create a game outright) — the explicit confirm is what actually
        # calls POST /game/create.
        jsclick(ana, '[data-action="createGame"]')
        ana.wait_for_selector('[data-action="confirmCreateGame"]')
        check("new game: Extended deck advertises six house cards",
              "+6 house cards" in ana.locator('[data-deck="extended"]').inner_text())
        jsclick(ana, '[data-action="confirmCreateGame"]')
        ana.wait_for_selector('#gameCodeInput')
        gid = ana.input_value('#gameCodeInput')
        jsclick(ana, '#colorSelection .color-btn[data-color="#FF6B6B"]')
        jsfill(ana, '#playerNameInput', 'Ana')
        jsclick(ana, '.screen.active button[data-action="joinGame"]')
        wait_for(lambda: active_screen(ana) == 'lobbyScreen')

        # Begin with fewer than 3 is refused (rulebook: 3–6 players)
        jsclick(ana, '[data-action="startFullGame"]')
        time.sleep(1.0)
        check("lobby: cannot begin with fewer than 3 players",
              active_screen(ana) == 'lobbyScreen', active_screen(ana))

        # Rename is available in the lobby (pencil next to your own name)
        check("lobby: rename pencil visible before the game starts",
              ana.locator('[data-action="renameSelf"]').count() == 1)

        # Add a computer player from the lobby UI
        jsclick(ana, '[data-action="addBot"]')
        wait_for(lambda: ana.locator('#playerList .bot-badge').count() == 1)
        check("lobby: computer player joins with a bot badge",
              ana.locator('#playerList .bot-badge').count() == 1)
        check("lobby: bot has a remove button (lobby only)",
              ana.locator('[data-action="removeBot"]').count() == 1)

        # Ben joins from his own phone
        jsclick(ben, '[data-action="showJoinForm"]')
        jsfill(ben, '#gameCodeInput', gid)
        jsfill(ben, '#playerNameInput', 'Ben')
        jsclick(ben, '#colorSelection .color-btn[data-color="#45B7D1"]')
        jsclick(ben, '.screen.active button[data-action="joinGame"]')
        wait_for(lambda: active_screen(ben) == 'lobbyScreen')
        wait_for(lambda: ana.locator('#playerList .player-card').count() == 3)
        check("lobby: all three players visible on every phone",
              ana.locator('#playerList .player-card').count() == 3
              and ben.locator('#playerList .player-card').count() == 3)

        g = state(gid)
        ids = {p["name"]: pid for pid, p in g["players"].items()}
        ana_id, ben_id = ids["Ana"], ids["Ben"]
        bot_id = next(pid for pid, p in g["players"].items() if p.get("isBot"))

        # ══════════════ U2 · Turn discipline in the interface ══════════════
        jsclick(ana, '[data-action="startFullGame"]')
        wait_for(lambda: active_screen(ana) == 'playingScreen')
        check("turn: game starts into the playing screen on every phone",
              wait_for(lambda: active_screen(ben) == 'playingScreen') is not None)

        # Deterministic hands for the scenario
        # Ana keeps a spare Action Card at the back: Sorry For You forces her to
        # discard 1, and it always comes off her non-Vote cards (the Vote Card is
        # out of the card economy's reach). The spare is what she pays, so the
        # three cards the later checks click on all survive.
        api("/api/test/set_hand", {"gameId": gid, "playerId": ana_id,
            "hand": ["camp_raid", "the_spy_shack", "immunity_idol",
                     "inheritance_red", "vote"]})
        api("/api/test/set_hand", {"gameId": gid, "playerId": ben_id,
            "hand": ["sorry_for_you", "vote"]})
        api("/api/test/set_hand", {"gameId": gid, "playerId": bot_id, "hand": ["vote"]})
        time.sleep(0.6)

        check("turn: guidance opens on the Steal step",
              wait_for(lambda: 'Steal' in guidance(ana)) is not None, guidance(ana))
        check("turn: tribe rows are tappable steal targets",
              ana.locator('.lives-row.steal-target').count() >= 2)
        check("info: every phone always shows every player's card count",
              ben.evaluate("() => [...document.querySelectorAll('.lives-row')]"
                           ".every(r => /\\d/.test(r.textContent))"))

        # Ana raids Ben — Ben holds Sorry For You, so HIS phone gets the choice
        jsclick(ana, '.lives-row.steal-target', 'Ben')
        raid = wait_for(lambda: ben.locator('.raid-dialog').count() and
                        ben.locator('.raid-dialog').inner_text(), desc="raid dialog")
        check("sorry-for-you: the defender's phone shows the raid dialog", bool(raid), raid)
        jsclick(ben, '[data-raid="play"]')
        wait_for(lambda: ben.locator('.raid-dialog').count() == 0)

        # Ana owes the penalty, and she picks what pays it. The Guide's own
        # advice: hold an Inheritance for a colour nobody is playing and feed
        # it to a Sorry For You. That was impossible while the engine took the
        # last takeable card without asking.
        penalty = wait_for(lambda: ana.locator('.penalty-discard').count() and
                           ana.locator('.penalty-discard').inner_text(),
                           desc="penalty discard dialog")
        check("sorry-for-you: the raider chooses which card they give up",
              bool(penalty), penalty)
        check("sorry-for-you: the Vote Card is never on the menu",
              'Vote' not in (penalty or ''), penalty)
        jsclick(ana, '.cardname-option', 'Inheritance')
        wait_for(lambda: ana.locator('.penalty-discard').count() == 0)

        g = state(gid)
        ana_hand = [c.get("type") for c in g["players"][ana_id]["hand"]]
        check("sorry-for-you: the block resolves — thief got nothing",
              not any(c.get("type") == "sorry_for_you"
                      for c in g["players"][ana_id]["hand"]),
              ana_hand)
        check("sorry-for-you: the card she chose is the card she lost",
              "inheritance_red" not in ana_hand and "camp_raid" in ana_hand, ana_hand)
        check("turn: steal step consumed, guidance moves to Play",
              wait_for(lambda: 'Play' in guidance(ana)) is not None, guidance(ana))

        # Card sheet: a tribal-only card is locked on a normal turn
        jsclick(ana, '.card-mini', 'Immunity Idol')
        ana.wait_for_selector('.card-sheet')
        sheet = ana.locator('.card-sheet').inner_text()
        check("sheet: a tribal-only card offers no Play button on a normal turn",
              ana.locator('#cardSheetPlayBtn').count() == 0
              and 'Not playable right now' in sheet, sheet[:90])
        ana.keyboard.press("Escape")
        time.sleep(0.3)

        # Play Camp Raid on the bot through the sheet → trap marker appears
        jsclick(ana, '.card-mini.playable', 'Camp Raid')
        ana.wait_for_selector('#cardSheetPlayBtn')
        jsclick(ana, '#cardSheetPlayBtn')
        ana.wait_for_selector('dialog[open] .picker-hint, dialog[open]')
        jsclick(ana, 'dialog[open] button', 'Coconut')
        check("camp raid: the face-up trap marker shows on the target's row",
              wait_for(lambda: ana.locator('.raid-tag').count() >= 1) is not None)
        check("camp raid: the other phones see the marker too",
              wait_for(lambda: ben.locator('.raid-tag').count() >= 1) is not None)

        # One play per turn: the hand locks, remaining cards explain why
        check("turn: after the one play, no card shows as playable",
              wait_for(lambda: ana.locator('.card-mini.playable').count() == 0)
              is not None)
        jsclick(ana, '.card-mini', 'Spy Shack')
        ana.wait_for_selector('.card-sheet')
        check("sheet: second play refused — sheet has no Play button",
              ana.locator('#cardSheetPlayBtn').count() == 0)
        ana.keyboard.press("Escape")
        time.sleep(0.3)

        # Keep the three turn-ending draws deterministic. Coconut has Ana's
        # Camp Raid in front of it; if its random draw is Sorry For You, the bot
        # correctly answers the raid and waits for Ana to choose a penalty
        # discard. That is a different flow from the unattended-bot assertion
        # below and made this test depend on the shuffled deck.
        api("/api/test/stack_deck", {
            "gameId": gid,
            "top": ["extra_vote", "extra_vote", "extra_vote"],
        })

        # One draw ends the turn all by itself — the torch moves to Ben
        jsclick(ana, '[data-action="drawCard"]')
        check("turn: drawing ends the turn automatically",
              wait_for(lambda: state(gid)["turnOrder"]
                       [state(gid)["currentTurnIndex"]] != ana_id, 10)
              is not None, guidance(ana))
        r_draw2 = api("/api/turn/draw", {"gameId": gid, "playerId": ana_id})
        check("turn: an out-of-turn draw is refused",
              not r_draw2.get("success")
              and "not your turn" in (r_draw2.get("message") or ""),
              r_draw2.get("message"))

        # Ben's quick turn, then the bot plays itself
        wait_for(lambda: 'Steal' in guidance(ben), 15)
        # A0 regression: before the fix, narrator.js bound 'game_event' to
        # socketManager.socket at DOMContentLoaded — before the socket
        # existed — so no handler was EVER attached and this narration was
        # silently dead on every phone. This is a REAL steal over the REAL
        # socket; snapshot first so pre-existing history can't fake a pass.
        # Targeted at Ana specifically (not left to whichever row renders
        # first): the server's private "robbed" alert only fires for a
        # human victim, and doubling this steal as the A1/A4 end-to-end
        # check below needs a known victim.
        narrator_before = narrator_entries(ana)
        jsclick(ben, '.lives-row.steal-target', 'Ana')
        time.sleep(1.0)
        # (a raid dialog can appear on Ana if Ben stole from her — she declines)
        if ana.locator('.raid-dialog').count():
            jsclick(ana, '[data-raid="allow"]')
            time.sleep(0.6)

        # A1 (web half) + A4, end to end: the server now actually emits a
        # private "robbed" alert to the victim's own room (on_join/A2 are
        # live in this tree). Ana's phone should show the banner; Ben's —
        # the thief, room-mate in the SAME broadcast room — never should.
        # Checked BEFORE the narrator-queue assertion below on purpose: the
        # banner renders immediately (no typing effect) and auto-dismisses
        # after ~5s, while the narrator's own queue can still be working
        # through earlier events' typing animation — polling for the banner
        # after that catches up would just watch it dismiss unseen.
        check("robbed (E2E): the victim's own phone gets the private banner",
              wait_for(lambda: ana.locator('.robbed-banner').count() == 1, 8) is not None,
              ana.locator('.robbed-banner').count())
        check("robbed (E2E): the thief's phone never gets a banner",
              ben.locator('.robbed-banner').count() == 0)
        ana.evaluate("() => document.getElementById('robbedBanner')?.remove()")

        check("narrator: a real steal's game_event reaches the DOM (A0 regression)",
              wait_for(lambda: len(narrator_entries(ana)) > len(narrator_before)
                       and 'Ben' in narrator_entries(ana)[0], 20) is not None,
              narrator_entries(ana)[:2])
        wait_for(lambda: 'Play' in guidance(ben) or 'Draw' in guidance(ben), 10)
        jsclick(ben, '[data-action="drawCard"]')
        time.sleep(0.8)
        check("bots: the computer player takes its turn unattended",
              wait_for(lambda: (state(gid)["turnOrder"]
                                [state(gid)["currentTurnIndex"]] == ana_id)
                       and not state(gid)["players"][ana_id]["hasStolen"], 25)
              is not None)

        # ══════════════ U3 · Tribal Council through real screens ══════════════
        api("/api/test/stack_deck", {"gameId": gid, "top": ["tribal_council_single"]})
        # Ana's turn: steal, then draw the stacked Tribal Council Card
        jsclick(ana, '.lives-row.steal-target', 'Coconut')
        time.sleep(0.8)
        # Deterministic ballots for the ceremony: Ana holds NO vote (she'll pass
        # the box), Ben and the bot each hold exactly one
        api("/api/test/set_hand", {"gameId": gid, "playerId": ana_id, "hand": []})
        api("/api/test/set_hand", {"gameId": gid, "playerId": ben_id, "hand": ["vote"]})
        api("/api/test/set_hand", {"gameId": gid, "playerId": bot_id, "hand": ["vote"]})
        time.sleep(0.4)
        jsclick(ana, '[data-action="drawCard"]')
        check("tribal: drawing the card opens the ceremony for everyone",
              wait_for(lambda: active_screen(ana) == 'tribalAnnouncementScreen', 10)
              is not None and
              wait_for(lambda: active_screen(ben) == 'tribalAnnouncementScreen', 10)
              is not None)

        g = state(gid)
        check("tribal: the drawer is the Council Leader",
              g["currentVote"]["councilLeaderId"] == ana_id)
        check("tribal: only the Leader's phone has the ceremony controls",
              ana.locator('[data-action="openDiscussion"]').count() == 1
              and ben.locator('[data-action="openDiscussion"]').count() == 0)

        jsclick(ana, '[data-action="openDiscussion"]')
        wait_for(lambda: active_screen(ana) == 'tribalDiscussionScreen')
        check("tribal: Leader opens the discussion; non-leader has no vote button",
              ben.locator('[data-action="startVoting"]').count() == 0)

        jsclick(ana, '[data-action="startVoting"]')
        wait_for(lambda: active_screen(ana) == 'votingScreen')
        wait_for(lambda: active_screen(ben) == 'votingScreen')

        names_on_ballot = ana.evaluate(
            "() => [...document.querySelectorAll('.vote-target-name')]"
            ".map(e => e.textContent.trim())")
        check("vote: your own name is not on your ballot",
              'Ana' not in names_on_ballot, names_on_ballot)

        # The Leader cannot tally before the box has reached everyone
        if ana.locator('[data-action="revealVotes"]').count():
            jsclick(ana, '[data-action="revealVotes"]')
            time.sleep(0.8)
            check("vote: early reveal is refused until everyone has voted",
                  active_screen(ana) == 'votingScreen',
                  toast_text(ana))
        else:
            check("vote: early reveal is refused until everyone has voted",
                  True, "reveal control not offered before votes are in")

        # Ana's Vote Card was burned as the Sorry For You penalty — the rulebook
        # still passes her the box, and the UI must offer exactly that
        check("vote: a card-less player is offered 'Pass the Voting Box'",
              wait_for(lambda: ana.locator('[data-action="passVotingBox"]').count() == 1,
                       8) is not None)
        jsclick(ana, '[data-action="passVotingBox"]')
        time.sleep(0.4)
        ui_vote(ben, gid, ben_id, 'Coconut')
        got_all = wait_for(lambda: len((state(gid)["currentVote"] or {}).get("votes", {}))
                           >= 3, 20)
        g2 = state(gid); cv_dump = g2.get("currentVote") or {}
        check("vote: bot casts its own ballot", got_all is not None,
              {"voted": [g2["players"][p]["name"] for p in cv_dump.get("votes", {})],
               "phase": cv_dump.get("phase"),
               "ana_hand": [c.get("type") for c in g2["players"][ana_id]["hand"]],
               "ana_voted": g2["players"][ana_id].get("hasVoted")})

        # Leader seals the box — the idol window opens on every phone. The
        # Guide puts idols AFTER the last ballot and BEFORE the tally, so this
        # first tap must NOT show a result.
        wait_for(lambda: ana.locator('[data-action="revealVotes"]').count() >= 1, 10)
        jsclick(ana, '[data-action="revealVotes"]')
        check("vote: sealing the box opens the idol window, it does not tally",
              wait_for(lambda: active_screen(ana) == 'immunityScreen', 10) is not None
              and wait_for(lambda: active_screen(ben) == 'immunityScreen', 10) is not None)

        # Leader reads the votes — results appear on every phone
        wait_for(lambda: ana.locator('[data-action="revealVotes"]').count() >= 1, 10)
        jsclick(ana, '[data-action="revealVotes"]')
        check("vote: the reveal shows the tally on every phone",
              wait_for(lambda: active_screen(ana) == 'resultsScreen', 10) is not None
              and wait_for(lambda: active_screen(ben) == 'resultsScreen', 10) is not None)
        check("vote: results name the voted-out player",
              'Coconut' in ana.locator('#voteResults, .results-container, .screen.active'
                                       ).first.inner_text())

        # A tied tally is the Leader's to break (the bot's free ballot can tie it)
        cv1 = state(gid).get("currentVote") or {}
        if cv1.get("tieBreakNeeded"):
            tied = cv1.get("tiedPlayers") or []
            pick = bot_id if bot_id in tied else (tied[0] if tied else None)
            if pick:
                api("/api/vote/tiebreak", {"gameId": gid, "leaderId": ana_id,
                                           "chosenId": pick})
        wait_for(lambda: ana.locator('[data-action="completeTribal"]').count() >= 1, 10)
        jsclick(ana, '[data-action="completeTribal"]')
        check("tribal: completing returns the tribe to the island",
              wait_for(lambda: active_screen(ana) == 'playingScreen', 10) is not None)

        # ══════════════ U4 · To the end: Final Tribal and the winner ══════════════
        # The ceremony's tap-through is proven above — this section verifies the
        # ENDGAME SCREENS, so the second tribal is driven deterministically.
        api("/api/test/set_flags", {"gameId": gid, "playerId": bot_id,
                                    "characterCards": 1})

        # March turns via the API; the tribal card is stacked only at the moment
        # a HUMAN is about to draw, so a human is always the Council Leader
        # (a bot leader would race this script's API ceremony with its own).
        for _ in range(60):
            g4 = state(gid)
            if g4.get("phase") != "playing":
                break
            theft = g4.get("pending_theft") or {}
            if theft.get("reactive_window_open"):
                api("/api/reactive/complete_theft", {"gameId": gid})
                continue
            cur = g4["turnOrder"][g4["currentTurnIndex"]]
            if g4["players"][cur].get("isBot"):
                time.sleep(0.5)
                continue
            if not g4["players"][cur].get("hasStolen"):
                victim = next(p for p in g4["turnOrder"]
                              if p != cur and not g4["players"][p].get("isEliminated"))
                api("/api/turn/steal", {"gameId": gid, "thiefId": cur, "targetId": victim})
                continue
            api("/api/test/stack_deck", {"gameId": gid, "top": ["tribal_council_single"]})
            api("/api/turn/draw", {"gameId": gid, "playerId": cur})

        check("tribal #2: the ceremony opens again on every phone",
              wait_for(lambda: active_screen(ana) == 'tribalAnnouncementScreen', 12)
              is not None, state(gid).get("phase"))

        # The Leader (whoever drew) runs the ceremony; every human ballots the bot.
        # Hands reset first — the march's steals shuffle Vote Cards unpredictably.
        cv4 = state(gid)["currentVote"]
        leader4 = cv4["councilLeaderId"]
        api("/api/test/set_hand", {"gameId": gid, "playerId": ana_id, "hand": ["vote"]})
        api("/api/test/set_hand", {"gameId": gid, "playerId": ben_id, "hand": ["vote"]})
        api("/api/test/set_hand", {"gameId": gid, "playerId": bot_id, "hand": ["vote"]})
        api("/api/tribal/advance", {"gameId": gid, "phase": "discussion",
                                    "playerId": leader4})
        api("/api/vote/start", {"gameId": gid, "voteType": "elimination",
                                "playerId": leader4})
        for voter in (ana_id, ben_id):
            g4 = state(gid)
            mv = max(1, g4["players"][voter].get("mandatoryVotes", 1))
            r = api("/api/vote/cast", {"gameId": gid, "voterId": voter,
                                       "votesData": [{"targetId": bot_id, "votes": mv}]})
            if not r.get("success"):
                print(f"   [cast debug] {g4['players'][voter]['name']} mv={mv} "
                      f"refused: {r.get('message')}")
                api("/api/vote/cast", {"gameId": gid, "voterId": voter, "votesData": []})
        wait_for(lambda: len((state(gid)["currentVote"] or {}).get("votes", {})) >= 3, 15)
        # Two beats: seal the box, then tally (the idol window sits between).
        api("/api/vote/reveal", {"gameId": gid, "playerId": leader4})
        api("/api/vote/reveal", {"gameId": gid, "playerId": leader4})
        cv4 = state(gid).get("currentVote") or {}
        if cv4.get("tieBreakNeeded"):
            tied = cv4.get("tiedPlayers") or []
            pick = bot_id if bot_id in tied else (tied[0] if tied else None)
            if pick:
                api("/api/vote/tiebreak", {"gameId": gid, "leaderId": leader4,
                                           "chosenId": pick})
        api("/api/tribal/complete", {"gameId": gid, "playerId": leader4})

        check("final: the moment only 2 remain, Final Tribal opens on every phone",
              wait_for(lambda: active_screen(ana) == 'finalTribalScreen', 15) is not None
              and wait_for(lambda: active_screen(ben) == 'finalTribalScreen', 15) is not None,
              {"phase": state(gid).get("phase"), "ana": active_screen(ana)})
        final_text = ana.locator('.screen.active').inner_text()
        check("final: the three official questions are asked",
              'strategy' in final_text.lower() and 'best move' in final_text.lower()
              and 'outplay' in final_text.lower())
        check("final: finalists can play no cards",
              ana.locator('.card-mini.playable').count() == 0
              and ben.locator('.card-mini.playable').count() == 0)

        # The bot is the whole jury — it signals, votes, and crowns a winner
        check("final: the jury's vote crowns a Sole Survivor on screen",
              wait_for(lambda: active_screen(ana) == 'gameOverScreen', 60) is not None,
              active_screen(ana))
        winner_name = ana.locator('#winnerInfo').inner_text()
        check("final: the winner is named", winner_name.strip() != "", winner_name)

        # House rule: a game with a computer player never reaches the Hall of Fame
        record_visible = ana.evaluate(
            "() => { const b = document.querySelector("
            "'#gameOverActions [data-action=\"recordWinner\"]');"
            "return b && getComputedStyle(b).display !== 'none'; }")
        check("hall of fame: Record Winner is hidden in games with computer players",
              not record_visible)

        # ══════════════ U5 · Hall of Fame ══════════════
        jsclick(ana, '#campMenuBtn')
        wait_for(lambda: ana.locator('[data-camp="leaderboard"]').count(), 6)
        jsclick(ana, '[data-camp="leaderboard"]')
        wait_for(lambda: active_screen(ana) == 'leaderboardScreen', 8)
        hof = ana.locator('#leaderboardList').inner_text()
        check("hall of fame: opens from the camp menu (empty on a fresh island)",
              'No Sole Survivor yet' in hof or 'carved' in hof, hof[:60])

        # ══════════════ U6 · The robbed banner (A4) ══════════════
        # The private-room plumbing this event would ordinarily ride (A1's
        # and A2's server halves) is outside this suite's ownership, so this
        # exercises exactly the web contract: handleGameEvent -> the banner,
        # gated on the viewer being the addressed victim — by dispatching the
        # server's documented payload straight at the narrator, the same way
        # a private 'game_event' would arrive over the socket.
        robbed_event = {
            "type": "robbed", "timestamp": 0,
            "thiefId": ben_id, "thief": "Ben",
            "victimId": ana_id, "victim": "Ana",
            "count": 1, "cards": [{"name": "Hidden Immunity Idol", "type": "immunity_idol"}],
            "message": "Ben took your Hidden Immunity Idol",
        }
        ana.evaluate("(e) => window.SurvivorNarrator.handleGameEvent(e)", robbed_event)
        check("robbed: the victim's banner shows the server's message verbatim",
              wait_for(lambda: ana.locator('.robbed-banner').count() == 1
                       and 'Hidden Immunity Idol' in ana.locator('.robbed-banner').inner_text(),
                       5) is not None)

        jsclick(ana, '.robbed-banner')
        check("robbed: tapping the banner dismisses it",
              wait_for(lambda: ana.locator('.robbed-banner').count() == 0, 3) is not None)

        # Gate: an event addressed to someone else must never render here,
        # even though the server should only ever reach the victim's own
        # private room — defense against a routing bug.
        other_event = dict(robbed_event, thiefId=ana_id, thief="Ana",
                            victimId=ben_id, victim="Ben",
                            message="Ana took your Hidden Immunity Idol")
        ana.evaluate("(e) => window.SurvivorNarrator.handleGameEvent(e)", other_event)
        time.sleep(0.5)
        check("robbed: a banner addressed to someone else never renders for this viewer",
              ana.locator('.robbed-banner').count() == 0)

        # ══════════════ U7 · A shared link survives the gate's reload (B1) ══════════════
        # The gate can swap in accessScreen before a tapped link's code ever
        # reaches the join form, and submitAccessCode()'s location.reload()
        # wipes the DOM AND the (already-cleaned) address bar — sessionStorage
        # is the only thing that survives that round trip. Actually enabling
        # SURVIVOR_ACCESS_CODE here would 401 every other check's raw api()
        # call, so this exercises the stash/restore mechanics directly: a
        # real reload, on the real code path, standing in for the gate's own.
        #
        # Uses the ?join= form, not /join/CODE: navigating straight to a
        # nested path 404s on THIS server today — Flask's own static handler
        # (static_url_path="") registers at the same "/<path:...>" shape as
        # the app's SPA-fallback route and Werkzeug ranks it first regardless
        # of registration order (the plan's Task B2 already names this
        # quirk for the AASA route), so a bare GET /join/CODE never reaches
        # index-optimized.html at all — a real bug in survivor_server.py,
        # outside this suite's ownership, flagged separately. ?join= hits the
        # exact "/" route and is unaffected, and it exercises the identical
        # stash/restore code path applyJoinLink() runs for either form.
        join_game = api("/api/game/create", {"deckMode": "official", "expansion": False})
        join_gid = join_game["gameId"]
        join_ctx = browser.new_context(viewport={"width": 390, "height": 844})
        join_page = join_ctx.new_page()
        join_page.goto(f"{BASE}/?join={join_gid}")
        join_page.wait_for_selector('#gameCodeInput')

        check("join link: ?join=CODE prefills the join form",
              join_page.input_value('#gameCodeInput') == join_gid)
        check("join link: the address bar is cleaned after the prefill",
              join_page.evaluate("() => window.location.pathname") == '/')
        stashed = join_page.evaluate("() => sessionStorage.getItem('survivorPendingJoin')")
        check("join link: the code is stashed in sessionStorage before the cleanup",
              stashed == join_gid, stashed)

        join_page.reload()
        join_page.wait_for_selector('#gameCodeInput')
        check("join link: the code survives a reload via the sessionStorage stash",
              join_page.input_value('#gameCodeInput') == join_gid)

        jsfill(join_page, '#playerNameInput', 'Zed')
        jsclick(join_page, '#colorSelection .color-btn')
        jsclick(join_page, '.screen.active button[data-action="joinGame"]')
        wait_for(lambda: active_screen(join_page) == 'lobbyScreen', 8)
        check("join link: the stashed code actually joins the game",
              active_screen(join_page) == 'lobbyScreen')
        check("join link: the stash clears once the code is actually used to join",
              join_page.evaluate(
                  "() => sessionStorage.getItem('survivorPendingJoin')") is None)
        join_ctx.close()

        browser.close()


if __name__ == "__main__":
    print("🧪 UI Rules Verification (browser twin of the compliance checklist)")
    print("=" * 68)
    main()
