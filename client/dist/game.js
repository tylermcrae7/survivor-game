/**
 * Survivor Game - Core Game Logic Module
 * Handles game state management, card systems, and core game mechanics
 */

// Game State Management
let localGameState = {
    gameId: null,
    playerId: null,
    playerColor: null,
    isLeader: false,
    currentScreen: 'startScreen'
};

let fullGameState = {};
let appInitialized = false;

// Survivor Card Database - Loaded from JSON
let SURVIVOR_CARDS = {};

// Game Phase Constants
const GAME_PHASES = {
    LOBBY: "lobby",
    PLAYING: "playing", 
    TRIBAL: "tribal_council",
    FINAL: "final"
};

const TURN_PHASES = {
    STEAL: "turn_steal",
    PLAY: "turn_play", 
    DRAW: "turn_draw"
};

const TRIBAL_PHASES = {
    ANNOUNCEMENT: "announcement",
    ADVANTAGE_PLAY: "advantage_play",
    DISCUSSION: "tribal_discussion",
    IMMUNITY: "tribal_immunity",
    VOTING: "tribal_voting",
    REVEAL: "tribal_reveal"
};

/**
 * Load card definitions from server
 * @returns {Promise<boolean>} Success status
 */
async function loadCardDefinitions() {
    try {
        const response = await fetch('/api/cards');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const cardData = await response.json();
        
        // Convert JSON format to JavaScript format for compatibility
        SURVIVOR_CARDS = {};
        for (const [cardType, cardInfo] of Object.entries(cardData.cards)) {
            // Convert snake_case properties to camelCase for JS compatibility
            SURVIVOR_CARDS[cardType.toUpperCase()] = {
                type: cardInfo.type,
                category: cardInfo.category,
                name: cardInfo.name,
                description: cardInfo.description,
                playablePhases: cardInfo.playable_phases,
                requiresTarget: cardInfo.requires_target,
                requiresMultipleTargets: cardInfo.requires_multiple_targets,
                requiresConfirmation: cardInfo.requires_confirmation,
                reactiveOnly: cardInfo.reactive_only,
                count: cardInfo.count
            };
        }
        
        console.log(`Loaded ${Object.keys(SURVIVOR_CARDS).length} card types from server`);
        return true;
    } catch (error) {
        console.error('Failed to load card definitions:', error);
        // Fallback to basic cards
        SURVIVOR_CARDS = {
            VOTE: {
                type: "vote",
                category: "vote",
                description: "Basic vote",
                playablePhases: ["tribal_voting"],
                requiresConfirmation: false,
                count: 6
            }
        };
        return false;
    }
}

/**
 * Card validation helper functions
 */
function getCardInfo(cardType) {
    return Object.values(SURVIVOR_CARDS).find(card => card.type === cardType);
}

function canPlayCard(card, currentPhase) {
    const cardInfo = getCardInfo(card.type);
    return cardInfo && cardInfo.playablePhases.includes(currentPhase);
}

function cardRequiresTarget(cardType) {
    const cardInfo = getCardInfo(cardType);
    return cardInfo ? cardInfo.requiresTarget : false;
}

function cardRequiresConfirmation(cardType) {
    const cardInfo = getCardInfo(cardType);
    return cardInfo ? cardInfo.requiresConfirmation : false;
}

/**
 * Game Phase Logic
 */
function getCurrentTurnPhase(gameState, playerId) {
    if (!gameState || !gameState.players || !playerId) return 'waiting';
    
    const player = gameState.players[playerId];
    if (!player || player.isEliminated) return 'waiting';
    
    const turnOrder = gameState.turnOrder || [];
    const currentPlayerIndex = gameState.currentTurnIndex || 0;
    const currentPlayerId = turnOrder[currentPlayerIndex];
    
    if (currentPlayerId !== playerId) return 'waiting';
    
    // Determine phase based on player state
    if (!player.hasStolen) {
        return TURN_PHASES.STEAL;
    } else {
        return TURN_PHASES.PLAY;
    }
}

function getPlayableCards(hand, currentPhase) {
    if (!hand || !Array.isArray(hand)) return [];
    
    return hand.filter(card => {
        const cardInfo = getCardInfo(card.type);
        if (!cardInfo) return false;
        
        return cardInfo.playablePhases.includes(currentPhase);
    });
}

/**
 * Player Management
 */
function isCurrentPlayer(gameState, playerId) {
    if (!gameState || !gameState.turnOrder || !playerId) return false;
    
    const currentTurnIndex = gameState.currentTurnIndex || 0;
    const currentPlayerId = gameState.turnOrder[currentTurnIndex];
    
    return currentPlayerId === playerId;
}

