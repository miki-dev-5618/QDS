# QDS: Multi-Hop Routing and Link-Aware Rerouting

Date: 29 October 2026  
Status: Design blueprint; no feature implementation included  
Repository branch: https://github.com/miki-dev-5618/QDS/tree/verif-eff  
Reviewed baseline: `8b8798a3c10d20ea59794ed59305cd824feb2880` — Added N-Verfiers Extension

## 1. Objective

Allow QDS evidence distribution to use multiple relay paths and continue serving reachable recipients when a particular network edge is quarantined.

The feature changes isolation from a global stop to evidence-based, appropriately scoped isolation. It adds route selection, alternative paths, per-edge operational state, multi-hop channel simulation and an explanatory admin graph.

The goal is delivery resilience within the existing closed simulation. It is not public verification, a production quantum network, or an automatic improvement in signature security.

## 2. Document boundary

This document describes required behaviour, design constraints, unresolved decisions, work packages and acceptance criteria. It does not prescribe classes, algorithms, database layouts or implementation code.

The implementer must independently inspect the current repository, reconcile intervening changes, choose an architecture and validate its assumptions. Recommendations below are proposed defaults unless marked as required correctness constraints.

Creating this document does not authorise implementation, repository changes or deployment.

## 3. Current behaviour and the intended change

The latest reviewed router supports the N-verifier roster but retains a star through one relay. Additional recipients receive additional `QR-1->verifier` hops.

The enforcement layer tracks two logical groups:

- `alice->verifiers`: signer distribution and reveal workflow.
- `bob->charlie`: legacy identifier now used for pooled verifier transfers.

Hop states mirror their logical group. Counters are per hop, but observations and quarantine are not independently attributed to each edge. In `check_open`, any quarantined logical link blocks every new transmission, even on the other group.

| Current behaviour | Target behaviour |
| --- | --- |
| Fixed star | Configurable graph with alternative relay paths |
| Global refusal when any logical link is quarantined | Refuse only operations whose required routes or other applicable safety policies make them unavailable |
| Hop colours mirror pooled state | Edge colours reflect independently supported edge state |
| No alternate-path selection | Select an eligible route before distribution |
| Pooled observations | Explicit distinction between edge observations and end-to-end observations |
| Aggregate route representation | Auditable record of the actual path and topology version |

The code review is not a runtime validation. Establish a test baseline before changing these behaviours.

## 4. User-visible example

Configure two paths to Bob:

- Primary: Alice → R1 → R2 → Bob.
- Alternative: Alice → R3 → Bob.

During an attack scenario, independent monitoring of R1–R2 produces sufficient evidence to quarantine that edge. The current affected session is stopped or rejected under its normal rules. A subsequent session selects the route through R3.

Alice can continue reaching Charlie if Charlie's own required distribution and symmetrisation routes remain usable. If Bob is required for the session and cannot be reached, the configured session policy determines whether the entire session is refused; this must not be decided implicitly by the interface.

If no eligible route exists, return HTTP 423 with a reason and the affected recipient or operation. Do not describe a policy-blocked route as a physical disconnection.

## 5. Goals and non-goals

### Goals

- Represent relays, signer, verifiers and permitted edges in a validated graph.
- Simulate the quantum-state path through multiple hops rather than merely draw extra relays.
- Accumulate channel effects along the selected path.
- Associate operational state and supporting observations with stable edge identities.
- Avoid quarantined edges and prefer healthy paths over suspect alternatives.
- Preserve distribution commitments, bounded reserve evidence, replay protection and observation-only threat detection.
- Explain selected paths, unavailable paths and rerouting decisions in the dashboard and audit history.
- Integrate with the newly added N-verifier configuration without treating verifier forwarding depth as relay-hop count.

### Non-goals for the first release

- Physical fibre switching, quantum hardware deployment or production entanglement provisioning.
- Arbitrary Internet routing or universal signature verification.
- Seamless migration of an in-progress quantum session between paths.
- Automatic proof of which edge an attacker used from end-to-end errors alone.
- Guaranteed availability against an attacker controlling all alternative routes.
- Proven security against malicious or colluding relays.
- Dynamic topology editing during an active session.
- Load balancing, congestion optimisation or a general network orchestration platform.

## 6. Decisions to resolve before implementation

