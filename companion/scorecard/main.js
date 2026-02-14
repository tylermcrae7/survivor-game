// Survivor Winners Scorecard JavaScript
// Handles scoreboard state, local persistence and peer‑to‑peer syncing.

(() => {
  /** Scoreboard array: each entry has the shape { name: string, score: number } */
  let scoreboard = [];
  /** Whether this page instance is the host (creator) of the board */
  let isHost = false;
  /** PeerJS instance */
  let peer;
  /** Connections to viewers (used by host) */
  const connections = [];

  /** DOM references */
  const tbody = document.querySelector('#scoreboard tbody');
  const hostControls = document.getElementById('host-controls');
  const shareSection = document.getElementById('share-section');

  /** Render the scoreboard table */
  function renderScoreboard() {
    // Clear existing rows
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (!scoreboard || scoreboard.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 3;
      td.className = 'empty';
      td.textContent = 'No players yet.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    // Determine highest score to highlight leader
    const scores = scoreboard.map(p => p.score);
    const maxScore = scores.length > 0 ? Math.max(...scores) : 0;
    scoreboard.forEach((player, index) => {
      const tr = document.createElement('tr');
      // Highlight leader if single highest
      const leaderCount = scores.filter(s => s === maxScore).length;
      if (player.score === maxScore && leaderCount === 1) {
        tr.classList.add('leader');
      }
      const nameTd = document.createElement('td');
      nameTd.textContent = player.name;
      const scoreTd = document.createElement('td');
      scoreTd.textContent = player.score;
      const actionsTd = document.createElement('td');
      actionsTd.className = 'actions';
      if (isHost) {
        // decrement button
        const minusBtn = document.createElement('button');
        minusBtn.textContent = '−';
        minusBtn.title = 'Decrease score';
        minusBtn.onclick = () => updateScore(index, -1);
        // increment button
        const plusBtn = document.createElement('button');
        plusBtn.textContent = '+';
        plusBtn.title = 'Increase score';
        plusBtn.onclick = () => updateScore(index, 1);
        actionsTd.appendChild(minusBtn);
        actionsTd.appendChild(plusBtn);
      } else {
        actionsTd.textContent = '';
      }
      tr.appendChild(nameTd);
      tr.appendChild(scoreTd);
      tr.appendChild(actionsTd);
      tbody.appendChild(tr);
    });
  }

  /** Persist scoreboard to localStorage and broadcast to viewers */
  function saveState() {
    if (isHost) {
      try {
        localStorage.setItem('survivor_scoreboard', JSON.stringify(scoreboard));
      } catch (err) {
        console.warn('Unable to save scoreboard', err);
      }
      broadcastState();
    }
    renderScoreboard();
  }

  /** Send the current scoreboard state to all connected viewers */
  function broadcastState() {
    connections.forEach(conn => {
      if (conn.open) {
        try {
          conn.send({ type: 'state', scoreboard });
        } catch (err) {
          console.warn('Failed to send state', err);
        }
      }
    });
  }

  /** Adjust a player's score by a delta */
  function updateScore(index, delta) {
    scoreboard[index].score += delta;
    saveState();
  }

  /** Initialize host mode: create peer, set up controls and share link */
  function initHost() {
    isHost = true;
    // show host interface
    hostControls.style.display = '';
    shareSection.style.display = '';
    // read any saved scoreboard
    try {
      const saved = localStorage.getItem('survivor_scoreboard');
      if (saved) scoreboard = JSON.parse(saved);
    } catch (err) {
      console.warn('Error loading saved scoreboard', err);
    }

    // Attach add‑player handler early so it still works even if PeerJS fails
    document.getElementById('add-player').onclick = () => {
      const nameInput = document.getElementById('player-name');
      const scoreInput = document.getElementById('player-score');
      const name = nameInput.value.trim();
      const score = parseInt(scoreInput.value, 10) || 0;
      if (!name) {
        alert('Please enter a player name.');
        return;
      }
      scoreboard.push({ name, score });
      nameInput.value = '';
      scoreInput.value = '0';
      saveState();
    };

    // Attach reset board handler
    const resetBtn = document.getElementById('reset-board');
    if (resetBtn) {
      resetBtn.onclick = () => {
        if (confirm('Reset scoreboard? All players and scores will be removed.')) {
          // Clear array and local storage
          scoreboard = [];
          try {
            localStorage.removeItem('survivor_scoreboard');
          } catch (err) {
            console.warn('Unable to clear saved scoreboard', err);
          }
          saveState();
        }
      };
    }

    // Render current scoreboard after loading saved state
    renderScoreboard();

    // Try initializing PeerJS for remote sharing; if running from file:// this may throw
    try {
      peer = new Peer();
      peer.on('open', id => {
        const shareLink = document.getElementById('share-link');
        const copyBtn = document.getElementById('copy-link');
        const baseUrl = window.location.href.split('#')[0];
        const link = `${baseUrl}#peer=${id}`;
        shareLink.value = link;
        // copy to clipboard
        copyBtn.onclick = () => {
          shareLink.select();
          document.execCommand('copy');
          alert('Link copied to clipboard!');
        };
      });
      peer.on('connection', conn => {
        connections.push(conn);
        conn.on('open', () => {
          // send current state on connect
          conn.send({ type: 'state', scoreboard });
        });
        conn.on('data', data => {
          // currently ignore incoming messages from viewers
          console.log('Received data from viewer', data);
        });
      });
    } catch (err) {
      console.warn('PeerJS could not be initialized', err);
      // Hide share link since remote connections are unavailable
      shareSection.style.display = 'none';
    }
  }

  /** Initialize viewer mode: connect to host and listen for updates */
  function initViewer(hostId) {
    isHost = false;
    // hide host controls
    hostControls.style.display = 'none';
    shareSection.style.display = 'none';
    // do not load saved scoreboard
    // Setup PeerJS and connect to host
    peer = new Peer();
    peer.on('open', () => {
      const conn = peer.connect(hostId);
      conn.on('open', () => {
        // request initial state
        conn.send({ type: 'join' });
      });
      conn.on('data', data => {
        if (data && data.type === 'state') {
          scoreboard = data.scoreboard.slice();
          renderScoreboard();
        }
      });
    });
  }

  /** Parse the peer ID from URL hash */
  function getHostIdFromHash() {
    const hash = window.location.hash.slice(1);
    const params = new URLSearchParams(hash);
    return params.get('peer');
  }

  // Run on page load
  window.addEventListener('load', () => {
    const hostId = getHostIdFromHash();
    if (hostId) {
      initViewer(hostId);
    } else {
      initHost();
    }
  });
})();