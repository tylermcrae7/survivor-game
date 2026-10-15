/**
 * Device settings — one versioned localStorage blob, defaults that exactly
 * reproduce the app's behavior before this module existed. Anything here is
 * per-phone; per-game settings (bot pace, tribal pace, bot style) live on the
 * server in game.settings and are set at creation or by the Leader.
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
        discordUserId: '',
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

    function reset() {
        try { localStorage.removeItem(KEY); } catch (e) {}
        cache = null;
        apply();
    }

    /** Toast duration in ms for a toast type; 0 means stay until tapped. */
    function toastMs(type) {
        const base = TOAST_MS[get('toastPace')] ?? TOAST_MS.normal;
        if (base === 0) return 0;
        return (type === 'error' || type === 'warning') ? Math.round(base * 1.3) : base;
    }

    function hapticsOn() { return !!get('haptics'); }
    function soundOn() { return !!get('sound'); }

    /**
     * The saved Discord user ID, but only if it still looks like a snowflake.
     * The server rejects a malformed one with a 400 that fails the whole join,
     * so a value saved by an older build must never be allowed to lock this
     * device out of the game. Empty string means "not linked".
     */
    function discordUserId() {
        const value = String(get('discordUserId') || '').trim();
        return /^[0-9]{15,25}$/.test(value) ? value : '';
    }

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
        // "Off" means full motion even when the OS asks for less — the
        // stylesheet honours the OS preference unless this class is set.
        root.classList.toggle('motion-full', get('reduceMotion') === 'off');
        syncWakeLock();
    }

    // ── Wake lock: hold the screen open while a game screen is showing ──
    let wakeLock = null;
    let wakeRequest = null;   // the request in flight — never two at once
    let wakeWanted = false;

    function wakeShould() {
        return wakeWanted && !!get('keepAwake') && document.visibilityState === 'visible';
    }

    function acquireWakeLock() {
        if (!('wakeLock' in navigator) || wakeLock || wakeRequest) return;
        wakeRequest = navigator.wakeLock.request('screen')
            .then(lock => {
                // Every screen change calls sync; the answer can arrive after
                // we stopped wanting it. A lock nobody holds a reference to
                // can never be released — let go of it right here instead.
                if (!wakeShould()) {
                    lock.release().catch(() => {});
                    return;
                }
                wakeLock = lock;
                lock.addEventListener('release', () => { if (wakeLock === lock) wakeLock = null; });
            })
            .catch(() => { /* low battery or unsupported — fine */ })
            .finally(() => { wakeRequest = null; });
    }

    /** ui.js calls this with true when entering game screens, false on leave. */
    function setWakeWanted(wanted) {
        wakeWanted = !!wanted;
        syncWakeLock();
    }

    function syncWakeLock() {
        const should = wakeShould();
        if (should && !wakeLock) acquireWakeLock();
        if (!should && wakeLock) {
            const lock = wakeLock;
            wakeLock = null;
            try { lock.release().catch(() => {}); } catch (e) { /* already gone */ }
        }
    }

    document.addEventListener('visibilitychange', syncWakeLock);

    // "Match device" follows the OS setting live, not just at load
    try {
        const mq = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
        if (mq) {
            if (mq.addEventListener) mq.addEventListener('change', apply);
            else if (mq.addListener) mq.addListener(apply);
        }
    } catch (e) { /* very old browser */ }

    window.SurvivorSettings = {
        get, set, reset, apply, toastMs, hapticsOn, soundOn, motionReduced,
        discordUserId, setWakeWanted, DEFAULTS, TOAST_MS
    };

    apply();
})();
