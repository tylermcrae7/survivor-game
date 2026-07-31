/**
 * Survivor Game - Network Communication Module
 * Handles API calls, Socket.IO communication, and state synchronization
 */

// Network state
let socket = null;
let originalEmit = null;
let isConnected = false;
let reconnectAttempts = 0;
let pendingRequests = new Map();
let requestQueue = [];
let isOnline = navigator.onLine;

// Configuration
const API_URL = window.API_URL || window.location.origin;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;
const REQUEST_TIMEOUT = 10000;
const BATCH_DELAY = 100;

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
 * Enhanced API call function with retry logic and error handling
 */
async function apiCall(endpoint, data = {}, method = 'POST', options = {}) {
    const {
        timeout = REQUEST_TIMEOUT,
        retries = 3,
        retryDelay = 1000
    } = options;
    
    const requestId = generateRequestId();
    const requestOptions = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-Request-ID': requestId
        }
    };
    
    if (method !== 'GET' && method !== 'HEAD') {
        requestOptions.body = JSON.stringify(data);
    }
    
    // Add to pending requests for tracking
    pendingRequests.set(requestId, {
        endpoint,
        data,
        method,
        timestamp: Date.now()
    });
    
    let lastError;
    
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeout);
            
            requestOptions.signal = controller.signal;
            
            const response = await fetch(`${API_URL}/api${endpoint}`, requestOptions);
            clearTimeout(timeoutId);
            
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
            
            // Remove from pending requests
            pendingRequests.delete(requestId);
            
            // Show success notification for important operations
            if (method !== 'GET' && result.success) {
                showToast(result.message || 'Operation completed successfully', 'success');
            }
            
            return result;
            
        } catch (error) {
            lastError = error;
            
            // Don't retry on certain errors
            if (error.name === 'AbortError' || error.status === 404 ||
                error.message.includes('400')) {
                break;
            }
            
            // Wait before retry
            if (attempt < retries) {
                await sleep(retryDelay * Math.pow(2, attempt));
            }
        }
    }
    
    // Remove from pending requests
    pendingRequests.delete(requestId);
    
    // Handle final error
    console.error('API Call failed:', lastError);
    showToast(lastError.message || 'Network error occurred', 'error');
    
    throw lastError;
}

/**
 * Request batching system for performance optimization
 */
class RequestBatcher {
    constructor(delay = BATCH_DELAY) {
        this.queue = [];
        this.timer = null;
        this.delay = delay;
    }
    
    add(request) {
        this.queue.push(request);
        
        if (!this.timer) {
            this.timer = setTimeout(() => this.flush(), this.delay);
        }
    }
    
    async flush() {
        if (this.queue.length === 0) return;
        
        const requests = [...this.queue];
        this.queue = [];
        this.timer = null;
        
        try {
            // Group requests by type for batching
            const batchableRequests = requests.filter(req => req.batchable);
            const individualRequests = requests.filter(req => !req.batchable);
            
            // Send batched requests
            if (batchableRequests.length > 1) {
                await apiCall('/batch', { operations: batchableRequests });
            } else if (batchableRequests.length === 1) {
                const req = batchableRequests[0];
                await apiCall(req.endpoint, req.data, req.method);
            }
            
            // Send individual requests
            await Promise.all(
                individualRequests.map(req => 
                    apiCall(req.endpoint, req.data, req.method)
                )
            );
            
        } catch (error) {
            console.error('Batch request failed:', error);
        }
    }
}

const requestBatcher = new RequestBatcher();