function getCouncilLeader(gameState) {
    if (!gameState || !gameState.players) return null;
    
    // Check for explicit council leader ID
    if (gameState.currentVote && gameState.currentVote.councilLeaderId) {
        return gameState.players[gameState.currentVote.councilLeaderId];
    }
    
    // Fall back to checking isCouncilLeader flag
    for (const [playerId, player] of Object.entries(gameState.players)) {
        if (player.isCouncilLeader) {
            return player;
        }
    }
    
    return null;
}

function getEligibleVoteTargets(gameState, voterId) {
    if (!gameState || !gameState.players) return [];
    
    return Object.values(gameState.players).filter(player => {
        // Can't vote for eliminated players
        if (player.isEliminated) return false;
        
        // Can't vote for yourself in most cases
        if (player.id === voterId) return false;
        
        // Can't vote for players with immunity protection
        if (player.immunityIdolProtection || player.temporaryImmunity) return false;
        
        return true;
    });
}

/**
 * Turn Management
 */
function getNextPlayer(gameState) {
    if (!gameState || !gameState.turnOrder) return null;
    
    const turnOrder = gameState.turnOrder;
    let nextIndex = (gameState.currentTurnIndex + 1) % turnOrder.length;
    
    // Skip eliminated players
    let attempts = 0;
    while (attempts < turnOrder.length) {
        const nextPlayerId = turnOrder[nextIndex];
        const nextPlayer = gameState.players[nextPlayerId];
        
        if (nextPlayer && !nextPlayer.isEliminated) {
            return nextPlayer;
        }
        
        nextIndex = (nextIndex + 1) % turnOrder.length;
        attempts++;
    }
    
    return null;
}

/**
 * Card Effects (Basic implementations)
 */
function resolveCardEffect(card, gameState, playerId, targetId = null) {
    const cardInfo = getCardInfo(card.type);
    if (!cardInfo) return { success: false, message: "Unknown card type" };
    
    // Basic effect implementations - these would be expanded
    switch (card.type) {
        case 'extra_vote':
            return { success: true, message: "Extra vote granted" };
        case 'sorry_for_you':
            return { success: true, message: "Theft blocked!" };
        case 'immunity_idol':
            return { success: true, message: "Immunity idol played" };
        default:
            return { success: true, message: `${cardInfo.name} played` };
    }
}

/**
 * Tribal Council Logic
 */
function getTribalPhase(gameState) {
    if (!gameState || gameState.phase !== GAME_PHASES.TRIBAL) return null;
    if (!gameState.currentVote) return TRIBAL_PHASES.ANNOUNCEMENT;
    
    return gameState.currentVote.phase || TRIBAL_PHASES.ANNOUNCEMENT;
}

function canAdvanceTribalPhase(gameState, playerId) {
    if (!gameState || !playerId) return false;
    
    const leader = getCouncilLeader(gameState);
    return leader && leader.id === playerId;
}

/**
 * Final Tribal Council Logic
 */
function getFinalTribalPhase(gameState) {
    if (!gameState || gameState.phase !== GAME_PHASES.FINAL) return null;
    if (!gameState.finalTribal) return 'questions';
    
    return gameState.finalTribal.phase || 'questions';
}

function getFinalists(gameState) {
    if (!gameState || !gameState.players) return [];
    
    return Object.values(gameState.players).filter(player => 
        !player.isEliminated && !gameState.jury.includes(player.id)
    );
}

function getJury(gameState) {
    if (!gameState || !gameState.jury || !gameState.players) return [];
    
    return gameState.jury.map(juryId => gameState.players[juryId]).filter(Boolean);
}

/**
 * Game State Validation
 */
function validateGameState(gameState) {
    if (!gameState) return false;
    
    // Basic validation
    if (!gameState.id || !gameState.players || !gameState.phase) {
        return false;
    }
    
    // Validate player structure
    for (const [playerId, player] of Object.entries(gameState.players)) {
        if (!player.id || !player.name) {
            return false;
        }
    }
    
    return true;
}

/**
 * Utility Functions
 */
function shuffleArray(array) {
    const shuffled = [...array];
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
}

function getRandomElement(array) {
    return array[Math.floor(Math.random() * array.length)];
}

function formatPlayerName(player, maxLength = 15) {
    if (!player || !player.name) return 'Unknown';
    
    const name = player.name.trim();
    return name.length > maxLength ? name.substring(0, maxLength - 3) + '...' : name;
}

