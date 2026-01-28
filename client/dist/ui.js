/**
 * Survivor Game - UI Management Module
 * Handles all user interface rendering, interactions, and screen management
 */

// UI State
let currentScreen = 'startScreen';
let toastContainer = null;
let modalOverlay = null;
let loadingOverlay = null;
let cardTooltip = null;

// Component cache for performance
const componentCache = new Map();
const animationQueue = [];
let isAnimating = false;

// ─────────────────────────────────────────────────────────────────────────────
// CARD TOOLTIP SYSTEM
// ─────────────────────────────────────────────────────────────────────────────

const CardTooltipManager = {
    tooltip: null,
    hideTimeout: null,
    currentCardType: null,

    init() {
        // Create tooltip container if it doesn't exist
        if (!document.getElementById('cardTooltip')) {
            const tooltip = document.createElement('div');
            tooltip.id = 'cardTooltip';
            tooltip.className = 'card-tooltip';
            tooltip.innerHTML = `
                <div class="card-tooltip-arrow bottom"></div>
                <div class="card-tooltip-header">
                    <span class="card-tooltip-name"></span>
                    <span class="card-tooltip-category"></span>
                </div>
                <div class="card-tooltip-description"></div>
                <div class="card-tooltip-timing">
                    <span class="card-tooltip-timing-icon">⏱️</span>
                    <span class="card-tooltip-timing-text">Playable during:</span>
                </div>
                <div class="card-tooltip-phases"></div>
            `;
            document.body.appendChild(tooltip);
        }
        this.tooltip = document.getElementById('cardTooltip');
    },

    show(cardType, targetElement) {
        if (!this.tooltip) this.init();
        if (this.hideTimeout) {
            clearTimeout(this.hideTimeout);
            this.hideTimeout = null;
        }

        const cardInfo = window.SurvivorGame?.getCardInfo(cardType);
        if (!cardInfo) return;

        this.currentCardType = cardType;

        // Populate tooltip content
        this.tooltip.querySelector('.card-tooltip-name').textContent = cardInfo.name || cardType;
        this.tooltip.querySelector('.card-tooltip-category').textContent = cardInfo.category || 'Card';
        this.tooltip.querySelector('.card-tooltip-description').textContent = cardInfo.description || '';

        // Format playable phases
        const phasesContainer = this.tooltip.querySelector('.card-tooltip-phases');
        const phases = cardInfo.playablePhases || [];
        phasesContainer.innerHTML = phases.map(phase => {
            const phaseName = this.formatPhaseName(phase);
            return `<span class="card-tooltip-phase">${phaseName}</span>`;
        }).join('');

        // Position tooltip
        this.position(targetElement);

        // Show tooltip with animation
        this.tooltip.classList.add('visible');
    },

    hide() {
        if (this.tooltip) {
            this.tooltip.classList.remove('visible');
            this.currentCardType = null;
        }
    },

    hideDelayed(delay = 150) {
        this.hideTimeout = setTimeout(() => this.hide(), delay);
    },

    position(targetElement) {
        if (!this.tooltip || !targetElement) return;

        const rect = targetElement.getBoundingClientRect();
        const tooltipRect = this.tooltip.getBoundingClientRect();
        const arrow = this.tooltip.querySelector('.card-tooltip-arrow');

        // Default: show above the card
        let top = rect.top - tooltipRect.height - 12;
        let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);

        // If would go above viewport, show below instead
        if (top < 10) {
            top = rect.bottom + 12;
            arrow.className = 'card-tooltip-arrow top';
        } else {
            arrow.className = 'card-tooltip-arrow bottom';
        }

        // Keep within horizontal bounds
        if (left < 10) left = 10;
        if (left + tooltipRect.width > window.innerWidth - 10) {
            left = window.innerWidth - tooltipRect.width - 10;
        }

        this.tooltip.style.top = `${top}px`;
        this.tooltip.style.left = `${left}px`;
    },

    formatPhaseName(phase) {
        const phaseNames = {
            'turn_steal': 'Steal',
            'turn_play': 'Play',
            'turn_draw': 'Draw',
            'tribal_announcement': 'Tribal Start',
            'tribal_advantage_play': 'Advantage',
            'tribal_discussion': 'Discussion',
            'tribal_immunity': 'Immunity',
            'tribal_voting': 'Voting',
            'tribal_reveal': 'Reveal',
            'reactive': 'Reactive'
        };
        return phaseNames[phase] || phase.replace(/_/g, ' ');
    }
};

/**
 * Screen Management
 */
function showScreen(screenId) {
    // Hide all screens
    document.querySelectorAll('.screen').forEach(screen => {
        screen.classList.remove('active');
    });
    
    // Show target screen
    const targetScreen = document.getElementById(screenId);
    if (targetScreen) {
        targetScreen.classList.add('active', 'fade-in');
        currentScreen = screenId;
        
        // Update local game state
        if (window.SurvivorGame) {
            window.SurvivorGame.localGameState.currentScreen = screenId;
        }
        
        // Trigger screen-specific setup
        setupScreen(screenId);
        
        console.log(`📱 Navigated to screen: ${screenId}`);
    } else {
        console.error(`❌ Screen not found: ${screenId}`);
    }
}

function setupScreen(screenId) {
    switch (screenId) {
        case 'lobbyScreen':
            setupLobbyScreen();
            break;
        case 'playingScreen':
            setupPlayingScreen();
            break;
        case 'votingScreen':
            setupVotingScreen();
            break;
        case 'resultsScreen':
            setupResultsScreen();
            break;
        case 'immunityScreen':
            setupImmunityScreen();
            break;
        default:
            // No specific setup needed
            break;
    }
}

