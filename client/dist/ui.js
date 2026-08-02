/**
 * Survivor Game - UI Management Module
 * Handles all user interface rendering, interactions, and screen management
 * Enhanced 2026: Haptic feedback, micro-interactions, tropical theme
 */

// UI State
let currentScreen = 'startScreen';
let toastContainer = null;
let modalOverlay = null;
let loadingOverlay = null;
let cardTooltip = null;

// Animation state
let isAnimating = false;

// ─────────────────────────────────────────────────────────────────────────────
// ICON SYSTEM — inline SVG sprite (see index-optimized.html). No emoji chrome.
// ─────────────────────────────────────────────────────────────────────────────

function icon(name, cls = '') {
    return `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// HAPTIC FEEDBACK SYSTEM (2026 Enhancement)
// ─────────────────────────────────────────────────────────────────────────────

const Haptics = {
    patterns: {
        light: 10,
        medium: 25,
        heavy: 50,
        success: [10, 50, 10],
        error: [50, 30, 50],
        warning: [30, 20, 30],
        select: 15,
        vote: [20, 40, 20, 40, 80]
    },

    /**
     * Trigger haptic feedback if supported
     * @param {string} type - Type of haptic pattern
     */
    trigger(type = 'light') {
        if (window.SurvivorSettings && !window.SurvivorSettings.hapticsOn()) return;
        if ('vibrate' in navigator) {
            const pattern = this.patterns[type] || this.patterns.light;
            navigator.vibrate(pattern);
        }
    },

    /**
     * Check if haptics are supported
     */
    isSupported() {
        return 'vibrate' in navigator;
    }
};

// Add haptic feedback to all button clicks
document.addEventListener('click', (e) => {
    if (e.target.matches('.btn, .card-button, .vote-option, .player-card')) {
        Haptics.trigger('select');
    }
}, { passive: true });

// ─────────────────────────────────────────────────────────────────────────────
// CARD TOOLTIP SYSTEM
// ─────────────────────────────────────────────────────────────────────────────

const CardTooltipManager = {
    tooltip: null,
    hideTimeout: null,
    currentCardType: null,

    init() {
        this.tooltip = document.getElementById('cardTooltip');
        // Fallback: create tooltip if not in HTML (shouldn't happen)
        if (!this.tooltip) {
            const tooltip = document.createElement('div');
            tooltip.id = 'cardTooltip';
            tooltip.className = 'card-tooltip';
            tooltip.setAttribute('popover', '');
            tooltip.innerHTML = `
                <div class="card-tooltip-arrow bottom"></div>
                <div class="card-tooltip-header">
                    <span class="card-tooltip-name"></span>
                    <span class="card-tooltip-category"></span>
                </div>
                <div class="card-tooltip-description"></div>
                <div class="card-tooltip-timing">
                    <span class="card-tooltip-timing-icon"></span>
                    <span class="card-tooltip-timing-text">Playable during:</span>
                </div>
                <div class="card-tooltip-phases"></div>
            `;
            document.body.appendChild(tooltip);
            this.tooltip = tooltip;
        }
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
        this.tooltip.querySelector('.card-tooltip-category').textContent =
            (cardInfo.category || 'Card').replace(/_/g, ' ');
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

        // Show via Popover API (with fallback)
        if (this.tooltip.showPopover) {
            try { this.tooltip.showPopover(); } catch(e) { /* already open */ }
        } else {
            this.tooltip.classList.add('visible');
        }
    },

    hide() {
        if (this.tooltip) {
            if (this.tooltip.hidePopover) {
                try { this.tooltip.hidePopover(); } catch(e) { /* already closed */ }
            } else {
                this.tooltip.classList.remove('visible');
            }
            this.currentCardType = null;
        }
    },

    hideDelayed(delay = 150) {
        this.hideTimeout = setTimeout(() => this.hide(), delay);
    },

    position(targetElement) {
        if (!this.tooltip || !targetElement) return;

        const rect = targetElement.getBoundingClientRect();
        const arrow = this.tooltip.querySelector('.card-tooltip-arrow');

        // Temporarily make visible to measure (popover may not have dimensions yet)
        const wasHidden = !this.tooltip.matches(':popover-open') && !this.tooltip.classList.contains('visible');
        if (wasHidden) {
            this.tooltip.style.visibility = 'hidden';
            this.tooltip.style.opacity = '0';
        }

        const tooltipRect = this.tooltip.getBoundingClientRect();

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

        if (wasHidden) {
            this.tooltip.style.visibility = '';
            this.tooltip.style.opacity = '';
        }
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
    function applyScreenChange() {
        // A tooltip anchored to the old screen must not haunt the new one
        CardTooltipManager.hide();

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

            // Hold the screen awake while the table is mid-game (device setting)
            window.SurvivorSettings?.setWakeWanted([
                'playingScreen', 'tribalAnnouncementScreen', 'tribalAdvantageScreen',
                'tribalDiscussionScreen', 'votingScreen', 'immunityScreen',
                'resultsScreen', 'finalTribalScreen'
            ].includes(screenId));

            // Announce screen change for accessibility
            announce && announce(`Navigated to ${screenId.replace('Screen', ' screen')}`);

            console.log(`Navigated to screen: ${screenId}`);
        } else {
            console.error(`Screen not found: ${screenId}`);
        }
    }

    // Use View Transitions API if available (progressive enhancement).
    // Rapid successive navigations (routing + socket updates landing together)
    // would interrupt each other and spam "Transition was skipped" — only start
    // a transition when none is in flight.
    if (document.startViewTransition && !showScreen._transitioning) {
        showScreen._transitioning = true;
        const transition = document.startViewTransition(() => applyScreenChange());
        transition.finished.finally(() => { showScreen._transitioning = false; });
    } else {
        applyScreenChange();
    }
}

function setupScreen(screenId) {
    // Render-on-show: a freshly shown screen must paint from the current state
    // immediately, not wait for the next socket update to arrive.
    const gameState = window.SurvivorGame?.fullGameState;
    if (gameState && Object.keys(gameState).length) {
        updateCurrentScreen(gameState);
    }
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
        const chip = document.getElementById('gameChip');
        if (chip) chip.hidden = false;
        const storyBtn = document.getElementById('storyBtn');
        if (storyBtn) storyBtn.hidden = false;
    }

    // Keep an open story drawer fed with the latest events
    if (document.getElementById('storyDrawer')?.classList.contains('open')) {
        renderStoryList(gameState);
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
            const chip = document.getElementById('playerChip');
            if (chip) chip.hidden = false;
        }
    }

    // (The legacy fixed phase indicator stays hidden — the phase guidance strip
    //  and ceremony modes carry that information now.)
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
    if (!votingInfo || !gameState.currentVote) return;

    const voteCount = Object.keys(gameState.currentVote.votes || {}).length;
    const playerCount = Object.keys(gameState.players || {}).filter(id => !gameState.players[id].isEliminated).length;

    // My parchment: how many votes I must place in the box
    const me = gameState.players?.[window.SurvivorGame?.localGameState?.playerId];
    let chips = '';
    if (me && !me.isEliminated) {
        const mandatory = me.mandatoryVotes ?? 1;
        const extra = me.extraVotes ?? 0;
        const voted = me.hasVoted;
        const chipEls = [];
        for (let i = 0; i < mandatory; i++) {
            chipEls.push(`<span class="vote-chip ${voted ? 'spent' : ''}">${icon('ballot')} Vote</span>`);
        }
        for (let i = 0; i < extra; i++) {
            chipEls.push(`<span class="vote-chip ${voted ? 'spent' : ''}">${icon('ballot')} Extra</span>`);
        }
        if (!chipEls.length) chipEls.push(`<span class="vote-chip spent">No Vote Card</span>`);
        chips = `<div class="my-votes"><span>Your parchment</span>${chipEls.join('')}</div>`;
        if (!mandatory && !extra && !voted) {
            // "Pass the box to the player on your left (even if they don't
            // have a Vote Card)" — the tally waits until it has reached everyone
            chips += `<button class="btn btn-secondary btn-enhanced touch-target pass-box-btn"
                        data-action="passVotingBox">Pass the Voting Box</button>`;
        }
    }

    votingInfo.innerHTML = `
        ${chips}
        <p class="panel-sub" style="text-align:center; margin-bottom: 0.9rem;">
            ${voteCount} of ${playerCount} players have voted
        </p>
    `;
    votingInfo.querySelector('[data-action="passVotingBox"]')
        ?.addEventListener('click', () => window.SurvivorGame?.passVotingBox());
}

function renderTurnInfo(gameState) {
    if (!gameState) return;

    const currentPlayerIndicator = document.getElementById('currentPlayerIndicator');
    const turnPhaseIndicator = document.getElementById('turnPhaseIndicator');
    if (!currentPlayerIndicator || !gameState.turnOrder || gameState.currentTurnIndex === undefined) return;

    const currentPlayerId = gameState.turnOrder[gameState.currentTurnIndex];
    const currentPlayer = gameState.players[currentPlayerId];
    if (!currentPlayer) return;

    const myId = window.SurvivorGame?.localGameState?.playerId;
    const isMine = currentPlayerId === myId;

    currentPlayerIndicator.innerHTML = `
        <div class="turn-who ${isMine ? 'mine' : ''}">
            ${isMine ? 'Your torch burns' : escapeHtml(currentPlayer.name) + '’s turn'}
        </div>
    `;
    announce(`It is ${currentPlayer.name}'s turn`);

    // STEAL → PLAY → DRAW tracker for the player whose turn it is.
    // One steal, at most one play, one draw — the draw ends the turn.
    if (turnPhaseIndicator) {
        const stolen = !!currentPlayer.hasStolen;
        const played = !!currentPlayer.hasPlayed;
        const drawn = !!currentPlayer.hasDrawn;
        const step = (label, state) => `<span class="step ${state}">${label}</span>`;
        const playState = !stolen ? '' : (played || drawn) ? 'done' : 'now';
        turnPhaseIndicator.innerHTML = `
            <div class="turn-steps" aria-label="Turn order: steal, then play, then draw">
                ${step('Steal', stolen ? 'done' : 'now')}
                <span class="sep">→</span>
                ${step('Play', playState)}
                <span class="sep">→</span>
                ${step('Draw', drawn ? 'done' : (played ? 'now' : ''))}
            </div>
        `;
    }
}

function renderVoteResults(gameState) {
    if (!gameState) return;

    const voteResults = document.getElementById('voteResults');
    const eliminationResults = document.getElementById('eliminationResults');
    let resultCount = 0;

    if (voteResults && gameState.currentVote) {
        const currentVote = gameState.currentVote;

        // Prefer the server's tally (post-immunity); fall back to summing the
        // raw ballots, which are shaped voterId -> { targetId: count }.
        let voteCounts = currentVote.voteResults;
        if (!voteCounts || !Object.keys(voteCounts).length) {
            voteCounts = {};
            Object.values(currentVote.votes || {}).forEach(ballot => {
                Object.entries(ballot || {}).forEach(([targetId, count]) => {
                    voteCounts[targetId] = (voteCounts[targetId] || 0) + (count || 0);
                });
            });
        }

        // Who voted for whom (for the "voted by" line)
        const votersByTarget = {};
        Object.entries(currentVote.votes || {}).forEach(([voterId, ballot]) => {
            Object.keys(ballot || {}).forEach(targetId => {
                (votersByTarget[targetId] = votersByTarget[targetId] || []).push(voterId);
            });
        });

        const totalVotes = Object.values(voteCounts).reduce((a, b) => a + b, 0);
        const sortedResults = Object.entries(voteCounts).sort((a, b) => b[1] - a[1]);
        resultCount = sortedResults.length;

        // Ballots flip in one at a time — the reveal is a ceremony
        const resultsHtml = sortedResults.map(([playerId, count], i) => {
            const player = gameState.players[playerId];
            const playerName = escapeHtml(player?.name || 'Unknown');
            const percentage = totalVotes > 0 ? Math.round((count / totalVotes) * 100) : 0;
            const isEliminated = currentVote.eliminated?.includes(playerId);
            const voterNames = (votersByTarget[playerId] || []).map(vid =>
                escapeHtml(gameState.players[vid]?.name || 'Unknown')).join(', ');

            return `
                <div class="vote-result-card ${isEliminated ? 'eliminated' : ''}"
                     style="animation-delay: ${i * 320}ms">
                    <div class="vote-result-header">
                        <div class="vote-result-player">
                            <div class="vote-result-avatar" style="background: ${escapeHtml(player?.color || '#666')}">
                                ${playerName.charAt(0).toUpperCase()}
                            </div>
                            <span class="vote-result-name">${playerName}</span>
                            ${isEliminated ? `<span class="vote-result-eliminated-badge">${icon('torch-out')} VOTED OUT</span>` : ''}
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
                        <span class="voters-label">Voted by</span>
                        <span class="voters-names">${voterNames || 'no one'}</span>
                    </div>
                </div>
            `;
        }).join('');

        // A tie the Council Leader still has to break
        let tieNote = '';
        if (currentVote.tieBreakNeeded) {
            const tiedIds = (currentVote.tiedPlayers || []).filter(pid => gameState.players[pid]);
            const tied = tiedIds.map(pid =>
                escapeHtml(gameState.players[pid]?.name || pid)).join(', ');
            const myId = window.SurvivorGame?.localGameState?.playerId;
            const leaderId = currentVote.councilLeaderId;
            const iAmLeader = myId && myId === leaderId;
            const picksLeft = Math.max(1,
                (currentVote.eliminationsNeeded || 1) - (currentVote.eliminated || []).length);

            if (iAmLeader) {
                const pickBtns = tiedIds.map(pid => `
                    <button class="btn btn-danger btn-enhanced touch-target tiebreak-pick-btn"
                            data-picked-id="${escapeHtml(pid)}"
                            style="margin: 0.25rem;">
                        ${icon('torch-out')} ${escapeHtml(gameState.players[pid]?.name || pid)}
                    </button>`).join('');
                tieNote = `
                    <div style="text-align:center; margin-top: 0.8rem;">
                        <p class="panel-sub">${icon('alert')} Deadlocked — as Council Leader, YOU break the tie.
                        Choose ${picksLeft === 1 ? 'the player' : `${picksLeft} players`} whose torch goes out:</p>
                        <div class="tiebreak-picks">${pickBtns}</div>
                    </div>`;
            } else {
                const leaderName = escapeHtml(gameState.players[leaderId]?.name || 'the Council Leader');
                tieNote = `
                    <p class="panel-sub" style="text-align:center; margin-top: 0.8rem;">
                        ${icon('alert')} Deadlocked — <strong>${leaderName}</strong> must choose between: <strong>${tied}</strong>
                    </p>`;
            }
        }

        voteResults.innerHTML = `
            <div class="vote-results-container">
                <div class="vote-results-grid">${resultsHtml || '<p class="panel-sub" style="text-align:center">No votes were cast.</p>'}</div>
                ${tieNote}
            </div>
        `;

        // Leader's tie-break picks go straight to the official cascade endpoint
        voteResults.querySelectorAll('.tiebreak-pick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const chosenId = btn.dataset.pickedId;
                const gameId = window.SurvivorGame?.localGameState?.gameId;
                const leaderId = window.SurvivorGame?.localGameState?.playerId;
                const name = gameState.players[chosenId]?.name || 'this player';
                showConfirm(`Snuff ${name}'s torch? The Council Leader's word is final.`, async () => {
                    try {
                        showLoading('Breaking the tie…');
                        const result = await window.SurvivorNetwork?.apiCall('/vote/tiebreak',
                            { gameId, leaderId, chosenId });
                        // apiCall toasts the success message itself; only the refusal needs saying
                        if (!result?.success && result?.message) showToast(result.message, 'error');
                    } catch (error) {
                        showToast(error.message || 'Tie-break failed', 'error');
                    } finally {
                        hideLoading();
                    }
                });
            });
        });
    }

    if (eliminationResults && gameState.currentVote && gameState.currentVote.eliminated) {
        const eliminated = gameState.currentVote.eliminated.map(id => {
            const player = gameState.players[id];
            return escapeHtml(player?.name || id);
        });

        if (eliminated.length > 0) {
            // The announcement waits for the last ballot to flip
            const delay = 500 + resultCount * 320;
            eliminationResults.innerHTML = `
                <div class="elimination-announcement" style="--announce-delay: ${delay}ms; animation-delay: ${delay}ms;">
                    <div class="torch-snuff-icon" style="animation-delay: ${delay + 250}ms;">
                        <svg><use href="#i-torch-out"></use></svg>
                    </div>
                    <h3>The Tribe Has Spoken</h3>
                    <p class="eliminated-names">${eliminated.join(', ')}</p>
                    <p class="elimination-subtext">The torch is turned. Bring your Vote Card back to camp.</p>
                </div>
            `;
            announce(`Eliminated: ${eliminated.join(', ')}. The tribe has spoken.`);
        } else {
            eliminationResults.innerHTML = '';
        }
    }
}

