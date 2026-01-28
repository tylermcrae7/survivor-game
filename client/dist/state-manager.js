/**
 * Survivor Game - Advanced State Management Module
 * Implements state diffing, caching, and optimistic updates
 */

class StateManager {
    constructor() {
        this.state = {};
        this.lastKnownState = {};
        this.stateHistory = [];
        this.maxHistorySize = 10;
        this.pendingOptimisticUpdates = new Map();
        this.subscribers = new Map();
        this.compressor = new StateCompressor();
    }

    /**
     * Update state with diff-based system
     */
    updateState(newState, source = 'server') {
        const diff = this.calculateDiff(this.state, newState);
        
        if (Object.keys(diff).length === 0) {
            console.log('📊 No state changes detected');
            return false;
        }
        
        // Store previous state in history
        this.addToHistory(this.state);
        
        // Apply diff to current state
        this.state = this.mergeState(this.state, diff);
        this.lastKnownState = JSON.parse(JSON.stringify(newState));
        
        // Notify subscribers with diff
        this.notifySubscribers(diff, source);
        
        console.log(`📊 State updated from ${source}:`, Object.keys(diff));
        return true;
    }

    /**
     * Apply optimistic update (for immediate UI feedback)
     */
    applyOptimisticUpdate(updateId, statePatch) {
        console.log('⚡ Applying optimistic update:', updateId);
        
        // Store the update for potential rollback
        this.pendingOptimisticUpdates.set(updateId, {
            patch: statePatch,
            previousState: JSON.parse(JSON.stringify(this.state))
        });
        
        // Apply the update
        this.state = this.mergeState(this.state, statePatch);
        
        // Notify subscribers
        this.notifySubscribers(statePatch, 'optimistic');
    }

    /**
     * Confirm or rollback optimistic update
     */
    resolveOptimisticUpdate(updateId, success = true) {
        const pendingUpdate = this.pendingOptimisticUpdates.get(updateId);
        if (!pendingUpdate) return;
        
        if (!success) {
            console.log('🔄 Rolling back optimistic update:', updateId);
            // Rollback to previous state
            this.state = pendingUpdate.previousState;
            this.notifySubscribers(pendingUpdate.patch, 'rollback');
        } else {
            console.log('✅ Confirmed optimistic update:', updateId);
        }
        
        this.pendingOptimisticUpdates.delete(updateId);
    }

    /**
     * Calculate difference between two states
     */
    calculateDiff(oldState, newState) {
        const diff = {};
        
        // Check for added or modified properties
        for (const key in newState) {
            const oldValue = oldState[key];
            const newValue = newState[key];
            
            if (this.hasChanged(oldValue, newValue)) {
                if (typeof newValue === 'object' && newValue !== null && !Array.isArray(newValue)) {
                    // Nested object diff
                    const nestedDiff = this.calculateDiff(oldValue || {}, newValue);
                    if (Object.keys(nestedDiff).length > 0) {
                        diff[key] = newValue; // For now, replace entire object
                    }
                } else {
                    diff[key] = newValue;
                }
            }
        }
        
        // Check for deleted properties
        for (const key in oldState) {
            if (!(key in newState)) {
                diff[key] = undefined;
            }
        }
        
        return diff;
    }

    /**
     * Check if a value has changed
     */
    hasChanged(oldValue, newValue) {
        if (oldValue === newValue) return false;
        
        // Handle null/undefined
        if (oldValue == null && newValue == null) return false;
        if (oldValue == null || newValue == null) return true;
        
        // Handle arrays
        if (Array.isArray(oldValue) && Array.isArray(newValue)) {
            if (oldValue.length !== newValue.length) return true;
            return oldValue.some((item, index) => this.hasChanged(item, newValue[index]));
        }
        
        // Handle objects
        if (typeof oldValue === 'object' && typeof newValue === 'object') {
            const oldKeys = Object.keys(oldValue);
            const newKeys = Object.keys(newValue);
            
            if (oldKeys.length !== newKeys.length) return true;
            
            return oldKeys.some(key => this.hasChanged(oldValue[key], newValue[key]));
        }
        
        // Handle primitives
        return oldValue !== newValue;
    }

    /**
     * Merge state changes
     */
    mergeState(baseState, changes) {
        const result = { ...baseState };
        
        for (const key in changes) {
            if (changes[key] === undefined) {
                delete result[key];
            } else {
                result[key] = changes[key];
            }
        }
        
        return result;
    }

