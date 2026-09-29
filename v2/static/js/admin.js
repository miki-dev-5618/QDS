let currentThreat = 'authentic';
const seenTx = new Set();

document.addEventListener('DOMContentLoaded', () => {
  connectSocket('admin', handleMessage, online => {
    setConnectionBadge(online, 'ONLINE');
    if (online) logTerminal('SYS', 'Authenticated WebSocket connected.');
  });
  initThreatCards();
  initComposer();
  document.getElementById('btnResetLinks').addEventListener('click', resetLinks);
  document.getElementById('btnCheckChain').addEventListener('click', checkChain);
  loadHistory();
  refreshMetrics();
  refreshTopology();
  loadIncidents();
});

function handleMessage(msg) {
  if (msg.event === 'init_sync') {
    if (msg.data.stats) updateStatsDisplay(msg.data.stats);
    if (msg.data.active_threat) setArmedThreatUI(msg.data.active_threat);
    renderLinks(msg.data.channel_state);
  } else if (msg.event === 'new_transmission') {
    handleNewTransmission(msg.data.transmission);
    if (msg.data.stats) updateStatsDisplay(msg.data.stats);
    refreshMetrics();
    refreshTopology();
    if (msg.data.transmission.enforcement.incident_id) loadIncidents();
  } else if (msg.event === 'threat_armed') {
    setArmedThreatUI(msg.data.active_threat);
  } else if (msg.event === 'channel_state') {
    renderLinks(msg.data);
    refreshTopology();
  } else if (msg.event === 'security_event') {
    logTerminal('SEC', `${msg.data.type}: ${msg.data.detail}`);
  }
}

function initThreatCards() {
  const cards = document.querySelectorAll('.threat-card');
  cards.forEach(card => {
    card.addEventListener('click', async () => {
      const threatType = card.dataset.threat;
      setArmedThreatUI(threatType);
      try {
        await api('/api/arm-threat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ threat_type: threatType })
        }, 'admin');
        logTerminal('ARMED', `Injector set to scenario [${threatType.toUpperCase()}] (not visible to verifiers)`);
      } catch (err) {
        logTerminal('ERR', `Failed to arm: ${err.message}`);
      }
    });
  });
}

function setArmedThreatUI(threatType) {
  currentThreat = threatType;
  document.querySelectorAll('.threat-card').forEach(c => {
    c.classList.toggle('active', c.dataset.threat === threatType);
    c.setAttribute('aria-pressed', String(c.dataset.threat === threatType));
  });
  const tamperedGroup = document.getElementById('tamperedGroup');
  if (tamperedGroup) tamperedGroup.style.display = threatType === 'message_tampering' ? 'block' : 'none';
  const badge = document.getElementById('activeThreatBadge');
  if (badge) {
    badge.textContent = threatType.toUpperCase();
    badge.classList.toggle('danger', threatType !== 'authentic');
  }
}

