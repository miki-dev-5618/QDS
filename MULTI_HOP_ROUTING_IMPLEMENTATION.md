# QDS Multi-Hop Routing: How It Works and How It Is Implemented

Date: 29 October 2026
Branch: `verif-eff` (baseline `8b8798a`, test baseline 270 passed / 1 skipped)
Companion to: `QDS_Multi_Hop_Routing_Blueprint.md` (requirements). This document records the design decisions taken against that blueprint, how the feature works, how it maps onto the code, and what is implemented so far.

> **Status: partially implemented, work paused.** Only the topology layer and the first part of the enforcement changes exist in the working tree. Everything else below is the agreed design, not running code. See [§13 Implementation status](#13-implementation-status).

---

## 1. What the feature does

Today every session goes Alice → `QR-1` → each verifier (a fixed star). Quarantine works on two pooled logical links, and `ChannelGuard.check_open` refuses **every** transmission while **any** link is quarantined.

With this feature:

1. The network is a **versioned, validated graph** of signer, relays and verifiers, connected by directed quantum edges.
2. Before a session is prepared, the engine **plans a route per recipient** and avoids quarantined edges and paths.
3. The quantum state is **teleported hop by hop** along the chosen route, so channel effects build up in route order.
4. **Isolation is scoped.** An edge, a path, the signer or forwarding can each be quarantined on its own, and only operations that need that scope are refused.
5. When no acceptable route exists, the request gets **HTTP 423** naming the affected recipient, the topology version and the blocking state.
6. Routes, reroutes, edge observations and refusals are **persisted, signed into audit records and shown on an admin graph**.

Example (demo topology):

```
            ┌── R1 ──── R2 ──┬── bob        primary   (cost 3, low noise)
  alice ────┤                └── charlie
            └── R3 ──────────┬── bob        alternative (cost 4, noisier, 2% loss/hop)
                             └── charlie
```

A tap on `R1->R2` is picked up by edge probes, and `edge:R1->R2` is quarantined. The current session is stopped under its normal rules. The next session plans again and goes through R3. Bob and Charlie remain reachable, and nothing is shut down globally.

---

## 2. Decisions taken (decision gate, blueprint §6)

| Topic | Decision | Source |
| --- | --- | --- |
| Scope of this pass | Phases 1–5 (topology, routing, multi-hop simulation, evidence-based isolation, audit/UI). Phase 6 only as a basic eval script plus documented limits | User |
| WATCH edges | **Opt-in fallback.** Prefer all-OPEN routes; use a WATCH route only if `allow_watch_fallback` is on (default **off**). Fallback use is recorded and raises the test budget | User |
| Edge localisation | **Independent per-edge probe sessions.** Only probe evidence moves an edge's state. End-to-end alarms act on **path scopes** and never single out an edge | User |
| Symmetrisation / forwarding | **Classical, assumed available.** Authenticated classical channel between all participants; not modelled as edges or included in quantum preflight. Forwarding keeps its own enforceable scope (`bob->charlie`) | User |
| Relay trust | Honest-but-curious operators. **No malicious-relay security claimed** | Default |
| Required recipients | All-or-nothing preflight for the signed roster | Default (blueprint) |
| Recovery | Admin reset → monitored probation (RESET_PENDING) | Default (existing model) |
| Probation edges | Eligible, ranked below OPEN, with a raised test budget | Default |
| Unmonitored edges | Eligible but **explicitly flagged** `unmonitored` in the plan; never reported as healthy | Default |
| Topology source | Versioned JSON in `config/topologies/`, plus a built-in legacy star | Default (blueprint) |
| Routing time | Before preparing tokens. No mid-session migration; a changed route aborts the session | Default (blueprint) |
| Default topology | `legacy-star/1` (compatible with today). Demo: `demo-multihop/1` | Default |

---

## 3. Architecture overview

```
           ┌──────────────┐  frozen per session   ┌───────────────┐
 JSON ───► │ topology.py  │──────────────────────►│  routing.py   │◄── guard states (edge:/path:/signer)
           │ validate,    │   simple paths,        │ RoutingPolicy │    + monitoring freshness
           │ digest       │   declared params      │ plan / 423    │
           └──────────────┘                        └──────┬────────┘
                                                          │ RoutePlan (per recipient)
                                                          ▼
 ┌──────────────┐  per-hop events   ┌──────────────────────────────┐   per-edge counters ┌───────────┐
 │ ChannelModel │──────────────────►│ protocol.distribute()        │────────────────────►│ router.py │
 │ (session,    │  edge params +    │  route-aware budgets         │                     └───────────┘
 │  hop 0)      │  hidden taps      │  revalidate each block       │
 └──────────────┘                   │  teleportation.py (multi-hop)│
                                    └──────────────┬───────────────┘
                                                   ▼
                       assess(): decide() ──► scope mapping ──► ChannelGuard.apply(...)
                                                   │                   ▲
                                 path alarm ──► auto-diagnose ──► monitoring.py (edge probes)
                                                   ▼
                          store.py (routes, observations, scopes) ─► audit.py (signed routing section)
                                                   ▼
                              server.py (API, 423) ─► admin.html / admin.js (graph)
```

### Modules

| Module | Role | State |
| --- | --- | --- |
| `topology.py` | Topology model, JSON validation, digest, simple-path enumeration, reachability, legacy star | **Implemented** |
| `config/topologies/demo-multihop.json` | Demo graph | **Implemented** |
| `enforcement.py` | Scoped states, no global stop, emergency stop, manual injection, migration | **Partial** |
| `routing.py` | `RoutingPolicy`, `RoutePlan`, planner, `NoRouteAvailable`, `RecipientUnreachable` | Designed |
| `monitoring.py` | Per-edge probe sessions, multiple-testing control, freshness | Designed |
| `teleportation.py` | Hop-by-hop teleportation (statevector and Qiskit) | Designed |
| `router.py` | Topology-aware per-edge counters and display state | Designed |
| `protocol.py` | Plan → distribute → revalidate → assess with scope mapping | Designed |
| `verifier.py` | Route-aware honest model per recipient | Designed |
| `store.py`, `audit.py` | Route and observation persistence, signed routing section | Designed |
| `server.py`, `admin.html`, `admin.js` | Endpoints, 423 payloads, graph UI | Designed |

---

## 4. Topology (implemented: `src/quantum_engine/topology.py`)

### Document format (`hedwig-topology/1`)

```json
{
  "schema": "hedwig-topology/1",
  "version": "demo-multihop/1",
  "max_hops": 4,
  "nodes": [{"id": "alice", "role": "signer"}, {"id": "R1", "role": "relay"}, {"id": "bob", "role": "verifier"}],
  "edges": [{"id": "alice->R1", "src": "alice", "dst": "R1", "depolarizing": 0.002, "eta_loss": 0.0,
             "damping_gamma": 0.0, "cost": 1.0}]
}
```

### Edge semantics

- Every edge is a **directed quantum teleportation hop**. Its two endpoints share one Bell pair per token. The upstream node Bell-measures and sends two correction bits downstream.
- The declared parameters (`depolarizing`, `eta_loss`, `damping_gamma`) describe the **honest calibrated channel** of that hop. They drive both the simulation and the evidence planning. They are configuration, not attack ground truth.
- Correction bits, the signer's reveal, symmetrisation and verifier forwarding go over an authenticated classical channel that is **assumed available**.

### Validation (rejected before activation)

- Unknown schema, empty version, duplicate node or edge ids, unknown roles.
- Verifier nodes that are not enrolled identities (`VERIFIER_POOL`), or enrolled identities given another role.
- No signer node.
- Self-edges, parallel edges (same ordered endpoints), and any `kind` other than `quantum`.
- Edges **into** a signer, or **out of** a verifier (a verifier is never a relay).
- Probabilities out of range (`depolarizing` and `damping_gamma` in [0,1], `eta_loss` in [0,0.99]) and costs that are not positive and finite.
- `max_hops` outside 1..8.

Directed cycles among relays are allowed, because routes are **simple paths** of at most `max_hops` edges. Unreachable verifiers are allowed and reported by `reachability()`. A session that needs one fails preflight.

### Helpers

- `pauli_flip(d) = 2d/3`: matched-basis flip probability of a depolarising hop.
- `compose_flips([...])`: **ordered composition** `e ← e + f − 2ef`. Percentages are never simply added.
- `Edge.honest_flip`, `Edge.survival = 1 − eta_loss`.
- `Topology.digest`: SHA-256 of canonical JSON. Every session records it so historical routes are never reinterpreted.
- `legacy_star()`: `legacy-star/1`. It has `alice->QR-1` plus `QR-1->v` for every enrolled verifier, all noiseless. Edge ids match the old router's hop names, so existing displays and tests keep working.

### Demo topology

`demo-multihop/1` has a primary path through R1→R2 (low noise, cost 3) and an alternative through R3 (higher noise, 2% loss per hop, cost 4) to bob, charlie, dave and erin. The other enrolled verifiers are deliberately unreachable, to demonstrate preflight failure.

---

## 5. Isolation scopes and enforcement (partially implemented: `enforcement.py`)

### Scopes

| Scope key | Meaning | What moves it |
| --- | --- | --- |
| `alice->verifiers` | Signer scope: signer or session findings that are not channel faults (external forgery, repudiation) | Detector decisions on signer transcripts with those classifications |
| `bob->charlie` | Pooled classical verifier-to-verifier forwarding | Decisions on forwarding transcripts (e.g. dishonest verifier) |
| `edge:<edge id>` | One quantum edge | **Only** edge probes, or admin **manual failure injection** (labelled) |
| `path:<e1>\|<e2>\|…` | One end-to-end route | Pooled end-to-end channel evidence from sessions that used that route |
| `*emergency-stop*` | Explicit global stop | Admin only; logged separately |

Every scope runs the existing state machine independently: OPEN → WATCH → QUARANTINED → RESET_PENDING → OPEN, with Fisher-combined escalation and watch-window expiry.

### Key behaviour changes

- **No implicit global stop.** `check_open(scope)` refuses only when *that* scope is quarantined or an emergency stop is active.
- **One incident per assessment.** When one assessment quarantines several path scopes, they share a single incident id.
- **No state bloat.** `apply()` with action `none` on a scope that never left OPEN does nothing and creates no entry.
- **Manual injection is labelled.** `force_quarantine()` records actor and reason with the prefix `MANUAL FAILURE INJECTION (admin; not detector evidence)` and sets `scope_note = "manual_failure_injection"`. It never counts as detector localisation.
- **Scoped reset.** `request_reset(scope)` resets one scope and leaves the others alone. `request_reset(None)` remains an explicit "reset everything".
- **Emergency stop.** `set_emergency(active, actor, reason)` is a separate, persisted global stop, distinct from quarantine.
- **Migration.** On first load of a pre-routing store, an active `alice->verifiers` or `bob->charlie` restriction is **kept**. It is labelled with `scope_note = LEGACY_NOTE` ("legacy pooled logical-link isolation … not attributed to any edge"), and a `system:migration` transition is logged once. No per-edge observation is invented. The marker `links_schema = hedwig-scopes/1` prevents a second migration.

**Already in the file:** `edge_scope()`, `path_scope()`, `scope_kind()`, the `EMERGENCY` and `SCOPES_SCHEMA` constants, `ChannelQuarantined.payload()`, the `EmergencyStop` exception and the `LinkState.scope_note` field.
**Not yet written:** the `ChannelGuard` rewrite described above. The old global-refusal `check_open` is still active.

### Which classification goes to which scope

| Classification (signer transcript) | Scope |
| --- | --- |
| `EAVESDROPPING_TAMPERING`, `UNDETERMINED_DISTURBANCE`, `INSUFFICIENT_TOKENS` | Path scopes of **every route the session used** |
| `EXTERNAL_FORGERY`, `REPUDIATION_ATTEMPT` | Signer scope `alice->verifiers` |
| `DISHONEST_VERIFIER_FORGERY` on forwarding | Forwarding scope `bob->charlie` |
| Classical rejections (replay, impersonation, integrity …) | None (unchanged policy: rejected and logged) |

So a forgery or impersonation finding is never read as a quantum-edge failure.

---

## 6. Route planning (designed: `routing.py`)

### `RoutingPolicy` (`hedwig-route/1`)

| Field | Default | Meaning |
| --- | --- | --- |
| `allow_watch_fallback` | `False` | Use a WATCH route only if no OPEN or probation route exists |
| `probation_eligible` | `True` | RESET_PENDING scopes may carry monitored traffic |
| `unmonitored_eligible` | `True` | Edges with no fresh probe are eligible but flagged |
| `max_paths_per_recipient` | 16 | Bound on enumeration |
| `max_route_honest_qber` | 0.05 | Above this, a route is *unacceptable for the security policy* |
| `min_route_survival` | 0.6 | Declared survival below this makes a route unacceptable |
| `probe_tokens`, `probe_round_alpha`, `probe_strong_alpha`, `probe_max_age_s`, `min_probe_samples`, `auto_diagnose` | 128, 0.01, 1e-3, 900 s, 32, `True` | Edge monitoring (§8) |

### Algorithm (deterministic)

For each recipient in the signed roster:

1. Enumerate simple paths `alice → v` (≤ `max_hops`, never through another verifier).
2. For each path, collect the states of its `edge:` scopes and its own `path:` scope.
   - Any QUARANTINED → **excluded**, with the reason recorded (e.g. `edge R1->R2 quarantined (INC-…)`).
   - Declared honest QBER or survival outside policy → **unacceptable for the security policy**. This is distinct from blocked.
3. Rank the eligible paths:
   - **Tier:** 0 for all OPEN, 1 if it contains probation, 2 if it contains WATCH (only when fallback is allowed).
   - **Tie-breaks**, in order: declared cost, then hop count, then the edge-id tuple. The result is reproducible, with no claim of global optimality.
4. Pick the first ranked path.

Preflight is **all-or-nothing**:

- If any recipient has no physical path → `RecipientUnreachable` (a `ConfigurationError`, **HTTP 400**).
- If any recipient's paths are all blocked or unacceptable → `NoRouteAvailable` (a `ChannelQuarantined`, **HTTP 423**). Its payload lists, per recipient, the rejected candidates and why, plus the topology version and the blocking scopes, without private evidence.

A signer-scope quarantine or an emergency stop refuses before planning.

### `RoutePlan` (recorded with the session)

```json
{
  "topology_version": "demo-multihop/1", "topology_digest": "…", "policy_version": "hedwig-route/1",
  "routes": {"bob": {"edges": ["alice->R3","R3->bob"], "nodes": ["alice","R3","bob"], "hops": 2,
                     "cost": 4.0, "tier": "open", "honest_qber": 0.0253, "survival": 0.9604,
                     "unmonitored_edges": ["R3->bob"], "suspect_edges": []}},
  "rejected": {"bob": [{"edges": ["alice->R1","R1->R2","R2->bob"], "reason": "edge R1->R2 quarantined (INC-…)"}]},
  "fallback_used": false,
  "reroutes": [{"recipient": "bob", "old": [...], "new": [...], "reason": "edge R1->R2 quarantined"}]
}
```

`reroutes` compares each route with the recipient's previous route and gives the reason the old one was rejected.

---

## 7. Multi-hop quantum simulation (designed: `teleportation.py`)

### Model

A route of *k* edges means *k* successive teleportations. At hop *i*, the node holding the state Bell-measures it together with its half of the hop's Bell pair. The two correction bits go classically downstream, and the receiver applies `X^m2 Z^m1`. Unknown states are never copied: each recipient gets its own copy prepared by Alice, as today.

### Data structures

- `HopEvent(eve_basis, noise_pauli, damping_gamma, is_lost)`: the channel events on one edge for one token.
- `TeleportJob.path_events: Tuple[HopEvent, ...]` holds one event per route edge.
  - Hop 0 applies the legacy job fields first (the session `ChannelModel`: Eve, noise, damping, Bell-measurement readout), then `path_events[0]`.
  - Hops `i ≥ 1` apply `path_events[i]`.
  - Verifier readout applies only at the final measurement.
- `TeleportOutcome` gains `lost_at_hop` and `hops_attempted`.

### Event sampling (`protocol.distribute`)

Each token is sampled along its recipient's route:

- **Declared edge noise and loss:** `rng` is drawn **only when the parameter is > 0**. Noiseless legacy-star sessions therefore use exactly the same random stream as today, and existing seeded tests are unaffected.
- **Hidden edge taps** (`engine.network_taps[edge] = intercept_rate`): experimental ground truth set by the injector or admin. They are applied to session tokens and probes that cross the edge, and are **never** passed to the detector, the planner or the scope mapping.

### Statevector backend

- Hop 0 runs the existing 3-qubit circuit.
- After the corrections, the travelling qubit is pure: q0 and q1 have been measured. Its 2-vector is extracted and used as the input of the next hop.
- A hop with no events is an exact identity under the correction convention. It is **elided** by default, so the RNG stream stays identical. A `faithful_hops=True` backend option simulates every hop, and tests check that both modes agree.
- Loss at hop *i* stops the token: it counts as attempted on hops 0..i and lost at *i*, and is never counted as a contradiction.

### Qiskit backend

- Multi-hop jobs are built as one circuit with `1 + 2k` qubits, mid-circuit Bell measurements and `if_test` corrections at each hop.
- Readout errors use a per-width `NoiseModel` on the hop-0 Bell qubits and the final qubit.
- Single-hop-equivalent jobs keep the existing circuit.

### IBM fake backend

It supports only routes whose edge events are all empty. Otherwise it raises a `ConfigurationError`, which is the honest limitation.

### Resource accounting

The router counts **attempted / received / lost** per edge from each token's actual progress, only for tokens actually sent (early abort included). It does not assume that every token crossed the whole path.

---

## 8. Edge monitoring and attribution (designed: `monitoring.py`)

Pooled end-to-end errors cannot identify a faulty middle edge, so edge state is driven only by **independent per-edge probe sessions**.

- **Probe.** The edge's endpoints run a single-hop teleportation of `probe_tokens` test tokens across that edge alone. The run uses the edge's declared noise and loss, plus any physical tap. Tokens are measured in their preparation basis.
  - Trust assumption: honest-but-curious relays run probes faithfully.
- **Null hypothesis.** The honest probe QBER is `compose(params.honest_qber, edge.honest_flip)`. This is conservative: a larger null means fewer false alarms.
- **Multiple testing.** A probe round over *m* edges uses Bonferroni thresholds: `probe_round_alpha/m` (→ WATCH) and `probe_strong_alpha/m` (→ QUARANTINE). The target is the stated network-wide false-alarm rate per round, not a per-test rate reused as a network guarantee.
- **Insufficient samples.** Fewer than `min_probe_samples` received → the observation is recorded as `insufficient` and no state changes.
- **Probation.** A passing probe on a RESET_PENDING edge returns it to OPEN.
- **Freshness.** Each edge reports `fresh`, `stale` (older than `probe_max_age_s`) or `unmonitored`. The planner flags non-fresh edges rather than treating them as healthy.
- **Auto-diagnosis.** After a path-scope WATCH or QUARANTINE (if `auto_diagnose`), the engine probes every edge on the affected routes with a dedicated `probe_rng`, so edge localisation comes only from edge-scope evidence.
- **Triggers.** Probes run on admin request (`POST /api/topology/probe`) and in auto-diagnosis. Optional auto-probing of stale edges before a session is off by default.

### Kinds of information and where each may be used

| Kind | Permitted use |
| --- | --- |
| Edge probe measurements | Move that edge's scope |
| End-to-end session measurements | Move path scopes of the routes used; trigger diagnosis |
| Injector taps (`network_taps`) | Ground truth in `result.ground_truth` and experiment reports only |

A session-wide intercept on the star (today's `EVE_INTERCEPT`) quarantines the **path** scopes and leaves the edges OPEN. That is the intended "no unsupported unique-edge attribution" outcome.

---

## 9. Route-aware calibration and evidence planning

Longer or noisier routes have higher honest error rates, so each session's statistics are built from the routes it actually uses. Only declared and calibrated values are used, never the attack label.

| Quantity | Route-aware rule |
| --- | --- |
| Per-recipient honest QBER | `compose(params.honest_qber, declared flips along that recipient's route)`, passed to the verifier as `DistributionRecord.honest_qber`. The verifier evaluates its elimination rule with `replace(params, honest_qber=…)` |
| Test tokens | Assigned round-robin to the recipients' routes (`Slot.route_to`); per-route counts are recorded as path-level observations |
| Pooled Tier-1 null | Mean of the route QBERs over the test-token assignment. Using a binomial at the mean is conservative relative to the true Poisson-binomial |
| Test-token budget / early-abort threshold | Computed with the session's null QBER |
| Reserve plan | Uses the worst route QBER, and planned loss `max(observed_loss, 1 − min route survival)` |
| Unattainable assurance | Routes over `max_route_honest_qber` or under `min_route_survival` are refused as *policy-unacceptable*, not as disconnected |

On the legacy star every route equals `params.honest_qber`, so behaviour is unchanged. Rerouting onto a longer path is an availability trade-off, not equal verification quality, and the plan reports both values.

---

## 10. Session lifecycle

1. Validate the roster and freeze the active topology (version and digest).
2. Check the emergency stop and the signer scope.
3. **Plan** routes (§6). Refuse with 400 or 423 before any token is prepared.
4. Compute route-aware budgets (§9) and record the plan.
5. Prepare, symmetrise and interleave tokens as today; each slot carries its recipient's route.
6. Teleport in blocks along the routes. **Before every block, revalidate** the plan against current scope states. If an edge or path used by the plan has become quarantined (for example by a concurrent probe), stop sending and set `route_abort = {reason, tokens_sent}`.
   - The session is aborted and never revealed.
   - Tokens already sent are reported; there is no claim of an atomic rewind.
7. If an alarm, insufficient tokens or a route abort occurred, nothing is revealed. Otherwise reveal and verify under the existing commitment, reserve and replay rules.
8. Assess: classification → decision → **scope mapping** (§5) → transitions (shared incident id) → optional auto-diagnosis → signed records.
9. The next session plans again and may take another route. Any retry is a **new** session with fresh identifiers, commitments and evidence. Partially distributed evidence is never reused.

Relay hops and **verifier forwarding depth** stay separate. Crossing more relays never increments the signature transfer level.

---

## 11. API, persistence, audit and UI (designed)

### API (`server.py`)

| Endpoint | Role | Purpose |
| --- | --- | --- |
| `GET /api/topology` | any | Topology, edge states, freshness, counters, last plan (other recipients' routes stripped for verifiers) |
| `POST /api/topology/activate` | admin | Activate a preset (`star`, `demo-multihop`) or a validated JSON document for **future** sessions |
| `POST /api/topology/probe` | admin | Probe one edge or all edges |
| `POST /api/topology/edges/{id}/manual-fault` | admin | Manual failure injection (labelled) |
| `POST /api/topology/taps` | admin | Arm or disarm a hidden tap (**experimental ground truth**) |
| `POST /api/channel/reset` | admin | Now takes any scope (`edge:…`, `path:…`, signer, forward) or all |
| `POST /api/channel/emergency-stop` | admin | Set or clear the emergency stop |
| `GET /api/sessions/{id}/routes` | admin | The routes **recorded** for that session |

**423 payload.** `status` is `no_route`, `quarantined` or `emergency_stop`. It also carries `operation`, the blocked recipients with reasons, `topology_version`, the blocking scopes (state, incident id, reason, `scope_note`) and `refusal_us`.
- Physically unreachable recipients and malformed topologies return **400**.
- Policy-blocked routes are never described as physical disconnection.

### Persistence (`store.py`)

- New tables:
  - `session_routes(session_id, topology_version, plan, created_at)`
  - `edge_observations(id, ts, edge, topology_version, n, received, errors, p_value, decision, round_id, detail)`
- New kv entries: `topology:<version>` snapshots, the active topology, `emergency_stop`, `links_schema`.
- All scopes stay in the `links` kv. The transitions table's `link` column holds the scope key.
- After a restart, restrictions and history are restored. Quantum evidence is never rebuilt from summaries, and restored probe results are subject to the freshness rule.

### Audit (`audit.py`)

- New transaction records carry a `routing` section: plan, topology digest, fallback use, reroutes, per-edge token metrics for the session and any `route_abort`.
- Incident records list every affected scope.
- Old certificates are untouched and still verify, because signatures cover the stored payload bytes. Signed history is never rewritten: later state changes produce new transitions and records.

### Admin UI (`admin.html`, `admin.js`)

- **Graph.** Nodes are laid out by BFS layer from the signer, with directed quantum edges. Every edge shows a **text** state label as well as colour (OPEN / WATCH / QUARANTINED / PROBATION).
- **Routes and reroutes.** Each recipient's selected route is highlighted, with the topology version. Reroute entries show the old path, the new path and the reason.
- **Edge table.** For each edge: state and reason, last probe (time, QBER, p-value, freshness), and attempted / received / lost tokens.
- **Admin controls.** Probe all, manual fault, scoped reset, topology preset, emergency stop.
- **Ground-truth panel.** Taps appear in a separate panel labelled "EXPERIMENTAL GROUND TRUTH — not visible to the detector". Edge colour alone never implies proven localisation.
- **History.** Historical sessions are drawn from their **recorded** routes, not from the current topology.

---

## 12. Validation plan

New `tests/test_routing.py`, plus updates to tests whose old expectations the blueprint deliberately changes:

| Scenario | Expected |
| --- | --- |
| Legacy star, 2 verifiers | Existing workflows unchanged; seeded RNG streams identical |
| Topology validation | Each structural rule in §4 rejected with a clear error |
| Noiseless multi-hop | Unit fidelity; elided and faithful hop modes agree |
| Noisy / lossy route | Ordered composition matches `compose_flips`; loss is attributed per hop and is not a mismatch |
| Middle-edge tap + probe | `edge:R1->R2` quarantined; next session routes via R3 |
| Unrelated edge quarantined | Unaffected sessions proceed (no global stop) |
| All routes blocked | 423 with recipients, version and blocking scopes; no bypass through legacy `forward`/`deliver` |
| Only WATCH routes | Refused by default; used and recorded with `allow_watch_fallback` |
| End-to-end alarm, no edge evidence | Path scopes move; all edges stay OPEN |
| Same observations, different tap label | Identical decisions |
| Shared edge fault | All dependent recipients rerouted or refused consistently |
| Mid-session quarantine | `route_abort`, never revealed, tokens sent reported |
| Edge reset | Probation; passing probe → OPEN; other scopes unchanged |
| Restart / legacy DB | Restrictions kept; legacy label and migration transition present; old certificates verify |
| Forgery / forwarding attack | Signer / forward scope only; no edge state change |

Tests that change on purpose: `test_strong_alert_quarantines_immediately_and_blocks_all_links` (now scoped), `test_router_drops_quarantined_link` (edges no longer mirror pooled state), `test_alert_quarantines_link_until_reset` and `test_quarantine_blocks_until_reset` (path scopes and resets).

**Phase 6 (basic):** `experiments/routing_eval.py` measures probe false-alarm and detection rates, honest acceptance by path length, reroute success and refusal rate on the demo graph. It reports trial counts and uncertainty and makes no numeric promises.

---

## 13. Implementation status

| Item | Status |
| --- | --- |
| Decision gate (§2) | ✅ Resolved with the user |
| `topology.py` (model, validation, paths, digest, legacy star) | ✅ Written, not yet covered by tests |
| `config/topologies/demo-multihop.json` | ✅ Written |
| `enforcement.py` scope helpers, `EmergencyStop`, `ChannelQuarantined.payload`, `LinkState.scope_note`, new module docstring | ✅ Written |
| `ChannelGuard` rewrite (no global stop, emergency, manual injection, scoped reset, migration) | ⏸ Designed, not applied. **The old global `check_open` is still active** |
| `routing.py`, `monitoring.py` | ⏸ Designed |
| Multi-hop `teleportation.py` (statevector + Qiskit) | ⏸ Designed |
| `router.py`, `protocol.py`, `verifier.py` integration | ⏸ Designed |
| `store.py`, `audit.py` persistence and signing | ⏸ Designed |
| `server.py` endpoints and 423 payloads; admin graph UI | ⏸ Designed |
| Tests, eval script, README | ⏸ Not started |

The working tree also shows `experiments/calibration/ibm_generic_backend_5q.json` as modified. Running the test suite rewrites it; it is not part of this feature.

### Suggested order to resume

1. `ChannelGuard` rewrite, then update the four intentionally changed tests.
2. `routing.py` and the `router.py` rewrite, with manual edge states only (Phase 2 exit).
3. Multi-hop teleportation and `distribute()` integration with route-aware budgets (Phase 3 exit).
4. `monitoring.py` and the assessment scope mapping (Phase 4 exit).
5. Persistence, audit, API and UI (Phase 5 exit).
6. `routing_eval.py`, README limits and trust model.

---

## 14. Limits and assumptions (to keep in the README)

- Simulation only: no physical fibre switching, hardware, or entanglement provisioning.
- Relays are honest-but-curious, with **no security against malicious or colluding relays**.
- The classical channel (corrections, reveal, symmetrisation, forwarding) is assumed authenticated and available.
- No mid-session failover. Retries are visible new sessions.
- Localisation needs probe evidence. End-to-end evidence alone restricts paths, not edges.
- An attacker controlling every alternative route can still deny service.
- Rerouting onto a longer route trades verification margin for availability.
- Supported graph and path sizes are to be set from the Phase 6 measurements; up to 8 hops is accepted structurally.
