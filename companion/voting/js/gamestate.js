// Survivor Voting App - Game state management
//
// This module exposes a simple GameState object to track players, rounds,
// votes and the flow of the game. All state is stored on the client side
// (using in-memory variables) but could be persisted to localStorage for
// longer sessions or shared via WebSockets in a multi-device scenario.

(function () {
  const GameState = {
    players: [],         // Array of player objects { name, color, alive, characterCards }
    leaderIndex: 0,      // Index of the current Tribal Council leader in players array
    round: 0,            // Current round (Tribal Council number)
    history: [],         // Array of past councils: { round, votes, eliminatedIndex, tie }
    currentVotes: [],    // Votes cast in the current council: { voterIndex, targetIndex }
    votingOrder: [],     // Order in which players vote during the current council
    currentVoterIdx: 0,  // Pointer into votingOrder to know whose turn it is
    phase: 'setup',      // Setup | game | council-vote | reveal
    eliminationMode: 'single', // 'single' or 'double'
    tieBreaker: 'random',      // 'random' or 'none'
  };

  /**
   * Initialize a new game with the provided player data.
   * @param {Array<{name: string, color: string}>} playersData
   * @param {number} leaderIndex
   */
  function createGame(playersData, leaderIndex = 0, eliminationMode = 'single', tieBreaker = 'random') {
    GameState.players = playersData.map((p) => ({
      name: p.name.trim() || 'Player',
      color: p.color || '#ffffff',
      alive: true,
      characterCards: [],
      extraVotes: 0,
      idols: 0,
    }));
    GameState.leaderIndex = leaderIndex;
    GameState.round = 0;
    GameState.history = [];
    GameState.phase = 'game';
    // Set elimination mode and tiebreaker for new game
    GameState.eliminationMode = eliminationMode;
    GameState.tieBreaker = tieBreaker;
  }

  /**
   * Start a new Tribal Council. Prepares the voting order starting from the leader.
   */
  function startCouncil() {
    GameState.currentVotes = [];
    // Determine order of alive players starting from leader
    const aliveIndices = GameState.players
      .map((_, idx) => idx)
      .filter((idx) => GameState.players[idx].alive);
    // Find the first alive index equal or after leader
    const startIdx = aliveIndices.indexOf(GameState.leaderIndex);
    // Base order of alive players starting from leader
    const baseOrder = aliveIndices
      .slice(startIdx)
      .concat(aliveIndices.slice(0, startIdx));
    // Build voting order, duplicating entries based on extraVotes
    const expandedOrder = [];
    baseOrder.forEach((idx) => {
      expandedOrder.push(idx);
      const extra = GameState.players[idx].extraVotes || 0;
      for (let i = 0; i < extra; i++) {
        expandedOrder.push(idx);
      }
      // Consume extra votes for next councils
      GameState.players[idx].extraVotes = 0;
    });
    GameState.votingOrder = expandedOrder;
    GameState.currentVoterIdx = 0;
    GameState.phase = 'council-vote';
  }

  /**
   * Record a vote for the current voter.
   * @param {number} targetIndex Index of the player being voted for
   */
  function castVote(targetIndex) {
    const voterIndex = GameState.votingOrder[GameState.currentVoterIdx];
    GameState.currentVotes.push({ voterIndex, targetIndex });
    GameState.currentVoterIdx += 1;
  }

  /**
   * Determine if there are remaining voters.
   * @returns {boolean}
   */
  function hasMoreVoters() {
    return GameState.currentVoterIdx < GameState.votingOrder.length;
  }

  /**
   * Finalize the current Tribal Council. Calculates vote tallies and
   * determines who is eliminated (if any). Updates history and player status.
   * Returns an object summarizing the results.
   */
  function finalizeCouncil(protectedIndices = []) {
    // Tally votes for alive players excluding protected players
    const tally = {};
    GameState.players.forEach((player, idx) => {
      if (player.alive && !protectedIndices.includes(idx)) {
        tally[idx] = 0;
      }
    });
    GameState.currentVotes.forEach((v) => {
      // Ignore votes cast against protected players
      if (protectedIndices.includes(v.targetIndex)) {
        return;
      }
      if (tally.hasOwnProperty(v.targetIndex)) {
        tally[v.targetIndex]++;
      }
    });
    // Build list of candidates sorted by vote count (desc)
    const candidates = Object.keys(tally).map((s) => ({
      idx: parseInt(s, 10),
      votes: tally[s],
    }));
    candidates.sort((a, b) => b.votes - a.votes);
    const eliminatedIndices = [];
    let tie = false;
    if (candidates.length > 0) {
      if (GameState.eliminationMode === 'double') {
        // Determine top vote count and potential second vote count
        const topVotes = candidates[0].votes;
        // Collect all with topVotes
        const topCandidates = candidates.filter((c) => c.votes === topVotes).map((c) => c.idx);
        if (topCandidates.length >= 2) {
          // If tie on top and we need two eliminations
          if (GameState.tieBreaker === 'none') {
            tie = true;
          } else {
            // Randomly pick two from tied candidates
            const shuffled = topCandidates.sort(() => Math.random() - 0.5);
            eliminatedIndices.push(shuffled[0]);
            eliminatedIndices.push(shuffled[1]);
          }
        } else if (topCandidates.length === 1) {
          const first = topCandidates[0];
          eliminatedIndices.push(first);
          // Determine second highest vote count
          const secondVotes = candidates.find((c) => c.idx !== first)?.votes ?? 0;
          // All candidates with secondVotes (excluding first)
          const secondCandidates = candidates
            .filter((c) => c.idx !== first && c.votes === secondVotes)
            .map((c) => c.idx);
          if (secondCandidates.length === 0 || secondVotes === 0) {
            // No second candidate means only one elimination
          } else if (secondCandidates.length === 1) {
            eliminatedIndices.push(secondCandidates[0]);
          } else {
            // Tie for second spot
            if (GameState.tieBreaker === 'none') {
              tie = true;
            } else {
              const randIdx = Math.floor(Math.random() * secondCandidates.length);
              eliminatedIndices.push(secondCandidates[randIdx]);
            }
          }
        }
      } else {
        // Single elimination
        const topVotes = candidates[0].votes;
        const topCandidates = candidates.filter((c) => c.votes === topVotes).map((c) => c.idx);
        if (topCandidates.length === 1) {
          eliminatedIndices.push(topCandidates[0]);
        } else {
          // Tie for top
          tie = true;
          if (GameState.tieBreaker === 'none') {
            // No elimination on tie
          } else {
            const rand = Math.floor(Math.random() * topCandidates.length);
            eliminatedIndices.push(topCandidates[rand]);
          }
        }
      }
    }
    // Apply eliminations
    eliminatedIndices.forEach((elimIdx) => {
      GameState.players[elimIdx].alive = false;
    });
    // Update leader: if current leader eliminated, pick next alive
    const aliveIndices = GameState.players
      .map((_, idx) => idx)
      .filter((idx) => GameState.players[idx].alive);
    if (aliveIndices.length > 0) {
      if (eliminatedIndices.includes(GameState.leaderIndex)) {
        // If multiple eliminations, leader might not be first elimination
        // Choose next alive index in aliveIndices list (circular)
        let pos = aliveIndices.indexOf(GameState.leaderIndex);
        if (pos === -1) {
          // If leaderIndex is eliminated, default to first alive
          GameState.leaderIndex = aliveIndices[0];
        } else {
          GameState.leaderIndex = aliveIndices[pos % aliveIndices.length];
        }
      }
    }
    // Save history
    GameState.history.push({
      round: GameState.round + 1,
      votes: [...GameState.currentVotes],
      eliminatedIndices: [...eliminatedIndices],
      tie,
      protected: [...protectedIndices],
    });
    GameState.round += 1;
    GameState.phase = 'game';
    // For backward compatibility, return eliminatedIndex as first eliminated if exists
    const result = {
      tally,
      eliminatedIndex: eliminatedIndices.length > 0 ? eliminatedIndices[0] : null,
      tie,
      eliminatedIndices,
    };
    return result;
  }

  /**
   * Determine if the game has reached the final phase (two players left).
   * @returns {boolean}
   */
  function isFinalCouncil() {
    const aliveCount = GameState.players.filter((p) => p.alive).length;
    return aliveCount <= 2;
  }

  /**
   * Export the GameState and associated functions to the global scope.
   */
  window.GameState = GameState;
  window.createGame = createGame;
  window.startCouncil = startCouncil;
  window.castVote = castVote;
  window.hasMoreVoters = hasMoreVoters;
  window.finalizeCouncil = finalizeCouncil;
  window.isFinalCouncil = isFinalCouncil;
})();