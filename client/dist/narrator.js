/**
 * Survivor Game - Narrator System
 * Creates an immersive TV show-like experience with dramatic commentary,
 * typing effects, sound cues, and celebration animations.
 */

// ─────────────────────────────────────────────────────────────────────────────
// NARRATOR COMMENTARY TEMPLATES
// ─────────────────────────────────────────────────────────────────────────────

const NARRATOR_TEMPLATES = {
    // Game lifecycle
    game_start: [
        "The tribe has gathered. {count} castaways. Only one will be named... the Sole Survivor.",
        "{count} players enter. One will outwit, outplay, and outlast all others.",
        "Welcome to Survivor! {count} players, countless betrayals ahead. Let the game begin."
    ],
    game_start_playing: [
        "The game is afoot! May the craftiest castaway prevail.",
        "Alliances will form. Alliances will crumble. Let's play Survivor!"
    ],

    // Turn events
    turn_start: [
        "{player}, it's your move. Choose wisely.",
        "The spotlight falls on {player}. What will they do?",
        "{player} steps up. The tribe watches closely."
    ],
    turn_start_self: [
        "It's YOUR turn! Steal, play a card if you want, then draw.",
        "Your move! Remember: Steal first, then play (optional), then draw."
    ],

    // Stealing
    steal_success: [
        "{thief} reaches into {victim}'s bag and pulls out... a card!",
        "A bold move! {thief} steals from {victim}!",
        "{thief} makes their move, snatching a card from {victim}!"
    ],
    steal_blocked: [
        "{victim} saw it coming! The steal attempt is blocked!",
        "Not so fast! {victim} protects their cards!"
    ],

    // Card plays
    card_play: [
        "{player} reveals: {cardName}!",
        "{player} plays {cardName}! The game shifts...",
        "A dramatic move! {player} unleashes {cardName}!"
    ],
    card_play_immunity_idol: [
        "WAIT! {player} reaches into their pocket... 'I'd like to play this!' AN IMMUNITY IDOL!",
        "{player} stands: 'Before you read the votes... I'm playing my idol!'",
        "The tribe gasps! {player} reveals an Immunity Idol!"
    ],
    card_play_idol_nullifier: [
        "BUT WAIT! {player} played an Idol Nullifier! That idol... has no power here.",
        "Plot twist! {player}'s Nullifier renders the idol useless!",
        "The ultimate counter! {player}'s Nullifier strikes!"
    ],
    card_play_steal_vote: [
        "{player} steals {target}'s vote! The power shifts!",
        "Democracy disrupted! {player} takes control of {target}'s vote!"
    ],
    card_play_extra_vote: [
        "{player} reveals an Extra Vote! Their voice counts twice tonight!",
        "Double the power! {player} will cast two votes!"
    ],

    // Tribal Council
    tribal_drawn: [
        "A Tribal Council card! The torches are lit. Someone's going home tonight.",
        "TRIBAL COUNCIL! Grab your torches, it's time to vote.",
        "The dreaded Tribal Council card appears! Someone's torch will be snuffed."
    ],
    tribal_start: [
        "Come on in, guys! Welcome to Tribal Council.",
        "Fire represents your life in this game. When your fire's gone, so are you.",
        "Behind each of you is a torch. In this game, fire represents life."
    ],
    tribal_advantage_phase: [
        "Before we vote... does anyone have an advantage to play?",
        "This is your last chance to play any tribal advantages.",
        "The floor is open. Any advantages?"
    ],
    tribal_discussion: [
        "Let's talk about what happened since last tribal.",
        "The tribe discusses strategy. Alliances are tested.",
        "Whispers and glances. Who's really with who?"
    ],
    tribal_voting_start: [
        "It is time to vote. {player}, you're up.",
        "The moment of truth. Time to vote.",
        "One by one, cast your votes. The tribe will decide."
    ],
    vote_cast: [
        "{player} has voted.",
        "{player} returns from voting.",
        "Another vote is cast..."
    ],
    tribal_immunity_phase: [
        "If anyone has a Hidden Immunity Idol and wants to play it, now is the time.",
        "Last chance... any idols?",
        "Before I read the votes... any immunity idols?"
    ],

    // Vote reveal
    vote_reveal_start: [
        "I'll read the votes...",
        "Once the votes are read, the decision is final.",
        "Let's see where the votes fell..."
    ],
    vote_reveal_vote: [
        "...{target}.",
        "{count} vote{s} {target}.",
        "That's {count} for {target}."
    ],
    vote_reveal_tie: [
        "We have a TIE! {player1} and {player2}!",
        "Deadlocked! {player1} and {player2} are tied!",
        "This changes everything! A tie between {player1} and {player2}!"
    ],

    // Elimination
    elimination: [
        "The tribe has spoken. {player}, your torch has been snuffed.",
        "{player}, the tribe has spoken. Time to go.",
        "It's official. {player}, bring me your torch."
    ],
    elimination_jury: [
        "{player}, you will now become a member of the jury.",
        "You're out, but not done. {player} joins the jury.",
        "{player} takes their seat on the jury. They'll help decide the winner."
    ],

    // Final Tribal Council
    final_tribal_start: [
        "You've made it to the Final Tribal Council! The power now shifts to the jury.",
        "Congratulations, final {count}! The jury will now decide your fate.",
        "From {total} players to {count}. The jury holds your destiny."
    ],
    final_tribal_question: [
        "Jury, you may now address the finalists.",
        "The time has come for the jury to speak.",
        "Final {count}, defend your game to the jury."
    ],
    final_tribal_voting: [
        "Jury, it's time to vote for a WINNER.",
        "This time, you're voting FOR someone to win.",
        "Cast your vote for the Sole Survivor."
    ],

    // Winner
    winner: [
        "The winner of Survivor... {player}! THE SOLE SURVIVOR!",
        "By a vote of {votes}, {player} is the SOLE SURVIVOR!",
        "Congratulations {player}! You've outwitted, outplayed, and outlasted them all!"
    ],

    // Miscellaneous
    player_joined: [
        "{player} joins the tribe!",
        "Welcome {player} to the game!",
        "A new castaway appears: {player}!"
    ],
    player_left: [
        "{player} has left the game.",
        "{player} quits! The tribe is shocked.",
        "We've lost {player}..."
    ],
    game_reset: [
        "The game has been reset. A fresh start for everyone.",
        "All is forgiven. The game begins anew.",
        "Reset! The past is forgotten. Let's play again."
    ]
};

