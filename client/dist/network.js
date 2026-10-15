/**
 * Survivor Game - Network Communication Module
 * Handles API calls, Socket.IO communication, and state synchronization
 */

// Network state
let isOnline = navigator.onLine;

// Configuration
const API_URL = window.API_URL || window.location.origin;
const REQUEST_TIMEOUT = 10000;
const SOCKET_CONNECT_TIMEOUT = 10000;
// How long a dropped socket may stay down before the player is told about it.
// A server bounce or a tunnel blip usually heals inside this window, and a
// toast for every blip was most of the old "toast storm".
const CONNECTION_LOST_NOTICE_MS = 8000;

/**
 * The server says our game is gone — clear this device and head back to shore.
 * Debounced because several in-flight requests can 404 at once.
 */
let gameGoneHandled = false;
function handleGameGone() {
    if (gameGoneHandled || !window.SurvivorGame?.localGameState?.gameId) return;
    gameGoneHandled = true;
    setTimeout(() => { gameGoneHandled = false; }, 5000);

    showToast('That game is gone — back to the start screen', 'info');
    window.SurvivorGame?.wipeLocalGame();
}

/**
 * API call with error handling.
 *
 * Retries: only GETs, and only when the request never got an answer (network
 * error). A POST is an action — resending one the server may already have
 * applied could steal or vote twice — and an answer from the server (a 400
 * refusal, a 403, a 404) is final: retrying it just made the player wait ~7s
 * and then toasted the same refusal again.
 *
 * options.silent: no success/error toasts (background bookkeeping calls).
 */
async function apiCall(endpoint, data = {}, method = 'POST', options = {}) {
    const isRead = method === 'GET' || method === 'HEAD';
    const {
        timeout = REQUEST_TIMEOUT,
        retries = isRead ? 2 : 0,
        retryDelay = 1000,
        silent = false
    } = options;

    const requestOptions = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-Request-ID': generateRequestId()
        }
    };
    if (!isRead) {
        requestOptions.body = JSON.stringify(data);
    }

    const maxRetries = isRead ? retries : 0;
    let lastError;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        try {
            requestOptions.signal = controller.signal;
            const response = await fetch(`${API_URL}/api${endpoint}`, requestOptions);

            if (!response.ok) {
                // Try to get error message from response
                const errorData = await response.json().catch(() => ({}));
                if (response.status === 404 && endpoint.startsWith('/game/')) {
                    // Our game no longer exists — someone wiped it while this phone
                    // was asleep and missed the broadcast. Go home instead of
                    // polling a dead game code forever.
                    handleGameGone();
                }
                const httpError = new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
                httpError.status = response.status;
                throw httpError;
            }

            const contentType = response.headers.get("content-type");
            const result = contentType && contentType.includes("application/json")
                ? await response.json()
                : await response.text();

            // The server's own words for a completed action are worth showing
            // ("You'll hear the conch from anywhere"); a generic "Operation
            // completed successfully" on every tap was not.
            if (!silent && !isRead && result && result.success && result.message) {
                showToast(result.message, 'success');
            }

            return result;

        } catch (error) {
            lastError = error;
            // The server answered (status set) or we timed out: final.
            if (error.status || error.name === 'AbortError' || attempt >= maxRetries) break;
            await sleep(retryDelay * Math.pow(2, attempt));
        } finally {
            clearTimeout(timeoutId);
        }
    }

    console.error('API Call failed:', lastError);
    if (!silent) {
        const message = lastError?.name === 'AbortError'
            ? 'The island is slow to answer — try again'
            : (lastError?.message || 'Network error occurred');
        showToast(message, 'error');
    }

    throw lastError;
}

/**
 * Socket.IO connection, ONE reconnection mechanism: Socket.IO's own.
 *
 * The old code ran Socket.IO's built-in reconnection AND a home-made timer
 * loop on top of it. The timers stacked (one per disconnect and per
 * connect_error), each one tore down whatever socket existed — including a
 * healthy one the built-in loop had just reconnected — and each toasted, so a
 * server bounce produced a storm of "Reconnecting... (n/10)" toasts and often
 * ended at a false "Please refresh the page".
 *
 * Now: one socket object per game, created once; Socket.IO reconnects it with
 * jittered exponential backoff, forever. Handlers are attached once, when the
 * socket is created, and survive every reconnect. `kick()` forces an immediate
 * retry when the page comes back to the foreground (iOS throttles timers in
 * the background) or the device comes back online.
 */
