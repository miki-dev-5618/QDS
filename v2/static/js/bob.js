let ws = null;
let currentTxId = null;

document.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
  initDishonestButton();
  initDownloadQCertButton();
});

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/bob`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    updateConnectionBadge(true);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.event === 'init_sync') {
        if (msg.data.circuit_breaker) updateCircuitBreakerBadge(msg.data.circuit_breaker.status);
        if (msg.data.transmissions && msg.data.transmissions.length > 0) {
          renderTransmission(msg.data.transmissions[msg.data.transmissions.length - 1]);
        }
      } else if (msg.event === 'new_transmission') {
        renderTransmission(msg.data.transmission);
      } else if (msg.event === 'circuit_breaker_update') {
        updateCircuitBreakerBadge(msg.data.status);
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
      text.textContent = 'ONLINE / LISTENING';
    } else {
      dot.classList.add('danger');
      text.textContent = 'RECONNECTING';
    }
  }
}

function updateCircuitBreakerBadge(status) {
  const badge = document.getElementById('cbStatusBadge');
  const tag = document.getElementById('cbStatusTag');
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

function initDishonestButton() {
  const btn = document.getElementById('btnDishonestForward');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = 'Crafting Counterfeit Signature to Charlie...';

    try {
      const res = await fetch('/api/dishonest-bob-forward', { method: 'POST' });
      const data = await res.json();
      console.log('Dishonest forward triggered:', data);
    } catch (err) {
      console.error('Dishonest forward error:', err);
    } finally {
      btn.disabled = false;
      btn.textContent = '⚠️ Attempt Dishonest Forgery to Charlie';
    }
  });
}

function initDownloadQCertButton() {
  const btn = document.getElementById('btnDownloadQCert');
  if (!btn) return;

  btn.addEventListener('click', () => {
    if (!currentTxId) {
      alert('No transmission verified yet to generate Q-Cert.');
      return;
    }
    window.location.href = `/api/qcert/${currentTxId}?node=bob`;
  });
}

function renderTransmission(tx) {
  currentTxId = tx.transmission_id;

  const emptyState = document.getElementById('emptyState');
  const activeContent = document.getElementById('activeContent');
  if (emptyState) emptyState.style.display = 'none';
  if (activeContent) activeContent.style.display = 'block';

  const isBobValid = tx.bob.is_valid;
  const report = tx.threat_report;

  // 1. INNOVATION 2: Quantum Circuit Breaker Active Interlock Banner
  const cbBanner = document.getElementById('cbBanner');
  const cbDetails = document.getElementById('cbDetailsText');
  const cbIncidentId = document.getElementById('cbIncidentIdText');

  if (tx.circuit_breaker && tx.circuit_breaker.status === 'TRIPPED') {
    updateCircuitBreakerBadge('TRIPPED');
    if (cbBanner) {
      cbBanner.style.display = 'block';
      if (tx.circuit_breaker.incident) {
        cbDetails.textContent = `Active threat auto-quenched in ${tx.circuit_breaker.incident.quarantine_latency_ms}ms. In-flight entangled Bell pair buffers purged from memory. Virtual quantum channel locked.`;
        cbIncidentId.textContent = `INCIDENT ID: ${tx.circuit_breaker.incident.incident_id}`;
      }
    }
  } else {
    updateCircuitBreakerBadge('ARMED');
    if (cbBanner) cbBanner.style.display = 'none';
  }

  // 2. Render Verdict Banner
  const banner = document.getElementById('verdictBanner');
  const icon = document.getElementById('verdictIcon');
  const title = document.getElementById('verdictTitle');
  const subtitle = document.getElementById('verdictSubtitle');
  const mismatchesVal = document.getElementById('mismatchesVal');
  const qberVal = document.getElementById('qberVal');
  const msgDisplay = document.getElementById('verifiedMsgText');

  if (banner) {
    banner.className = `verdict-banner ${isBobValid ? 'verified' : 'threat'}`;
    icon.textContent = isBobValid ? '✓' : '⚠️';
    title.textContent = isBobValid ? 'SIGNATURE VERIFIED AUTHENTIC' : 'SECURITY ALERT: THREAT QUENCHED';
    subtitle.textContent = isBobValid 
      ? 'Alice signature states match orthogonal elimination rules. Dual-Tier noise test passed.'
      : report.details;
  }

  if (mismatchesVal) mismatchesVal.textContent = `${tx.bob.mismatches} / ${tx.bob.total_checked}`;
  if (qberVal) qberVal.textContent = `${(tx.channel.qber * 100).toFixed(1)}%`;
  if (msgDisplay) msgDisplay.textContent = tx.message_text;

  // 3. INNOVATION 1: Render Q-THB Status
  const qthbDigestEl = document.getElementById('bobQthbDigest');
  const qthbStatusEl = document.getElementById('bobQthbStatus');
  if (tx.qthb) {
    if (qthbDigestEl) qthbDigestEl.textContent = tx.qthb.message_digest.slice(0, 24) + '...';
    if (qthbStatusEl) {
      if (tx.qthb.is_tampered) {
        qthbStatusEl.textContent = 'Q-THB DESYNCHRONIZED (TAMPERED)';
        qthbStatusEl.style.color = 'var(--crimson)';
        qthbStatusEl.style.borderColor = 'rgba(244,63,94,0.5)';
      } else {
        qthbStatusEl.textContent = 'Q-THB SYNCHRONIZED';
        qthbStatusEl.style.color = 'var(--cyan-glow)';
        qthbStatusEl.style.borderColor = 'rgba(0,242,254,0.4)';
      }
    }
  }

  // 4. INNOVATION 3: Render Dual-Tier Discriminator
  if (report.dual_tier_discrimination) {
    const dt = report.dual_tier_discrimination;
    const t1El = document.getElementById('tier1Status');
    const t2El = document.getElementById('tier2Status');
    const faEl = document.getElementById('tierFaBound');

    if (t1El) {
      t1El.textContent = dt.tier1_status;
      t1El.className = dt.tier1_status.includes('PASS') ? 'tier-tag tier-pass' : 'tier-tag tier-alert';
    }
    if (t2El) {
      t2El.textContent = dt.tier2_status;
      t2El.className = dt.tier2_disturbance_detected ? 'tier-tag tier-alert' : 'tier-tag tier-pass';
    }
    if (faEl) faEl.textContent = dt.false_alarm_bound_str;
  }

  // 5. Render Orthogonal Elimination Matrix
  const tbody = document.getElementById('matrixBody');
  if (tbody) {
    tbody.innerHTML = '';
    const n = tx.n_bits;
    for (let i = 0; i < n; i++) {
      const held = (tx.bob.held_tokens && tx.bob.held_tokens[i]) ? tx.bob.held_tokens[i].join(', ') : 'None';
      const elim = (tx.bob.eliminated_states && tx.bob.eliminated_states[i]) ? tx.bob.eliminated_states[i] : [];
      const revealed = tx.alice.revealed_signature && tx.alice.revealed_signature[i];
      const stateSym = revealed ? getStateSymbol(revealed[0], revealed[1]) : '—';
      
      const isCollision = elim.includes(stateSym);

      const tr = document.createElement('tr');
      if (isCollision) tr.className = 'collision-row';

      tr.innerHTML = `
        <td>#${i}</td>
        <td>${held || 'Forwarded to Charlie'}</td>
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

  // 6. Render Chernoff Security Certificate
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
