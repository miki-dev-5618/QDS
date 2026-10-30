# QDS: Optional N-Verifier Extension — Implementation Plan

Date: 29 October 2026  
Status: Planning only; no implementation authorised by this document  
Repository: https://github.com/miki-dev-5618/QDS/tree/verif-eff  
Reviewed baseline: `78d39603920a2f25ded0aa653a4a4b4fa5689e9d`

## 1. Purpose

Extend the existing Alice–Bob–Charlie simulation so one signer can serve a configurable group of pre-enrolled verifiers. Preserve the two-verifier demonstration as the default.

The feature addresses recipient scalability: more participants can independently authenticate the same signed message, including through a bounded forwarding workflow. It does not inherently improve detection, security, throughput or public accessibility.

This is an optional extension. It should not displace the project's main objective: quantum-inspired threat detection for teleportation-based QDS without AI or machine learning.

## 2. Deliverable boundary

This document specifies intended behaviour, constraints, work packages and acceptance criteria. It contains no implementation code, patches, class designs or prescribed algorithms. The developer independently selects the internal architecture, interfaces and implementation method after resolving the decision gates below.

Do not treat proposed defaults as decisions already approved in discussion. No repository mutation, deployment or feature activation is requested by this planning document.

## 3. Goals and non-goals

| Goal | Observable outcome |
| --- | --- |
| Configurable recipient group | A session can include more than Bob and Charlie without separate protocol implementations for each participant. |
| Independent verification | Each recipient checks against its own previously distributed evidence. |
| Bounded transfer | An unchanged signed package can travel through an allowed chain with explicit depth and history. |
| Generalised attack demonstration | A selected dishonest verifier can modify a package and send it to the next honest recipient. |
| Complete visibility | Admin can inspect every recipient and verification event, including missing or inconclusive results. |
| Durable accountability | SQLite history and Q-Cert evidence preserve identities, decisions and transfer relationships. |
| Honest reporting | Applied rules, achieved statistical risks and unsupported security claims remain distinguishable. |
| Backward compatibility | The normal two-verifier workflow remains available and recognisable. |

Not goals:

- Universal public verification comparable to RSA or ECC.
- Multiple signers, joint approval, voting, consensus or threshold signatures.
- Automatic increases in security from adding participants.
- Production quantum networking or physical routing.
- Proven security against arbitrary collusion.
- Dynamic enrolment into a session after its evidence distribution.
- An implementation or proof of an entire published multiparty QDS protocol unless separately selected and scoped.

## 4. Practical use case

Use a hypothetical headquarters-and-regional-offices workflow for the demonstration. Alice issues an instruction; several known offices independently verify it before acting. A forwarding workflow demonstrates an instruction passing between offices without altering Alice's signed content.

These examples motivate additional recipients. They do not establish that QDS is preferable to conventional or post-quantum signatures for those organisations.

A useful demonstration must show why recipients need independent verification. Merely displaying more verifier cards is insufficient.

## 5. Existing baseline and constraints

The earlier code review found:

- Alice prepares states for Bob and Charlie, followed by random keep-or-forward symmetrisation.
- Verifiers use distribution records, message/context commitments, freshness checks and orthogonal elimination evidence.
- The default policy uses exact finite-sample rules, including inconclusive outcomes and bounded reserve evidence distributed before reveal.
- Legacy direct and forwarded rates remain available.
- Routing models a signer link and a Bob-to-Charlie transfer link.
- Forwarding records the immediate sender rather than a complete chain.
- SQLite preserves replay nonces, link transitions and signed audit artifacts. Distribution evidence and signer sessions are transient.
- Several protocol, transcript, threat, presentation and audit paths explicitly name Bob and Charlie.

This baseline is a source review, not a claim that runtime checks passed. Before implementation, confirm the current branch against the pinned commit and account for intervening changes.

## 6. Scope and decision register

