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
    }

    /**
     * Record the latest server state. Subscribers (if any) get the diff; with
     * none, nothing is diffed or deep-copied — this runs on every push.
     */
    updateState(newState, source = 'server') {
        if (!newState || typeof newState !== 'object') return false;
        const previous = this.state;
        this.state = newState;
        if (this.subscribers.size === 0) return true;

        const diff = this.calculateDiff(previous, newState);
        if (Object.keys(diff).length === 0) return false;
        this.notifySubscribers(diff, source);
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
 * Legacy storage keys. Earlier builds wrote the FULL game state — every
 * player's hand — into localStorage on every update and kept it for a day.
 * Nothing ever read it back usefully (a reload rejoins and gets fresh state
 * from the server), so it is no longer written, and the old copy is purged.
 */
const LEGACY_STATE_KEYS = ['survivor-game-state', 'survivor-metadata'];

function clearLegacyState() {
    try {
        LEGACY_STATE_KEYS.forEach(key => localStorage.removeItem(key));
    } catch (error) { /* private mode */ }
}

// Create global state manager instance
const globalStateManager = new StateManager();

// Export for use in other modules
window.SurvivorStateManager = {
    manager: globalStateManager,

    // Convenience methods
    getState: () => globalStateManager.getState(),
    updateState: (state, source) => globalStateManager.updateState(state, source),
    subscribe: (callback, filter) => globalStateManager.subscribe(callback, filter),
    applyOptimisticUpdate: (id, patch) => globalStateManager.applyOptimisticUpdate(id, patch),
    resolveOptimisticUpdate: (id, success) => globalStateManager.resolveOptimisticUpdate(id, success),

    // One fresh read of the game from the server. There is no polling loop any
    // more: the socket pushes every change, and network.js resyncs when the
    // page returns to the foreground or the device comes back online.
    syncState: () => window.SurvivorNetwork?.resyncNow?.() ?? Promise.resolve(null),

    // Kept for callers that clear "everything this device remembers"
    clearState: () => { globalStateManager.clear(); clearLegacyState(); }
};

document.addEventListener('DOMContentLoaded', function() {
    clearLegacyState();
    console.log('📊 State Manager initialized');

    // Notify that module is ready
    if (window.onStateManagerModuleReady) {
        window.onStateManagerModuleReady();
    }
    console.log('✅ State Manager module ready');
});

console.log('📊 State Management module loaded');