| Decision | Recommended initial direction | Reason |
| --- | --- | --- |
| Topology source | Versioned JSON configuration | Reproducible, reviewable demonstrations |
| Routing time | Before preparing/distributing a new session | Avoids unclear evidence ownership during migration |
| Route changes during distribution | Abort affected session; start a fresh session if retry is permitted | Preserves session and evidence boundaries |
| QUARANTINED edges | Always excluded from ordinary traffic | Prevents bypass of enforcement |
| WATCH edges | Prefer OPEN routes; use WATCH only under an explicit fallback policy | Original screenshot excludes WATCH; fallback is a proposed change needing approval |
| RESET_PENDING edges | Explicit monitored probation policy | Do not silently equate probation with healthy operation |
| Required recipients | All-or-nothing preflight for the configured roster | Preserves signed roster and expected group semantics |
| Route selection | Deterministic eligible-path preference, considering declared channel cost | Reproducible without prescribing an algorithm |
| Isolation trigger | Independent edge observations; otherwise retain broader scope | Avoids invented localisation |
| Recovery | Admin reset followed by monitored probation | Compatible with existing operational model |
| First demonstration | A small fixed graph with an attacked middle edge and one alternative | Keeps validation interpretable |

Decision gate: confirm WATCH handling, relay trust model, monitoring method, required-recipient semantics, recovery behaviour and treatment of symmetrisation traffic before implementing security-sensitive routing.

## 7. Topology contract

Each topology version must declare unique node and edge identities, node roles, endpoints, directionality, channel type, channel parameters and operational cost metadata needed by the chosen routing policy.

Keep quantum-distribution edges distinct from authenticated classical communication. Define whether classical corrections use a separate network, an assumed always-available channel or explicitly modelled edges.

Validate configuration before activating it:

- Referenced nodes exist and have compatible roles.
- Duplicate or ambiguous edge identities are rejected.
- Noise, loss and other probabilities are valid.
- Directionality is explicit; do not assume a reverse edge exists.
- A configured verifier has a meaningful reachability result.
- Unsupported loops, self-edges or parallel-edge configurations are rejected or explicitly supported.
- Paths cannot traverse another verifier as a relay unless that role combination is deliberately supported.

Unreachable participants may be allowed in the graph for demonstrations, but sessions requiring them must fail preflight clearly.

Freeze the active topology version for each session. Applying a new configuration affects future sessions, not the meaning of existing records.

## 8. Multi-hop quantum simulation and trust boundary

The feature must do more than count hops. The receiving verifier's observation must reflect the channel effects along its actual selected path.

At the model level, each teleportation hop consumes the appropriate simulated entanglement resource, produces Bell-measurement information and transfers the state onward with the required correction treatment. The developer may choose a faithful circuit representation or a validated equivalent channel composition.

Required properties:

- In the noiseless case, multiple hops reproduce the prepared state under the model's correction convention.
- Hop effects are applied in route order; do not add QBER percentages as a generic composition rule.
- Loss at a hop prevents that token from arriving downstream and is counted consistently.
- Do not copy unknown quantum states to supply extra paths or recipients.
- A rerouted new session obtains fresh session identity and evidence; it does not reuse partially distributed evidence as though untouched.
- Reserve tokens experience the declared route/channel model before reveal.
- Resource metrics reflect attempted hops, including losses, rather than assuming every token traversed the whole path.

The statement “the relay never sees the state” needs qualification. The relay interface must not expose Alice's preparation labels or let the normal simulated relay inspect those labels. Teleportation and authenticated classical corrections alone do not establish security against an arbitrarily malicious relay.

Explicitly state whether relays are trusted operators, honest-but-curious abstractions, or adversarial components. The first release must not claim malicious-relay security unless analysed and tested for the selected construction.

## 9. Route-aware calibration and evidence adequacy

Longer paths can produce different honest error and survival rates. The verifier must not compare a longer, noisier route against an unrelated single-hop honest baseline without justification.

Define how the honest mismatch model, channel-test null hypothesis, test budget and reserve plan depend on the selected route and declared/calibrated channel parameters.

Required constraints:

- Determine the session's planned policy and evidence budget before reveal.
- Use observable configuration or calibration, not the injected attack label.
- Preserve false-alarm and detection-power reporting under the selected model.
- Report inadequate evidence honestly rather than making thresholds permissive after seeing a failed result.
- Refuse or flag routes whose expected loss/noise makes the requested assurance unattainable.
- Distinguish physical reachability from a route being acceptable for the security policy.

