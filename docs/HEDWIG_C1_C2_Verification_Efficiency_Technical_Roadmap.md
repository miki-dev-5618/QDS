# HEDWIG — Verification Reliability and Efficiency Enhancement Roadmap

**Project:** Quantum-Inspired Cyber Threat Detection for Digital Signature Security (SIH26141)  
**System:** HEDWIG, Team Athena's simulated teleportation-based Quantum Digital Signature (QDS) framework  
**Focus:** C1 — Exact binomial verification thresholds; C2 — Adaptive token allocation and borderline-result handling  
**Review basis:** `miki-dev-5618/QDS`, `main` at commit `0f6afcd` (21 October 2026); supplied SIH26141 problem statement and project goal; C1/C2 task assignments  
**Document purpose:** Define the engineering questions, proposed technical approach, integration considerations, and evidence of success—**not** a prescriptive implementation or source-code specification.

---

## 1. Project Context and Intended Outcome

The project is a software framework for studying and detecting threats to teleportation-based quantum digital signatures without using machine learning. Its intended mechanism combines simulated Bell-state entanglement and quantum teleportation, Pauli operations, projective measurement, quantum-state elimination, statistical decisions, and contextual checks against forgery, impersonation, replay, and channel manipulation.

HEDWIG already implements much of the end-to-end simulation: Alice distributes prepared states, Bob and Charlie build elimination evidence, the system checks a committed classical payload, and a two-tier detector decides whether observed failures are consistent with channel disturbance, signature inconsistency, or another event. A response layer can watch or quarantine links, and audit records preserve evidence.

The **next engineering challenge** is not adding more detection labels. It is strengthening the *decision-making quality* of the existing verification pipeline—particularly when the signature is short, the channel is noisy, or the available evidence is borderline—while using additional simulated quantum resources only when justified.

The desired end state is a verification system that:

- Makes acceptance and rejection decisions using statistical reasoning appropriate to the actual evidence available.
- Quantifies the trade-off between rejecting genuine signatures and accepting forged ones.
- Adapts its evidence budget to signature length, channel state, observed uncertainty, and the risk being evaluated.
- Treats ambiguous observations explicitly instead of silently making either an unsafe acceptance or an overconfident attack accusation.
- Preserves the sign/reveal/verify chronology, verifier independence, and commitments binding the message to its signature context.
- Reports measurable security and efficiency improvements under controlled tests, without claiming guarantees stronger than the model supports.

The SIH objective is an **executable, verifiable prototype** accompanied by a mathematical model, threat simulations, and performance evidence. Both C1 and C2 must therefore work within the full system rather than as isolated formulas.

---

## 2. Current Baseline: What Exists and What Is Missing

The current `main` branch was reviewed for architecture and relevant verification behavior. This is a **code-level assessment**, not a claim that all tests have been executed against the latest commit.

| Area | Current behavior | Enhancement needed |
|---|---|---|
| Signature acceptance | Uses separate direct (`s_a`) and forwarded (`s_v`) mismatch limits derived from the assumed honest/forger gap | Evaluate whether exact finite-sample probabilities support better acceptance policies at small sample counts |
| Security estimates | Displays Hoeffding-style bounds for false rejection, forgery acceptance, and repudiation | Distinguish an exact probability within a specified model from a conservative bound or a broader security claim |
| Channel tests | Already use binomial-tail calculations for test-token errors | Reuse compatible statistical concepts, but carefully distinguish channel QBER tests from signature-elimination checks |
| Token budgeting | Allocates a base number of test tokens and doubles it in WATCH/probation states | Make the allocation responsive to sample length, required power, observed uncertainty, and resource cost |
| Borderline evidence | Primarily produces a pass/fail result from the available sample | Define a secure, bounded route to collecting more evidence *where the protocol permits it* |
| Two-tier detection | Uses test-token and elimination evidence to identify disturbance patterns and may abstain from attribution | Ensure new verification logic does not inadvertently distort the detector's evidence interpretation |
| Response enforcement | Can watch, quarantine, and manage recovery | Keep uncertain results distinct from genuinely strong evidence of malicious activity |
| Evaluation | Earlier seeded experiments report performance at L=16, 32, and 64 | Re-run comparable experiments after changes, including recent noise/loss behavior |