/**
 * Screen Setup Functions
 */
function setupLobbyScreen() {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState) return;
    
    renderPlayerList(gameState);
    updateGameInfo(gameState);
    setupLeaderControls();
}

function setupPlayingScreen() {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState) return;
    
    renderPlayerHand(gameState);
    renderTurnInfo(gameState);
    updatePhaseIndicator(gameState);
}

function setupVotingScreen() {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState) return;
    
    renderVoteTargets(gameState);
    updateVotingInfo(gameState);
}

function setupResultsScreen() {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState) return;
    
    renderVoteResults(gameState);
}

function setupImmunityScreen() {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState) return;
    
    renderImmunityPlayers(gameState);
}

function setupLeaderControls() {
    const gameState = window.SurvivorGame?.fullGameState;
    const localPlayerId = window.SurvivorGame?.localGameState?.playerId;
    const leaderControls = document.getElementById('leaderControls');
    
    if (!leaderControls || !gameState || !localPlayerId) return;
    
    const player = gameState.players[localPlayerId];
    if (player && player.isCouncilLeader) {
        leaderControls.style.display = 'block';
    } else {
        leaderControls.style.display = 'none';
    }
}

function updateGameInfo(gameState) {
    if (!gameState) return;

    // Update game code (header)
    const gameCodeEl = document.getElementById('gameCode');
    if (gameCodeEl && gameState.id) {
        gameCodeEl.textContent = gameState.id;
    }

    // Update game code (lobby display)
    const lobbyGameCode = document.getElementById('lobbyGameCode');
    if (lobbyGameCode && gameState.id) {
        lobbyGameCode.textContent = gameState.id;
    }

    // Update player count/info
    const playerInfo = document.getElementById('playerInfo');
    if (playerInfo && window.SurvivorGame?.localGameState?.playerId) {
        const player = gameState.players?.[window.SurvivorGame.localGameState.playerId];
        if (player) {
            playerInfo.textContent = player.name;
        }
    }

    // Update phase indicator if visible
    const phaseIndicator = document.getElementById('phaseIndicator');
    if (phaseIndicator && gameState.phase === 'lobby') {
        phaseIndicator.style.display = 'block';
    }
}

function updatePhaseIndicator(gameState) {
    if (!gameState) return;
    
    const phaseIndicator = document.querySelector('.phase-indicator .phase-text');
    if (phaseIndicator && gameState.phase) {
        const phaseNames = {
            'lobby': 'Lobby',
            'playing': 'Playing',
            'tribal_discussion': 'Tribal Discussion',
            'voting': 'Voting',
            'immunity': 'Immunity',
            'results': 'Results'
        };
        phaseIndicator.textContent = phaseNames[gameState.phase] || gameState.phase;
    }
}

function updateVotingInfo(gameState) {
    if (!gameState) return;
    
    const votingInfo = document.getElementById('votingInfo');
    if (votingInfo && gameState.currentVote) {
        const voteCount = Object.keys(gameState.currentVote.votes || {}).length;
        const playerCount = Object.keys(gameState.players || {}).filter(id => !gameState.players[id].isEliminated).length;
        votingInfo.innerHTML = `<p>Votes cast: ${voteCount}/${playerCount}</p>`;
    }
}

function renderTurnInfo(gameState) {
    if (!gameState) return;
    
    const turnInfo = document.getElementById('turnInfo');
    const currentPlayerIndicator = document.getElementById('currentPlayerIndicator');
    const turnPhaseIndicator = document.getElementById('turnPhaseIndicator');
    
    if (turnInfo && gameState.turnOrder && gameState.currentTurnIndex !== undefined) {
        const currentPlayerId = gameState.turnOrder[gameState.currentTurnIndex];
        const currentPlayer = gameState.players[currentPlayerId];
        
        if (currentPlayerIndicator && currentPlayer) {
            currentPlayerIndicator.innerHTML = `<p>Current Player: ${escapeHtml(currentPlayer.name)}</p>`;
        }

        if (turnPhaseIndicator && gameState.phase) {
            turnPhaseIndicator.innerHTML = `<p>Phase: ${escapeHtml(gameState.phase)}</p>`;
        }
    }
}

