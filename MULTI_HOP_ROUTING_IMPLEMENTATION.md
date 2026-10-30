# Multi-hop routing and link-aware rerouting

Implemented 30 October 2026, using the alternate-routing guide as a blueprint.

The default topology remains the compatible `legacy-star/1`. The admin console can activate `demo-multihop`, or upload a validated topology JSON. Set `HEDWIG_TOPOLOGY=demo-multihop` to select the bundled demo at startup. A persisted activation is otherwise restored after restart.

## Try the requested demonstration

1. Start the server normally, log in as Admin, and find **Links & router ? Quantum routes**.
2. Select **Multi-hop demo (R1/R2 + R3)** and click **Activate preset**. Use Bob and Charlie (the demo additionally supports Dave and Erin).
3. Send an authentic baseline. Its recorded routes use Alice ? R1 ? R2 ? each recipient.
4. In **Experimental ground truth**, select `R1->R2` and click **Inject intercept**. This changes simulation physics only, without declaring a detector finding.
5. Click **Probe selected edge**. The independent probe reports counts, its statistical decision, and the resulting topology-specific edge state. Detection is statistical; a failed probe can be repeated with fresh evidence.
6. Send a fresh authentic transmission. Once the middle edge is restricted, its route uses Alice ? R3 ? each recipient. The first session keeps its original topology and route snapshot.
7. Quarantine `alice->R3` manually as well. A new send returns HTTP 423 with affected recipients, rejected candidates, and search-completeness information before preparing tokens.
8. Remove the injected intercept, reset the primary edge to probation, and run recovery probes. Edge recovery needs at least 1024 surviving probe tests over at least two rounds after reset. A new adverse observation re-quarantines it.

Manual quarantine and WATCH controls remain explicitly labeled as manual events. Emergency stop is separate and cannot be cleared with the ordinary reset button.

## Implementation and policy

- `topology.py` validates bounded, directed graphs with exactly one signer; rejects malformed entries, boolean hop counts, nonfinite numbers, invalid roles/endpoints, self/parallel edges, and invalid verifier identities. Nodes, edges and adjacency are immutable. Canonical serialization sorts nodes and edges; labels and descriptions are included in the digest.
- `routing.py` performs bounded, deterministic simple-path search. It prunes blocked edges before expanding them, rejects restricted exact paths and unacceptable error/survival predictions, and allocates the complete roster before preparation. Priority is OPEN over probation over explicitly permitted WATCH, then monitoring freshness, cost and stable edge IDs. It does not filter only the first 64 DFS candidates. An exhausted work budget reports an incomplete search, not disconnection.
- `enforcement.py` checks only required scopes plus explicit emergency stop. Edge/path IDs hash structured data including topology identity. Old pooled restrictions remain pooled and persist; migration never fabricates edge attribution. Duplicate evidence cannot create duplicate strikes, including after restart.
- `teleportation.py` executes each hop with a fresh Bell pair, Bell measurement and classical Pauli correction. The statevector backend carries the corrected amplitudes into the next circuit; Qiskit connects each destination qubit to the next Bell circuit. Neither measures and reconstructs an intermediate preparation label. Destination measurement occurs once. IBM fake-backend calibration is supported only for the exact legacy star through its existing effective logical-channel model; custom topologies require statevector or Qiskit and fail configuration preflight otherwise.
- `multihop.py` builds ordered declared/injected hop channels and records real traversal. Heralded loss ends the token; downstream edges receive no attempt. One Bell pair is consumed per edge attempt, including a lost attempt. Shared edges accumulate separate recipient-copy uses. Probe counters remain separate from user-session counters.
- `protocol.py` freezes plans, preflights every recipient, and checks required scopes before each block and immediately before reveal. A changed restriction aborts that plan and discards valid-evidence status; retrying requires a new session. Interrupted/insufficient sessions return an unrevealed placeholder with no signature or blinding. Their actual attempted work remains recorded.
- `monitoring.py` produces independent edge probes. End-to-end observations restrict recorded paths and never identify an individual edge. The exact legacy star retains its pre-existing pooled response convention for backward compatibility. Signer findings and classical forwarding keep their separate scopes.
- `store.py` retains immutable plans, topology snapshots, finalized execution, probe observations, activations, refusals and transitions. Live counters and hidden experimental attacks are process-local. One-time verifier evidence is not restored for new verification after restart.
- `audit.py` signs topology/plan/execution commitments, binding the full route snapshot in attached evidence. Admin downloads include that evidence. Participant downloads omit it and retain verifiable signed commitments, while participant route endpoints return only that recipient's route and counters. Mutating routes, execution or their signed commitments fails audit verification.

