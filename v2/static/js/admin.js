let ws = null;
let currentThreat = 'authentic';

document.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
  initThreatCards();
  initComposer();
  initQTHBListener();
  loadHistory();
});

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/admin`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    logTerminal('SYS', 'Secure WebSocket channel connected to QDS Kernel.');
    updateConnectionBadge(true);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.event === 'init_sync') {
        if (msg.data.stats) updateStatsDisplay(msg.data.stats);
        if (msg.data.active_threat) setArmedThreatUI(msg.data.active_threat);
        if (msg.data.circuit_breaker) updateCircuitBreakerUI(msg.data.circuit_breaker.status);
      } else if (msg.event === 'new_transmission') {
        handleNewTransmission(msg.data.transmission);
        if (msg.data.stats) updateStatsDisplay(msg.data.stats);
        if (msg.data.transmission.circuit_breaker) {
          updateCircuitBreakerUI(msg.data.transmission.circuit_breaker.status);
        }
      } else if (msg.event === 'threat_armed') {
        setArmedThreatUI(msg.data.active_threat);
      } else if (msg.event === 'circuit_breaker_update') {
        updateCircuitBreakerUI(msg.data.status);
      }
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };

  ws.onclose = () => {
    logTerminal('WARN', 'WebSocket disconnected. Reconnecting in 2s...');
    updateConnectionBadge(false);
    setTimeout(initWebSocket, 2000);
  };
}

function updateConnectionBadge(online) {
  const dot = document.getElementById('connDot');
  const text = document.getElementById('connText');
  if (dot && text) {
    if (online) {
      dot.classList.remove('danger');
      text.textContent = 'ONLINE';
    } else {
      dot.classList.add('danger');
      text.textContent = 'RECONNECTING';
    }
  }
}

function updateCircuitBreakerUI(status) {
  const tag = document.getElementById('cbHeaderTag');
  const badge = document.getElementById('cbHeaderStatus');
  if (badge && tag) {
    badge.textContent = status;
    if (status === 'ARMED') {
      badge.style.color = 'var(--emerald)';
      tag.style.borderColor = 'rgba(16,185,129,0.3)';
    } else {
      badge.style.color = 'var(--crimson)';
      tag.style.borderColor = 'var(--crimson)';
    }
  }
}

function initThreatCards() {
  const cards = document.querySelectorAll('.threat-card');
  cards.forEach(card => {
    card.addEventListener('click', async () => {
      const threatType = card.dataset.threat;
      cards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      currentThreat = threatType;

      const tamperedGroup = document.getElementById('tamperedGroup');
      if (tamperedGroup) {
        tamperedGroup.style.display = (threatType === 'message_tampering') ? 'block' : 'none';
      }

      try {
        await fetch('/api/arm-threat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ threat_type: threatType })
        });
        logTerminal('ARMED', `Threat engine set to scenario: [${threatType.toUpperCase()}]`);
      } catch (err) {
        console.error('Failed to arm threat:', err);
      }
    });
  });
}

function setArmedThreatUI(threatType) {
  currentThreat = threatType;
  const cards = document.querySelectorAll('.threat-card');
  cards.forEach(c => {
    if (c.dataset.threat === threatType) {
      c.classList.add('active');
    } else {
      c.classList.remove('active');
    }
  });

  const badge = document.getElementById('activeThreatBadge');
  if (badge) {
    badge.textContent = threatType.toUpperCase();
    if (threatType === 'authentic') {
      badge.style.color = 'var(--cyan-glow)';
      badge.style.borderColor = 'rgba(0, 242, 254, 0.4)';
    } else {
      badge.style.color = 'var(--crimson)';
      badge.style.borderColor = 'rgba(244, 63, 94, 0.5)';
    }
  }
}

function initComposer() {
  const form = document.getElementById('signForm');
  const bitSelect = document.getElementById('bitDepth');
  const previewBox = document.getElementById('tokenPreview');

  function renderDummyTokens(n) {
    previewBox.innerHTML = '';
    const sampleStates = [
      { sym: '|0⟩', cls: 'token-z0' },
      { sym: '|1⟩', cls: 'token-z1' },
      { sym: '|+⟩', cls: 'token-x0' },
      { sym: '|−⟩', cls: 'token-x1' }
    ];
    for (let i = 0; i < n; i++) {
      const s = sampleStates[Math.floor(Math.random() * sampleStates.length)];
      const span = document.createElement('span');
      span.className = `qubit-token ${s.cls}`;
      span.textContent = `Q${i}: ${s.sym}`;
      previewBox.appendChild(span);
    }
  }

  renderDummyTokens(parseInt(bitSelect.value));

  bitSelect.addEventListener('change', () => {
    renderDummyTokens(parseInt(bitSelect.value));
    updateQTHBPreview();
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btnSign');
    const msgText = document.getElementById('messageText').value;
    const nBits = parseInt(bitSelect.value);
    const tamperedText = document.getElementById('tamperedText') ? document.getElementById('tamperedText').value : null;

    btn.disabled = true;
    btn.innerHTML = `<span class="title-icon">⏳</span> Quantum Teleporting & Signing...`;

    try {
      const res = await fetch('/api/sign-and-send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_text: msgText,
          n_bits: nBits,
          threat_type: currentThreat,
          tampered_text: tamperedText,
          claimed_sender: 'Alice'
        })
      });

      const data = await res.json();
      if (data.status === 'success') {
        const tx = data.transmission;
        logTerminal('TX', `Dispatched ID: ${tx.transmission_id} | Q-THB: ${tx.qthb.digest_truncated} | Threat: ${currentThreat}`);
      }
    } catch (err) {
      logTerminal('ERR', `Transmission failed: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span class="title-icon">⚡</span> Quantum Sign & Transmit Token`;
    }
  });
}

function initQTHBListener() {
  const msgArea = document.getElementById('messageText');
  if (msgArea) {
    msgArea.addEventListener('input', () => updateQTHBPreview());
  }
  updateQTHBPreview();
}

async function updateQTHBPreview() {
  const text = (document.getElementById('messageText') && document.getElementById('messageText').value) || ' ';
  const nBits = parseInt((document.getElementById('bitDepth') && document.getElementById('bitDepth').value) || '16');

  try {
    const msgBuffer = new TextEncoder().encode(text);
    const hashBuffer = await crypto.subtle.digest('SHA-512', msgBuffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

    const digestEl = document.getElementById('qthbDigest');
    const scheduleEl = document.getElementById('qthbSchedule');

    if (digestEl) {
      digestEl.textContent = hashHex.slice(0, 20) + '...' + hashHex.slice(-8);
    }

    if (scheduleEl) {
      scheduleEl.innerHTML = '';
      const displayCount = Math.min(nBits, 16);
      for (let i = 0; i < displayCount; i++) {
        const basis = (hashArray[i % hashArray.length] % 2 === 0) ? 'Z' : 'X';
        const pill = document.createElement('span');
        pill.className = `qthb-schedule-pill ${basis === 'Z' ? 'qthb-z' : 'qthb-x'}`;
        pill.textContent = basis;
        scheduleEl.appendChild(pill);
      }
      if (nBits > 16) {
        const extra = document.createElement('span');
        extra.style.color = 'var(--text-dim)';
        extra.style.fontSize = '0.7rem';
        extra.textContent = ` +${nBits - 16} more`;
        scheduleEl.appendChild(extra);
      }
    }
  } catch (err) {
    console.error('QTHB preview error:', err);
  }
}

function handleNewTransmission(tx) {
  const container = document.getElementById('recentTxList');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'glass-panel';
  row.style.padding = '0.85rem';
  row.style.marginBottom = '0.75rem';

  const report = tx.threat_report;
  const isThreat = report.is_threat_detected;

  row.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
      <span style="font-family:var(--font-mono); font-weight:700; color:var(--cyan-glow);">${tx.transmission_id}</span>
      <span style="font-size:0.75rem; font-family:var(--font-mono); color:${isThreat ? 'var(--crimson)' : 'var(--emerald)'}">
        ${isThreat ? 'THREAT DETECTED' : 'VERIFIED AUTHENTIC'}
      </span>
    </div>
    <div style="font-size:0.85rem; margin-bottom:0.4rem; color:var(--text-main);">"${tx.message_text}"</div>
    <div style="display:flex; gap:1rem; font-size:0.75rem; font-family:var(--font-mono); color:var(--text-dim); flex-wrap:wrap;">
      <span>Bob: ${tx.bob.mismatches} err</span>
      <span>Charlie: ${tx.charlie.mismatches} err</span>
      <span>QBER: ${(tx.channel.qber * 100).toFixed(1)}%</span>
      <span>Q-THB: ${tx.qthb ? tx.qthb.digest_truncated : 'Active'}</span>
      <span>QCB: ${tx.circuit_breaker ? tx.circuit_breaker.status : 'ARMED'}</span>
    </div>
  `;

  container.prepend(row);
  logTerminal('RECV', `Verdict on ${tx.transmission_id}: ${report.verdict}`);
}