    /**
     * Add state to history
     */
    addToHistory(state) {
        this.stateHistory.push({
            state: JSON.parse(JSON.stringify(state)),
            timestamp: Date.now()
        });
        
        // Limit history size
        if (this.stateHistory.length > this.maxHistorySize) {
            this.stateHistory.shift();
        }
    }

    /**
     * Subscribe to state changes
     */
    subscribe(callback, filter = null) {
        const id = Math.random().toString(36).substring(2);
        this.subscribers.set(id, { callback, filter });
        
        return () => this.subscribers.delete(id);
    }

    /**
     * Notify all subscribers of state changes
     */
    notifySubscribers(diff, source) {
        this.subscribers.forEach(({ callback, filter }) => {
            if (!filter || this.matchesFilter(diff, filter)) {
                try {
                    callback(diff, this.state, source);
                } catch (error) {
                    console.error('Subscriber callback error:', error);
                }
            }
        });
    }

    /**
     * Check if diff matches subscriber filter
     */
    matchesFilter(diff, filter) {
        if (typeof filter === 'string') {
            return diff.hasOwnProperty(filter);
        }
        
        if (Array.isArray(filter)) {
            return filter.some(key => diff.hasOwnProperty(key));
        }
        
        if (typeof filter === 'function') {
            return filter(diff);
        }
        
        return true;
    }

    /**
     * Get current state
     */
    getState() {
        return { ...this.state };
    }

    /**
     * Get state history
     */
    getHistory() {
        return [...this.stateHistory];
    }

    /**
     * Restore state from history
     */
    restoreFromHistory(index = -1) {
        const historyEntry = this.stateHistory[index < 0 ? this.stateHistory.length + index : index];
        if (historyEntry) {
            this.state = JSON.parse(JSON.stringify(historyEntry.state));
            this.notifySubscribers(this.state, 'history');
            return true;
        }
        return false;
    }

    /**
     * Clear all state
     */
    clear() {
        this.state = {};
        this.lastKnownState = {};
        this.stateHistory = [];
        this.pendingOptimisticUpdates.clear();
        this.notifySubscribers({}, 'clear');
    }
}

/**
 * State Compression for efficient storage and transmission
 */
