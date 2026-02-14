// Main application script for Survivor Voting App
// Handles user interactions, orchestrates the different game phases and
// updates the UI accordingly. Assumes GameState and UI helper functions
// (renderPlayerList, renderHistory, renderStatus, showSection, etc.) are
// already defined on the window.

document.addEventListener('DOMContentLoaded', () => {
  // --- PeerJS Host Logic ---
  let peer = null;
  let peerConnections = [];

  function initializePeerHost() {
    // Use a unique ID for the host, e.g., based on the game session
    const hostId = 'survivor-host-' + Date.now();
    peer = new Peer(hostId);

    peer.on('open', id => {
      console.log('Host PeerJS ID:', id);
      // Attempt to connect to the known viewer client ID
      const conn = peer.connect('survivor-viewer-client');
      if (conn) {
        conn.on('open', () => {
          console.log('Connected to viewer.');
          peerConnections.push(conn);
        });
      }
    });

    peer.on('connection', conn => {
        console.log('Viewer connected.');
        peerConnections.push(conn);
    });

    peer.on('error', err => {
        console.error('PeerJS host error:', err);
    });
  }

  function broadcastToViewers(data) {
    peerConnections.forEach(conn => {
        if (conn.open) {
            conn.send(data);
        }
    });
  }
  // --- End of PeerJS Host Logic ---


  // Setup-phase elements
  const playerCountSelect = document.getElementById('player-count');
  const playersSetupDiv = document.getElementById('players-setup');
  const startGameBtn = document.getElementById('start-game-btn');

  // Game-phase elements
  const callCouncilBtn = document.getElementById('call-council-btn');
  const nextRoundBtn = document.getElementById('next-round-btn');

  // New UI elements for advanced phases
  const statsBtn = document.getElementById('stats-btn');
  const exportBtn = document.getElementById('export-btn');
  const theaterBtn = document.getElementById('theater-btn');
  const statsModal = document.getElementById('stats-modal');
  const statsContentDiv = document.getElementById('stats-content');
  const closeStatsBtn = document.getElementById('close-stats-btn');

  // Council-phase elements
  const councilStatusDiv = document.getElementById('council-status');
  const discussionPhase = document.getElementById('discussion-phase');
  const startVotingBtn = document.getElementById('start-voting-btn');
  const votingPhase = document.getElementById('voting-phase');
  const castVoteBtn = document.getElementById('cast-vote-btn');
  const idolPhase = document.getElementById('idol-phase');
  const revealPhase = document.getElementById('reveal-phase');
  // Note: revealVotesBtn removed; idol phase now uses play/skip buttons
  const councilCompleteBtn = document.getElementById('council-complete-btn');

  // Idol-phase elements
  const idolSelect = document.getElementById('idol-select');
  const playIdolBtn = document.getElementById('play-idol-btn');
  const skipIdolBtn = document.getElementById('skip-idol-btn');

  // Advantage management modal elements
  const manageAdvBtn = document.getElementById('manage-advantages-btn');
  const advModal = document.getElementById('advantages-modal');
  const advPlayerSelect = document.getElementById('adv-player-select');
  const giveExtraBtn = document.getElementById('give-extra-btn');
  const giveIdolBtn = document.getElementById('give-idol-btn');
  const advList = document.getElementById('adv-list');
  const closeAdvBtn = document.getElementById('close-adv-btn');

  // Final council elements
  const finalPhase = document.getElementById('final-phase');
  const finalInstructions = document.getElementById('final-instructions');
  const finalVotesContainer = document.getElementById('final-votes-container');
  const revealFinalBtn = document.getElementById('reveal-final-btn');
  const finalResultDiv = document.getElementById('final-result');

  // Discussion timer state
  let discussionInterval = null;
  let votingStartedAutomatically = false;

  // Load confessional notes from localStorage for the current session
  const confessionalArea = document.getElementById('confessional-notes');
  if (confessionalArea) {
    const saved = localStorage.getItem('survivorNotes');
    if (saved) {
      confessionalArea.value = saved;
    }
    confessionalArea.addEventListener('input', () => {
      localStorage.setItem('survivorNotes', confessionalArea.value);
    });
  }

  /**
   * Regenerate the player name/color input fields based on the selected
   * player count. Called whenever the user changes the number of players.
   */
  function updatePlayerInputs() {
    const count = parseInt(playerCountSelect.value, 10);
    playersSetupDiv.innerHTML = '';
    for (let i = 0; i < count; i++) {
      const wrapper = document.createElement('div');
      wrapper.style.marginTop = '1rem';
      // Player name input
      const nameLabel = document.createElement('label');
      nameLabel.textContent = `Player ${i + 1} Name:`;
      const nameInput = document.createElement('input');
      nameInput.type = 'text';
      nameInput.placeholder = `Player ${i + 1}`;
      nameInput.required = true;
      // Player color input
      const colorLabel = document.createElement('label');
      colorLabel.textContent = `Player ${i + 1} Color:`;
      const colorInput = document.createElement('input');
      colorInput.type = 'color';
      // Append to wrapper
      wrapper.appendChild(nameLabel);
      wrapper.appendChild(nameInput);
      wrapper.appendChild(colorLabel);
      wrapper.appendChild(colorInput);
      playersSetupDiv.appendChild(wrapper);
    }
  }

  playerCountSelect.addEventListener('change', updatePlayerInputs);
  // Initialize inputs on page load
  updatePlayerInputs();

  /**
   * Collect player data from the setup form and start the game.
   */
  function startGame() {
    const inputWrappers = playersSetupDiv.children;
    const players = [];
    for (let i = 0; i < inputWrappers.length; i++) {
      const wrapper = inputWrappers[i];
      const inputs = wrapper.querySelectorAll('input');
      const name = inputs[0].value.trim() || `Player ${i + 1}`;
      const color = inputs[1].value || '#ffffff';
      players.push({ name, color });
    }
    // Read game options
    const eliminationSelect = document.getElementById('elimination-mode');
    const tieSelect = document.getElementById('tie-breaker');
    const elimMode = eliminationSelect ? eliminationSelect.value : 'single';
    const tieRule = tieSelect ? tieSelect.value : 'random';
    // Set the leader as the first player initially and pass game options
    createGame(players, 0, elimMode, tieRule);

    // Initialize the PeerJS host
    initializePeerHost();

    // Switch to game view
    showSection('game-section');
    // Render initial UI
    renderPlayerList();
    renderHistory();
    renderStatus();
    // Reset next-round button
    nextRoundBtn.classList.add('hidden');
  }

  startGameBtn.addEventListener('click', startGame);

  /**
   * Called when the host initiates a Tribal Council. Prepares the council
   * phase UI and prompts for discussion before voting.
   */
  function callCouncil() {
    // Update status to indicate the council call
    councilStatusDiv.textContent = `Tribal Council called by ${GameState.players[GameState.leaderIndex].name}.`;
    // Hide other phases and show discussion
    discussionPhase.classList.remove('hidden');
    votingPhase.classList.add('hidden');
    idolPhase.classList.add('hidden');
    revealPhase.classList.add('hidden');
    councilCompleteBtn.classList.add('hidden');
    finalPhase.classList.add('hidden');
    // Show council section
    showSection('council-section');
    // Start discussion timer (e.g., 30 seconds) if not already started
    startDiscussionTimer(30);

    // Notify viewers that the council has started
    broadcastToViewers({ type: 'COUNCIL_START' });

    // Play atmospheric theme music during discussion
    if (typeof playThemeMusic === 'function') {
      playThemeMusic(30);
    }
  }

  callCouncilBtn.addEventListener('click', callCouncil);

  /**
   * Start the voting sequence. Initializes the voting order and updates
   * the UI for the first voter.
   */
  function startVoting() {
    // Clear discussion timer if active
    if (discussionInterval) {
      clearInterval(discussionInterval);
      discussionInterval = null;
    }
    // Prepare GameState for voting
    startCouncil();
    discussionPhase.classList.add('hidden');
    votingPhase.classList.remove('hidden');
    idolPhase.classList.add('hidden');
    revealPhase.classList.add('hidden');
    finalPhase.classList.add('hidden');
    councilCompleteBtn.classList.add('hidden');
    // Render the voting interface for the first voter
    updateVotingInterface(broadcastToViewers);
  }

  startVotingBtn.addEventListener('click', startVoting);

  /**
   * When a player casts their vote. Records the vote and advances
   * to the next voter or to the idol phase if all have voted.
   */
  function handleCastVote() {
    const targetIndex = parseInt(castVoteBtn.dataset.targetIndex, 10);
    if (isNaN(targetIndex)) return;
    // Record the vote
    castVote(targetIndex);
    playTap();
    // Clear button state
    castVoteBtn.disabled = true;
    castVoteBtn.removeAttribute('data-target-index');
    // Advance to next voter or move to idol phase
    if (hasMoreVoters()) {
      updateVotingInterface(broadcastToViewers);
    } else {
      // Voting finished
      votingPhase.classList.add('hidden');
      // Determine if final council (two players left)
      if (isFinalCouncil()) {
        // For the final council we only want to preview the votes without eliminating anyone
        const result = computePreviewTally([]);
        showVotesReveal(result, false);
        // After reveal, proceed to final council (jury vote)
        setTimeout(() => {
          startFinalCouncil();
        }, (GameState.currentVotes.length * 0.6 + 2) * 1000);
      } else {
        // Not final: prepare idol phase
        prepareIdolPhase();
      }
    }
  }

  castVoteBtn.addEventListener('click', handleCastVote);

  // handleRevealVotes removed; reveal handled via idol controls

  /**
   * Complete the current council and return to the game view. This resets
   * the council UI and updates the game status and history. Handles the
   * transition between rounds.
   */
  function completeCouncil() {
    // Hide council and show game
    showSection('game-section');
    // Reset council UI for next time
    discussionPhase.classList.add('hidden');
    votingPhase.classList.add('hidden');
    idolPhase.classList.add('hidden');
    revealPhase.classList.add('hidden');
    councilCompleteBtn.classList.add('hidden');
    // Update UI
    renderPlayerList();
    renderHistory();
    renderStatus();
    // Show next-round button if more than 1 player remains
    const aliveCount = GameState.players.filter((p) => p.alive).length;
    if (aliveCount > 1) {
      nextRoundBtn.classList.remove('hidden');
    }
  }

  councilCompleteBtn.addEventListener('click', completeCouncil);

  /**
   * Advance to the next round without calling a council. Useful for testing
   * or skipping elimination rounds (e.g., after a tie). Resets status and
   * hides the next-round button.
   */
  function nextRound() {
    nextRoundBtn.classList.add('hidden');
    renderStatus();
  }

  nextRoundBtn.addEventListener('click', nextRound);

  /**
   * Build and display the statistics modal. Shows per-round vote history and
   * aggregated statistics for each player.
   */
  function openStatsModal() {
    statsContentDiv.innerHTML = '';
    // Round-by-round history
    const history = GameState.history;
    const players = GameState.players;
    const list = document.createElement('div');
    list.style.marginBottom = '1rem';
    history.forEach((council) => {
      const roundDiv = document.createElement('div');
      roundDiv.style.marginBottom = '0.5rem';
      const title = document.createElement('strong');
      title.textContent = `Round ${council.round}: `;
      roundDiv.appendChild(title);
      // Build vote summary string
      const voteParts = council.votes.map((v) => {
        const voter = players[v.voterIndex].name;
        const target = players[v.targetIndex].name;
        return `${voter}→${target}`;
      });
      const summary = document.createElement('span');
      summary.textContent = voteParts.join(', ');
      roundDiv.appendChild(summary);
      // Elimination info
      const elimSpan = document.createElement('div');
      elimSpan.style.fontStyle = 'italic';
      if (council.tie && (!council.eliminatedIndices || council.eliminatedIndices.length === 0) && (council.eliminatedIndex === undefined || council.eliminatedIndex === null)) {
        elimSpan.textContent = 'Tie: no one was eliminated.';
      } else {
        // Determine eliminated names from either eliminatedIndices or eliminatedIndex
        let elimNames = null;
        if (council.eliminatedIndices && council.eliminatedIndices.length > 0) {
          elimNames = council.eliminatedIndices.map((idx) => players[idx].name).join(' & ');
        } else if (council.eliminatedIndex !== undefined && council.eliminatedIndex !== null) {
          elimNames = players[council.eliminatedIndex].name;
        }
        if (elimNames) {
          elimSpan.textContent = `Eliminated: ${elimNames}`;
        }
      }
      roundDiv.appendChild(elimSpan);
      list.appendChild(roundDiv);
    });
    statsContentDiv.appendChild(list);
    // Aggregated statistics
    const aggTitle = document.createElement('h4');
    aggTitle.textContent = 'Player Statistics';
    statsContentDiv.appendChild(aggTitle);
    // Compute votes cast and received
    const castCounts = {};
    const recvCounts = {};
    players.forEach((p, idx) => {
      castCounts[idx] = 0;
      recvCounts[idx] = 0;
    });
    history.forEach((council) => {
      council.votes.forEach((v) => {
        castCounts[v.voterIndex]++;
        // Count target only if alive at that time (we already tallied) but include anyway
        recvCounts[v.targetIndex]++;
      });
    });
    const table = document.createElement('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    ['Player', 'Votes Cast', 'Votes Received'].forEach((h) => {
      const th = document.createElement('th');
      th.textContent = h;
      th.style.textAlign = 'left';
      th.style.padding = '0.3rem';
      th.style.borderBottom = `1px solid var(--primary-color)`;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    players.forEach((p, idx) => {
      const row = document.createElement('tr');
      const nameTd = document.createElement('td');
      nameTd.textContent = p.name;
      nameTd.style.padding = '0.3rem';
      const castTd = document.createElement('td');
      castTd.textContent = castCounts[idx].toString();
      castTd.style.padding = '0.3rem';
      const recvTd = document.createElement('td');
      recvTd.textContent = recvCounts[idx].toString();
      recvTd.style.padding = '0.3rem';
      row.appendChild(nameTd);
      row.appendChild(castTd);
      row.appendChild(recvTd);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    statsContentDiv.appendChild(table);
    // Show modal
    statsModal.classList.remove('hidden');
  }

  function closeStatsModal() {
    statsModal.classList.add('hidden');
  }

  statsBtn.addEventListener('click', () => {
    openStatsModal();
  });
  closeStatsBtn.addEventListener('click', () => {
    closeStatsModal();
  });

  /**
   * Export the entire game history and player data to a downloadable JSON file.
   */
  function exportHistory() {
    const data = {
      players: GameState.players,
      history: GameState.history,
      rounds: GameState.round,
    };
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `survivor_history_round${GameState.round}.json`;
    document.body.appendChild(a);
a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 0);
  }

  exportBtn.addEventListener('click', exportHistory);

  /**
   * Toggle full screen mode for theater presentation.
   */
  function toggleTheaterMode() {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      const elem = document.documentElement;
      if (elem.requestFullscreen) {
        elem.requestFullscreen();
      } else if (elem.webkitRequestFullscreen) {
        elem.webkitRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  }

  theaterBtn.addEventListener('click', toggleTheaterMode);

  /**
   * Start a countdown for the discussion phase. When the timer reaches
   * zero and voting has not begun, automatically triggers the startVoting
   * function. Duration is specified in seconds.
   * @param {number} seconds
   */
  function startDiscussionTimer(seconds) {
    // Clear any existing timer
    if (discussionInterval) {
      clearInterval(discussionInterval);
      discussionInterval = null;
    }
    const timerEl = document.getElementById('discussion-timer');
    if (!timerEl) return;
    let remaining = seconds;
    timerEl.textContent = `Time remaining: ${remaining}s`;
    discussionInterval = setInterval(() => {
      remaining--;
      timerEl.textContent = `Time remaining: ${remaining}s`;
      if (remaining <= 0) {
        clearInterval(discussionInterval);
        discussionInterval = null;
        // Automatically start voting if discussion is still visible
        if (!discussionPhase.classList.contains('hidden')) {
          startVoting();
        }
      }
    }, 1000);
  }

  /**
   * Prepare the idol phase. If no players have idols, skip straight to reveal.
   */
  function prepareIdolPhase() {
    // Gather players with at least one idol
    const idolPlayers = GameState.players
      .map((p, idx) => ({ player: p, idx }))
      .filter((p) => p.player.alive && p.player.idols > 0);
    if (idolPlayers.length === 0) {
      // No idols available, reveal votes immediately
      const result = finalizeCouncil();
      idolPhase.classList.add('hidden');
      revealPhase.classList.remove('hidden');
      showVotesReveal(result);
      return;
    }
    // Populate the select with idol players
    idolSelect.innerHTML = '';
    idolPlayers.forEach(({ player, idx }) => {
      const opt = document.createElement('option');
      opt.value = idx;
      opt.textContent = player.name;
      idolSelect.appendChild(opt);
    });
    // Show idol phase
    idolPhase.classList.remove('hidden');
    revealPhase.classList.add('hidden');
    councilCompleteBtn.classList.add('hidden');
  }

  // Play idol button: protect selected player and proceed to reveal
  playIdolBtn.addEventListener('click', () => {
    const idx = parseInt(idolSelect.value, 10);
    if (!isNaN(idx) && GameState.players[idx].idols > 0) {
      // Remove an idol from player
      GameState.players[idx].idols -= 1;
      // Finalize council with protected player
      const result = finalizeCouncil([idx]);
      // Hide idol phase and show reveal
      idolPhase.classList.add('hidden');
      revealPhase.classList.remove('hidden');
      showVotesReveal(result);
    }
  });
  // Skip idol: finalize without protection
  skipIdolBtn.addEventListener('click', () => {
    const result = finalizeCouncil();
    idolPhase.classList.add('hidden');
    revealPhase.classList.remove('hidden');
    showVotesReveal(result);
  });

  /**
   * Compute a tally of votes without altering game state. Used for the final
   * council preview where no player is eliminated. Accepts optional
   * protectedIndices to ignore votes against protected players (not used in final).
   * Returns an object similar to finalizeCouncil with tally and tie state, but
   * no eliminated players.
   */
  function computePreviewTally(protectedIndices = []) {
    // Build tally for alive players excluding protected ones
    const tally = {};
    GameState.players.forEach((player, idx) => {
      if (player.alive && !protectedIndices.includes(idx)) {
        tally[idx] = 0;
      }
    });
    GameState.currentVotes.forEach((v) => {
      if (protectedIndices.includes(v.targetIndex)) {
        return;
      }
      if (tally.hasOwnProperty(v.targetIndex)) {
        tally[v.targetIndex]++;
      }
    });
    // Determine if tie
    let maxVotes = 0;
    for (const idx in tally) {
      if (tally[idx] > maxVotes) {
        maxVotes = tally[idx];
      }
    }
    const top = Object.keys(tally).filter((idx) => tally[idx] === maxVotes);
    const tie = top.length > 1;
    return { tally, eliminatedIndices: [], eliminatedIndex: null, tie };
  }

  /**
   * Manage advantages modal logic: open, close, assign extra vote or idol.
   */
  function openAdvModal() {
    // Populate player select
    advPlayerSelect.innerHTML = '';
    GameState.players.forEach((p, idx) => {
      if (p.alive) {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = p.name;
        advPlayerSelect.appendChild(opt);
      }
    });
    // Render advantage counts
    renderAdvantageList();
    advModal.classList.remove('hidden');
  }
  function closeAdvModal() {
    advModal.classList.add('hidden');
  }
  function renderAdvantageList() {
    advList.innerHTML = '';
    GameState.players.forEach((p) => {
      const li = document.createElement('li');
      li.textContent = `${p.name}: Extra Votes ${p.extraVotes}, Idols ${p.idols}`;
      advList.appendChild(li);
    });
  }
  manageAdvBtn.addEventListener('click', openAdvModal);
  closeAdvBtn.addEventListener('click', () => {
    closeAdvModal();
    renderPlayerList();
  });
  giveExtraBtn.addEventListener('click', () => {
    const idx = parseInt(advPlayerSelect.value, 10);
    if (!isNaN(idx)) {
      GameState.players[idx].extraVotes += 1;
      renderAdvantageList();
      renderPlayerList();
    }
  });
  giveIdolBtn.addEventListener('click', () => {
    const idx = parseInt(advPlayerSelect.value, 10);
    if (!isNaN(idx)) {
      GameState.players[idx].idols += 1;
      renderAdvantageList();
      renderPlayerList();
    }
  });

  /**
   * Initiate the final council (jury vote) phase. Displays a form for
   * eliminated players (jury) to vote for a winner among the remaining
   * contestants.
   */
  function startFinalCouncil() {
    // Determine finalists and jury
    const finalists = GameState.players
      .map((p, idx) => ({ player: p, idx }))
      .filter((p) => p.player.alive);
    const jury = GameState.players
      .map((p, idx) => ({ player: p, idx }))
      .filter((p) => !p.player.alive);
    // Reset UI
    discussionPhase.classList.add('hidden');
    votingPhase.classList.add('hidden');
    idolPhase.classList.add('hidden');
    revealPhase.classList.add('hidden');
    councilCompleteBtn.classList.add('hidden');
    // Build final vote form
    finalVotesContainer.innerHTML = '';
    finalInstructions.textContent = 'The jury will now vote for the winner.';
    jury.forEach(({ player, idx: juryIdx }) => {
      const wrapper = document.createElement('div');
      wrapper.style.marginBottom = '0.5rem';
      const label = document.createElement('span');
      label.textContent = `${player.name}: `;
      wrapper.appendChild(label);
      finalists.forEach(({ player: fplayer, idx: fIdx }) => {
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = `jury-${juryIdx}`;
        radio.value = fIdx;
        wrapper.appendChild(radio);
        const rLabel = document.createElement('label');
        rLabel.style.marginRight = '1rem';
        rLabel.textContent = fplayer.name;
        wrapper.appendChild(rLabel);
      });
      finalVotesContainer.appendChild(wrapper);
    });
    // Show final-phase and reveal button
    finalPhase.classList.remove('hidden');
    revealFinalBtn.classList.remove('hidden');
    finalResultDiv.textContent = '';
  }

  // Reveal final winner based on jury votes
  revealFinalBtn.addEventListener('click', () => {
    // Determine finalists
    const finalists = GameState.players
      .map((p, idx) => ({ player: p, idx }))
      .filter((p) => p.player.alive);
    const voteCounts = {};
    finalists.forEach(({ idx }) => {
      voteCounts[idx] = 0;
    });
    // Collect votes
    const jury = GameState.players
      .map((p, idx) => ({ player: p, idx }))
      .filter((p) => !p.player.alive);
    let valid = true;
    jury.forEach(({ idx: juryIdx }) => {
      const radios = document.getElementsByName(`jury-${juryIdx}`);
      let voted = false;
      radios.forEach((el) => {
        if (el.checked) {
          voteCounts[parseInt(el.value, 10)]++;
          voted = true;
        }
      });
      if (!voted) valid = false;
    });
    if (!valid) {
      finalResultDiv.textContent = 'Please collect a vote from each jury member.';
      return;
    }
    // Determine winner
    let max = 0;
    let winnerIdx = null;
    for (const idx in voteCounts) {
      if (voteCounts[idx] > max) {
        max = voteCounts[idx];
        winnerIdx = parseInt(idx, 10);
      }
    }
    const winner = GameState.players[winnerIdx];
    finalResultDiv.textContent = `${winner.name} wins the game with ${max} vote${max === 1 ? '' : 's'}!`;
    revealFinalBtn.classList.add('hidden');
  });
});