Rerouting through a longer path is therefore an availability trade-off, not a guarantee of equivalent verification quality.

## 10. Edge monitoring and attribution

This is the central security design problem. Pooled end-to-end channel errors cannot identify a unique faulty middle edge.

Per-edge state transitions require observations that actually support that scope. Candidate approaches include independent per-link test sessions or monitored link-establishment/calibration observations under a declared trust model. The developer must select and justify the method.

Separate three kinds of information:

| Information | Permitted use |
| --- | --- |
| Independent edge measurements | Assess that edge under the declared model |
| End-to-end recipient measurements | Assess the observed path/session; localisation requires additional evidence |
| Attack injector's selected edge | Experimental ground truth only; never an input to detector or quarantine selection |

An admin-forced edge shutdown may demonstrate routing independently of detection, but label it as manual failure injection. It cannot count as evidence that the detector localised an attack.

Multiple edge tests increase the number of statistical decisions. Define the scope of false-alarm targets and any adjustment or aggregation method; do not reuse a per-test target as a network-wide guarantee.

Monitor confidence, evidence age and insufficient samples. Unmonitored edges are not automatically healthy. Define their eligibility explicitly.

If only path-level evidence is available, use a conservative path-level response or request further diagnosis. Do not arbitrarily quarantine one edge merely to produce the desired rerouting animation.

## 11. State, routing and enforcement semantics

Maintain operational state independently for each supported edge. Suggested states align with the current model: OPEN, WATCH, QUARANTINED and RESET_PENDING. A separate evidence freshness/unknown status may be needed; its representation is left to the implementer.

Ordinary route selection must exclude quarantined edges. Under the proposed fallback policy, first search for an acceptable OPEN route, then consider WATCH routes only if configured. Record any fallback and its extra monitoring requirements.

Define deterministic tie-breaking and enforce path bounds. A shortest path by hop count is not necessarily the best path under loss, error or policy constraints. Document the selected objective without claiming a universally optimal route.

Required enforcement outcomes:

- Quarantine of an unrelated edge does not globally block all traffic.
- A blocked edge cannot be used by changing an API route or invoking a legacy forwarding action.
- All applicable scopes are checked: edge state, signer/session restrictions, authentication and evidence validity.
- A signature forgery or impersonation finding is not automatically interpreted as failure of a quantum edge.
- Explicit emergency global shutdown may remain, but must be distinct from ordinary edge quarantine.
- Recovery of one edge does not reset unrelated quarantines.

Handle races between route selection and quarantine: revalidate before use and stop affected work safely if state changes. Define the treatment of already-sent tokens; do not report an atomic rewind.

## 12. Integration with N verifiers and symmetrisation

For each configured verifier, determine the required distribution route before a session starts. Recipients keep distinct evidence and identity even if their paths share edges.

Shared edges have shared consequences. Quarantining Alice–R1 can affect several recipients, while quarantining a leaf edge may affect only one. The interface and refusal reason must show that dependency.

The existing symmetrisation phase also moves evidence between participants. Decide whether those movements are modelled as quantum transfers or protected classical evidence exchanges, consistent with the current extension's design. Their required connectivity must be included in preflight; routing Alice-to-verifier paths alone is not sufficient if symmetrisation requires unavailable links.

Keep these concepts separate:

- Relay hops: network steps carrying a quantum distribution token.
- Verifier forwarding depth: successive recipients of Alice's revealed classical signature package.

Do not increment signature transfer level because a quantum path crosses additional relays.

Prefer all-required-recipient preflight for the first release. If partial delivery is introduced later, define its signed roster, success semantics, evidence allocation and certificate outcome explicitly rather than silently dropping unreachable recipients.

## 13. Session lifecycle and rerouting

1. Validate session roster and topology version.
2. Read current eligible-edge state and monitoring freshness.
3. Select and validate required distribution/symmetrisation routes.
4. Determine route-aware evidence budgets and policy.
5. If no acceptable plan exists, refuse before preparing tokens where possible.
6. Distribute and measure tokens with route-ordered channel effects.
7. Abort/reject affected sessions when observations or state changes require it.
8. Reveal and verify only under existing distribution-success and binding constraints.
9. Record route observations, state transitions and final outcomes.
10. A subsequent transmission plans again and can choose another path.