| Topic | Planning position | Status |
| --- | --- | --- |
| Product role | Optional recipient-scaling extension; retain the core threat-detection focus | Established discussion direction |
| Membership | Closed network with evidence distributed before verification | Existing design constraint |
| Default group | Alice plus Bob and Charlie | Preserve existing behaviour |
| Initial supported range | Two to ten verifiers | Proposed engineering limit; validate performance |
| Delivery modes | Direct-to-all and one linear forwarding chain | Proposed first-release scope |
| Dishonesty | One dishonest verifier per scenario | Proposed initial threat model |
| Collusion | Explicitly unsupported security claim in first release | Proposed boundary |
| Stop condition | Stop normal forwarding on rejection or inconclusive verification | Proposed; malicious forwarding remains a separate action |
| Additional terminals | Extra verifiers visible in admin only; Bob/Charlie pages remain recognisable | Original feature specification |
| Default statistics | Preserve exact finite-sample policy | Recommended; needs a level-aware design |
| Rate formula | Experimental legacy comparison only until justified | Recommended limitation |
| Membership changes | Apply to future sessions only | Required for coherent evidence ownership |

Decision gate before protocol implementation: confirm delivery modes, maximum N and depth, dishonesty assumptions, symmetrisation model and statistical policy. UI sketches and baseline review can proceed before these choices; security-sensitive behaviour cannot be finalised without them.

## 7. Session and participant behaviour

### 7.1 Configuration

Each session has one signer, a fixed ordered roster of unique verifier identities, a delivery mode, an allowed route or chain, a maximum depth and a fixed policy version.

Reject invalid configurations before preparing evidence. Examples include duplicate identities, unknown recipients, routes containing non-members, unsupported depth and a dishonest-forwarder scenario with no downstream recipient.

Configuration changes must not reinterpret active sessions or historical records. Verifier identities must remain stable even if display labels change.

### 7.2 Evidence distribution

Every participant that may verify the session must receive its evidence before signature reveal. A participant appearing late in a forwarding chain still needs initial distribution evidence.

Do not let new recipients verify an old session simply because they receive the classical package or an audit certificate.

Main and reserve evidence must follow a consistent generalised distribution model. Preserve pre-reveal commitments and bounded reserve opening. Do not generate fresh verification evidence after reveal to improve a failed result.

### 7.3 Direct delivery

Alice reveals the package to all configured recipients after successful distribution. Each independently verifies it. Preserve individual outcomes even when the group summary is unsuccessful.

For an all-recipient workflow, report overall success only when every required recipient accepted. Distinguish rejected, inconclusive and incomplete sessions; do not introduce majority approval implicitly.

### 7.4 Forwarding

For the proposed chain mode, Alice reveals to the first recipient. A recipient that accepts may forward the unchanged package to the next permitted participant.

Forwarding is classical package transfer, not another round of quantum evidence creation. Every downstream participant checks against its own initial evidence.

The first recipient uses depth 0. Every subsequent transfer increases depth by one. N is recipient count; H is maximum forwarding depth. They are separate settings. A chain visiting N distinct recipients requires N − 1 forwards.

Normal forwarding stops on rejection or inconclusive verification under the proposed default. Remaining participants become `not reached`, not rejected. Explicit malicious actions may attempt forwarding despite a failed local result.

## 8. Symmetrisation design gate

The two-party rule cannot be extended simply by replacing names in a loop: with more than two recipients, the destination of a forwarded token must be defined.

Two candidate models discussed:

| Candidate | Behaviour | Limitation |
| --- | --- | --- |
| Uniform final holder | Each initially prepared copy is assigned privately and uniformly across the N recipients | Reproduces current two-recipient holder probabilities, but is not itself a multiparty security proof |
| Half keep / half forward | Keep with probability one-half; otherwise choose another recipient | For N greater than two, final destinations are not uniform across all recipients |

Select and document one model before implementing distribution. State whether transfers model quantum copies or measurement records; do not silently change the existing simulation's semantics.

Required invariants:

- No accidental duplication or disappearance of tokens during assignment.
- Every retained item has unambiguous source, signature position and final holder.
- Alice does not obtain recipients' private assignment decisions through the simulated signer interface.
- Each verifier evaluates only evidence assigned to it.
- Main and reserve assignment use the declared policy.
- N = 2 has an explicit compatibility expectation; do not demand identical random traces unless intentional.

Recommended resource model: prepare one initial copy per recipient per signature position. This increases distribution cost with N but avoids dividing the existing two-copy budget among a larger group. The developer must validate and document this choice rather than assume unchanged evidence quality.

## 9. Verification policy and security reporting

### 9.1 Preserve the current default

The branch's exact policy distinguishes direct and forwarded verification; it does not yet express a sequence of forwarding levels. A new rate formula alone will not extend that default policy.

