/* Views consume frozen route records. Current configuration never redraws history. */
let routingLive = null;
let routingSessions = [];
const routingColours = {open: '#22c55e', watch: '#f59e0b', quarantined: '#ef4444', reset_pending: '#38bdf8'};
const routeEl = id => document.getElementById(id);
const re = value => escapeHtml(String(value ?? '—'));
const routeTable = (head, rows) => `<table class="matrix-table"><thead><tr>${head.map(h => `<th>${re(h)}</th>`).join('')}</tr></thead><tbody>` +
  (rows.length ? rows.map(row => `<tr>${row.map(c => `<td>${re(c)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${head.length}">No recorded execution yet.</td></tr>`) + '</tbody></table>';
const routePct = n => `${(100 * n).toFixed(2)}%`;

function routingScopeLabel(scope) {
  if (CLASSICAL_SCOPES[scope]) return CLASSICAL_SCOPES[scope].name;
  const edge = routingLive?.edges.find(e => e.scope === scope);
  if (edge) return edge.id;
  for (const row of routingSessions) {
    const route = Object.values(row.plan.routes).find(r => r.route_id === scope);
    if (route) return route.nodes.join(' → ');
  }
  return scope.startsWith('edge:') ? 'Historical edge restriction' : scope.startsWith('path:') ? 'Historical route restriction' : scope;
}

function renderRouteRefusal(data) {
  routeEl('routingMessage').textContent = `${data.message} · ${data.detail.reason || data.status}`;
  routeEl('routeRefusal').innerHTML = '<p class="section-note">Latest recorded preflight refusal' +
    (data.timestamp ? ` · ${re(new Date(data.timestamp*1000).toLocaleString())}` : '') + '</p>' +
    routeTable(['Recipient', 'Blocked candidate / edge', 'Reason', 'Search complete'],
    Object.entries(data.detail.candidates || {}).flatMap(([v, d]) => d.rejected.length ? d.rejected.map(c =>
      [v, c.edge || c.edges?.join(' → '), c.reason, d.search_complete ? 'yes' : 'no (work limit reached)']) :
      [[v, 'No candidate', d.reason || data.detail.reason, d.search_complete ? 'yes' : 'no (work limit reached)']]));
}

// ---------------------------------------------- shared by the console strip and the routing page
// Groups recipients that share a relay path: "alice → R1 → R2 → bob, charlie (3 hops)".
function routeGroups(routes) {
  const groups = {};
  Object.entries(routes || {}).forEach(([v, r]) => {
    const key = r.nodes.slice(0, -1).join(' → ');
    (groups[key] ||= {hops: r.hops, recipients: []}).recipients.push(v);
  });
  return Object.entries(groups).map(([path, g]) => `${path} → ${g.recipients.join(', ')} (${g.hops} hop${g.hops === 1 ? '' : 's'})`).join(' · ');
}

function setNextRoute(text, badge, tone) {
  const summary = routeEl('nextRouteSummary'), pill = routeEl('nextRouteBadge');
  if (summary) summary.textContent = text;
  if (pill) {
    pill.textContent = badge;
    pill.classList.toggle('neutral', tone === 'neutral');
    pill.classList.toggle('danger', tone === 'danger');
  }
}

async function refreshRoutingPreview() {
  if (!routeEl('nextRouteSummary')) return;
  const body = typeof routingPreviewConfig === 'function' ? routingPreviewConfig() : {};
  try {
    const {data} = await api('/api/routing/preview', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}, 'admin');
    if (data.status === 'ready') {
      const rerouted = Object.values(data.plan.routes).some(r => r.rerouted);
      setNextRoute(routeGroups(data.plan.routes), rerouted ? 'Rerouted' : 'Ready', 'neutral');
    } else {
      setNextRoute(`${data.message || 'No eligible route'} · ${data.detail?.reason || data.status}`, 'Blocked', 'danger');
    }
  } catch (err) { setNextRoute(err.message, 'Unavailable', 'danger'); }
}

function renderLinks(channelState) {
  if (!channelState) return;
  renderChannelBanner(channelState);
  const el = routeEl('linkStates');
  if (!el) return;
  // Compact views list only restricted links; open edges are visible on the route graph.
  const compact = el.hasAttribute('data-compact');
  const rows = Object.entries(channelState).filter(([link, s]) =>
    compact ? s.state !== 'open' : !link.startsWith('edge:') && !link.startsWith('path:') || s.state !== 'open');
  el.innerHTML = rows.length ? rows.map(([link, s]) =>
    `<span class="link-chip ${s.state}">${escapeHtml(routingScopeLabel(link))}: ${s.state.replace('_', ' ').toUpperCase()}` +
    `${s.strikes ? ` · strikes ${s.strikes}` : ''}${s.refused ? ` · refused ${s.refused}` : ''}</span>`).join('') :
    '<span class="link-chip open">All links open</span>';
}

async function refreshTopology() {
  try {
    const {data} = await api('/api/topology', {}, 'admin');
    await renderRouting(data);
    renderLinks(data.channel_state);
  } catch (e) { /* informational */ }
  refreshRoutingPreview();
}

// ---------------------------------------------- qubit flow (latest send, per verifier)
// Replays a finished send hop by hop: the server reports a session once distribution completes.
function renderQubitFlow(tx, animate) {
  const box = routeEl('qubitFlow');
  if (!box || !tx) return;
  const plan = tx.routing?.plan, execution = tx.routing?.execution;
  const verdicts = Object.fromEntries((tx.participants || []).map(p => [p.verifier, p.status]));
  routeEl('flowSession').textContent = `${tx.transmission_id} · ${new Date((execution?.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString()}` +
    (execution ? ` · distribution ${execution.status}${execution.abort_reason ? ` (${execution.abort_reason.replace(/_/g, ' ')})` : ''}` : '');
  // Links the post-alarm probes located and restricted for this send.
  const enf = tx.enforcement || {};
  const located = new Set([enf.transition, ...(enf.route_transitions || [])].filter(t => t && t.link?.startsWith('edge:') &&
    ['quarantined', 'watch'].includes(t.new_state)).map(t => t.link));
  const scopeId = Object.fromEntries(Object.entries(plan?.edge_scope_map || {}).map(([id, scope]) => [scope, id]));
  const alert = routeEl('flowAlert');
  if (alert) {
    const names = [...located].map(s => (scopeId[s] || 'link').replace('->', ' → '));
    alert.hidden = !enf.attribution;
    alert.className = `flow-alert ${names.length ? 'located' : ''}`;
    alert.textContent = names.length ? `Attack located on ${names.join(', ')} — quarantined automatically. Fresh sends route around it, or are refused if no other path exists.` :
      enf.attribution ? `Qubit attack detected, but no single link failed its probe (${enf.attribution}).` : '';
  }
  if (!plan) { box.innerHTML = '<p class="section-note">This send has no routing record.</p>'; return; }
  box.innerHTML = Object.entries(plan.routes).map(([v, r], lane) => {
    const stats = execution?.recipients?.[v] || {};
    const stopAt = r.edge_scopes.indexOf(execution?.stopping_scope);
    let track = `<span class="flow-node signer">${re(r.nodes[0])}</span>`;
    r.edges.forEach((eid, hop) => {
      const c = stats.edges?.[eid];
      const cls = (stopAt === hop ? 'stopped' : stopAt >= 0 && hop > stopAt ? 'unreached' :
        !c?.attempted ? 'unreached' : c.lost ? 'lossy' : 'ok') + (located.has(r.edge_scopes[hop]) ? ' located' : '');
      track += `<span class="flow-seg ${cls}" style="--hop:${hop}" title="${re(eid)} · ${c ? `${c.attempted} sent, ${c.received} through, ${c.lost} lost` : 'no qubits'}${located.has(r.edge_scopes[hop]) ? ' · ATTACK LOCATED HERE — quarantined' : ''}"></span>` +
        `<span class="flow-node${hop === r.edges.length - 1 ? ' verifier' : ''}">${re(r.nodes[hop + 1])}</span>`;
    });
    // Verdicts are about the signature check, not the qubits: 'not_reached' means no package arrived to verify.
    const verdict = verdicts[v] || execution?.status || 'planned';
    const verdictLabel = {not_reached: 'no signature', outside_depth: 'outside depth', distribution_aborted: 'aborted'}[verdict] || verdict.replace(/_/g, ' ');
    return `<div class="flow-lane" style="--lane:${lane}">` +
      `<div class="flow-track">${track}</div>` +
      `<span class="flow-count" title="qubits received / planned">${stats.received ?? 0}/${stats.planned ?? 0}</span>` +
      `<span class="flow-status ${re(verdict)}" title="signature verdict">${re(verdictLabel)}${r.rerouted ? ' · rerouted' : ''}</span></div>`;
  }).join('');
  if (animate) {
    box.classList.remove('is-live');
    void box.offsetWidth;
    box.classList.add('is-live');
  }
}

async function loadLatestFlow() {
  if (!routeEl('qubitFlow')) return;
  try {
    const {data} = await api('/api/history', {}, 'admin');
    renderQubitFlow((data.transmissions || []).at(-1), false);
  } catch (e) { /* informational */ }
}

const FAILOVER_CHECKS = {
  baseline_used_R1_R2: 'Baseline send used R1 → R2',
  probe_quarantined_middle_edge: 'Independent probe quarantined R1 → R2',
  new_session_used_R3: 'Fresh send was routed through R3',
  alternate_carried_tokens: 'Alternate edge alice → R3 carried tokens',
  blocked_edge_carried_zero_new_tokens: 'Quarantined edge carried no new tokens',
  failed_edge_still_quarantined: 'Failed edge stayed quarantined',
  no_reset_performed: 'No reset was needed',
  new_distribution_completed: 'Fresh distribution completed',
};

async function runFailoverTest() {
  const out = routeEl('failoverTestResult'), button = routeEl('runFailoverTest');
  button.disabled = true;
  out.innerHTML = '<p class="section-note">Running isolated test on the real simulator…</p>';
  try {
    const {data} = await api('/api/routing/demo', {method: 'POST'}, 'admin');
    const passed = data.status === 'passed';
    out.innerHTML = `<div class="route-comparison"><h3 class="${passed ? 'route-test-pass' : 'route-test-fail'}">Failover test ${re(data.status.toUpperCase())}</h3>` +
      `<div class="route-line"><span>Before</span><strong>${re(routeGroups(data.before.plan.routes))}</strong></div>` +
      `<div class="route-line"><span>After</span><strong>${re(routeGroups(data.after.plan.routes))}</strong></div>` +
      `<details class="routing-details"><summary>Checks (${Object.values(data.checks).filter(Boolean).length}/${Object.keys(data.checks).length} passed)</summary>` +
      Object.entries(data.checks).map(([k, ok]) => `<div class="route-test-step"><span class="${ok ? 'route-test-pass' : 'route-test-fail'}">${ok ? '✓' : '✗'}</span> ${re(FAILOVER_CHECKS[k] || k)}</div>`).join('') +
      `</details><p class="route-reason">${re(data.note)} · test ${re(data.test_id)}</p></div>`;
  } catch (err) {
    out.innerHTML = `<div class="route-stop">${re(err.message)}</div>`;
  } finally { button.disabled = false; }
}

document.addEventListener('DOMContentLoaded', () => {
  // The console page only shows the compact strip; the controls below live on /admin/routing.
  if (!routeEl('topologySvg')) return;
  routeEl('runFailoverTest').onclick = runFailoverTest;
  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(drawRouting, 150); });
  routeEl('activateTopology').onclick = () => routingAction('/api/topology', {preset: routeEl('routingPreset').value});
  routeEl('topologyFile').onchange = async event => {
    try {
      const file = event.target.files[0];
      if (!file) return;
      if (file.size > 200000) throw new Error('Topology JSON must be under 200 KB.');
      await routingAction('/api/topology', {topology: JSON.parse(await file.text())});
    } catch (err) { routeEl('routingMessage').textContent = err.message; }
    event.target.value = '';
  };
  routeEl('refreshRouting').onclick = refreshTopology;
  routeEl('routeSession').onchange = drawRouting;
  routeEl('routeRecipient').onchange = drawRouting;
  routeEl('routingEdge').onchange = showRoutingEdge;
  routeEl('toggleIntercept').onclick = () => routingFault(routingLive?.injections?.[routeEl('routingEdge').value] ? 'clear_attack' : 'attack');
  routeEl('quarantineRoutingEdge').onclick = () => routingFault('manual');
  routeEl('probeRoutingEdge').onclick = () => routingAction('/api/routing/probe', {edges: [routeEl('routingEdge').value], count: 512});
  routeEl('resetRoutingEdge').onclick = () => {
    const edge = routingLive.edges.find(e => e.id === routeEl('routingEdge').value);
    if (edge) routingAction('/api/channel/reset', {link: edge.scope, reason: routeEl('routingReason').value});
  };
  routeEl('toggleEmergency').onclick = () => routingAction('/api/routing/emergency', {enabled: !emergencyActive(), reason: routeEl('routingReason').value});
});