**Important distinction:** The code already performs an **exact binomial channel-error test**. C1 is specifically about improving the **signature acceptance/rejection threshold** and its security accounting; it is not about introducing binomial mathematics for the first time.

### Why L=16 deserves priority

The previously generated experiment report (`experiments/results.md`, dated 28 September 2026) reported false rejection for some honest L=16 runs, while longer signatures were more stable under that particular simulated channel and experimental setup. These are historical results, not guaranteed figures for the latest code. Short signatures produce fewer mismatch observations and therefore more discrete, less decisive evidence. A change of even one permissible mismatch may materially alter both honest acceptance and forgery resistance.

Do **not** assume that an exact statistical formula can remove the underlying shortage of evidence. Exactness improves *calibration*; additional independent evidence improves *statistical separation*.

---

## 3. Shared Statistical and Security Model

Both tasks should begin with a common statement of what an observation means and what assumptions make its probability calculations legitimate.

### 3.1 Keep three evidence types distinct

**Signature elimination evidence.** Each verifier measures its held quantum-state copies in its chosen bases and records the states ruled out by those outcomes. A contradiction occurs if a later revealed signature state equals an eliminated state. The relevant count is the number of **measured copies actually checked**, not automatically the signature length L. Symmetrisation, forwarding, early termination, and losses can change this count.

**Channel test evidence.** Separately prepared test tokens are used to estimate disturbance of the simulated quantum communication channel. Their errors measure a channel phenomenon, not directly whether the revealed signature belongs to Alice.

**Classical validity evidence.** Message digest, session identifier, authenticated distribution record, commitment, nonce, freshness, authorized verifier identity, and forwarded provenance determine whether a package is correctly bound to the claimed context. Statistical tolerance for quantum noise must **never** relax these checks.

A sound implementation treats these as complementary sources of evidence, not interchangeable quantities.

### 3.2 Specify the statistical hypotheses

For signature elimination, the existing model distinguishes an honest mismatch probability associated with the expected channel noise and a higher minimum mismatch probability for certain unauthorized strategies. The code currently uses the illustrative relationships `mu_h = e0/2`, `p_min = 1/6` for a dishonest verifier in a specified attack model, and a larger mismatch rate for simple external guessing.

For channel tests, the null hypothesis concerns the baseline channel error rate; alternative hypotheses concern elevated disturbance, such as intercept-resend behavior.

An **exact binomial** probability is exact only if the trial count and per-trial success probability describe the measurement process, ordinarily requiring independent, identically distributed Bernoulli observations under the specified hypothesis. Finite population effects, correlations introduced by allocation, burst noise, readout bias, adversarially selected losses, and coherent attacks may invalidate a naive binomial interpretation.

The project should make these assumptions visible. It should not present an exact probability *within a simplified model* as unconditional information-theoretic security.

### 3.3 Define success as a multi-objective problem

A verification change should be judged against at least four competing outcomes:

1. **Honest reliability:** genuine signatures are accepted when modeled channel behavior is within acceptable limits.
2. **Adversarial resistance:** the probability of accepting a forged or unauthorized signature remains within the chosen threat model's acceptable risk.
3. **Efficiency:** fewer unnecessary test tokens, fewer simulated circuit operations, and lower decision latency per useful verified transaction.
4. **Decision integrity:** uncertain evidence is reported honestly; early stopping and adaptation do not silently undermine statistical error control.

Optimizing only honest acceptance, only attack detection, or only runtime can make the overall system worse.

---

## 4. C1 — Exact Binomial Thresholds for Signature Verification

**Objective:** Improve the reliability and interpretability of direct and forwarded signature decisions, especially at small checked-copy counts, while preserving meaningful constraints on false acceptance.

