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