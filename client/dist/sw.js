/**
 * Survivor App - Service Worker
 *
 * How a deploy reaches a phone:
 *   1. The server serves THIS file through a dedicated route that replaces
 *      every `__BUILD__` with a hash of the static files (it changes on every
 *      deploy) and sends `Cache-Control: no-cache`. New bytes → the browser
 *      installs a new worker on its next update check.
 *   2. The new worker precaches under a new cache name, skips waiting, and on
 *      activate deletes every older survivor-* cache and claims the pages.
 *   3. Independently of 1–2, the app's own code (HTML/JS/CSS) is fetched
 *      NETWORK-FIRST, so even a page still controlled by an old worker gets the
 *      new files from the server. The cache is only an offline fallback.
 *
 * The old worker served game.js/ui.js/styles.css cache-first under a cache name
 * nobody remembered to bump, so phones kept running code that had been fixed
 * on the server for weeks. Do not make app code cache-first again.
 */

const BUILD = '__BUILD__';
const STATIC_CACHE = `survivor-static-${BUILD}`;

// Precached so the app shell still opens offline. Paths are absolute.
const STATIC_ASSETS = [
    '/',
    '/styles.css',
    '/settings.js',
    '/game.js',
    '/network.js',
    '/ui.js',
    '/state-manager.js',
    '/narrator.js',
    '/socket.io.min.js',
    '/manifest.json',
    '/icon-192x192.png',
    '/icon-512x512.png'
];

// App code: always try the server first; the cache is the offline fallback.
const NETWORK_FIRST_EXT = ['.js', '.css', '.html', '.json', '.webmanifest'];
// Images only change with a deploy, and every deploy gets a fresh cache.
const CACHE_FIRST_EXT = ['.png', '.jpg', '.jpeg', '.svg', '.ico', '.webp'];

/** A response we are willing to keep: a plain, same-origin 200 that was not redirected. */
function cacheable(response) {
    return !!response && response.ok && !response.redirected && response.type === 'basic';
}

// ── Install: precache what we can, then take over without waiting ──
self.addEventListener('install', event => {
    event.waitUntil((async () => {
        const cache = await caches.open(STATIC_CACHE);
        // allSettled: one missing icon must not abort the whole install (the
        // old addAll did, which left the previous worker — and its stale code —
        // in charge). `cache: 'reload'` skips the HTTP cache so the new build
        // is what lands in the new cache.
        await Promise.allSettled(STATIC_ASSETS.map(async url => {
            const response = await fetch(new Request(url, { cache: 'reload' }));
            if (cacheable(response)) await cache.put(url, response);
        }));
    })());
    self.skipWaiting();
});

// ── Activate: drop every older cache and claim the open pages ──
self.addEventListener('activate', event => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(names
            .filter(name => name.startsWith('survivor-') && name !== STATIC_CACHE)
            .map(name => caches.delete(name)));
        await self.clients.claim();
    })());
});

// ── Fetch routing ──
self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    // Cross-origin (fonts) — the browser handles it; nothing here to go stale.
    if (url.origin !== self.location.origin) return;

    const path = url.pathname;
    // Live data and the share-link redirect are never the worker's business:
    //   /api/      game state must come from the server, every time
    //   /socket.io/ the long-polling transport (NOT /socket.io.min.js — the
    //               vendored client is app code and must work offline)
    //   /join/CODE  a 302 to /?join=CODE — a redirected response must not be
    //               handed to a navigation or cached as the app shell
    if (path.startsWith('/api/') || path.startsWith('/socket.io/') || path.startsWith('/join/')) return;

    if (request.mode === 'navigate') {
        event.respondWith(handleNavigation(event));
        return;
    }

    const lower = path.toLowerCase();
    if (CACHE_FIRST_EXT.some(ext => lower.endsWith(ext))) {
        event.respondWith(cacheFirst(request));
    } else if (NETWORK_FIRST_EXT.some(ext => lower.endsWith(ext))) {
        event.respondWith(networkFirst(request));
    }
    // Anything else: no respondWith — straight to the network.
});

/**
 * Network first for app code. `cache: 'no-cache'` makes the browser revalidate
 * with the server (a cheap 304 when nothing changed) instead of trusting its
 * HTTP cache. Falls back to the cache when offline or when the tunnel answers
 * with an error page (502 during a server bounce).
 */