Do not promise transparent mid-session failover in the initial release. If an automated retry is offered, it must be a visible, bounded new session with fresh identifiers, commitments and evidence. Report the failed attempt as well as the successful retry.

## 14. API and failure behaviour

Expose enough information for the interface to explain the topology, active routes, edge state and refusal reasons. Exact endpoint and payload design remains independent implementation work.

HTTP 423 is the intended response when routing policy blocks a requested operation because no eligible required route remains. Distinguish configuration errors, unknown participants and malformed requests from this condition.

A blocked response should identify the affected operation/recipient, topology version and relevant blocking state without exposing private evidence or confidential token assignments.

Use existing authorisation boundaries for topology changes, manual quarantine and reset. Regular verifiers must not gain admin control or access other recipients' private evidence through new graph/history APIs.

## 15. Admin dashboard

Provide a graph showing signer, relays, verifiers and typed edges. Keep classical forwarding and quantum distribution visually distinguishable.

Required display:

- OPEN, WATCH, QUARANTINED and probation state with text labels as well as colour.
- Selected path per recipient and the topology version used.
- Latest edge observation summary, timestamp and reason for state.
- Clear separation between observed faults and injected experimental ground truth.
- Reroute event showing old path, new path and reason.
- Refused/unreachable recipient state when no acceptable route exists.
- Per-edge attempted/received/lost token or resource metrics where supported.

Historical sessions must show their own recorded routes, not redraw them using the current topology. A graph edge colour alone must not imply proven attack localisation.

## 16. Persistence, audit and migration

Persist stable topology/edge identities, relevant configuration versions, state transitions and supporting observation references. Record actual routes, policy decisions, fallback use and rerouting/refusal reasons with each session or linked event.

Signed records must bind the relevant route and outcome information. Preserve the distinction between the QDS evidence and the computationally signed audit artifact.

Do not silently rewrite signed history after an edge changes state. New transitions and reroutes produce new auditable events.

The existing store contains pooled logical-link state. Define a migration strategy that does not invent per-edge observations or silently clear an active quarantine. Preserve legacy records and label their original isolation scope.

After restart, retain appropriate edge restrictions and audit history. Existing transient quantum evidence must not be reconstructed from audit summaries for fresh verification. Define evidence-age handling for restored monitoring state.

Certificate/schema changes must preserve validation of old artifacts under their original formats.

## 17. Likely affected areas

These are inspection targets, not mandatory file edits.

| Area | Likely modules | Responsibility |
| --- | --- | --- |
| Topology and path selection | `router.py`, new configuration resources as needed | Graph validation, eligible paths and actual-route tracking |
| Enforcement | `enforcement.py`, `circuit_breaker.py` if used, `policy.py` | Edge scope, global-stop removal, recovery and legacy migration |
| Distribution | `protocol.py`, `transcript.py`, symmetrisation modules | Route-aware lifecycle and evidence ownership |
| Quantum/channel simulation | `teleportation.py`, `channel.py` | Ordered multi-hop effects and resource accounting |
| Statistical assessment | `detection.py`, `security.py`, `thresholds.py` | Edge/path observation scope and route-aware baselines |
| Scenarios | `threats.py`, experiment tools | Middle-edge injection isolated from detector inputs |
| Persistence/certificates | `store.py`, `audit.py`, `qcert.py` | Topology references, transitions and compatible signed history |
| API/access | `server.py`, authentication modules | Safe requests, refusal reasons and admin actions |
| Interface | `templates/admin.html`, admin JavaScript/styles | Graph, routes, state and history |
| Validation/docs | Tests, experiments and README | Regression, statistical evidence and limitations |

Inspect the active enforcement call path rather than assuming a file named `circuit_breaker.py` owns the operational guard. The reviewed global refusal resides in `enforcement.py`.

## 18. Work packages and exit conditions

### Phase 1 — Baseline and design gates

Review the latest branch, establish existing checks and resolve configuration, monitoring, trust and routing-policy choices.

Exit: a coherent observation model and approved behaviour; no implied edge attribution from pooled evidence.

### Phase 2 — Graph and eligible routing