function renderImmunityPlayers(gameState) {
    if (!gameState) return;

    const immunityPlayers = document.getElementById('immunityPlayers');
    if (!immunityPlayers || !gameState.players) return;

    const me = window.SurvivorGame?.localGameState?.playerId;
    const myself = gameState.players[me] || {};
    const myHand = myself.hand || [];
    const iHoldIdol = myHand.some(c => c.type === 'immunity_idol');
    const iHoldNullifier = myHand.some(c => c.type === 'idol_nullifier');

    const players = Object.values(gameState.players).filter(p => !p.isEliminated);
    immunityPlayers.innerHTML = players.map(player => {
        const safeName = escapeHtml(player.name);
        const safeId = escapeHtml(player.id);
        const isMe = player.id === me;
        const shielded = !!player.immunityIdolProtection;
        const actions = [];
        // Your idol protects you (or an ally — tap their row while holding it)
        if (iHoldIdol && !myself.immunityPlayed && !shielded) {
            actions.push(`<button class="btn btn-sm btn-warning immunity-idol-btn"
                                  data-player-id="${safeId}">
                              ${icon('idol')} ${isMe ? 'Play Idol' : 'Shield them'}
                          </button>`);
        }
        // A nullifier answers an idol that has been played on this player
        if (iHoldNullifier && shielded) {
            actions.push(`<button class="btn btn-sm btn-danger nullifier-btn"
                                  data-player-id="${safeId}">
                              ${icon('x')} Nullify
                          </button>`);
        }
        return `
            <div class="immunity-player" data-player-id="${safeId}">
                <span>${safeName}${isMe ? ' (you)' : ''}${shielded
                    ? ` <span class="panel-sub">· protected</span>` : ''}</span>
                <div class="immunity-actions">${actions.join('')}</div>
            </div>
        `;
    }).join('');

    if (!iHoldIdol && !iHoldNullifier) {
        immunityPlayers.innerHTML += `
            <p class="panel-sub" style="text-align:center; margin-top:0.5rem">
                Nothing in your hand plays in this window.
            </p>`;
    }

    immunityPlayers.querySelectorAll('.immunity-idol-btn').forEach(btn => {
        btn.addEventListener('click', () =>
            window.playImmunityIdol(btn.dataset.playerId));
    });
    immunityPlayers.querySelectorAll('.nullifier-btn').forEach(btn => {
        btn.addEventListener('click', () =>
            window.playIdolNullifier(btn.dataset.playerId));
    });
}

/**
 * The idol/nullifier plays. These were referenced by the immunity screen's
 * buttons but never defined — every tap was a silent no-op, which is exactly
 * "couldn't play my hidden immunity idol" from the playtest.
 */
window.playImmunityIdol = async function (targetId) {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const playerId = window.SurvivorGame?.localGameState?.playerId;
    if (!gameId || !playerId) return;
    try {
        const result = await window.SurvivorNetwork?.apiCall('/immunity/play',
            { gameId, playerId, targetId });
        if (result?.success) {
            Haptics.trigger('success');
        } else if (result?.message) {
            showToast(result.message, 'error');
        }
    } catch (error) {
        showToast(error.message || 'The idol slipped', 'error');
    }
};

window.playIdolNullifier = async function (targetId) {
    const me = window.SurvivorGame?.localGameState?.playerId;
    const hand = window.SurvivorGame?.fullGameState?.players?.[me]?.hand || [];
    if (!hand.some(c => c.type === 'idol_nullifier')) {
        showToast("You don't hold an Idol Nullifier", 'warning');
        return;
    }
    // /immunity/block, not playCard. The generic play path reaches the effect
    // without the check that the target actually holds protection, so this
    // used to let you burn the nullifier on somebody holding nothing — and
    // stamp them `idolNullified`, which then refused a later, real one.
    await window.SurvivorNetwork.blockImmunity(
        window.SurvivorGame.localGameState.gameId, targetId);
};

/**
 * Component Rendering
 */
function renderPlayerList(gameState) {
    const container = document.getElementById('playerList');
    if (!container || !gameState.players) return;
    
    const players = Object.values(gameState.players);
    const html = players.map(player => createPlayerCard(player, gameState)).join('');
    
    container.innerHTML = html;
    
    // Add event listeners
    container.querySelectorAll('.player-card').forEach(card => {
        setupPlayerCardEvents(card);
    });
    container.querySelector('[data-action="renameSelf"]')
        ?.addEventListener('click', (e) => { e.stopPropagation(); showRenameForm(); });
    container.querySelectorAll('[data-action="removeBot"]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            window.SurvivorGame?.removeBot(btn.dataset.playerId);
        });
    });
}

/** Lobby-only: change your own name before the game starts. */
function showRenameForm() {
    const current = window.SurvivorGame?.fullGameState?.players?.[
        window.SurvivorGame?.localGameState?.playerId]?.name || '';
    showModal(`
        <div class="form-group">
            <label for="renameInput">Your name</label>
            <input type="text" id="renameInput" class="form-input" maxlength="30"
                   value="${escapeHtml(current)}" placeholder="What does the tribe call you?">
        </div>
        <p class="picker-hint">You can change this until the game starts.</p>
        <button class="btn btn-primary btn-enhanced touch-target" id="renameSaveBtn">Save</button>
    `, { title: 'Change your name' });

    setTimeout(() => {
        const input = document.getElementById('renameInput');
        input?.focus();
        input?.select();
        document.getElementById('renameSaveBtn')?.addEventListener('click', async () => {
            const newName = input?.value.trim();
            if (!newName) { showToast('A name is required', 'warning'); return; }
            if (newName === current) { hideModal(); return; }
            try {
                const result = await window.SurvivorNetwork.apiCall('/player/rename', {
                    gameId: window.SurvivorGame.localGameState.gameId,
                    playerId: window.SurvivorGame.localGameState.playerId,
                    newName
                });
                if (result?.success) {
                    hideModal();
                    // Header chip + saved session follow the new name
                    const info = document.getElementById('playerInfo');
                    if (info) info.textContent = result.newName || newName;
                    try {
                        const saved = JSON.parse(localStorage.getItem('survivorState') || '{}');
                        saved.playerName = result.newName || newName;
                        localStorage.setItem('survivorState', JSON.stringify(saved));
                    } catch (e) { /* cosmetic only */ }
                }
            } catch (error) {
                // apiCall already toasts the server's reason
            }
        });
    }, 60);
}

/**
 * Render a player's remaining Survivor Character Cards as drawn torches.
 * 2 = two lit torches; 1 = one lit, one smoking; 0 = a skull.
 */
function renderLives(player) {
    const total = 2;
    const left = Math.max(0, Math.min(total, player.characterCards ?? total));
    if (left === 0) {
        return `<span class="lives lives-out" title="Both Survivor Character Cards turned over"
                      aria-label="Eliminated">${icon('skull')}</span>`;
    }
    const lit = icon('torch', 'torch-lit').repeat(left);
    const spent = icon('torch-out', 'torch-spent').repeat(total - left);
    const label = `${left} of ${total} Survivor Character Cards left`;
    return `<span class="lives" title="${label}" aria-label="${label}">${lit}${spent}</span>`;
}

function createPlayerCard(player, gameState) {
    const isLeader = player.isCouncilLeader;
    const isEliminated = player.isEliminated;
    const cardCount = player.hand ? player.hand.length : 0;
    const hasNecklace = gameState && gameState.necklaceHolder === player.id;
    // In the lobby you can still change what the tribe calls you
    const canRename = gameState?.phase === 'lobby' &&
                      player.id === window.SurvivorGame?.localGameState?.playerId;

    return `
        <div class="player-card ${isLeader ? 'leader' : ''} ${isEliminated ? 'eliminated' : ''}"
             data-player-id="${player.id}">
            <div class="player-avatar" style="background: ${escapeHtml(player.color || '#666')}">
                ${escapeHtml(player.name.charAt(0).toUpperCase())}
            </div>
            <div class="player-info">
                <div class="player-name">
                    ${escapeHtml(formatPlayerName(player))}
                    ${player.isBot ? `<span class="bot-badge" title="Computer player">${icon('bot')}</span>` : ''}
                    ${canRename ? `<button class="rename-btn" data-action="renameSelf"
                        aria-label="Change your name" title="Change your name">${icon('pencil')}</button>` : ''}
                    ${player.isBot && gameState?.phase === 'lobby' ? `<button class="rename-btn bot-remove-btn"
                        data-action="removeBot" data-player-id="${escapeHtml(player.id)}"
                        aria-label="Remove ${escapeHtml(player.name)}" title="Send them back to the jungle">${icon('x')}</button>` : ''}
                </div>
                <div class="player-status">
                    ${renderLives(player)}
                    ${isLeader ? `<span class="player-tag gold">${icon('crown')} Leader</span>` : ''}
                    ${hasNecklace ? `<span class="player-tag gold" title="Wearing the Immunity Idol Necklace — cannot be voted for">${icon('necklace')} Immune</span>` : ''}
                    ${player.campRaidedBy ? `<span class="player-tag raid-tag" title="Camp Raid: their next drawn card goes to the raider">${icon('target')} Raided</span>` : ''}
                    ${!isEliminated ? `<span class="player-tag">${icon('cards')} ${cardCount}</span>` : ''}
                </div>
            </div>
            ${createPlayerActions(player)}
        </div>
    `;
}

/**
 * The tribe panel (playing screen): every player's torches, card count and
 * necklace at a glance — and, on YOUR steal step, the rows become steal targets.
 */
function renderLivesTracker(gameState) {
    const container = document.getElementById('livesTracker');
    if (!container || !gameState || !gameState.players) return;

    const myId = window.SurvivorGame?.localGameState?.playerId;
    const turnPhase = window.SurvivorGame?.getCurrentTurnPhase?.(gameState, myId);
    const stealTime = turnPhase === 'turn_steal';
    const currentTurnId = gameState.turnOrder?.[gameState.currentTurnIndex];

    const order = gameState.turnOrder && gameState.turnOrder.length
        ? gameState.turnOrder.filter(id => gameState.players[id])
        : Object.keys(gameState.players);

    const rows = order.map(id => {
        const player = gameState.players[id];
        const isMe = id === myId;
        const stealable = stealTime && !isMe && !player.isEliminated;
        const classes = [
            'lives-row',
            player.isEliminated ? 'eliminated' : '',
            isMe ? 'me' : '',
            id === currentTurnId && !player.isEliminated ? 'current-turn' : '',
            stealable ? 'steal-target' : ''
        ].filter(Boolean).join(' ');

        const raidTag = player.campRaidedBy
            ? `<span class="player-tag raid-tag" title="Camp Raid: their next drawn card goes to the raider">${icon('target')}</span>` : '';
        // At steal time you need the counts MORE, not less — show hand size
        // beside the steal hint so you can pick the richest target.
        const handCount = `<span title="Cards in hand">${icon('cards')} ${player.hand ? player.hand.length : 0}</span>`;
        const necklaceTag = gameState.necklaceHolder === id
            ? `<span class="necklace" title="Immunity Idol Necklace">${icon('necklace')}</span>` : '';
        const meta = stealable
            ? `<span class="row-meta">${necklaceTag} ${handCount}</span>
               <span class="steal-hint">${icon('swap')} steal</span>`
            : `<span class="row-meta">
                   ${necklaceTag}
                   ${handCount}
               </span>`;

        return `
            <div class="${classes}" data-player-id="${escapeHtml(id)}"
                 ${stealable ? `data-steal-target="${escapeHtml(id)}" role="button" tabindex="0" aria-label="Steal a card from ${escapeHtml(player.name)}"` : ''}>
                <span class="lives-dot" style="background: ${escapeHtml(player.color || '#666')}">${escapeHtml(player.name.charAt(0).toUpperCase())}</span>
                <span class="lives-name">${escapeHtml(formatPlayerName(player, 12))}${player.isBot ? ` <span class="bot-badge">${icon('bot')}</span>` : ''}${isMe ? ' <small style="color:var(--text-faint)">(you)</small>' : ''}</span>
                ${renderLives(player)}
                ${raidTag}
                ${meta}
            </div>
        `;
    }).join('');

    const hint = stealTime
        ? `<p class="panel-sub" style="margin: 0.5rem 0 0;">Your turn opens with a raid — tap a player to steal a random card.</p>`
        : '';

    container.innerHTML = `
        <p class="tribe-label">${icon('users')} The tribe</p>
        <div class="lives-strip">${rows}</div>
        ${hint}
    `;

    // Steal targets go through the same API path the old lobby buttons used
    container.querySelectorAll('[data-steal-target]').forEach(row => {
        const act = () => {
            const targetId = row.dataset.stealTarget;
            const gameId = window.SurvivorGame?.localGameState.gameId;
            const thiefId = window.SurvivorGame?.localGameState.playerId;
            if (!(gameId && thiefId && targetId)) return;
            const doSteal = () => {
                hapticFeedback('medium');
                window.SurvivorNetwork?.GameAPI.stealCard(gameId, thiefId, targetId);
            };
            if (window.SurvivorSettings?.get('confirmSteals')) {
                const name = window.SurvivorGame?.fullGameState?.players?.[targetId]?.name || 'them';
                showConfirm(`Steal a random card from ${name}?`, doSteal);
            } else {
                doSteal();
            }
        };
        row.addEventListener('click', act);
        row.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); }
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// PLACES — where around camp everyone is standing
// ─────────────────────────────────────────────────────────────────────────────
//
// While the game is in play the tribe drifts between camp places, and who
// slipped off with whom is meant to be PUBLIC — that is the whole drama. At
// Tribal Council the server forces everyone into one place and this panel
// locks shut. A Discord bot may later mirror places onto voice channels; this
// panel has to be the whole story on its own without one.

const PLACE_LABELS = {
    camp_fire: 'Camp Fire',
    the_beach: 'The Beach',
    the_water_well: 'The Water Well',
    tribal_council: 'Tribal Council'
};

/** Known places get their proper name; anything new gets a readable fallback. */
function placeLabel(place) {
    if (PLACE_LABELS[place]) return PLACE_LABELS[place];
    const words = String(place || '').split('_').filter(Boolean);
    if (!words.length) return 'Somewhere';
    return words.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

/** One player as a name/color chip — the tribe panel's dot, at chip scale. */
function renderPlaceChip(player, isMe) {
    const classes = ['place-chip', player.isEliminated ? 'is-out' : '', isMe ? 'is-me' : '']
        .filter(Boolean).join(' ');
    const initial = escapeHtml(String(player.name || '?').charAt(0).toUpperCase());
    return `<span class="${classes}">
        <span class="lives-dot" style="background: ${escapeHtml(player.color || '#666')}">${initial}</span>
        <span class="place-chip-name">${escapeHtml(formatPlayerName(player, 12))}</span>
        ${player.isBot ? `<span class="bot-badge">${icon('bot')}</span>` : ''}
    </span>`;
}

/**
 * One place: its name, who is standing there, and — when it is open and you
 * are not already in it — a tap target that walks you over.
 */
function renderPlaceRow({ place, members, myId, locked, here }) {
    const label = placeLabel(place);
    const chips = members.length
        ? members.map(([id, player]) => renderPlaceChip(player, id === myId)).join('')
        : `<span class="place-empty">Nobody</span>`;

    const tappable = !locked && !here;
    const classes = ['place-row', locked ? 'is-locked' : '', here ? 'is-here' : '', tappable ? 'is-open' : '']
        .filter(Boolean).join(' ');

    let tag;
    if (locked) tag = `<span class="place-tag locked">${icon('lock')} Closed</span>`;
    else if (here) tag = `<span class="place-tag here">${icon('check')} You are here</span>`;
    else tag = `<span class="place-tag go">${icon('swap')} Go there</span>`;

    let attrs;
    if (tappable) attrs = `data-place-move="${escapeHtml(place)}" role="button" tabindex="0" aria-label="Walk over to ${escapeHtml(label)}"`;
    else if (locked) attrs = 'aria-disabled="true"';
    else attrs = 'aria-current="true"';

    return `
        <div class="${classes}" data-place="${escapeHtml(place)}" ${attrs}>
            <div class="place-head">
                <span class="place-name">${escapeHtml(label)}</span>
                ${tag}
            </div>
            <div class="place-people">${chips}</div>
        </div>
    `;
}

/** One move at a time — a double-tap must not race two walks to the server. */
let placeMoveInFlight = false;

function renderPlacesPanel(gameState) {
    const container = document.getElementById('placesPanel');
    if (!container) return;

    const hide = () => { container.style.display = 'none'; container.innerHTML = ''; };

    // A server that predates places sends no policy — then say nothing at all
    // rather than inventing a camp that the server will not honour.
    const policy = gameState && gameState.placePolicy;
    if (!policy || !gameState.players) return hide();

    const myId = window.SurvivorGame?.localGameState?.playerId;
    const myPlace = gameState.players[myId]?.place || null;

    // Turn order keeps the chips in the same familiar sequence as the tribe panel
    const order = gameState.turnOrder && gameState.turnOrder.length
        ? gameState.turnOrder.filter(id => gameState.players[id])
        : Object.keys(gameState.players);
    const everyone = order.map(id => [id, gameState.players[id]]);
    const membersAt = (place) => everyone.filter(([, player]) => player.place === place);

    let rows;
    let hint;

    if (policy.forced) {
        // Called together: one row, everybody in it, nothing to tap.
        let members = membersAt(policy.forced);
        if (!members.length) members = everyone;   // server state still catching up
        rows = renderPlaceRow({ place: policy.forced, members, myId, locked: true,
                                here: myPlace === policy.forced });
        hint = `<p class="panel-sub places-hint">${icon('lock')} The tribe has been called together — nobody wanders off now.</p>`;
    } else {
        const open = Array.isArray(policy.open) ? policy.open.filter(Boolean) : [];
        if (!open.length) return hide();
        rows = open.map(place => renderPlaceRow({
            place,
            members: membersAt(place),
            myId,
            locked: false,
            here: myPlace === place
        })).join('');
        hint = `<p class="panel-sub places-hint">Tap a place to walk over. The whole tribe can see where you went.</p>`;
    }

    container.style.display = '';
    container.innerHTML = `
        <p class="tribe-label">${icon('users')} Around camp</p>
        <div class="places-strip">${rows}</div>
        ${hint}
    `;

    container.querySelectorAll('[data-place-move]').forEach(row => {
        const act = () => movePlaceTo(row.dataset.placeMove);
        row.addEventListener('click', act);
        row.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); }
        });
    });
}