class StateCompressor {
    /**
     * Compress state for storage
     */
    compress(state) {
        try {
            // Simple JSON compression (could be enhanced with actual compression)
            const json = JSON.stringify(state);
            
            // Remove redundant data
            const compressed = json
                .replace(/{"type":/g, '{"t":')
                .replace(/,"category":/g, ',"c":')
                .replace(/,"name":/g, ',"n":')
                .replace(/,"description":/g, ',"d":')
                .replace(/,"isEliminated":false/g, '')
                .replace(/,"hasVoted":false/g, '')
                .replace(/,"hasStolen":false/g, '');
            
            console.log(`📦 Compressed state: ${json.length} → ${compressed.length} bytes (${Math.round((1 - compressed.length / json.length) * 100)}% reduction)`);
            
            return compressed;
        } catch (error) {
            console.error('State compression failed:', error);
            return JSON.stringify(state);
        }
    }

    /**
     * Decompress state from storage
     */
    decompress(compressedState) {
        try {
            // Reverse the compression
            const json = compressedState
                .replace(/{"t":/g, '{"type":')
                .replace(/,"c":/g, ',"category":')
                .replace(/,"n":/g, ',"name":')
                .replace(/,"d":/g, ',"description":');
            
            return JSON.parse(json);
        } catch (error) {
            console.error('State decompression failed:', error);
            return {};
        }
    }
}

/**
 * Local Storage Manager with compression
 */
class LocalStorageManager {
    constructor(stateManager) {
        this.stateManager = stateManager;
        this.storageKey = 'survivor-game-state';
        this.metadataKey = 'survivor-metadata';
        
        // Auto-save on state changes
        this.stateManager.subscribe((diff, state) => {
            this.saveState(state);
        });
    }

    /**
     * Save state to local storage
     */
    saveState(state) {
        try {
            const compressed = this.stateManager.compressor.compress(state);
            localStorage.setItem(this.storageKey, compressed);
            localStorage.setItem(this.metadataKey, JSON.stringify({
                timestamp: Date.now(),
                version: '1.0.0'
            }));
        } catch (error) {
            console.error('Failed to save state:', error);
        }
    }

    /**
     * Load state from local storage
     */
    loadState() {
        try {
            const compressed = localStorage.getItem(this.storageKey);
            const metadata = JSON.parse(localStorage.getItem(this.metadataKey) || '{}');
            
            if (!compressed) return null;
            
            // Check if state is too old (e.g., older than 24 hours)
            const maxAge = 24 * 60 * 60 * 1000;
            if (metadata.timestamp && Date.now() - metadata.timestamp > maxAge) {
                console.log('💨 Clearing old cached state');
                this.clearState();
                return null;
            }
            
            const state = this.stateManager.compressor.decompress(compressed);
            console.log('📂 Loaded state from local storage');
            return state;
        } catch (error) {
            console.error('Failed to load state:', error);
            return null;
        }
    }

    /**
     * Clear saved state
     */
    clearState() {
        localStorage.removeItem(this.storageKey);
        localStorage.removeItem(this.metadataKey);
    }
}

/**
 * Network State Synchronization
 */
class NetworkStateSyncer {
    constructor(stateManager, networkManager) {
        this.stateManager = stateManager;
        this.networkManager = networkManager;
        this.syncQueue = [];
        this.isSyncing = false;
        this.lastSyncTime = 0;
        this.syncInterval = 5000; // 5 seconds
        
        this.setupAutoSync();
    }

    /**
     * Setup automatic state synchronization
     */
    setupAutoSync() {
        // Sync on state changes (debounced)
        let syncTimeout;
        this.stateManager.subscribe((diff, state, source) => {
            if (source === 'optimistic') {
                clearTimeout(syncTimeout);
                syncTimeout = setTimeout(() => {
                    this.requestSync();
                }, 1000);
            }
        });

        // Periodic sync
        setInterval(() => {
            if (Date.now() - this.lastSyncTime > this.syncInterval) {
                this.requestSync();
            }
        }, this.syncInterval);

        // Sync on connectivity restore
        window.addEventListener('online', () => {
            this.requestSync();
        });
    }

    /**
     * Request state synchronization
     */
    async requestSync() {
        if (this.isSyncing || !this.networkManager.isOnline()) {
            return;
        }

        this.isSyncing = true;
        this.lastSyncTime = Date.now();

        try {
            // Get current game state from server
            const gameId = window.SurvivorGame?.localGameState?.gameId;
            if (!gameId) return;

            const serverState = await this.networkManager.apiCall(`/game/${gameId}/state`);
            if (serverState) {
                this.stateManager.updateState(serverState, 'sync');
            }
        } catch (error) {
            console.error('State sync failed:', error);
        } finally {
            this.isSyncing = false;
        }
    }

    /**
     * Send optimistic update to server
     */
    async sendOptimisticUpdate(updateId, action, data) {
        try {
            const result = await this.networkManager.apiCall(action.endpoint, data, action.method);
            
            if (result && result.success) {
                this.stateManager.resolveOptimisticUpdate(updateId, true);
            } else {
                this.stateManager.resolveOptimisticUpdate(updateId, false);
            }
            
            return result;
        } catch (error) {
            this.stateManager.resolveOptimisticUpdate(updateId, false);
            throw error;
        }
    }
}

// Create global state manager instance
const globalStateManager = new StateManager();
const localStorageManager = new LocalStorageManager(globalStateManager);

// Export for use in other modules
window.SurvivorStateManager = {
    manager: globalStateManager,
    storage: localStorageManager,
    
    // Convenience methods
    getState: () => globalStateManager.getState(),
    updateState: (state, source) => globalStateManager.updateState(state, source),
    subscribe: (callback, filter) => globalStateManager.subscribe(callback, filter),
    applyOptimisticUpdate: (id, patch) => globalStateManager.applyOptimisticUpdate(id, patch),
    resolveOptimisticUpdate: (id, success) => globalStateManager.resolveOptimisticUpdate(id, success),
    
    // Storage methods
    saveState: (state) => localStorageManager.saveState(state),
    loadState: () => localStorageManager.loadState(),
    clearState: () => localStorageManager.clearState()
};

// Initialize syncer when network module is available
document.addEventListener('DOMContentLoaded', function() {
    if (window.SurvivorNetwork) {
        const syncer = new NetworkStateSyncer(globalStateManager, window.SurvivorNetwork);
        window.SurvivorStateManager.syncer = syncer;
    }
    
    // Load saved state
    const savedState = localStorageManager.loadState();
    if (savedState) {
        globalStateManager.updateState(savedState, 'storage');
    }
    
    console.log('📊 State Manager initialized');
    
    // Notify that module is ready
    if (window.onStateManagerModuleReady) {
        window.onStateManagerModuleReady();
    }
    console.log('✅ State Manager module ready');
});

console.log('📊 State Management module loaded');