function initComposer() {
  const form = document.getElementById('signForm');
  const bitSelect = document.getElementById('bitDepth');
  const previewBox = document.getElementById('tokenPreview');

  function renderPreview(n, symbols) {
    previewBox.innerHTML = '';
    const cls = { '|0⟩': 'token-z0', '|1⟩': 'token-z1', '|+⟩': 'token-x0', '|−⟩': 'token-x1' };
    for (let i = 0; i < n; i++) {
      const sym = symbols ? symbols[i] : '?';
      const span = document.createElement('span');
      span.className = `qubit-token ${cls[sym] || ''}`;
      span.textContent = `Q${i}: ${sym}`;
      previewBox.appendChild(span);
    }
  }
  window.renderTokenPreview = renderPreview;
  renderPreview(parseInt(bitSelect.value), null);
  bitSelect.addEventListener('change', () => renderPreview(parseInt(bitSelect.value), null));
  initHashPreview();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btnSign');
    const tampered = document.getElementById('tamperedText');
    btn.disabled = true;
    btn.innerHTML = `${icon('loader', 'spin')} Teleporting & signing...`;
    try {
      const { status, data } = await api('/api/sign-and-send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message_text: document.getElementById('messageText').value,
          n_bits: parseInt(bitSelect.value),
          threat_type: currentThreat,
          tampered_text: tampered ? tampered.value : null
        })
      }, 'admin');
      if (status === 423) {
        logTerminal('BLOCK', `Refused in ${data.refusal_us} µs: link ${data.link} is quarantined ` +
          `(${data.detail.reason}; incident ${data.detail.incident_id}). Reset it with a reason to continue.`);
        refreshTopology();
      } else {
        data.transmissions.forEach(tx =>
          logTerminal('TX', `${tx.transmission_id} dispatched | ${tx.n_bits} qubits | injected: ${tx.ground_truth.injected_scenario}`));
        const last = data.transmission;
        if (last.alice) renderPreview(last.alice.state_symbols.length, last.alice.state_symbols);
        if (last.context) showCommittedDigest(last.context.message_digest);
      }
    } catch (err) {
      logTerminal('ERR', `Transmission failed: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${icon('zap')} Quantum Sign & Transmit Token`;
    }
  });
}

// Mirrors binding.message_digest(): SHA-256("HEDWIG-QDS-v2|message|" || UTF-8(message)).
const MESSAGE_DOMAIN = 'HEDWIG-QDS-v2|message|';
let currentDigest = null;
let committedDigest = null;

async function messageDigest(text) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(MESSAGE_DOMAIN + text));
  return Array.from(new Uint8Array(buf), b => b.toString(16).padStart(2, '0')).join('');
}

function initHashPreview() {
  const msgArea = document.getElementById('messageText');
  const digestEl = document.getElementById('hashDigest');
  const copyBtn = document.getElementById('hashCopy');
  if (!crypto.subtle) {   // only available in secure contexts (https or localhost)
    digestEl.textContent = 'Unavailable: page is not served over HTTPS';
    copyBtn.hidden = true;
    return;
  }
  let seq = 0;
  const update = async () => {
    const mine = ++seq;
    const hex = await messageDigest(msgArea.value);
    if (mine !== seq) return;   // a newer keystroke already started
    currentDigest = hex;
    digestEl.textContent = hex;
    markCommittedMatch();
  };
  msgArea.addEventListener('input', update);
  copyBtn.addEventListener('click', async () => {
    if (!currentDigest) return;
    try {
      await navigator.clipboard.writeText(currentDigest);
      copyBtn.textContent = 'Copied';
    } catch (e) {
      copyBtn.textContent = 'Failed';
    }
    setTimeout(() => { copyBtn.textContent = 'Copy'; }, 1200);
  });
  update();
}

function showCommittedDigest(hex) {
  committedDigest = hex;
  document.getElementById('hashCommitted').textContent = hex;
  markCommittedMatch();
}

function markCommittedMatch() {
  const el = document.getElementById('hashCommitted');
  if (!committedDigest) return;
  const match = committedDigest === currentDigest;
  el.classList.toggle('match', match);
  el.classList.toggle('stale', !match);
  el.title = match ? 'Matches the message above' : 'Message edited since this was committed';
}

function verifierSummary(name, v) {
  if (!v) return `<span>${name}: —</span>`;
  const cls = v.is_valid ? 'v-accept' : 'v-reject';
  const mode = v.mode === 'forwarded' ? ` via ${escapeHtml(v.forwarded_by)}` : '';
  return `<span class="${cls}">${name}${mode}: ${v.is_valid ? 'ACCEPT' : 'REJECT'} ` +
         `${v.mismatches}/${v.total_checked}≤${v.acceptance_limit}</span>`;
}