// ─────────────────────────────────────────────────────────────────────────────
// SOUND MANAGER
// ─────────────────────────────────────────────────────────────────────────────

const SoundManager = {
    muted: localStorage.getItem('survivorSoundMuted') === 'true',
    sounds: {},
    audioContext: null,

    init() {
        // Use Web Audio API to generate sounds (no external files needed)
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        } catch (e) {
            console.warn('Web Audio API not supported');
        }
    },

    toggle() {
        this.muted = !this.muted;
        localStorage.setItem('survivorSoundMuted', this.muted);
        return !this.muted;
    },

    isMuted() {
        return this.muted;
    },

    // Generate sounds using Web Audio API
    play(soundType) {
        if (this.muted || !this.audioContext) return;

        try {
            const ctx = this.audioContext;
            const now = ctx.currentTime;

            switch (soundType) {
                case 'tribal_gong':
                    this._playGong(ctx, now);
                    break;
                case 'torch_snuff':
                    this._playSnuff(ctx, now);
                    break;
                case 'vote_reveal':
                    this._playDrum(ctx, now);
                    break;
                case 'card_play':
                    this._playWhoosh(ctx, now);
                    break;
                case 'victory':
                    this._playVictory(ctx, now);
                    break;
                case 'steal':
                    this._playSwoosh(ctx, now);
                    break;
                case 'notification':
                    this._playNotification(ctx, now);
                    break;
            }
        } catch (e) {
            console.warn('Sound play failed:', e);
        }
    },

    // Deep gong for tribal council
    _playGong(ctx, now) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(80, now);
        osc.frequency.exponentialRampToValueAtTime(40, now + 2);
        gain.gain.setValueAtTime(0.5, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 2);
        osc.start(now);
        osc.stop(now + 2);
    },

    // Sizzle/whoosh for torch snuff
    _playSnuff(ctx, now) {
        const bufferSize = ctx.sampleRate * 1.5;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (ctx.sampleRate * 0.3));
        }
        const noise = ctx.createBufferSource();
        const filter = ctx.createBiquadFilter();
        const gain = ctx.createGain();
        noise.buffer = buffer;
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(3000, now);
        filter.frequency.exponentialRampToValueAtTime(200, now + 1.5);
        gain.gain.setValueAtTime(0.4, now);
        noise.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);
        noise.start(now);
    },

    // Dramatic drum beat for vote reveal
    _playDrum(ctx, now) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(150, now);
        osc.frequency.exponentialRampToValueAtTime(50, now + 0.2);
        gain.gain.setValueAtTime(0.6, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.3);
    },

    // Swoosh for card play
    _playWhoosh(ctx, now) {
        const bufferSize = ctx.sampleRate * 0.3;
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
            const t = i / ctx.sampleRate;
            data[i] = (Math.random() * 2 - 1) * Math.sin(t * Math.PI) * 0.5;
        }
        const noise = ctx.createBufferSource();
        const filter = ctx.createBiquadFilter();
        noise.buffer = buffer;
        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(1000, now);
        filter.Q.setValueAtTime(1, now);
        noise.connect(filter);
        filter.connect(ctx.destination);
        noise.start(now);
    },

    // Victory fanfare
    _playVictory(ctx, now) {
        const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
        notes.forEach((freq, i) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.frequency.setValueAtTime(freq, now);
            osc.type = 'triangle';
            gain.gain.setValueAtTime(0, now + i * 0.15);
            gain.gain.linearRampToValueAtTime(0.3, now + i * 0.15 + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.15 + 0.5);
            osc.start(now + i * 0.15);
            osc.stop(now + i * 0.15 + 0.5);
        });
    },

    // Quick swoosh for stealing
    _playSwoosh(ctx, now) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.exponentialRampToValueAtTime(200, now + 0.15);
        osc.type = 'sawtooth';
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
        osc.start(now);
        osc.stop(now + 0.15);
    },

    // Notification ping
    _playNotification(ctx, now) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(880, now);
        osc.type = 'sine';
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
        osc.start(now);
        osc.stop(now + 0.2);
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// ANIMATION MANAGER
// ─────────────────────────────────────────────────────────────────────────────