/** Walk to a place. The server is the authority on whether you may. */
async function movePlaceTo(place) {
    if (!place || placeMoveInFlight) return;
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const playerId = window.SurvivorGame?.localGameState?.playerId;
    const api = window.SurvivorNetwork?.GameAPI;
    if (!gameId || !playerId || !api?.movePlace) return;

    placeMoveInFlight = true;
    hapticFeedback('light');
    try {
        const result = await api.movePlace(gameId, playerId, place);
        if (result?.gameState && window.updateGameState) {
            window.updateGameState(result.gameState);
        }
        announce(`You moved to ${placeLabel(place)}`);
    } catch (error) {
        // apiCall has already toasted the reason — a forced place, a closed
        // place, or a server with no /api/place/move yet. Swallow it here so a
        // refused walk never becomes an unhandled rejection.
        console.warn('Place move refused:', error?.message || error);
    } finally {
        placeMoveInFlight = false;
    }
}

function createPlayerActions(player) {
    // Stealing is a turn action — it lives on the playing screen's tribe panel,
    // never in the lobby. The lobby only offers leadership handoff.
    const isLeader = window.SurvivorGame?.localGameState.isLeader;

    if (isLeader && !player.isCouncilLeader && !player.isEliminated) {
        return `
            <div class="player-actions">
                <button class="btn btn-sm btn-secondary leader-btn" data-target-id="${escapeHtml(player.id)}">
                    ${icon('crown')} Make Leader
                </button>
            </div>
        `;
    }
    return '';
}

// ─────────────────────────────────────────────────────────────────────────────
// ROCKS EXPANSION — ACTIVE CHALLENGE PANEL
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Render the active Rocks Challenge, including the controls for whoever is up.
 * All four playable challenges share this panel; the button set comes from the
 * server's `challenge.actions` list so the UI can never offer an illegal move.
 */
function renderChallengePanel(gameState) {
    const container = document.getElementById('challengePanel');
    if (!container) return;

    const ch = gameState && gameState.challenge;
    if (!ch) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    const myId = window.SurvivorGame?.localGameState?.playerId;
    const isMyMove = ch.currentPlayerId === myId && ch.phase !== 'complete';
    const name = pid => escapeHtml(gameState.players?.[pid]?.name || 'Player');

    const bag = ch.bag || { grey: 0, purple: 0 };
    const bagLeft = (bag.grey || 0) + (bag.purple || 0);

    const knocked = (ch.knockedOut || []).map(name).join(', ');
    const log = (ch.log || []).slice(-5).map(l => `<li>${escapeHtml(l)}</li>`).join('');

    let controls = '';
    if (isMyMove) {
        const actions = ch.actions || [];
        const buttons = [];

        if (actions.includes('bid')) {
            buttons.push(`
                <div class="challenge-input-row">
                    <input type="number" id="challengeBidInput" class="form-input"
                           min="${(ch.currentBid || 0) + 1}" max="${ch.maxBid || bagLeft}"
                           value="${(ch.currentBid || 0) + 1}" aria-label="Bid amount">
                    <button class="btn btn-enhanced touch-target" data-challenge-action="bid">Bid</button>
                </div>
            `);
        }
        if (actions.includes('pull') && ch.type === 'lowest_score_loses') {
            buttons.push(`
                <div class="challenge-input-row">
                    <input type="number" id="challengePullInput" class="form-input"
                           min="0" max="${ch.maxPull ?? bagLeft}" value="0" aria-label="Rocks to pull">
                    <button class="btn btn-enhanced touch-target" data-challenge-action="pull">Pull secretly</button>
                </div>
            `);
        } else if (actions.includes('pull')) {
            buttons.push(`<button class="btn btn-enhanced touch-target" data-challenge-action="pull">Pull a rock</button>`);
        }
        if (actions.includes('pass')) {
            buttons.push(`<button class="btn btn-secondary btn-enhanced touch-target" data-challenge-action="pass">Pass</button>`);
        }
        if (actions.includes('steal')) {
            const options = (ch.stealTargets || [])
                .map(pid => `<option value="${escapeHtml(pid)}">${name(pid)}</option>`).join('');
            buttons.push(`
                <div class="challenge-input-row">
                    <select id="challengeStealTarget" class="form-input" aria-label="Steal from">${options}</select>
                    <button class="btn btn-warning btn-enhanced touch-target" data-challenge-action="steal">Steal their rock</button>
                </div>
            `);
        }
        controls = `<div class="challenge-controls">${buttons.join('')}</div>`;
    } else if (ch.phase !== 'complete' && ch.currentPlayerId) {
        controls = `<p class="challenge-waiting">Waiting for ${name(ch.currentPlayerId)}…</p>`;
    } else if (ch.phase === 'complete') {
        controls = `<button class="btn btn-success btn-enhanced touch-target" data-challenge-action="dismiss">Continue</button>`;
    }

    const rockDot = (purple) => `<span class="rock ${purple ? 'purple' : ''}"></span>`;

    let scoreboard = '';
    if (ch.type === 'lowest_score_loses' && ch.lastRound && ch.lastRound.scores) {
        const rows = Object.entries(ch.lastRound.scores)
            .sort((a, b) => b[1] - a[1])
            .map(([pid, score]) => {
                const pulls = (ch.lastRound.pulls || {})[pid] || {};
                return `<li>${name(pid)}: <strong>${score > 0 ? '+' : ''}${score}</strong>
                        <span class="rock-tag">${pulls.grey || 0} ${rockDot(false)}</span>
                        <span class="rock-tag">${pulls.purple || 0} ${rockDot(true)}</span></li>`;
            }).join('');
        scoreboard = `<ul class="challenge-scores">${rows}</ul>`;
    }
    if (ch.type === 'pull_or_steal' && ch.rocks && Object.keys(ch.rocks).length) {
        const rows = Object.entries(ch.rocks)
            .map(([pid, rock]) => `<li>${name(pid)}: <span class="rock-tag">${rockDot(rock === 'purple')} ${rock === 'purple' ? 'Purple' : 'Grey'}</span></li>`).join('');
        scoreboard = `<ul class="challenge-scores">${rows}</ul>`;
    }

    // The bag, drawn: one dot per rock still inside (purple count is public setup info)
    const bagDots = rockDot(false).repeat(Math.min(bag.grey || 0, 12)) +
                    rockDot(true).repeat(Math.min(bag.purple || 0, 4));

    container.style.display = 'block';
    container.innerHTML = `
        <div class="challenge-header">
            <h3>${icon('rock')} ${escapeHtml(ch.name || 'Challenge')}</h3>
            <span class="challenge-round">Round ${ch.round || 1}</span>
        </div>
        <p class="challenge-goal">${escapeHtml(ch.goal || '')}</p>
        <p class="challenge-prompt">${escapeHtml(ch.prompt || '')}</p>
        <div class="challenge-meta">
            <span class="bag-meter" title="${bagLeft} rock(s) in the bag">Bag ${bagDots || '— empty'}</span>
            ${ch.currentBid ? `<span>High bid ${ch.currentBid} · ${name(ch.highBidderId)}</span>` : ''}
            ${knocked ? `<span>Out: ${knocked}</span>` : ''}
        </div>
        ${scoreboard}
        ${controls}
        ${log ? `<ul class="challenge-log">${log}</ul>` : ''}
    `;

    setupChallengeInteractions();
}

function setupChallengeInteractions() {
    const buttons = Array.from(document.querySelectorAll('[data-challenge-action]'));

    buttons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const action = btn.dataset.challengeAction;
            let value = null;
            if (action === 'bid') {
                value = parseInt(document.getElementById('challengeBidInput')?.value, 10);
            } else if (action === 'pull') {
                const input = document.getElementById('challengePullInput');
                if (input) value = parseInt(input.value, 10);
            } else if (action === 'steal') {
                value = document.getElementById('challengeStealTarget')?.value;
            }

            // Guard against double-taps, but re-enable if the move was rejected so
            // the panel never wedges (a rejected action emits no state update).
            buttons.forEach(b => { b.disabled = true; });
            const result = await window.SurvivorGame?.challengeAction(action, value);
            if (!result || !result.success) {
                buttons.forEach(b => { b.disabled = false; });
            }
        });
    });
}

function renderPlayerHand(gameState, containerId = 'playerHand') {
    const container = document.getElementById(containerId);
    if (!container) return;

    const playerId = window.SurvivorGame?.localGameState.playerId;
    const player = gameState.players?.[playerId];

    if (!player || !player.hand || !player.hand.length) {
        container.innerHTML = `
            <p class="tribe-label">${icon('cards')} Your hand</p>
            <p class="empty-hand">No cards — the island provides at the next draw.</p>
        `;
        return;
    }

    const currentPhase = window.SurvivorGame?.getCurrentTurnPhase(gameState, playerId);
    const html = player.hand.map((card, index) =>
        createCardElement(card, index, currentPhase)
    ).join('');

    container.innerHTML = `
        <p class="tribe-label">${icon('cards')} Your hand <span style="letter-spacing:0; color:var(--text-faint)">· ${player.hand.length}</span></p>
        <div class="hand-grid">${html}</div>
    `;

    // Animate cards entering the hand
    const handRail = container.querySelector('.hand-grid');
    if (handRail) animateCardEntrance(handRail);

    // Setup card interactions
    setupCardInteractions();
}

const CATEGORY_LABELS = {
    action: 'Action',
    tribal_advantage: 'Tribal Advantage',
    vote: 'Vote',
    challenge: 'Challenge',
    tribal_council: 'Tribal Council'
};

function createCardElement(card, index, currentPhase) {
    const cardInfo = window.SurvivorGame?.getCardInfo(card.type);
    const isPlayable = window.SurvivorGame?.canPlayCard(card, currentPhase);
    const requiresTarget = cardInfo?.requiresTarget;
    const category = cardInfo?.category || 'action';
    const escapedName = escapeHtml(cardInfo?.name || card.type);

    // Mini face: the whole hand fits on screen at once. Rules and the play
    // action live in the card sheet a tap opens.
    return `
        <div class="card-button card-mini card-cat-${escapeHtml(category)} ${isPlayable ? 'playable' : 'locked'} touch-target"
             role="button" tabindex="0"
             data-card-index="${index}"
             data-card-type="${card.type}"
             aria-label="${escapedName}${isPlayable ? ' — playable now' : ''}">
            <div class="card-category">${escapeHtml(CATEGORY_LABELS[category] || category)}</div>
            <div class="card-name">${escapedName}</div>
            <div class="card-mini-badges">
                ${requiresTarget ? `<span class="card-mini-badge" title="Needs a target">${icon('target')}</span>` : ''}
                ${cardInfo?.reactiveOnly ? `<span class="card-mini-badge" title="Plays itself when you are raided">${icon('alert')}</span>` : ''}
                ${isPlayable ? `<span class="card-mini-badge card-mini-now">now</span>` : ''}
            </div>
        </div>
    `;
}

/**
 * The card sheet — tap a card in the grid to read it and (when legal) play it.
 * Doubles as the confirmation step: no card leaves the hand on a single tap.
 */
function openCardSheet(cardIndex) {
    const gameState = window.SurvivorGame?.fullGameState;
    const playerId = window.SurvivorGame?.localGameState?.playerId;
    const hand = gameState?.players?.[playerId]?.hand || [];
    const card = hand[cardIndex];
    if (!card) return;

    const cardInfo = window.SurvivorGame?.getCardInfo(card.type);
    const currentPhase = window.SurvivorGame?.getCurrentTurnPhase(gameState, playerId);
    const isPlayable = window.SurvivorGame?.canPlayCard(card, currentPhase);
    const category = cardInfo?.category || 'action';
    const phases = (cardInfo?.playablePhases || []).filter(ph => ph !== 'reactive_theft');

    const timingChips = phases.map(ph =>
        `<span class="card-sheet-phase">${escapeHtml(CardTooltipManager.formatPhaseName(ph))}</span>`
    ).join('');

    let footer;
    if (cardInfo?.reactiveOnly) {
        footer = `<p class="card-sheet-note">${icon('alert')} This card plays itself — when someone
                  tries to raid you, you'll be offered it on the spot.</p>`;
    } else if (isPlayable) {
        footer = `
            ${cardInfo?.requiresTarget ? `<p class="card-sheet-note">${icon('target')} You'll choose a target next.</p>` : ''}
            <button class="btn btn-primary btn-enhanced touch-target" id="cardSheetPlayBtn">
                Play This Card
            </button>`;
    } else {
        footer = `<p class="card-sheet-note card-sheet-locked-note">${icon('hourglass')} Not playable right now.</p>`;
    }

    showModal(`
        <div class="card-sheet card-cat-${escapeHtml(category)}">
            <p class="card-category">${escapeHtml(CATEGORY_LABELS[category] || category)}</p>
            <p class="card-sheet-desc">${escapeHtml(cardInfo?.description || '')}</p>
            ${timingChips ? `<div class="card-sheet-timing">
                <span class="card-sheet-timing-label">Playable during</span>${timingChips}
            </div>` : ''}
            ${footer}
        </div>
    `, { title: cardInfo?.name || card.type });

    setTimeout(() => {
        document.getElementById('cardSheetPlayBtn')?.addEventListener('click', () => {
            hideModal();
            // The hand may have shifted while the sheet was open (a raid, a
            // state push) — only play if this index still holds the same card.
            const freshHand = window.SurvivorGame?.fullGameState?.players?.[playerId]?.hand || [];
            if (freshHand[cardIndex]?.type !== card.type) {
                showToast('Your hand changed — check your cards', 'warning');
                return;
            }
            beginCardPlay(cardIndex, card.type);
        });
    }, 0);
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
        <div class="vote-target touch-target" data-player-id="${safeId}" role="button" tabindex="0"
             aria-label="Vote to send ${safeName} home">
            <div class="vote-target-avatar" style="background: ${safeColor}">
                ${initial}
            </div>
            <div class="vote-target-name">${escapeHtml(formatPlayerName(player))}</div>
            <div class="vote-count">write their name</div>
        </div>
    `;
}

/**
 * Event Handlers — Unified Pointer Events
 */

// Long-press state tracking
const LONG_PRESS_MS = 400;
let longPressTimer = null;
let longPressTriggered = false;
let activePointerId = null;

function setupCardInteractions() {
    CardTooltipManager.hide();
    document.querySelectorAll('.card-mini').forEach(cardElement => {
        const cardIndex = parseInt(cardElement.dataset.cardIndex);

        cardElement.addEventListener('click', () => {
            hapticFeedback('light');
            openCardSheet(cardIndex);
        });
        cardElement.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openCardSheet(cardIndex);
            }
        });
        cardElement.addEventListener('contextmenu', (e) => e.preventDefault());
    });
}