### 4.1 Core technical idea

The current verifier compares the number of elimination contradictions with a fraction-based cutoff. Its security report then estimates risks using Hoeffding bounds. Hoeffding offers broadly useful conservative bounds, but at low sample sizes the bound may be loose and may convey little about the true probability of particular integer mismatch counts under the model.

An exact finite-sample approach instead assesses the **complete mismatch-count distribution** under a clearly stated honest model and under an explicitly stated attacker model. The acceptance rule is considered at the level of integer mismatch counts rather than only a continuous mismatch fraction.

Conceptually, for each candidate acceptance region, evaluate two questions:

- How often would an honest signature fall outside it?
- How often could a specified forgery strategy fall inside it?

The outcome is an evidence-based account of the trade-off, rather than an assumption that a more permissive limit must be better.

### 4.2 Important design decisions

**Direct versus forwarded verification.** Bob's direct acceptance and Charlie's transferred/forwarded acceptance serve different security purposes. A more permissive transfer rule can support signature transferability but may affect dishonest-verifier forgery risk and repudiation analysis. These modes must remain distinguishable, even if they share a statistical calculation engine.

**Observed sample size rather than nominal L.** Calculate decisions from the number of usable measured copies associated with the verifier's own trusted distribution evidence. Do not assume that every position contributes exactly one observation or that all planned copies survived.

**Discrete thresholds.** At small sample sizes, changing the permitted mismatch count by one can move false-rejection and forgery-acceptance probabilities substantially. Threshold selection must account for this discreteness.

**Explicit risk budget.** The team should choose how much honest failure risk and forgery-acceptance risk it will tolerate in the experiment and security model. If those goals cannot simultaneously be satisfied at a given sample size, the system should recognize insufficient evidence or require a larger signature rather than quietly lowering security.

**Model uncertainty.** Estimated baseline noise rates are not guaranteed ground truth. Conservative handling of uncertain or changing noise is preferable to tuning acceptance thresholds against a single optimistic calibration.

**Comparison with the existing method.** The current policy should remain a reproducible baseline. The enhanced policy may improve discrimination in some conditions and offer no improvement in others; both outcomes should be reported.

### 4.3 Intended operational behavior

For an incoming signed package, the verifier continues to perform its independent context, authorization, freshness, commitment, and elimination checks. The enhanced statistical layer interprets the elimination mismatch count using the count of available trusted observations and the relevant verification mode.

The resulting assessment should communicate more than a binary result. It should be possible to understand whether a rejection follows a decisive contradiction count, a classical integrity failure, a high-noise channel alarm, or a failure to meet the required statistical confidence. The decision rule and the associated probability statement should refer to the **same** evidence and threshold.

Where the evidence is inadequate to meet both security and reliability constraints, the preferred outcome is a transparent limitation—not a fabricated security guarantee.

### 4.4 What C1 must *not* imply

- Replacing a displayed Hoeffding estimate with an exact binomial estimate does **not**, by itself, change a verifier's acceptance behavior.
- Raising an acceptance threshold to make genuine traffic pass more often usually raises forgery acceptance risk as well.
- A low observed attack rate on a small test set does not establish a cryptographic security bound.
- Probabilities computed for independent single-copy events do not automatically prove security against coordinated, coherent, or adaptive adversaries.
- The probabilities for Bob and Charlie cannot necessarily be multiplied as though their observations were independent; the protocol must account for symmetrisation and shared events.

### 4.5 Expected C1 outcomes

The work is complete when the project can **explain, justify, apply, and empirically validate** its signature mismatch threshold at the actual sample size, for both direct and forwarded verification. Threshold reporting must be mathematically consistent with the decision the verifier actually makes. Demonstrations should include small-sample boundary cases, normal noise, hostile signature replacement, and comparisons with the original threshold policy.

---

## 5. C2 — Adaptive Evidence and Token Allocation

