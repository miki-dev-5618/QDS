// Shared helpers for all HEDWIG terminals.
function icon(name, cls = '') {
  const px = cls.includes('icon-sm') ? 14 : 18;
  return `<svg class="icon ${cls}" width="${px}" height="${px}" aria-hidden="true"><use href="/static/img/icons.svg?v=2.3#i-${name}"/></svg>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

async function api(url, options = {}, role = null) {
  const res = await fetch(url, { credentials: 'same-origin', ...options });
  if (res.status === 401 && role) {
    window.location.href = `/login?role=${role}&next=${encodeURIComponent(window.location.pathname)}`;
    throw new Error('Session expired');
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON body */ }
  if (!res.ok && res.status !== 423) {
    throw new Error((data && (data.detail || data.message)) || `HTTP ${res.status}`);
  }
  return { status: res.status, data };
}

function connectSocket(role, onMessage, onStatus) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${role}`);
  ws.onopen = () => onStatus(true);
  ws.onmessage = (event) => {
    try { onMessage(JSON.parse(event.data)); } catch (e) { console.error('WS parse error:', e); }
  };
  ws.onclose = (event) => {
    onStatus(false);
    if (event.code === 4401) {
      window.location.href = `/login?role=${role}&next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }
    setTimeout(() => connectSocket(role, onMessage, onStatus), 2000);
  };
  return ws;
}

function setConnectionBadge(online, onlineText) {
  const dot = document.getElementById('connDot');
  const text = document.getElementById('connText');
  if (!dot || !text) return;
  dot.classList.toggle('danger', !online);
  text.textContent = online ? onlineText : 'RECONNECTING';
}

function renderChannelBanner(channelState) {
  const el = document.getElementById('channelBanner');
  if (!el || !channelState) return;
  const rows = Object.entries(channelState).filter(([, s]) => s.state !== 'open');
  if (!rows.length) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = 'block';
  el.innerHTML = rows.map(([link, s]) => {
    if (s.state === 'quarantined') {
      return `<div class="banner-quarantined">${icon('ban')}<span>LINK <strong>${escapeHtml(link)}</strong> QUARANTINED — ${escapeHtml(s.reason)} ` +
        `(${escapeHtml(s.transmission_id)}; incident ${escapeHtml(s.incident_id || '—')}; ` +
        `${s.purged_records} unaccepted record(s) purged). New transmissions are refused until an admin ` +
        `resets it with a reason.</span></div>`;
    }
    if (s.state === 'watch') {
      const until = s.watch_until ? new Date(s.watch_until * 1000).toLocaleTimeString() : '—';
      return `<div class="banner-watch">${icon('alert')}<span>LINK <strong>${escapeHtml(link)}</strong> ON WATCH — ` +
        `${escapeHtml(s.reason)} (strike ${s.strikes}; combined evidence p = ${fmtP(s.combined_p)}; window until ` +
        `${until}). Traffic flows with a doubled test-token budget; the link is quarantined if the accumulated ` +
        `evidence reaches p ≤ 0.01 or three alerts accumulate.</span></div>`;
    }
    return `<div class="banner-probation">${icon('rotate')}<span>LINK <strong>${escapeHtml(link)}</strong> ON PROBATION after reset by ` +
      `${escapeHtml(s.reset_by || 'admin')} ("${escapeHtml(s.reset_reason || '')}"). One fully accepted ` +
      `transmission reopens it; any quantum-evidence alert re-quarantines it.</span></div>`;
  }).join('');
}

function fmtP(p) {
  if (p === null || p === undefined) return '—';
  return p === 0 ? '0' : (p < 0.001 ? Number(p).toExponential(1) : Number(p).toFixed(3));
}

function renderTierPanel(tx) {
  const r = tx.threat_report || {};
  const t1 = r.tier1, t2 = r.tier2, resp = tx.response;
  const tag = (text, cls) => `<span class="tag ${cls}">${escapeHtml(text)}</span>`;
  let html = '';
  if (t1) {
    const abort = t1.early_abort ? `<div>Early abort: stream stopped after ${t1.tokens_sent}/${t1.tokens_planned} tokens</div>` : '';
    html += `<div class="tier-card"><strong>Tier 1 · channel test</strong>${t1.alarm ? tag('ALARM', 'bad') : tag('pass', 'ok')}
      <div>k/n = ${t1.error_count}/${t1.test_count} (planned ${t1.planned_test_count}) · p₀ = ${t1.honest_qber_assumption}</div>
      <div>alarm if k &gt; ${t1.alarm_threshold_errors} (α = ${t1.false_alarm_alpha}; exact level ${fmtP(t1.exact_false_alarm_level)}; Chernoff–KL bound ${fmtP(t1.chernoff_kl_bound)})</div>
      <div>p-value = ${fmtP(t1.p_value)} · QBER^ ${(t1.qber_estimate * 100).toFixed(1)}% [${(t1.qber_ci_low * 100).toFixed(1)}, ${(t1.qber_ci_high * 100).toFixed(1)}]</div>${abort}</div>`;
  }
  if (t2 && t2.applicable) {
    const cls = t2.attribution === 'signature_inconsistency' ? 'bad' : t2.attribution === 'channel_disturbance' ? 'warn' : t2.attribution === 'undetermined' ? 'warn' : 'ok';
    html += `<div class="tier-card"><strong>Tier 2 · disturbance pattern</strong>${tag(t2.attribution, cls)}
      <div>contradictions ${t2.contradictions}/${t2.copies} copies vs test errors ${t2.test_errors}/${t2.test_tokens}</div>
      <div>p_excess = ${fmtP(t2.p_excess)} (α₂ ${t2.alpha2}) · p_channel = ${fmtP(t2.p_channel)} (β ${t2.beta})</div>
      <div>KL from honest reference: ${t2.kl_nats} nats (diagnostic only)</div></div>`;
  }
  if (resp) {
    const cls = resp.response_action === 'quarantine' ? 'bad' : resp.response_action === 'watch' ? 'warn' : 'ok';
    const inc = tx.enforcement && tx.enforcement.incident_id
      ? `<div>Incident <a href="/api/audit/${encodeURIComponent(tx.enforcement.incident_id)}" target="_blank">${icon('download', 'icon-sm')}${escapeHtml(tx.enforcement.incident_id)}</a> (signed at quarantine time)</div>` : '';
    html += `<div class="tier-card"><strong>Response policy</strong>${tag(resp.response_action, cls)}
      <div>verdict: ${escapeHtml(resp.verdict)} · severity: ${escapeHtml(resp.severity)} · evidence p = ${fmtP(resp.evidence_p)}</div>
      <div>${escapeHtml(resp.reason)}</div>${inc}</div>`;
  }
  return html;
}

function getStateSymbol(bit, basis) {
  if (basis === 0) return bit === 0 ? '|0⟩' : '|1⟩';
  return bit === 0 ? '|+⟩' : '|−⟩';
}

document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-logout]');
  if (!el) return;
  e.preventDefault();
  try { await fetch(`/api/logout?role=${el.dataset.logout}`, { method: 'POST' }); } catch (err) { /* ignore */ }
  window.location.href = `/login?role=${el.dataset.logout}`;
});