The developer must define how depth affects exact acceptance limits, inconclusive bands, reserve use and achieved risks. Each event must record the rule actually applied to its observed evidence count.

Integer limits may coincide at short sample sizes. Do not invent distinct thresholds merely to display a different number at each depth. If the intended margins cannot be supported, report that limitation, restrict depth or require more evidence.

### 9.2 Experimental legacy schedule

The original feature proposes, for depth l from 0 through H:

`s_l = mu_h + (l + 1) * (p_min - mu_h) / (H + 2)`

Here `mu_h` is the assumed honest mismatch rate and `p_min` is the model's assumed minimum forger mismatch rate. H = 1 reproduces the existing legacy direct and forwarded rates.

Treat this as an experimental schedule requiring justification. Do not present it as an established multiparty result or silently apply legacy bounds to the exact policy.

The gap between adjacent levels shrinks with H. Any minimum-length claim must state its derivation, assumptions, sample-count unit, loss treatment and achieved target. No numerical minimum is fixed by this document.

### 9.3 Trust and risk boundaries

- Define the number of dishonest participants supported and what information they can access.
- Reassess whether the existing forger mismatch assumption still applies when recipients gain different evidence or collude.
- Separate per-verifier risk from an entire session's risk. Any aggregate bound must state how it is obtained and which events it covers.
- Do not interpret agreement among more recipients as independent corroboration without checking dependence.
- Distinguish package rejection from attribution of blame. A statistical failure alone does not prove which participant caused it.
- Keep detector inputs limited to observations; scenario ground truth must remain separate.
- Label results below target and inconclusive evidence honestly.
- Keep simulator evidence, computational commitments and Q-Cert signing separate from claims about information-theoretic QDS security.

Published multiparty QDS research is a reference for the analysis, not a security proof for this codebase: https://arxiv.org/abs/1505.07509. Selection and verification of a specific compatible protocol is a separate research task if stronger claims are required.

## 10. Forwarding integrity, replay and reserve rules

Maintain a verifiable relationship between each transfer and its parent event. A user-controlled depth field must not grant a more permissive rule.

Record the immediate sender, intended recipient, session, parent event, depth and policy. Define how sender identity and allowed transitions are authenticated within the simulation. Detect attempts to skip depth, substitute a parent, exceed H, use an unknown sender or form a loop.

Preserve Alice's original signed context across forwards. Forwarding metadata must not rewrite signer identity, original recipient roster or signed message semantics.

Specify duplicate-delivery handling across different routes or senders. Repeated deliveries must not create unlimited fresh verification attempts, consume additional evidence beyond policy or overwrite earlier outcomes.

Reserve use must remain bounded per session and verifier under an explicit rule across delivery modes and senders. Forwarded borderline results need a defined reserve-opening path; the existing direct-delivery mechanism must not simply be assumed to cover them.

If Alice is unavailable to open reserve evidence, report the resulting limitation or inconclusive outcome. Do not fabricate an opening.

## 11. Attack scenarios and expected behaviour

| Scenario | Required observable behaviour |
| --- | --- |
| Honest direct delivery | Every recipient produces its own decision and evidence summary |
| Honest chain | Each reached recipient verifies the unchanged package at the validated depth |
| Verifier changes message | Next honest receiver rejects a digest or commitment inconsistency |
| Verifier changes signature | Next honest receiver rejects a commitment inconsistency; show statistical outcome separately |
| Replay through another sender | Duplicate policy prevents the route from granting unbounded new attempts |
| Unknown participant | Membership or sender validation rejects the attempt |
| Manipulated depth or route | Invalid transition is refused before obtaining a more permissive rule |
| Insufficient evidence or loss | Report insufficient or inconclusive evidence without claiming certain attacker detection |
| Dishonest signer | Exercise asymmetric preparation under the selected N-party distribution model; report observations without overstating attribution |
| Distribution abort | Do not release the signature to recipients; mark verification unavailable |
| Forwarder refuses to send | Mark downstream participants not reached; do not mislabel this as signature forgery |

“Caught at the next level” means the next reached honest verifier rejects an altered package under applicable integrity checks. It is not a promise that every alteration triggers statistical rejection, that colluders expose each other, or that withholding is detected as forgery.

## 12. Dashboard and user flow