function setupVoteInteractions() {
    document.querySelectorAll('.vote-target').forEach(target => {
        target.addEventListener('pointerup', handleVoteTargetClick);
        target.addEventListener('contextmenu', (e) => e.preventDefault());
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

/**
 * Card play pipeline — collects every parameter a card needs before it leaves
 * your hand. Some cards need more than a target: Knowledge Is Power names a
 * card, Do Or Die throws rock/paper/scissors, an Alliance picks two players.
 * Without these prompts the server either rejects the play or (worse) consumes
 * the card with no effect.
 */
function beginCardPlay(cardIndex, cardType) {
    const cardInfo = window.SurvivorGame?.getCardInfo(cardType);

    switch (cardType) {
        case 'the_spy_shack':
            // Official: "Look at any player's cards and take one." — pick whose
            // camp to enter, see their hand, choose your prize.
            showPlayerPicker({
                title: 'The Spy Shack',
                hint: 'Whose cards do you want to see?',
                onPick: (targetId) => showSpyHandPicker({
                    targetId,
                    onPick: (takeIndex) => playCard(cardIndex, { targetId, takeIndex })
                })
            });
            return;

        case 'reward_challenge_power_pair':
            // Official: "Pick 2 other players" — then all three of you throw fingers
            showPlayerPicker({
                title: 'Power Pair',
                hint: 'Pick the first of your two players.',
                onPick: (firstId) => showPlayerPicker({
                    title: 'Power Pair',
                    hint: 'Now the second — all three of you will show 1-3 fingers.',
                    excludeIds: [firstId],
                    onPick: (secondId) => playCard(cardIndex, { targetIds: [firstId, secondId] })
                })
            });
            return;

        case 'knowledge_is_power':
            // Target first, then name the card you demand from them
            showPlayerPicker({
                title: 'Knowledge Is Power',
                hint: 'Whose camp do you interrogate?',
                onPick: (targetId) => showCardNamePicker({
                    title: 'Name the card',
                    hint: 'If they have one, they must hand it over.',
                    onPick: (namedType) => playCard(cardIndex, { targetId, cardType: namedType })
                })
            });
            return;

        case 'reward_challenge_do_or_die':
            // Opponent first, then your secret throw
            showPlayerPicker({
                title: 'Do Or Die',
                hint: 'Challenge someone to Rock · Paper · Scissors.',
                onPick: (targetId) => showRpsPicker({
                    onPick: (choice) => playCard(cardIndex, { targetId, choice })
                })
            });
            return;

        case 'lets_form_an_alliance':
            // Partner first, then the victim (who can't be the partner)
            showPlayerPicker({
                title: "Let's Form An Alliance",
                hint: 'Choose your partner in crime.',
                onPick: (allyId) => showPlayerPicker({
                    title: "Let's Form An Alliance",
                    hint: 'Now choose the victim — you each steal one of their cards.',
                    excludeIds: [allyId],
                    onPick: (victimId) => playCard(cardIndex, { allyId, victimId })
                })
            });
            return;

        default:
            if (cardInfo?.requiresTarget) {
                showPlayerPicker({
                    title: cardInfo?.name || 'Select Target',
                    hint: 'Choose a player.',
                    onPick: (targetId) => playCard(cardIndex, { targetId })
                });
            } else {
                playCard(cardIndex);
            }
    }
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

    // Holding Extra Votes? Ask how many to pile on before the parchment goes in.
    const voterId = window.SurvivorGame?.localGameState?.playerId;
    const me = window.SurvivorGame?.fullGameState?.players?.[voterId];
    const extra = me?.extraVotes ?? 0;
    if (extra > 0 && !me?.hasVoted) {
        showExtraVoteChooser(playerId);
        return;
    }

    // Cast vote
    castVote(playerId);
}

/**
 * Extra Vote chooser — Extra Vote cards MAY be spent now or saved for a later
 * tribal, so the player picks how many ride along with the mandatory ballot.
 */
function showExtraVoteChooser(targetId) {
    const voterId = window.SurvivorGame?.localGameState?.playerId;
    const state = window.SurvivorGame?.fullGameState;
    const me = state?.players?.[voterId];
    const target = state?.players?.[targetId];
    if (!me || !target) { castVote(targetId); return; }

    const mandatory = me.mandatoryVotes ?? 0;
    const extra = me.extraVotes ?? 0;
    const minTotal = Math.max(1, mandatory);
    const maxTotal = mandatory + extra;

    let buttons = '';
    for (let t = minTotal; t <= maxTotal; t++) {
        const extrasUsed = Math.max(0, t - mandatory);
        const sub = extrasUsed === 0
            ? 'Save your Extra Votes for later'
            : `Adds ${extrasUsed} Extra Vote${extrasUsed === 1 ? '' : 's'}`;
        buttons += `
            <button class="btn btn-enhanced touch-target extra-vote-option"
                    style="width:100%; margin-bottom:0.5rem; display:block;"
                    data-total="${t}">
                ${t} vote${t === 1 ? '' : 's'} against ${escapeHtml(target.name || 'them')}
                <span class="panel-sub" style="display:block; font-size:0.8em;">${sub}</span>
            </button>`;
    }

    // Extra Votes are separate ballots — they may land on different heads
    const otherTargets = Object.values(state?.players || {}).filter(p =>
        !p.isEliminated && p.id !== voterId
        && p.id !== state?.necklaceHolder).length;
    const splitOption = (extra >= 1 && otherTargets >= 2) ? `
        <button class="btn touch-target extra-vote-option-split"
                style="width:100%; display:block;">
            Split votes across players…
            <span class="panel-sub" style="display:block; font-size:0.8em;">
                Write different names on different parchments</span>
        </button>` : '';

    showModal(`
        <p class="panel-sub" style="margin-bottom:0.75rem;">
            You hold ${extra} Extra Vote${extra === 1 ? '' : 's'}. Spend them now, or keep them hidden for a later Tribal Council.
        </p>
        ${buttons}
        ${splitOption}
    `, { title: 'How many votes?' });

    document.querySelectorAll('.extra-vote-option').forEach(btn => {
        btn.addEventListener('click', () => {
            const total = parseInt(btn.dataset.total, 10);
            hideModal();
            castVote(targetId, total);
        });
    });
    document.querySelector('.extra-vote-option-split')?.addEventListener('click', () => {
        hideModal();
        setTimeout(() => showSplitBallotBuilder(voterId, targetId), 80);
    });
}

/**
 * Split-ballot builder: allocate your Vote + Extra Votes across several
 * players. Mandatory cards must all be cast; extras are optional. The server
 * has always tallied multi-target ballots — this is the phone UI for it.
 */
function showSplitBallotBuilder(voterId, firstTargetId = null) {
    const state = window.SurvivorGame?.fullGameState;
    const me = state?.players?.[voterId];
    if (!me) return;

    const mandatory = me.mandatoryVotes ?? 0;
    const maxTotal = mandatory + (me.extraVotes ?? 0);
    const targets = Object.values(state.players).filter(p =>
        !p.isEliminated && p.id !== voterId && p.id !== state.necklaceHolder);
    const alloc = {};
    targets.forEach(t => { alloc[t.id] = 0; });
    if (firstTargetId && firstTargetId in alloc) alloc[firstTargetId] = 1;

    const rows = targets.map(t => `
        <div class="settings-row" data-ballot-row="${escapeHtml(t.id)}">
            <label>${escapeHtml(t.name)}</label>
            <div class="seg-group">
                <button class="seg-btn touch-target" data-ballot-minus="${escapeHtml(t.id)}">−</button>
                <span class="seg-btn" data-ballot-count="${escapeHtml(t.id)}"
                      style="cursor:default">${alloc[t.id]}</span>
                <button class="seg-btn touch-target" data-ballot-plus="${escapeHtml(t.id)}">+</button>
            </div>
        </div>`).join('');

    showModal(`
        <div class="cardname-selection">
            <p class="picker-hint" id="splitBallotStatus"></p>
            ${rows}
            <button class="btn btn-enhanced touch-target" id="splitBallotCast"
                    style="width:100%; margin-top:0.75rem;">Cast this ballot</button>
        </div>
    `, { title: 'Write your parchments' });

    const total = () => Object.values(alloc).reduce((a, b) => a + b, 0);
    const refresh = () => {
        targets.forEach(t => {
            const el = document.querySelector(`[data-ballot-count="${t.id}"]`);
            if (el) el.textContent = alloc[t.id];
        });
        const status = document.getElementById('splitBallotStatus');
        const castBtn = document.getElementById('splitBallotCast');
        const n = total();
        if (status) {
            status.textContent = n < mandatory
                ? `Cast at least ${mandatory} (your Vote Card${mandatory > 1 ? 's' : ''} must be used) — ${n} placed`
                : `${n} of up to ${maxTotal} votes placed`;
        }
        if (castBtn) castBtn.disabled = n < mandatory || n > maxTotal;
    };

    targets.forEach(t => {
        document.querySelector(`[data-ballot-plus="${t.id}"]`)?.addEventListener('click', () => {
            if (total() < maxTotal) { alloc[t.id] += 1; refresh(); }
        });
        document.querySelector(`[data-ballot-minus="${t.id}"]`)?.addEventListener('click', () => {
            if (alloc[t.id] > 0) { alloc[t.id] -= 1; refresh(); }
        });
    });
    refresh();

    document.getElementById('splitBallotCast')?.addEventListener('click', () => {
        const votesData = targets
            .filter(t => alloc[t.id] > 0)
            .map(t => ({ targetId: t.id, votes: alloc[t.id] }));
        hideModal();
        castSplitBallot(voterId, votesData);
    });
}

async function castSplitBallot(voterId, votesData, skipConfirm = false) {
    const gameId = window.SurvivorGame?.localGameState.gameId;
    if (!gameId || !voterId || !votesData?.length) return;

    if (!skipConfirm && window.SurvivorSettings?.get('confirmVotes')) {
        const state = window.SurvivorGame?.fullGameState;
        const summary = votesData.map(v =>
            `${v.votes} on ${state?.players?.[v.targetId]?.name || 'them'}`).join(', ');
        showConfirm(`Cast this ballot — ${summary}? A vote can't be taken back.`,
            () => castSplitBallot(voterId, votesData, true));
        return;
    }

    try {
        showLoading('The parchments go in the box…');
        const result = await window.SurvivorNetwork?.GameAPI.castVote(gameId, voterId, votesData);
        if (result && result.success) {
            Haptics.trigger('success');
        }
    } catch (error) {
        showToast(error.message || 'Failed to cast votes', 'error');
        Haptics.trigger('error');
    } finally {
        hideLoading();
    }
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

// Touch handlers replaced by unified Pointer Events in setupCardInteractions

/**
 * Game Actions
 */
async function playCard(cardIndex, params = {}) {
    const gameId = window.SurvivorGame?.localGameState.gameId;
    const playerId = window.SurvivorGame?.localGameState.playerId;

    if (!gameId || !playerId) {
        showToast('Game state error', 'error');
        return;
    }

    // Back-compat: older call sites passed a bare targetId string
    if (typeof params === 'string') params = { targetId: params };

    try {
        showLoading('Playing card...');
        // apiCall already toasts result.message on success — don't say it twice
        await window.SurvivorNetwork?.GameAPI.playCard(gameId, playerId, cardIndex, params);
    } catch (error) {
        showToast(error.message || 'Failed to play card', 'error');
    } finally {
        hideLoading();
    }
}

async function castVote(targetId, totalVotes = null, skipConfirm = false) {
    const gameId = window.SurvivorGame?.localGameState.gameId;
    const voterId = window.SurvivorGame?.localGameState.playerId;

    if (!gameId || !voterId || !targetId) {
        showToast('Vote error', 'error');
        Haptics.trigger('error');
        return;
    }

    // Optional mistap guard (device setting). Runs after the extra-vote
    // chooser, so the two dialogs never stack.
    if (!skipConfirm && window.SurvivorSettings?.get('confirmVotes')) {
        const name = window.SurvivorGame?.fullGameState?.players?.[targetId]?.name || 'this player';
        showConfirm(`Write ${name} on your parchment? A vote can't be taken back.`,
            () => castVote(targetId, totalVotes, true));
        return;
    }

    try {
        // Dramatic vote haptic feedback
        Haptics.trigger('vote');
        showLoading('Placing your parchment in the box…');

        // Every Vote/Goodwill Gamble card in hand MUST be cast at this tribal;
        // the server rejects partial ballots. Extra Votes may ride along when
        // the chooser passes a total. A player whose Vote Card was stolen
        // legally passes the box (empty ballot).
        const me = window.SurvivorGame?.fullGameState?.players?.[voterId];
        const maxVotes = me?.maxVotes ?? 1;
        const mandatory = me?.mandatoryVotes ?? 1;
        const votes = totalVotes != null
            ? Math.min(Math.max(totalVotes, Math.max(1, mandatory)), Math.max(maxVotes, 1))
            : Math.max(1, mandatory);
        const votesData = maxVotes === 0 ? [] : [{ targetId, votes }];
        const result = await window.SurvivorNetwork?.GameAPI.castVote(gameId, voterId, votesData);

        // apiCall already toasts result.message on success — only the haptic here
        if (result && result.success) {
            Haptics.trigger('success');
        }
    } catch (error) {
        showToast(error.message || 'Failed to cast vote', 'error');
        Haptics.trigger('error');
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

    // Use native dialog API if available, fall back to style toggle
    if (typeof modalOverlay.showModal === 'function') {
        // A stale inline display:none (from a fallback-path hide) would keep the
        // dialog invisible even while open — always clear it before showing.
        modalOverlay.style.removeProperty('display');
        if (!modalOverlay.open) modalOverlay.showModal();
    } else {
        modalOverlay.style.display = 'flex';
    }
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
        // Use native dialog API if available. Never set inline display:none on a
        // real <dialog> — hiding an ALREADY-closed dialog used to fall through to
        // the style branch, and the stale inline style then kept every future
        // dialog invisible while "open".
        if (typeof modalOverlay.close === 'function') {
            if (modalOverlay.open) modalOverlay.close();
        } else {
            modalOverlay.style.display = 'none';
        }
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

/**
 * Prompt helpers for the card play pipeline.
 * All of them render into the shared modal and hand the choice to `onPick`.
 */
function showPlayerPicker({ title = 'Select Target', hint = '', excludeIds = [], onPick }) {
    const gameState = window.SurvivorGame?.fullGameState;
    if (!gameState?.players) return;

    const playerId = window.SurvivorGame?.localGameState.playerId;
    const eligible = Object.values(gameState.players).filter(player =>
        player.id !== playerId && !player.isEliminated && !excludeIds.includes(player.id)
    );

    const content = `
        <div class="target-selection">
            ${hint ? `<p class="picker-hint">${escapeHtml(hint)}</p>` : ''}
            <div class="target-grid">
                ${eligible.map(player => {
                    const safeId = escapeHtml(player.id);
                    const safeName = escapeHtml(formatPlayerName(player));
                    const safeColor = escapeHtml(player.color || '#666');
                    return `
                        <button class="target-option touch-target" data-target-id="${safeId}">
                            <span class="target-dot" style="background:${safeColor}"></span>
                            <span class="target-name">${safeName}</span>
                        </button>
                    `;
                }).join('')}
            </div>
        </div>
    `;

    showModal(content, { title });

    setTimeout(() => {
        document.querySelectorAll('.target-option').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal();
                onPick && onPick(btn.dataset.targetId);
            });
        });
    }, 0);
}

/** Grid of every nameable card — for Knowledge Is Power's demand. */
const HOUSE_CARD_TYPES = ['idol_nullifier', 'steal_vote', 'block_vote', 'grant_immunity'];

function showCardNamePicker({ title = 'Name a card', hint = '', onPick }) {
    const cards = window.SurvivorGame?.SURVIVOR_CARDS || {};
    const gameState = window.SurvivorGame?.fullGameState || {};

    // Only offer cards that can actually be in someone's hand in THIS game:
    // no tribal council cards ever, no Challenge cards outside the expansion,
    // no house cards outside the extended deck, and never the Vote Card —
    // only Control The Vote can take that.
    const nameable = Object.values(cards)
        .filter(c => c.category !== 'tribal_council')
        .filter(c => c.type !== 'vote')
        .filter(c => gameState.expansion || c.category !== 'challenge')
        .filter(c => gameState.deckMode === 'extended' || !HOUSE_CARD_TYPES.includes(c.type))
        .sort((a, b) => (a.category + a.name).localeCompare(b.category + b.name));

    const content = `
        <div class="cardname-selection">
            ${hint ? `<p class="picker-hint">${escapeHtml(hint)}</p>` : ''}
            <div class="cardname-grid">
                ${nameable.map(c => `
                    <button class="cardname-option touch-target" data-card-type="${escapeHtml(c.type)}">
                        <span class="cardname-cat">${escapeHtml(CATEGORY_LABELS[c.category] || c.category)}</span>
                        <span class="cardname-name">${escapeHtml(c.name)}</span>
                    </button>
                `).join('')}
            </div>
        </div>
    `;

    showModal(content, { title });

    setTimeout(() => {
        document.querySelectorAll('.cardname-option').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal();
                onPick && onPick(btn.dataset.cardType);
            });
        });
    }, 0);
}

/** The Spy Shack: the look — the target's actual hand, take one. */
function showSpyHandPicker({ targetId, onPick }) {
    const gameState = window.SurvivorGame?.fullGameState;
    const target = gameState?.players?.[targetId];
    if (!target) return;

    const hand = target.hand || [];
    if (!hand.length) {
        showToast(`${target.name} has no cards to spy on`, 'warning');
        return;
    }

    // You see everything — that is the card. But the Vote Card is not yours to take.
    const anyTakeable = hand.some(c => c.type !== 'vote');
    const content = `
        <div class="cardname-selection">
            <p class="picker-hint">${escapeHtml(target.name)}'s hand, laid bare — ${anyTakeable
                ? 'take one.'
                : 'but they hold nothing you can take.'}</p>
            <div class="cardname-grid">
                ${hand.map((c, i) => {
                    const info = window.SurvivorGame?.getCardInfo(c.type);
                    const locked = c.type === 'vote';
                    return `
                        <button class="cardname-option touch-target${locked ? ' is-locked' : ''}"
                                ${locked ? 'disabled aria-label="Vote Card — only Control The Vote can take this"' : `data-take-index="${i}"`}>
                            <span class="cardname-cat">${escapeHtml(CATEGORY_LABELS[info?.category] || info?.category || '')}</span>
                            <span class="cardname-name">${escapeHtml(info?.name || c.type)}</span>
                            ${locked ? '<span class="cardname-locked">out of reach</span>' : ''}
                        </button>
                    `;
                }).join('')}
            </div>
        </div>
    `;

    showModal(content, { title: 'The Spy Shack' });

    setTimeout(() => {
        document.querySelectorAll('[data-take-index]').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal();
                onPick && onPick(parseInt(btn.dataset.takeIndex));
            });
        });
    }, 0);
}