**Objective:** Use simulated quantum resources more intelligently so the system spends additional evidence where it improves verification or threat detection, without universally increasing cost.

### 5.1 Core technical idea

HEDWIG already doubles its test-token budget while a link is on WATCH or probation. This is a useful first response to suspicion, but it is not a complete allocation strategy. It does not determine *why* a particular allocation is adequate or whether a shorter signature requires more independent observations.

A stronger adaptive approach makes budget decisions from the **statistical purpose of each token** and from the system's current uncertainty. The allocation policy should distinguish the budget required for channel-disturbance detection from the evidence required for signature authenticity.

### 5.2 Two separate resources

**Channel test tokens:** Sacrificial probes used to estimate channel error behavior. More of them can increase detection power against a weak intercept-resend attack or narrow uncertainty about channel quality. They cannot directly replace the signature copies needed for authenticity checks.

**Signature copies/positions:** The actual elimination evidence available to Bob and Charlie. More usable signature evidence can provide stronger discrimination between honest and forged state reveals, but obtaining it changes the resource and distribution requirements of the signature protocol. It cannot be manufactured after the fact by repeatedly measuring a qubit already consumed.

The allocation policy should make its resource categories and costs explicit. An improvement in channel attack detection must not be described as an improvement in signature-forgery probability unless supported by the mechanism and measurements.

### 5.3 Inputs that may justify an adaptive decision

The team may consider combinations of:

- Nominal signature length and actual number of usable checked copies per verifier.
- Baseline channel noise and uncertainty in its calibration.
- Current channel-test evidence and its statistical power to detect relevant attacks.
- Recent link state (OPEN, WATCH, probation) and evidence of repeated anomalous behavior.
- Photon loss and whether the remaining observations are representative.
- Difference between observed mismatch count and a relevant decision boundary.
- Remaining resource budget, acceptable latency, and a maximum practical evidence cap.

The precise weighting of these factors is an implementation design choice. It should be transparent, measurable, and selected without consulting secret injected attack labels.

### 5.4 L-aware allocation

Small signatures often offer less elimination evidence. A length-aware policy can respond by budgeting enough relevant evidence to meet preselected detection or confidence goals. However, there are limits to what additional *test* tokens can achieve when the problem is too few *signature* copies.

The system should therefore distinguish three cases:

1. **Insufficient channel evidence:** additional pre-reveal test tokens could help assess channel disturbance.
2. **Insufficient signature evidence:** a longer signature or an additional properly committed distribution round may be needed; more channel probes alone do not solve the problem.
3. **Sufficient evidence:** avoid unnecessary overhead even if the signature is nominally short.

This makes adaptation purposeful rather than merely multiplying every budget below an arbitrary length.

### 5.5 Borderline verification: possible approaches and constraints

A borderline result is not necessarily an attack. It may reflect ordinary measurement noise, a short sample, ambiguous attribution, or a weak disturbance. The system should identify such cases before deciding whether to reject, observe the link more closely, or seek more evidence.

The crucial constraint is **protocol chronology**. HEDWIG has a distribution-and-channel-test stage followed by a reveal-and-verification stage. Any extra measurement evidence must be acquired through a legitimate protocol mechanism:

- Additional *channel probes* may be scheduled before signature reveal or within a carefully specified sequential channel-test process.
- Additional *signature evidence* would require fresh, appropriately prepared and committed quantum-state copies or a new protocol round. A previously measured quantum token cannot be tested again as though it were a new independent sample.
- A failed binding, impersonation, replay, or authorization check cannot be converted into a successful signature by acquiring more noisy quantum samples.
- A rejected signature must not simply be resubmitted until statistical noise makes it pass; that would be an insecure retry policy.

The team can decide whether to support an explicit **inconclusive / more evidence required** state, a bounded pre-reveal evidence-gathering stage, or a conservative reject-and-restart workflow. These choices should be evaluated against user experience, security, and simulated overhead.

### 5.6 Sequential testing and early stopping

