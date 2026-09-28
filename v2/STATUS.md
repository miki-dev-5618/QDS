# HEDWIG V2 — Status Report: Innovations Progress

**As of:** 28 September 2026
**Version:** V2.2 (implements `../HEDWIG_V2_Implementation_and_Innovation_Roadmap.md`, steps 1 and 3–7, plus the simulated router)
**Change log and problems solved:** [`V2.2_IMPLEMENTATION_REPORT.md`](V2.2_IMPLEMENTATION_REPORT.md) · **Project guide:** [`../README.md`](../README.md)
**Reference:** `../INNOVATIONS_TEAM_ATHENA_V2.2.md` (corrected claims). The original `../INNOVATIONS_TEAM_ATHENA.md` is kept unchanged for history only.

**Legend**
- ✅ **Done**: implemented and tested
- 🟡 **Partial**: a working version exists but falls short of the claim
- ⏳ **Pending**: not started, but feasible
- ⛔ **Not feasible as claimed**: cannot be true for this design or at these parameters; the claim wording was changed

---

## 1. Progress at a glance

| Innovation | ✅ | 🟡 | ⏳ | ⛔ | Overall |
| :--- | :-: | :-: | :-: | :-: | :--- |
| 1. Message binding (was "Q-THB") | 5 | 0 | 0 | 2 | **Done** as a classical commitment; basis-schedule experiment run: a public schedule is harmful, a keyed one adds nothing measurable |
| 2. Quantum Circuit Breaker (QCB) | 8 | 0 | 0 | 0 | **Done** in simulation: WATCH/probation state machine, evidence accumulation, early abort, router, persistence, immediate incidents |
| 3. Two-tier discriminator | 5 | 1 | 0 | 0 | **Two tiers working**; 10⁻⁶ false alarms stays out of reach at these sizes |
| 4. Q-Cert audit record | 9 | 0 | 0 | 2 | **Done**: automatic, chained, per-verifier digests, bounds with assumptions, hybrid post-quantum signing when installed |

**Program health:**
- 149 tests pass; 1 more (hybrid ML-DSA-65) runs when `dilithium-py` is installed. It was verified locally with the provider and runs in CI.
- Server, Qiskit backend and all API routes are exercised by tests. The Qiskit path was smoke-tested: 2 honest runs and 1 intercept run with early abort.
- **Still to do by hand:** click-test the three dashboards in a browser (new WATCH banner, router diagram, incident list, reset prompt).

---

## 2. Innovation 1 — Message binding

**Honest claim:** a computational hash commitment binds arbitrary-length messages to a one-time simulated QDS verification record.

| # | Component | Status | Current point (code) |
| :-- | :--- | :-: | :--- |
| 1.1 | Sign arbitrary-length messages | ✅ | `binding.py` `SignedContext` |
| 1.2 | Detect single-character tampering | ✅ | Digest recomputed from the received text; 100% of trials |
| 1.3 | SHA3-512 option | ✅ | `SecurityParameters(digest_alg="sha3-512")`. The algorithm name is inside the commitment (no downgrade). The digest is domain separated. |
| 1.4 | Hash/keyed basis schedule | ✅ (experiment) | `schedule.py` and `experiments/basis_schedule.py` (see §6). Kept **off** by default. |
| 1.5 | Canonical encoding + hardening | ✅ | `canonical.py` rules (sorted keys, UTF-8, no normalisation, no NaN). Malformed blinding is rejected. Any change to sender, verifiers, nonce, timestamp, algorithm or version is rejected. Signatures cannot be transplanted between sessions. The nonce is consumed atomically and persistently. |
| 1.6 | "~50% quantum contradictions on tampering" | ⛔ | Removed. Verifiers measure before the message is revealed. |
| 1.7 | "Physically entangled" / information-theoretic | ⛔ | Removed. The binding is computational. |

## 3. Innovation 2 — Quantum Circuit Breaker

