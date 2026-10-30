/* Views consume frozen route records. Current configuration never redraws history. */
let routingLive = null;
let routingSessions = [];
let routingPreview = null;
const routingColours = {open: '#22c55e', watch: '#f59e0b', quarantined: '#ef4444', reset_pending: '#38bdf8'};
const routeEl = id => document.getElementById(id);
const re = value => escapeHtml(String(value ?? '—'));
const routeTable = (head, rows) => `<table class="matrix-table"><thead><tr>${head.map(h => `<th>${re(h)}</th>`).join('')}</tr></thead><tbody>` +
  (rows.length ? rows.map(row => `<tr>${row.map(c => `<td>${re(c)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${head.length}">No recorded execution yet.</td></tr>`) + '</tbody></table>';
const routePct = n => `${(100 * n).toFixed(2)}%`;

function previewRoutingRequest() {
  const payload = typeof recipientPayload === 'function' ? recipientPayload() : {n_verifiers: 2};
  return api('/api/routing/preview', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}, 'admin');
}

async function refreshRoutingPreview() {
  try {
    const {data} = await previewRoutingRequest();
    routingPreview = data;
    renderNextRoutes();
    if (routingLive) drawRouting();
  } catch (error) {
    routeEl('nextRouteBadge').textContent = 'Preview unavailable';
    routeEl('nextRouteSummary').textContent = error.message;
  }
}

function routeDecisionExplanation(plan, recipient) {
  const route = plan.routes[recipient];
  const excluded = plan.candidates[recipient]?.rejected || [];
  const reasons = [...new Set(excluded.map(c => c.edge ? `${c.edge.replaceAll('->', ' → ')} (${c.state?.toUpperCase() || c.reason})` :
    c.edges ? `${c.edges.join(', ')}: ${c.reason.replaceAll('_', ' ')}` : c.reason))];
  return (reasons.length ? `Skipped ${reasons.join('; ')}. ` : '') +
    `Among eligible routes, the planner prefers OPEN links, then fresher monitoring, then lower cost. Selected cost: ${route.cost}.`;
}

function renderNextRoutes() {
  if (!routingPreview || !routingLive) return;
  const badge = routeEl('nextRouteBadge');
  if (routingPreview.status !== 'ready') {
    badge.textContent = 'Next send blocked';
    const scope = routingPreview.link;
    const signerStop = ['alice->verifiers', '*emergency-stop*'].includes(scope) &&
      routingLive.channel_state[scope]?.state === 'quarantined';
    const reason = signerStop ?
      `A ${scope === '*emergency-stop*' ? 'global emergency' : 'signer'} stop is active. Every route uses Alice, so switching from R1/R2 to R3 cannot bypass this stop. Cause: ${routingLive.channel_state[scope].reason || 'see the scope record'}` :
      `No eligible quantum route serves the required recipients. ${routingPreview.message || ''} The planner will refuse before preparing qubits.`;
    routeEl('nextRouteSummary').innerHTML = `<div class="route-stop">${re(reason)}</div>`;
    return;
  }
  const plan = routingPreview.plan;
  const latest = routingSessions.find(s => s.plan.topology_digest === plan.topology_digest);
  const changed = latest && plan.roster.some(v => latest.plan.routes[v] && latest.plan.routes[v].route_id !== plan.routes[v].route_id);
  badge.textContent = changed ? 'Alternate route ready — no reset needed' : 'Route ready';
  routeEl('nextRouteSummary').innerHTML = plan.roster.map(v => {
    const previous = latest?.plan.routes[v];
    const next = plan.routes[v];
    const bypass = previous && previous.route_id !== next.route_id;
    return `<article class="route-comparison"><h3>To ${re(v)}</h3>` +
      `<div class="route-line"><span>${latest?.execution?.status === 'aborted' ? 'Last attempt' : 'Last send'}</span><span>${re(previous?.nodes.join(' → ') || 'No recorded send')}</span></div>` +
      `<div class="route-line"><span>Next send</span><strong>${re(next.nodes.join(' → '))}</strong></div>` +
      `<p class="route-reason">${re(routeDecisionExplanation(plan, v))}${bypass ? ' The failed route stays restricted. This new route needs no reset.' : ''}</p></article>`;
  }).join('') + (routingLive.topology.version === 'legacy-star/1' ?
    '<p class="section-note"><strong>The legacy star has no backup path.</strong> Activate the multi-hop demo to get the R1/R2 path and the R3 alternative.</p>' : '');
}

function explainRoutingEvent(tx) {
  if (tx.threat_report?.classification === 'EXTERNAL_FORGERY') {
    routeEl('routingLastEvent').textContent = 'Last event: the forged classical signature was rejected. No quantum edge was blamed and Alice was not stopped; an authentic next send remains possible.';
  } else if (tx.routing) {
    const rerouted = Object.values(tx.routing.plan.routes).some(r => r.rerouted);
    routeEl('routingLastEvent').textContent = rerouted ?
      `Last event: ${tx.transmission_id} used a different route with fresh preparation. Outcome: ${tx.session_outcome.replaceAll('_', ' ')}.` :
      `Last event: ${tx.transmission_id} finished with outcome ${tx.session_outcome.replaceAll('_', ' ')}. See its recorded route below.`;
  }
}

async function runRoutingSelfTest() {
  const button = routeEl('runFailoverTest');
  button.disabled = true;
  const result = routeEl('failoverTestResult');
  result.textContent = 'Running the actual simulator: baseline → independent middle-link probe → fresh send on the alternative…';
  try {
    const {data} = await api('/api/routing/demo', {method: 'POST'}, 'admin');
    const before = data.before.plan.routes.bob;
    const after = data.after.plan.routes.bob;
    const traffic = data.after.execution.edges['alice->R3'];
    result.innerHTML = `<article class="route-comparison"><h3 class="route-test-${data.status === 'passed' ? 'pass' : 'fail'}">FAILOVER TEST ${re(data.status.toUpperCase())}</h3>` +
      `<div class="route-test-step"><strong>1. Baseline sent</strong>${re(before.nodes.join(' → '))} · cost ${before.cost}</div>` +
      `<div class="route-test-step"><strong>2. Independent probe blocked R1 → R2</strong>${data.probe.test.error_count} errors / ${data.probe.test.test_count} measured test tokens. Decision: ${re(data.probe.decision.response_action)}.</div>` +
      `<div class="route-test-step"><strong>3. Fresh send used the alternate route</strong>${re(after.nodes.join(' → '))} · cost ${after.cost}. ${traffic?.attempted || 0} actual token attempts on Alice → R3; ${data.after.execution.edges['R1->R2']?.attempted || 0} on the blocked edge.</div>` +
      `<div class="route-test-step"><strong>4. The failed link stayed ${re(data.blocked_edge_after_send.toUpperCase())}</strong>No reset was performed. Rerouting worked while the primary remained blocked. Signature verification: ${re(data.verification_outcome.replaceAll('_', ' '))}.</div>` +
      `<p class="section-note">${re(data.note)} Backend: ${re(data.backend)}. <a href="/api/audit/${encodeURIComponent(data.test_id)}" target="_blank">Signed test evidence</a></p>` +
      `<details><summary>Check every assertion</summary>${routeTable(['Check', 'Result'], Object.entries(data.checks).map(([k, v]) => [k.replaceAll('_', ' '), v ? 'PASS' : 'FAIL']))}</details></article>`;
  } catch (error) { result.textContent = `Test could not finish: ${error.message}`; }
  finally { button.disabled = false; }
}

function routingScopeLabel(scope) {
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

document.addEventListener('DOMContentLoaded', () => {
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
  routeEl('routeHighlight').onchange = drawRouting;
  routeEl('quickActivateDemo').onclick = () => routingAction('/api/topology', {preset: 'demo-multihop'});
  routeEl('runFailoverTest').onclick = runRoutingSelfTest;
  routeEl('routingEdge').onchange = showRoutingEdge;
  document.querySelectorAll('[data-routing-action]').forEach(button => {
    button.onclick = () => routingFault(button.dataset.routingAction);
  });
  routeEl('watchRoutingEdge').onclick = () => routingFault('manual', 'watch');
  routeEl('probeRoutingEdge').onclick = () => routingAction('/api/routing/probe', {edges: [routeEl('routingEdge').value], count: 512});
  routeEl('resetRoutingEdge').onclick = () => {
    const edge = routingLive.edges.find(e => e.id === routeEl('routingEdge').value);
    if (edge) routingAction('/api/channel/reset', {link: edge.scope, reason: routeEl('routingReason').value});
  };
  routeEl('stopRouting').onclick = () => routingAction('/api/routing/emergency', {enabled: true, reason: routeEl('routingReason').value});
  routeEl('resumeRouting').onclick = () => routingAction('/api/routing/emergency', {enabled: false, reason: routeEl('routingReason').value});
});

async function routingFault(action, state = 'quarantined') {
  await routingAction('/api/routing/fault', {edge: routeEl('routingEdge').value, action, state, reason: routeEl('routingReason').value});
}

async function routingAction(url, body) {
  const controls = [...document.querySelectorAll('.routing-toolbar button')];
  controls.forEach(b => { b.disabled = true; });
  routeEl('routingMessage').textContent = 'Working…';
  try {
    const {data} = await api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}, 'admin');
    routeEl('routingMessage').textContent = data.observations ? data.observations.map(o =>
      `${o.edge}: ${o.test.error_count}/${o.test.test_count} errors; ${o.decision.response_action}; independent probe ${o.probe_id}`).join(' · ') :
      'Saved. Start a fresh transmission to allocate routes under the updated state.';
    await refreshTopology();
    const {data: states} = await api('/api/channel', {}, 'admin');
    renderLinks(states);
  } catch (error) {
    routeEl('routingMessage').textContent = error.message;
  } finally { controls.forEach(b => { b.disabled = false; }); }
}

async function renderRouting(data) {
  routingLive = data;
  const [{data: history}, {data: refusals}, {data: preview}] = await Promise.all([
    api('/api/routing/history', {}, 'admin'), api('/api/routing/refusals', {}, 'admin'), previewRoutingRequest()]);
  routingPreview = preview;
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
  renderNextRoutes();
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
  const roster = historical ? plan?.roster || [] : routingPreview?.plan?.roster || plan?.roster || [];
  const oldRecipient = routeEl('routeRecipient').value;
  routeEl('routeRecipient').innerHTML = roster.map(v => `<option value="${re(v)}">${re(v)}</option>`).join('');
  if (roster.includes(oldRecipient)) routeEl('routeRecipient').value = oldRecipient;
  const recipient = routeEl('routeRecipient').value;
  const lastRoute = plan?.routes[recipient];
  routeEl('routeHighlight').disabled = historical;
  const highlightNext = !historical && routeEl('routeHighlight').value === 'next';
  const route = highlightNext ? routingPreview?.plan?.routes[recipient] : lastRoute;
  const time = execution?.timestamp || plan?.created_at || routingLive.timestamp;
  routeEl('routingIdentity').textContent = `${historical ? 'HISTORICAL SNAPSHOT' : 'LIVE STATES'} · ${topology.version} · digest ${historical ? plan.topology_digest : routingLive.digest} · ${plan?.session_id || 'no plan'} · ${execution?.status || 'unallocated'} · ${new Date(time * 1000).toLocaleString()}${states['*emergency-stop*']?.state === 'quarantined' ? ' · EMERGENCY STOP' : ''}`;
  routeEl('routeDetail').textContent = route ? `${route.nodes.join(' → ')} · ${route.hops} quantum hops · predicted BB84 QBER ${routePct(route.expected_qber)} (basis upper bound ${routePct(route.qber_bound)}) · survival ${routePct(route.survival)} · ${route.reason} · monitoring ${Object.entries(route.monitoring).map(([e, m]) => `${e}: ${m}`).join(', ')}${!highlightNext && execution?.abort_reason ? ` · ABORT: ${execution.abort_reason}; no reveal` : ''}` :
    (highlightNext ? 'No eligible route for the next send. See the reason at the top of the page.' : 'No recorded route yet.');
  routeEl('routingGraphCaption').textContent = historical ? 'Recorded historical route and its original link states.' : highlightNext ?
    'NEXT SEND: cyan shows the route the planner would choose now. No qubits have been sent on this preview. Gray dashed shows the last recorded route.' :
    'LAST SEND: cyan shows its recorded route; counters below show what it actually attempted. Current link states may have changed since that send.';
  const graphTopology = {...topology, nodes: topology.nodes.filter(n => n.role !== 'verifier' || roster.includes(n.id)),
    edges: topology.edges.filter(e => !topology.nodes.some(n => n.id === e.dst && n.role === 'verifier' && !roster.includes(n.id)))};
  const graphIds = new Set(graphTopology.edges.map(e => e.id));
  drawRouteGraph(graphTopology, edges.filter(e => graphIds.has(e.id)), route, highlightNext ? null : execution,
                highlightNext ? lastRoute : null, !historical && routingPreview?.status !== 'ready');
  routeEl('routeAllocation').innerHTML = routeTable(['Recipient', 'Selected path', 'Hops', 'Decision', 'Distribution', 'Session outcome', 'Observed / planned'],
    Object.entries(plan?.routes || {}).map(([v, r]) => [v, r.nodes.join(' → '), r.hops,
      r.rerouted ? `Rerouted from ${r.previous_route.session_id}` : r.fallback ? 'Fallback allocation' : r.reason,
      execution?.recipients[v]?.planned > 0 && execution.recipients[v].attempted === execution.recipients[v].planned ? 'Traversal finished' : execution?.status || 'planned',
      execution?.session_outcome || (execution?.status === 'aborted' ? 'distribution_aborted' : 'Awaiting assessment'),
      `${execution?.recipients[v]?.received || 0} / ${execution?.recipients[v]?.planned || 0}`]));
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

function drawRouteGraph(topology, edges, route, execution, previousRoute = null, globalStop = false) {
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
  const height = Math.max(320, Math.max(...Object.values(columns).map(n => n.length)) * 90 + 140);
  const width = Math.max(740, (end + 1) * 200);
  const pos = {};
  Object.entries(columns).forEach(([c, nodes]) => nodes.sort((a, b) => a.id.localeCompare(b.id)).forEach((n, i) => {
    pos[n.id] = [60 + Number(c) * (width - 120) / end, (i + 1) * height / (nodes.length + 1)];
  }));
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  let out = '<defs><marker id="quantumArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="context-stroke"/></marker></defs>';
  let bypassIndex = 0;
  edges.forEach(e => {
    const [x1, y1] = pos[e.src], [x2, y2] = pos[e.dst];
    const selected = route?.edges.includes(e.id);
    const stopping = execution?.stopping_scope === e.scope;
    const colour = routingColours[e.state];
    const bypass = x2 - x1 > (width - 120) / end * 1.3;
    const lane = height - 25 - bypassIndex * 18;
    if (bypass) bypassIndex++;
    // Long edges use a bottom lane so they cannot appear to traverse an
    // unrelated relay drawn between the source and destination.
    const path = bypass ? `M${x1+22},${y1} C${x1+75},${y1} ${x1+70},${lane} ${x1+100},${lane} L${x2-85},${lane} C${x2-48},${lane} ${x2-75},${y2} ${x2-28},${y2}` :
      `M${x1 + 22},${y1} C${(x1+x2)/2},${y1} ${(x1+x2)/2},${y2} ${x2-28},${y2}`;
    if (selected) out += `<path d="${path}" fill="none" stroke="#38bdf8" stroke-width="11" opacity="0.3"/>`;
    if (previousRoute?.edges.includes(e.id) && !selected) out += `<path d="${path}" fill="none" stroke="#64748b" stroke-width="7" stroke-dasharray="8 7" opacity="0.4"/>`;
    const c = execution?.edges[e.id];
    out += `<g class="routing-edge" data-edge="${re(e.id)}" tabindex="0" role="button" aria-label="${re(e.id)} ${re(e.state)}">` +
      `<path d="${path}" fill="none" stroke="${colour}" stroke-width="${selected ? 3 : 2}" ${e.state === 'quarantined' ? 'stroke-dasharray="6 4"' : ''} marker-end="url(#quantumArrow)"/>` +
      `<text class="routing-edge-label" x="${(x1+x2)/2}" y="${bypass ? lane-5 : (y1+y2)/2-8}" text-anchor="middle">${re(e.state.toUpperCase())}${selected ? ` · hop ${route.edges.indexOf(e.id)+1}` : ''}${stopping ? ' · STOP' : ''}</text>` +
      `<title>${re(e.id)} · ${re(e.monitoring)} · ${c ? `${c.attempted} attempted, ${c.received} received, ${c.lost} lost` : 'no recorded session traffic'}</title></g>`;
  });
  topology.nodes.forEach(n => {
    const [x, y] = pos[n.id];
    const stoppedSigner = globalStop && n.role === 'signer' &&
      ['alice->verifiers', '*emergency-stop*'].some(s => routingLive?.channel_state[s]?.state === 'quarantined');
    out += `<circle cx="${x}" cy="${y}" r="23" fill="${stoppedSigner ? 'var(--danger-bg)' : 'var(--surface, #0f172a)'}" stroke="${stoppedSigner ? '#ef4444' : '#94a3b8'}" stroke-width="2"/>` +
      `<text class="routing-node-label" x="${x}" y="${y+4}" text-anchor="middle">${re(n.label || n.id)}</text>` +
      `<text class="routing-role" x="${x}" y="${y+40}" text-anchor="middle">${stoppedSigner ? 'SIGNER STOP' : re(n.role)}</text>`;
  });
  svg.innerHTML = out;
  svg.querySelectorAll('[data-edge]').forEach(g => {
    const select = () => { routeEl('routingEdge').value = g.dataset.edge; showRoutingEdge(); };
    g.onclick = select;
    g.onkeydown = event => { if (event.key === 'Enter' || event.key === ' ') select(); };
  });
}

function showRoutingEdge() {
  const edge = routingLive?.edges.find(e => e.id === routeEl('routingEdge').value);
  if (!edge) return;
  const probe = edge.probe;
  const injection = routingLive.injections?.[edge.id];
  routeEl('routingProbe').textContent = `LIVE ${edge.id}: ${edge.state.toUpperCase()} · monitoring ${edge.monitoring} · ` +
    (probe ? `last independent probe ${probe.test.error_count}/${probe.test.test_count} errors, ${probe.test.tokens_lost || 0} losses · ${new Date(probe.timestamp*1000).toLocaleString()} · recovery ${probe.recovery.tested}/1024 tests over ${probe.recovery.rounds}/2 rounds` : 'No independent probe yet') +
    (injection ? ' · EXPERIMENTAL INTERCEPT ACTIVE' : '');
}