async function networkFirst(request) {
    try {
        const response = await fetch(new Request(request, { cache: 'no-cache' }));
        if (cacheable(response)) {
            const copy = response.clone();
            caches.open(STATIC_CACHE)
                .then(cache => cache.put(stripSearch(request.url), copy))
                .catch(() => {});
            return response;
        }
        if (response.ok) return response;
        const cached = await matchCached(request);
        return cached || response;
    } catch (error) {
        const cached = await matchCached(request);
        if (cached) return cached;
        throw error;
    }
}

async function cacheFirst(request) {
    const cached = await matchCached(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (cacheable(response)) {
        const copy = response.clone();
        caches.open(STATIC_CACHE)
            .then(cache => cache.put(stripSearch(request.url), copy))
            .catch(() => {});
    }
    return response;
}

/**
 * Navigations: network first. Only the app shell ('/' and the file behind it)
 * is kept, under the '/' key, so ?join=CODE visits don't pile up in the cache.
 */
async function handleNavigation(event) {
    const url = new URL(event.request.url);
    const isShell = url.pathname === '/' || url.pathname === '/index-optimized.html';
    try {
        const response = await fetch(event.request);
        if (isShell && cacheable(response)) {
            const copy = response.clone();
            caches.open(STATIC_CACHE).then(cache => cache.put('/', copy)).catch(() => {});
        }
        if (response.ok || response.type === 'opaqueredirect') return response;
        // The server (or the tunnel in front of it) answered with an error page —
        // the cached shell is more useful than Cloudflare's 502.
        return (await caches.match('/', { ignoreSearch: true })) || response;
    } catch (error) {
        return (await caches.match('/', { ignoreSearch: true })) || offlinePage();
    }
}

function matchCached(request) {
    // Pages reference assets with ?v=... — match the stored copy regardless.
    return caches.match(request, { ignoreSearch: true });
}

function stripSearch(href) {
    const u = new URL(href);
    u.search = '';
    return u.href;
}

function offlinePage() {
    return new Response(`<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Survivor - Offline</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; display: flex;
               align-items: center; justify-content: center; min-height: 100vh; margin: 0;
               background: #0e1916; color: #f7f5ef; text-align: center; }
        .offline-content { max-width: 400px; padding: 2rem; }
        .btn { background: #e07a2e; color: white; border: none; padding: 1rem 2rem;
               border-radius: 8px; cursor: pointer; margin-top: 1rem; font-size: 16px; }
    </style>
</head>
<body>
    <div class="offline-content">
        <h1>Survivor</h1>
        <p>You're offline. Check your connection and try again.</p>
        <button class="btn" onclick="location.reload()">Retry</button>
    </div>
</body>
</html>`, { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

// ── Messages from the page ──
self.addEventListener('message', event => {
    const type = event.data && event.data.type;
    if (type === 'SKIP_WAITING') {
        self.skipWaiting();
    } else if (type === 'CLEAR_CACHE') {
        event.waitUntil(caches.keys().then(names =>
            Promise.all(names.filter(n => n.startsWith('survivor-')).map(n => caches.delete(n)))));
    }
});

// ── Turn notifications (Web Push) ──
self.addEventListener('push', (event) => {
    let data = { title: 'Survivor', body: 'The tribe has news.' };
    try { data = event.data.json(); } catch (e) { /* keep the fallback */ }
    event.waitUntil(self.registration.showNotification(data.title, {
        body: data.body,
        icon: '/icon-192x192.png',
        badge: '/icon-192x192.png',
        tag: 'survivor-turn'
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(list => list.length ? list[0].focus() : clients.openWindow('/')));
});

/**
 * The push service rotated (or expired) this device's subscription. The worker
 * doesn't know which game/seat it belongs to, so it re-subscribes with the
 * server's key and tells any open page, which re-registers it with the game.
 * With no page open, the next join/rejoin re-sends it (see network.js).
 */
self.addEventListener('pushsubscriptionchange', (event) => {
    event.waitUntil((async () => {
        try {
            let options = event.oldSubscription && event.oldSubscription.options;
            if (!options || !options.applicationServerKey) {
                const r = await fetch('/api/push/pubkey', { cache: 'no-store' });
                const body = r.ok ? await r.json() : null;
                if (!body || !body.key) return;
                options = { userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(body.key) };
            }
            await self.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: options.applicationServerKey
            });
            const pages = await clients.matchAll({ type: 'window', includeUncontrolled: true });
            pages.forEach(page => page.postMessage({ type: 'PUSH_SUBSCRIPTION_CHANGED' }));
        } catch (e) { /* best effort — the next join re-sends the subscription */ }
    })());
});

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    return Uint8Array.from([...raw].map(ch => ch.charCodeAt(0)));
}
