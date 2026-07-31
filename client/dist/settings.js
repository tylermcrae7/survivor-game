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
        get, set, reset, apply, toastMs, hapticsOn, soundOn, motionReduced,
        setWakeWanted, DEFAULTS, TOAST_MS
    };

    apply();
})();
