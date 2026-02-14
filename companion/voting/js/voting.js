// Survivor Voting App - UI helpers for voting and game display

// Ensure the script executes only after the DOM is loaded. The main app
// script (app.js) will call these functions when appropriate.

/**
 * Render the list of players and their status to the DOM. Each player shows
 * their name, color and whether they are the current leader.
 */
function renderPlayerList() {
  const container = document.getElementById('player-list');
  container.innerHTML = '';
  GameState.players.forEach((player, idx) => {
    const div = document.createElement('div');
    div.className = 'player-card';
    if (!player.alive) {
      div.classList.add('eliminated');
    }
    // Color badge
    const name = document.createElement('div');
    name.textContent = player.name;
    name.style.fontWeight = 'bold';
    const colorBadge = document.createElement('div');
    colorBadge.className = 'badge';
    colorBadge.style.backgroundColor = player.color;
    colorBadge.textContent = '';
    // Leader badge
    const leaderBadge = document.createElement('div');
    leaderBadge.className = 'badge';
    leaderBadge.style.backgroundColor = 'transparent';
    leaderBadge.style.border = `1px solid var(--primary-color)`;
    leaderBadge.textContent = 'Leader';
    leaderBadge.style.display = (idx === GameState.leaderIndex && player.alive) ? 'inline-block' : 'none';
    div.appendChild(name);
    div.appendChild(colorBadge);
    div.appendChild(leaderBadge);
    // Advantage info
    const advInfo = document.createElement('div');
    advInfo.className = 'advantage-info';
    // Show extra votes and idols if any
    const ev = player.extraVotes;
    const idl = player.idols;
    let info = '';
    if (ev > 0) info += `EV: ${ev} `;
    if (idl > 0) info += `Idol: ${idl}`;
    advInfo.textContent = info.trim();
    div.appendChild(advInfo);
    container.appendChild(div);
  });
}

/**
 * Render the history of tribal councils. Shows round number, votes and who
 * was eliminated or if there was a tie.
 */
function renderHistory() {
  const list = document.getElementById('history-list');
  list.innerHTML = '';
    GameState.history.forEach((council) => {
    const item = document.createElement('li');
    let text = `Round ${council.round}: `;
    if (council.tie && (!council.eliminatedIndices || council.eliminatedIndices.length === 0)) {
      text += 'Tie – no one was eliminated';
    } else if (council.eliminatedIndices && council.eliminatedIndices.length > 0) {
      const names = council.eliminatedIndices.map((idx) => GameState.players[idx].name).join(' & ');
      text += `${names} ${council.eliminatedIndices.length > 1 ? 'were' : 'was'} eliminated`;
    }
    item.textContent = text;
    list.appendChild(item);
  });
}

/**
 * Update the status information at the top of the game screen.
 */
function renderStatus() {
  const statusDiv = document.getElementById('status-info');
  const aliveCount = GameState.players.filter((p) => p.alive).length;
  const round = GameState.round + 1;
  const leader = GameState.players[GameState.leaderIndex];
  let text = `Round ${round} – ${aliveCount} player${aliveCount === 1 ? '' : 's'} remaining`;
  if (leader && leader.alive) {
    text += ` – Leader: ${leader.name}`;
  }
  statusDiv.textContent = text;
}

/**
 * Show the specified section and hide all others. Valid ids are
 * 'setup-section', 'game-section', and 'council-section'.
 * @param {string} id
 */
function showSection(id) {
  ['setup-section', 'game-section', 'council-section'].forEach((sec) => {
    const element = document.getElementById(sec);
    if (element) {
      element.classList.toggle('hidden', sec !== id);
    }
  });
}

/**
 * Prepare the voting interface for the current voter. Displays the list of
 * alive players as options (excluding the voter themselves), resets the
 * cast-vote button and updates instructions.
 */
function updateVotingInterface() {
  const instruction = document.getElementById('vote-instructions');
  const optionsContainer = document.getElementById('vote-options');
  const castVoteBtn = document.getElementById('cast-vote-btn');
  optionsContainer.innerHTML = '';
  castVoteBtn.disabled = true;
  // Determine current voter index
  const voterIndex = GameState.votingOrder[GameState.currentVoterIdx];
  const voter = GameState.players[voterIndex];
  instruction.textContent = `${voter.name}, please cast your vote.`;
  // Create options: alive players except the voter
  GameState.players.forEach((player, idx) => {
    if (player.alive && idx !== voterIndex) {
      const opt = document.createElement('div');
      opt.className = 'vote-option';
      opt.textContent = player.name;
      opt.dataset.targetIndex = idx.toString();
      opt.addEventListener('click', () => {
        // Deselect all and select this
        Array.from(optionsContainer.children).forEach((child) => {
          child.classList.remove('selected');
        });
        opt.classList.add('selected');
        castVoteBtn.disabled = false;
        castVoteBtn.dataset.targetIndex = idx.toString();
      });
      optionsContainer.appendChild(opt);
    }
  });
}

/**
 * Display the reveal of votes with a dramatic animation. Accepts the
 * vote results summary returned from finalizeCouncil() and appends
 * vote cards to the reveal container. After the reveal, shows
 * elimination outcome.
 * @param {{ tally: Object, eliminatedIndex: number|null, tie: boolean }} result
 */
function showVotesReveal(result, showContinue = true) {
  const container = document.getElementById('reveal-container');
  container.innerHTML = '';
  // Reveal each vote one at a time
  // Play drum when reveal starts
  if (typeof playDrum === 'function') {
    playDrum();
  }
  GameState.currentVotes.forEach((vote, idx) => {
    const voter = GameState.players[vote.voterIndex];
    const target = GameState.players[vote.targetIndex];
    const card = document.createElement('div');
    card.className = 'vote-card';
    // Delay the animation start for each card
    card.style.animationDelay = `${idx * 0.6}s`;
    card.textContent = `${target.name}`;
    container.appendChild(card);
  });
  // After all cards have appeared, append result summary
  const summary = document.createElement('div');
  summary.style.marginTop = '1rem';
  summary.style.fontWeight = 'bold';
  // Compute when to show summary (cards + 1s)
  const delay = GameState.currentVotes.length * 0.6 + 1.0;
  setTimeout(() => {
    if (result.tie && (!result.eliminatedIndices || result.eliminatedIndices.length === 0)) {
      summary.textContent = 'It was a tie! No one is eliminated.';
    } else if (result.eliminatedIndices && result.eliminatedIndices.length > 0) {
      if (result.eliminatedIndices.length === 1) {
        const eliminated = GameState.players[result.eliminatedIndices[0]];
        if (result.tie) {
          summary.textContent = `It was a tie! ${eliminated.name} was eliminated by tiebreaker.`;
        } else {
          summary.textContent = `${eliminated.name} has been eliminated.`;
        }
      } else {
        const names = result.eliminatedIndices.map((idx) => GameState.players[idx].name).join(' & ');
        if (result.tie) {
          summary.textContent = `It was a tie! ${names} were eliminated by tiebreaker.`;
        } else {
          summary.textContent = `${names} have been eliminated.`;
        }
      }
    }
    container.appendChild(summary);
    // Show continue button only if requested
    if (showContinue) {
      document.getElementById('council-complete-btn').classList.remove('hidden');
    }
  }, delay * 1000);
}