const emergencyActive = () => routingLive?.channel_state?.['*emergency-stop*']?.state === 'quarantined';

async function routingFault(action, state = 'quarantined') {
  await routingAction('/api/routing/fault', {edge: routeEl('routingEdge').value, action, state, reason: routeEl('routingReason').value});
}

async function routingAction(url, body) {
  const controls = [...document.querySelectorAll('.routing-toolbar button, .edge-group button, .danger-zone button, #btnResetLinks, #refreshRouting')];
  controls.forEach(b => { b.disabled = true; });
  routeEl('routingMessage').textContent = 'Working…';
  try {
    const {data} = await api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}, 'admin');
    routeEl('routingMessage').textContent = data.observations ? data.observations.map(o =>
      `${o.edge}: ${o.test.error_count}/${o.test.test_count} errors; ${o.decision.response_action}; independent probe ${o.probe_id}`).join(' · ') :
      'Saved. Start a fresh transmission to allocate routes under the updated state.';
    await refreshTopology();
  } catch (error) {
    routeEl('routingMessage').textContent = error.message;
  } finally {
    controls.forEach(b => { b.disabled = false; });
    showRoutingEdge();
  }
}

// Eve's position picker (threat studio): live quantum links, defaulting to a link worth locating.
function fillAttackEdges(data) {
  const select = routeEl('attackEdge');
  if (!select) return;
  const ids = data.edges.map(e => e.id);
  const roles = Object.fromEntries(data.topology.nodes.map(n => [n.id, n.role]));
  const keep = ids.includes(select.value) ? select.value : null;
  select.innerHTML = '<option value="">Whole send (not tied to one link)</option>' +
    ids.map(id => `<option value="${re(id)}">${re(id.replace('->', ' → '))}</option>`).join('');
  select.value = keep ?? (ids.includes('R1->R2') ? 'R1->R2' : ids.find(id => roles[id.split('->')[1]] === 'verifier') || '');
}