Retain the existing Bob and Charlie terminals. Additional recipients appear in the admin view for the initial release.

Admin controls should expose participant count/roster, delivery mode, allowed chain, maximum depth, scenario and selected dishonest forwarder. Show unsupported combinations as configuration errors.

Provide a compact latest-session matrix with one row per participant and access to its event history. Suggested fields:

- Identity and role in the route.
- Received from and validated depth.
- Accepted, rejected, inconclusive, not reached or distribution aborted.
- Mismatches, checked copies and applied acceptance limit.
- Reserve requested/used and final decision stage.
- Rejection reason and achieved assurance status.

Separate distribution/symmetrisation from later package forwarding in topology and labels. Display actual simulated paths and link state. If several events concern one verifier, do not replace the earlier event with the latest result without retaining history.

The interface should explain recipient scalability plainly and avoid suggesting universal verification or multi-party approval.

## 13. Persistence and certificates

Preserve the existing audit chain. Record enough information to reconstruct the session roster, policy, route and sequence of verification events.

Each event needs a unique identity and associations with its session and parent transfer. Record observed evidence count, applied rule, outcome, reason, depth, reserve status and relevant risk estimates. Do not key events solely by verifier plus direct/forwarded mode: repeated events would collide.

Q-Cert must bind the configured participants and the complete relevant event set, including extra recipients. Clearly distinguish an initial session record from later forwarding records; use immutable linked records or another explicitly documented signing lifecycle. Never silently mutate an already signed artifact.

Choose an explicit schema/version migration strategy. Old certificates must remain verifiable under their original schema and trust rules.

Persist audit history without implying that consumed or transient quantum evidence can be recovered for new verification after restart. If the existing transient-evidence policy is retained, pending old sessions must fail clearly and require redistribution.

An independently verified Q-Cert signature establishes the audit artifact's authenticity under its signing scheme. It does not give an external reader the missing private evidence required to independently perform QDS verification.

## 14. Routing, access and enforcement

Generalise routes to configured participants. Define whether quarantine isolates a specific transfer edge, one verifier or a shared signer-distribution link. This choice must reflect the granularity of available observations.

Do not automatically quarantine all recipients because one forwarding edge fails. Conversely, do not claim per-edge channel attribution from a pooled channel test.

Keep extra recipients admin-only in the initial interface. Existing Bob and Charlie permissions must remain restricted to their own permitted data and actions. Ordinary verifier access must not expose other participants' private distribution evidence.

Treat privileged admin inspection as part of the simulation's trust boundary. Do not use its visibility to claim the same secrecy guarantees for an untrusted real-world operator.

## 15. Likely affected areas

These are review targets, not mandatory edit instructions. The developer decides the final file boundaries.

| Area | Likely files or modules | Responsibility |
| --- | --- | --- |
| Protocol orchestration | `protocol.py` | Roster, distribution, reveal, delivery and forwarding lifecycle |
| Evidence allocation | `symmetrisation.py`, `schedule.py`, `transcript.py` | N-recipient assignment and ownership |
| Verification and statistics | `verifier.py`, `security.py`, `thresholds.py` | Depth-aware rules, reserve and risk reporting |
| Package integrity | `binding.py`, `replay.py` | Context consistency and duplicate handling |
| Threat handling | `threats.py`, `detection.py`, `policy.py` | Generic attacker identity and observation-based outcomes |
| Routing/enforcement | `router.py`, `enforcement.py` | Dynamic paths and correctly scoped isolation |
| Durable history | `store.py`, `audit.py`, `qcert.py` | Event persistence, certificate lifecycle and compatibility |
| Server/access | `server.py`, `auth.py` | Validation, role-filtered views and publication |
| Interface | Admin template/JavaScript and shared verifier presentation | Controls, matrix, topology and historical detail |
| Validation/docs | Tests, experiments and README | Regression, scaling evidence and honest limitations |

## 16. Implementation work packages

### Phase 1 — Baseline and decisions

Confirm the branch state, run existing relevant checks and map hard-coded two-verifier assumptions. Resolve the decision register and define the supported threat model.

Exit: approved behavioural specification with explicit N, H, delivery, assignment and statistical policies.

### Phase 2 — Generalised distribution

Enable a session roster and correct private evidence assignment for main and reserve evidence. Preserve all existing binding and abort constraints.