Repeatedly inspecting intermediate results changes the statistical problem. A fixed-sample false-alarm threshold does not automatically remain valid when the system checks after many intermediate blocks and stops whenever a threshold is crossed.

HEDWIG already includes sequential early abort for strong channel evidence. C2 should preserve that efficiency goal while accounting for how repeated checks affect the overall false-alarm rate. The statistical interpretation must reflect the stopping process, not simply the final observed count as though the sample size had been fixed in advance.

Useful conceptual options include prespecified staged testing, controlled sequential risk budgets, or valid sequential evidence measures. Selecting among them should remain an engineering/research decision driven by the project's requirements and evaluation results.

### 5.7 Resource-aware behavior

Adaptive allocation should be bounded. Every strategy should expose the potential cost of additional tokens, simulated circuits, latency, and repeated distribution attempts. The project should measure both:

- **Total overhead:** what adaptation costs during honest routine operation and under attack.
- **Useful savings:** unnecessary probes avoided on clean links, earlier attacks rejected, or ambiguous cases resolved without restarting unnecessarily.

An adaptive strategy that improves detection only by doubling all token usage is not an efficiency improvement unless its security benefit justifies that additional cost.

### 5.8 Expected C2 outcomes

The work is complete when the system selects resource usage based on a stated rationale, reacts sensibly to genuinely uncertain conditions, obeys the protocol's chronology, and reports the cost/benefit against fixed and WATCH-doubling baselines. It must show that any borderline retry is bounded, meaningful, and safe against adversarial repeated attempts.

---

## 6. C1 and C2 Must Be Designed Together

C1 defines **what sufficient evidence means** under the project's statistical and security assumptions. C2 determines **how to obtain that evidence efficiently**. They should not be treated as unrelated features.

A coherent high-level workflow is:

1. Define the protection goals and the direct/forwarded verification modes.
2. Determine the amount and type of evidence already available under the current channel and signature conditions.
3. Estimate whether that evidence is sufficient for the intended decision quality.
4. Where the protocol permits, plan additional channel probes or signature distribution evidence **before** committing to a final decision.
5. Carry out the normal distribution, commitment, channel testing, reveal, and independent-verification phases.
6. Evaluate observed evidence using the agreed finite-sample model and security policy.
7. Preserve a clear distinction among accepted, rejected, and insufficiently supported outcomes.
8. Provide downstream detection, enforcement, and audit layers with the relevant evidence and uncertainty information.

This is a conceptual workflow, not a mandated set of software functions. Different architectures are acceptable if they preserve the same trust and statistical properties.

### A subtle challenge: allocating based on borderline results

Some relevant information exists only **after** signature reveal, whereas some additional quantum samples must be prepared and distributed **before** reveal. A truly adaptive design must resolve this timing constraint. Options include a precommitted reserve of additional measurement resources, staged authenticated distribution, or a fresh signature session. A simple post-verification retry cannot be assumed valid.

---

## 7. Integration with the Existing HEDWIG System

Enhancements should be consistent with existing modules and their responsibilities, without locking implementers into a particular code layout.

### Verification and statistical layer

The acceptance policy belongs conceptually alongside `security.py` and `verifier.py`. The channel-test math in `channel.py` offers a relevant reference point, but the two statistical questions remain separate. Reporting should expose the assumptions, measured sample size, selected decision boundary, and the meaning of calculated risk estimates.

### Protocol and scheduling layer

Adaptive evidence allocation belongs conceptually in the distribution workflow currently coordinated by `protocol.py`. Basis selection and token ordering are important because verifier-private randomness, symmetrisation, and the separation of test tokens from signature tokens underpin the model. The resulting strategy should not leak test-token positions or private measurement information to the adversary.

### Detection and attribution layer

`detection.py` and `discriminator.py` already combine channel and signature evidence. Revised thresholds and changing test budgets may affect how often failures reach Tier 2 and how confidently they can be attributed. These effects should be measured rather than assumed harmless. The detector must remain blind to the attack scenario injected by the test harness.