function renderVoteResults(gameState) {
    if (!gameState) return;

    const voteResults = document.getElementById('voteResults');
    const eliminationResults = document.getElementById('eliminationResults');

    if (voteResults && gameState.currentVote && gameState.currentVote.votes) {
        const votes = gameState.currentVote.votes;
        const voteCounts = {};
        const votersByTarget = {};

        // Count votes and track who voted for whom
        Object.entries(votes).forEach(([voterId, targetId]) => {
            voteCounts[targetId] = (voteCounts[targetId] || 0) + 1;
            if (!votersByTarget[targetId]) votersByTarget[targetId] = [];
            votersByTarget[targetId].push(voterId);
        });

        // Get total votes and max votes for scaling
        const totalVotes = Object.values(voteCounts).reduce((a, b) => a + b, 0);
        const maxVotes = Math.max(...Object.values(voteCounts));

        // Sort by vote count (highest first)
        const sortedResults = Object.entries(voteCounts)
            .sort((a, b) => b[1] - a[1]);

        // Build vote result cards
        const resultsHtml = sortedResults.map(([playerId, count]) => {
            const player = gameState.players[playerId];
            const playerName = escapeHtml(player?.name || 'Unknown');
            const percentage = totalVotes > 0 ? Math.round((count / totalVotes) * 100) : 0;
            const isEliminated = gameState.currentVote?.eliminated?.includes(playerId);
            const voters = votersByTarget[playerId] || [];
            const voterNames = voters.map(vid => {
                const v = gameState.players[vid];
                return escapeHtml(v?.name || 'Unknown');
            }).join(', ');

            return `
                <div class="vote-result-card ${isEliminated ? 'eliminated' : ''}">
                    <div class="vote-result-header">
                        <div class="vote-result-player">
                            <div class="vote-result-avatar" style="background: ${player?.color || '#666'}">
                                ${playerName.charAt(0).toUpperCase()}
                            </div>
                            <span class="vote-result-name">${playerName}</span>
                            ${isEliminated ? '<span class="vote-result-eliminated-badge">🔥 ELIMINATED</span>' : ''}
                        </div>
                        <div class="vote-result-count">
                            <span class="vote-count-number">${count}</span>
                            <span class="vote-count-label">vote${count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                    <div class="vote-result-bar-container">
                        <div class="vote-result-bar ${isEliminated ? 'eliminated' : ''}"
                             style="width: ${percentage}%"></div>
                    </div>
                    <div class="vote-result-voters">
                        <span class="voters-label">Voted by:</span>
                        <span class="voters-names">${voterNames || 'No votes'}</span>
                    </div>
                </div>
            `;
        }).join('');

        voteResults.innerHTML = `
            <div class="vote-results-container">
                <h3 class="vote-results-title">📊 Vote Results</h3>
                <div class="vote-results-grid">${resultsHtml}</div>
            </div>
        `;
    }

    if (eliminationResults && gameState.currentVote && gameState.currentVote.eliminated) {
        const eliminated = gameState.currentVote.eliminated.map(id => {
            const player = gameState.players[id];
            return escapeHtml(player?.name || id);
        });

        if (eliminated.length > 0) {
            eliminationResults.innerHTML = `
                <div class="elimination-announcement">
                    <div class="torch-snuff-icon">🔥</div>
                    <h3>The Tribe Has Spoken</h3>
                    <p class="eliminated-names">${eliminated.join(', ')}</p>
                    <p class="elimination-subtext">Your torch has been snuffed.</p>
                </div>
            `;
        }
    }
}

function renderImmunityPlayers(gameState) {
    if (!gameState) return;

    const immunityPlayers = document.getElementById('immunityPlayers');
    if (!immunityPlayers || !gameState.players) return;

    const players = Object.values(gameState.players).filter(p => !p.isEliminated);
    immunityPlayers.innerHTML = players.map(player => {
        const safeName = escapeHtml(player.name);
        const safeId = escapeHtml(player.id);
        return `
            <div class="immunity-player" data-player-id="${safeId}">
                <span>${safeName}</span>
                <div class="immunity-actions">
                    <button class="btn btn-sm btn-warning immunity-idol-btn" data-player-id="${safeId}">
                        Play Immunity Idol
                    </button>
                    <button class="btn btn-sm btn-danger nullifier-btn" data-player-id="${safeId}">
                        Play Nullifier
                    </button>
                </div>
            </div>
        `;
    }).join('');

    // Bind event handlers instead of inline onclick (security best practice)
    immunityPlayers.querySelectorAll('.immunity-idol-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const playerId = btn.dataset.playerId;
            if (window.playImmunityIdol) window.playImmunityIdol(playerId);
        });
    });
    immunityPlayers.querySelectorAll('.nullifier-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const playerId = btn.dataset.playerId;
            if (window.playIdolNullifier) window.playIdolNullifier(playerId);
        });
    });
}

/**
 * Component Rendering
 */
function renderPlayerList(gameState) {
    const container = document.getElementById('playerList');
    if (!container || !gameState.players) return;
    
    const players = Object.values(gameState.players);
    const html = players.map(player => createPlayerCard(player)).join('');
    
    container.innerHTML = html;
    
    // Add event listeners
    container.querySelectorAll('.player-card').forEach(card => {
        setupPlayerCardEvents(card);
    });
}

function createPlayerCard(player) {
    const isLeader = player.isCouncilLeader;
    const isEliminated = player.isEliminated;
    const cardCount = player.hand ? player.hand.length : 0;
    
    return `
        <div class="player-card ${isLeader ? 'leader' : ''} ${isEliminated ? 'eliminated' : ''}" 
             data-player-id="${player.id}">
            <div class="player-avatar" style="background: ${player.color}">
                ${player.name.charAt(0).toUpperCase()}
            </div>
            <div class="player-info">
                <div class="player-name">${formatPlayerName(player)}</div>
                <div class="player-status">
                    ${isLeader ? '👑 Leader' : ''}
                    ${isEliminated ? '💀 Eliminated' : ''}
                    ${!isEliminated ? `🃏 ${cardCount}` : ''}
                </div>
            </div>
            ${createPlayerActions(player)}
        </div>
    `;
}

function createPlayerActions(player) {
    const currentPlayerId = window.SurvivorGame?.localGameState.playerId;
    const isCurrentPlayer = player.id === currentPlayerId;
    const isLeader = window.SurvivorGame?.localGameState.isLeader;
    
    let actions = '';
    
    if (!isCurrentPlayer && !player.isEliminated) {
        actions += `
            <button class="btn btn-sm btn-secondary steal-btn" 
                    data-target-id="${player.id}">
                Steal
            </button>
        `;
    }
    
    if (isLeader && !player.isCouncilLeader) {
        actions += `
            <button class="btn btn-sm btn-warning leader-btn" 
                    data-target-id="${player.id}">
                Make Leader
            </button>
        `;
    }
    
    return actions ? `<div class="player-actions">${actions}</div>` : '';
}