class SocketManager {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.eventListeners = new Map();
        this.connectionPromise = null;
        this.heartbeatInterval = null;
        this.latency = 0;
        this.latencyHistory = [];
        this.roomGameId = null; // Which game's broadcast room we're in
        this.intentionalDisconnect = false; // We hung up on purpose (left/wiped)
        this.everConnected = false;  // this socket has been up before → next connect is a REconnect
        this.lostNoticeTimer = null;
        this.lostNoticeShown = false;
        this._expectedClose = false;  // kick() is hanging up only to dial again
    }

    /**
     * Start heartbeat to keep WebSocket connection alive through Cloudflare
     * Also measures latency for connection quality indicator
     */
    startHeartbeat() {
        this.stopHeartbeat();
        this.heartbeatInterval = setInterval(() => {
            if (this.socket && this.isConnected) {
                const pingStart = performance.now();
                this.socket.volatile.emit('heartbeat', { t: pingStart }, () => {
                    this.latency = Math.round(performance.now() - pingStart);
                    this.latencyHistory.push(this.latency);
                    if (this.latencyHistory.length > 10) this.latencyHistory.shift();
                    this.updateConnectionQuality();
                });
            }
        }, 15000); // Ping every 15 seconds
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    /**
     * Get connection quality based on recent latency
     * Returns 'good' (<150ms), 'fair' (150-400ms), or 'poor' (>400ms)
     */
    getConnectionQuality() {
        if (!this.isConnected) return 'offline';
        if (this.latencyHistory.length === 0) return 'good';
        const avg = this.latencyHistory.reduce((a, b) => a + b, 0) / this.latencyHistory.length;
        if (avg < 150) return 'good';
        if (avg < 400) return 'fair';
        return 'poor';
    }

    updateConnectionQuality() {
        const quality = this.getConnectionQuality();
        if (window.SurvivorUI?.updateNetworkStatus) {
            const labels = { good: 'Connected', fair: 'Slow connection', poor: 'Poor connection' };
            window.SurvivorUI.updateNetworkStatus(true, labels[quality] || 'Connected');
        }
        // Update quality CSS class on indicator
        const indicator = document.getElementById('networkStatus');
        if (indicator) {
            indicator.classList.remove('status-fair', 'status-poor');
            if (quality === 'fair') indicator.classList.add('status-fair');
            if (quality === 'poor') indicator.classList.add('status-poor');
        }
    }

    /**
     * Connect (or make sure we are connected) and join `gameId`'s room.
     * Safe to call any number of times; resolves with the socket once it is
     * up, rejects on timeout. Callers must .catch() — a rejection only means
     * "not yet": Socket.IO keeps trying in the background.
     */
    connect(gameId = null) {
        this.intentionalDisconnect = false;
        if (gameId) this.roomGameId = gameId;

        if (typeof io !== 'function') {
            return Promise.reject(new Error('Socket.IO client not loaded'));
        }
        if (!this.socket) this._createSocket();

        if (this.socket.connected) {
            // Already up — players almost always pick their game *after* that,
            // so the room still needs joining or every room broadcast silently
            // misses this device.
            if (gameId) this._joinRoom();
            return Promise.resolve(this.socket);
        }

        // Not subscribed any more (e.g. the server refused the handshake) —
        // Socket.IO won't retry on its own from there.
        if (!this.socket.active) this.socket.connect();
        return this._waitForConnect();
    }

    /** Force an immediate attempt instead of waiting out the backoff timer. */
    kick(gameId = null) {
        if (this.intentionalDisconnect && !gameId) return Promise.resolve(null);
        if (this.socket && !this.socket.connected) {
            // disconnect() cancels the pending backoff timer; connect() opens now.
            this._expectedClose = true;
            this.socket.disconnect();
            this._expectedClose = false;
            this.socket.connect();
        }
        return this.connect(gameId || this.roomGameId);
    }

    _waitForConnect() {
        if (this.connectionPromise) return this.connectionPromise;
        const socket = this.socket;
        this.connectionPromise = new Promise((resolve, reject) => {
            const onConnect = () => { cleanup(); resolve(socket); };
            const timer = setTimeout(() => {
                cleanup();
                reject(new Error('Socket connection timeout'));
            }, SOCKET_CONNECT_TIMEOUT);
            const cleanup = () => {
                clearTimeout(timer);
                socket.off('connect', onConnect);
                this.connectionPromise = null;
            };
            socket.on('connect', onConnect);
        });
        return this.connectionPromise;
    }

    /** The playerId rides along so the server also drops this socket into its
     *  private room (gid::pid) for player-only events like a robbery banner. */
    _joinRoom() {
        const gameId = this.roomGameId || window.SurvivorGame?.localGameState?.gameId;
        if (!gameId || !this.socket?.connected) return;
        this.roomGameId = gameId;
        const playerId = window.SurvivorGame?.localGameState?.playerId;
        this.socket.emit('join', playerId ? { gameId, playerId } : { gameId });
    }

    _createSocket() {
        const socket = io(API_URL, {
            transports: ['websocket', 'polling'],
            timeout: 20000,
            forceNew: true,
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 500,
            reconnectionDelayMax: 3000,
            randomizationFactor: 0.5
        });
        this.socket = socket;
        this.everConnected = false;

        // Every handler registered through on() — before or after this socket
        // existed — is attached exactly once, here. Socket.IO keeps the same
        // socket object across reconnects, so nothing is ever re-added.
        for (const [event, handlers] of this.eventListeners) {
            for (const handler of handlers) socket.on(event, handler);
        }

        socket.on('connect', () => {
            const wasReconnect = this.everConnected;
            this.everConnected = true;
            this.isConnected = true;
            this.reconnectAttempts = 0;
            console.log(wasReconnect ? '✅ Socket reconnected' : '✅ Socket connected');

            this._clearLostNotice(wasReconnect);
            window.SurvivorUI?.updateNetworkStatus?.(true, 'Connected');
            this.startHeartbeat();

            // (Re)join the room. The server answers a join with a fresh
            // state_update, which is what heals a board that missed pushes.
            this._joinRoom();

            // Tell the server this seat is back (marks the player connected).
            const gameId = this.roomGameId;
            const playerId = window.SurvivorGame?.localGameState?.playerId;
            if (wasReconnect && gameId && playerId) {
                GameAPI.rejoinGame(gameId, playerId, { silent: true }).catch(() => {});
            }
        });

        socket.on('disconnect', (reason) => {
            this.isConnected = false;
            this.stopHeartbeat();
            console.log('❌ Socket disconnected:', reason);

            // Leaving or wiping a game hangs up on purpose — no alarm.
            if (this.intentionalDisconnect || this._expectedClose || reason === 'io client disconnect') return;
            this._connectionLost();
            // 'io server disconnect' is the server hanging up deliberately —
            // Socket.IO won't retry that by itself; kick() on the next
            // foreground/online event will.
        });

        socket.on('connect_error', (error) => {
            console.warn('Socket connection error:', error?.message || error);
            if (this.intentionalDisconnect) return;
            if (this.everConnected) this._connectionLost();
        });

        socket.io.on('reconnect_attempt', (attempt) => {
            this.reconnectAttempts = attempt;
            window.SurvivorUI?.showReconnecting?.(attempt);
        });
    }

    /** One status for a whole outage: indicator now, a single notice if it lasts. */
    _connectionLost() {
        window.SurvivorUI?.updateNetworkStatus?.(false, 'Reconnecting…');
        if (this.lostNoticeShown || this.lostNoticeTimer) return;
        this.lostNoticeTimer = setTimeout(() => {
            this.lostNoticeTimer = null;
            if (this.isConnected || this.intentionalDisconnect) return;
            this.lostNoticeShown = true;
            window.SurvivorUI?.hapticFeedback?.('error');
            const status = window.SurvivorUI?.showStatus;
            if (status) status('connection', 'Connection lost — reconnecting…', 'warning');
            else showToast('Connection lost — reconnecting…', 'warning');
        }, CONNECTION_LOST_NOTICE_MS);
    }

    _clearLostNotice(announce) {
        if (this.lostNoticeTimer) {
            clearTimeout(this.lostNoticeTimer);
            this.lostNoticeTimer = null;
        }
        if (this.lostNoticeShown) {
            this.lostNoticeShown = false;
            window.SurvivorUI?.clearStatus?.('connection');
            if (announce) {
                showToast('Connection restored', 'success');
                window.SurvivorUI?.hapticFeedback?.('success');
            }
        }
    }

    emit(event, data) {
        if (this.socket && this.isConnected) {
            this.socket.emit(event, data);
        } else {
            console.warn('Socket not connected, dropping event:', event);
        }
    }

    on(event, handler) {
        if (this.socket) {
            this.socket.on(event, handler);
        }
        // Stored so a socket created later gets it too
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(handler);
    }

    off(event, handler) {
        if (this.socket) {
            this.socket.off(event, handler);
        }
        if (this.eventListeners.has(event)) {
            const handlers = this.eventListeners.get(event);
            const index = handlers.indexOf(handler);
            if (index !== -1) handlers.splice(index, 1);
        }
    }

    /** Hang up for good (left or wiped the game). Nothing may reconnect after this. */
    disconnect() {
        this.intentionalDisconnect = true;
        this.stopHeartbeat();
        this._clearLostNotice(false);
        if (this.socket) {
            const socket = this.socket;
            this.socket = null;
            socket.io.off('reconnect_attempt');
            socket.disconnect();
            socket.off();
        }
        this.isConnected = false;
        this.everConnected = false;
        this.reconnectAttempts = 0;
        this.connectionPromise = null;
        this.roomGameId = null;
    }
}

