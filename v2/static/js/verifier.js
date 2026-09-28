// Shared dashboard for Bob and Charlie. window.HEDWIG_ROLE selects the verifier.
const ROLE = window.HEDWIG_ROLE;

const CHECK_LABELS = {
  distribution_record_found: 'Distribution record for session',
  sender_matches_record: 'Sender matches authenticated distributor',
  addressed_to_verifier: 'Addressed to this verifier',
  session_not_aborted: 'Channel test passed at distribution',
  fresh: 'Fresh (nonce unused, timestamp in window)',
  elimination_pass: 'Elimination mismatches within limit',
  message_digest_matches: 'Message SHA-256 matches signed context',
  commitment_matches: 'Matches signer commitment',
};

document.addEventListener('DOMContentLoaded', () => {
  connectSocket(ROLE, handleMessage,
    online => setConnectionBadge(online, ROLE === 'bob' ? 'ONLINE / LISTENING' : 'ONLINE / AUDITING'));
});

function handleMessage(msg) {
  if (msg.event === 'init_sync') {
    renderChannelBanner(msg.data.channel_state);
    const txs = msg.data.transmissions || [];
    if (txs.length) renderTransmission(txs[txs.length - 1]);
  } else if (msg.event === 'new_transmission') {
    renderTransmission(msg.data.transmission);
  } else if (msg.event === 'channel_state') {
    renderChannelBanner(msg.data);
  }
}

function renderTransmission(tx) {
  if (tx.enforcement) renderChannelBanner(tx.enforcement.channel_state);
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('activeContent').style.display = 'block';

  const v = tx[ROLE];
  const report = tx.threat_report;
  const banner = document.getElementById('verdictBanner');

  if (!v) {
    // This verifier took no part (e.g. Bob's forward was checked by Charlie only).
    banner.className = 'verdict-banner threat';
    document.getElementById('verdictIcon').innerHTML = icon('forward');
    const aborted = tx.revealed === false && tx.channel && tx.channel.alarm;
    document.getElementById('verdictTitle').textContent = aborted
      ? `${tx.transmission_id}: SESSION ABORTED AT DISTRIBUTION (NOTHING REVEALED)`
      : `${tx.transmission_id}: NOT VERIFIED BY ${ROLE.toUpperCase()}`;
    document.getElementById('verdictSubtitle').textContent =
      `${report.verdict} — ${report.details}`;
    document.getElementById('mismatchesVal').textContent = '—';
    document.getElementById('qberVal').textContent = tx.channel
      ? `${(tx.channel.qber_estimate * 100).toFixed(1)}% (${tx.channel.error_count}/${tx.channel.test_count})` : '—';
    document.getElementById('verifiedMsgText').textContent = tx.message_text;
    document.getElementById('matrixBody').innerHTML = '';
    document.getElementById('checksList').innerHTML = '';
    document.getElementById('certCard').innerHTML = '';
    renderAudit(tx);
    return;
  }

  const ok = v.is_valid;
  banner.className = `verdict-banner ${ok ? 'verified' : 'threat'}`;
  document.getElementById('verdictIcon').innerHTML = icon(ok ? 'check' : 'alert');
  const mode = v.mode === 'forwarded' ? ` (FORWARDED BY ${String(v.forwarded_by).toUpperCase()})` : '';
  document.getElementById('verdictTitle').textContent =
    (ok ? `${ROLE.toUpperCase()} ACCEPTS SIGNATURE` : `${ROLE.toUpperCase()} REJECTS: ${report.classification}`) + mode;
  document.getElementById('verdictSubtitle').textContent = ok
    ? `All checks passed. ${v.mismatches} mismatch(es) in ${v.total_checked} measured copies (limit ${v.acceptance_limit}).`
    : report.details;
  document.getElementById('mismatchesVal').textContent =
    `${v.mismatches} / ${v.total_checked} (≤${v.acceptance_limit})`;
  document.getElementById('qberVal').textContent = tx.channel
    ? `${(tx.channel.qber_estimate * 100).toFixed(1)}% (${tx.channel.error_count}/${tx.channel.test_count})`
    : 'n/a';
  document.getElementById('verifiedMsgText').textContent = v.received_message;

  renderChecks(v);
  renderMatrix(tx, v);
  renderBounds(v.bounds);
  renderAudit(tx);
}