function formatCardName(card) {
    if (!card) return 'Unknown Card';
    
    const cardInfo = getCardInfo(card.type);
    return cardInfo ? cardInfo.name : card.type;
}

// ─────────────────────────────────────────────────────────────────────────────
// GAME ACTION FUNCTIONS (moved from inline script)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Safe API call with loading states and error handling
 */
async function safeApiCall(endpoint, data = {}, method = 'POST') {
    if (!window.appReady) {
        window.showToast && window.showToast('App is still loading, please wait...', 'warning');
        return null;
    }

    try {
        const showLoading = window.SurvivorUI?.showLoading || window.showLoading;
        const hideLoading = window.SurvivorUI?.hideLoading || window.hideLoading;
        if (showLoading) showLoading('Connecting to server...');

        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };

        if (method !== 'GET') {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(`${window.API_URL}/api${endpoint}`, options);
        if (hideLoading) hideLoading();

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();

        if (result.success === false) {
            throw new Error(result.message || 'Operation failed');
        }

        return result;

    } catch (error) {
        const hideLoading = window.SurvivorUI?.hideLoading || window.hideLoading;
        if (hideLoading) hideLoading();
        console.error('API call failed:', error);
        const showToast = window.SurvivorUI?.showToast || window.showToast;
        if (showToast) showToast(error.message || 'Network error occurred', 'error');
        return null;
    }
}

async function createGame() {
    console.log('Creating new game...');
    const result = await safeApiCall('/game/create');

    if (result && result.gameId) {
        if (window.SurvivorGame) {
            window.SurvivorGame.localGameState.gameId = result.gameId;
            window.SurvivorGame.fullGameState = {
                id: result.gameId,
                players: {},
                phase: 'lobby'
            };
        }

        document.getElementById('gameCode').textContent = result.gameId;
        (window.SurvivorUI?.showToast || window.showToast)('Game created successfully!', 'success');
        showJoinForm();

        const gameCodeInput = document.getElementById('gameCodeInput');
        if (gameCodeInput) {
            gameCodeInput.value = result.gameId;
        }
    }
}

function showJoinForm() {
    const joinForm = document.getElementById('joinForm');
    if (joinForm) {
        const isVisible = joinForm.style.display !== 'none';
        joinForm.style.display = isVisible ? 'none' : 'block';
        if (!isVisible) {
            document.getElementById('gameCodeInput').focus();
        }
    }
}

async function joinGame() {
    const gameId = document.getElementById('gameCodeInput').value.trim();
    const name = document.getElementById('playerNameInput').value.trim();
    const colorBtn = document.querySelector('.color-btn.selected');
    const color = colorBtn ? colorBtn.dataset.color : null;
    const toast = window.SurvivorUI?.showToast || window.showToast;

    if (!gameId) { toast('Please enter a game code', 'warning'); document.getElementById('gameCodeInput').focus(); return; }
    if (!name) { toast('Please enter your name', 'warning'); document.getElementById('playerNameInput').focus(); return; }
    if (!color) { toast('Please select a color', 'warning'); return; }

    console.log('Joining game:', gameId);
    const result = await safeApiCall('/player/join', { gameId, name, color });

    if (result && result.success) {
        if (window.SurvivorGame) {
            window.SurvivorGame.localGameState.gameId = gameId;
            window.SurvivorGame.localGameState.playerId = result.playerId;
            window.SurvivorGame.fullGameState = result.gameState || {};
        }

        if (window.SurvivorNetwork && window.SurvivorNetwork.socketManager) {
            window.SurvivorNetwork.socketManager.connect(gameId);
        }

        document.getElementById('gameCode').textContent = gameId;
        document.getElementById('playerInfo').textContent = name;

        localStorage.setItem('survivorState', JSON.stringify({
            gameId: gameId,
            playerId: result.playerId,
            playerName: name
        }));

        toast('Joined game successfully!', 'success');
        const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
        showScreen('lobbyScreen');

        const lobbyGameCode = document.getElementById('lobbyGameCode');
        if (lobbyGameCode) lobbyGameCode.textContent = gameId;

        if (result.gameState) {
            window.updateGameState && window.updateGameState(result.gameState);
        }
    }
}