function updateStatsDisplay(stats) {
  const elTotal = document.getElementById('statTotal');
  const elAuth = document.getElementById('statAuth');
  const elThreat = document.getElementById('statThreat');
  const elQber = document.getElementById('statQber');

  if (elTotal) elTotal.textContent = stats.total_sent;
  if (elAuth) elAuth.textContent = stats.verified_authentic;
  if (elThreat) elThreat.textContent = stats.threats_quenched;
  if (elQber) elQber.textContent = `${(stats.last_qber * 100).toFixed(1)}%`;
}

async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    if (data.stats) updateStatsDisplay(data.stats);
    if (data.circuit_breaker) updateCircuitBreakerUI(data.circuit_breaker.status);
    if (data.transmissions && data.transmissions.length > 0) {
      data.transmissions.slice(-5).forEach(tx => handleNewTransmission(tx));
    }
  } catch (e) {
    console.error('History load error:', e);
  }
}

function logTerminal(prefix, msg) {
  const term = document.getElementById('terminalLog');
  if (!term) return;

  const now = new Date().toLocaleTimeString();
  const line = document.createElement('div');
  line.className = 'log-entry';

  let cls = '';
  if (prefix === 'ARMED' || prefix === 'ERR') cls = 'log-threat';
  if (prefix === 'TX' || prefix === 'RECV') cls = 'log-success';

  line.innerHTML = `<span class="log-ts">[${now}]</span> <span class="log-prefix">${prefix}</span> <span class="${cls}">${msg}</span>`;
  term.appendChild(line);
  term.scrollTop = term.scrollHeight;
}