const socketManager = new SocketManager();

/**
 * One state pipeline: every server push goes through window.updateGameState
 * exactly once (it guards against other games' and older states, stores the
 * state and renders the current screen).
 */
function applyServerState(gameState) {
    if (gameState && window.updateGameState) window.updateGameState(gameState);
}

/**
 * Resync once — on returning to the foreground, the device coming back online,
 * or a test asking for it. One GET, no retries (the next foreground will try
 * again), and a socket kick if the socket isn't up.
 */
let resyncInFlight = false;
async function resyncNow() {
    // Card definitions load once at boot; a boot during a tunnel blip left
    // the hand unplayable for the whole session.
    window.SurvivorGame?.ensureCardDefinitions?.();
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    if (!gameId) return null;
    if (!socketManager.isConnected) socketManager.kick(gameId).catch(() => {});
    if (resyncInFlight) return null;
    resyncInFlight = true;
    try {
        const state = await apiCall(`/game/${encodeURIComponent(gameId)}/state`, {}, 'GET',
            { retries: 0, silent: true });
        if (state && typeof state === 'object' && state.id) applyServerState(state);
        return state;
    } catch (error) {
        console.warn('Resync failed:', error?.message || error);
        return null;
    } finally {
        resyncInFlight = false;
    }
}

/**
 * Turn notifications: the push subscription lives on this device, but the
 * server files it under (game, player). A new game — or a subscription the push
 * service rotated — means the server has to hear about it again, or
 * notifications silently stop after the first game.
 */