### Response-policy layer

`policy.py` and `enforcement.py` should continue separating **the disposition of the current signature** from **the disposition of future traffic on the channel**. An uncertain or statistically weak observation should not automatically become an aggressive channel quarantine. Conversely, a decisive classical integrity failure must not be excused as quantum noise.

### Loss and realistic-noise models

Recent code includes photon erasure, readout imperfections, amplitude damping, and IBM-like simulated noise. The enhanced statistics must be tested with these conditions. In particular, selective loss or basis-dependent losses can undermine assumptions that surviving evidence is an unbiased sample. A minimum survivor count alone does not prove that an adversary has not manipulated the sample.

### User interface and auditability

The dashboards and audit records should allow a judge or developer to understand *why* a decision occurred. Helpful categories include sample sufficiency, actual/nominal evidence counts, reliability/forgery trade-offs, channel test power, reason for increased token allocation, time/resource overhead, and the stage at which a run stopped. The UI should not label conditional model estimates as unconditional security proofs.

---

## 8. Validation Strategy and Evidence of Completion

Feature completion means that the full project behaves correctly under controlled experiments—not merely that a statistical helper returns a number.

### 8.1 Establish comparable baselines

Evaluate the existing behavior, C1 alone, C2 alone, and the combined C1+C2 approach where feasible. Keep the testing environment, randomization strategy, threat intensity, and resource accounting comparable. This isolates whether an apparent gain comes from better decision logic, additional evidence, or a changed simulator condition.

Historical experiment files are useful reference points, but their results must not be silently reused as evidence for revised code. Regenerate results using the version under evaluation.

### 8.2 Scenario coverage

| Scenario family | Main question |
|---|---|
| Honest ideal channel | Can valid signatures be verified without unnecessary work? |
| Honest channel near the assumed noise limit | Are legitimate users rejected or escalated too often? |
| Short, medium, and longer signatures | How does decision quality scale with actual evidence count? |
| External signature forgery | Does a more generous acceptance threshold weaken forgery resistance? |
| Dishonest forwarding | Are forwarded-verifier protections preserved? |
| Repudiation-like inconsistent distribution | Are disagreement and attribution handled honestly? |
| Intercept-resend and weak channel tampering | Do additional test tokens increase detection power enough to justify cost? |
| Message alteration, replay, impersonation, unauthorized verification | Are classical validity checks still decisive and independent of noise tolerance? |
| Burst noise, readout error, damping | Where do simple binomial assumptions fail or become inaccurate? |
| Photon loss and selective erasure | Does reduced or biased evidence cause unsafe acceptance? |
| Repeated borderline attempts | Can an attacker exploit retry or repeated-testing behavior? |
| WATCH, quarantine, and probation sequences | Does adaptation create false lockouts or uncontrolled resource consumption? |

### 8.3 Core metrics

**Verification quality**

- Honest-signature acceptance and false-rejection rates.
- Forgery-acceptance rate and attack-detection rate, disaggregated by attack type.
- Direct and forwarded verifier decisions, including disagreements.
- Frequency of inconclusive outcomes and false threat attribution.

**Statistical credibility**

- Match between predicted probability and observed frequency under the conditions where the statistical model applies.
- Coverage of uncertainty intervals and sensitivity to baseline-noise calibration.
- Whether error control still holds under staged/sequential observation and repeated sessions.
- Validity boundaries under correlated noise, selective loss, and stronger adversaries.

**Efficiency**

- Planned, sent, received, tested, and successfully verified token counts.
- Simulated quantum circuit work and protocol runtime, not only detector microseconds.
- Additional evidence requested because of uncertainty.
- Resources saved by avoiding unnecessary tests or aborting adversarial sessions early.
- Verification outcome per unit of resource expenditure.

**System behavior**

- Correctness of logging, audit trails, and explanations.
- No weakening of binding, nonce freshness, authorization, or independent verifier state.
- Appropriate link responses to weak alerts, strong attacks, and benign noise.

