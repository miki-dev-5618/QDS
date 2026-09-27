let ws = null;

document.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
});

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/charlie`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    updateConnectionBadge(true);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.event === 'init_sync' && msg.data.transmissions && msg.data.transmissions.length > 0) {
        renderTransmission(msg.data.transmissions[msg.data.transmissions.length - 1]);
      } else if (msg.event === 'new_transmission') {
        renderTransmission(msg.data.transmission);
      }
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };

  ws.onclose = () => {
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
      text.textContent = 'ONLINE / AUDITING';
    } else {
      dot.classList.add('danger');
      text.textContent = 'RECONNECTING';
    }
  }
}

function renderTransmission(tx) {
  const emptyState = document.getElementById('emptyState');
  const activeContent = document.getElementById('activeContent');
  if (emptyState) emptyState.style.display = 'none';
  if (activeContent) activeContent.style.display = 'block';

  // 1. Render Verdict Banner
  const banner = document.getElementById('verdictBanner');
  const icon = document.getElementById('verdictIcon');
  const title = document.getElementById('verdictTitle');
  const subtitle = document.getElementById('verdictSubtitle');
  const mismatchesVal = document.getElementById('mismatchesVal');
  const qberVal = document.getElementById('qberVal');
  const msgDisplay = document.getElementById('verifiedMsgText');

  const isCharlieValid = tx.charlie.is_valid;
  const report = tx.threat_report;

  if (banner) {
    banner.className = `verdict-banner ${isCharlieValid ? 'verified' : 'threat'}`;
    icon.textContent = isCharlieValid ? '✓' : '⚠️';
    title.textContent = isCharlieValid ? 'SIGNATURE AUDITED & VERIFIED' : 'SECURITY ALERT: THREAT CAUGHT';
    subtitle.textContent = isCharlieValid 
      ? 'Alice signature states are consistent with Charlie orthogonal elimination table.'
      : report.details;
  }

  if (mismatchesVal) mismatchesVal.textContent = `${tx.charlie.mismatches} / ${tx.charlie.total_checked}`;
  if (qberVal) qberVal.textContent = `${(tx.channel.qber * 100).toFixed(1)}%`;
  if (msgDisplay) msgDisplay.textContent = tx.message_text;

  // 2. Render Orthogonal Elimination Matrix
  const tbody = document.getElementById('matrixBody');
  if (tbody) {
    tbody.innerHTML = '';
    const n = tx.n_bits;
    for (let i = 0; i < n; i++) {
      const held = (tx.charlie.held_tokens && tx.charlie.held_tokens[i]) ? tx.charlie.held_tokens[i].join(', ') : 'None';
      const elim = (tx.charlie.eliminated_states && tx.charlie.eliminated_states[i]) ? tx.charlie.eliminated_states[i] : [];
      const revealed = tx.alice.revealed_signature && tx.alice.revealed_signature[i];
      const stateSym = revealed ? getStateSymbol(revealed[0], revealed[1]) : '—';
      
      const isCollision = elim.includes(stateSym);

      const tr = document.createElement('tr');
      if (isCollision) tr.className = 'collision-row';

      tr.innerHTML = `
        <td>#${i}</td>
        <td>${held || 'Forwarded to Bob'}</td>
        <td>${elim.map(s => `<span class="elim-badge">${s}</span>`).join('') || '<span style="color:var(--text-dim)">—</span>'}</td>
        <td style="font-weight:600; color:var(--cyan-glow);">${stateSym}</td>
        <td>
          <span style="color:${isCollision ? 'var(--crimson)' : 'var(--emerald)'}; font-weight:700;">
            ${isCollision ? '✗ CONTRADICTION' : '✓ VALID'}
          </span>
        </td>
      `;
      tbody.appendChild(tr);
    }
  }

  // 3. Render Chernoff Security Certificate
  if (report.certificate) {
    const cert = report.certificate;
    const certCard = document.getElementById('certCard');
    if (certCard) {
      certCard.innerHTML = `
        <div class="cert-cell">
          <span class="cert-cell-label">Acceptance Bound (s_a)</span>
          <span class="cert-cell-value">${cert.acceptance_threshold_sa}</span>
        </div>
        <div class="cert-cell">
          <span class="cert-cell-label">Verification Bound (s_v)</span>
          <span class="cert-cell-value">${cert.verification_threshold_sv}</span>
        </div>
        <div class="cert-cell">
          <span class="cert-cell-label">Safety Margin (Δ)</span>
          <span class="cert-cell-value">${cert.safety_margin_delta}</span>
        </div>
        <div class="cert-cell">
          <span class="cert-cell-label">P(Forge) Bound</span>
          <span class="cert-cell-value">${cert.forgery_probability_bound}</span>
        </div>
        <div class="cert-cell">
          <span class="cert-cell-label">P(FRR) Bound</span>
          <span class="cert-cell-value">${cert.false_rejection_probability_bound}</span>
        </div>
        <div class="cert-cell">
          <span class="cert-cell-label">Security Level</span>
          <span class="cert-cell-value">${cert.security_level_bits} bits</span>
        </div>
      `;
    }
  }
}

function getStateSymbol(bit, basis) {
  if (basis === 0) return bit === 0 ? '|0⟩' : '|1⟩';
  return bit === 0 ? '|+⟩' : '|−⟩';
}
