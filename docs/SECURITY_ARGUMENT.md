# HEDWIG security argument

**Status:** this document adapts the reasoning of published quantum digital signature (QDS) analyses to the
thresholds HEDWIG implements. It is **not a new security proof**, it does **not** cover all attacks, and HEDWIG
itself is a classical simulation of the quantum layer (Qiskit / statevector), so it provides no physical
quantum-channel security at all. Every formula below is taken from the code it names; `tests/test_security_argument.py`
recomputes the numbers in this file from `SecurityParameters` so the document fails CI if the code changes.

Code references: [`src/quantum_engine/security.py`](../src/quantum_engine/security.py),
[`src/quantum_engine/thresholds.py`](../src/quantum_engine/thresholds.py),
[`src/quantum_engine/discriminator.py`](../src/quantum_engine/discriminator.py),
[`src/quantum_engine/channel.py`](../src/quantum_engine/channel.py).

---

## 1. Setting and assumptions

Three parties: a signer (Alice) and two verifiers (Bob, Charlie). For a signature of length L, Alice prepares two
copies of a random BB84 state (|0⟩, |1⟩, |+⟩, |−⟩) per position. Each verifier keeps or forwards each copy
(symmetrisation), every held copy is teleported to its holder and measured in a random basis, and the holder records
the state that outcome *eliminates*. A copy is a **mismatch** when the revealed signature state equals the
eliminated state. Each verifier ends up with n checked copies, n ~ Bin(2L, 1/2) ≈ L (`reserve_plan()` plans for
one standard deviation below the mean).

The argument holds only under these assumptions (the code lists them as `ASSUMPTIONS` in `security.py`):

| # | Assumption | Where it is used / enforced |
|---|---|---|
| A1 | **Authenticated classical channel** between all parties (commitments, reveals and test-token disclosures cannot be forged in transit). | Binding: `binding.py` commitment `C = SHA-256(domain ‖ canonical(context) ‖ signature ‖ salt)`. Assumed, not proven. |
| A2 | **i.i.d. honest noise**: honest test-token QBER ≤ e0, so an honest copy mismatches with probability ≤ μ_h = e0/2 (a copy can only eliminate the true state when measured in its preparation basis, probability 1/2, *and* flipped). | Tier 1 channel test enforces e0 statistically at level α (`channel.py`, `estimate_channel_qber`). |
| A3 | **Simulated, ideal teleportation resource**: Bell pairs and feed-forward are perfect apart from the configured channel model. | All of `teleportation.py`. A modelling assumption. |
| A4 | **Independence of tokens** after symmetrisation and the random stream permutation: per-copy outcomes are independent, and every copy is assigned to Bob or Charlie independently and uniformly. | `symmetrisation.py`, `protocol.distribute()` (`rng.permutation`). |
| A5 | **Forger model**: a party without Alice's states mismatches each copy with probability ≥ p_min. p_min = 1/4 for an outside guesser, ≥ 1/6 for a dishonest verifier holding one copy of the same token. The code uses the conservative **p_min = 1/6** for both modes. | `SecurityParameters.forger_min_mismatch`. See section 5 for an adversary that violates it. |

## 2. Definitions

For one verification of n checked copies with M mismatches, under a fixed decision rule:

- **Honest false rejection** (FR): P(signature not accepted | honest signer, channel satisfies A2).
  Honest model: M ~ Bin(n, μ_h).