function renderChecks(v) {
  const list = document.getElementById('checksList');
  const items = Object.entries(CHECK_LABELS).map(([key, label]) => {
    const pass = !!v.checks[key];
    const extra = key === 'fresh' ? ` <span class="check-note">(${escapeHtml(v.checks.freshness_reason)})</span>` : '';
    return `<div class="check-item ${pass ? 'pass' : 'fail'}"><span>${icon(pass ? 'check' : 'x')}</span>` +
           `<span>${label}${extra}</span></div>`;
  });
  const reasons = (v.reasons || []).map(r => `<li>${escapeHtml(r)}</li>`).join('');
  list.innerHTML = items.join('') + (reasons ? `<ul class="reason-list">${reasons}</ul>` : '');
}

function renderMatrix(tx, v) {
  const tbody = document.getElementById('matrixBody');
  tbody.innerHTML = '';
  const n = Math.max(v.eliminated_states.length, v.revealed_signature.length);
  for (let i = 0; i < n; i++) {
    const held = (v.held_tokens[i] || []).join(', ');
    const elim = v.eliminated_states[i] || [];
    const revealed = v.revealed_signature[i];
    const sym = revealed ? getStateSymbol(revealed[0], revealed[1]) : '—';
    const hits = elim.filter(s => s === sym).length;
    const tr = document.createElement('tr');
    if (hits) tr.className = 'collision-row';
    tr.innerHTML = `
      <td>#${i}</td>
      <td>${escapeHtml(held) || '<span class="cell-muted">none held</span>'}</td>
      <td>${elim.map(s => `<span class="elim-badge">${s}</span>`).join('') || '<span class="cell-muted">—</span>'}</td>
      <td class="cell-revealed">${sym}</td>
      <td><span class="${hits ? 'status-bad' : (elim.length ? 'status-ok' : 'status-none')}">
        ${hits ? `✗ ${hits} MISMATCH` : (elim.length ? '✓ CONSISTENT' : '— NOT CHECKED')}</span></td>`;
    tbody.appendChild(tr);
  }
}

function renderBounds(b) {
  const card = document.getElementById('certCard');
  if (!b) { card.innerHTML = ''; return; }
  const cell = (label, value) =>
    `<div class="cert-cell"><span class="cert-cell-label">${label}</span><span class="cert-cell-value">${value}</span></div>`;
  card.innerHTML =
    cell('Copies checked (n)', b.inputs.n_checked_copies) +
    cell(`Limit rate (${b.mode === 'forwarded' ? 's_v' : 's_a'})`, b.inputs.limit_rate_used) +
    cell('Accept if mismatches ≤', b.acceptance_limit) +
    cell('P(false reject) ≤', b.values.false_reject) +
    cell('P(forgery accepted) ≤', b.values.forgery_accept) +
    cell('P(repudiation) ≤', b.values.repudiation) +
    `<div class="cert-note">
      <div><strong>Rule:</strong> ${escapeHtml(b.decision_rule)}</div>
      <div><strong>n needed for ${b.target_failure}:</strong> ${b.n_required_for_target} copies
        ${b.meets_target ? '(met)' : '<span class="warn-text">(not met at this signature length)</span>'}</div>
      <div><strong>Inputs:</strong> e0=${b.inputs.e0_honest_qber}, μ_h=${b.inputs.mu_honest}, p_min=${b.inputs.p_min_forger},
        s_a=${b.inputs.s_a}, s_v=${b.inputs.s_v}</div>
      <details><summary>Assumptions (${escapeHtml(b.status)})</summary>
        <ul>${b.assumptions.map(a => `<li>${escapeHtml(a)}</li>`).join('')}</ul></details>
    </div>`;
}

function renderAudit(tx) {
  const el = document.getElementById('auditRow');
  if (!el) return;
  const l = tx.latency || {};
  const a = tx.audit;
  const auditInfo = a
    ? `chain #${a.chain_seq} · ${a.post_quantum ? 'Ed25519 + ML-DSA-65 (hybrid)' : 'Ed25519 (classical)'} · ${escapeHtml(a.assurance)}`
    : 'not issued';
  el.innerHTML = `<a class="nav-btn" href="/api/audit/${encodeURIComponent(tx.transmission_id)}" target="_blank">
    ${icon('download', 'icon-sm')} Signed audit record (${escapeHtml(tx.transmission_id)})</a>
    <span class="check-note">${auditInfo}</span>
    <span class="check-note">channel observation ${l.channel_observation_ms ?? '—'} ms · detection ${l.detection_us} µs ·
      post-verdict enforcement ${l.enforcement_us} µs${l.incident_signing_us ? ` · incident signing ${l.incident_signing_us} µs` : ''}</span>
    <div class="tier-panel">${renderTierPanel(tx)}</div>`;
}