async function resendPushSubscription() {
    try {
        if (!window.SurvivorSettings?.get('turnNotifications')) return;
        if (!('serviceWorker' in navigator) || !('Notification' in window)) return;
        if (Notification.permission !== 'granted') return;
        const gameId = window.SurvivorGame?.localGameState?.gameId;
        const playerId = window.SurvivorGame?.localGameState?.playerId;
        if (!gameId || !playerId) return;
        const reg = await navigator.serviceWorker.getRegistration();
        const subscription = await reg?.pushManager?.getSubscription();
        if (!subscription) return;
        await GameAPI.pushSubscribe(gameId, playerId, subscription.toJSON(), { silent: true });
    } catch (error) {
        console.warn('Could not re-send the push subscription:', error?.message || error);
    }
}

/**
 * Network status monitoring
 */
function setupNetworkMonitoring() {
    window.addEventListener('online', () => {
        isOnline = true;
        console.log('📶 Connection restored');
        window.SurvivorUI?.updateNetworkStatus?.(true, 'Online');
        resyncNow();
    });

    window.addEventListener('offline', () => {
        isOnline = false;
        console.log('📵 Connection lost');
        window.SurvivorUI?.updateNetworkStatus?.(false, 'Offline');
    });

    // A phone that slept through pushes (or whose socket died in the
    // background) catches up the moment it is looked at again.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') resyncNow();
    });
}