/** Rock · Paper · Scissors throw for Do Or Die. */
function showRpsPicker({ onPick }) {
    const throws = [
        { value: 'rock',     label: 'Rock',     mark: '●' },
        { value: 'paper',    label: 'Paper',    mark: '▭' },
        { value: 'scissors', label: 'Scissors', mark: '✕' },
    ];
    const content = `
        <div class="rps-selection">
            <p class="picker-hint">Make your throw — winner steals 2 cards, a tie swaps 1.</p>
            <div class="rps-row">
                ${throws.map(t => `
                    <button class="rps-option touch-target" data-choice="${t.value}">
                        <span class="rps-mark" aria-hidden="true">${t.mark}</span>
                        <span class="rps-label">${t.label}</span>
                    </button>
                `).join('')}
            </div>
        </div>
    `;

    showModal(content, { title: 'Do Or Die' });

    setTimeout(() => {
        document.querySelectorAll('.rps-option').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal();
                onPick && onPick(btn.dataset.choice);
            });
        });
    }, 0);
}

/** Back-compat shims — older call sites route through the pipeline. */
function showTargetSelectionModal(cardIndex, cardType) {
    beginCardPlay(parseInt(cardIndex), cardType);
}

function selectTarget(cardIndex, targetId) {
    hideModal();
    playCard(parseInt(cardIndex), { targetId });
}

/**
 * Toast Notifications
 */