function renderPlayerHand(gameState) {
    const container = document.getElementById('playerHand');
    if (!container) return;
    
    const playerId = window.SurvivorGame?.localGameState.playerId;
    const player = gameState.players?.[playerId];
    
    if (!player || !player.hand) {
        container.innerHTML = '<p>No cards in hand</p>';
        return;
    }
    
    const currentPhase = window.SurvivorGame?.getCurrentTurnPhase(gameState, playerId);
    const html = player.hand.map((card, index) => 
        createCardElement(card, index, currentPhase)
    ).join('');
    
    container.innerHTML = `<div class="hand-grid">${html}</div>`;
    
    // Setup card interactions
    setupCardInteractions();
}

function createCardElement(card, index, currentPhase) {
    const cardInfo = window.SurvivorGame?.getCardInfo(card.type);
    const isPlayable = window.SurvivorGame?.canPlayCard(card, currentPhase);
    const requiresTarget = cardInfo?.requiresTarget;
    const escapedName = escapeHtml(cardInfo?.name || card.type);
    const escapedDesc = escapeHtml(cardInfo?.description || '');

    return `
        <div class="card-button ${isPlayable ? 'playable' : 'locked'} touch-target"
             data-card-index="${index}"
             data-card-type="${card.type}"
             data-requires-target="${requiresTarget}"
             data-card-name="${escapedName}"
             data-card-category="${escapeHtml(cardInfo?.category || '')}"
             data-card-phases="${escapeHtml(JSON.stringify(cardInfo?.playablePhases || []))}">
            <button class="card-info-btn" data-card-type="${card.type}" aria-label="Card info">?</button>
            <div class="card-name">${escapedName}</div>
            <div class="card-description">${escapedDesc}</div>
            ${requiresTarget ? '<div class="card-target-indicator">🎯</div>' : ''}
        </div>
    `;
}

// HTML escaping utility for XSS prevention
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderVoteTargets(gameState) {
    const container = document.getElementById('voteTargets');
    if (!container) return;
    
    const playerId = window.SurvivorGame?.localGameState.playerId;
    const eligibleTargets = window.SurvivorGame?.getEligibleVoteTargets(gameState, playerId) || [];
    
    const html = eligibleTargets.map(player => createVoteTargetElement(player)).join('');
    container.innerHTML = `<div class="vote-targets">${html}</div>`;
    
    // Setup vote interactions
    setupVoteInteractions();
}

function createVoteTargetElement(player) {
    const safeId = escapeHtml(player.id);
    const safeName = escapeHtml(player.name || '');
    const safeColor = escapeHtml(player.color || '#666');
    const initial = safeName.charAt(0).toUpperCase();

    return `
        <div class="vote-target touch-target" data-player-id="${safeId}">
            <div class="vote-target-avatar" style="background: ${safeColor}">
                ${initial}
            </div>
            <div class="vote-target-name">${escapeHtml(formatPlayerName(player))}</div>
            <div class="vote-count">0 votes</div>
        </div>
    `;
}

/**
 * Event Handlers
 */
function setupCardInteractions() {
    document.querySelectorAll('.card-button').forEach(cardElement => {
        const cardType = cardElement.dataset.cardType;

        // Info button (tooltip trigger)
        const infoBtn = cardElement.querySelector('.card-info-btn');
        if (infoBtn) {
            infoBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // Don't trigger card play
                CardTooltipManager.show(cardType, cardElement);
            });
        }

        // Hover tooltip (desktop)
        cardElement.addEventListener('mouseenter', () => {
            CardTooltipManager.show(cardType, cardElement);
        });
        cardElement.addEventListener('mouseleave', () => {
            CardTooltipManager.hideDelayed();
        });

        // Skip play interactions for locked cards
        if (cardElement.classList.contains('locked')) return;

        cardElement.addEventListener('click', handleCardClick);

        // Touch optimizations
        cardElement.addEventListener('touchstart', handleTouchStart, { passive: true });
        cardElement.addEventListener('touchend', handleTouchEnd, { passive: true });
    });

    // Hide tooltip when clicking elsewhere
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.card-button') && !e.target.closest('.card-tooltip')) {
            CardTooltipManager.hide();
        }
    });
}

function setupVoteInteractions() {
    document.querySelectorAll('.vote-target').forEach(target => {
        target.addEventListener('click', handleVoteTargetClick);
    });
}

function setupPlayerCardEvents(playerCard) {
    // Steal button
    const stealBtn = playerCard.querySelector('.steal-btn');
    if (stealBtn) {
        stealBtn.addEventListener('click', handleStealClick);
    }
    
    // Leader button
    const leaderBtn = playerCard.querySelector('.leader-btn');
    if (leaderBtn) {
        leaderBtn.addEventListener('click', handleLeaderClick);
    }
}

function handleCardClick(event) {
    const cardElement = event.currentTarget;
    const cardIndex = parseInt(cardElement.dataset.cardIndex);
    const cardType = cardElement.dataset.cardType;
    const requiresTarget = cardElement.dataset.requiresTarget === 'true';

    // Haptic feedback on card interaction
    hapticFeedback('medium');

    if (requiresTarget) {
        showTargetSelectionModal(cardIndex, cardType);
    } else {
        playCard(cardIndex);
    }

    // Add visual feedback
    addCardPlayAnimation(cardElement);
}

function handleVoteTargetClick(event) {
    const targetElement = event.currentTarget;
    const playerId = targetElement.dataset.playerId;

    // Haptic feedback on vote
    hapticFeedback('heavy');

    // Toggle selection
    document.querySelectorAll('.vote-target').forEach(el => {
        el.classList.remove('selected');
    });
    targetElement.classList.add('selected');

    // Cast vote
    castVote(playerId);
}