async function startFullGame() {
    if (!localGameState.gameId) {
        (window.SurvivorUI?.showToast || window.showToast)('No active game found', 'error');
        return;
    }
    console.log('Starting full game...');
    const result = await safeApiCall('/game/start_full', { gameId: localGameState.gameId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Game started successfully!', 'success');
        const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
        showScreen('playingScreen');
    }
}

async function resetGame() {
    if (!localGameState.gameId) {
        (window.SurvivorUI?.showToast || window.showToast)('No active game found', 'error');
        return;
    }
    if (!confirm('Are you sure you want to reset the game? This cannot be undone.')) return;

    console.log('Resetting game...');
    const result = await safeApiCall('/game/reset', { gameId: localGameState.gameId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Game reset successfully!', 'success');
        const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
        showScreen('lobbyScreen');
    }
}

async function drawCard() {
    const gameId = localGameState.gameId;
    const playerId = localGameState.playerId;
    if (!gameId || !playerId) {
        (window.SurvivorUI?.showToast || window.showToast)('Game state error', 'error');
        return;
    }
    console.log('Drawing card...');
    const result = await safeApiCall('/turn/draw', { gameId, playerId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Card drawn successfully!', 'success');
    }
}

async function advanceTurn() {
    if (!localGameState.gameId) {
        (window.SurvivorUI?.showToast || window.showToast)('No active game found', 'error');
        return;
    }
    console.log('Advancing turn...');
    const result = await safeApiCall('/turn/advance', { gameId: localGameState.gameId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Turn advanced!', 'success');
    }
}

async function revealVotes() {
    if (!localGameState.gameId) {
        (window.SurvivorUI?.showToast || window.showToast)('No active game found', 'error');
        return;
    }
    console.log('Revealing votes...');
    const result = await safeApiCall('/vote/reveal', { gameId: localGameState.gameId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Votes revealed!', 'success');
        const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
        showScreen('resultsScreen');
    }
}

function proceedToVoting() {
    const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
    showScreen('votingScreen');
}

async function completeTribal() {
    if (!localGameState.gameId) {
        (window.SurvivorUI?.showToast || window.showToast)('No active game found', 'error');
        return;
    }
    console.log('Completing tribal council...');
    const result = await safeApiCall('/tribal/complete', { gameId: localGameState.gameId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Tribal council completed!', 'success');
        const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
        showScreen('playingScreen');
    }
}

async function resetTribal() {
    if (!localGameState.gameId) {
        (window.SurvivorUI?.showToast || window.showToast)('No active game found', 'error');
        return;
    }
    if (!confirm('Are you sure you want to reset the tribal council?')) return;

    console.log('Resetting tribal council...');
    const result = await safeApiCall('/tribal/reset', { gameId: localGameState.gameId });
    if (result && result.success) {
        (window.SurvivorUI?.showToast || window.showToast)('Tribal council reset!', 'success');
        const showScreen = window.SurvivorUI?.showScreen || window.showScreen;
        showScreen('playingScreen');
    }
}

function recordWinner() {
    (window.SurvivorUI?.showToast || window.showToast)('Winner recording feature coming soon!', 'info');
}

function startNewGame() {
    if (confirm('Start a new game? Current game will be lost.')) {
        localStorage.removeItem('survivorState');
        location.reload();
    }
}

// Export functions for use in other modules
window.SurvivorGame = {
    // State
    localGameState,
    fullGameState,
    SURVIVOR_CARDS,
    GAME_PHASES,
    TURN_PHASES,
    TRIBAL_PHASES,
    
    // Card System
    loadCardDefinitions,
    getCardInfo,
    canPlayCard,
    cardRequiresTarget,
    cardRequiresConfirmation,
    getPlayableCards,
    resolveCardEffect,
    
    // Game Logic
    getCurrentTurnPhase,
    isCurrentPlayer,
    getCouncilLeader,
    getEligibleVoteTargets,
    getNextPlayer,
    
    // Tribal Council
    getTribalPhase,
    canAdvanceTribalPhase,
    
    // Final Tribal
    getFinalTribalPhase,
    getFinalists,
    getJury,
    
    // Game Actions
    safeApiCall,
    createGame,
    showJoinForm,
    joinGame,
    startFullGame,
    resetGame,
    drawCard,
    advanceTurn,
    revealVotes,
    proceedToVoting,
    completeTribal,
    resetTribal,
    recordWinner,
    startNewGame,

    // Utilities
    validateGameState,
    shuffleArray,
    getRandomElement,
    formatPlayerName,
    formatCardName
};

// Initialize card definitions when module loads
document.addEventListener('DOMContentLoaded', function() {
    loadCardDefinitions().then(success => {
        if (success) {
            console.log('✅ Card definitions loaded successfully');
        } else {
            console.warn('⚠️ Using fallback card definitions');
        }
        
        // Notify that module is ready
        if (window.onGameModuleReady) {
            window.onGameModuleReady();
        }
        console.log('✅ Game module ready');
    });
});