All reported empirical rates should include the trial count and a suitable uncertainty estimate. **Zero observed failures is not proof of zero failure probability.**

### 8.4 Interpret the results without cherry-picking

The project should report both improvements and costs. For example, a policy may reduce honest rejection but increase forgery acceptance, or improve weak-channel detection but consume significantly more tokens. Those are trade-offs to evaluate, not evidence to hide. The test design should include conditions where the new method might reasonably perform worse.

---

## 9. Practical Phases and Dependencies

The following sequence sets milestones without prescribing source-code structure or individual algorithms.

| Phase | Technical work | Evidence that it is ready |
|---|---|---|
| A. Baseline characterization | Confirm present verifier rules, observed evidence counts, baseline noise model, and current experiment behavior | Reproducible reference outcomes and documented statistical assumptions |
| B. C1 model and threshold policy | Explore exact finite-sample acceptance decisions for direct and forwarded modes, including feasible security/reliability limits | Decisions and displayed probabilities are consistent; small-sample boundaries are understood |
| C. C1 system integration | Apply the chosen decision policy in actual verifier flow while preserving classical checks and independent evidence | End-to-end honest and hostile scenarios behave according to the policy |
| D. C2 allocation research | Explore evidence needs, detection-power targets, and cost of extra channel versus signature observations | A defensible rationale for when additional resources help—and when they cannot |
| E. C2 protocol integration | Support adaptive pre-reveal testing and any legitimate borderline-resolution mechanism | No reuse of consumed quantum evidence; bounded and statistically valid retries/stopping |
| F. Joint integration | Reconcile C1/C2 with detection attribution, circuit breaker, loss handling, UI, and audit records | Transparent outcomes and sensible link behavior across scenarios |
| G. Experimentation and comparison | Evaluate fixed baseline, C1, C2, and combined behavior under seeded noisy/adversarial trials | Reproducible security/reliability/resource comparisons and limitations |
| H. SIH demonstration and documentation | Present the model, attack scenarios, real decisions, resource use, and prototype operation | The demo claims match actual measured behavior |

**Dependency note:** C1 should first define what counts as statistically adequate evidence. C2 can then optimize the process of obtaining it. The tasks may be researched in parallel, but their security assumptions and decision vocabulary need to align before integration.

---

## 10. Non-Negotiable Constraints

1. **No hidden attack labels in live decisions.** The detector and allocation strategy may use observable trusted evidence; injected scenario names belong only in experimentation and evaluation.
2. **No classical-check bypass.** A package with an invalid commitment, message digest, identity, or replay context must not pass because its quantum mismatch statistic is favorable.
3. **No invalid quantum reuse.** Projective measurement consumes the relevant state; extra evidence requires a legitimate fresh resource or an earlier reserved sample.
4. **No unlimited try-until-pass behavior.** Retries, additional samples, and repeated threshold checks must be bounded and statistically justified.
5. **No unproven absolute security claims.** A simulated QDS component, classical cryptographic commitments, and optional post-quantum audit signatures have distinct security roles. Finite-sample binomial models are not complete proofs against general quantum attacks.
6. **No fabricated empirical guarantees.** Present measured rates, assumptions, uncertainty, and security limitations separately.
7. **No efficiency claim based only on detection latency.** Include the quantum-simulation workload and additional evidence expenditure.
8. **No aggressive quarantine from inconclusive data alone.** Response escalation must remain tied to appropriate evidence and policy.

---

## 11. Questions Left Open for Independent Design

These are deliberate design choices, not missing instructions that must be resolved in one predetermined way.

### Statistical policy

- What risk levels should be imposed on honest rejection and accepted forgery, and must the same requirements apply to every L?
- Is the priority maximum honest throughput, strict adversarial security, balanced performance, or an explicit multi-objective trade-off?
- Which adversary model is used when presenting a claimed minimum forgery mismatch probability?
- How should uncertainty in the honest QBER be represented?
- Should the framework distinguish ordinary rejection from a failure to collect statistically sufficient evidence?