const AnimationManager = {
    // Confetti celebration for winner
    showConfetti() {
        const container = document.createElement('div');
        container.className = 'confetti-container';
        container.id = 'confetti-container';

        const colors = ['#ff6b6b', '#ffd93d', '#6bcb77', '#4d96ff', '#ff9f43', '#a55eea'];

        for (let i = 0; i < 150; i++) {
            const confetti = document.createElement('div');
            confetti.className = 'confetti-piece';
            confetti.style.cssText = `
                left: ${Math.random() * 100}%;
                background-color: ${colors[Math.floor(Math.random() * colors.length)]};
                animation-delay: ${Math.random() * 3}s;
                animation-duration: ${2 + Math.random() * 2}s;
            `;
            container.appendChild(confetti);
        }

        document.body.appendChild(container);
        setTimeout(() => container.remove(), 6000);
    },

    // Torch snuff animation on player card
    animateTorchSnuff(playerId) {
        const playerCard = document.querySelector(`[data-player-id="${playerId}"]`);
        if (playerCard) {
            playerCard.classList.add('torch-snuff-animation');
            setTimeout(() => {
                playerCard.classList.remove('torch-snuff-animation');
                playerCard.classList.add('eliminated');
            }, 2000);
        }
    },

    // Dramatic pause overlay
    dramaticPause(duration = 2000) {
        return new Promise(resolve => {
            const overlay = document.createElement('div');
            overlay.className = 'dramatic-pause-overlay';
            overlay.innerHTML = '<div class="dramatic-dots">...</div>';
            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.remove();
                resolve();
            }, duration);
        });
    },

    // Vote slam animation
    voteSlam(targetName) {
        const voteEl = document.createElement('div');
        voteEl.className = 'vote-slam';
        voteEl.textContent = targetName;
        document.body.appendChild(voteEl);

        setTimeout(() => voteEl.remove(), 1500);
    },

    // Highlight current player
    highlightPlayer(playerId, highlight = true) {
        const playerCard = document.querySelector(`[data-player-id="${playerId}"]`);
        if (playerCard) {
            if (highlight) {
                playerCard.classList.add('current-turn');
            } else {
                playerCard.classList.remove('current-turn');
            }
        }
    },

    // Pulse effect on element
    pulseElement(elementId) {
        const el = document.getElementById(elementId);
        if (el) {
            el.classList.add('pulse-highlight');
            setTimeout(() => el.classList.remove('pulse-highlight'), 1000);
        }
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// MAIN NARRATOR CLASS
// ─────────────────────────────────────────────────────────────────────────────

class GameNarrator {
    constructor() {
        this.events = [];
        this.maxEvents = 50;
        this.isNarrating = false;
        this.narrateQueue = [];
        this.typingSpeed = 30; // ms per character
        this.previousState = null;

        // DOM elements (will be set on init)
        this.panelEl = null;
        this.messageEl = null;
        this.historyEl = null;
        this.cursorEl = null;

        // Initialize sound manager
        SoundManager.init();
    }

    // Initialize the narrator UI
    init() {
        this.createNarratorPanel();
        this.bindEvents();
        console.log('Narrator initialized');
    }

    // Create the narrator panel in the DOM
    createNarratorPanel() {
        // Check if already exists
        if (document.getElementById('narratorPanel')) {
            this.panelEl = document.getElementById('narratorPanel');
            this.messageEl = document.getElementById('narratorMessage');
            this.historyEl = document.getElementById('narratorHistory');
            this.cursorEl = document.getElementById('narratorCursor');
            return;
        }

        const panel = document.createElement('div');
        panel.id = 'narratorPanel';
        panel.className = 'narrator-panel';
        panel.innerHTML = `
            <div class="narrator-header">
                <span class="narrator-avatar">🏝️</span>
                <span class="narrator-title">Survivor Narrator</span>
                <button id="narratorSoundToggle" class="narrator-sound-toggle" title="Toggle sound">
                    ${SoundManager.isMuted() ? '🔇' : '🔊'}
                </button>
                <button id="narratorToggle" class="narrator-toggle" title="Minimize">▼</button>
            </div>
            <div class="narrator-content">
                <div class="narrator-text">
                    <span id="narratorMessage" class="narrator-message"></span>
                    <span id="narratorCursor" class="narrator-cursor">▋</span>
                </div>
                <div id="narratorHistory" class="narrator-history"></div>
            </div>
        `;

        // Find the best place to insert
        const gameContainer = document.querySelector('.game-container') || document.body;
        gameContainer.insertBefore(panel, gameContainer.firstChild);

        this.panelEl = panel;
        this.messageEl = document.getElementById('narratorMessage');
        this.historyEl = document.getElementById('narratorHistory');
        this.cursorEl = document.getElementById('narratorCursor');

        // Sound toggle button
        document.getElementById('narratorSoundToggle').addEventListener('click', () => {
            const isOn = SoundManager.toggle();
            document.getElementById('narratorSoundToggle').textContent = isOn ? '🔊' : '🔇';
        });

        // Minimize toggle
        document.getElementById('narratorToggle').addEventListener('click', () => {
            panel.classList.toggle('minimized');
            document.getElementById('narratorToggle').textContent =
                panel.classList.contains('minimized') ? '▲' : '▼';
        });
    }

    bindEvents() {
        // Listen for socket events if available
        if (window.SurvivorNetwork?.socketManager?.socket) {
            const socket = window.SurvivorNetwork.socketManager.socket;

            socket.on('game_event', (data) => {
                this.handleGameEvent(data);
            });

            socket.on('state_update', (gameState) => {
                this.handleStateUpdate(gameState);
            });

            socket.on('game_updated', (gameState) => {
                this.handleStateUpdate(gameState);
            });
        }
    }

    // Handle specific game events from server
    handleGameEvent(event) {
        const { type, player, target, card, count } = event;

        switch (type) {
            case 'steal':
                this.narrateSteal(player, target);
                break;
            case 'card_played':
                this.narrateCardPlay(player, card, target);
                break;
            case 'vote_cast':
                this.narrateVoteCast(player);
                break;
            case 'elimination':
                this.narrateElimination(player);
                break;
            case 'tribal_start':
                this.narrateTribalStart();
                break;
            case 'tribal_phase_change':
                this.narratePhaseChange(event.phase, event);
                break;
            case 'immunity_played':
                this.queueNarration('card_play_immunity_idol', { player });
                SoundManager.play('card_play');
                break;
            case 'immunity_nullified':
                this.queueNarration('card_play_idol_nullifier', { player, target });
                SoundManager.play('card_play');
                break;
            case 'player_joined':
                this.queueNarration('player_joined', { player });
                break;
            case 'game_start':
                this.queueNarration('game_start', { count: count || 0 });
                break;
            case 'winner':
                this.narrateWinner(player, event.votes);
                break;
            default:
                console.log('Narrator: unhandled event type:', type, event);
        }
    }

    // Handle state updates and detect changes
    handleStateUpdate(gameState) {
        if (!this.previousState) {
            this.previousState = gameState;
            return;
        }

        // Detect phase changes
        if (gameState.phase !== this.previousState.phase) {
            this.narratePhaseChange(gameState.phase, gameState);
        }

        // Detect player count changes (joins/leaves)
        const prevPlayerCount = Object.keys(this.previousState.players || {}).length;
        const newPlayerCount = Object.keys(gameState.players || {}).length;
        if (newPlayerCount > prevPlayerCount) {
            const newPlayers = Object.values(gameState.players).filter(
                p => !this.previousState.players?.[p.id]
            );
            newPlayers.forEach(p => {
                this.queueNarration('player_joined', { player: p.name });
            });
        }

        // Detect current player change (turn advance)
        if (gameState.currentPlayerId !== this.previousState.currentPlayerId) {
            const currentPlayer = gameState.players?.[gameState.currentPlayerId];
            if (currentPlayer && gameState.phase?.startsWith('turn_')) {
                const localPlayerId = window.SurvivorGame?.localGameState?.playerId;
                const isSelf = gameState.currentPlayerId === localPlayerId;
                this.queueNarration(isSelf ? 'turn_start_self' : 'turn_start', {
                    player: currentPlayer.name
                });
                AnimationManager.highlightPlayer(gameState.currentPlayerId);
            }
        }

        this.previousState = JSON.parse(JSON.stringify(gameState));
    }

    // Narrate phase changes
    narratePhaseChange(phase, gameState) {
        const phaseNarrations = {
            'lobby': null,
            'playing': () => {
                const count = Object.keys(gameState.players || {}).length;
                this.queueNarration('game_start', { count }, 'tribal_gong');
            },
            'tribal_announcement': () => {
                this.queueNarration('tribal_drawn', {}, 'tribal_gong');
            },
            'tribal_advantage_play': () => {
                this.queueNarration('tribal_advantage_phase', {});
            },
            'tribal_discussion': () => {
                this.queueNarration('tribal_discussion', {});
            },
            'tribal_voting': () => {
                const leader = this.getCouncilLeader(gameState);
                this.queueNarration('tribal_voting_start', { player: leader?.name || 'Unknown' });
            },
            'tribal_immunity': () => {
                this.queueNarration('tribal_immunity_phase', {});
            },
            'tribal_reveal': () => {
                this.queueNarration('vote_reveal_start', {}, 'vote_reveal');
            },
            'final_tribal': () => {
                const count = Object.values(gameState.players || {}).filter(p => !p.isEliminated).length;
                this.queueNarration('final_tribal_start', { count });
            },
            'finished': () => {
                const winner = this.getWinner(gameState);
                if (winner) {
                    this.narrateWinner(winner.name);
                }
            }
        };

        const handler = phaseNarrations[phase];
        if (handler) {
            handler();
        }
    }

    // Queue a narration (handles async typing)
    queueNarration(templateKey, data = {}, sound = null, animation = null) {
        this.narrateQueue.push({ templateKey, data, sound, animation });
        this.processQueue();
    }

    async processQueue() {
        if (this.isNarrating || this.narrateQueue.length === 0) return;

        this.isNarrating = true;
        const { templateKey, data, sound, animation } = this.narrateQueue.shift();

        // Get random template
        const templates = NARRATOR_TEMPLATES[templateKey];
        if (!templates || templates.length === 0) {
            console.warn('No template for:', templateKey);
            this.isNarrating = false;
            this.processQueue();
            return;
        }

        const template = templates[Math.floor(Math.random() * templates.length)];
        const message = this.interpolate(template, data);

        // Play sound
        if (sound) {
            SoundManager.play(sound);
        }

        // Trigger animation
        if (animation) {
            AnimationManager[animation]?.();
        }

        // Type out the message
        await this.typeMessage(message);

        // Add to history
        this.addToHistory(message);

        // Small pause between narrations
        await this.sleep(500);

        this.isNarrating = false;
        this.processQueue();
    }

    // Type out a message with cursor effect
    async typeMessage(message) {
        if (!this.messageEl || !this.cursorEl) return;

        this.messageEl.textContent = '';
        this.cursorEl.style.display = 'inline';

        for (let i = 0; i < message.length; i++) {
            this.messageEl.textContent += message[i];
            await this.sleep(this.typingSpeed);
        }

        // Keep cursor blinking for a moment
        await this.sleep(500);
        this.cursorEl.style.display = 'none';
    }

    // Add message to scrollable history
    addToHistory(message) {
        if (!this.historyEl) return;

        const event = {
            message,
            timestamp: Date.now()
        };

        this.events.push(event);
        if (this.events.length > this.maxEvents) {
            this.events.shift();
        }

        const entry = document.createElement('div');
        entry.className = 'narrator-history-entry';
        entry.innerHTML = `
            <span class="history-time">${this.formatTime(event.timestamp)}</span>
            <span class="history-message">${this.escapeHtml(message)}</span>
        `;

        this.historyEl.insertBefore(entry, this.historyEl.firstChild);

        // Trim old entries
        while (this.historyEl.children.length > this.maxEvents) {
            this.historyEl.removeChild(this.historyEl.lastChild);
        }
    }

    // Specific narration methods
    narrateSteal(thief, victim) {
        this.queueNarration('steal_success', { thief, victim }, 'steal');
    }

    narrateCardPlay(player, cardName, target) {
        // Check for special cards
        const cardLower = cardName?.toLowerCase() || '';

        if (cardLower.includes('immunity idol') && !cardLower.includes('nullifier')) {
            this.queueNarration('card_play_immunity_idol', { player, cardName }, 'card_play');
        } else if (cardLower.includes('nullifier')) {
            this.queueNarration('card_play_idol_nullifier', { player, cardName, target }, 'card_play');
        } else if (cardLower.includes('steal') && cardLower.includes('vote')) {
            this.queueNarration('card_play_steal_vote', { player, target }, 'card_play');
        } else if (cardLower.includes('extra vote')) {
            this.queueNarration('card_play_extra_vote', { player }, 'card_play');
        } else {
            this.queueNarration('card_play', { player, cardName }, 'card_play');
        }
    }

    narrateVoteCast(player) {
        this.queueNarration('vote_cast', { player }, 'notification');
    }

    narrateElimination(player) {
        SoundManager.play('torch_snuff');
        AnimationManager.animateTorchSnuff(player.id || player);
        this.queueNarration('elimination', { player: player.name || player });
    }

    narrateTribalStart() {
        this.queueNarration('tribal_start', {}, 'tribal_gong');
    }

    narrateWinner(playerName, votes) {
        SoundManager.play('victory');
        AnimationManager.showConfetti();
        this.queueNarration('winner', {
            player: playerName,
            votes: votes || ''
        });
    }

    // Utility methods
    interpolate(template, data) {
        return template.replace(/\{(\w+)\}/g, (match, key) => {
            return data[key] !== undefined ? data[key] : match;
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    getCouncilLeader(gameState) {
        const leaderId = gameState.currentVote?.councilLeaderId;
        return leaderId ? gameState.players?.[leaderId] : null;
    }

    getWinner(gameState) {
        const activePlayers = Object.values(gameState.players || {}).filter(p => !p.isEliminated);
        return activePlayers.length === 1 ? activePlayers[0] : null;
    }

    // Public method to manually trigger narration
    narrate(message, options = {}) {
        const { sound, animation } = options;
        if (sound) SoundManager.play(sound);
        if (animation) AnimationManager[animation]?.();
        this.typeMessage(message).then(() => this.addToHistory(message));
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// EXPORT & INITIALIZATION
// ─────────────────────────────────────────────────────────────────────────────

// Create global instance
window.SurvivorNarrator = new GameNarrator();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { GameNarrator, SoundManager, AnimationManager };
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.SurvivorNarrator.init();
    });
} else {
    window.SurvivorNarrator.init();
}

console.log('Narrator module loaded');