function showToast(message, type = 'info', duration = null) {
    if (!toastContainer) {
        toastContainer = createToastContainer();
    }

    // Reading pace is a device setting; errors linger ~30% longer.
    // 0 (pinned) means the toast stays until tapped.
    if (duration == null) {
        duration = window.SurvivorSettings
            ? window.SurvivorSettings.toastMs(type)
            : ((type === 'error' || type === 'warning') ? 6500 : 5000);
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

    // Every toast dismisses on tap; only a positive duration auto-removes,
    // so the "pinned" pace waits for the reader.
    const dismiss = () => {
        if (!toast.parentNode) return;
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    };
    toast.addEventListener('click', dismiss);

    if (duration > 0) {
        setTimeout(dismiss, duration);
    }
}

function getToastIcon(type) {
    const icons = {
        success: icon('check'),
        error: icon('x'),
        warning: icon('alert'),
        info: icon('info')
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
    // Enhanced card play animation using Web Animations API
    const animation = cardElement.animate([
        { transform: 'scale(1) translateY(0)', opacity: 1 },
        { transform: 'scale(1.1) translateY(-20px)', opacity: 1, offset: 0.3 },
        { transform: 'scale(0.8) translateY(-60px)', opacity: 0 }
    ], {
        duration: 500,
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        fill: 'forwards'
    });

    animation.onfinish = () => {
        cardElement.style.opacity = '0';
    };
}

/**
 * Animate cards dealing into the hand (entrance animation)
 */
function animateCardEntrance(container) {
    const cards = container.querySelectorAll('.card-button');
    cards.forEach((card, i) => {
        card.animate([
            { transform: 'translateY(40px) scale(0.9)', opacity: 0 },
            { transform: 'translateY(0) scale(1)', opacity: 1 }
        ], {
            duration: 300,
            delay: i * 60,
            easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
            fill: 'backwards'
        });
    });
}

/**
 * Animate a stolen card flying from target to thief
 */
function animateCardSteal(fromEl, toEl) {
    if (!fromEl || !toEl) return;
    const fromRect = fromEl.getBoundingClientRect();
    const toRect = toEl.getBoundingClientRect();
    const dx = toRect.left - fromRect.left;
    const dy = toRect.top - fromRect.top;

    const ghost = document.createElement('div');
    ghost.className = 'card-button';
    ghost.style.cssText = `position:fixed;top:${fromRect.top}px;left:${fromRect.left}px;width:${fromRect.width}px;height:${fromRect.height}px;z-index:9999;pointer-events:none;`;
    ghost.textContent = '?';
    document.body.appendChild(ghost);

    ghost.animate([
        { transform: 'translate(0,0) rotate(0deg)', opacity: 1 },
        { transform: `translate(${dx}px,${dy}px) rotate(${dx > 0 ? 15 : -15}deg)`, opacity: 0.6 }
    ], { duration: 400, easing: 'ease-in-out' }).onfinish = () => ghost.remove();
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
        inset-block-start: calc(20px + env(safe-area-inset-top, 0px));
        inset-inline-end: calc(20px + env(safe-area-inset-right, 0px));
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
        renderLivesTracker(window.SurvivorGame.fullGameState);
        // A player object changing may mean somebody walked off — redraw places
        renderPlacesPanel(window.SurvivorGame.fullGameState);
    }

    // The camp opening up or being called together
    if (diff.placePolicy !== undefined) {
        renderPlacesPanel(window.SurvivorGame.fullGameState);
    }

    if (diff.phase) {
        updatePhaseIndicator(window.SurvivorGame.fullGameState);
    }

    if (diff.currentVote) {
        updateVotingInfo(window.SurvivorGame.fullGameState);
    }

    if (diff.challenge !== undefined) {
        renderChallengePanel(window.SurvivorGame.fullGameState);
    }

    if (diff.necklaceHolder !== undefined) {
        renderPlayerList(window.SurvivorGame.fullGameState);
        renderLivesTracker(window.SurvivorGame.fullGameState);
    }

    // Reactive theft window opening/closing arrives as a pending_theft diff
    if (diff.pending_theft !== undefined) {
        renderReactiveTheft(window.SurvivorGame.fullGameState);
    }

    // An idol awaiting its answer arrives as a pending_nullifier diff
    if (diff.pending_nullifier !== undefined) {
        renderNullifierWindow(window.SurvivorGame.fullGameState);
    }

    // Reward Challenge interaction state changes
    if (diff.interaction !== undefined) {
        renderInteraction(window.SurvivorGame.fullGameState);
    }

    // Additional diff-based updates could be added here
}

/**
 * Phase Guidance System
 * Provides contextual help based on current game phase
 */
const PHASE_GUIDANCE = {
    'lobby':       { icon: 'users',  text: 'Gathering the tribe', action: 'Share the fire code and wait for everyone to arrive.' },
    'turn_steal':  { icon: 'swap',   text: 'Steal', action: 'Tap a tribe member to steal a random card.' },
    'turn_play':   { icon: 'cards',  text: 'Play', action: 'Play a card if you like, then draw to end your turn.' },
    'turn_draw':   { icon: 'draw',   text: 'Draw', action: 'Card played — take the top card of the Draw Pile. Drawing ends your turn.' },
    'turn_done':   { icon: 'check',  text: 'Turn over', action: 'You drew — the torch passes on its own.' },
    'playing':     { icon: 'hourglass', text: 'On the island', action: 'Wait for the torch to come around.' },
    'tribal_council': { icon: 'torch', text: 'Tribal Council', action: 'Someone drew a Tribal Council card. The tribe must vote.' },
    'voting':      { icon: 'ballot', text: 'The vote', action: 'Tap a name to write it on your parchment.' },
    'immunity':    { icon: 'idol',   text: 'Idols', action: 'Play a Hidden Immunity Idol now — or hold your peace.' },
    'results':     { icon: 'eye',    text: 'The reveal', action: 'The Council Leader reads the votes.' },
    'final':       { icon: 'crown',  text: 'Final Tribal', action: 'The jury decides the Sole Survivor.' },
    'final_tribal':{ icon: 'crown',  text: 'Final Tribal', action: 'The jury decides the Sole Survivor.' },
    'finished':    { icon: 'crown',  text: 'Sole Survivor', action: 'The game is won.' }
};

function renderPhaseGuidance(gameState) {
    if (!gameState) return;

    // Find or create guidance container (mounted at the top of <main>)
    let guidanceEl = document.getElementById('phaseGuidance');
    if (!guidanceEl) {
        const main = document.querySelector('.main');
        if (!main) return;
        guidanceEl = document.createElement('div');
        guidanceEl.id = 'phaseGuidance';
        guidanceEl.className = 'phase-guidance';
        main.insertBefore(guidanceEl, main.firstChild);
    }

    // The guidance strip earns its place only once a game exists — and never
    // on the Hall of Fame or Settings, which are detours outside the game.
    if (!window.SurvivorGame?.localGameState?.gameId
            || currentScreen === 'leaderboardScreen'
            || currentScreen === 'settingsScreen') {
        guidanceEl.style.display = 'none';
        return;
    }
    guidanceEl.style.display = '';

    const myId = window.SurvivorGame?.localGameState?.playerId;
    const currentTurnId = gameState.turnOrder?.[gameState.currentTurnIndex];
    const isMyTurn = !!myId && currentTurnId === myId;

    // Resolve the most specific phase we can
    let key = gameState.phase || 'lobby';
    if (key === 'playing' && isMyTurn) {
        const turnPhase = window.SurvivorGame?.getCurrentTurnPhase?.(gameState, myId);
        if (['turn_steal', 'turn_play', 'turn_draw', 'turn_done'].includes(turnPhase)) key = turnPhase;
    } else if (key === 'tribal_council') {
        const sub = gameState.currentVote?.phase;
        if (sub === 'voting') key = 'voting';
        else if (sub === 'immunity') key = 'immunity';
        else if (sub === 'reveal') key = 'results';
    }

    const guidance = PHASE_GUIDANCE[key] || PHASE_GUIDANCE['playing'];

    let actionText = guidance.action;
    if (gameState.phase === 'playing' && !isMyTurn) {
        const currentPlayer = gameState.players?.[currentTurnId];
        actionText = `The torch is with ${currentPlayer?.name || 'another player'}.`;
    }

    guidanceEl.innerHTML = `
        <span class="phase-guidance-icon">${icon(guidance.icon)}</span>
        <div class="phase-guidance-content">
            <strong class="phase-guidance-text">${isMyTurn && gameState.phase === 'playing' ? 'Your turn — ' : ''}${guidance.text}</strong>
            <span class="phase-guidance-action">${actionText}</span>
        </div>
    `;

    // Add pulse effect when it's your turn
    if (isMyTurn && gameState.phase === 'playing') {
        guidanceEl.classList.add('your-turn');
    } else {
        guidanceEl.classList.remove('your-turn');
    }
}

/**
 * Ceremony modes — the whole app shifts atmosphere with the game phase.
 */
function setBodyMode(gameState) {
    const phase = gameState?.phase;
    let mode = null;
    if (phase === 'tribal_council') mode = 'council';
    else if (phase === 'final' || phase === 'final_tribal') mode = 'final';
    else if (phase === 'finished') mode = 'victory';

    if (mode) document.body.dataset.mode = mode;
    else delete document.body.dataset.mode;
}

/**
 * Phase-driven navigation: the island decides which screen you're on.
 * (Without this, the tribal ceremony screens are unreachable.)
 */
function desiredScreenFor(gameState) {
    if (!window.SurvivorGame?.localGameState?.gameId) return null;
    switch (gameState.phase) {
        case 'lobby':   return 'lobbyScreen';
        case 'playing': return 'playingScreen';
        case 'tribal_council': {
            const sub = gameState.currentVote?.phase || 'announcement';
            return {
                announcement: 'tribalAnnouncementScreen',
                advantage_play: 'tribalAdvantageScreen',
                discussion: 'tribalDiscussionScreen',
                voting: 'votingScreen',
                immunity: 'immunityScreen',
                reveal: 'resultsScreen'
            }[sub] || 'tribalAnnouncementScreen';
        }
        case 'final':
        case 'final_tribal': return 'finalTribalScreen';
        case 'finished': return 'gameOverScreen';
        default: return null;
    }
}

let isRouting = false;
function routeToPhase(gameState) {
    if (isRouting) return false;
    const target = desiredScreenFor(gameState);
    if (!target || target === currentScreen) return false;
    isRouting = true;
    try {
        showScreen(target);   // showScreen -> setupScreen -> updateCurrentScreen
    } finally {
        isRouting = false;
    }
    return true;
}

/**
 * Tribal ceremony screens — leader phrases and leader-only controls.
 * Tribal advantage cards remain playable via the ordinary hand rail.
 */
function renderTribalCeremony(gameState) {
    const currentVote = gameState.currentVote || {};
    const leaderId = currentVote.councilLeaderId;
    const leader = gameState.players?.[leaderId];
    const iAmLeader = leaderId === window.SurvivorGame?.localGameState?.playerId;
    const leaderName = escapeHtml(leader?.name || 'The Council Leader');

    const leaderBar = (label, action, iconName) => iAmLeader
        ? `<div class="game-actions" style="margin-top:1rem">
               <button class="btn btn-enhanced touch-target" data-action="${action}">
                   ${icon(iconName)} ${label}
               </button>
           </div>`
        : `<p class="panel-sub" style="text-align:center; margin-top:1rem">
               ${leaderName} leads this council…
           </p>`;

    if (currentScreen === 'tribalAnnouncementScreen') {
        const phraseEl = document.getElementById('tribalLeaderPhrase');
        const contentEl = document.getElementById('tribalAnnouncementContent');
        if (phraseEl) phraseEl.innerHTML = `
            <p class="leader-phrase">Welcome to Tribal Council. If anyone has a Tribal
            Advantage Card, you may play it now — or anytime before we vote.</p>
            <p class="leader-attribution">— ${leaderName}, Council Leader</p>
        `;
        if (contentEl) {
            contentEl.innerHTML = `<div class="panel"><div id="ceremonyHandAnnouncement"></div>${leaderBar('Open the Discussion', 'openDiscussion', 'speech')}</div>`;
            renderPlayerHand(gameState, 'ceremonyHandAnnouncement');
        }
    }

    if (currentScreen === 'tribalAdvantageScreen') {
        const contentEl = document.getElementById('tribalAdvantageContent');
        if (contentEl) {
            contentEl.innerHTML = `
                <p class="panel-sub">Tribal Advantage cards must be played before the vote begins.</p>
                <div id="ceremonyHandAdvantage"></div>
                ${leaderBar('Open the Discussion', 'openDiscussion', 'speech')}
            `;
            renderPlayerHand(gameState, 'ceremonyHandAdvantage');
        }
    }

    if (currentScreen === 'tribalDiscussionScreen') {
        const phraseEl = document.getElementById('tribalDiscussionPhrase');
        const contentEl = document.getElementById('tribalDiscussionContent');
        if (phraseEl) phraseEl.innerHTML = `
            <p class="leader-phrase">Now let's discuss who should be voted out. We can ask
            questions, form alliances, tell the truth, lie, and speak in private.</p>
        `;
        if (contentEl) {
            contentEl.innerHTML = `
                <div id="ceremonyHandDiscussion"></div>
                ${leaderBar('It Is Time to Vote', 'startVoting', 'ballot')}
            `;
            renderPlayerHand(gameState, 'ceremonyHandDiscussion');
        }
    }
}

/**
 * Final tribal: the official three questions, the jury's vote, the tie-break.
 */
function renderFinalTribal(gameState) {
    const container = document.getElementById('finalTribalContent');
    if (!container) return;

    const ft = gameState.finalTribal || {};
    const myId = window.SurvivorGame?.localGameState?.playerId;
    const finalists = ft.finalists || [];
    const jury = ft.jury || [];
    const name = pid => escapeHtml(gameState.players?.[pid]?.name || 'Unknown');
    const iAmJuror = jury.includes(myId);
    const iAmLeader = ft.leader === myId;

    const finalistCards = finalists.map(pid => {
        const player = gameState.players?.[pid] || {};
        const votes = ft.voteCounts?.[pid];
        return `
            <div class="player-card" data-player-id="${escapeHtml(pid)}">
                <div class="player-avatar" style="background: ${escapeHtml(player.color || '#666')}">${name(pid).charAt(0)}</div>
                <div class="player-info">
                    <div class="player-name">${name(pid)}</div>
                    <div class="player-status">${renderLives(player)} <span class="player-tag gold">${icon('crown')} Finalist</span></div>
                </div>
                ${votes !== undefined ? `<span class="row-meta"><span class="vote-count-number" style="font-size:1.3rem">${votes}</span></span>` : ''}
            </div>
        `;
    }).join('');

    const questions = (ft.questions || []).map((q, i) =>
        `<p class="leader-phrase" style="margin:0.5rem auto">${i + 1}. ${escapeHtml(q)}</p>`).join('');

    let action = '';
    if (ft.phase === 'questions' || ft.phase === 'deliberation') {
        action = iAmLeader
            ? `<div class="game-actions"><button class="btn btn-enhanced touch-target" data-action="beginFinalVote">${icon('ballot')} Call for the Vote</button></div>`
            : `<p class="panel-sub" style="text-align:center">${name(ft.leader)} leads the final council…</p>`;
    } else if (ft.phase === 'voting') {
        if (iAmJuror && !ft.votes?.[myId]) {
            action = `
                <p class="tribe-label">${icon('ballot')} Cast your jury vote — for the WINNER</p>
                <div class="vote-targets">
                    ${finalists.map(pid => `
                        <div class="vote-target touch-target final-vote-target" data-finalist-id="${escapeHtml(pid)}" role="button" tabindex="0">
                            <div class="vote-target-avatar" style="background: ${escapeHtml(gameState.players?.[pid]?.color || '#666')}">${name(pid).charAt(0)}</div>
                            <div class="vote-target-name">${name(pid)}</div>
                            <div class="vote-count">deserves to win</div>
                        </div>
                    `).join('')}
                </div>`;
        } else if (iAmJuror) {
            action = `<p class="panel-sub" style="text-align:center">Your vote is in. ${Object.keys(ft.votes || {}).length} of ${jury.length} jurors have spoken.</p>`;
        } else {
            action = `<p class="panel-sub" style="text-align:center">The jury is voting… ${Object.keys(ft.votes || {}).length} of ${jury.length} fingers raised.</p>`;
        }
    } else if (ft.phase === 'reveal' && ft.tieBreakNeeded) {
        action = iAmLeader
            ? `
                <p class="tribe-label">${icon('alert')} Dead even — you break the tie</p>
                <div class="vote-targets">
                    ${(ft.tiedFinalists || finalists).map(pid => `
                        <div class="vote-target touch-target final-tiebreak-target" data-finalist-id="${escapeHtml(pid)}" role="button" tabindex="0">
                            <div class="vote-target-avatar" style="background: ${escapeHtml(gameState.players?.[pid]?.color || '#666')}">${name(pid).charAt(0)}</div>
                            <div class="vote-target-name">${name(pid)}</div>
                            <div class="vote-count">crown them</div>
                        </div>
                    `).join('')}
                </div>`
            : `<p class="panel-sub" style="text-align:center">A tie — ${name(ft.leader)} must choose the winner.</p>`;
    }

    container.innerHTML = `
        <div class="player-grid" style="margin-top:0">${finalistCards}</div>
        ${questions ? `<div style="margin-top: 0.8rem">${questions}</div>` : ''}
        ${action}
    `;

    // Jury vote + tie-break taps
    container.querySelectorAll('.final-vote-target').forEach(el => {
        el.addEventListener('click', async () => {
            const finalistId = el.dataset.finalistId;
            hapticFeedback('heavy');
            await window.SurvivorGame?.safeApiCall('/final/vote', {
                gameId: window.SurvivorGame.localGameState.gameId,
                juryMemberId: myId, finalistId
            });
        });
    });
    container.querySelectorAll('.final-tiebreak-target').forEach(el => {
        el.addEventListener('click', async () => {
            const finalistId = el.dataset.finalistId;
            await window.SurvivorGame?.safeApiCall('/final/tie_break', {
                gameId: window.SurvivorGame.localGameState.gameId,
                leaderId: myId, chosenWinner: finalistId
            });
        });
    });

    // Leader "call for the vote" (questions -> voting)
    const beginBtn = container.querySelector('[data-action="beginFinalVote"]');
    if (beginBtn) {
        beginBtn.addEventListener('click', async () => {
            await window.SurvivorGame?.safeApiCall('/final/advance', {
                gameId: window.SurvivorGame.localGameState.gameId, phase: 'voting'
            });
        });
    }
}

/**
 * Game over — dawn breaks for one player.
 */
function renderGameOver(gameState) {
    const winnerInfo = document.getElementById('winnerInfo');
    if (!winnerInfo) return;

    const winner = gameState.winner;
    const winnerId = typeof winner === 'object' ? winner?.playerId : winner;
    const winnerName = (typeof winner === 'object' && winner?.playerName)
        || gameState.players?.[winnerId]?.name
        || gameState.finalTribal?.winner && gameState.players?.[gameState.finalTribal.winner]?.name
        || '';

    winnerInfo.textContent = winnerName ? winnerName : 'The tribe has spoken.';

    // Games with computer players never enter the Hall of Fame — the server
    // refuses, so don't offer the button.
    const hasBot = Object.values(gameState.players || {}).some(p => p.isBot);
    const recordBtn = document.querySelector('#gameOverActions [data-action="recordWinner"]');
    if (recordBtn) recordBtn.style.display = hasBot ? 'none' : '';
}

/**
 * Update UI based on current screen and game state
 */
function updateCurrentScreen(gameState) {
    if (!gameState) return;

    // The Hall of Fame and Settings are deliberate detours — a background
    // state update must not drag the player back into the game screens.
    if (currentScreen === 'leaderboardScreen' || currentScreen === 'settingsScreen') return;

    // Atmosphere + navigation follow the game phase
    setBodyMode(gameState);
    if (routeToPhase(gameState)) return;   // routing re-enters with the new screen

    // Always render phase guidance + header chips
    renderPhaseGuidance(gameState);
    updateGameInfo(gameState);

    // Reactive theft window (Sorry For You) — must render regardless of screen
    renderReactiveTheft(gameState);
    renderNullifierWindow(gameState);

    // Reward Challenge interactions (Do Or Die / Power Pair / Numbers Game)
    renderInteraction(gameState);

    // Update UI based on current screen
    switch (currentScreen) {
        case 'lobbyScreen':
            renderPlayerList(gameState);
            setupLeaderControls();
            break;
        case 'playingScreen':
            renderTurnInfo(gameState);
            updatePhaseIndicator(gameState);
            renderLivesTracker(gameState);
            renderPlacesPanel(gameState);
            renderPlayerHand(gameState);
            renderChallengePanel(gameState);
            break;
        case 'tribalAnnouncementScreen':
        case 'tribalAdvantageScreen':
        case 'tribalDiscussionScreen':
            renderTribalCeremony(gameState);
            break;
        case 'votingScreen':
            renderVoteTargets(gameState);
            updateVotingInfo(gameState);
            setupTribalLeaderControls(gameState, 'leaderVotingControls');
            break;
        case 'resultsScreen':
            renderVoteResults(gameState);
            setupTribalLeaderControls(gameState, 'leaderResultsControls');
            break;
        case 'immunityScreen':
            renderImmunityPlayers(gameState);
            setupTribalLeaderControls(gameState, 'leaderImmunityControls');
            break;
        case 'finalTribalScreen':
            renderFinalTribal(gameState);
            break;
        case 'gameOverScreen':
            renderGameOver(gameState);
            break;
        // Add other screens as needed
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// REACTIVE THEFT WINDOW — Sorry For You
// ─────────────────────────────────────────────────────────────────────────────
//
// When a steal targets a player holding Sorry For You, the server pauses the
// theft (`pending_theft.reactive_window_open`) until the defender decides.
// Before this existed the thief's tap appeared to do nothing and — since no UI
// ever resolved the window — the game wedged forever. Now:
//   · the DEFENDER gets a blocking raid dialog: play the card, or let it happen
//   · the THIEF gets a waiting banner naming who they're waiting on
//   · everyone else sees nothing

let reactiveTheftKey = null;

function renderReactiveTheft(gameState) {
    const pending = gameState?.pending_theft;
    const open = !!(pending && pending.reactive_window_open);
    const me = window.SurvivorGame?.localGameState?.playerId;
    const key = open ? `${pending.thiefId}:${pending.targetId}` : null;

    if (key === reactiveTheftKey) return;   // no change

    // Window closed (or changed): clear whatever we showed for the old one
    if (reactiveTheftKey !== null) {
        removeReactiveWaitBanner();
        const dialog = document.querySelector('.raid-dialog');
        if (dialog) hideModal();
    }
    reactiveTheftKey = key;
    if (!open) return;

    const thiefIds = pending.thiefIds || [pending.thiefId];
    const thiefNames = thiefIds
        .map(id => gameState.players?.[id]?.name || 'Someone');
    const thiefName = thiefNames.join(' and ');
    const targetName = gameState.players?.[pending.targetId]?.name || 'them';

    if (me === pending.targetId) {
        showRaidDialog(gameState, pending, thiefName);
    } else if (thiefIds.includes(me)) {
        showReactiveWaitBanner(targetName);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// THE IDOL NULLIFIER WINDOW
//
// A nullifier answers an idol, and the server refuses one until a target
// actually holds protection — so it can never be played early. Before this
// window existed the only thing between a holder and their card was how fast
// the Leader tapped, and the tally could land at any moment.
//
// Unlike the theft gate this does NOT hold the idol back: protection applies at
// once and the nullifier undoes it, because you have to see the shield to aim
// at it.
//
// Who gets prompted is decided from your OWN hand. The server keeps the list of
// holders under an underscore key and strips it before the state ships, so no
// client can learn who else is holding one.

let nullifierWindowKey = null;

function renderNullifierWindow(gameState) {
    const pending = gameState?.pending_nullifier;
    const open = !!(pending && pending.reactive_window_open);
    const me = window.SurvivorGame?.localGameState?.playerId;
    const key = open ? `${pending.idolPlayerId}:${pending.targetId}` : null;

    if (key === nullifierWindowKey) return;   // no change

    if (nullifierWindowKey !== null) {
        removeReactiveWaitBanner();
        if (document.querySelector('.nullifier-dialog')) hideModal();
    }
    nullifierWindowKey = key;
    if (!open) return;

    const hand = gameState.players?.[me]?.hand || [];
    const holdsNullifier = hand.some(c => c.type === 'idol_nullifier');
    const idolName = gameState.players?.[pending.idolPlayerId]?.name || 'Someone';
    const shieldedName = gameState.players?.[pending.targetId]?.name || idolName;

    if (holdsNullifier && me !== pending.idolPlayerId
        && !gameState.players?.[me]?.isEliminated) {
        showNullifierDialog(pending, idolName, shieldedName);
    } else if (me === pending.idolPlayerId) {
        showReactiveWaitBanner(shieldedName);
    }
}

function showNullifierDialog(pending, idolName, shieldedName) {
    const shieldedAnAlly = pending.targetId !== pending.idolPlayerId;
    const content = `
        <div class="nullifier-dialog">
            <div class="raid-mark">${icon('idol', 'raid-icon')}</div>
            <p class="raid-line">
                <strong>${escapeHtml(idolName)}</strong> played a Hidden Immunity Idol${
                    shieldedAnAlly ? ` for <strong>${escapeHtml(shieldedName)}</strong>` : ''
                }. Every vote against them is about to count for nothing.
            </p>
            <p class="picker-hint">You're holding an <em>Idol Nullifier</em> — play it now and
            the idol does nothing, or hold your peace and let it stand.</p>
            <div class="raid-actions">
                <button class="btn btn-primary touch-target" data-nullifier="play">
                    ${icon('x')} Nullify it
                </button>
                <button class="btn btn-secondary touch-target" data-nullifier="allow">
                    Let it stand
                </button>
            </div>
        </div>
    `;

    showModal(content, { title: 'An Idol Is Played', showClose: false });
    Haptics.trigger('warning');

    setTimeout(() => {
        const gameId = window.SurvivorGame?.localGameState?.gameId;
        const me = window.SurvivorGame?.localGameState?.playerId;
        document.querySelector('[data-nullifier="play"]')?.addEventListener('click', async () => {
            hideModal();
            // Through /immunity/block, NOT the generic play_card path. Only
            // this route closes the window, and until now the web played the
            // card the other way — which skipped the check that the target
            // actually holds protection, so a nullifier could be burned on
            // somebody holding nothing at all.
            await window.SurvivorNetwork.blockImmunity(gameId, pending.targetId);
        }, { once: true });
        document.querySelector('[data-nullifier="allow"]')?.addEventListener('click', async () => {
            hideModal();
            await window.SurvivorNetwork.declineNullifier(gameId, me);
        }, { once: true });
    }, 0);
}

/** Defender's blocking choice: burn the Sorry For You, or let the raid land. */
function showRaidDialog(gameState, pending, thiefName) {
    // The gate covers every taking the Guide names — say which card is doing it
    const source = pending.source && pending.source !== 'steal' ? pending.source : null;
    const raidLine = source
        ? `<strong>${escapeHtml(thiefName)}</strong> ${pending.thiefIds?.length > 1 ? 'are' : 'is'}
           coming for your cards — <em>${escapeHtml(source)}</em>.`
        : `<strong>${escapeHtml(thiefName)}</strong> is raiding your camp for a random card.`;
    const content = `
        <div class="raid-dialog">
            <div class="raid-mark">${icon('torch-out', 'raid-icon')}</div>
            <p class="raid-line">${raidLine}</p>
            <p class="picker-hint">You're holding <em>Sorry For You</em> — play it and they get
            nothing (each raider must discard a card), or let them take their prize.</p>
            <div class="raid-actions">
                <button class="btn btn-primary touch-target" data-raid="play">
                    ${icon('x')} Sorry for you!
                </button>
                <button class="btn btn-secondary touch-target" data-raid="allow">
                    Let them take it
                </button>
            </div>
        </div>
    `;

    // Don't fall back to "Camp Raid!" — that is a real card, and the plain
    // turn-opening steal is not it.
    showModal(content, { title: source ? `${source}!` : 'A Raid On Your Camp', showClose: false });
    Haptics.trigger('warning');

    setTimeout(() => {
        const playBtn = document.querySelector('[data-raid="play"]');
        const allowBtn = document.querySelector('[data-raid="allow"]');
        const gameId = window.SurvivorGame?.localGameState?.gameId;
        const myId = window.SurvivorGame?.localGameState?.playerId;

        if (playBtn) playBtn.addEventListener('click', async () => {
            const hand = window.SurvivorGame?.fullGameState?.players?.[myId]?.hand || [];
            const cardIdx = hand.findIndex(c => c.type === 'sorry_for_you');
            hideModal();
            if (cardIdx < 0) { showToast('Sorry For You is no longer in your hand', 'error'); return; }
            try {
                await window.SurvivorNetwork?.GameAPI.playReactiveCard(gameId, myId, cardIdx);
                Haptics.trigger('success');
            } catch (e) { showToast(e.message || 'Could not play Sorry For You', 'error'); }
        });

        if (allowBtn) allowBtn.addEventListener('click', async () => {
            hideModal();
            try {
                await window.SurvivorNetwork?.GameAPI.completeTheft(gameId);
            } catch (e) { showToast(e.message || 'Could not resolve the raid', 'error'); }
        });
    }, 0);
}

// ─────────────────────────────────────────────────────────────────────────────
// REWARD CHALLENGE INTERACTIONS — Do Or Die / Power Pair / Numbers Game
// ─────────────────────────────────────────────────────────────────────────────
//
// These mini-games are bluffing contests, so every pick comes from a real
// player. The server pauses the turn in game.interaction until everyone has
// acted; this renderer prompts whoever is due and shows everyone else who
// they're waiting on, then reveals the picks.

let interactionKey = null;

function renderInteraction(gameState) {
    const it = gameState?.interaction;
    const me = window.SurvivorGame?.localGameState?.playerId;
    const active = !!(it && it.phase);
    const awaitingMe = active && (it.awaiting || []).includes(me);
    const key = active
        ? `${it.type}:${it.phase}:${it.round}:${awaitingMe}:${(it.awaiting || []).length}`
        : null;

    if (key === interactionKey) return;

    // Clear whatever the previous interaction state showed
    if (interactionKey !== null) {
        removeInteractionBanner();
        if (document.querySelector('.interaction-ui')) hideModal();
    }
    interactionKey = key;
    if (!active) return;

    if (it.phase === 'picking' && awaitingMe) {
        showInteractionPickModal(gameState, it);
    } else if (it.phase === 'give' && awaitingMe) {
        showInteractionGiveModal(gameState, it);
    } else if (it.phase === 'choose_victim' && it.winnerId === me) {
        showInteractionVictimPicker(gameState, it);
    } else if (it.phase === 'complete') {
        showInteractionReveal(gameState, it);
    } else {
        showInteractionBanner(gameState, it);
    }
}

/** My secret pick: a throw (Do Or Die) or fingers (Power Pair / Numbers Game). */
function showInteractionPickModal(gameState, it) {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const me = window.SurvivorGame?.localGameState?.playerId;
    const act = (action, value) => window.SurvivorNetwork?.GameAPI
        .interactionAct(gameId, me, action, value)
        .catch(e => showToast(e.message || 'That did not land', 'error'));

    if (it.type === 'do_or_die') {
        const opponent = (it.participants || []).find(p => p !== me);
        const opponentName = gameState.players?.[opponent]?.name || 'your opponent';
        const content = `
            <div class="interaction-ui rps-selection">
                <p class="picker-hint">${escapeHtml(opponentName)} has already thrown.
                Make yours — winner steals 2 cards, a tie swaps 1 of your choice.</p>
                <div class="rps-row">
                    <button class="rps-option touch-target" data-pick="rock"><span class="rps-mark">●</span><span class="rps-label">Rock</span></button>
                    <button class="rps-option touch-target" data-pick="paper"><span class="rps-mark">▭</span><span class="rps-label">Paper</span></button>
                    <button class="rps-option touch-target" data-pick="scissors"><span class="rps-mark">✕</span><span class="rps-label">Scissors</span></button>
                </div>
            </div>
        `;
        showModal(content, { title: 'Do Or Die', showClose: false });
    } else {
        const top = it.type === 'power_pair' ? 3 : 5;
        const hint = it.type === 'power_pair'
            ? 'On the count of three — show 1, 2 or 3 fingers. Match exactly one other player to raid the third together.'
            : 'Show 1-5 fingers. The lowest number nobody else picked wins.';
        const fingers = Array.from({ length: top }, (_, i) => i + 1);
        const content = `
            <div class="interaction-ui finger-selection">
                <p class="picker-hint">${hint}${it.round > 1 ? ` (Round ${it.round})` : ''}</p>
                <div class="finger-row fingers-${top}">
                    ${fingers.map(n => `
                        <button class="finger-option touch-target" data-pick="${n}">
                            <span class="finger-num">${n}</span>
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
        showModal(content, { title: it.name || 'Reward Challenge', showClose: false });
    }

    setTimeout(() => {
        document.querySelectorAll('[data-pick]').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal();
                Haptics.trigger('select');
                act('pick', btn.dataset.pick);
            });
        });
    }, 0);
}

/** Tie swap / all-match discard: choose a card from MY hand to give up. */
function showInteractionGiveModal(gameState, it) {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const me = window.SurvivorGame?.localGameState?.playerId;
    const hand = gameState.players?.[me]?.hand || [];
    const swap = it.giveReason === 'swap';
    // The Vote Card never leaves your hand this way — only Control The Vote takes it.
    const offerable = hand
        .map((c, i) => ({ card: c, index: i }))
        .filter(({ card }) => card.type !== 'vote');

    const content = `
        <div class="interaction-ui cardname-selection">
            <p class="picker-hint">${swap
                ? 'A tie! Choose the card you hand to your opponent.'
                : 'All three matched — choose the card you discard.'}</p>
            <div class="cardname-grid">
                ${offerable.map(({ card, index }) => {
                    const info = window.SurvivorGame?.getCardInfo(card.type);
                    return `
                        <button class="cardname-option touch-target" data-give-index="${index}">
                            <span class="cardname-cat">${escapeHtml(CATEGORY_LABELS[info?.category] || info?.category || '')}</span>
                            <span class="cardname-name">${escapeHtml(info?.name || card.type)}</span>
                        </button>
                    `;
                }).join('')}
            </div>
        </div>
    `;
    showModal(content, { title: swap ? 'The Swap' : 'The Discard', showClose: false });

    setTimeout(() => {
        document.querySelectorAll('[data-give-index]').forEach(btn => {
            btn.addEventListener('click', () => {
                hideModal();
                window.SurvivorNetwork?.GameAPI
                    .interactionAct(gameId, me, 'give', parseInt(btn.dataset.giveIndex))
                    .catch(e => showToast(e.message || 'That did not land', 'error'));
            });
        });
    }, 0);
}

/** Numbers Game winner's spoils: pick who loses 2 random cards. */
function showInteractionVictimPicker(gameState, it) {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const me = window.SurvivorGame?.localGameState?.playerId;
    showPlayerPicker({
        title: "It's A Numbers Game",
        hint: 'Your number stood alone — steal 2 random cards from any player.',
        onPick: (victimId) => window.SurvivorNetwork?.GameAPI
            .interactionAct(gameId, me, 'steal_from', victimId)
            .catch(e => showToast(e.message || 'That did not land', 'error'))
    });
    // Mark the modal so renderInteraction can manage it
    setTimeout(() => document.querySelector('.target-selection')?.classList.add('interaction-ui'), 0);
}

/** The reveal: everyone's picks plus what happened, then back to the turn. */
function showInteractionReveal(gameState, it) {
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const me = window.SurvivorGame?.localGameState?.playerId;
    const picks = (it.lastRound && it.lastRound.picks) || it.picks || {};
    const throwMark = { rock: '●', paper: '▭', scissors: '✕' };

    const rows = Object.entries(picks).map(([pid, pick]) => {
        const player = gameState.players?.[pid];
        const shown = it.type === 'do_or_die'
            ? `${throwMark[pick] || ''} ${pick}` : `${pick}`;
        return `
            <li class="reveal-row">
                <span class="target-dot" style="background:${escapeHtml(player?.color || '#666')}"></span>
                <span class="reveal-name">${escapeHtml(player?.name || pid)}</span>
                <span class="reveal-pick">${escapeHtml(String(shown))}</span>
            </li>
        `;
    }).join('');

    const content = `
        <div class="interaction-ui reveal-ui">
            <ul class="reveal-list">${rows}</ul>
            <p class="reveal-outcome">${escapeHtml(it.prompt || '')}</p>
            <button class="btn btn-primary touch-target" data-interaction-dismiss>Continue</button>
        </div>
    `;
    showModal(content, { title: `${it.name} — The Reveal`, showClose: false });

    setTimeout(() => {
        document.querySelector('[data-interaction-dismiss]')?.addEventListener('click', () => {
            hideModal();
            window.SurvivorNetwork?.GameAPI.interactionAct(gameId, me, 'dismiss')
                .catch(() => {});   // already dismissed elsewhere is fine
        });
    }, 0);
}

/** Everyone not currently due: who the table is waiting on. */
function showInteractionBanner(gameState, it) {
    removeInteractionBanner();
    const names = (it.awaiting || [])
        .map(p => gameState.players?.[p]?.name || p).join(', ');
    const banner = document.createElement('div');
    banner.id = 'interactionBanner';
    banner.className = 'reactive-banner';
    banner.setAttribute('role', 'status');
    banner.innerHTML = `
        <span class="reactive-banner-flame">${icon('cards')}</span>
        <span><strong>${escapeHtml(it.name || 'Reward Challenge')}</strong> — waiting on
        ${escapeHtml(names || 'the tribe')}…</span>
    `;
    document.body.appendChild(banner);
}

function removeInteractionBanner() {
    document.getElementById('interactionBanner')?.remove();
}

/** Thief's non-blocking wait state while the defender decides. */
function showReactiveWaitBanner(targetName) {
    removeReactiveWaitBanner();
    const banner = document.createElement('div');
    banner.id = 'reactiveWaitBanner';
    banner.className = 'reactive-banner';
    banner.setAttribute('role', 'status');
    banner.innerHTML = `
        <span class="reactive-banner-flame">${icon('torch')}</span>
        <span>Waiting on <strong>${escapeHtml(targetName)}</strong> — they may play
        <em>Sorry For You</em>…</span>
    `;
    document.body.appendChild(banner);
}

function removeReactiveWaitBanner() {
    document.getElementById('reactiveWaitBanner')?.remove();
}

// ─────────────────────────────────────────────────────────────────────────────
// CAMP MENU — leaderboard, leave, and the full wipe
// ─────────────────────────────────────────────────────────────────────────────

/** Header menu: everything that isn't part of playing a turn. */
/**
 * The Story So Far — a slide-over reading of the server's event log, so a
 * player who was disconnected (or just distracted) can catch up.
 */
function openStory() {
    const drawer = document.getElementById('storyDrawer');
    const overlay = document.getElementById('storyOverlay');
    if (!drawer || !overlay) return;
    renderStoryList(window.SurvivorGame?.fullGameState);
    drawer.classList.add('open');
    overlay.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    overlay.addEventListener('click', closeStory, { once: true });
    drawer.querySelector('[data-action="closeStory"]')
        ?.addEventListener('click', closeStory, { once: true });
}

function closeStory() {
    const drawer = document.getElementById('storyDrawer');
    const overlay = document.getElementById('storyOverlay');
    drawer?.classList.remove('open');
    overlay?.classList.remove('open');
    drawer?.setAttribute('aria-hidden', 'true');
}

function renderStoryList(gameState) {
    const list = document.getElementById('storyList');
    if (!list) return;
    let events = gameState?.eventLog || [];
    if (window.SurvivorSettings?.get('historyLength') === '30') {
        events = events.slice(-30);
    }
    if (!events.length) {
        list.innerHTML = `<div class="story-empty">${icon('hourglass')}<p>Nothing has happened yet.<br>The island is quiet.</p></div>`;
        return;
    }
    // column-reverse flexbox shows the LAST child first — append in order
    list.innerHTML = events.map(ev => {
        let when = '';
        try {
            when = new Date(ev.t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        } catch (e) { /* no timestamp, no line */ }
        return `<div class="story-item">${when ? `<time>${when}</time>` : ''}${escapeHtml(ev.msg || '')}</div>`;
    }).join('');
}

function openCampMenu() {
    const inGame = !!window.SurvivorGame?.localGameState?.gameId;
    const gameId = window.SurvivorGame?.localGameState?.gameId;

    const content = `
        <div class="camp-menu">
            ${inGame ? `<p class="picker-hint">Fire <strong>${escapeHtml(gameId)}</strong></p>` : ''}
            <button class="camp-menu-item touch-target" data-camp="settings">
                ${icon('gear')}
                <span><strong>Settings</strong><em>Pacing, accessibility, your identity</em></span>
            </button>
            <button class="camp-menu-item touch-target" data-camp="leaderboard">
                ${icon('crown')}
                <span><strong>Hall of Fame</strong><em>Every Sole Survivor so far</em></span>
            </button>
            ${inGame ? `
                <button class="camp-menu-item touch-target" data-camp="story">
                    ${icon('eye')}
                    <span><strong>The Story So Far</strong><em>Everything that's happened this game</em></span>
                </button>
                <button class="camp-menu-item touch-target" data-camp="pace">
                    ${icon('hourglass')}
                    <span><strong>Game pace</strong><em>Bot speed, tribal rhythm — the Leader's call</em></span>
                </button>
                <button class="camp-menu-item touch-target" data-camp="leave">
                    ${icon('swap')}
                    <span><strong>Leave this game</strong><em>Just you — the game keeps going</em></span>
                </button>
                <button class="camp-menu-item camp-menu-danger touch-target" data-camp="wipe">
                    ${icon('torch-out')}
                    <span><strong>Burn it down</strong><em>Wipe the game for everyone and start fresh</em></span>
                </button>
            ` : ''}
        </div>
    `;

    showModal(content, { title: 'Camp' });

    setTimeout(() => {
        document.querySelector('[data-camp="settings"]')?.addEventListener('click', () => {
            hideModal();
            openSettings();
        });
        document.querySelector('[data-camp="leaderboard"]')?.addEventListener('click', () => {
            hideModal();
            showLeaderboard();
        });
        document.querySelector('[data-camp="story"]')?.addEventListener('click', () => {
            hideModal();
            setTimeout(openStory, 80);
        });
        document.querySelector('[data-camp="pace"]')?.addEventListener('click', () => {
            hideModal();
            setTimeout(showGamePaceSheet, 80);
        });
        document.querySelector('[data-camp="leave"]')?.addEventListener('click', () => {
            hideModal();
            window.SurvivorGame?.leaveGame();
        });
        document.querySelector('[data-camp="wipe"]')?.addEventListener('click', () => {
            hideModal();
            // Destructive and it hits everyone's phone — make them mean it.
            setTimeout(() => showConfirm(
                'Burn this game down for everyone? Every player is sent back to the start screen and the game is gone for good.',
                () => window.SurvivorGame?.wipeGame()
            ), 120);
        });
    }, 0);
}

/** Game pace sheet — per-game settings, enforced Leader-only by the server. */
function showGamePaceSheet() {
    const gameState = window.SurvivorGame?.fullGameState || {};
    const settings = gameState.settings
        || { botPace: 'normal', tribalPace: 'normal', botStyle: 'normal' };
    const ROWS = [
        ['botPace', 'Computer player speed',
            [['chill', 'Chill'], ['normal', 'Normal'], ['fast', 'Fast']]],
        ['tribalPace', 'Tribal ceremony pace',
            [['normal', 'Normal'], ['relaxed', 'Relaxed'], ['tv', 'TV drama']]],
        ['botStyle', 'Computer player style',
            [['chill', 'Chill'], ['normal', 'Normal'], ['cutthroat', 'Cutthroat']]],
    ];
    const content = `
        <div class="cardname-selection">
            <p class="picker-hint">The Leader sets the pace for the whole tribe.</p>
            ${ROWS.map(([key, label, opts]) => `
                <div class="settings-row"><label>${label}</label>
                    <div class="seg-group">${opts.map(([v, l]) =>
                        `<button class="seg-btn touch-target" data-pace-key="${key}"
                                 data-pace-value="${v}"
                                 aria-pressed="${(settings[key] || 'normal') === v}">${l}</button>`
                    ).join('')}</div>
                </div>`).join('')}
        </div>
    `;
    showModal(content, { title: 'Game pace' });

    setTimeout(() => {
        document.querySelectorAll('[data-pace-key]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const gameId = window.SurvivorGame?.localGameState?.gameId;
                const playerId = window.SurvivorGame?.localGameState?.playerId;
                hideModal();
                const result = await window.SurvivorNetwork?.GameAPI.updateGameSettings(
                    gameId, playerId,
                    { [btn.dataset.paceKey]: btn.dataset.paceValue });
                // apiCall toasts the success message; only a refusal needs saying
                if (!result?.success && result?.message) showToast(result.message, 'error');
            });
        });
    }, 0);
}