function handleStealClick(event) {
    event.stopPropagation();
    const targetId = event.currentTarget.dataset.targetId;
    const gameId = window.SurvivorGame?.localGameState.gameId;
    const thiefId = window.SurvivorGame?.localGameState.playerId;
    
    if (gameId && thiefId && targetId) {
        window.SurvivorNetwork?.GameAPI.stealCard(gameId, thiefId, targetId);
    }
}

function handleLeaderClick(event) {
    event.stopPropagation();
    const newLeaderId = event.currentTarget.dataset.targetId;
    const gameId = window.SurvivorGame?.localGameState.gameId;
    
    if (gameId && newLeaderId) {
        showConfirm('Make this player the new Tribal Council Leader?', () => {
            window.SurvivorNetwork?.apiCall('/leader/change', { gameId, newLeaderId });
        });
    }
}

function handleTouchStart(event) {
    event.currentTarget.classList.add('touching');
}

function handleTouchEnd(event) {
    event.currentTarget.classList.remove('touching');
}

/**
 * Game Actions
 */
async function playCard(cardIndex) {
    const gameId = window.SurvivorGame?.localGameState.gameId;
    const playerId = window.SurvivorGame?.localGameState.playerId;
    
    if (!gameId || !playerId) {
        showToast('Game state error', 'error');
        return;
    }
    
    try {
        showLoading('Playing card...');
        const result = await window.SurvivorNetwork?.GameAPI.playCard(gameId, playerId, cardIndex);
        
        if (result && result.success) {
            showToast(result.message || 'Card played successfully', 'success');
        }
    } catch (error) {
        showToast(error.message || 'Failed to play card', 'error');
    } finally {
        hideLoading();
    }
}

async function castVote(targetId) {
    const gameId = window.SurvivorGame?.localGameState.gameId;
    const voterId = window.SurvivorGame?.localGameState.playerId;
    
    if (!gameId || !voterId || !targetId) {
        showToast('Vote error', 'error');
        return;
    }
    
    try {
        showLoading('Casting vote...');
        const votesData = { [targetId]: 1 }; // Basic single vote
        const result = await window.SurvivorNetwork?.GameAPI.castVote(gameId, voterId, votesData);
        
        if (result && result.success) {
            showToast('Vote cast successfully', 'success');
        }
    } catch (error) {
        showToast(error.message || 'Failed to cast vote', 'error');
    } finally {
        hideLoading();
    }
}

/**
 * Modal System
 */
// Store modal callbacks safely (avoid eval/new Function vulnerability)
let modalCloseCallback = null;

function showModal(content, options = {}) {
    const {
        title = '',
        showClose = true,
        onClose = null
    } = options;

    if (!modalOverlay) {
        modalOverlay = document.getElementById('modalOverlay') || createModalOverlay();
    }

    const modalContent = modalOverlay.querySelector('.modal-content');
    const safeTitle = title ? escapeHtml(title) : '';

    modalContent.innerHTML = `
        ${showClose ? '<button class="modal-close" aria-label="Close modal">×</button>' : ''}
        ${safeTitle ? `<h2>${safeTitle}</h2>` : ''}
        <div class="modal-body">${content}</div>
    `;

    // Bind close button event (instead of inline onclick)
    const closeBtn = modalContent.querySelector('.modal-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', hideModal);
    }

    modalOverlay.style.display = 'flex';
    modalOverlay.classList.add('fade-in');

    // Store close callback as a function reference (safe, no eval)
    modalCloseCallback = typeof onClose === 'function' ? onClose : null;

    // Focus management
    const firstInput = modalContent.querySelector('input, button, select');
    if (firstInput) {
        firstInput.focus();
    }
}

function hideModal() {
    if (modalOverlay) {
        modalOverlay.style.display = 'none';
        modalOverlay.classList.remove('fade-in');

        // Call onClose callback if set (safely stored function reference)
        if (modalCloseCallback && typeof modalCloseCallback === 'function') {
            try {
                modalCloseCallback();
            } catch (error) {
                console.error('Modal onClose error:', error);
            }
            modalCloseCallback = null;
        }
    }
}

// Store confirm callbacks safely
let confirmCallbacks = null;

function showConfirm(message, onConfirm, onCancel = null) {
    const safeMessage = escapeHtml(message);
    const content = `
        <div class="confirm-dialog">
            <p>${safeMessage}</p>
            <div class="confirm-actions">
                <button class="btn btn-danger confirm-btn" data-action="confirm">Confirm</button>
                <button class="btn btn-secondary confirm-btn" data-action="cancel">Cancel</button>
            </div>
        </div>
    `;

    confirmCallbacks = { onConfirm, onCancel };
    showModal(content, { title: 'Confirm Action' });

    // Bind confirm/cancel buttons safely (no inline onclick)
    setTimeout(() => {
        const confirmBtn = document.querySelector('.confirm-btn[data-action="confirm"]');
        const cancelBtn = document.querySelector('.confirm-btn[data-action="cancel"]');

        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => confirmAction(true));
        }
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => confirmAction(false));
        }
    }, 0);
}

function confirmAction(confirmed) {
    if (confirmCallbacks) {
        if (confirmed && typeof confirmCallbacks.onConfirm === 'function') {
            confirmCallbacks.onConfirm();
        } else if (!confirmed && typeof confirmCallbacks.onCancel === 'function') {
            confirmCallbacks.onCancel();
        }
        confirmCallbacks = null;
    }
    hideModal();
}