async function renderRouting(data) {
  routingLive = data;
  fillAttackEdges(data);
  if (!routeEl('topologySvg')) return;
  const [{data: history}, {data: refusals}] = await Promise.all([
    api('/api/routing/history', {}, 'admin'), api('/api/routing/refusals', {}, 'admin')]);
  routingSessions = history.sessions || [];
  const selected = routeEl('routeSession').value;
  routeEl('routeSession').innerHTML = '<option value="live">Live topology + latest matching plan</option>' + routingSessions.map(row =>
    `<option value="${re(row.plan.session_id)}">${re(row.plan.session_id)} · ${re(row.execution?.status || 'planned')} · ${re(row.plan.topology.version)}</option>`).join('');
  if ([...routeEl('routeSession').options].some(o => o.value === selected)) routeEl('routeSession').value = selected;
  const edge = routeEl('routingEdge').value;
  routeEl('routingEdge').innerHTML = data.edges.map(e => `<option value="${re(e.id)}">${re(e.id)} · ${re(e.state.toUpperCase())}</option>`).join('');
  if (data.edges.some(e => e.id === edge)) routeEl('routingEdge').value = edge;
  routeEl('routingPreset').value = data.topology.version.startsWith('demo-multihop') ? 'demo-multihop' : 'star';
  drawRouting();
  showRoutingEdge();
  if (refusals.refusals?.length) renderRouteRefusal(refusals.refusals[0]);
}