/** Hall of Fame — the winners recorded in winners.json. */
async function showLeaderboard() {
    hofEditMode = false;
    const editBtn = document.getElementById('hofEditBtn');
    if (editBtn) editBtn.textContent = 'Edit the record';
    const list = document.getElementById('leaderboardList');
    if (list) list.innerHTML = `<p class="picker-hint">Reading the tribe's history…</p>`;
    showScreen('leaderboardScreen');
    document.getElementById('phaseGuidance')?.style.setProperty('display', 'none');

    let winners = [];
    try {
        const response = await fetch('/api/winners', { cache: 'no-store' });
        if (response.ok) winners = await response.json();
    } catch (error) {
        console.warn('Could not load winners:', error);
        if (list) list.innerHTML = `<p class="picker-hint">Couldn't reach the island's records.</p>`;
        return;
    }

    if (!list) return;
    if (!Array.isArray(winners) || !winners.length) {
        list.innerHTML = `
            <div class="hof-empty">
                ${icon('torch-out', 'hof-empty-icon')}
                <p class="reveal-outcome">No Sole Survivor yet.</p>
                <p class="picker-hint">Win a game and your name is carved here.</p>
            </div>
        `;
        return;
    }

    const ranked = [...winners].sort((a, b) =>
        (b.victories || 0) - (a.victories || 0) ||
        String(a.winner_name).localeCompare(String(b.winner_name))
    );
    const most = ranked[0].victories || 0;

    list.innerHTML = `<ol class="hof-list">${ranked.map((w, i) => {
        const wins = w.victories || 0;
        const latest = (w.dates && w.dates[0]) ? w.dates[0] : '';
        return `
            <li class="hof-row ${i === 0 && most > 0 ? 'hof-champion' : ''}">
                <span class="hof-rank">${i + 1}</span>
                <span class="hof-name">
                    ${escapeHtml(w.winner_name || 'Unknown')}
                    ${latest ? `<em class="hof-date">last won ${escapeHtml(latest)}</em>` : ''}
                </span>
                <span class="hof-wins">
                    ${i === 0 && most > 0 ? icon('crown', 'hof-crown') : ''}
                    <strong>${wins}</strong><em>${wins === 1 ? 'win' : 'wins'}</em>
                </span>
            </li>
        `;
    }).join('')}</ol>`;
}

// ── Hall of Fame editing ────────────────────────────────────────────────────
// The record is a list of individual wins (name + date). Anyone at the fire
// can tend it: fix a name, correct a date, add a game played off-app.

let hofEditMode = false;

function toggleLeaderboardEdit() {
    hofEditMode = !hofEditMode;
    if (hofEditMode) renderLeaderboardEdit();
    else showLeaderboard();
}