- **Forgery acceptance** (FA): P(signature accepted | revealed signature does not come from Alice's states).
  Forger model: M ~ Bin(n, p_min).
- **Repudiation**: Alice makes Bob accept a signature directly (limit s_a) while Charlie, receiving it forwarded
  from Bob, rejects it (limit s_v). Symmetrisation makes Alice unable to tell which copy went to whom, so both
  verifiers face the same per-copy mismatch probability.

## 3. Thresholds

### 3.1 Parameters (defaults in `SecurityParameters`)

| Symbol | Code | Value |
|---|---|---|
| e0 | `honest_qber` | 0.02 |
| μ_h = e0 / 2 | `mu_honest` | 0.01 |
| p_min | `forger_min_mismatch` | 1/6 ≈ 0.1667 |
| gap = p_min − μ_h | `gap` | 0.1567 |
| FR target / FA target (exact rule) | `fr_target` / `fa_target` | 0.01 / 0.01 |
| Hoeffding target (legacy) | `target_failure` | 1e-06 |

### 3.2 Legacy thresholds s_a and s_v

The gap between the honest and forger mismatch rates is split into thirds:

```
s_a = μ_h +     gap / 3  = 0.0622     (direct:    accept iff M <= floor(s_a · n))
s_v = μ_h + 2 · gap / 3  = 0.1144     (forwarded: accept iff M <= floor(s_v · n))
```

`security.py`: `s_a`, `s_v`, `limit_rate()`; `thresholds.legacy_rule()` computes `floor(limit_rate · n + 1e-9)`.
The ordering μ_h < s_a < s_v < p_min gives a margin on each side:
s_a − μ_h = gap/3 (honest margin), p_min − s_a = 2·gap/3 (forgery margin), s_v − s_a = gap/3 (transfer margin).

### 3.3 Hoeffding bounds, step by step

Hoeffding's inequality for the mean of n independent [0,1] variables with mean p: for d > 0,
P(M/n − p ≥ d) ≤ exp(−2d²n), and P(M/n − p ≤ −d) ≤ exp(−2d²n). The code (`security._hoeffding`, `bounds()`)
applies it three times at the legacy rate s (s = s_a direct, s_v forwarded):

1. **False rejection.** The rule rejects when M > floor(s·n), i.e. M ≥ floor(s·n) + 1 > s·n. So
   FR ≤ P(M/n ≥ s) = P(M/n − μ_h ≥ s − μ_h) ≤ **exp(−2 (s − μ_h)² n)**.
2. **Forgery acceptance.** The rule accepts when M ≤ floor(s·n) ≤ s·n. With the forger's mean ≥ p_min,
   FA ≤ P(M/n ≤ s) ≤ P(M/n − p_min ≤ −(p_min − s)) ≤ **exp(−2 (p_min − s)² n)**.
3. **Repudiation.** Let p be the common per-copy mismatch probability and d = (s_v − s_a)/2. Bob accepts and
   Charlie rejects only if Bob's rate ≤ s_a and Charlie's rate > s_v, which needs Bob's rate ≤ p − d or Charlie's
   rate ≥ p + d. A union bound gives
   P(repudiation) ≤ 2 exp(−2 d² n) = **2 exp(−(s_v − s_a)² n / 2)**.

The sample size needed for a target ε (`_n_required`): n ≥ ln(factor/ε) / (2d²). At ε = 1e-06 the three bounds
need n ≥ **2533** (FR, direct), **634** (FA, direct) and **10641** (repudiation) checked copies per verifier.

### 3.4 Exact binomial thresholds (C1, the default rule)

`threshold_policy="exact"` (default) replaces the fractional limits with integer limits chosen from the exact
binomial distributions at the observed n (`thresholds.py`):

```
k_fr = min k  with  P_h(M > k)  <= fr_target      M ~ Bin(n, μ_h)      reliability_limit()
k_fa = max k  with  P_f(M <= k) <= fa_target      M ~ Bin(n, p_min)    forgery_cap_limit()
```

- **Feasible** (k_fr ≤ k_fa): direct accepts iff M ≤ k_fr, forwarded accepts iff M ≤ k_fa (the most permissive
  limit inside the forgery budget, which keeps a transfer margin). Both FR and FA are exact within the i.i.d. model.
- **Infeasible** (too few copies): accept iff M ≤ max(k_fa, 0), reject iff M > k_fr, and counts in between are
  **INCONCLUSIVE** (`INCONCLUSIVE_EVIDENCE`: not accepted, no attack attributed).
- **Two-stage reserve** (C2): with n2 precommitted reserve copies, stage 1 accepts M1 ≤ a1, rejects M1 > r1, and
  otherwise opens the reserve and accepts iff M1 + M2 ≤ a2. FR and FA are computed for the whole stopping rule
  (`_two_stage_errors`), so looking at stage 1 first does not inflate either error.

The smallest single-stage n meeting both 1% targets is **n = 57** (`min_sufficient_n`). Repudiation has no exact
value: the two verifiers' counts are correlated under symmetrisation, so the code shows only the Hoeffding
reference for it.

### 3.5 What the numbers look like at HEDWIG's sizes

Computed with the default parameters (`SecurityParameters().elimination_rule(n, forwarded)` and `bounds()`):

| n (copies per verifier) | Rule | Limit | Exact FR | Exact FA | Hoeffding FR | Hoeffding FA |
|---|---|---|---|---|---|---|
| 16 | exact, direct | 0 (INCONCLUSIVE up to 2) | 1.49e-01 | 5.41e-02 | 9.164e-01 | 7.053e-01 |
| 32 | exact, direct | 0 (INCONCLUSIVE up to 2) | 2.75e-01 | 2.93e-03 | 8.398e-01 | 4.975e-01 |
| 64 | exact, direct | 3 | 3.94e-03 | 3.66e-03 | 7.053e-01 | 2.475e-01 |
| 64 | legacy, forwarded (s_v) | 7 | 2.69e-07 | 1.42e-01 | 2.475e-01 | 7.053e-01 |
| 64 | exact, forwarded | 3 | 3.94e-03 | 3.66e-03 | — | — |

Reading this table honestly:

- **The Hoeffding bounds are vacuous at demo sizes.** At n ≤ 256 the false-rejection bound is between 0.25 and
  0.92 and the repudiation bound is 1.0. They are kept as a conservative reference, not as evidence.
- **The legacy forwarded limit is weak.** s_v = 0.1144 is close to p_min = 0.1667, so at n = 64 a forger is accepted
  with exact probability 0.142 under the legacy rule. The exact rule caps it at the 1% target.
- **Short signatures cannot meet the 1% targets in one stage.** At L = 16 and 32 the exact rule needs the
  precommitted reserve (`reserve_plan()` sizes it at 16 and 28 extra positions) or returns INCONCLUSIVE.

### 3.6 Tier 1 and Tier 2 (supporting checks)

- **Tier 1** (`channel.py`): with t disclosed test tokens and e errors, alarm iff e > k where
  k = min k with P(Bin(t, e0) > k) ≤ α (α = `false_alarm_alpha` = 0.01). Early abort uses the stricter
  `strong_alpha` = 1e-3 level after each stream block.
- **Tier 2** (`discriminator.py`): conditional on D = e + m disturbances, m | D ~ Bin(D, π) with
  π = (n/2)/(t + n/2), whatever the unknown QBER. p_excess = P(Bin(D, π) ≥ m) ≤ 0.05 attributes the rejection to
  the signature; else p_channel = P(Bin(t, e0) ≥ e) ≤ 0.10 attributes it to the channel; else UNDETERMINED.
  Tier 2 never rejects on its own, so it does not change FR; its cost is mislabelling.

### 3.7 Mismatches between documentation and code found while writing this

| Where | Says | Code does | Severity |
|---|---|---|---|
| `README.md` architecture step 5 | Mismatches are tested "against Hoeffding and exact binomial acceptance thresholds (s_a for direct delivery, s_v for forwarded)" | The default exact rule uses the integer limits k_fr (direct) and k_fa (forwarded) from section 3.4; s_a / s_v are used only with `threshold_policy="legacy"`, and the Hoeffding values are a displayed reference, not a decision rule | Wording could mislead |
| `experiments/results.md` | Detection table for the current system | Generated 2026-09-28, before the exact thresholds and adaptive test allocation (C1/C2) | Results out of date; regenerate with `run_experiments.py` |
| `security.py` `bounds()` | `hoeffding_reference.false_reject` for forwarded mode | Uses s = s_v, i.e. the legacy forwarded rate even when the exact rule is applied | Consistent with its label ("legacy rate"), but easy to misread |

No formula in `security.py`, `thresholds.py` or `discriminator.py` was found to disagree with its own docstring.

## 4. Relation to published QDS work

HEDWIG's structure (one-time quantum signature states, elimination measurements, symmetrisation between two
recipients, and separate acceptance thresholds for direct and forwarded signatures) follows the QDS literature
below. The bibliographic details were checked against arXiv / publisher records; **the specific claims about what
each paper contains, and any mapping of HEDWIG's thresholds onto them, must be verified against the papers before
use** — this document does not claim to reproduce any of their proofs.