function drawRouting() {
  if (!routingLive) return;
  const historical = routeEl('routeSession').value !== 'live';
  const row = historical ? routingSessions.find(s => s.plan.session_id === routeEl('routeSession').value) :
    routingSessions.find(s => s.plan.topology_digest === routingLive.digest);
  const plan = row?.plan;
  const execution = row?.execution;
  const topology = historical && plan ? plan.topology : routingLive.topology;
  const states = historical && plan ? plan.scope_snapshot : routingLive.channel_state;
  const edges = topology.edges.map(e => {
    const live = routingLive.edges.find(l => l.id === e.id);
    const scope = plan && plan.topology_digest === (historical ? plan.topology_digest : routingLive.digest) ?
      Object.values(plan.routes).map(r => {
        const i = r.edges.indexOf(e.id); return i >= 0 ? r.edge_scopes[i] : null;
      }).find(Boolean) : null;
    // Historical edges not used by the selected plan still have states in its
    // frozen snapshot, mapped using the stored topology-specific scope table.
    const savedScope = plan?.edge_scope_map?.[e.id] || scope;
    return {...e, scope: historical ? savedScope : live?.scope,
      state: historical ? states[savedScope]?.state || 'open' : live?.state || 'open',
      monitoring: historical ? plan?.monitoring_snapshot?.[e.id] || 'unmonitored' : live?.monitoring || 'unmonitored'};
  });
  const oldRecipient = routeEl('routeRecipient').value;
  routeEl('routeRecipient').innerHTML = (plan?.roster || []).map(v => `<option value="${re(v)}">${re(v)}</option>`).join('');
  if (plan?.roster.includes(oldRecipient)) routeEl('routeRecipient').value = oldRecipient;
  const recipient = routeEl('routeRecipient').value;
  const route = plan?.routes[recipient];
  const time = execution?.timestamp || plan?.created_at || routingLive.timestamp;
  routeEl('routingIdentity').textContent = `${historical ? 'HISTORICAL SNAPSHOT' : 'LIVE STATES'} · ${topology.version} · digest ${historical ? plan.topology_digest : routingLive.digest} · ${plan?.session_id || 'no plan'} · ${execution?.status || 'unallocated'} · ${new Date(time * 1000).toLocaleString()}${states['*emergency-stop*']?.state === 'quarantined' ? ' · EMERGENCY STOP' : ''}`;
  const fact = (k, v) => `<div><dt>${re(k)}</dt><dd>${re(v)}</dd></div>`;
  routeEl('routeDetail').innerHTML = route ? '<dl class="route-facts">' +
    fact('Path', route.nodes.join(' → ')) + fact('Quantum hops', route.hops) +
    fact('Predicted QBER', `${routePct(route.expected_qber)} (bound ${routePct(route.qber_bound)})`) +
    fact('Survival', routePct(route.survival)) +
    fact('Monitoring', Object.entries(route.monitoring).map(([e, m]) => `${e}: ${m}`).join(', ')) +
    fact('Why', route.rerouted ? `Rerouted from ${route.previous_route.session_id}` : route.reason) +
    (execution?.abort_reason ? fact('Abort', `${execution.abort_reason}; no reveal`) : '') + '</dl>' :
    'Select the multi-hop demo network, send a baseline, then inject an intercept on R1→R2 and probe it. The next session can use R3.';
  drawRouteGraph(topology, edges, route, execution);
  routeEl('routeAllocation').innerHTML = routeTable(['Recipient', 'Path', 'Received', 'Outcome'],
    Object.entries(plan?.routes || {}).map(([v, r]) => [v, r.nodes.slice(1, -1).join(' → ') + (r.rerouted ? ' (rerouted)' : ''),
      `${execution?.recipients[v]?.received || 0} / ${execution?.recipients[v]?.planned || 0}`,
      execution?.session_outcome || (execution?.status === 'aborted' ? 'aborted' : execution?.status || 'planned')]));
  routeEl('routeCandidates').innerHTML = routeTable(['Recipient', 'Candidate / scope', 'Decision', 'Monitoring', 'Search'],
    Object.entries(plan?.candidates || {}).flatMap(([v, d]) => [
      [v, plan.routes[v].nodes.join(' → '), 'Selected: minimum eligible cost', Object.values(plan.routes[v].monitoring).join(', '), `${d.expansions} expansions; ${d.search_complete ? 'exhausted' : 'stopped at optimal selection'}`],
      ...d.rejected.map(c => [v, c.edge || c.edges?.join(' → '), `${c.reason}${c.state ? ` (${c.state})` : ''}`, c.monitoring || '—', 'pruned / excluded'])]));
  const nodes = topology.nodes.map(n => n.id);
  const stateCode = {open: 'O', watch: 'W', quarantined: 'Q', reset_pending: 'P'};
  routeEl('routeAdjacency').innerHTML = '<p class="section-note">O OPEN · W WATCH · Q QUARANTINED · P probation · — no directed edge. OPEN means unrestricted; freshness is separate.</p>' +
    routeTable(['From / To', ...nodes], nodes.map(a => [a, ...nodes.map(b => {
      const e = edges.find(e => e.src === a && e.dst === b); return e ? stateCode[e.state] : '—';
    })]));
  routeEl('routeIncidence').innerHTML = routeTable(['Recipient', ...edges.map(e => e.id)],
    Object.entries(plan?.routes || {}).map(([v, r]) => [v, ...edges.map(e => r.edges.includes(e.id) ? 1 : 0)]));
  routeEl('routeExecution').innerHTML = routeTable(['Edge', 'Attempted', 'Received', 'Lost', 'Bell pairs', 'Source'],
    Object.entries(execution?.edges || {}).map(([e, c]) => [e, c.attempted, c.received, c.lost, c.bell_pairs, 'Session traversal (probes separate)']));
  routeEl('routeHistory').innerHTML = routeTable(['Session', 'Recipient', 'Old path', 'New path', 'Event', 'Outcome'],
    routingSessions.flatMap(s => Object.entries(s.plan.routes).map(([v, r]) => [s.plan.session_id, v,
      r.previous_route?.nodes.join(' → ') || 'No prior route', r.nodes.join(' → '),
      r.rerouted ? 'Fresh-session reroute; restrictions / policy changed' : r.fallback ? 'Fallback allocation' : 'Allocated',
      s.execution?.session_outcome || s.execution?.status || 'planned'])));
}