async function renderLeaderboardEdit() {
    const list = document.getElementById('leaderboardList');
    const editBtn = document.getElementById('hofEditBtn');
    if (editBtn) editBtn.textContent = 'Done';
    if (list) list.innerHTML = `<p class="picker-hint">Reading the tribe's history…</p>`;

    let records = [];
    try {
        const response = await fetch('/api/winners/records', { cache: 'no-store' });
        if (response.ok) records = await response.json();
    } catch (error) {
        console.warn('Could not load winner records:', error);
    }
    if (!list) return;
    if (!Array.isArray(records)) records = [];

    const sorted = [...records].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
    const rows = sorted.map(r => `
        <li class="hof-row hof-edit-row" data-record-id="${escapeHtml(r.id || '')}">
            <span class="hof-name">
                ${escapeHtml(r.winner_name || 'Unknown')}
                <em class="hof-date">${escapeHtml(r.date || 'no date')}</em>
            </span>
            <button class="hof-icon-btn" data-hof="edit" aria-label="Edit this win">${icon('pencil')}</button>
            <button class="hof-icon-btn hof-icon-danger" data-hof="delete" aria-label="Delete this win">${icon('x')}</button>
        </li>
    `).join('');

    list.innerHTML = `
        <p class="picker-hint">Each row is one win. Tap ${icon('pencil')} to fix a name or date.</p>
        <ol class="hof-list">${rows || ''}</ol>
        ${rows ? '' : `<p class="picker-hint">No wins recorded yet.</p>`}
        <button class="btn btn-secondary btn-enhanced touch-target" id="hofAddBtn">
            ${icon('crown')} Add a win
        </button>
    `;

    list.querySelectorAll('[data-hof="edit"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.closest('[data-record-id]').dataset.recordId;
            const rec = records.find(r => r.id === id);
            if (rec) showWinnerForm(rec);
        });
    });
    list.querySelectorAll('[data-hof="delete"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const id = btn.closest('[data-record-id]').dataset.recordId;
            const rec = records.find(r => r.id === id);
            showConfirm(
                `Strike ${rec?.winner_name || 'this win'} (${rec?.date || 'no date'}) from the record?`,
                async () => {
                    await hofApi('/api/winners/delete', { id });
                    renderLeaderboardEdit();
                }
            );
        });
    });
    document.getElementById('hofAddBtn')?.addEventListener('click', () => showWinnerForm(null));
}

/** Add (record = null) or edit one win. */
function showWinnerForm(record) {
    const isNew = !record;
    const today = new Date().toISOString().slice(0, 10);
    showModal(`
        <div class="form-group">
            <label for="hofNameInput">Winner</label>
            <input type="text" id="hofNameInput" class="form-input" maxlength="50"
                   value="${escapeHtml(record?.winner_name || '')}" placeholder="Who claimed the title?">
        </div>
        <div class="form-group">
            <label for="hofDateInput">Date won</label>
            <input type="date" id="hofDateInput" class="form-input"
                   value="${escapeHtml(record?.date || today)}">
        </div>
        <button class="btn btn-primary btn-enhanced touch-target" id="hofSaveBtn">
            ${isNew ? 'Carve it in' : 'Save'}
        </button>
    `, { title: isNew ? 'Add a win' : 'Edit this win' });

    setTimeout(() => {
        document.getElementById('hofSaveBtn')?.addEventListener('click', async () => {
            const name = document.getElementById('hofNameInput')?.value.trim();
            const date = document.getElementById('hofDateInput')?.value.trim();
            if (!name) { showToast('A winner needs a name', 'warning'); return; }
            if (!date) { showToast('A win needs a date', 'warning'); return; }
            const body = isNew
                ? { winner_name: name, date }
                : { id: record.id, winner_name: name, date };
            const ok = await hofApi(isNew ? '/api/winners/add' : '/api/winners/update', body);
            if (ok) {
                hideModal();
                renderLeaderboardEdit();
            }
        });
        document.getElementById('hofNameInput')?.focus();
    }, 60);
}

/** Small POST helper for the winners endpoints. Returns true on success. */
async function hofApi(path, body) {
    try {
        const response = await fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.success === false) {
            showToast(result.message || 'That did not take', 'error');
            return false;
        }
        if (result.message) showToast(result.message, 'success');
        return true;
    } catch (error) {
        showToast('Could not reach the island', 'error');
        return false;
    }
}

/** Back out of the Hall of Fame to wherever makes sense. */
function leaveLeaderboard() {
    hofEditMode = false;
    const gameState = window.SurvivorGame?.fullGameState;
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    if (gameId && gameState?.phase) {
        // Land somewhere real first — updateCurrentScreen ignores calls made from
        // the Hall of Fame on purpose — then let the phase router refine it.
        showScreen(gameState.phase === 'lobby' ? 'lobbyScreen' : 'playingScreen');
        updateCurrentScreen(gameState);
    } else {
        showScreen('startScreen');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS SCREEN
// ─────────────────────────────────────────────────────────────────────────────

const PLAYER_COLORS = [
    ['#FF6B6B', 'Red'], ['#4ECDC4', 'Teal'], ['#45B7D1', 'Blue'], ['#96CEB4', 'Sage'],
    ['#FFEAA7', 'Yellow'], ['#DDA0DD', 'Plum'], ['#98D8C8', 'Mint'], ['#F7DC6F', 'Gold'],
];

function settingsSpec() {
    return [
        { title: 'Reading & pacing', rows: [
            { key: 'toastPace', label: 'Message speed', type: 'seg',
              sub: 'How long announcements stay on screen',
              options: [['quick', 'Quick'], ['normal', 'Normal'], ['relaxed', 'Relaxed'], ['pinned', 'Until tapped']],
              onChange: () => showToast('Messages will stay on screen this long', 'info') },
            { key: 'defaultBotPace', label: 'Computer player speed', type: 'seg',
              sub: 'For games you create',
              options: [['chill', 'Chill'], ['normal', 'Normal'], ['fast', 'Fast']] },
            { key: 'defaultTribalPace', label: 'Tribal ceremony pace', type: 'seg',
              sub: 'For games you create — slower leaves room to play advantage cards',
              options: [['normal', 'Normal'], ['relaxed', 'Relaxed'], ['tv', 'TV drama']] },
            { key: 'defaultBotStyle', label: 'Computer player style', type: 'seg',
              sub: 'For games you create',
              options: [['chill', 'Chill'], ['normal', 'Normal'], ['cutthroat', 'Cutthroat']] },
        ]},
        { title: 'Accessibility', rows: [
            { key: 'textSize', label: 'Text size', type: 'seg',
              options: [['normal', 'Normal'], ['large', 'Large'], ['xl', 'Extra large']] },
            { key: 'reduceMotion', label: 'Reduce motion', type: 'seg',
              options: [['auto', 'Match device'], ['on', 'On'], ['off', 'Off']] },
            { key: 'haptics', label: 'Vibration', type: 'toggle' },
            { key: 'sound', label: 'Sound', type: 'toggle',
              sub: 'Master switch — the narrator has its own mute too' },
        ]},
        { title: 'Table rules', rows: [
            { key: 'confirmVotes', label: 'Confirm before casting a vote', type: 'toggle' },
            { key: 'confirmSteals', label: 'Confirm before stealing', type: 'toggle' },
            { key: 'defaultDeckMode', label: 'Default deck', type: 'seg',
              options: [['official', 'Official'], ['extended', 'Extended']] },
            { key: 'defaultExpansion', label: 'Add Rocks challenges by default', type: 'toggle' },
        ]},
        { title: 'You', rows: [
            { key: 'identityName', label: 'Your name', type: 'text',
              sub: 'Prefills the join form on this device' },
            { key: 'identityColor', label: 'Your buff', type: 'colors' },
            // Checked here as well as on the server: a bad value would otherwise
            // sit in settings and fail the NEXT join with a message nobody would
            // connect back to this box.
            { key: 'discordUserId', label: 'Discord user ID', type: 'text',
              placeholder: '123456789012345678',
              sub: 'Optional — lets the island follow you into Discord voice. In Discord: Settings → Advanced → turn on Developer Mode, then right-click (or long-press) your own name and choose Copy User ID.',
              validate: (value) => (!value || /^[0-9]{15,25}$/.test(value)) ? null
                  : "A Discord user ID is all digits — copy it with Copy User ID rather than typing your username" },
        ]},
        { title: 'Device', rows: [
            { key: 'keepAwake', label: 'Keep the screen awake during games', type: 'toggle' },
            { key: 'turnNotifications', label: 'Notify me on my turn', type: 'toggle',
              sub: 'On iPhone, add the app to your Home Screen first',
              onChange: (value) => handleTurnNotificationsToggle(value) },
            { key: 'historyLength', label: 'Story-so-far length', type: 'seg',
              options: [['30', 'Last 30'], ['all', 'Everything']] },
        ]},
    ];
}

function renderSettingsRow(row) {
    const S = window.SurvivorSettings;
    const value = S.get(row.key);
    const sub = row.sub ? `<span class="row-sub">${escapeHtml(row.sub)}</span>` : '';
    let control = '';

    if (row.type === 'seg') {
        control = `<div class="seg-group" role="group" aria-label="${escapeHtml(row.label)}">` +
            row.options.map(([v, label]) =>
                `<button class="seg-btn touch-target" data-set-key="${row.key}" data-set-value="${v}"
                         aria-pressed="${String(value) === v}">${escapeHtml(label)}</button>`).join('') +
            `</div>`;
    } else if (row.type === 'toggle') {
        // .checkbox-row styles a bare checkbox as the app's pill switch
        control = `<label class="checkbox-row" style="min-height:0">
            <input type="checkbox" data-set-key="${row.key}" data-set-toggle="1" ${value ? 'checked' : ''}>
        </label>`;
    } else if (row.type === 'text') {
        control = `<input type="text" class="form-input" data-set-key="${row.key}" data-set-text="1"
                          value="${escapeHtml(value || '')}" autocomplete="off"
                          placeholder="${escapeHtml(row.placeholder || '')}">`;
    } else if (row.type === 'colors') {
        control = `<div class="seg-group">` + PLAYER_COLORS.map(([hex, name]) =>
            `<button class="color-btn touch-target" data-set-key="${row.key}" data-set-value="${hex}"
                     style="background:${hex}" role="radio" aria-label="${name}"
                     aria-checked="${value === hex}"></button>`).join('') +
            `<button class="seg-btn touch-target" data-set-key="${row.key}" data-set-value=""
                     aria-pressed="${!value}">Any</button></div>`;
    }

    return `<div class="settings-row"><label>${escapeHtml(row.label)}${sub}</label>${control}</div>`;
}

function renderSettingsScreen() {
    const body = document.getElementById('settingsBody');
    if (!body || !window.SurvivorSettings) return;
    const inGame = !!window.SurvivorGame?.localGameState?.gameId;
    const version = window.SurvivorGame?.APP_VERSION || '';

    body.innerHTML = settingsSpec().map(section => `
        <div class="settings-section">
            <h3>${escapeHtml(section.title)}</h3>
            ${section.rows.map(renderSettingsRow).join('')}
        </div>
    `).join('') + `
        <div class="settings-section">
            <h3>Housekeeping</h3>
            ${inGame ? `
            <div class="settings-row"><label>Leave this game<span class="row-sub">Just you — the game keeps going</span></label>
                <button class="seg-btn touch-target" data-housekeeping="leave">Leave</button></div>` : ''}
            <div class="settings-row"><label>Forget this island<span class="row-sub">Clears the island code and any saved game on this device</span></label>
                <button class="seg-btn settings-danger touch-target" data-housekeeping="forget">Forget</button></div>
            <div class="settings-row"><label>Reset settings<span class="row-sub">Everything on this screen back to normal</span></label>
                <button class="seg-btn touch-target" data-housekeeping="reset">Reset</button></div>
            <p class="settings-about">Survivor: The Tribe Has Spoken — companion${version ? ` · v${version}` : ''}</p>
        </div>
    `;

    bindSettingsControls(body);
}

function bindSettingsControls(body) {
    const S = window.SurvivorSettings;

    body.querySelectorAll('[data-set-value]').forEach(btn => {
        btn.addEventListener('click', () => {
            const key = btn.dataset.setKey;
            S.set(key, btn.dataset.setValue);
            findSettingsRowOnChange(key)?.(btn.dataset.setValue);
            renderSettingsScreen();
        });
    });

    body.querySelectorAll('[data-set-toggle]').forEach(input => {
        input.addEventListener('change', () => {
            const key = input.dataset.setKey;
            S.set(key, input.checked);
            findSettingsRowOnChange(key)?.(input.checked);
        });
    });

    body.querySelectorAll('[data-set-text]').forEach(input => {
        input.addEventListener('change', () => {
            const key = input.dataset.setKey;
            const value = input.value.trim();
            const error = findSettingsRow(key)?.validate?.(value);
            if (error) {
                showToast(error, 'warning');
                input.value = S.get(key) || '';   // put the last good value back
                return;
            }
            S.set(key, value);
        });
    });

    body.querySelector('[data-housekeeping="leave"]')?.addEventListener('click', () => {
        showConfirm('Leave this game? The tribe plays on without you.',
            () => window.SurvivorGame?.leaveGame());
    });
    body.querySelector('[data-housekeeping="forget"]')?.addEventListener('click', () => {
        showConfirm('Forget this island? The code and any saved game on this device are cleared.',
            () => {
                window.SurvivorGame?.wipeLocalGame?.();
                try { localStorage.removeItem('survivorState'); } catch (e) {}
                document.cookie = 'survivor_access=; Max-Age=0; path=/';
                location.reload();
            });
    });
    body.querySelector('[data-housekeeping="reset"]')?.addEventListener('click', () => {
        S.reset();
        renderSettingsScreen();
        showToast('Settings are back to normal', 'success');
    });
}

/** The spec row for a settings key — carries onChange, validate, options, ... */
function findSettingsRow(key) {
    for (const section of settingsSpec()) {
        for (const row of section.rows) {
            if (row.key === key) return row;
        }
    }
    return null;
}

function findSettingsRowOnChange(key) {
    return findSettingsRow(key)?.onChange || null;
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = window.atob(base64);
    return Uint8Array.from([...raw].map(ch => ch.charCodeAt(0)));
}

/** Enable/disable turn notifications: permission → subscribe → tell the server. */
async function handleTurnNotificationsToggle(on) {
    const S = window.SurvivorSettings;
    const revert = (message) => {
        S.set('turnNotifications', false);
        if (message) showToast(message, 'warning');
        renderSettingsScreen();
    };

    const gameId = window.SurvivorGame?.localGameState?.gameId;
    const playerId = window.SurvivorGame?.localGameState?.playerId;

    if (!on) {
        try {
            const reg = await navigator.serviceWorker?.ready;
            const sub = await reg?.pushManager.getSubscription();
            if (sub) await sub.unsubscribe();
        } catch (e) { /* local unsubscribe is best-effort */ }
        if (gameId && playerId) {
            window.SurvivorNetwork?.GameAPI.pushUnsubscribe(gameId, playerId);
        }
        return;
    }

    if (!('serviceWorker' in navigator) || !('PushManager' in window)
            || !('Notification' in window)) {
        return revert("This browser can't do notifications — on iPhone, add the app to your Home Screen first");
    }
    if (!gameId || !playerId) {
        return revert('Join a game first, then flip this on');
    }

    try {
        const keyResult = await window.SurvivorNetwork?.GameAPI.pushPubkey();
        if (!keyResult?.key) {
            return revert("Notifications aren't set up on this server");
        }
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            return revert('Notifications stay off until the browser allows them');
        }
        const reg = await navigator.serviceWorker.ready;
        const subscription = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(keyResult.key)
        });
        const result = await window.SurvivorNetwork?.GameAPI.pushSubscribe(
            gameId, playerId, subscription.toJSON());
        if (!result?.success) {
            return revert(result?.message || 'The server refused the subscription');
        }
        // apiCall already toasted the server's confirmation
    } catch (error) {
        console.warn('Push subscribe failed:', error);
        return revert('Could not turn notifications on');
    }
}

function openSettings() {
    showScreen('settingsScreen');
    document.getElementById('phaseGuidance')?.style.setProperty('display', 'none');
    renderSettingsScreen();
}

function leaveSettings() {
    const gameState = window.SurvivorGame?.fullGameState;
    const gameId = window.SurvivorGame?.localGameState?.gameId;
    if (gameId && gameState?.phase) {
        showScreen(gameState.phase === 'lobby' ? 'lobbyScreen' : 'playingScreen');
        updateCurrentScreen(gameState);
    } else {
        showScreen('startScreen');
    }
}

/** Leader-only control strips on the tribal screens. */
function setupTribalLeaderControls(gameState, elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const leaderId = gameState.currentVote?.councilLeaderId;
    const iAmLeader = leaderId && leaderId === window.SurvivorGame?.localGameState?.playerId;
    el.style.display = iAmLeader ? 'flex' : 'none';
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

    // The copied text is a link that walks a friend straight onto the island —
    // opening it prefills the join form with this code.
    const joinLink = `${window.location.origin}/?join=${encodeURIComponent(gameId)}`;
    try {
        await navigator.clipboard.writeText(joinLink);
        showToast('Join link copied!', 'success');
        hapticFeedback('success');
    } catch (error) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = joinLink;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showToast('Join link copied!', 'success');
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

    const shareUrl = `${window.location.origin}/?join=${encodeURIComponent(gameId)}`;
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

/**
 * Screen reader announcement
 */
function announce(message) {
    const announcer = document.getElementById('srAnnouncer');
    if (announcer) {
        announcer.textContent = '';
        // Force reflow so screen readers pick up the change
        void announcer.offsetHeight;
        announcer.textContent = message;
    }
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
    renderReactiveTheft,
    renderNullifierWindow,
    renderInteraction,
    beginCardPlay,
    openCampMenu,
    openSettings,
    leaveSettings,
    openStory,
    closeStory,
    showLeaderboard,
    leaveLeaderboard,
    toggleLeaderboardEdit,
    renderLives,
    renderLivesTracker,
    renderPlacesPanel,
    movePlaceTo,
    placeLabel,
    renderChallengePanel,
    renderTribalCeremony,
    renderFinalTribal,
    icon,

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

    // Accessibility
    announce,

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