/**
 * Enhanced Socket.IO management with robust reconnection
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
        this.pendingEmits = []; // Queue events while disconnected
        this.roomGameId = null; // Which game's broadcast room we're in
        this.intentionalDisconnect = false; // We hung up on purpose (left/wiped)
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
     * Flush queued events that were buffered during disconnect
     */
    flushPendingEmits() {
        while (this.pendingEmits.length > 0) {
            const { event, data } = this.pendingEmits.shift();
            this.socket.emit(event, data);
        }
    }
    
    async connect(gameId = null) {
        this.intentionalDisconnect = false;
        if (this.connectionPromise) {
            // The socket is already up (or coming up) — players almost always pick
            // their game *after* that, so the room still needs joining or every
            // room broadcast silently misses this device.
            if (gameId) this.joinRoom(gameId);
            return this.connectionPromise;
        }

        this.roomGameId = gameId || this.roomGameId;
        this.connectionPromise = this._doConnect(gameId);
        return this.connectionPromise;
    }

    /** Join (or re-join) a game's broadcast room; queued if the socket isn't up yet. */
    joinRoom(gameId) {
        if (!gameId) return;
        this.roomGameId = gameId;
        this.emit('join', { gameId });
    }
    
    async _doConnect(gameId) {
        try {
            // Disconnect existing socket
            if (this.socket) {
                this.socket.disconnect();
            }
            
            this.socket = io(API_URL, {
                transports: ['websocket', 'polling'],
                timeout: 20000,
                forceNew: true
            });

            // Re-attach every handler registered through on() before this socket
            // existed. Module setup runs at DOMContentLoaded, long before the first
            // game is joined — without this, no server push ever reaches the app
            // and everything silently falls back to HTTP polling.
            for (const [storedEvent, handlers] of this.eventListeners) {
                for (const handler of handlers) {
                    this.socket.on(storedEvent, handler);
                }
            }

            // Set up event listeners
            this.socket.on('connect', () => {
                this.isConnected = true;
                const wasReconnecting = this.reconnectAttempts > 0;
                this.reconnectAttempts = 0;
                console.log('✅ Socket connected');

                // Update network status indicator
                if (window.SurvivorUI && window.SurvivorUI.updateNetworkStatus) {
                    window.SurvivorUI.updateNetworkStatus(true, 'Connected');
                }

                // Show reconnected message if we were reconnecting
                if (wasReconnecting) {
                    showToast('Connection restored!', 'success');
                    // Haptic feedback on reconnection
                    if (window.SurvivorUI && window.SurvivorUI.hapticFeedback) {
                        window.SurvivorUI.hapticFeedback('success');
                    }
                }

                // Start heartbeat for Cloudflare WebSocket keep-alive + latency
                this.startHeartbeat();

                // Join game room if provided (or rejoin on reconnect)
                const activeGameId = gameId || this.roomGameId ||
                                     window.SurvivorGame?.localGameState?.gameId;
                if (activeGameId) {
                    this.roomGameId = activeGameId;
                    this.socket.emit('join', { gameId: activeGameId });

                    // Request fresh state on reconnect
                    if (wasReconnecting) {
                        const playerId = window.SurvivorGame?.localGameState?.playerId;
                        if (playerId) {
                            GameAPI.rejoinGame(activeGameId, playerId).catch(() => {});
                        }
                    }
                }

                // Flush any events that were queued while disconnected
                this.flushPendingEmits();
                
                // Register game event handlers
                this.socket.on('game_updated', (gameState) => {
                    console.log('📊 Game updated received:', gameState);
                    if (window.updateGameState) {
                        window.updateGameState(gameState);
                    }
                    if (window.SurvivorUI) {
                        window.SurvivorUI.updateCurrentScreen(gameState);
                    }
                });
                
                this.socket.on('state_update', (gameState) => {
                    console.log('📊 State update received:', gameState);
                    if (window.updateGameState) {
                        window.updateGameState(gameState);
                    }
                    if (window.SurvivorUI) {
                        window.SurvivorUI.updateCurrentScreen(gameState);
                    }
                });
                
                this.socket.on('player_joined', (data) => {
                    console.log('👤 Player joined:', data);
                    if (window.showToast) {
                        window.showToast(`${data.playerName} joined the game`, 'info');
                    }
                });
                
                this.socket.on('player_left', (data) => {
                    console.log('👤 Player left:', data);
                    if (window.showToast) {
                        window.showToast(`${data.playerName} left the game`, 'info');
                    }
                });
                
                // Trigger custom connect handlers
                this.emit('connected');
            });
            
            this.socket.on('disconnect', (reason) => {
                this.isConnected = false;
                console.log('❌ Socket disconnected:', reason);

                // Stop heartbeat on disconnect
                this.stopHeartbeat();

                // Leaving or wiping a game hangs up on purpose — no alarm, no
                // reconnect loop dragging the player back into a dead game.
                if (this.intentionalDisconnect || reason === 'io client disconnect') {
                    return;
                }

                // Show disconnect notification
                showToast('Connection lost. Attempting to reconnect...', 'warning');

                // Update network status indicator
                if (window.SurvivorUI && window.SurvivorUI.updateNetworkStatus) {
                    window.SurvivorUI.updateNetworkStatus(false, 'Disconnected');
                }

                // Haptic feedback on disconnect
                if (window.SurvivorUI && window.SurvivorUI.hapticFeedback) {
                    window.SurvivorUI.hapticFeedback('error');
                }

                // Trigger custom disconnect handlers
                this.emit('disconnected', reason);

                // Schedule reconnection for unexpected disconnects
                if (reason === 'io server disconnect') {
                    // Server initiated disconnect - don't reconnect
                    return;
                }

                this.scheduleReconnect(gameId);
            });
            
            this.socket.on('connect_error', (error) => {
                console.error('Socket connection error:', error);
                this.emit('error', error);
                this.scheduleReconnect(gameId);
            });
            
            this.socket.on('error', (error) => {
                console.error('Socket error:', error);
                this.emit('error', error);
            });
            
            // Wait for connection
            await new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    reject(new Error('Socket connection timeout'));
                }, 10000);
                
                this.socket.on('connect', () => {
                    clearTimeout(timeout);
                    resolve();
                });
                
                this.socket.on('connect_error', (error) => {
                    clearTimeout(timeout);
                    reject(error);
                });
            });
            
            return this.socket;
            
        } finally {
            this.connectionPromise = null;
        }
    }
    
    scheduleReconnect(gameId) {
        if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            console.error('❌ Max reconnection attempts reached');
            showToast('Connection lost. Please refresh the page.', 'error');
            // Update network status indicator
            if (window.SurvivorUI && window.SurvivorUI.updateNetworkStatus) {
                window.SurvivorUI.updateNetworkStatus(false, 'Connection failed');
            }
            return;
        }

        const delay = Math.min(
            BASE_RECONNECT_DELAY * Math.pow(2, this.reconnectAttempts),
            MAX_RECONNECT_DELAY
        );

        this.reconnectAttempts++;

        console.log(`🔄 Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);

        // Show reconnecting UI feedback
        showToast(`Reconnecting... (${this.reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, 'warning');

        // Update network status indicator
        if (window.SurvivorUI && window.SurvivorUI.showReconnecting) {
            window.SurvivorUI.showReconnecting(this.reconnectAttempts);
        }

        setTimeout(() => {
            this.connect(gameId);
        }, delay);
    }
    
    emit(event, data) {
        if (this.socket && this.isConnected) {
            this.socket.emit(event, data);
        } else {
            console.warn('Socket not connected, queueing event:', event);
            // Queue non-internal events for replay on reconnect
            if (event !== 'connected' && event !== 'disconnected' && event !== 'error') {
                this.pendingEmits.push({ event, data });
            }
        }
    }
    
    on(event, handler) {
        if (this.socket) {
            this.socket.on(event, handler);
        }
        
        // Store for reconnection
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(handler);
    }
    
    off(event, handler) {
        if (this.socket) {
            this.socket.off(event, handler);
        }
        
        // Remove from stored listeners
        if (this.eventListeners.has(event)) {
            const handlers = this.eventListeners.get(event);
            const index = handlers.indexOf(handler);
            if (index !== -1) {
                handlers.splice(index, 1);
            }
        }
    }
    
    disconnect() {
        this.intentionalDisconnect = true;
        this.stopHeartbeat();
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        this.isConnected = false;
        this.reconnectAttempts = 0;
        // Without clearing these, the next connect() returns the old promise and
        // never opens a socket again.
        this.connectionPromise = null;
        this.roomGameId = null;
        this.pendingEmits = [];
    }
}