Introduce validated configuration and deterministic route planning. Use manually controlled edge states to test routing separately from attack detection.

Exit: alternative-path and no-path outcomes work with no quantum-security claim attached to manual injection.

### Phase 3 — Multi-hop distribution

Integrate actual route effects, loss/resource accounting, route-aware evidence planning and symmetrisation requirements.

Exit: noiseless equivalence, ordered noise behaviour and session boundaries validated.

### Phase 4 — Evidence-based isolation

Introduce independent edge observations and scoped state transitions. Replace unconditional global refusal with explicit applicable-scope checks.

Exit: the attacked middle-edge demonstration isolates only what its evidence supports; unaffected eligible operations continue.

### Phase 5 — Audit and interface

Complete persistence, migration, certificates, graph display and refusal/reroute explanations.

Exit: displayed paths and edge transitions trace to durable records with proper access restrictions.

### Phase 6 — Evaluation and release

Measure honest and attacked operation across path lengths, recipient counts and channel conditions. Set supported graph/path limits from results.

Exit: acceptance criteria pass and remaining simulation/trust limitations are documented.

## 19. Validation matrix

| Scenario | Expected result |
| --- | --- |
| Original two-verifier star | Existing workflows remain available under documented compatibility rules |
| Noiseless multi-hop route | Correct final-state/measurement behaviour under the chosen model |
| Noisy/lossy route | Effects follow ordered path composition; loss is not counted as a contradiction |
| Primary middle edge quarantined | Next session avoids that edge and selects an eligible alternative |
| Unrelated edge quarantined | Unaffected eligible sessions are not globally refused |
| All routes blocked | HTTP 423 with a clear reason; no hidden bypass |
| Only WATCH route remains | Explicit configured fallback or refusal; never an accidental choice |
| End-to-end alarm without edge evidence | No unsupported unique-edge attribution |
| Changed injector label, identical observations | Detector/enforcement decisions do not change merely because ground truth changes |
| Shared edge fault | All dependent routes are treated consistently |
| Mid-session state change | Safe abort/stop behaviour; no reuse of invalid partial evidence |
| Quarantined edge reset | Monitored probation; unrelated states retained |
| Restart/migration | Restrictions and history preserved without fabricating quantum evidence |
| N-recipient session | All required connectivity, including symmetrisation, is checked |
| Classical forwarding attack | Correct integrity response without inventing a quantum-edge fault |
| Historical certificate | Original routes/outcomes remain verifiable and immutable |

Evaluate channel-test false alarms, attack detection/localisation rates, uncertain localisation, honest acceptance/inconclusive rates, reroute success and refusal rates. Report monitoring overhead separately from signature-distribution resources.

Measure latency, token/Bell-resource use, path length, recipient count, graph size and history growth. State experiment counts, assumptions and uncertainty. Do not promise numeric performance or security targets before validating the selected model.

## 20. Completion criteria

- [ ] Configurable versioned topology is validated before activation.
- [ ] Quantum and classical paths have explicit semantics.
- [ ] Actual selected paths influence simulated outcomes and resource accounting.
- [ ] Route-aware evidence planning preserves declared statistical assumptions.
- [ ] Edge isolation is supported by edge-scope observations or honestly labelled manual action.
- [ ] Attack ground truth never determines detector localisation.
- [ ] A quarantined edge does not trigger unconditional global shutdown.
- [ ] All affected operations enforce quarantine consistently, including legacy paths.
- [ ] WATCH/probation eligibility follows an explicit policy.
- [ ] Next-session rerouting works and no-route refusal is explained.
- [ ] Distribution, reserve, replay and symmetrisation constraints remain valid.
- [ ] Relay-hop count remains distinct from verifier forwarding depth.
- [ ] Audit history and certificates bind actual paths and preserve compatibility.
- [ ] Dashboard explains routing and evidence without overstating localisation.
- [ ] Recovery, restart and legacy-state migration are tested.
- [ ] Supported limits and trust assumptions are documented.

## 21. Handoff direction

Implement the behaviour independently in reviewable increments. Keep routing resilience, attack localisation and multi-hop quantum fidelity as separate validation obligations: success in one does not establish the others.

The feature is complete when a supported, evidence-based edge quarantine leaves safe alternative delivery usable, with accurate quantum outcomes, preserved verification constraints and an auditable explanation of the decision.