| Paper | Bibliographic record (checked) | What HEDWIG takes from it (verify before use) |
|---|---|---|
| D. Gottesman, I. Chuang, *Quantum Digital Signatures* (2001) | arXiv:quant-ph/0105032 | The idea of a one-time quantum signature built from a quantum one-way function, modelled on classical one-time signatures. |
| V. Dunjko, P. Wallden, E. Andersson, *Quantum Digital Signatures without Quantum Memory*, Phys. Rev. Lett. **112**, 040502 (2014) | arXiv:1309.1375 | A scheme in which recipients need no long-term quantum memory and can measure immediately. |
| R. J. Collins, R. J. Donaldson, V. Dunjko, P. Wallden, P. J. Clarke, E. Andersson, J. Jeffers, G. S. Buller, *Realization of Quantum Digital Signatures without the Requirement of Quantum Memory*, Phys. Rev. Lett. **113**, 040502 (2014) | arXiv:1311.5760 | Quantum state elimination as the recipients' measurement; an experimental realisation with linear optics. |
| R. Amiri, P. Wallden, A. Kent, E. Andersson, *Secure quantum signatures using insecure quantum channels*, Phys. Rev. A **93**, 032325 (2016) | arXiv:1507.02975, DOI 10.1103/PhysRevA.93.032325 | Security without trusted quantum channels; direct vs. forwarded verification thresholds. Note that this paper claims security against general coherent attacks; HEDWIG's i.i.d. analysis does **not** inherit that claim. |