const socketManager = new SocketManager();

/**
 * State synchronization with diff-based updates
 */
let lastKnownState = {};
let stateUpdateQueue = [];
let isProcessingStateUpdate = false;

function processStateUpdate(newState) {
    if (isProcessingStateUpdate) {
        stateUpdateQueue.push(newState);
        return;
    }
    
    isProcessingStateUpdate = true;
    
    try {
        // Calculate diff
        const diff = calculateStateDiff(lastKnownState, newState);
        
        if (Object.keys(diff).length === 0) {
            // No changes
            return;
        }
        
        // Apply diff to local state
        Object.assign(window.SurvivorGame.fullGameState, diff);
        
        // Update last known state
        lastKnownState = JSON.parse(JSON.stringify(newState));
        
        // Trigger UI update with diff
        if (window.SurvivorUI && window.SurvivorUI.updateFromDiff) {
            window.SurvivorUI.updateFromDiff(diff);
        } else {
            // Fallback to full update
            window.updateGameState && window.updateGameState(newState);
        }
        
        console.log('📊 State updated with diff:', Object.keys(diff));
        
    } finally {
        isProcessingStateUpdate = false;
        
        // Process queued updates
        if (stateUpdateQueue.length > 0) {
            const nextUpdate = stateUpdateQueue.shift();
            setTimeout(() => processStateUpdate(nextUpdate), 0);
        }
    }
}

