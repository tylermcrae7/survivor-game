/**
 * Survivor App - Service Worker
 * Provides offline functionality and performance optimization
 */

// Bump these on every client change — the static cache is cache-first, so a stale
// cache name means installed PWAs keep running the old game.js/ui.js/styles.css.
const CACHE_NAME = 'survivor-v3.6.1';
const STATIC_CACHE = 'survivor-static-v3.6.1';
const DYNAMIC_CACHE = 'survivor-dynamic-v3.6.1';

// Assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/index-optimized.html',
    '/styles.css',
    '/game.js',
    '/network.js',
    '/ui.js',
    '/narrator.js',
    '/state-manager.js',
    '/manifest.json',
    '/icon-192x192.png',
    '/icon-512x512.png',
    'https://cdn.socket.io/4.7.5/socket.io.min.js'
];

// API endpoints that can be cached
const CACHEABLE_API_ENDPOINTS = [
    '/api/cards',
    '/api/winners'
];

// Maximum cache age in milliseconds
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000; // 24 hours
const DYNAMIC_CACHE_MAX_ITEMS = 50;

/**
 * Service Worker Installation
 */
self.addEventListener('install', event => {
    console.log('🔧 Service Worker installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => {
                console.log('📦 Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => {
                console.log('✅ Service Worker installed');
                return self.skipWaiting();
            })
            .catch(error => {
                console.error('❌ Service Worker installation failed:', error);
            })
    );
});

/**
 * Service Worker Activation
 */
self.addEventListener('activate', event => {
    console.log('🚀 Service Worker activating...');
    
    event.waitUntil(
        Promise.all([
            // Clean up old caches
            cleanupOldCaches(),
            // Take control of all clients
            self.clients.claim()
        ]).then(() => {
            console.log('✅ Service Worker activated');
        })
    );
});

/**
 * Fetch Event Handler
 */
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') {
        return;
    }
    
    // Skip Socket.IO requests
    if (url.pathname.includes('socket.io')) {
        return;
    }
    
    // Handle different types of requests.
    // API first: game state must NEVER be served cache-first.
    if (isAPIRequest(url)) {
        event.respondWith(handleAPIRequest(request));
    } else if (isStaticAsset(url)) {
        event.respondWith(handleStaticAsset(request));
    } else if (isNavigationRequest(request)) {
        event.respondWith(handleNavigationRequest(request));
    } else {
        event.respondWith(handleDynamicRequest(request));
    }
});

/**
 * Background Sync (for offline actions)
 */
self.addEventListener('sync', event => {
    console.log('🔄 Background sync triggered:', event.tag);
    
    if (event.tag === 'survivor-offline-actions') {
        event.waitUntil(syncOfflineActions());
    }
});

/**
 * Push Notifications (future feature)
 */
