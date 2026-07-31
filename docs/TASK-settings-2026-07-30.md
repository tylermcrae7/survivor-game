# Settings Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A full settings screen for the Survivor PWA — reading pace, tribal pacing, bot speed/style, accessibility, tap confirmations, identity defaults, wake lock, turn notifications, and housekeeping — with per-device settings in localStorage and per-game settings on the server.

**Architecture:** A new `client/dist/settings.js` module owns every device-local setting (versioned localStorage JSON, defaults that exactly reproduce today's behavior) and applies them (CSS classes, toast durations, haptics gate, wake lock). Per-game settings (`botPace`, `tribalPace`, `botStyle`) live in `game["settings"]` on the server — set at creation, adjustable by the Leader via a new `update_game_settings` action — and `bots.py` reads them per game instead of module-level constants. Turn notifications use standard Web Push: the server auto-generates VAPID keys into a runtime file, stores subscriptions in a runtime file (never in game state, which every client receives), and fires on turn start and tribal start.

**Tech Stack:** Vanilla JS PWA (no framework), Flask + Socket.IO server, `pywebpush` for Web Push, unittest test battery via `run_all_tests.py`.

**House rules that bind every task:**
- Any client asset change bumps all three cache names in `client/dist/sw.js` to `3.11.0` (done once, Task 2).
- Defaults must reproduce current behavior exactly — a player who never opens Settings sees no change.
- Every server behavior gets a unittest; the full battery (`.venv/bin/python run_all_tests.py`) must be 22/22 (24/24 after the two new suites) before each commit.
- `rules_engine.py` uses tabs; the other Python files use spaces.

---

## File Map

| File | Role |
|---|---|
| `client/dist/settings.js` (create) | Device settings store + apply logic (toasts, text size, motion, haptics, sound, wake lock, identity, deck defaults, history length, confirmations, notifications toggle state) |
| `client/dist/index-optimized.html` (modify) | `settingsScreen` markup, gear button in header, camp-menu "Settings" item, `<script src="settings.js">` before ui.js |
| `client/dist/styles.css` (modify) | Settings screen styles (segmented controls, toggle rows), `html.text-large/.text-xl`, `html.reduce-motion` overrides |
| `client/dist/ui.js` (modify) | `showToast` reads settings + tap-to-dismiss; confirm dialogs for votes/steals; settings screen renderer + handlers; history drawer length; join prefill from identity |
| `client/dist/game.js` (modify) | `APP_VERSION` constant; createGame sends per-game settings defaults |
| `client/dist/network.js` (modify) | `createGame` passes `settings`; `GameAPI.updateGameSettings`; push subscribe/unsubscribe calls |
| `client/dist/sw.js` (modify) | cache names → 3.11.0; `settings.js` in STATIC_ASSETS; `push` + `notificationclick` handlers |
| `client/dist/narrator.js` (modify) | master-sound gate from settings |
| `survivor_server.py` (modify) | `create_game(settings=…)`, `update_game_settings` (leader-only), settings validation, push endpoints, push send on turn/tribal start |
| `bots.py` (modify) | per-game pace/style: `_pace(game)`, `windows_for(game)`, style-scaled play/steal chances |
| `push_notify.py` (create) | VAPID key management, subscription store, guarded pywebpush send |
| `requirements.txt` (modify) | `pywebpush` |
| `deploy/redeploy.sh` + `.gitignore` (modify) | exclude `push_keys.json`, `push_subs.json` |
| `tests/test_game_settings.py` (create) | validation, leader gate, bot pace/style/window math, cutthroat full-game soak |
| `tests/test_push_notifications.py` (create) | key generation, subscribe/unsubscribe, send-on-turn hook, graceful degradation |
| `run_all_tests.py` (modify) | register the two new suites |

**Settings inventory (device-local, localStorage key `survivorSettings.v1`):**

```js
{
  toastPace: 'normal',      // quick 3000 | normal 5000 | relaxed 8000 | pinned 0 (tap to dismiss)
  textSize: 'normal',       // normal | large | xl
  reduceMotion: 'auto',     // auto (follow OS) | on | off
  haptics: true,
  sound: true,              // master; narrator's own mute stays subordinate
  confirmVotes: false,
  confirmSteals: false,
  defaultDeckMode: 'official',
  defaultExpansion: false,
  defaultBotPace: 'normal',     // sent with create_game
  defaultTribalPace: 'normal',  // sent with create_game
  defaultBotStyle: 'normal',    // sent with create_game
  identityName: '',
  identityColor: '',
  keepAwake: true,
  historyLength: 'all',     // '30' | 'all'
  turnNotifications: false
}
```

**Per-game settings (server, `game["settings"]`):**

```python
GAME_SETTINGS_DEFAULTS = {"botPace": "normal", "tribalPace": "normal", "botStyle": "normal"}
GAME_SETTINGS_VALUES = {
    "botPace":    ("chill", "normal", "fast"),
    "tribalPace": ("normal", "relaxed", "tv"),
    "botStyle":   ("chill", "normal", "cutthroat"),
}
# botPace  → bot action delay ×: chill 1.8, normal 1.0, fast 0.4
# tribalPace → ceremony window ×: normal 1.0, relaxed 2.0, tv 3.5
#   plus a human floor: with any live human, advantage/discussion windows
#   never drop below 12s × tribal multiplier (fixes the bot-leader race).
# botStyle → play/steal chance: chill (play ×0.5, steal 0.25),
#   normal (today: play 0.75, steal 0.5), cutthroat (play 0.95, steal 0.8)
```

---

### Task 1: Device settings module

**Files:** Create `client/dist/settings.js`

- [ ] **Step 1: Write the module** — full content:

```js
/**
 * Device settings — one versioned localStorage blob, defaults that exactly
 * reproduce the app's behavior before this module existed.
 */
(function () {
    'use strict';

    const KEY = 'survivorSettings.v1';

    const DEFAULTS = {
        toastPace: 'normal',
        textSize: 'normal',
        reduceMotion: 'auto',
        haptics: true,
        sound: true,
        confirmVotes: false,
        confirmSteals: false,
        defaultDeckMode: 'official',
        defaultExpansion: false,
        defaultBotPace: 'normal',
        defaultTribalPace: 'normal',
        defaultBotStyle: 'normal',
        identityName: '',
        identityColor: '',
        keepAwake: true,
        historyLength: 'all',
        turnNotifications: false
    };

    const TOAST_MS = { quick: 3000, normal: 5000, relaxed: 8000, pinned: 0 };

    let cache = null;

    function load() {
        if (cache) return cache;
        let stored = {};
        try { stored = JSON.parse(localStorage.getItem(KEY) || '{}'); }
        catch (e) { stored = {}; }
        cache = Object.assign({}, DEFAULTS, stored);
        return cache;
    }

    function get(name) { return load()[name]; }

    function set(name, value) {
        const s = load();
        s[name] = value;
        try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private mode */ }
        apply();
        return s[name];
    }

    /** Toast duration in ms for a toast type; 0 means stay until tapped. */
    function toastMs(type) {
        const base = TOAST_MS[get('toastPace')] ?? TOAST_MS.normal;
        if (base === 0) return 0;
        return (type === 'error' || type === 'warning') ? Math.round(base * 1.3) : base;
    }

    function hapticsOn() { return !!get('haptics'); }
    function soundOn() { return !!get('sound'); }

    function motionReduced() {
        const v = get('reduceMotion');
        if (v === 'on') return true;
        if (v === 'off') return false;
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    /** Stamp presentation classes on <html>. Idempotent; call any time. */
    function apply() {
        const root = document.documentElement;
        root.classList.toggle('text-large', get('textSize') === 'large');
        root.classList.toggle('text-xl', get('textSize') === 'xl');
        root.classList.toggle('reduce-motion', motionReduced());
        syncWakeLock();
    }

    // ── Wake lock: hold the screen open while a game screen is showing ──
    let wakeLock = null;
    let wakeWanted = false;

    async function acquireWakeLock() {
        if (!('wakeLock' in navigator)) return;
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            wakeLock.addEventListener('release', () => { wakeLock = null; });
        } catch (e) { wakeLock = null; /* low battery or unsupported — fine */ }
    }

    /** ui.js calls this with true when entering game screens, false on leave. */
    function setWakeWanted(wanted) {
        wakeWanted = !!wanted;
        syncWakeLock();
    }

    function syncWakeLock() {
        const should = wakeWanted && get('keepAwake') && document.visibilityState === 'visible';
        if (should && !wakeLock) acquireWakeLock();
        if (!should && wakeLock) { try { wakeLock.release(); } catch (e) {} wakeLock = null; }
    }

    document.addEventListener('visibilitychange', syncWakeLock);

    window.SurvivorSettings = {
        get, set, apply, toastMs, hapticsOn, soundOn, motionReduced,
        setWakeWanted, DEFAULTS, TOAST_MS
    };

    apply();
})();
```

- [ ] **Step 2: Load it before the other modules** — in `client/dist/index-optimized.html`, the script block that loads `network.js` / `game.js` / `ui.js`, add **first**:

```html
<script src="settings.js" defer></script>
```

(Keep the same `defer`/ordering style as the neighboring script tags; settings.js must appear before `ui.js` so `SurvivorSettings` exists when ui.js initializes.)

- [ ] **Step 3: Register it in the service worker** — `client/dist/sw.js` STATIC_ASSETS gains `'/settings.js'` (Task 2 bumps the cache version).

- [ ] **Step 4: Verify in browser** — dev server up, `window.SurvivorSettings.get('toastPace')` → `'normal'`; `set('textSize','large')` toggles `<html class="text-large">`.

### Task 2: Service-worker bump to 3.11.0

**Files:** Modify `client/dist/sw.js:8-10`

- [ ] Replace the three cache names `survivor-v3.10.1` / `survivor-static-v3.10.1` / `survivor-dynamic-v3.10.1` with `3.11.0` equivalents. One bump covers every client change in this plan.

### Task 3: Toasts obey the pace setting, pinned toasts dismiss on tap

**Files:** Modify `client/dist/ui.js:1778-1808` (`showToast`)

- [ ] Replace the hardcoded duration block:

```js
    // Reading pace is a device setting; errors linger ~30% longer.
    // 0 (pinned) means the toast stays until tapped.
    if (duration == null) {
        duration = window.SurvivorSettings
            ? window.SurvivorSettings.toastMs(type)
            : ((type === 'error' || type === 'warning') ? 6500 : 5000);
    }
```

- [ ] After `toastContainer.appendChild(toast)`, make every toast tap-dismissable and only auto-remove when duration > 0:

```js
    const dismiss = () => {
        if (!toast.parentNode) return;
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    };
    toast.addEventListener('click', dismiss);

    if (duration > 0) {
        setTimeout(dismiss, duration);
    }
```

- [ ] Gate `Haptics.trigger` at its definition (ui.js:29-…): first line of `trigger()` becomes `if (window.SurvivorSettings && !window.SurvivorSettings.hapticsOn()) return;`

- [ ] Browser check: set `toastPace` to `pinned`, play a card — toast stays until tapped; set `quick` — gone in 3s.

### Task 4: Text size + reduce motion CSS

**Files:** Modify `client/dist/styles.css` (append a `/* ── Device settings ── */` section)

- [ ] Append:

```css
/* ── Device settings: text size ── */
html.text-large { font-size: 17.5px; }
html.text-xl    { font-size: 19.5px; }

/* ── Device settings: reduce motion ── */
html.reduce-motion *, html.reduce-motion *::before, html.reduce-motion *::after {
    animation-duration: 0.001s !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001s !important;
    scroll-behavior: auto !important;
}
```

(The app sizes with rem off the root; if the root font-size is set elsewhere in styles.css, adjust these two rules to override it — verify in browser that cards and the log actually grow.)

### Task 5: Master sound gate

**Files:** Modify `client/dist/narrator.js:183-198` region

- [ ] Where the narrator checks `this.muted` before speaking/playing, extend the check to `this.muted || (window.SurvivorSettings && !window.SurvivorSettings.soundOn())`. Locate every audio emission point in narrator.js (speech + any sfx) and gate each. The narrator's own toggle keeps working; master off silences regardless.

### Task 6: Settings screen UI

**Files:** Modify `client/dist/index-optimized.html` (new screen + entry points), `client/dist/ui.js` (renderer + handlers), `client/dist/styles.css` (controls)

- [ ] **Markup** — after `leaderboardScreen` (line ~264), add:

```html
<div id="settingsScreen" class="screen" role="region" aria-label="Settings">
    <div class="panel">
        <h2 class="panel-title">Settings</h2>
        <div id="settingsBody"><!-- rendered by ui.js --></div>
    </div>
</div>
```

- [ ] **Entry points** — a gear `chip-btn` next to `campMenuBtn` (header, line ~215) with `data-action="openSettings"` and an `⚙` icon (reuse the `<svg><use>` icon pattern; add `#i-gear` symbol if none exists). Add a "Settings" item to the camp menu markup/renderer alongside its existing items.

- [ ] **Renderer** in ui.js — `renderSettingsScreen()` builds sections from a declarative spec so rows stay consistent:

```js
const SETTINGS_SPEC = [
    { title: 'Reading & pacing', rows: [
        { key: 'toastPace', label: 'Message speed', type: 'seg',
          options: [['quick','Quick'],['normal','Normal'],['relaxed','Relaxed'],['pinned','Until tapped']],
          onChange: () => showToast('Messages will stay this long', 'info') },
        { key: 'defaultBotPace', label: 'Computer player speed (new games)', type: 'seg',
          options: [['chill','Chill'],['normal','Normal'],['fast','Fast']] },
        { key: 'defaultTribalPace', label: 'Tribal ceremony pace (new games)', type: 'seg',
          options: [['normal','Normal'],['relaxed','Relaxed'],['tv','TV drama']] },
        { key: 'defaultBotStyle', label: 'Computer player style (new games)', type: 'seg',
          options: [['chill','Chill'],['normal','Normal'],['cutthroat','Cutthroat']] },
    ]},
    { title: 'Accessibility', rows: [
        { key: 'textSize', label: 'Text size', type: 'seg',
          options: [['normal','Normal'],['large','Large'],['xl','Extra large']] },
        { key: 'reduceMotion', label: 'Reduce motion', type: 'seg',
          options: [['auto','Match device'],['on','On'],['off','Off']] },
        { key: 'haptics', label: 'Vibration', type: 'toggle' },
        { key: 'sound', label: 'Sound', type: 'toggle' },
    ]},
    { title: 'Table rules', rows: [
        { key: 'confirmVotes', label: 'Confirm before casting a vote', type: 'toggle' },
        { key: 'confirmSteals', label: 'Confirm before stealing', type: 'toggle' },
        { key: 'defaultDeckMode', label: 'Default deck', type: 'seg',
          options: [['official','Official'],['extended','Extended']] },
        { key: 'defaultExpansion', label: 'Add Rocks challenges by default', type: 'toggle' },
    ]},
    { title: 'You', rows: [
        { key: 'identityName', label: 'Your name', type: 'text', placeholder: 'Prefills the join form' },
        { key: 'identityColor', label: 'Your buff', type: 'colors' },
    ]},
    { title: 'Device', rows: [
        { key: 'keepAwake', label: 'Keep the screen awake during games', type: 'toggle' },
        { key: 'turnNotifications', label: 'Notify me on my turn', type: 'toggle',
          onChange: handleTurnNotificationsToggle },   // Task 12
        { key: 'historyLength', label: 'Story-so-far length', type: 'seg',
          options: [['30','Last 30'],['all','Everything']] },
    ]},
];
```

Rows render as: `seg` → a `color-grid`-style row of buttons with `aria-pressed`; `toggle` → the existing switch pattern (`expansionToggle` checkbox styling); `text` → `form-input`; `colors` → reuse the join form's `color-btn` grid. All handlers call `SurvivorSettings.set(key, value)` then re-render the row. Below the sections, a **Housekeeping** block (Task 11).

- [ ] **Wire `openSettings`** through the same delegated `data-action` dispatch the camp menu uses; `showScreen('settingsScreen')` + `renderSettingsScreen()`. Back behavior mirrors other secondary screens (the header/back affordance used by `leaderboardScreen`).

- [ ] **Styles** — append to styles.css: `.settings-section`, `.settings-row` (flex, label left, control right, wraps on narrow), `.seg-group .seg-btn[aria-pressed="true"]` highlighted with the existing accent variables. Match the app's dark theme tokens.

- [ ] Browser check: open via gear and via camp menu; every row round-trips (reload page, values persist).

### Task 7: Identity + deck defaults feed the forms

**Files:** Modify `client/dist/ui.js` (join prefill + save-back), `client/dist/game.js` / `network.js` (create payload)

- [ ] Where the join form initializes, prefill `playerNameInput` from `SurvivorSettings.get('identityName')` (existing `survivorState.playerName` wins if a rejoin is in progress) and pre-select the `color-btn` matching `identityColor` if it's free.
- [ ] On successful join, write the chosen name/color back: `SurvivorSettings.set('identityName', name); SurvivorSettings.set('identityColor', color);`
- [ ] On the start screen, initialize the deck segmented control and Rocks toggle from `defaultDeckMode` / `defaultExpansion`; changing them updates the settings (they ARE the defaults).
- [ ] `network.js createGame` (line 680) gains settings:

```js
    async createGame(options = {}) {
        const { deckMode = 'official', expansion = false, settings = null } = options;
        return apiCall('/game/create', settings ? { deckMode, expansion, settings }
                                                : { deckMode, expansion });
    },
```

and the caller passes `settings: { botPace: S.get('defaultBotPace'), tribalPace: S.get('defaultTribalPace'), botStyle: S.get('defaultBotStyle') }` (omit when all normal).

### Task 8: Vote & steal confirmations

**Files:** Modify `client/dist/ui.js` (`castVote` line ~1435, steal handler line ~822, tie-break handler ~547)

- [ ] Add a promise confirm helper near the other modal helpers:

```js
function showConfirm({ title, body, yes = 'Yes', no = 'Never mind' }) {
    return new Promise(resolve => {
        showModal(`
            <div class="confirm-sheet">
                <h3>${escapeHtml(title)}</h3>
                <p class="panel-sub">${escapeHtml(body)}</p>
                <button class="btn btn-enhanced touch-target" data-confirm="yes">${escapeHtml(yes)}</button>
                <button class="btn touch-target" data-confirm="no">${escapeHtml(no)}</button>
            </div>`);
        document.querySelectorAll('[data-confirm]').forEach(b =>
            b.addEventListener('click', () => { hideModal(); resolve(b.dataset.confirm === 'yes'); }));
    });
}
```

(Adapt to the file's actual modal helper names — the card sheet and raid dialog show the pattern.)

- [ ] In `castVote`, before submitting: if `SurvivorSettings.get('confirmVotes')`, `showConfirm({title: 'Cast this vote?', body: 'Write ' + targetName + ' on your parchment? A vote can't be taken back.'})` — bail on false. Same gate on the tie-break pick.
- [ ] In the steal tap handler: if `SurvivorSettings.get('confirmSteals')`, confirm "Steal a random card from {name}?" first.
- [ ] The extra-vote chooser already interrupts vote taps — confirm runs **after** the chooser (confirm the final total), not before, so the two dialogs never stack.

### Task 9: Server per-game settings + leader control

**Files:** Modify `survivor_server.py` (`create_game` line 298, `handle()` LEADER_ONLY block, new `update_game_settings`), `client/dist/network.js`, camp menu UI; Create `tests/test_game_settings.py`

- [ ] **Failing tests first** (`tests/test_game_settings.py`, unittest style copied from `CardEffectTestBase` fixtures):

```python
class TestGameSettings(SettingsTestBase):
    def test_create_accepts_and_sanitizes_settings(self):
        gid = self.gs.create_game(settings={"botPace": "fast", "tribalPace": "junk", "extra": 1})
        s = self.gs.games[gid]["settings"]
        self.assertEqual(s, {"botPace": "fast", "tribalPace": "normal", "botStyle": "normal"})

    def test_create_without_settings_gets_defaults(self):
        gid = self.gs.create_game()
        self.assertEqual(self.gs.games[gid]["settings"],
                         {"botPace": "normal", "tribalPace": "normal", "botStyle": "normal"})

    def test_update_game_settings_validates_and_merges(self):
        result = self.gs.update_game_settings(self.game_id, playerId=self.leader,
                                              settings={"tribalPace": "relaxed"})
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(self.gs.games[self.game_id]["settings"]["tribalPace"], "relaxed")

    def test_update_refuses_junk_values(self):
        result = self.gs.update_game_settings(self.game_id, playerId=self.leader,
                                              settings={"botPace": "ludicrous"})
        self.assertFalse(result["success"])
```

- [ ] **Implement** in `survivor_server.py`:

```python
GAME_SETTINGS_DEFAULTS = {"botPace": "normal", "tribalPace": "normal", "botStyle": "normal"}
GAME_SETTINGS_VALUES = {
    "botPace": ("chill", "normal", "fast"),
    "tribalPace": ("normal", "relaxed", "tv"),
    "botStyle": ("chill", "normal", "cutthroat"),
}

def sanitize_game_settings(raw, base=None):
    """Unknown keys are dropped; unknown values fall back to the base/default."""
    out = dict(base or GAME_SETTINGS_DEFAULTS)
    for key, allowed in GAME_SETTINGS_VALUES.items():
        value = (raw or {}).get(key)
        if value in allowed:
            out[key] = value
    return out
```

`create_game` gains `settings=None` and sets `game["settings"] = sanitize_game_settings(settings)`. `update_game_settings(gid, playerId, settings)` refuses values not in `GAME_SETTINGS_VALUES` (that's the "refuses junk" test — explicit refusal, not silent fallback), merges over the existing dict, `_save()`s, returns a message naming what changed (public — fine for the event log). Register the action in `handle()`'s routing and add `'update_game_settings'` to the `LEADER_ONLY` set (Leader = council leader fallback chain already used there).

- [ ] **Client**: `GameAPI.updateGameSettings(gameId, playerId, settings)` → `apiCall('/game/update_settings', …)` (match the URL convention `handle()` exposes); camp menu gains a Leader-only "Game pace" sheet listing the three segmented rows, current values from `gameState.settings`, calls the API on change.
- [ ] Run the new suite + battery; commit.

### Task 10: Bots read per-game pace, style, and windows

**Files:** Modify `bots.py`; extend `tests/test_game_settings.py`

- [ ] **Failing tests first:**

```python
class TestBotPacing(SettingsTestBase):
    def test_pace_multipliers(self):
        import bots
        self.game["settings"] = {"botPace": "chill", "tribalPace": "relaxed", "botStyle": "normal"}
        self.assertAlmostEqual(bots.delay_mult(self.game), 1.8)
        self.assertAlmostEqual(bots.window_mult(self.game), 2.0)

    def test_windows_scale_and_floor_with_humans(self):
        import bots
        self.game["settings"]["tribalPace"] = "normal"
        w = bots.windows_for(self.game)
        # any live human → the advantage window never dips below 12s
        self.assertGreaterEqual(w["advantage"], 12.0)

    def test_bot_only_games_keep_fast_windows(self):
        import bots
        for p in self.game["players"].values():
            p["isBot"] = True
        w = bots.windows_for(self.game)
        self.assertEqual(w, {k: v * 1.0 for k, v in bots.WINDOWS.items()})

    def test_style_scales_play_and_steal(self):
        import bots
        self.game["settings"]["botStyle"] = "cutthroat"
        self.assertAlmostEqual(bots.play_chance(self.game), 0.95)
        self.assertAlmostEqual(bots.steal_chance(self.game), 0.8)


def test_cutthroat_fast_game_finishes():
    """Style/pace multipliers must never break termination (soak, both extremes)."""
    for style, pace in (("cutthroat", "fast"), ("chill", "normal")):
        name, steps = _play_full_bot_game("official", False, seed=11,
                                          settings={"botStyle": style, "botPace": pace})
        assert name, f"{style}/{pace} game did not finish"
```

- [ ] **Implement** in `bots.py` near the constants:

```python
PACE_DELAY = {"chill": 1.8, "normal": 1.0, "fast": 0.4}
TRIBAL_WINDOW = {"normal": 1.0, "relaxed": 2.0, "tv": 3.5}
STYLE_PLAY = {"chill": PLAY_CHANCE * 0.5, "normal": PLAY_CHANCE, "cutthroat": 0.95}
STYLE_STEAL = {"chill": 0.25, "normal": 0.5, "cutthroat": 0.8}
# With a live human at the table, the advantage/discussion windows keep a
# floor so a bot Council Leader can't race past the one moment a human may
# play I'm The Leader Now or an idol. Bot-only games stay quick.
HUMAN_WINDOW_FLOORS = {"advantage": 12.0, "discussion": 10.0}

def _setting(game, key):
    return (game.get("settings") or {}).get(key, "normal")

def delay_mult(game):  return PACE_DELAY.get(_setting(game, "botPace"), 1.0)
def window_mult(game): return TRIBAL_WINDOW.get(_setting(game, "tribalPace"), 1.0)
def play_chance(game): return STYLE_PLAY.get(_setting(game, "botStyle"), PLAY_CHANCE)
def steal_chance(game): return STYLE_STEAL.get(_setting(game, "botStyle"), 0.5)

def windows_for(game):
    mult = window_mult(game)
    w = {k: v * mult for k, v in WINDOWS.items()}
    if any(not p.get("isBot") and not p.get("isEliminated")
           for p in game.get("players", {}).values()):
        for k, floor in HUMAN_WINDOW_FLOORS.items():
            w[k] = max(w[k], floor * mult)
    return w
```

Thread them through: `poke()` multiplies its delay by `delay_mult(game)`; every `WINDOWS[...]` comparison in `_tribal_action` (and the final-tribal pacing if it uses WINDOWS) goes through `windows_for(game)`; `_turn_action`'s `PLAY_CHANCE` and steal `0.5` become `play_chance(game)` / `steal_chance(game)`. `_play_full_bot_game` in `tests/test_bots.py` gains `settings=None` passed to `create_game`.

- [ ] `SURVIVOR_BOT_DELAY=0` (the test env) must still collapse everything to zero — multipliers apply to the base, so 0 × anything = 0; the floors also multiply against a `scale` of 0 via `WINDOWS` already being 0 — **check `windows_for` under zero-delay tests**: when `BASE_DELAY` is 0, `WINDOWS` are all 0 and floors would still impose 12s. Guard: `if not BASE_DELAY: return dict(WINDOWS)` at the top of `windows_for`.
- [ ] Run suite + battery + the soak test; commit.

### Task 11: Housekeeping section

**Files:** Modify `client/dist/ui.js` (settings renderer), `client/dist/game.js` (version)

- [ ] `game.js`: `const APP_VERSION = '3.11.0';` exported on `window.SurvivorGame`.
- [ ] Housekeeping block at the bottom of the settings screen:
  - **Leave this game** — visible when `survivorState` has a game; existing leave/wipe flow (`wipeLocalGame`), confirm first.
  - **Forget this island** — clears the access-gate cookie + `survivorState` (the access flow's own storage), returns to `accessScreen`; confirm first.
  - **Reset settings** — `localStorage.removeItem('survivorSettings.v1')` + re-apply + re-render.
  - **About** — "Survivor: The Tribe Has Spoken — companion · v{APP_VERSION}".
- [ ] History drawer: where ui.js renders `gameState.eventLog` (line ~2836), slice to the last 30 when `historyLength === '30'`.

### Task 12: Web Push — server side

**Files:** Create `push_notify.py`, `tests/test_push_notifications.py`; Modify `survivor_server.py`, `requirements.txt`, `deploy/redeploy.sh`, `.gitignore`

- [ ] **Failing tests first** (`tests/test_push_notifications.py`): keys generate once and persist; `subscribe/unsubscribe` round-trip in the store file (never in `game`); `notify_player` invokes the sender (monkeypatched `push_notify._webpush`); `advance_turn` on a human with a subscription triggers exactly one send (monkeypatch, count calls); with `push_notify.AVAILABLE = False` everything no-ops without error.

- [ ] **`push_notify.py`** — the whole module:

```python
"""
Web Push for turn/tribal notifications.

Keys and subscriptions are RUNTIME state (like games.json): auto-generated,
stored beside the server, excluded from git and from redeploy's rsync.
Subscriptions must never ride inside game state — every client receives the
full game state, and a push endpoint is a private capability URL.
"""
import json, logging, os, threading

logger = logging.getLogger(__name__)

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid02, b64urlencode
    AVAILABLE = True
except ImportError:          # dependency not installed — feature stays dark
    AVAILABLE = False

KEYS_FILE = "push_keys.json"
SUBS_FILE = "push_subs.json"
_lock = threading.Lock()


def _load_json(path, fallback):
    try:
        with open(path) as f: return json.load(f)
    except (OSError, ValueError): return fallback


def get_keys():
    """VAPID keypair, auto-generated on first use."""
    if not AVAILABLE: return None
    keys = _load_json(KEYS_FILE, None)
    if keys and keys.get("private") and keys.get("public"):
        return keys
    vapid = Vapid02()
    vapid.generate_keys()
    from cryptography.hazmat.primitives import serialization
    private = vapid.private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    keys = {"private": private, "public": b64urlencode(raw)}
    with open(KEYS_FILE, "w") as f: json.dump(keys, f)
    logger.info("Generated new VAPID keys for turn notifications")
    return keys


def public_key():
    keys = get_keys()
    return keys["public"] if keys else None


def _subs():
    return _load_json(SUBS_FILE, {})


def _write_subs(subs):
    with open(SUBS_FILE, "w") as f: json.dump(subs, f)


def subscribe(gid, player_id, subscription):
    with _lock:
        subs = _subs()
        subs[f"{gid}:{player_id}"] = subscription
        _write_subs(subs)


def unsubscribe(gid, player_id):
    with _lock:
        subs = _subs()
        if subs.pop(f"{gid}:{player_id}", None) is not None:
            _write_subs(subs)


def _webpush(subscription, payload, keys):     # test seam
    webpush(subscription_info=subscription, data=payload,
            vapid_private_key=keys["private"],
            vapid_claims={"sub": "mailto:tylermcrae7@gmail.com"},
            timeout=4)


def notify_player(gid, player_id, title, body):
    """Fire-and-forget; a dead subscription unsubscribes itself."""
    if not AVAILABLE: return
    sub = _subs().get(f"{gid}:{player_id}")
    if not sub: return
    keys = get_keys()
    if not keys: return

    def _send():
        try:
            _webpush(sub, json.dumps({"title": title, "body": body}), keys)
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                unsubscribe(gid, player_id)   # endpoint expired
            else:
                logger.warning(f"Push to {gid}:{player_id} failed: {e}")
        except Exception as e:
            logger.warning(f"Push to {gid}:{player_id} failed: {e}")

    threading.Thread(target=_send, daemon=True).start()
```

(`py_vapid` ships with `pywebpush`. If `Vapid02` key export differs at implementation time, adapt inside `get_keys` only — its contract is `{"private": PEM, "public": b64url}`.)

- [ ] **Server wiring** (`survivor_server.py`): `import push_notify`; three routes gated exactly like other `/api/*` (access cookie): `GET /api/push/pubkey` → `{"key": push_notify.public_key()}` or 404 when unavailable; `POST /api/push/subscribe` `{gameId, playerId, subscription}` (validate the player exists in the game); `POST /api/push/unsubscribe`. Sends: at the end of `advance_turn`, if the new current player is a human, `notify_player(gid, pid, "Your torch burns", "It's your turn in Survivor")`; in `_trigger_tribal_council`, notify every live human `("Tribal Council", "The tribe must vote")`. Both wrapped `try/except` — a push failure must never break a turn.
- [ ] `requirements.txt`: `pywebpush>=2.0.0`. `.gitignore` + `deploy/redeploy.sh` excludes: `push_keys.json`, `push_subs.json`.
- [ ] Run suite + battery; commit.

### Task 13: Web Push — client side

**Files:** Modify `client/dist/sw.js`, `client/dist/network.js`, `client/dist/ui.js` (`handleTurnNotificationsToggle`)

- [ ] **sw.js** handlers (append):

```js
self.addEventListener('push', (event) => {
    let data = { title: 'Survivor', body: 'The tribe has news.' };
    try { data = event.data.json(); } catch (e) {}
    event.waitUntil(self.registration.showNotification(data.title, {
        body: data.body, icon: '/icon-192x192.png', badge: '/icon-192x192.png',
        tag: 'survivor-turn'
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(list => list.length ? list[0].focus() : clients.openWindow('/')));
});
```

- [ ] **network.js**: `pushPubkey()`, `pushSubscribe(gameId, playerId, subscription)`, `pushUnsubscribe(gameId, playerId)` — thin `apiCall` wrappers.
- [ ] **ui.js** `handleTurnNotificationsToggle(on)`: on **enable** — feature-detect (`'serviceWorker' in navigator && 'PushManager' in window`), fetch pubkey (404 → toast "Notifications aren't set up on this server", revert toggle), `Notification.requestPermission()` (denied → revert + toast), `registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key)})`, POST subscribe with the current `gameId/playerId` (no active game → toast "Join a game first, then flip this on", revert). On **disable** — unsubscribe both locally and server-side. Include the standard `urlBase64ToUint8Array` helper.
- [ ] iOS note in the row's sub-label: "On iPhone, add the app to your Home Screen first."
- [ ] Browser check: toggle in the dev server — permission prompt appears (or a clean revert + toast in the embedded pane if the prompt is suppressed); a fake subscription round-trips the API (verified by the server suite regardless).

### Task 14: Wake lock + screen-enter hooks

**Files:** Modify `client/dist/ui.js` (`showScreen`)

- [ ] In `showScreen`, after the screen swap: `window.SurvivorSettings?.setWakeWanted(['playingScreen','tribalAnnouncementScreen','tribalAdvantageScreen','tribalDiscussionScreen','votingScreen','immunityScreen','resultsScreen','finalTribalScreen'].includes(screenId));` — the module handles acquire/release/visibility.

### Task 15: Full battery, browser pass, docs

- [ ] Register both new suites in `run_all_tests.py` (mirror an existing entry pair).
- [ ] `.venv/bin/python run_all_tests.py` → 24/24.
- [ ] Browser pass on the dev server: settings screen round-trips; pinned toast; text-XL visibly larger; a bot game created with `tribalPace: relaxed` shows an obviously longer advantage window; leader "Game pace" sheet changes stick (state shows new settings); join form prefills.
- [ ] Update `README.md` features list (settings screen + turn notifications) and append the change to `docs/PROGRESS-2026-07-29.md` per house habit.

### Task 16: Commit, push, deploy, notify

- [ ] Commits land per phase (Tasks 1–8 client foundation; 9–10 server pace/style; 11 housekeeping rolls into the client commit if small; 12–13 push notifications; 15 docs — each with battery green first).
- [ ] `git push origin main`.
- [ ] `deploy/redeploy.sh`; verify: new PID, `sw.js` serves 3.11.0, log shows VAPID keys generated once, no errors; spot-check `https://localhost:8080` still 200.
- [ ] Telegram notification at: plan done, each commit, battery green, pushed, deployed.

---

## Self-review

- **Coverage:** every idea from the approved list maps to a task — toast duration (3), bot speed (9–10), ceremony pacing incl. the bot-leader fix (10), reveal linger (via `tv`/`relaxed` window mult on `reveal`), text size/motion/haptics/sound (4–6), confirmations (8), deck defaults (7), bot style (10), identity defaults (7), wake lock (1, 14), turn notifications (12–13), leave/forget/about/history length (11).
- **Types:** `SurvivorSettings.get/set/toastMs/setWakeWanted` used consistently; server `settings` dict shape identical in create/update/bots; `windows_for` returns the same keys as `WINDOWS`.
- **No placeholders:** each code step carries its content; the two "adapt to the file's actual helper names" notes are anchored to concrete patterns already read in this session (modal helpers, icon symbols).