Differences that matter: HEDWIG teleports discrete BB84-like states in a simulator instead of sending coherent
states optically; its forger bound p_min and the gap-in-thirds thresholds are HEDWIG's own choices; the exact
binomial rule, reserve stage, Tier 2 attribution and circuit breaker are HEDWIG additions with no counterpart
claimed in these papers.

## 5. Empirical evidence (tests, not proofs)

These are seeded simulations of the model in section 1. They test whether the implementation behaves as the
analysis predicts against the adversaries that were coded; they cannot show security against adversaries nobody
wrote.

| Task | What was tested | Output | What it shows |
|---|---|---|---|
| B2 cloning | Universal (F = 5/6) and phase-covariant 1→2 cloners, L = 16/32/64, ≥ 200 trials | [`experiments/cloning_results.md`](../experiments/cloning_results.md) | Detection 100% and forgery success 0% in every cell. **But** Bob's measured elimination mismatch is 0.067–0.105, *below* p_min = 1/6: assumption A5 does not hold for a cloner. The protection comes from the Tier 1 channel test (measured cloner QBER 0.147–0.185 ≫ e0 = 0.02), not from the elimination threshold. |
| B2 partial intercept-resend | Intercept fraction 0.05–1.0, L = 16/32/64, 200 trials | [`experiments/sweep_partial_ir.csv`](../experiments/sweep_partial_ir.csv), [`.png`](../experiments/sweep_partial_ir.png) | Detection grows with the intercepted fraction; at fraction 0.05 and L = 32 it is 3% [1.4%, 6.4%]. A low-rate intercept stays inside the honest-noise allowance by design. |
| D1 harness | All scenarios × L × noise profiles, 1,000 trials per cell, Wilson 95% CIs | `experiments/harness.py` → `summary.csv` (generate with `run_experiments.py`) | Detection, false-rejection and correct-class rates per cell. |
| D2 ROC | Mismatch-rate score, honest vs. each attack, bootstrap AUC CI, Hoeffding and exact operating points | `experiments/make_roc.py` → `roc_auc.csv`, `roc_L*.png` | Separation of honest and attack mismatch rates at each L. |
| D3 / D4 ablations | Early abort on/off; Tier 1 only vs. Tier 1 + 2 | `experiments/ablate_early_abort.py`, `experiments/ablate_tiers.py` | Bandwidth saved by early abort; attribution accuracy added by Tier 2. |
| D5–D7 | Adaptive allocation, Fisher escalation vs. k-alert, baselines | `experiments/ablate_adaptive.py`, `ablate_escalation.py`, `baselines.py` | Effect of each design choice against simpler baselines. |
| B1, B3, B4, D8 | — | **Not in the repository yet** | No evidence; see section 6. |

Regenerate everything with one command: `python run_experiments.py --seed 2026`. Numbers produced before the C1/C2
merge (including `experiments/results.md`) describe the legacy rule and should not be quoted for the current system.

## 6. What we do NOT prove

- **General collective or coherent attacks.** Every probability above assumes independent per-copy outcomes (A4)
  and a forger with per-copy mismatch ≥ p_min (A5). An adversary who entangles tokens, adapts across copies or
  correlates loss with outcomes is outside the model. The published schemes in section 4 that do claim coherent-attack
  security use different protocols and proofs; HEDWIG does not inherit them.
- **The p_min assumption for every adversary.** The B2 cloning results show an adversary whose per-copy mismatch is
  below p_min. HEDWIG still caught it, but through the channel test; there is no proof that the channel test and the
  elimination check together cover every adversary.
- **Hardware imperfections.** No real photons, detectors or Bell measurements are involved. Detector efficiency
  mismatch, multi-photon pulses, dark counts and calibration drift are not modelled beyond the configurable noise
  profiles (depolarising, amplitude damping, readout error, heralded loss, IBM fake-backend noise).
- **Side channels.** Timing, power and electromagnetic leakage, and the pure-Python ML-DSA reference implementation
  (`dilithium-py`, not side-channel hardened), are out of scope.
- **Fisher independence under drift.** The circuit breaker combines p-values with Fisher's method, which assumes
  independent p-values under the null. Slowly drifting channel noise breaks that assumption. The planned test (D8)
  is not in the repository, so this remains unverified.
- **Repudiation, exactly.** Only the Hoeffding reference exists, and it is vacuous at demo sizes (section 3.5).
- **The classical layer.** The authenticated classical channel (A1), the SHA-256 commitment, nonce/replay
  protection and the Ed25519 / ML-DSA-65 audit signatures are standard primitives assumed secure, not analysed here.
- **Composability.** None of the statements above is a composable security proof.

**One-line summary:** HEDWIG's security argument adapts published QDS analyses to its thresholds; it is not a new
proof and does not cover all attacks.