Exit: token conservation, ownership, membership and N = 2 compatibility demonstrated.

### Phase 3 — Verification and transfer lifecycle

Add validated forwarding history, bounded depth, duplicate rules, reserve handling and level-aware decisions. Maintain separate per-event and session outcomes.

Exit: honest direct delivery and chains work for supported configurations; invalid routes and repeated attempts obey policy.

### Phase 4 — Attacks and enforcement

Generalise the dishonest-forwarder scenario and assess other existing threats under N recipients. Ensure observation-only detection and correctly scoped enforcement.

Exit: attack rejection and its actual cause are visible; ground truth is not used to determine outcomes.

### Phase 5 — Records and interface

Complete persistent event history, compatible certificates, admin controls and recipient matrix. Retain existing terminal access boundaries.

Exit: every displayed result can be traced to durable event evidence and the appropriate signed record.

### Phase 6 — Evaluation and release decision

Measure supported configurations, validate regression behaviour, document assumptions and set defensible operational limits.

Exit: acceptance criteria pass; unsupported guarantees and remaining limitations are documented before enabling the extension by default or exposing broader configurations.

## 17. Validation and evaluation

Use targeted unit, integration and statistical evaluation appropriate to protocol changes. Select exact test cases independently; the outcomes below are required.

### Functional and compatibility checks

- Existing two-recipient workflows and supported old certificates remain usable.
- Representative N = 2, 3, 5 and 10 sessions behave correctly within the chosen support limit.
- Every token has valid ownership; no evidence is duplicated during reassignment.
- Direct and forwarded verification use the declared policy and correct observed sample size.
- Invalid membership, loops, depth manipulation and duplicate attempts are handled explicitly.
- Reserve limits remain effective across senders and delivery modes.
- Loss, early abort, inconclusive evidence and restart behaviour are represented correctly.
- Extra-recipient results appear in both history and certificates without overwriting earlier events.
- Bob/Charlie access remains isolated from other recipients' private evidence.

### Statistical and performance evaluation

Vary N, H, signature length and channel conditions separately. Record:

| Metric | Purpose |
| --- | --- |
| Honest acceptance / rejection / inconclusive rate | Assess usability and evidence adequacy |
| Attack acceptance and rejection cause | Separate binding protection from elimination detection |
| Achieved per-event and session-level risk statements | Prevent misleading aggregate assurance |
| Planned/sent/received tokens and reserve use | Quantify resource cost |
| Distribution, verification and total chain latency | Identify scaling bottlenecks |
| Memory and history/certificate growth | Establish practical limits |
| Symmetrisation holder counts | Check assignment behaviour and uneven evidence |

Report trial counts, seeds where reproducible, uncertainty and model assumptions. Zero accepted attacks in a finite experiment is not proof of zero forgery probability. Do not fix numerical performance promises before measuring the implementation.

## 18. Completion criteria

- [ ] The extension demonstrably serves additional independent, pre-enrolled recipients.
- [ ] The default remains the existing two-verifier workflow unless explicitly changed later.
- [ ] Session roster, maximum depth and policy are fixed and auditable.
- [ ] Main and reserve distribution obey the chosen assignment model and conservation rules.
- [ ] Forwarding cannot obtain extra permissions by inventing depth, sender or parent history.
- [ ] Each reached verifier uses its own evidence and reports the applied rule.
- [ ] Rejected, inconclusive, not reached and aborted outcomes remain distinct.
- [ ] Duplicate deliveries and reserve openings are bounded across routes.
- [ ] A selected dishonest forwarder can be demonstrated without leaking attack labels into detection.
- [ ] Admin can inspect all recipients while existing verifier access boundaries remain intact.
- [ ] Persistent records and Q-Cert include all relevant events and preserve old-artifact compatibility.
- [ ] Resource and statistical evaluation supports the advertised N/H limits.
- [ ] Documentation makes no automatic-security, universal-verification or unsupported-collusion claims.

## 19. Handoff to the implementer

Use this plan as a behavioural contract, not a prescribed code structure. Inspect the current repository, resolve the open choices, choose the internal design independently and implement in reviewable increments.

The key release question is whether the extension provides a useful multi-recipient workflow while preserving the existing threat-detection behaviour and honest security reporting. Increasing the number of visible verifier nodes alone does not satisfy that objective.