self.addEventListener('push', event => {
    const options = {
        body: event.data ? event.data.text() : 'Game update available',
        icon: '/icon-192x192.png',
        badge: '/icon-192x192.png',
        vibrate: [100, 50, 100],
        data: {
            dateOfArrival: Date.now(),
            primaryKey: 1
        },
        actions: [
            {
                action: 'explore',
                title: 'View Game',
                icon: '/icon-192x192.png'
            },
            {
                action: 'close',
                title: 'Close',
                icon: '/icon-192x192.png'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification('Survivor Game', options)
    );
});

/**
 * Helper Functions
 */

function isStaticAsset(url) {
    // NEVER treat an API call as a static asset — those are network-first.
    if (isAPIRequest(url)) return false;

    const staticExtensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico', '.json'];
    if (staticExtensions.some(ext => url.pathname.endsWith(ext))) return true;

    // Match precached entries by exact pathname (for same-origin) or exact href
    // (for the CDN entry). The old `url.href.includes(asset)` test matched EVERY
    // request because STATIC_ASSETS contains '/', so live game state was served
    // cache-first and every resync returned permanently stale data.
    return STATIC_ASSETS.some(asset =>
        asset.startsWith('http') ? url.href === asset : url.pathname === asset
    );
}

function isAPIRequest(url) {
    return url.pathname.startsWith('/api/');
}

function isNavigationRequest(request) {
    const accept = request.headers.get('accept') || '';
    return request.mode === 'navigate' ||
           (request.method === 'GET' && accept.includes('text/html'));
}

/**
 * Static Asset Handler (Cache First Strategy)
 */
async function handleStaticAsset(request) {
    try {
        // Try cache first
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Fetch from network and cache
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('Static asset fetch failed:', error);
        // Return offline fallback if available
        return new Response('Offline', { status: 503 });
    }
}

/**
 * API Request Handler (Network First with Cache Fallback)
 */
async function handleAPIRequest(request) {
    let networkResponse;

    try {
        // Try network first, bypassing the HTTP cache entirely — game state changes
        // several times a second and a reused response silently desyncs the board.
        networkResponse = await fetch(new Request(request, { cache: 'no-store' }));
    } catch (error) {
        // The request never reached the server — this is the only real offline case.
        console.log('API request failed, trying cache:', error.message);

        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }

        return new Response(JSON.stringify({
            success: false,
            message: 'Offline - this action will be retried when connection is restored',
            offline: true
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }

    // Cache successful GET requests for certain endpoints
    if (networkResponse.ok && CACHEABLE_API_ENDPOINTS.some(endpoint => request.url.includes(endpoint))) {
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, networkResponse.clone());
    }

    // The server answered. Pass it through even when it's a 404 or a 500 — a wiped
    // game must read as "gone", not as "you're offline".
    return networkResponse;
}

/**
 * Navigation Request Handler (Cache First with Network Fallback)
 */
async function handleNavigationRequest(request) {
    try {
        // Try cache first for the main app
        const cachedResponse = await caches.match('/index-optimized.html') || 
                              await caches.match('/');
        
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Try network
        return await fetch(request);
    } catch (error) {
        // Return offline page
        return new Response(`
            <!DOCTYPE html>
            <html>
            <head>
                <title>Survivor - Offline</title>
                <meta name="viewport" content="width=device-width,initial-scale=1">
                <style>
                    body { 
                        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        min-height: 100vh;
                        margin: 0;
                        background: #0e1916;
                        color: #f7f5ef;
                        text-align: center;
                    }
                    .offline-content {
                        max-width: 400px;
                        padding: 2rem;
                    }
                    .btn {
                        background: #e07a2e;
                        color: white;
                        border: none;
                        padding: 1rem 2rem;
                        border-radius: 8px;
                        cursor: pointer;
                        margin-top: 1rem;
                    }
                </style>
            </head>
            <body>
                <div class="offline-content">
                    <h1>🏝️ Survivor</h1>
                    <p>You're currently offline. Please check your connection and try again.</p>
                    <button class="btn" onclick="location.reload()">Retry</button>
                </div>
            </body>
            </html>
        `, {
            headers: { 'Content-Type': 'text/html' }
        });
    }
}

/**
 * Dynamic Request Handler (Network First)
 */
async function handleDynamicRequest(request) {
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            // Cache in dynamic cache with size limit
            const cache = await caches.open(DYNAMIC_CACHE);
            await limitCacheSize(cache, DYNAMIC_CACHE_MAX_ITEMS);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        // Try cache fallback
        const cachedResponse = await caches.match(request);
        return cachedResponse || new Response('Offline', { status: 503 });
    }
}

/**
 * Cache Management
 */
async function cleanupOldCaches() {
    const cacheNames = await caches.keys();
    const oldCaches = cacheNames.filter(name => 
        name !== STATIC_CACHE && 
        name !== DYNAMIC_CACHE && 
        name.startsWith('survivor-')
    );
    
    return Promise.all(
        oldCaches.map(cacheName => {
            console.log('🗑️ Deleting old cache:', cacheName);
            return caches.delete(cacheName);
        })
    );
}

async function limitCacheSize(cache, maxItems) {
    const keys = await cache.keys();
    if (keys.length > maxItems) {
        // Remove oldest entries
        const excessKeys = keys.slice(0, keys.length - maxItems);
        await Promise.all(excessKeys.map(key => cache.delete(key)));
    }
}

/**
 * Offline Action Sync
 */
async function syncOfflineActions() {
    try {
        // Get offline actions from IndexedDB (would need to implement storage)
        const offlineActions = await getOfflineActions();
        
        for (const action of offlineActions) {
            try {
                const response = await fetch(action.url, action.options);
                if (response.ok) {
                    await removeOfflineAction(action.id);
                    console.log('✅ Synced offline action:', action.type);
                }
            } catch (error) {
                console.error('❌ Failed to sync action:', action.type, error);
            }
        }
    } catch (error) {
        console.error('❌ Background sync failed:', error);
    }
}

// Placeholder functions for offline action storage
async function getOfflineActions() {
    // Would implement IndexedDB storage for offline actions
    return [];
}

async function removeOfflineAction(id) {
    // Would implement removal from IndexedDB
    return true;
}

/**
 * Message Handling (for communication with main thread)
 */
self.addEventListener('message', event => {
    const { type, payload } = event.data;
    
    switch (type) {
        case 'SKIP_WAITING':
            self.skipWaiting();
            break;
        case 'CACHE_URLS':
            event.waitUntil(cacheUrls(payload.urls));
            break;
        case 'CLEAR_CACHE':
            event.waitUntil(clearCaches());
            break;
        default:
            console.log('Unknown message type:', type);
    }
});

async function cacheUrls(urls) {
    const cache = await caches.open(DYNAMIC_CACHE);
    return Promise.all(
        urls.map(url => 
            fetch(url).then(response => {
                if (response.ok) {
                    return cache.put(url, response);
                }
            }).catch(error => {
                console.error('Failed to cache URL:', url, error);
            })
        )
    );
}

async function clearCaches() {
    const cacheNames = await caches.keys();
    return Promise.all(
        cacheNames.map(cacheName => caches.delete(cacheName))
    );
}

console.log('🎮 Survivor Service Worker loaded');