function showTargetSelectionModal(cardIndex, cardType) {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState) return;

    const playerId = window.SurvivorGame?.localGameState.playerId;
    const eligibleTargets = Object.values(gameState.players).filter(player =>
        player.id !== playerId && !player.isEliminated
    );

    const content = `
        <div class="target-selection">
            <p>Select a target for your card:</p>
            <div class="target-grid">
                ${eligibleTargets.map(player => {
                    const safeId = escapeHtml(player.id);
                    const safeName = escapeHtml(formatPlayerName(player));
                    return `
                        <button class="btn btn-secondary target-option"
                                data-target-id="${safeId}"
                                data-card-index="${cardIndex}">
                            ${safeName}
                        </button>
                    `;
                }).join('')}
            </div>
        </div>
    `;

    showModal(content, { title: 'Select Target' });

    // Bind target selection events safely (no inline onclick)
    setTimeout(() => {
        document.querySelectorAll('.target-option').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.dataset.targetId;
                const idx = btn.dataset.cardIndex;
                selectTarget(idx, targetId);
            });
        });
    }, 0);
}

function selectTarget(cardIndex, targetId) {
    hideModal();
    // Pass target info to playCard function
    playCard(parseInt(cardIndex), targetId);
}

/**
 * Toast Notifications
 */
function showToast(message, type = 'info', duration = 3000) {
    if (!toastContainer) {
        toastContainer = createToastContainer();
    }
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type} fade-in`;
    toast.innerHTML = `
        <div class="toast-content">
            <span class="toast-icon">${getToastIcon(type)}</span>
            <span class="toast-message">${message}</span>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    // Auto-remove after duration
    setTimeout(() => {
        if (toast.parentNode) {
            toast.classList.add('fade-out');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }
    }, duration);
}

function getToastIcon(type) {
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    return icons[type] || icons.info;
}

/**
 * Loading States - Consolidated Loading Manager
 */