function handleNewTransmission(tx) {
  if (seenTx.has(tx.transmission_id)) return;
  seenTx.add(tx.transmission_id);
  const container = document.getElementById('recentTxList');
  if (!container) return;
  if (seenTx.size === 1) container.innerHTML = '';

  const report = tx.threat_report;
  const injected = (tx.ground_truth && tx.ground_truth.injected_scenario) || 'unknown';
  const isThreat = report.is_threat_detected;
  const injectedAttack = injected !== 'authentic';
  const outcome = injectedAttack === isThreat
    ? (isThreat ? 'attack detected' : 'honest accepted')
    : (isThreat ? 'FALSE ALARM' : 'ATTACK MISSED');
  const channel = tx.channel
    ? `QBER^ ${(tx.channel.qber_estimate * 100).toFixed(1)}% (${tx.channel.error_count}/${tx.channel.test_count}, alarm >${tx.channel.alarm_threshold_errors}, p=${fmtP(tx.channel.p_value)})` +
      (tx.channel.early_abort ? ` · EARLY ABORT ${tx.channel.tokens_sent}/${tx.channel.tokens_planned} tokens` : '')
    : 'no channel test';
  const t2 = report.tier2 && report.tier2.applicable ? `Tier 2: ${report.tier2.attribution}` : '';
  const resp = tx.response ? `${tx.response.response_action} (p=${fmtP(tx.response.evidence_p)})` : tx.enforcement.action;
  const incident = tx.enforcement.incident_id
    ? `<a href="/api/audit/${encodeURIComponent(tx.enforcement.incident_id)}" target="_blank" class="incident-link">${icon('download', 'icon-sm')}incident ${escapeHtml(tx.enforcement.incident_id)}</a>` : '';

  const row = document.createElement('div');
  row.className = 'dispatch-item';
  row.innerHTML = `
    <div class="dispatch-head">
      <span class="dispatch-id">${escapeHtml(tx.transmission_id)}</span>
      <span class="dispatch-class ${isThreat ? 'bad' : 'ok'}">${escapeHtml(report.classification)}</span>
    </div>
    <div class="dispatch-msg">"${escapeHtml(tx.message_text)}"</div>
    <div class="dispatch-meta">
      ${verifierSummary('Bob', tx.bob)}
      ${verifierSummary('Charlie', tx.charlie)}
      <span>${channel}</span>
    </div>
    <div class="dispatch-links">
      <span>injected: <strong>${escapeHtml(injected)}</strong></span>
      <span class="${outcome === outcome.toUpperCase() ? 'outcome-flag' : ''}">${outcome}</span>
      <span>${escapeHtml(tx.enforcement.action)} → ${escapeHtml(resp)}</span>
      ${t2 ? `<span>${escapeHtml(t2)}</span>` : ''}
      <a href="/api/audit/${encodeURIComponent(tx.transmission_id)}" target="_blank">${icon('download', 'icon-sm')}audit</a>
      ${incident}
    </div>`;
  container.prepend(row);
  logTerminal('RECV', `${tx.transmission_id}: ${report.verdict}`);
  renderLinks(tx.enforcement.channel_state);
}

function renderLinks(channelState) {
  if (!channelState) return;
  renderChannelBanner(channelState);
  const el = document.getElementById('linkStates');
  if (!el) return;
  el.innerHTML = Object.entries(channelState).map(([link, s]) =>
    `<span class="link-chip ${s.state}">${escapeHtml(link)}: ${s.state.replace('_', ' ').toUpperCase()}` +
    `${s.strikes ? ` · strikes ${s.strikes}` : ''}${s.refused ? ` · refused ${s.refused}` : ''}</span>`).join('');
}

async function resetLinks() {
  const reason = window.prompt('Reason for resetting the quarantined / watched links (kept in the signed audit chain):');
  if (!reason || reason.trim().length < 3) {
    logTerminal('ERR', 'Reset cancelled: a reason of at least 3 characters is required.');
    return;
  }
  try {
    const { data } = await api('/api/channel/reset', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: reason.trim() })
    }, 'admin');
    renderLinks(data.channel_state);
    refreshTopology();
    const n = (data.transitions || []).length;
    logTerminal('SYS', n
      ? `${n} link(s) reset by admin ("${reason.trim()}"): quarantined → probation, watch → open. Signed reset record #${data.reset_record.chain_seq}.`
      : 'No link needed a reset.');
  } catch (err) {
    logTerminal('ERR', `Reset failed: ${err.message}`);
  }
}