/**
 * Game-specific API calls
 */
const GameAPI = {
    // Game management
    async createGame(options = {}) {
        const { deckMode = 'official', expansion = false } = options;
        return apiCall('/game/create', { deckMode, expansion });
    },

    async joinGame(gameId, name, color, discordUserId) {
        // discordUserId is optional and only sent when this device has one, so
        // a server that predates places sees exactly the old payload. Defaults
        // to whatever is saved in settings.
        const body = { gameId, name, color };
        const discord = discordUserId ?? window.SurvivorSettings?.discordUserId?.() ?? '';
        if (discord) body.discordUserId = discord;
        return apiCall('/player/join', body);
    },

    async rejoinGame(gameId, playerId, options = {}) {
        // A phone coming back carries its Discord link along — that is how an
        // ID typed into settings AFTER joining ever reaches the server.
        const body = { gameId, playerId };
        const discord = window.SurvivorSettings?.discordUserId?.() || '';
        if (discord) body.discordUserId = discord;
        return apiCall('/player/rejoin', body, 'POST', options);
    },

    async startGame(gameId) {
        return apiCall('/game/start_full', { gameId });
    },

    // Turn actions
    async stealCard(gameId, thiefId, targetId) {
        return apiCall('/turn/steal', { gameId, thiefId, targetId });
    },

    async playCard(gameId, playerId, cardIdx, params = {}) {
        // Extra params (targetId, allyId, cardType, ...) ride along to the server,
        // which reads them as card-effect kwargs.
        return apiCall('/turn/play_card', { gameId, playerId, cardIdx, ...params });
    },

    async drawCard(gameId, playerId) {
        return apiCall('/turn/draw', { gameId, playerId });
    },

    async advanceTurn(gameId) {
        return apiCall('/turn/advance', { gameId });
    },

    // Places — walk yourself to another spot around camp. The server refuses
    // when a place is forced (Tribal Council) or is not in placePolicy.open.
    async movePlace(gameId, playerId, place) {
        return apiCall('/place/move', { gameId, playerId, place });
    },

    // Let's Go To Rocks challenges
    async challengeAction(gameId, playerId, action, value = null) {
        return apiCall('/challenge/action', { gameId, playerId, action, value });
    },

    // Reactive theft window (Sorry For You)
    async playReactiveCard(gameId, playerId, cardIdx) {
        return apiCall('/reactive/play_card', { gameId, playerId, cardIdx });
    },

    // Reward Challenge interactions (Do Or Die / Power Pair / Numbers Game)
    async interactionAct(gameId, playerId, action, value = null) {
        return apiCall('/interaction/act', { gameId, playerId, action, value });
    },

    async completeTheft(gameId, playerId) {
        return apiCall('/reactive/complete_theft', { gameId, playerId });
    },

    // Self-leave, lobby only — the server refuses once the game has started.
    async leaveGame(gameId, playerId) {
        return apiCall('/player/leave', { gameId, playerId });
    },

    // State sync — GET-only route on the server
    async fetchGameState(gameId) {
        return apiCall(`/game/${encodeURIComponent(gameId)}/state`, {}, 'GET');
    },

    // Tribal council
    async startVoting(gameId, voteType) {
        return apiCall('/vote/start', { gameId, voteType });
    },

    async castVote(gameId, voterId, votesData) {
        return apiCall('/vote/cast', { gameId, voterId, votesData });
    },

    async updateGameSettings(gameId, playerId, settings) {
        return apiCall('/game/update_settings', { gameId, playerId, settings });
    },

    async pushPubkey() {
        const response = await fetch('/api/push/pubkey', { cache: 'no-store' });
        return response.ok ? response.json() : null;
    },

    async pushSubscribe(gameId, playerId, subscription, options = {}) {
        return apiCall('/push/subscribe', { gameId, playerId, subscription }, 'POST', options);
    },

    async pushUnsubscribe(gameId, playerId) {
        return apiCall('/push/unsubscribe', { gameId, playerId });
    },

    async playImmunity(gameId, playerId) {
        return apiCall('/immunity/play', { gameId, playerId });
    },

    async blockImmunity(gameId, targetId) {
        return apiCall('/immunity/block', { gameId, targetId });
    },

    async declineNullifier(gameId, playerId) {
        return apiCall('/immunity/decline', { gameId, playerId });
    },

    async choosePenaltyDiscard(gameId, playerId, cardIdx) {
        return apiCall('/reactive/choose_discard', { gameId, playerId, cardIdx });
    },

    async revealVotes(gameId) {
        return apiCall('/vote/reveal', { gameId });
    },

    async completeTribal(gameId) {
        return apiCall('/tribal/complete', { gameId });
    },

    // Game state
    async resetGame(gameId) {
        return apiCall('/game/reset', { gameId });
    },

    async recordWinner(gameId, winnerId) {
        return apiCall('/game/finish', { gameId, winnerId });
    }
};