const LoadingManager = {
    overlay: null,
    hideTimeout: null,
    requestCount: 0, // Track nested show/hide calls

    init() {
        // Use the existing HTML loading overlay
        this.overlay = document.getElementById('loading-overlay');
        if (!this.overlay) {
            // Fallback: create one if missing
            this.overlay = this.create();
        }
    },

    create() {
        const overlay = document.createElement('div');
        overlay.id = 'loading-overlay';
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="loading-spinner"></div>
            <div class="loading-text">Loading...</div>
        `;
        overlay.style.display = 'none';
        document.body.appendChild(overlay);
        return overlay;
    },

    show(message = 'Loading...') {
        if (!this.overlay) this.init();
        if (this.hideTimeout) {
            clearTimeout(this.hideTimeout);
            this.hideTimeout = null;
        }

        this.requestCount++;

        const loadingText = this.overlay.querySelector('.loading-text');
        if (loadingText) {
            loadingText.textContent = message;
        }

        this.overlay.style.display = 'flex';
    },

    hide() {
        this.requestCount = Math.max(0, this.requestCount - 1);

        // Only hide if all requests are complete
        if (this.requestCount === 0 && this.overlay) {
            // Small delay to prevent flicker on quick operations
            this.hideTimeout = setTimeout(() => {
                if (this.overlay) {
                    this.overlay.style.display = 'none';
                }
            }, 100);
        }
    },

    forceHide() {
        // Emergency hide - ignores request count
        this.requestCount = 0;
        if (this.hideTimeout) clearTimeout(this.hideTimeout);
        if (this.overlay) {
            this.overlay.style.display = 'none';
        }
    }
};

function showLoading(message = 'Loading...') {
    LoadingManager.show(message);
}

function hideLoading() {
    LoadingManager.hide();
}

/**
 * Animations
 */
function addCardPlayAnimation(cardElement) {
    cardElement.classList.add('playing-animation');
    setTimeout(() => {
        cardElement.classList.remove('playing-animation');
    }, 600);
}

function animateStateChange(element, property, from, to, duration = 300) {
    return new Promise(resolve => {
        const start = performance.now();
        
        function animate(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            
            const current = from + (to - from) * progress;
            element.style[property] = current;
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                resolve();
            }
        }
        
        requestAnimationFrame(animate);
    });
}

/**
 * Utility Functions
 */
function formatPlayerName(player, maxLength = 15) {
    if (!player || !player.name) return 'Unknown';
    
    const name = player.name.trim();
    return name.length > maxLength ? name.substring(0, maxLength - 3) + '...' : name;
}

function createModalOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'modalOverlay';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = '<div class="modal-content"></div>';
    document.body.appendChild(overlay);
    
    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            hideModal();
        }
    });
    
    return overlay;
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 10px;
    `;
    document.body.appendChild(container);
    return container;
}

// createLoadingOverlay is now handled by LoadingManager

/**
 * State Update Handler
 */
function updateFromDiff(diff) {
    console.log('🔄 Updating UI from state diff:', Object.keys(diff));
    
    // Update specific components based on diff
    if (diff.players) {
        renderPlayerList(window.SurvivorGame.fullGameState);
    }
    
    if (diff.phase) {
        updatePhaseIndicator(window.SurvivorGame.fullGameState);
    }
    
    if (diff.currentVote) {
        updateVotingInfo(window.SurvivorGame.fullGameState);
    }
    
    // Additional diff-based updates could be added here
}

/**
 * Phase Guidance System
 * Provides contextual help based on current game phase
 */
const PHASE_GUIDANCE = {
    'lobby': {
        icon: '👥',
        text: 'Waiting for players to join...',
        action: 'Share the game code with friends!'
    },
    'turn_steal': {
        icon: '🎯',
        text: 'Steal Phase',
        action: 'Click a player to steal one of their cards'
    },
    'turn_play': {
        icon: '🃏',
        text: 'Play Phase',
        action: 'Play a card from your hand, or click "Skip" to draw'
    },
    'turn_draw': {
        icon: '📥',
        text: 'Draw Phase',
        action: 'Drawing a card...'
    },
    'playing': {
        icon: '⏳',
        text: 'Game in Progress',
        action: 'Wait for your turn'
    },
    'tribal_announcement': {
        icon: '🔥',
        text: 'Tribal Council!',
        action: 'Someone drew a Tribal Council card. Time to vote someone out!'
    },
    'tribal_advantage_play': {
        icon: '🎭',
        text: 'Advantage Play',
        action: 'Play any Tribal Advantage cards NOW, before voting starts!'
    },
    'tribal_discussion': {
        icon: '💬',
        text: 'Tribal Discussion',
        action: 'Discuss strategy. Council Leader will advance when ready.'
    },
    'tribal_voting': {
        icon: '🗳️',
        text: 'Voting Time',
        action: 'Click on a player to cast your vote'
    },
    'voting': {
        icon: '🗳️',
        text: 'Voting Time',
        action: 'Click on a player to cast your vote'
    },
    'tribal_immunity': {
        icon: '🛡️',
        text: 'Immunity Phase',
        action: 'Play Immunity Idol now or forever hold your peace!'
    },
    'immunity': {
        icon: '🛡️',
        text: 'Immunity Phase',
        action: 'Play Immunity Idol now or forever hold your peace!'
    },
    'tribal_reveal': {
        icon: '📊',
        text: 'Vote Reveal',
        action: 'Revealing the votes...'
    },
    'results': {
        icon: '📊',
        text: 'Results',
        action: 'The votes have been counted.'
    },
    'final_tribal': {
        icon: '🏆',
        text: 'Final Tribal Council',
        action: 'The jury will decide the Sole Survivor!'
    },
    'finished': {
        icon: '🎉',
        text: 'Game Over',
        action: 'Congratulations to the Sole Survivor!'
    }
};

function renderPhaseGuidance(gameState) {
    if (!gameState) return;

    // Find or create guidance container
    let guidanceEl = document.getElementById('phaseGuidance');
    if (!guidanceEl) {
        guidanceEl = document.createElement('div');
        guidanceEl.id = 'phaseGuidance';
        guidanceEl.className = 'phase-guidance';

        // Insert at top of game container
        const gameContainer = document.querySelector('.game-container');
        if (gameContainer) {
            gameContainer.insertBefore(guidanceEl, gameContainer.firstChild);
        }
    }

    const phase = gameState.phase || 'lobby';
    const guidance = PHASE_GUIDANCE[phase] || PHASE_GUIDANCE['playing'];

    // Check if it's the current player's turn
    const localPlayerId = window.SurvivorGame?.localGameState?.playerId;
    const isMyTurn = gameState.currentPlayerId === localPlayerId;

    // Customize action text for current player
    let actionText = guidance.action;
    if (phase.startsWith('turn_') && !isMyTurn) {
        const currentPlayer = gameState.players?.[gameState.currentPlayerId];
        actionText = `Waiting for ${currentPlayer?.name || 'another player'}...`;
    } else if (phase.startsWith('turn_') && isMyTurn) {
        actionText = `YOUR TURN! ${guidance.action}`;
    }

    guidanceEl.innerHTML = `
        <span class="phase-guidance-icon">${guidance.icon}</span>
        <div class="phase-guidance-content">
            <strong class="phase-guidance-text">${guidance.text}</strong>
            <span class="phase-guidance-action">${actionText}</span>
        </div>
    `;

    // Add pulse effect when it's your turn
    if (isMyTurn && phase.startsWith('turn_')) {
        guidanceEl.classList.add('your-turn');
    } else {
        guidanceEl.classList.remove('your-turn');
    }
}

/**
 * Update UI based on current screen and game state
 */
function updateCurrentScreen(gameState) {
    if (!gameState) return;

    // Always render phase guidance
    renderPhaseGuidance(gameState);

    // Update UI based on current screen
    switch (currentScreen) {
        case 'lobbyScreen':
            renderPlayerList(gameState);
            updateGameInfo(gameState);
            setupLeaderControls();
            break;
        case 'playingScreen':
            renderPlayerHand(gameState);
            renderTurnInfo(gameState);
            updatePhaseIndicator(gameState);
            break;
        case 'votingScreen':
            renderVoteTargets(gameState);
            updateVotingInfo(gameState);
            break;
        case 'resultsScreen':
            renderVoteResults(gameState);
            break;
        case 'immunityScreen':
            renderImmunityPlayers(gameState);
            break;
        // Add other screens as needed
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// GAME SHARING SYSTEM
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Copy game code to clipboard
 */
async function copyGameCode() {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    if (!gameId) {
        showToast('No game code to copy', 'warning');
        return;
    }

    try {
        await navigator.clipboard.writeText(gameId);
        showToast('Game code copied!', 'success');
        hapticFeedback('success');
    } catch (error) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = gameId;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showToast('Game code copied!', 'success');
            hapticFeedback('success');
        } catch (e) {
            showToast('Failed to copy code', 'error');
        }
        document.body.removeChild(textArea);
    }
}

/**
 * Share game using native share API or fallback
 */
async function shareGame() {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    if (!gameId) {
        showToast('No game to share', 'warning');
        return;
    }

    const shareUrl = `${window.location.origin}/join/${gameId}`;
    const shareData = {
        title: 'Join my Survivor game!',
        text: `Join my Survivor game with code: ${gameId}`,
        url: shareUrl
    };

    // Try native share API first (mobile)
    if (navigator.share && navigator.canShare && navigator.canShare(shareData)) {
        try {
            await navigator.share(shareData);
            hapticFeedback('success');
            showToast('Shared successfully!', 'success');
            return;
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.log('Native share failed, using fallback');
            }
        }
    }

    // Fallback: copy link to clipboard
    try {
        await navigator.clipboard.writeText(`Join my Survivor game! Code: ${gameId}\n${shareUrl}`);
        showToast('Share link copied to clipboard!', 'success');
        hapticFeedback('success');
    } catch (error) {
        copyGameCode(); // Ultimate fallback
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// HAPTIC FEEDBACK SYSTEM
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Provide haptic feedback for interactions
 * @param {string} type - Type of feedback: 'light', 'medium', 'heavy', 'success', 'error'
 */
function hapticFeedback(type = 'light') {
    if (!('vibrate' in navigator)) return;

    const patterns = {
        light: [10],
        medium: [30],
        heavy: [50],
        success: [10, 50, 10],
        error: [100, 50, 100],
        warning: [50, 30, 50]
    };

    try {
        navigator.vibrate(patterns[type] || patterns.light);
    } catch (error) {
        // Silently fail - vibration not critical
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// NETWORK STATUS INDICATOR
// ─────────────────────────────────────────────────────────────────────────────

const NetworkStatusManager = {
    indicator: null,
    isOnline: true,

    init() {
        // Create indicator if it doesn't exist
        if (!document.getElementById('networkStatus')) {
            const indicator = document.createElement('div');
            indicator.id = 'networkStatus';
            indicator.className = 'network-status status-online';
            indicator.innerHTML = `
                <span class="network-status-dot"></span>
                <span class="network-status-text">Connected</span>
            `;

            // Insert into header
            const header = document.querySelector('.header .game-info');
            if (header) {
                header.appendChild(indicator);
            } else {
                document.body.appendChild(indicator);
            }
        }
        this.indicator = document.getElementById('networkStatus');

        // Listen for online/offline events
        window.addEventListener('online', () => this.setStatus(true));
        window.addEventListener('offline', () => this.setStatus(false));

        // Initial status
        this.setStatus(navigator.onLine);
    },

    setStatus(isOnline, message = null) {
        this.isOnline = isOnline;
        if (!this.indicator) return;

        const dot = this.indicator.querySelector('.network-status-dot');
        const text = this.indicator.querySelector('.network-status-text');

        if (isOnline) {
            this.indicator.className = 'network-status status-online';
            if (text) text.textContent = message || 'Connected';
        } else {
            this.indicator.className = 'network-status status-offline';
            if (text) text.textContent = message || 'Offline';
            hapticFeedback('warning');
        }
    },

    setReconnecting(attempt = 0) {
        if (!this.indicator) return;
        this.indicator.className = 'network-status status-reconnecting';
        const text = this.indicator.querySelector('.network-status-text');
        if (text) text.textContent = attempt > 0 ? `Reconnecting (${attempt})...` : 'Reconnecting...';
    }
};

/**
 * Update network status from external source
 */
function updateNetworkStatus(isOnline, message = null) {
    NetworkStatusManager.setStatus(isOnline, message);
}

/**
 * Show reconnecting state
 */
function showReconnecting(attempt = 0) {
    NetworkStatusManager.setReconnecting(attempt);
}

// ─────────────────────────────────────────────────────────────────────────────
// DEEP LINK HANDLING
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Check URL for game code deep link and pre-fill
 */
function handleDeepLink() {
    const pathMatch = window.location.pathname.match(/^\/join\/([A-Za-z0-9]+)$/i);
    if (pathMatch) {
        const gameCode = pathMatch[1].toUpperCase();
        console.log(`🔗 Deep link detected: ${gameCode}`);

        // Pre-fill the game code input
        setTimeout(() => {
            const gameCodeInput = document.getElementById('gameCodeInput');
            if (gameCodeInput) {
                gameCodeInput.value = gameCode;
                // Show the join form
                const joinForm = document.getElementById('joinForm');
                if (joinForm) {
                    joinForm.style.display = 'block';
                }
                // Focus on name input
                const nameInput = document.getElementById('playerNameInput');
                if (nameInput) {
                    nameInput.focus();
                }
                showToast(`Game code ${gameCode} detected!`, 'info');
            }
        }, 100);

        return true;
    }
    return false;
}

// Export UI interface
window.SurvivorUI = {
    // Screen management
    showScreen,
    currentScreen: () => currentScreen,

    // Components
    renderPlayerList,
    renderPlayerHand,
    renderVoteTargets,

    // Modals and notifications
    showModal,
    hideModal,
    showConfirm,
    showToast,

    // Loading states
    showLoading,
    hideLoading,
    LoadingManager,

    // Game actions
    playCard,
    castVote,

    // State updates
    updateFromDiff,
    updateCurrentScreen,

    // Screen setup
    setupLeaderControls,

    // Sharing
    copyGameCode,
    shareGame,

    // Haptic feedback
    hapticFeedback,

    // Network status
    updateNetworkStatus,
    showReconnecting,
    NetworkStatusManager,

    // Deep links
    handleDeepLink,

    // Utilities
    formatPlayerName
};

// Auto-setup on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    console.log('🎨 UI module initialized');

    // Initialize network status indicator
    NetworkStatusManager.init();

    // Handle deep links (e.g., /join/ABC123)
    handleDeepLink();

    // Setup global click handlers
    document.addEventListener('click', (e) => {
        // Handle any global click events here
    });

    // Setup keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // ESC to close modals
        if (e.key === 'Escape' && modalOverlay && modalOverlay.style.display === 'flex') {
            hideModal();
        }
    });

    // Notify that module is ready
    if (window.onUIModuleReady) {
        window.onUIModuleReady();
    }
    console.log('✅ UI module ready');
});