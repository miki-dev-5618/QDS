# HEDWIG V2: Teleportation QDS with Evidence-Based Threat Detection

**Team ATHENA | Smart India Hackathon (SIH 2026)**
**Problem Statement:** PS 26141 — Quantum-Inspired Cyber Threat Detection for Digital Signature Security

V2.1 reworked detection so that every verdict comes from what the verifiers can observe. The attack menu drives an *injector* only; Bob, Charlie and the detector never receive the scenario label. The changes follow `QDS_V2_Detection_Issues.md` (see [§8](#8-review-issue-mapping)).

**V2.2** implements `../HEDWIG_V2_Implementation_and_Innovation_Roadmap.md`: a second statistical tier that attributes contradictions to the channel or the signer (or abstains), a WATCH → QUARANTINE → probation circuit breaker driven by evidence strength, sequential early abort, a simulated router, SQLite persistence, hash-chained audit records issued automatically (optionally hybrid post-quantum signed), and three new experiment scripts. Status per item: [`STATUS.md`](STATUS.md). Everything that changed and every problem solved: [`V2.2_IMPLEMENTATION_REPORT.md`](V2.2_IMPLEMENTATION_REPORT.md). Beginner-friendly project guide (setup, how it works, demo script, API, troubleshooting): [`../README.md`](../README.md).

---

## 1. What the system does

A three-party quantum digital signature simulation. Alice signs. Bob and Charlie verify independently.

1. **Distribution.** Alice prepares random Pauli eigenstates `{|0⟩,|1⟩,|+⟩,|−⟩}`, one copy for each verifier. Bob and Charlie *keep or forward* each copy (symmetrisation). Every held copy is **teleported** through a Bell pair with a Bell measurement, classical feed-forward and an `X^m2 Z^m1` correction. The verifier then measures it in a random basis and records the orthogonal state it rules out. **Test tokens** are interleaved at secret random stream positions and measured in their disclosed basis to estimate the channel QBER. The stream goes out in blocks; as soon as the running test-error count is *decisive* (above the quarantine-grade threshold) the rest of the stream is never sent (**sequential early abort**, same false-alarm level). Alice sends each verifier a SHA-256 **commitment** to `(context, signature)`.
2. **Reveal.** If the channel test passed, Alice sends the message, the context, the signature and a blinding value. An aborted session is never revealed.
3. **Verify.** Each verifier independently checks:
   - that a distribution record exists for this session and sender;
   - that the package is addressed to it;
   - that the session was not aborted;
   - freshness (nonce not already used, timestamp within the window);
   - elimination mismatches against the threshold;
   - that the message digest and the commitment both match.
4. **Assess.** A blind classifier (Tier 1 channel test + Tier 2 disturbance attribution) turns those observations into a verdict for *this* transmission. A separate response policy decides what happens to *future* traffic (none / watch / quarantine) from the evidence strength. Every run gets a signed audit record at once; a quarantine also gets a signed incident record at once.

The context is `version, session_id, sender, verifiers, nonce, timestamp, digest_alg, digest(message)`, encoded by the rules in `canonical.py` (sorted keys, UTF-8, no Unicode normalisation, no NaN). The digest is domain separated (`"HEDWIG-QDS-v2|message|" || message`) and is SHA-256 by default or SHA3-512 (`SecurityParameters(digest_alg="sha3-512")`); the algorithm name is inside the commitment, so it cannot be downgraded.

The teleportation circuit runs in **Qiskit Aer** in the live app (`HEDWIG_BACKEND=qiskit`, the default). It runs on an equivalent **3-qubit statevector simulator** for bulk experiments. `tests/test_teleportation.py` checks both backends:
- unit fidelity on a noiseless channel;
- identical matched-basis outcomes;
- about a 25% error rate under intercept-resend.

## 2. Roles and access control

| Node | Page | Can do |
| :--- | :--- | :--- |
| Alice / Admin (signer) | `/admin` | Sign and send, arm the attack injector, reset quarantined links, view metrics and security events |
| Bob (verifier 1) | `/bob` | See his own verification; act as a *dishonest* Bob forwarding a forgery to Charlie |
| Charlie (verifier 2) | `/charlie` | See his own verification, including checks on packages forwarded by Bob |

- **Sessions.** Each role logs in separately. The server keeps each session and sets an HttpOnly, SameSite=Strict cookie per role (`hedwig_admin`, `hedwig_bob`, `hedwig_charlie`), so one browser can hold all three.
- **Access checks.** Every page, API route and WebSocket (`/ws/{role}`) checks the session server-side. A Bob session cannot sign as Alice, reset links, or open `/ws/admin`.
- **Sender identity.** The signer identity comes from the authenticated session, never from the request body.
- **Security events.** Attempts to fetch another verifier's verification (`/api/verification/{tx}/{verifier}`) are logged as `UNAUTHORIZED_VERIFICATION`. Failed logins, unauthenticated calls and rejected WebSockets are logged too.
- **Credentials.** Passwords are stored as PBKDF2-SHA256 hashes. Without `HEDWIG_USERS_FILE` the built-in **demo** accounts are active (`admin/admin2026`, `alice|bob|charlie/quantum2026`), and the server and login page warn about it. Create real accounts before exposing the server:
  ```powershell
  python auth.py add-user users.json alice admin
  $env:HEDWIG_USERS_FILE = "users.json"
  ```

## 3. Attack injectors and how each one is detected

| Injected scenario | What the injector changes | Evidence the verifiers use |
| :--- | :--- | :--- |
| `authentic` | Nothing (lightly noisy channel, depolarising p = 0.01) | — |
| `eve_forgery` | Replaces the revealed signature with random guesses | Elimination mismatches **and** commitment mismatch → `EXTERNAL_FORGERY` |
| `dishonest_bob` | Bob builds a signature for his own message from *his* eliminations and forwards it to Charlie | Charlie's forwarded-mode check (limit `s_v`) plus commitment → `DISHONEST_VERIFIER_FORGERY` |
| `eve_intercept` | Eve intercept-resends every Bell half | Test-token error count above the binomial alarm threshold (Tier 1) → `EAVESDROPPING_TAMPERING`; if Tier 1 misses but contradictions match an elevated channel (Tier 2) → same label, "channel anomaly (Tier 2)" |
| `message_tampering` | Changes the message after signing | Digest of the received message ≠ context digest → `MESSAGE_INTEGRITY_VIOLATION` |
| `repudiation` | Dishonest Alice puts orthogonal states in Charlie's copy at 50% of positions | Her own committed signature fails elimination and Tier 2 finds more contradictions than the channel explains → `REPUDIATION_ATTEMPT`; if Tier 2 cannot tell → `UNDETERMINED_DISTURBANCE` |
| `replay` | Re-sends an identical copy of the last accepted package | Nonce already consumed → `REPLAY_ATTACK` |
| `impersonation` | Rogue sender claims to be Alice with no distribution stage | No distribution record for the claimed sender → `IMPERSONATION_ATTACK` |

Decision order and classification rules are documented in `src/quantum_engine/detection.py`.

## 4. Thresholds, bounds and their assumptions

There is one threat model (`src/quantum_engine/security.py`):

| Symbol | Default | Meaning |
| :--- | :--- | :--- |
| `e0` | 0.02 | Assumed honest channel QBER, enforced by the channel test at α = 0.01 |
| `μ_h` | `e0/2` | Honest per-copy mismatch probability |
| `p_min` | `1/6` | Minimum per-copy mismatch probability of a forger lacking the signer's states: 1/4 for an outside guesser, ≥ 1/6 for a dishonest verifier holding one copy (derivation in `security.py`) |
| `s_a` | `μ_h + (p_min − μ_h)/3` | Acceptance limit for a signature received directly |
| `s_v` | `μ_h + 2(p_min − μ_h)/3` | Acceptance limit for a forwarded signature (`s_a < s_v`) |

**Decision rule:** accept iff `mismatches ≤ floor(s · n)`, where `n` is the number of measured copies. The dashboards display Hoeffding bounds for this same rule, with their inputs:
- `P(false reject) ≤ exp(−2(s−μ_h)²n)`
- `P(forgery accepted) ≤ exp(−2(p_min−s)²n)`
- `P(repudiation) ≤ 2exp(−(s_v−s_a)²n/2)`

These bounds assume:
- independent per-copy outcomes;
- the per-copy rates above;
- uniform keep-or-forward.

They do **not** cover coherent or collective attacks, and they are illustrative rather than a composable security proof.

At the signature lengths offered in the UI (16–64), the bounds are **far from 10⁻⁶**. Each dashboard shows the `n` that would be needed (thousands of copies). The observed detection rates below are much better than the bounds, because the bounds are worst-case, but those rates are measurements, not guarantees.

**Tier 1 (channel test).** Raises an alarm when test-token errors exceed the smallest `k` with `P(Bin(n, e0) > k) ≤ α`. It reports `k/n`, the exact p-value, the exact false-alarm level, the Chernoff–KL bound `exp(−n·D((k+1)/n ‖ e0))` beside it (always ≥ the exact level), the Wilson 95% interval and the power against intercept-resend (QBER = 0.25).

**Tier 2 (disturbance attribution, `discriminator.py`).** A Pauli-type channel disturbance with matched-basis error `q` makes test tokens err with probability `q` and signature copies contradict with probability `q/2`. Conditional on the total `D = e + m`, the contradiction count is `Bin(D, π)` with `π = (n/2)/(t + n/2)`, whatever `q` is. So:
- `p_excess = P(Bin(D, π) ≥ m)` ≤ α₂ = 0.05 → **signature inconsistency** (more contradictions than the channel explains);
- else `p_channel = P(Bin(t, e0) ≥ e)` ≤ β = 0.10 → **channel disturbance**;
- else → **undetermined**.

Tier 2 never rejects on its own. It only attributes a rejection the elimination check already made, so the rejection false-alarm rate is unchanged; its cost is mislabelling or abstaining, which `experiments/sweep_tiers.py` measures. A KL divergence from the honest reference (Jeffreys-smoothed) is shown as a diagnostic only.

**Response policy (`policy.py`, `hedwig-qcb/2`).** Classical rejections (replay, impersonation, message integrity) never lock a link, because anyone can trigger them at will. Quantum-evidence rejections quarantine immediately when the evidence p-value is ≤ 10⁻³. Otherwise the link goes on WATCH. Further weak alerts within 15 minutes are combined with **Fisher's method** (`−2Σ ln pᵢ ~ χ²₂ₖ`), and the link is quarantined when the combined p ≤ 0.01 or after three alerts. Two borderline honest-noise alerts (p ≈ 0.15 each) combine to ≈ 0.11 and do not lock the link; two moderately strong ones (p ≈ 0.02) combine to ≈ 0.004 and do. By the union bound, an immediate false quarantine on one honest run is ≤ 3 × 10⁻³ under the honest-noise model; escalation through WATCH is measured, not bounded.

## 5. Measured behaviour (seeded experiments)

Run with `python experiments/run_trials.py --trials 200 --bits 16 32 64` (seed 2026, statevector backend). Full tables: [`experiments/results.md`](experiments/results.md), [`experiments/sweep_tiers.md`](experiments/sweep_tiers.md), [`experiments/basis_schedule.md`](experiments/basis_schedule.md). Brackets are 95% Wilson intervals.

| L | Honest false rejection (immediate quarantine) | Eve forgery flagged | Dishonest Bob: flagged / elimination-only | Intercept: flagged / labelled eavesdropping / early abort | Repudiation: flagged / labelled / undetermined |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 16 | 0.030 [0.014, 0.064] (0.000) | 1.000 | 1.000 / 0.880 | 0.985 / 0.910 / 0.285 | 0.985 / 0.365 / 0.615 |
| 32 | 0.000 [0.000, 0.019] (0.000) | 1.000 | 1.000 / 0.955 | 1.000 / 0.985 / 0.765 | 0.985 / 0.905 / 0.075 |
| 64 | 0.000 [0.000, 0.019] (0.000) | 1.000 | 1.000 / 0.985 | 1.000 / 1.000 / 0.975 | 1.000 / 1.000 / 0.000 |

Replay, impersonation and message tampering were flagged in every run at every length.

What these numbers mean:
- **Small signatures are weak.** At L = 16, about 3% of honest runs are rejected. They are now labelled `UNDETERMINED_DISTURBANCE` and only put the link on WATCH; no single honest run was quarantined. Over 200 sequences of 10 honest runs, 4.0% [2.0, 7.7] ever reached quarantine at L = 16 (12% with a plain two-strike rule), and none at L = 32 or 64. Use L ≥ 32 for demos.
- **Tier 2 fixes the intercept labelling** at L = 16 (0.775 → 0.910). **It abstains rather than guess** on most small-L repudiation runs; V2.1's default "repudiation" label looked better there but mislabelled 17–44% of intercept runs and 3–20% of noisy honest runs (`sweep_tiers.md`).
- **Early abort** stops attacked streams after 54–67% of the tokens on average.
- **Dishonest-Bob detection is 100% overall because of the classical commitment.** The *elimination-only* column is the quantum check on its own: 0.88 at L = 16, rising to 0.985 at L = 64.
- **Bursty noise** is Tier 2's weak spot: 4.5–10% of honest runs with bursts get a confident wrong cause label (the model assumes independent errors).
- **Latency:** the classifier (Tier 1 + Tier 2 + evidence) takes about 60–380 µs (p50, varies by run and scenario) on the development laptop, up from about 30 µs in V2.1. Qiskit channel observation takes about 320 ms for an honest L = 32 run and about 160 ms when aborted early. This is host-specific; `/api/metrics` reports live p50/p95/p99.

## 6. Circuit breaker, router and audit

- **State machine (per link: `alice->verifiers`, `bob->charlie`).** `OPEN → WATCH` on a weak alert; `WATCH → QUARANTINED` when the accumulated evidence in the window is strong enough (Fisher p ≤ 0.01) or after three alerts; any link `→ QUARANTINED` on strong evidence; `WATCH → OPEN` when the window expires. An admin reset needs the admin role **and a reason** and moves `QUARANTINED → RESET_PENDING` (probation). One fully accepted transmission reopens the link; any quantum-evidence alert on probation re-quarantines it. Every transition is logged with actor, time, evidence id, old/new state and policy version (`GET /api/channel/transitions`).
- **Adaptive test allocation.** While a link is on WATCH or probation, each transmission uses twice as many test tokens, so detection power rises where suspicion exists.
- **Quarantine.** Refuses new sends with HTTP 423 (the refusal time is measured). The verifiers drop pending, unaccepted distribution records from that sender. These are software records: no physical Bell pair is destroyed. An **incident record** is signed at the moment of quarantine.
- **Simulated router (`router.py`).** Star topology `alice → QR-1 → bob / charlie` plus the classical `bob → charlie` link. Hop state follows the link (up / degraded / probation / down), with per-hop token counters and dropped-request counts (`GET /api/topology`, drawn on the admin page). It is a routing model only; no fibre is switched.
- **Timing.** Reported separately (`/api/metrics`, p50/p95/p99): channel observation (the simulator run), detection, post-verdict enforcement, incident signing, audit signing, HTTP-423 refusal, and the whole run. Post-verdict enforcement is **not** attack-to-isolation time.
- **Persistence (`store.py`, `data/hedwig.db`).** Link states, the transition log, consumed replay nonces and every signed artifact (exact signed bytes) survive restarts. Distribution records do not; sessions in flight at a restart must be re-sent.
- **Audit records (`hedwig-audit/2`).** Issued automatically for every transmission, incident and reset, in one append-only **hash chain** (each record carries the SHA-256 of the previous signed payload), so a removed or reordered record is detected. A transaction record holds: signer and verifiers, nonce, created/expiry times, message digest (plaintext redacted), outcome and decision path, response and incident id, per-verifier check summary, SHA3-256 digests of each verifier's elimination table and of the keep/forward actions, channel test `k/n`, p₀, α, p-value and bounds, Tier 2 statistics, the per-verifier Hoeffding bounds **with inputs and assumptions**, a model-based fidelity estimate `F = 1 − QBER` (only under the depolarising model; "not reported" when the channel test rejects that model), an assurance level computed from the bounds, the parameters and policy, and disclaimers. The evidence is attached unsigned and bound by the digests.
- **Signatures.** Ed25519 by default (classical, **not post-quantum**). If `dilithium-py` or `liboqs-python` is installed (`pip install -r requirements-pq.txt`), every record is **hybrid-signed** with Ed25519 + ML-DSA-65, and it verifies only if both signatures do. Stripping the ML-DSA signature is detected. `HEDWIG_AUDIT_PQ=off|auto|require`. Keys live in `data/` (git-ignored). `POST /api/audit/rotate-key` retires the active Ed25519 key; retired keys stay in the keyring, so old records keep verifying.
- **Verifying offline** (no trust in the server):
  ```powershell
  # save the keyring from GET /api/audit-public-key as keyring.json, then:
  python tools/verify_audit.py hedwig-audit-TX-XXXX.json --keys keyring.json
  python tools/verify_audit.py chain.json --chain --keys keyring.json          # export of GET /api/audit/chain
  python tools/verify_audit.py cert.json --keys keyring.json --require-pq      # demand the ML-DSA signature
  ```
  `POST /api/audit/verify` returns the same per-check report. Changing any field, the evidence, or the signature list makes verification fail.

## 7. Running, testing, experimenting

```powershell
.\run_v2.bat                       # installs requirements, starts server, opens the three terminals
# or
pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q                                   # unit, blind-detector, API and statistical tests
python experiments/run_trials.py --trials 200 --bits 16 32 64
python experiments/run_trials.py --backend qiskit --trials 30 --bits 32   # same, through Qiskit Aer
python experiments/sweep_tiers.py --trials 200                        # one-tier vs two-tier attribution
python experiments/basis_schedule.py --trials 200 --bits 32           # exploratory: basis schedules
```

CI (`.github/workflows/v2-tests.yml`) runs the test suite, the post-quantum audit tests (with `dilithium-py`) and small seeded runs of all three experiments on every change under `v2/`.

Environment variables:
- `HEDWIG_BACKEND`: `qiskit` or `statevector`
- `HEDWIG_USERS_FILE`: path to the hashed credentials file
- `HEDWIG_AUDIT_KEY`: path to the audit signing key (ML-DSA key and retired keys are stored beside it)
- `HEDWIG_DB`: path to the SQLite state file (default `data/hedwig.db`)
- `HEDWIG_AUDIT_PQ`: `auto` (default: hybrid when a provider is installed), `off`, or `require`

## 8. Review issue mapping

| Issue | Change | Tests |
| :--- | :--- | :--- |
| 1 Labels determined detection | `QDSDetectionEngine.classify(observations, channel_test)` has no scenario input. Verifiers decide independently. Ground truth is attached after detection and hidden from verifier dashboards. | `test_detector_blind.py` |
| 2 Replay was a flag | Random nonce and timestamp are bound in the commitment. A per-verifier consumed-nonce set and clock window; nonces are consumed only on acceptance. The injector re-sends a real package. | `test_replay_binding.py` |
| 3 Tampering was a flag | Canonical context with SHA-256 message digest and a distribution-stage commitment, recomputed from the received payload | `test_replay_binding.py` |
| 4 No trust boundary | Server-side sessions and role checks on pages, APIs and WebSockets; sender taken from the session; unauthorized-verification events; hashed credentials | `test_api.py` |
| 5 QBER configured | Hidden `ChannelModel` separated from observable test-token counts. Qiskit teleportation circuit in the executed path. | `test_teleportation.py`, `test_thresholds.py` |
| 6 Claims outran evidence | One parameter set drives both the decision and the displayed bounds, with inputs, assumptions and required `n` | `test_thresholds.py` |
| 7 Circuit breaker was a label | Link quarantine with refusal, buffer purge and reset; measured latency; signed, verifiable audit records | `test_enforcement_audit.py` |
| 8 No V2 tests | 99 tests, seeded experiments, CI workflow | `tests/`, `experiments/` |

V2.2 (roadmap steps 3–7):

| Roadmap step | Change | Tests |
| :--- | :--- | :--- |
| 3 Message and authorisation hardening | Canonical encoding rules, domain-separated digest, selectable SHA3-512 bound in the commitment, malformed-input rejection, atomic persistent nonce consumption, reset needs role + reason | `test_binding_tier2_schedule.py`, `test_api.py` |
| 4 Safer QCB | WATCH / probation state machine, evidence-strength policy, early abort, adaptive tests, immediate signed incidents, router, persistence, separated timings | `test_enforcement_audit.py`, `test_api.py` |
| 5 Two-tier detector | Tier 2 attribution, `UNDETERMINED_DISTURBANCE`, p-values and Chernoff–KL bound, KL diagnostic, sweep script | `test_binding_tier2_schedule.py`, `experiments/sweep_tiers.py` |
| 6 Q-Cert completeness | `hedwig-audit/2`, automatic issue, per-verifier and symmetrisation digests, bounds with assumptions, model-based fidelity, hash chain, key rotation, hybrid ML-DSA-65 | `test_enforcement_audit.py`, `test_api.py` |
| 7 Exploratory novelty | Random / public-hash / keyed-HMAC basis schedules and a schedule-aware Eve at equal budgets; adaptive test allocation | `test_binding_tier2_schedule.py`, `experiments/basis_schedule.py` |

## 9. Limitations

- This is a simulation: no photonic hardware, and a simplified noise model (depolarising noise plus intercept-resend).
- The binding and commitment are computational (SHA-256), not information-theoretic.
- Forgery bounds assume independent per-copy attacks. Coherent attacks and a dishonest verifier holding both copies of a position are not analysed.
- The message is bound through a classical commitment. A full QDS protocol would sign each message bit with its own quantum signature.
- Distribution records and in-flight sessions are in memory; a restart discards them. Link state, nonces and audit records persist in SQLite (one process; multiple processes rely on SQLite file locking).
- Tier 2 assumes a Pauli-type channel (depolarising, intercept-resend). Coherent or basis-biased attacks could mimic the channel pattern. With few tokens it often abstains; that is reported, not hidden.
- The pure-Python ML-DSA provider (`dilithium-py`) is not side-channel hardened; use `liboqs-python` for anything beyond a demonstration.
- Use `../INNOVATIONS_TEAM_ATHENA_V2.2.md` (corrected claims) instead of the original innovations document for slides and judging.

## 10. Technology stack

Python 3.10+, FastAPI, Uvicorn, WebSockets, Qiskit and Qiskit Aer, NumPy, `cryptography` (Ed25519), optional `dilithium-py` / `liboqs-python` (ML-DSA-65), SQLite (standard library), pytest. The front end uses plain HTML, CSS and JavaScript.