### Resource allocation

- Is additional evidence permitted only through channel-test probes, or may the signature-distribution design also be extended?
- Can the protocol support a committed reserve or staged pre-reveal distribution without weakening authenticity or blinding?
- What are acceptable resource and delay ceilings under clean operation, suspicious operation, and recovery?
- How should the budget react when the link's baseline noise changes or token loss is selective?
- Which sequential-testing approach can satisfy the desired overall false-alarm policy?

### Product and demonstration scope

- Should L=16 be explicitly identified as a demonstration / low-evidence setting if it cannot satisfy stronger risk targets?
- Are Bob and Charlie expected to expose separate diagnostic policies or a common auditable policy with mode-specific parameters?
- Which metrics are most important for SIH judging: detection accuracy, false rejection, low-cost verification, resilience to noisy channels, or interpretability?
- Will evaluation cover a fixed simulator noise model only, or several realistic-noise backends and attack strengths?

The answers should emerge from model analysis and experiments, then be recorded as project decisions.

---

## 12. Definition of Done

### C1 is complete when:

- The project provides a defensible exact finite-sample interpretation of elimination mismatch counts under its stated model.
- The verifier's actual acceptance/rejection rule agrees with the statistical explanation it reports.
- Direct and forwarded modes retain their distinct threat assumptions and protections.
- Small-sample cases are handled without concealing the honest-rejection versus forgery-risk trade-off.
- Existing identity, message-binding, freshness, and independent-verification rules remain intact.
- Reproducible experiments show the outcome relative to the previous policy, including any costs or cases with no improvement.

### C2 is complete when:

- Token allocation responds to evidence requirements and channel/security conditions rather than only a fixed multiplier.
- Channel-test and signature-evidence requirements are treated as different questions.
- Borderline results have a defined, secure, bounded outcome consistent with distribution and reveal chronology.
- Repeated testing or early stopping does not silently invalidate the intended statistical error control.
- The approach functions across relevant short and longer signatures, noise conditions, and attack scenarios.
- Empirical results justify the security benefit relative to increased token use, runtime, and possible false lockouts.

### The combined enhancement is complete when:

HEDWIG can demonstrate, for a specified risk model and channel condition, **why a signature was accepted or rejected, how much evidence was necessary, what extra evidence cost, what attacks were detected or missed, and where the model's security claims stop**. The SIH demonstration, repository behavior, tests, and documentation must tell the same story.

---

## 13. Scope Boundary and Interpretation of Claims

This roadmap is a **technical direction document**, not an assertion that C1/C2 are already implemented and not a formal cryptographic proof. It intentionally leaves freedom to select numerical methods, internal APIs, test frameworks, resource policies, and protocol refinements, provided the design is explainable and empirically defensible.

The current HEDWIG implementation includes classical commitments and digital signatures in support of the simulation and audit system. Those components should be distinguished from any information-theoretic claim attributed to the underlying QDS protocol. Likewise, a faster quantum-inspired simulator is not the same as a deployable physical quantum communication system.

**Guiding principle:** Improve verification by acquiring and interpreting the *right* evidence—not by relaxing the definition of a valid signature or by adding complexity that the experiments cannot justify.

---

## Reference Basis

- SIH26141 supplied problem statement: *Quantum-Inspired Cyber Threat Detection for Digital Signature Security*, especially objectives and expected deliverables.
- Supplied `Goal.txt`: stated SIH objective and request to evaluate repository progress and remaining work.
- C1/C2 assignment screenshot: exact binomial threshold; L-aware adaptive token allocation and borderline retry.
- Reviewed project code and documentation in `miki-dev-5618/QDS`, `main` at `0f6afcd` (21 October 2026), particularly verification/security, channel tests, protocol, scheduling, detection, policy, enforcement, loss/noise behavior, and historical experiments.
- Historical results referenced from repository experiment documents generated in September 2026; not treated as fresh performance validation for the October codebase.