function drawRouteGraph(topology, edges, route, execution) {
  const svg = routeEl('topologySvg');
  const signer = topology.nodes.find(n => n.role === 'signer');
  const depths = {[signer.id]: 0};
  const queue = [signer.id];
  while (queue.length) {
    const src = queue.shift();
    edges.filter(e => e.src === src).forEach(e => {
      if (depths[e.dst] === undefined) { depths[e.dst] = depths[src] + 1; queue.push(e.dst); }
    });
  }
  const relays = topology.nodes.filter(n => n.role === 'relay');
  const end = Math.max(1, ...relays.map(n => depths[n.id] || 1)) + 1;
  const columns = {};
  topology.nodes.forEach(n => {
    const column = n.role === 'signer' ? 0 : n.role === 'verifier' ? end : depths[n.id] || 1;
    (columns[column] ||= []).push(n);
  });
  // Drawn at the container's real width so labels stay at their CSS size instead of being scaled.
  const width = Math.max(480, (svg.parentElement.clientWidth || 640) - 24);
  const rows = Math.max(...Object.values(columns).map(n => n.length));
  const top = 40, bottom = 40;
  const height = Math.max(200, top + bottom + rows * 38);
  const boxW = n => Math.max(56, String(n.label || n.id).length * 8 + 22);
  const margin = 50, step = (width - 2 * margin) / end;
  const pos = {};
  Object.entries(columns).forEach(([c, nodes]) => nodes.sort((a, b) => a.id.localeCompare(b.id)).forEach((n, i) => {
    pos[n.id] = [margin + Number(c) * step, top + (i + 0.5) * (height - top - bottom) / nodes.length, boxW(n) / 2];
  }));
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  const onRoute = new Set(route?.nodes || []);
  let out = '<defs><marker id="quantumArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="context-stroke"/></marker></defs>';
  Object.keys(columns).forEach(c => {
    const label = Number(c) === 0 ? 'SIGNER' : Number(c) === end ? 'VERIFIERS' : end > 2 ? `RELAY · HOP ${c}` : 'RELAYS';
    out += `<text class="routing-column" x="${margin + Number(c) * step}" y="16" text-anchor="middle">${label}</text>`;
  });
  let bypassIndex = 0;
  const halos = [], lines = [];
  edges.forEach(e => {
    const [x1, y1, w1] = pos[e.src], [x2, y2, w2] = pos[e.dst];
    const selected = route?.edges.includes(e.id);
    const stopping = execution?.stopping_scope === e.scope;
    const bypass = x2 - x1 > step * 1.3;
    const lane = height - 14 - bypassIndex * 12;
    if (bypass) bypassIndex++;
    const sx = x1 + w1, ex = x2 - w2 - 4;
    // Long edges use a bottom lane so they cannot appear to traverse an
    // unrelated relay drawn between the source and destination.
    const path = bypass ? `M${sx},${y1} C${sx+40},${y1} ${sx+30},${lane} ${sx+70},${lane} L${ex-70},${lane} C${ex-30},${lane} ${ex-40},${y2} ${ex},${y2}` :
      `M${sx},${y1} C${(sx+ex)/2},${y1} ${(sx+ex)/2},${y2} ${ex},${y2}`;
    if (selected) halos.push(`<path d="${path}" fill="none" stroke="#38bdf8" stroke-width="10" stroke-linecap="round" opacity="0.35"/>`);
    // Only label what differs from the default: restricted links, the selected route's hops, a stop point.
    const tags = [e.state !== 'open' ? e.state.replace('_', ' ').toUpperCase() : '', selected ? `hop ${route.edges.indexOf(e.id) + 1}` : '', stopping ? 'STOP' : ''].filter(Boolean);
    const c = execution?.edges[e.id];
    lines.push(`<g class="routing-edge${selected ? ' is-selected' : ''}" data-edge="${re(e.id)}" tabindex="0" role="button" aria-label="${re(e.id)} ${re(e.state)}">` +
      `<path d="${path}" fill="none" stroke="transparent" stroke-width="12"/>` +
      `<path d="${path}" fill="none" stroke="${routingColours[e.state]}" stroke-width="${selected ? 2.5 : 1.5}" opacity="${selected || e.state !== 'open' ? 1 : 0.55}" ${e.state === 'quarantined' ? 'stroke-dasharray="6 4"' : ''} marker-end="url(#quantumArrow)"/>` +
      (tags.length ? `<text class="routing-edge-label" x="${bypass ? (sx + ex) / 2 : sx + (ex - sx) * 0.42}" y="${bypass ? lane - 5 : y1 + (y2 - y1) * 0.42 - 6}" text-anchor="middle">${re(tags.join(' · '))}</text>` : '') +
      `<title>${re(e.id)} · ${re(e.state)} · monitoring ${re(e.monitoring)} · ${c ? `${c.attempted} attempted, ${c.received} received, ${c.lost} lost` : 'no recorded session traffic'}</title></g>`);
  });
  out += halos.join('') + lines.join('');
  topology.nodes.forEach(n => {
    const [x, y, hw] = pos[n.id];
    out += `<g class="routing-node ${re(n.role)}${onRoute.has(n.id) ? ' on-route' : ''}"${n.role === 'verifier' ? ` data-recipient="${re(n.id)}" tabindex="0" role="button"` : ''}>` +
      `<rect x="${x - hw}" y="${y - 13}" width="${hw * 2}" height="26" rx="13"/>` +
      `<text class="routing-node-label" x="${x}" y="${y + 4}" text-anchor="middle">${re(n.label || n.id)}</text>` +
      `<title>${re(n.id)} · ${re(n.role)}</title></g>`;
  });
  svg.innerHTML = out;
  svg.querySelectorAll('[data-edge]').forEach(g => {
    const select = () => { routeEl('routingEdge').value = g.dataset.edge; showRoutingEdge(); };
    g.onclick = select;
    g.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') select(); };
  });
  // Clicking a verifier shows its route.
  svg.querySelectorAll('[data-recipient]').forEach(g => {
    const select = () => {
      if (![...routeEl('routeRecipient').options].some(o => o.value === g.dataset.recipient)) return;
      routeEl('routeRecipient').value = g.dataset.recipient; drawRouting();
    };
    g.onclick = select;
    g.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') select(); };
  });
}