function calculateStateDiff(oldState, newState) {
    const diff = {};
    
    // Simple diff implementation - could be enhanced
    for (const key in newState) {
        if (JSON.stringify(oldState[key]) !== JSON.stringify(newState[key])) {
            diff[key] = newState[key];
        }
    }
    
    return diff;
}

/**
 * Network status monitoring
 */
function setupNetworkMonitoring() {
    window.addEventListener('online', () => {
        isOnline = true;
        console.log('📶 Connection restored');
        showToast('Internet connection restored', 'success');

        // Update network status indicator
        if (window.SurvivorUI && window.SurvivorUI.updateNetworkStatus) {
            window.SurvivorUI.updateNetworkStatus(true, 'Online');
        }

        // Haptic feedback
        if (window.SurvivorUI && window.SurvivorUI.hapticFeedback) {
            window.SurvivorUI.hapticFeedback('success');
        }

        // Reconnect socket if needed
        if (!socketManager.isConnected && window.SurvivorGame?.localGameState?.gameId) {
            socketManager.connect(window.SurvivorGame.localGameState.gameId);
        }
    });

    // Auto-connect if game is active
    setTimeout(() => {
        if (window.SurvivorGame?.localGameState?.gameId && !socketManager.isConnected) {
            console.log('🔌 Auto-connecting to game:', window.SurvivorGame.localGameState.gameId);
            socketManager.connect(window.SurvivorGame.localGameState.gameId);
        }
    }, 1000);

    window.addEventListener('offline', () => {
        isOnline = false;
        console.log('📵 Connection lost');
        showToast('No internet connection', 'warning');

        // Update network status indicator
        if (window.SurvivorUI && window.SurvivorUI.updateNetworkStatus) {
            window.SurvivorUI.updateNetworkStatus(false, 'Offline');
        }

        // Haptic feedback
        if (window.SurvivorUI && window.SurvivorUI.hapticFeedback) {
            window.SurvivorUI.hapticFeedback('warning');
        }
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
    
    async joinGame(gameId, name, color) {
        return apiCall('/player/join', { gameId, name, color });
    },
    
    async rejoinGame(gameId, playerId) {
        return apiCall('/player/rejoin', { gameId, playerId });
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

    async completeTheft(gameId) {
        return apiCall('/reactive/complete_theft', { gameId });
    },

    // State sync — GET-only route on the server
    async fetchGameState(gameId) {
        return apiCall(`/game/${gameId}/state`, {}, 'GET');
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

    async pushSubscribe(gameId, playerId, subscription) {
        return apiCall('/push/subscribe', { gameId, playerId, subscription });
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
 * Setup Socket.IO event handlers
 */
function setupSocketEventHandlers() {
    socketManager.on('state_update', processStateUpdate);
    
    socketManager.on('game_reset', (data) => {
        if (data && data.gameId && window.SurvivorGame.localGameState.gameId === data.gameId) {
            console.log('🔄 Game reset received');
            showToast('Game has been reset', 'info');
            
            // Reset local state
            window.SurvivorGame.localGameState.gameId = null;
            window.SurvivorGame.localGameState.playerId = null;
            window.SurvivorGame.fullGameState = {};
            
            // Navigate to start screen
            if (window.SurvivorUI && window.SurvivorUI.showScreen) {
                window.SurvivorUI.showScreen('startScreen');
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

    socketManager.on('global_reset', (data) => {
        console.log('🔄 Global reset received');
        // Handle global reset if needed
    });
    
    socketManager.on('error', (error) => {
        console.error('Socket error:', error);
        showToast('Connection error occurred', 'error');
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
    
    // State management
    processStateUpdate,
    
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