The server supports one process/worker. Guard locks serialize a scope transition against one transmission block and the reveal check; up to the already-running block may complete before a pending quarantine is applied. SQLite durability does not provide cross-process coordination of live guards or quantum evidence. Run with one Uvicorn worker.

## Channel and evidence model

Per-hop order is heralded loss, experimental interception on the traveling Bell half, independent declared/injected Pauli channels, damping, Bell measurement, authenticated correction bits and Pauli correction. Only the destination makes the verifier measurement. Session-wide legacy experimental noise acts once at the first hop; declared edge noise acts at every hop. Preparation labels are used only at the signer and for later test disclosure.

For declared Bell-half depolarization `p` followed by amplitude damping `g`, the teleportation-averaged Bloch transfer coefficients are:

- X: `(1 - 4p/3) * sqrt(1-g)`
- Z: `(1 - 4p/3) * (1-g)`

Multiply these coefficients in route order. The per-basis QBER is `(1-coefficient)/2`; the uniform BB84 prediction is their mean. A single damping hop therefore has mean QBER `(g + 1 - sqrt(1-g))/4`, not `g/4`. Survival is the product of edge survival probabilities. The statistical null uses a conservative maximum of the two basis errors, composed with the pre-existing honest Pauli error envelope; it does not apply a binomial test at a heterogeneous mean. Verification records retain recipient-specific parameters and evidence counts.

Custom-topology sessions allocate a test budget to each recipient and split the false-alarm budget between the pooled test and the Bonferroni-corrected route tests. Counts are tested against their fixed planned sample budgets, including under loss and decisive early stopping. Too little surviving evidence at any required recipient aborts the entire session. Early stopping uses the conservative planned-count threshold; unfinished tokens are never counted as sent.

Independent monitoring round `r` spends `alpha * 6/(pi*r)^2`, divided among the tested edges. The sum across all rounds is at most alpha under the declared independent channel model. Probe rounds and recovery evidence persist. The existing broader signer/Tier-2 response policy remains an illustrative simulation policy, with its original repeated-assessment assumptions; this is not a composable security proof.

Relays are assumed to follow the protocol. Classical correction/reveal/symmetrisation/forwarding channels are assumed authenticated; this simulation does not implement a quantum-network classical authentication mechanism or resistance to malicious/colluding relays. Quantum relay hops and classical signature forwarding depth are distinct quantities. Distinct prepared copies travel to distinct recipients; no relay copies an unknown state.

## APIs and views

| Endpoint | Access / behavior |
| --- | --- |
| `GET /api/topology` | Authenticated; topology, edge restriction state and independent monitoring freshness; experimental injections and full router data are admin-only |
| `POST /api/topology` | Admin; activate `{preset: "demo-multihop"}` or `{topology: ...}` for future sessions |
| `GET /api/routing/refusals` | Admin; persisted preflight refusals and rejected candidates |
| `GET /api/routing/history` | Authorized stored route plans and execution; recipient-filtered outside Admin |
| `GET /api/sessions/{id}/routes` | Authorized historical topology, plan, decisions and execution |
| `POST /api/routing/fault` | Admin; edge, reason and action `attack`, `clear_attack`, or `manual`; manual state `watch` or `quarantined` |
| `POST /api/routing/probe` | Admin; distinct edge IDs and 64?4096 fresh test tokens per edge |
| `POST /api/channel/reset` | Admin; existing edge/path/signer/forwarding scope; edge enters monitored probation |
| `POST /api/routing/emergency` | Admin; explicit `enabled` boolean and reason |

The dashboard has a directed graph with text states, an independent selected-route halo, recipient route allocation table, candidate decisions, adjacency matrix, incidence matrix, actual edge-resource table and fresh-session route history. Historical views read their stored snapshots. Distribution completion is separate from whole-session verification acceptance; completed physical traversal never makes a partially aborted session valid.

## Validation and reproducible evaluation

Run `python -m pytest -q` for the complete suite. New routing tests cover canonical immutable identity, malformed documents, unambiguous scopes, paths beyond the old candidate cutoff, stale/unmonitored policy, local restrictions, WATCH fallback, independent edge attribution, both teleportation backends, damping predictions, upstream and concentrated loss, in-flight and pre-reveal quarantine, monitored recovery, durable history, authorization, emergency stop, duplicate evidence and signed-route tampering.

Run `python experiments/routing_eval.py --trials 10 --seed 2026 --output experiments/routing_results.json` for matched primary/fresh-session-failover trials. Every attempted outcome, including refusal/inconclusive outcomes, is retained. Allocation, verification acceptance, loss, Bell pairs, probe overhead, route predictions and host timing are reported separately. The checked-in sample uses three trials and is a functional smoke evaluation; its wide Wilson intervals do not establish a production acceptance/detection rate.