| # | Component | Status | Current point (code) |
| :-- | :--- | :-: | :--- |
| 2.1 | Automatic trigger | ✅ | `policy.py` `decide()` works from evidence strength. Classical rejections never lock a link (no free denial-of-service). |
| 2.2 | Quarantine, reset, probation | ✅ | `enforcement.py`: OPEN → WATCH → QUARANTINED → RESET_PENDING → OPEN. Reset needs the admin role **and a reason**, and issues a signed reset record. |
| 2.3 | Buffer purge | ✅ | Unaccepted distribution records are purged. The UI says these are software records, not destroyed qubits. |
| 2.4 | Timing | ✅ | Intervals are reported separately (`/api/metrics`, p50/p95/p99): channel observation, detection, post-verdict enforcement, incident signing, audit signing, 423 refusal, whole run. **Sequential early abort** saves 33–46% of tokens on attacked links. |
| 2.5 | Signed incident certificate | ✅ | Signed **at quarantine time** (`kind: incident`), linked to the transaction record |
| 2.6 | Incident timing record | ✅ | Transition log (actor, time, evidence id, old/new state, policy version) persisted in SQLite |
| 2.7 | Channel router | ✅ | `router.py`: star topology via relay QR-1 plus the classical `bob → charlie` link, with per-hop state, counters and drops. Diagram on the admin page. |
| 2.8 | Avoid false lock-outs | ✅ | 0% immediate honest quarantines at every L. WATCH escalation uses **Fisher-combined evidence**. Honest 10-run sequences ever quarantined at L = 16: **4.0%** (12% with a plain two-strike rule); 0% at L = 32 and 64. |
| — | Adaptive test allocation | ✅ | Twice as many test tokens while a link is on WATCH or probation |
| — | Persistence | ✅ | `store.py`: link state, transitions, nonces and audit chain survive restarts. Distribution records do not. |

## 4. Innovation 3 — Two-tier discriminator

| # | Component | Status | Current point (code) |
| :-- | :--- | :-: | :--- |
| 3.1 | No AI/ML | ✅ | Exact binomial tests, a conditional binomial test and Fisher's method; fixed, prespecified rules |
| 3.2 | Tier 1 with bounds shown | ✅ | `k/n`, exact p-value, exact false-alarm level and the Chernoff–KL bound beside it |
| 3.3 | Tier 2 as a separate statistic | ✅ | `discriminator.py`: conditional excess-contradiction test (`Bin(D, π)`) plus channel elevation. Result is channel / signature / **undetermined**. Tier 2 never rejects on its own. |
| 3.4 | KL divergence | ✅ | Shown as a diagnostic (Jeffreys smoothing), explicitly not a detector |
| 3.5 | False alarms < 10⁻⁶ | 🟡 | The immediate false-quarantine bound is ≤ 3×10⁻³ per honest run (union bound, honest-noise model). False rejection is measured: 3.0% at L = 16, 0/200 at L = 32 and 64. 10⁻⁶ still needs thousands of tokens. |
| 3.6 | Correct labelling | ✅ | Eavesdropping at L = 16 is labelled correctly in **91%** of runs (was 77.5%). Confident wrong labels on honest noise drop from 3–20% to 0–10% (sweep). The cost is abstention: see §7. |

## 5. Innovation 4 — Q-Cert audit record

| # | Component | Status | Current point (code) |
| :-- | :--- | :-: | :--- |
| 4.1 | Downloadable JSON | ✅ | `GET /api/audit/{id}` for transactions, incidents and resets |
| 4.2 | Cryptographically validated | ✅ | Per-check report (`POST /api/audit/verify`, `tools/verify_audit.py`), including the chain check |
| 4.3 | Issued on every transaction | ✅ | Automatically at assessment and persisted as exact signed bytes. The download is stable, never re-signed. |
| 4.4 | Bounds in the record | ✅ | Per-verifier values, inputs, formulas, required n and assumptions |
| 4.5 | P_forgery ≤ 2.4×10⁻⁸ | ⛔ | The record shows the actual value (≈ 0.4–0.9 at L = 16–64) |
| 4.6 | Elimination digest | ✅ | SHA3-256 per verifier. The evidence is attached and bound by the digests; tampering with it is detected. |
| 4.7 | Symmetrisation hash | ✅ | SHA3-256 of both verifiers' keep/forward actions |
| 4.8 | Fidelity | ✅ | Model-based `F = 1 − QBER` with CI, derived for a uniform Pauli channel. "Not reported" when the channel test rejects that model. |
| 4.9 | Post-quantum signature | ✅ | Hybrid Ed25519 + ML-DSA-65 when a provider is installed (`requirements-pq.txt`). Removing the ML-DSA signature is detected. Ed25519-only records are never labelled post-quantum. |
| 4.10 | Assurance level | ✅ | Computed from the bounds: `REJECTED` / `ACCEPTED - DEMONSTRATION GRADE` / `ACCEPTED - BOUNDS MEET TARGET` |
| 4.11 | "Zero-knowledge" | ⛔ | Renamed "signed audit record"; disclaimers are inside every record |
| — | Hash chain, key rotation | ✅ | Removed or reordered records are detected. Retired keys keep old records verifiable. |

## 6. Exploratory result: basis schedules (roadmap step 7)

`experiments/basis_schedule.md`, L = 32, 200 trials, equal qubit budgets. A schedule-aware Eve taps every token:

| Schedule | Tier 1 alarm | Forgery contradiction rate | Quantum layer alone would accept (of runs not aborted) |
| :--- | :-- | :-- | :-- |
| random (default) | 98.0% | 0.234 | 0% |
| public hash of message | 97.0% | **0.005** | **83%** |
| keyed HMAC (verifier secret) | 98.5% | 0.240 | 0% |

Conclusion: a public message-derived schedule lets Eve learn the eliminated states and **defeats the quantum layer**. The channel test and the classical commitment still stop her. A keyed schedule is indistinguishable from random, so there is no measurable gain. Random bases stay the default; the "Q-THB" basis idea is not adopted.

## 7. Measured results

From `experiments/results.md` and `experiments/sweep_tiers.md`: seed 2026, 200 trials per cell, honest depolarising p = 0.01, statevector backend. Brackets are 95% Wilson intervals.

| Scenario | L = 16 | L = 32 | L = 64 |
| :--- | :--- | :--- | :--- |
| Honest runs wrongly rejected | 3.0% [1.4, 6.4] | 0% [0, 1.9] | 0% [0, 1.9] |
| Honest runs quarantined immediately | 0% [0, 1.9] | 0% | 0% |
| Honest 10-run sequences ever quarantined (200 sequences) | 4.0% [2.0, 7.7] | 0% [0, 1.9] | 0% [0, 1.9] |
| Eve forgery flagged | 100% | 100% | 100% |
| Dishonest Bob flagged (elimination alone) | 100% (88%) | 100% (95.5%) | 100% (98.5%) |
| Eavesdropping flagged (labelled correctly) | 98.5% (91%) | 100% (98.5%) | 100% (100%) |
| Eavesdropping aborted early (tokens saved) | 28.5% (33%) | 76.5% (39%) | 97.5% (46%) |
| Repudiation flagged (labelled / undetermined) | 98.5% (36.5% / 61.5%) | 98.5% (90.5% / 7.5%) | 100% (100% / 0%) |
| Tampering / replay / impersonation flagged | 100% | 100% | 100% |

**Honest trade-offs:**
- At L = 16, Tier 2 abstains on most repudiation runs instead of guessing. V2.1 labelled them "repudiation" by default, which also mislabelled 17–44% of intercept runs and 3–20% of noisy honest runs. Use L ≥ 32 for the demo.
- With bursty noise, Tier 2 still wrongly attributes 4.5–10% of honest runs to an attack cause. Its binomial model assumes independent errors.
- The detector now takes about 60–380 µs (p50, varies by run and scenario), up from about 30 µs, because it computes the Tier 2 statistics and builds the evidence. Qiskit channel observation takes about 320 ms for an honest run at L = 32, and about 160 ms when aborted early.

## 8. Remaining work

| Step | Work | Effort |
| :-- | :--- | :-: |
| 1 | Click-test all three dashboards; rehearse the SIH demo script (roadmap §SIH) | S |
| 2 | Push to a branch so CI runs, including the ML-DSA job; record commit and environment | S |
| 3 | Replace demo credentials before any non-localhost use | S |
| 4 | Optional: a Tier 2 model that allows bursts (e.g. a runs test) to cut honest-burst misattribution | M |
| 5 | Optional: a formal composable bound for the exact protocol (roadmap workstream 5) | L |

## 9. Running and verifying

```powershell
cd v2
.\run_v2.bat                                            # or: python -m uvicorn server:app --port 8000
pip install -r requirements-dev.txt                     # add requirements-pq.txt for hybrid ML-DSA-65
python -m pytest tests -q                               # 149 tests (+1 with an ML-DSA provider)
python experiments/run_trials.py --trials 200 --bits 16 32 64
python experiments/sweep_tiers.py --trials 200
python experiments/basis_schedule.py --trials 200 --bits 32
```

Demo logins (localhost only): `admin/admin2026`, `bob/quantum2026`, `charlie/quantum2026`.

## 10. Key files per innovation

| Innovation | Files |
| :--- | :--- |
| 1. Binding | `binding.py`, `canonical.py`, `verifier.py`, `replay.py`, `schedule.py` |
| 2. QCB | `policy.py`, `enforcement.py`, `router.py`, `store.py`, `protocol.py` (early abort, `assess`), `server.py` |
| 3. Discriminator | `channel.py` (Tier 1), `discriminator.py` (Tier 2), `detection.py`, `security.py` |
| 4. Q-Cert | `audit.py`, `signers.py`, `tools/verify_audit.py`, `server.py` (`/api/audit/*`) |
| Evidence | `tests/`, `experiments/run_trials.py`, `experiments/sweep_tiers.py`, `experiments/basis_schedule.py` |