function showRoutingEdge() {
  const edge = routingLive?.edges.find(e => e.id === routeEl('routingEdge').value);
  if (!edge) return;
  const probe = edge.probe;
  const injection = routingLive.injections?.[edge.id];
  const pill = routeEl('routingEdgeState');
  pill.className = `link-chip ${edge.state}`;
  pill.textContent = edge.state.replace('_', ' ').toUpperCase() + (injection ? ' · INTERCEPTED' : '');
  routeEl('routingProbe').textContent = `Monitoring ${edge.monitoring} · ` +
    (probe ? `last probe ${probe.test.error_count}/${probe.test.test_count} errors, ${probe.test.tokens_lost || 0} lost · ${new Date(probe.timestamp*1000).toLocaleTimeString()} · recovery ${probe.recovery.tested}/1024 tests, ${probe.recovery.rounds}/2 rounds` : 'not probed yet');
  // Each control is enabled only when it would change something for this link.
  routeEl('toggleIntercept').innerHTML = `<span class="step-no">1</span> ${injection ? 'Remove intercept' : 'Inject intercept'}`;
  routeEl('toggleIntercept').classList.toggle('is-active', Boolean(injection));
  routeEl('quarantineRoutingEdge').disabled = edge.state === 'quarantined';
  routeEl('resetRoutingEdge').disabled = !['quarantined', 'watch'].includes(edge.state);
  const stopped = emergencyActive();
  routeEl('toggleEmergency').textContent = stopped ? 'Resume sends' : 'Stop all sends';
  routeEl('toggleEmergency').closest('.danger-zone').classList.toggle('is-active', stopped);
}