const HOP_COLOURS = { up: 'var(--success-ink)', degraded: 'var(--warning-ink)', probation: 'var(--info-ink)', down: 'var(--danger-ink)' };

async function refreshTopology() {
  try {
    const { data } = await api('/api/topology', {}, 'admin');
    renderTopology(data.router);
  } catch (e) { /* informational */ }
}

function renderTopology(router) {
  const svg = document.getElementById('topologySvg');
  if (!svg || !router) return;
  const pos = { alice: [50, 95], 'QR-1': [220, 95], bob: [400, 38], charlie: [400, 152] };
  const hops = router.hops;
  const line = (name, a, b, bend) => {
    const h = hops[name];
    const c = HOP_COLOURS[h.state] || 'var(--ink-muted)';
    const [x1, y1] = pos[a], [x2, y2] = pos[b];
    const mx = (x1 + x2) / 2 + (bend || 0), my = (y1 + y2) / 2;
    const path = bend ? `M${x1},${y1} Q${mx},${my} ${x2},${y2}` : `M${x1},${y1} L${x2},${y2}`;
    const dash = h.kind === 'classical' ? ' stroke-dasharray="5 4"' : '';
    const main = `${escapeHtml(h.state)} · ${h.tokens_carried} tok`;
    const drop = h.dropped ? ` · ${h.dropped} dropped` : '';
    let label;
    if (bend) {
      // Beside the curve's midpoint, on the inner side so it stays inside the viewBox.
      const cx = (x1 + 2 * mx + x2) / 4, cy = (y1 + 2 * my + y2) / 4;
      label = `<text class="hop-label" text-anchor="end" x="${cx - 8}" y="${cy - 2}">${main}` +
        (drop ? `<tspan x="${cx - 8}" dy="12">${drop.slice(3)}</tspan>` : '') + `</text>`;
    } else {
      // Centred along the line: state and tokens above it, drop count below it.
      const ang = (Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI).toFixed(1);
      label = `<text class="hop-label" text-anchor="middle" transform="translate(${mx},${my}) rotate(${ang})">` +
        `<tspan x="0" y="-8">${main}</tspan>` + (drop ? `<tspan x="0" y="16">${drop.slice(3)}</tspan>` : '') + `</text>`;
    }
    return `<path d="${path}" fill="none" stroke="${c}" stroke-width="${h.state === 'down' ? 3 : 2}"${dash}/>` + label;
  };
  const node = (name, label) => {
    const [x, y] = pos[name];
    return `<circle cx="${x}" cy="${y}" r="18" fill="var(--surface, #ffffff)" stroke="var(--primary)" stroke-width="2"/>` +
      `<text x="${x}" y="${y + 4}" text-anchor="middle">${label}</text>`;
  };
  svg.innerHTML =
    line('alice->QR-1', 'alice', 'QR-1') + line('QR-1->bob', 'QR-1', 'bob') + line('QR-1->charlie', 'QR-1', 'charlie') +
    line('bob->charlie', 'bob', 'charlie', 60) +
    node('alice', 'A') + node('QR-1', 'QR') + node('bob', 'B') + node('charlie', 'C');
}

async function loadIncidents() {
  try {
    const { data } = await api('/api/incidents', {}, 'admin');
    const el = document.getElementById('incidentList');
    if (!el) return;
    const items = (data.incidents || []).slice(-6).reverse();
    el.innerHTML = items.length ? items.map(c => {
      const r = c.record;
      return `<div class="incident-item">${icon('ban', 'icon-sm')}<div><strong>${escapeHtml(r.incident_id)}</strong> · ${escapeHtml(r.link)} · ` +
        `${escapeHtml(r.trigger.classification)} (p=${fmtP(r.trigger.evidence_p)}) · ` +
        `${new Date(r.issued_at * 1000).toLocaleTimeString()} · chain #${r.chain.seq} ` +
        `<a href="/api/audit/${encodeURIComponent(r.incident_id)}" target="_blank">${icon('download', 'icon-sm')}record</a></div></div>`;
    }).join('') : '<div class="truth-row">No incidents.</div>';
  } catch (e) { /* informational */ }
}