/**
 * Utility functions
 */
function generateRequestId() {
    return Math.random().toString(36).substring(2) + Date.now().toString(36);
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function showToast(message, type = 'info') {
    // This will be implemented in ui.js
    if (window.SurvivorUI && window.SurvivorUI.showToast) {
        window.SurvivorUI.showToast(message, type);
    } else {
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}

/**
 * Setup Socket.IO event handlers — registered ONCE, at module start, through
 * socketManager.on() (which attaches them to the socket when it is created).
 * They used to be added inside the 'connect' handler, so every reconnect added
 * another copy and one push rendered the board several times over.
 */
function setupSocketEventHandlers() {
    socketManager.on('state_update', applyServerState);
    socketManager.on('game_updated', applyServerState);

    socketManager.on('player_joined', (data) => {
        if (data?.playerName) showToast(`${data.playerName} joined the game`, 'info');
    });

    socketManager.on('player_left', (data) => {
        if (data?.playerName) showToast(`${data.playerName} left the game`, 'info');
    });

    socketManager.on('game_reset', (data) => {
        if (data && data.gameId && window.SurvivorGame?.localGameState?.gameId === data.gameId) {
            console.log('🔄 Game reset received');
            showToast('Game has been reset', 'info');

            // A robbed banner — on stage or still queued — belongs to the
            // game that just ended; it must not play into the next one.
            window.SurvivorNarrator?.clearRobberies?.();

            // The seat is gone with the game: forget it on this device too,
            // or the next cold start tries to rejoin it.
            if (window.SurvivorGame?.wipeLocalGame) {
                window.SurvivorGame.wipeLocalGame();
            } else {
                try { localStorage.removeItem('survivorState'); } catch (e) { /* ignore */ }
            }
        }
    });

    // The game was wiped for everyone — clear this device completely.
    socketManager.on('game_wiped', (data) => {
        const localId = window.SurvivorGame?.localGameState?.gameId;
        if (data && data.gameId && localId && data.gameId !== localId) return;
        console.log('🔥 Game wiped');
        showToast('The camp was struck — this game is gone', 'info');
        window.SurvivorGame?.wipeLocalGame();
    });

    socketManager.on('error', (error) => {
        // Server-sent socket errors ({message}) — log; the HTTP paths surface
        // anything the player needs to act on.
        console.warn('Socket error from server:', error?.message || error);
    });
}

/**
 * Initialize network module
 */
function initializeNetwork() {
    setupNetworkMonitoring();
    setupSocketEventHandlers();

    console.log('📡 Network module initialized');
}

// Export the network interface
window.SurvivorNetwork = {
    // API
    apiCall,
    GameAPI,
    handleGameGone,

    // Socket management
    socketManager,

    // State
    resyncNow,
    resendPushSubscription,

    // Utilities
    isOnline: () => isOnline,
    isConnected: () => socketManager.isConnected,
    getLatency: () => socketManager.latency,
    getConnectionQuality: () => socketManager.getConnectionQuality(),

    // Initialization
    initialize: initializeNetwork
};

// Auto-initialize when module loads
document.addEventListener('DOMContentLoaded', function() {
    initializeNetwork();

    // Notify that module is ready
    if (window.onNetworkModuleReady) {
        window.onNetworkModuleReady();
    }
    console.log('✅ Network module ready');
});