async function checkChain() {
  try {
    const { data } = await api('/api/audit/chain', {}, 'admin');
    const v = data.verification;
    const pq = (data.certificates || []).some(c => (c.signatures || []).some(s => s.post_quantum));
    document.getElementById('chainRow').textContent =
      `Chain: ${v.length} signed artifact(s) · ${v.valid ? 'ALL SIGNATURES AND HASH LINKS VALID' : `${v.problems.length} PROBLEM(S)`}` +
      ` · ${pq ? 'hybrid Ed25519 + ML-DSA-65' : 'Ed25519 (classical)'}`;
    logTerminal(v.valid ? 'SYS' : 'ERR', `Audit chain check: ${v.valid ? 'valid' : JSON.stringify(v.problems.slice(0, 3))}`);
  } catch (err) {
    logTerminal('ERR', `Chain check failed: ${err.message}`);
  }
}

function updateStatsDisplay(stats) {
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('statTotal', stats.total_sent);
  set('statAuth', stats.verified_authentic);
  set('statThreat', stats.threats_detected);
  set('statQber', `${(stats.last_qber * 100).toFixed(1)}%`);
  set('statTruth', `Injected attacks: ${stats.attacks_injected} · missed: ${stats.attacks_missed} · false alarms: ${stats.false_alarms}` +
    ` · watch: ${stats.watch_events ?? 0} · quarantines: ${stats.quarantines ?? 0} · early aborts: ${stats.early_aborts ?? 0} · refused: ${stats.refused_sends ?? 0}`);
}

async function refreshMetrics() {
  try {
    const { data } = await api('/api/metrics', {}, 'admin');
    const l = data.latency;
    const fmt = s => s && s.count ? `p50 ${s.p50} / p95 ${s.p95}` : '—';
    const item = (label, s) => `<div><dt>${label}</dt><dd>${escapeHtml(fmt(s))}</dd></div>`;
    document.getElementById('latencyRow').innerHTML =
      `<div class="latency-head">Latency (${escapeHtml(data.backend)}; n=${l.detection_us.count || 0})</div><dl class="latency-grid">` +
      item('Channel observation (ms)', l.channel_observation_ms) + item('Detection (µs)', l.detection_us) +
      item('Post-verdict enforcement (µs)', l.enforcement_us) + item('Incident signing (µs)', l.incident_signing_us) +
      item('423 refusal (µs)', l.refusal_us) + item('Full run (ms)', l.protocol_ms) + `</dl>`;
  } catch (e) { /* metrics are informational */ }
}

async function loadHistory() {
  try {
    const { data } = await api('/api/history', {}, 'admin');
    if (data.stats) updateStatsDisplay(data.stats);
    renderLinks(data.channel_state);
    (data.transmissions || []).slice(-5).forEach(tx => handleNewTransmission(tx));
  } catch (e) {
    console.error('History load error:', e);
  }
}

function logTerminal(prefix, msg) {
  const term = document.getElementById('terminalLog');
  if (!term) return;
  const line = document.createElement('div');
  line.className = 'log-entry';
  let cls = '';
  if (['ARMED', 'ERR', 'SEC', 'BLOCK'].includes(prefix)) cls = 'log-threat';
  if (prefix === 'TX' || prefix === 'RECV') cls = 'log-success';
  line.innerHTML = `<span class="log-ts">[${new Date().toLocaleTimeString()}]</span> ` +
                   `<span class="log-prefix">${prefix}</span> <span class="${cls}">${escapeHtml(msg)}</span>`;
  term.appendChild(line);
  term.scrollTop = term.scrollHeight;
}
