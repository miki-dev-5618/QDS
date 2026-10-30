# HEDWIG — AI Context Document

> **For AI coding sessions.** Read this before making any change. Then read the
> actual source file(s) relevant to your task before editing anything.

---

## Quick-Start Checklist for AI Agents

1. Read `docs/GEMINI.md` (one-line rules already in your system prompt) and this file.
2. Locate the source module(s) relevant to your task and read them.
3. Trace all callers/callees affected by your change before touching code.
4. Follow existing conventions; do **not** refactor unrelated code.
5. Every new behaviour must be opt-in via a parameter or env var (Rule 3 in `GEMINI.md`).
6. Every new feature needs a test with a fixed seed.
7. Run `pytest -q` after any change and report the actual outcome.
8. No number or claimed result in docs may be invented; all must come from a reproducible script.

---

## 1. Project Overview

**HEDWIG V2.2** is a **simulated** three-party Quantum Digital Signature (QDS)
platform built as a Smart-India Hackathon 2026 submission by Team ATHENA.

It is **entirely a classical-computer simulation**. It uses Qiskit Aer / NumPy
statevectors to model teleportation circuits, quantum noise, and eavesdropping.
No real quantum hardware is involved.

### What it demonstrates

| Capability | Where implemented |
|---|---|
| Bell-state teleportation of Pauli-eigenstate tokens | `src/quantum_engine/teleportation.py` |
| Keep-or-forward symmetrisation (binds Alice) | `src/quantum_engine/symmetrisation.py` |
| Orthogonal-state elimination tables | `src/quantum_engine/elimination.py` |
| Tier 1 channel test + sequential early abort | `src/quantum_engine/channel.py` |
| Tier 2 blind disturbance-pattern attribution | `src/quantum_engine/discriminator.py` |
| Adaptive test-token allocation (C2) | `src/quantum_engine/security.py`, `thresholds.py` |
| Exact binomial threshold calculations (C1) | `src/quantum_engine/thresholds.py`, `verifier.py` |
| Precommitted reserve evidence stage | `src/quantum_engine/binding.py`, `verifier.py` |
| 11 simulated attack injectors (ThreatSuite) | `src/quantum_engine/threats.py` |
| Quantum Circuit Breaker (OPEN/WATCH/QUARANTINED/RESET_PENDING) | `src/quantum_engine/enforcement.py` |
| Fisher combined p-value escalation | `src/quantum_engine/policy.py` |
| Hybrid Ed25519 + ML-DSA-65 Q-Cert audit ledger | `src/quantum_engine/audit.py`, `signers.py` |
| Key providers (software PEM/JSON & SoftHSM2 PKCS#11) | `src/quantum_engine/key_provider.py`, `audit.py` |
| SHA-256 hash-chained audit records | `src/quantum_engine/audit.py`, `store.py` |
| SQLite persistence (circuit-breaker state, nonces, audit chain) | `src/quantum_engine/store.py` |
| FastAPI web UI with role-based sessions and WebSocket broadcast | `server.py`, `auth.py` |
| Docker Compose deployment (App + PostgreSQL 15) & Locust load testing harness | `Dockerfile`, `docker-compose.yml`, `locustfile.py`, `run_experiments_docker_locust.py`, `parse_locust_csv.py` |
| N-verifier extension (2–10 verifiers, direct/chain delivery) — §15 | `roster.py`, `ledger.py`, `verifier.py`, `thresholds.py` |
| Multi-hop routing, link-aware rerouting, edge probes — §16 | `topology.py`, `routing.py`, `multihop.py`, `monitoring.py` |
| `hedwig-client` Python SDK — §14 | `hedwig_client/` |
| IBM QPU 3-qubit teleportation benchmark (protocol NOT on hardware) — §17 | `experiments/hardware/` |

---

## 2. Repository Map

```
QDS/                          # github.com/miki-dev-5618/QDS (line counts below are historical)
├── server.py                 # FastAPI app + all HTTP/WS route handlers
├── auth.py                   # PBKDF2-SHA256 authenticator; role session management (128 lines)
├── users.json                # Hashed demo credentials (DO NOT put real creds here)
├── README.md                 # Full human-readable documentation with Mermaid diagrams
├── N_VERIFIER_EXTENSION.md   # N-verifier design + evaluation (implemented)
├── MULTI_HOP_ROUTING_IMPLEMENTATION.md   # Multi-hop routing implementation notes (implemented 2026-10-30)
├── QDS_N_Verifier_Implementation_Plan.md, QDS_Multi_Hop_Routing_Blueprint.md,
│   QDS_Alternate_Routing_Implementation_and_Visualisation_Guide.md   # Pre-implementation plans (may diverge from code)
├── docs/
│   ├── CONTEXT.md            # This file
│   ├── GEMINI.md             # Hard rules for AI agents (read this first)
│   ├── FOR_DUMMIES.md        # Plain-English beginner guide + viva prep
│   └── PROOF.md, SECURITY_ARGUMENT.md   # Security reasoning notes
├── hedwig_client/, examples/, pyproject.toml   # SDK (§14)
├── Dockerfile, docker-compose.yml, render.yaml, Procfile, runtime.txt   # Deployment
├── locustfile.py, run_experiments_docker_locust.py, parse_locust_csv.py # Load testing
├── requirements-hsm.txt      # Optional PKCS#11 deps
├── requirements.txt          # Core production deps (fastapi, uvicorn, qiskit, cryptography)
├── requirements-pq.txt       # Adds dilithium-py for ML-DSA-65; extends requirements.txt
├── requirements-dev.txt      # Adds pytest, httpx, matplotlib; extends requirements.txt
├── run_v2.bat                # Windows one-click launcher
├── run_experiments.py        # Orchestrates all experiment scripts with a seed; saves manifest
├── data/
│   ├── hedwig.db             # SQLite database (auto-created; do not commit)
│   └── audit_ed25519.pem     # Ed25519 private key (auto-generated; do not commit or leak)
├── src/
│   └── quantum_engine/       # Entire simulation core (also: topology, routing, multihop, monitoring, roster, ledger, key_provider — see §15/§16)
│       ├── __init__.py       # Public API: re-exports all user-facing symbols
│       ├── protocol.py       # TeleportationQDS orchestrator -- main entry point (537 lines)
│       ├── teleportation.py  # Bell-circuit + statevector backends; TeleportJob/Outcome (728 lines)
│       ├── channel.py        # ChannelModel (hidden params); Tier 1 QBER test; early abort (336 lines)
│       ├── symmetrisation.py # Keep-or-forward random swap (73 lines)
│       ├── elimination.py    # OrthogonalEliminationEngine; SYMBOL_MAP
│       ├── binding.py        # SignedContext, SignedPackage, commitment(), reserve_commitment()
│       ├── verifier.py       # VerifierNode; DistributionRecord; VerificationResult (357 lines)
│       ├── detection.py      # QDSDetectionEngine; ThreatClassification; 9-rule decision tree (318 lines)
│       ├── discriminator.py  # tier_two(): Tier 2 attribution (118 lines, self-contained)
│       ├── policy.py         # ResponsePolicy; Fisher escalation; decide() (146 lines)
│       ├── enforcement.py    # ChannelGuard; LinkState; QCB state machine (241 lines)
│       ├── threats.py        # ThreatSuite; ThreatType enum; 11 injectors (302 lines)
│       ├── audit.py          # AuditAuthority; Q-Cert ledger; hash chain; build_record() (394 lines)
│       ├── signers.py        # Ed25519Signer; MLDSA65Signer; pq_provider() (173 lines)
│       ├── store.py          # Store (SQLite); 4 tables: kv, transitions, nonces, audit (160 lines)
│       ├── security.py       # SecurityParameters; threshold models; Hoeffding bounds (319 lines)
│       ├── thresholds.py     # exact_rule(); plan_test_tokens(); plan_reserve() (514 lines)
│       ├── router.py         # SimulatedRouter; star topology via QR-1 relay (75 lines)
│       ├── schedule.py       # RandomSchedule for measurement basis interleaving
│       ├── cloning.py        # Universal/phase-covariant cloner fidelity models
│       ├── qcert.py          # Q-Cert certificate helpers
│       ├── qthb.py           # Quantum Threshold Bound calculations
│       ├── replay.py         # ReplayGuard; per-verifier nonce consumption
│       ├── canonical.py      # canonical_json(); deterministic UTF-8 JSON serialisation
│       ├── transcript.py     # SigningSession, Transcript dataclasses (session state)
│       └── circuit_breaker.py# Stub/helper; main QCB logic is in enforcement.py
├── templates/                # Jinja2 HTML templates
│   ├── login.html            # Multi-role login
│   ├── admin.html            # Alice console (sign, inject attacks, reset circuit breaker)
│   ├── bob.html              # Bob verifier + dishonest-forward trigger
│   ├── charlie.html          # Charlie verifier + cross-check
│   └── routing.html          # Multi-hop routing dashboard
├── static/
│   ├── css/style.css         # Vanilla CSS design system
│   ├── js/app.js             # WebSocket client; dynamic DOM; Chart.js charts
│   └── img/icons.svg         # SVG icon sprites
├── tests/                    # pytest suites (see §10)
│   ├── conftest.py           # Shared fixtures: FakeClock, rng (seed 12345), engine
│   └── test_*.py             # See Section 10 for full list
└── experiments/              # Scientific evaluation harnesses and ablation scripts
    ├── harness.py            # Resumable grid runner (seed x scenario x L x noise)
    ├── make_roc.py           # ROC curves with bootstrapped AUC CI
    ├── ablate_*.py           # Feature ablation studies
    ├── baselines.py          # 11% QBER cutoff baseline comparison
    ├── sweep_*.py            # Parameter sweeps
    ├── run_trials.py         # False lock-out measurement over honest sequences
    ├── n_verifier_eval.py    # N-verifier evaluation -> n_verifier_eval.md/.json
    ├── routing_eval.py       # Primary vs fresh-session failover routing trials
    └── hardware/             # IBM QPU teleportation benchmark (§17)
```

---

## 3. Architecture

### 3.1 The Two Logical Links

The circuit breaker tracks exactly two links (both constants defined in `enforcement.py`):

| Constant | String value | Covers |
|---|---|---|
| `LINK_SIGNER` | `"alice->verifiers"` | Alice distribution path to Bob and Charlie |
| `LINK_FORWARD` | `"bob->charlie"` | Bob classical forwarding path to Charlie |

Quarantining **either** link refuses **all** new transmissions until an admin reset.

### 3.2 Network Topology (from `router.py`)

```
alice --quantum-- QR-1 --quantum-- bob
                    \---quantum-- charlie
bob -----classical-----------    charlie   (forwarded signatures)
```

Hop states mirror link state: `up` (open), `degraded` (watch), `probation` (reset_pending), `down` (quarantined).

This is the default `legacy-star/1` topology. Under N-verifier the star is redrawn per roster, with one classical hop per forwarding edge used. Custom/multi-hop topologies add **edge- and path-scoped** restrictions plus an explicit emergency stop (§16). The legacy star keeps the pooled two-link convention.

### 3.3 Circuit Breaker State Machine (from `enforcement.py`)

```
OPEN --weak alert--> WATCH --Fisher p <= escalate_alpha OR watch_strikes alerts--> QUARANTINED
OPEN/WATCH --strong alert (p <= strong_alpha)--> QUARANTINED
WATCH --window expires, no new alerts--> OPEN
QUARANTINED --admin reset--> RESET_PENDING
RESET_PENDING --one accepted transmission--> OPEN
RESET_PENDING --any quantum-evidence alert--> QUARANTINED
```

`CARRIES_TRAFFIC = {OPEN, WATCH, RESET_PENDING}` — these states allow transmissions.

---

## 4. Critical Workflows

### 4.1 Sign-and-Send: POST /api/sign-and-send

```
POST /api/sign-and-send  (admin session required)
  |
  +-- server.py: validate, build ThreatScenarioConfig, optional ChannelModel
  +-- asyncio.to_thread -> qds_engine.execute_protocol(...)
  |
  +-- protocol.py: TeleportationQDS.execute_protocol()
       |
       +-- [1] distribute(sender, message, n_bits, rng, channel, adversary)
       |       +-- guard.check_open(LINK_SIGNER)  -> raises ChannelQuarantined if blocked
       |       +-- allocation_plan() -> test + reserve budget (observable state only)
       |       +-- generate random Pauli signature [(bit, basis), ...]
       |       +-- SignedContext.new() + commitment() + reserve_commitment()
       |       +-- SymmetrisationManager.perform_symmetrisation_swap()
       |       +-- build slot stream (sig slots + interleaved test slots)
       |       +-- [optionally] ThreatSuite modifies slot stream (attack injection)
       |       +-- loop over blocks -> teleport each slot -> verifier measures
       |       |     +-- channel.estimate_channel_qber()  # Tier 1 running QBER check
       |       |     +-- [early abort if decisive error threshold crossed]
       |       +-- verifiers store DistributionRecord (eliminated states + commitment)
       |       +-- returns SigningSession
       |
       +-- [2] [if channel test passed] reveal(session) -> SignedPackage
       |
       +-- [3] deliver(package, session=session)
       |       +-- guard.check_open(LINK_SIGNER)
       |       +-- verifier.verify(package, "direct") for each verifier
       |       |     +-- binding check (recompute commitment)
       |       |     +-- replay/nonce/timestamp check
       |       |     +-- elimination check (mismatches vs threshold)
       |       |     +-- [if borderline] request reserve -> open_reserve() -> second pass
       |       +-- returns List[VerificationResult]
       |
       +-- [4] assess(transcript, scenario, started_ns)
               +-- QDSDetectionEngine.classify(verifications, channel_test, params)
               |     +-- Tier 1: channel alarm?
               |     +-- Tier 2: tier_two() discriminator (if detection_tiers >= 2)
               |     +-- 9-rule decision tree -> ThreatReport + ThreatClassification
               +-- ResponsePolicy.decide(report) -> ResponseDecision
               +-- ChannelGuard.apply(decision, link, evidence_id)
               +-- AuditAuthority.issue(record, artifact_id) -> signed Q-Cert
               +-- [if QUARANTINED] issue incident cert

  +-- result.to_dict() -> tx  (ground_truth attached AFTER detection)
  +-- SystemState.record(tx)  (in-memory ring buffer, 500 max)
  +-- ConnectionManager.broadcast_transmission(tx) -> WebSocket push to all roles
       +-- view_for(role, tx): admin sees all; bob/charlie never see ground_truth or alice fields
```

### 4.2 Dishonest Bob Forward: POST /api/dishonest-bob-forward

```
POST /api/dishonest-bob-forward  (bob session required)
  +-- ThreatSuite.dishonest_bob_forward(engine, session_id, message, rng)
  |     +-- Bob builds a forged package from his own DistributionRecord
  |     +-- delivers it to Charlie via LINK_FORWARD
  +-- assess() -> detection -> enforcement -> audit  (same pipeline as above)
```

### 4.3 Channel Reset: POST /api/channel/reset

```
POST /api/channel/reset  (admin session required)
  +-- ChannelGuard.request_reset(link, actor, reason)
  |     +-- QUARANTINED -> RESET_PENDING  (persisted to SQLite)
  |     +-- router.sync() updates hop states
  +-- build_reset_record(transitions, actor, reason)
  +-- AuditAuthority.issue(reset_record) -> signed Q-Cert stored in SQLite
  +-- broadcast channel_state event to all WebSocket clients
```

### 4.4 WebSocket Real-Time Updates

- Each role (`admin`, `bob`, `charlie`) connects to `/ws/{role}`.
- Session cookie validated at connection; refused with code 4401 if missing/invalid.
- On connect: `init_sync` event with current state + last 5 transmissions.
- On each new transmission: `new_transmission` pushed to all three roles.
- On channel state changes: `channel_state` pushed to all roles.

---

## 5. Module Responsibilities

### `protocol.py` — `TeleportationQDS`

- Central orchestrator wiring all sub-components at construction time.
- Constructor parameters: `backend` (`"qiskit"` or `"statevector"`), `channel`, `clock`, `store`, `audit`, `policy`, `schedule`.
- `execute_protocol()` runs the full 4-stage pipeline and returns `QDSExecutionResult`.
- `allocation_plan(n_bits)` computes test-token and reserve budget from **observable state only** (link state + `observed_loss`). Never reads the injected scenario.
- `_signer_sessions` (OrderedDict, maxlen 50): Alice reserve state per session.
- All protocol execution is synchronous; the server wraps it in `asyncio.to_thread`.

### `teleportation.py` — Two Backends

| Class | Mechanism | Use |
|---|---|---|
| `QiskitTeleportationBackend` | Qiskit circuit with `if_test` mid-circuit measurement, AerSimulator | Default (`HEDWIG_BACKEND=qiskit`) |
| `StatevectorTeleportationBackend` | 3-qubit NumPy statevector; same gate sequence | Experiments and fast tests |

`TeleportJob` is a frozen dataclass encoding one token's full channel parameters. `sample_channel_events()` samples channel randomness classically so both backends execute the **same** circuit instance.

### `channel.py` — `ChannelModel` and Tier 1

- `ChannelModel` holds **hidden** physical parameters (depolarizing, intercept_rate, etc.). Ground truth only; verifiers never read it.
- `estimate_channel_qber()` performs the observable Tier 1 test: sacrificed test tokens measured in disclosed basis, binomial tail test, optional sequential early abort.
- Early abort fires only on a **decisive** count (`errors > k_strong`) so the p-value remains valid under optional stopping.

### `detection.py` — 9-Rule Decision Tree

Rules applied in strict priority order (first match wins):

1. Tier 1 channel alarm -> `EAVESDROPPING_TAMPERING`
2. No distribution record / sender mismatch -> `IMPERSONATION_ATTACK`
3. Nonce consumed / timestamp stale -> `REPLAY_ATTACK`
4. Forwarded package fails binding or elimination -> `DISHONEST_VERIFIER_FORGERY`
5. Binding fails + elimination fails -> `EXTERNAL_FORGERY`
6. Binding fails + elimination passes -> `MESSAGE_INTEGRITY_VIOLATION`
7. Binding passes + elimination fails:
   - Tier 2 says `signature_inconsistency` -> `REPUDIATION_ATTEMPT`
   - Tier 2 says `channel_disturbance` -> `EAVESDROPPING_TAMPERING`
   - Tier 2 says `undetermined` -> `UNDETERMINED_DISTURBANCE`
   - 7b. Elimination inconclusive -> `INCONCLUSIVE_EVIDENCE`
8. All accepted + some mismatches -> `CHANNEL_NOISE`
9. All accepted + no mismatches -> `BENIGN_AUTHENTIC`

**Critical:** Classical-only rejections (replay, impersonation, message integrity) never escalate the circuit breaker. Enforced by `CLASSICAL_ONLY` set in `policy.py`.

### `discriminator.py` — Tier 2 `tier_two()`

Asks whether signature contradictions exceed what the channel error rate can explain. Uses a conditional binomial test: `m | D ~ Bin(D, pi)`. Completely stateless; takes only verifier observations + channel test result. Returns `TierTwoResult` with attribution: `signature_inconsistency`, `channel_disturbance`, or `undetermined`.

### `policy.py` — `ResponsePolicy`

Default parameters (verified in source):
- `strong_alpha = 1e-3`: immediate quarantine threshold.
- `escalate_alpha = 1e-2`: Fisher-combined escalation threshold.
- `watch_window_s = 900.0`: 15-minute window for accumulating weak evidence.
- `watch_strikes = 3`: fallback counter escalation.
- Escalation rule controlled by env var `ESCALATION` (`fisher` | `fisher_only` | `counter`); default `fisher`.

### `enforcement.py` — `ChannelGuard`

- Thread-safe (RLock). All state transitions are atomic.
- Persists link state and transition log to SQLite via `Store` on every transition.
- Restores link state from SQLite on startup.
- `ChannelQuarantined` exception raised by `check_open()` when any link is quarantined; caught by server to return HTTP 423.

### `audit.py` — `AuditAuthority`

- Certificate format: `hedwig-audit/3` for new records (adds session config/outcome, reveal events, `events_sha3_256`). `hedwig-audit/2` certificates still verify under their original rules.
- Artifact kinds on one append-only chain: `transaction`, `incident`, `link_reset`, `transfer` (one per N-verifier chain forwarding event, linked by `parent_record`).
- Multi-hop: topology/plan/execution commitments are signed. Admin downloads include the route evidence; participant downloads omit it.
- Canonical JSON (`canonical.py`) is the signed payload; `payload_sha256` stored alongside.
- Each record includes `chain.prev_sha256` linking to the previous artifact.
- Evidence (verifier records, channel test) is unsigned but bound by `evidence_digests` inside the signed record.
- Message plaintext is redacted; only domain-separated `message_digest` is stored.

### `signers.py` — Signing

- `Ed25519Signer.load_or_create(path)`: loads PEM private key or generates and persists a new one.
- `MLDSA65Signer.load_or_create(path)`: tries `liboqs` first, then `dilithium-py`; returns `None` if neither installed.
- `pq_provider()` returns `"liboqs"`, `"dilithium-py"`, or `None`.
- A hybrid certificate is valid only when **all** listed signatures verify.

### `store.py` — SQLite Schema (core 4 tables; PostgreSQL when `HEDWIG_DATABASE_URL=postgresql://…`)

Extensions add `sessions` + `verification_events` (N-verifier, insert-only) and stores for topology snapshots, route plans/execution, probe observations, activations and refusals (multi-hop).

- `kv (key TEXT PK, value TEXT)`: generic JSON key-value; key `"links"` stores circuit-breaker link state.
- `transitions`: timestamped log of every circuit-breaker state change.
- `nonces (verifier, channel, nonce PK)`: replay protection; append-only.
- `audit (artifact_id PK, kind, seq UNIQUE, ...)`: append-only Q-Cert chain.

`Store(":memory:")` gives identical behaviour without a file; used in all tests.

### `auth.py` — `Authenticator`

- Sessions: random 256-bit URL-safe tokens, in-memory dict, 8-hour TTL.
- One cookie per role (`hedwig_admin`, `hedwig_bob`, `hedwig_charlie`); allows all three roles from one browser.
- `PBKDF2_ITERATIONS = 200_000` SHA-256.
- Always hashes even for unknown usernames (constant-time behaviour).
- Without `HEDWIG_USERS_FILE`, built-in demo accounts are used with a warning logged.

---

## 6. Data Models

### `SignedContext` (`binding.py`)

```python
session_id: str       # "S-" + 8 random hex bytes
sender: str           # "alice"
verifiers: List[str]  # ["bob", "charlie"]
nonce: str            # random hex
timestamp: float      # time.time() at distribution
message_digest: str   # H("HEDWIG-QDS-v2|message|" + message)
digest_alg: str       # "sha256" or "sha3-512"
version: str          # "HEDWIG-QDS-v2.2"
```

### `QDSExecutionResult` (`protocol.py`)

Top-level result of one protocol run. `to_dict()` produces the transmission JSON pushed over WebSocket. Key fields:

- `transmission_id`: UUID
- `transcript`: internal `Transcript` (session + channel test + verifier results)
- `threat_report`: `ThreatReport` (classification + verdict + evidence_p)
- `enforcement`: dict from `ChannelGuard`
- `ground_truth`: attached **after** detection returns; admin-only via `view_for()`
- `audit_cert`: shallow inline summary; full cert fetched via `/api/audit/{id}`

---

## 7. Environment Variables (Verified in source)

| Variable | Default | Effect |
|---|---|---|
| `PORT` | `8000` | HTTP server port |
| `HOST` | `0.0.0.0` | Bind address |
| `HEDWIG_BACKEND` | `qiskit` | Simulation backend: `qiskit` or `statevector` |
| `HEDWIG_DB` | `data/hedwig.db` | SQLite database path |
| `HEDWIG_DATABASE_URL` | (none) | `postgresql://…` selects PostgreSQL in `store.py` (set by docker-compose) |
| `HEDWIG_TOPOLOGY` | (legacy star) | `demo-multihop` selects the bundled multi-hop demo at startup |
| `HEDWIG_AUDIT_KEY` | `data/audit_ed25519.pem` | Ed25519 private key path |
| `HEDWIG_AUDIT_PQ` | `auto` | ML-DSA-65 mode: `auto`, `require`, `off` |
| `HEDWIG_KEY_PROVIDER` | `software` | Key provider: `software` (file-backed) or `softhsm` (PKCS#11) |
| `HEDWIG_PKCS11_LIB` | (none) | Path to SoftHSM2/PKCS#11 DLL/so |
| `HEDWIG_PKCS11_TOKEN` | `hedwig` | SoftHSM2 token label |
| `HEDWIG_PKCS11_PIN` | (none) | User PIN for SoftHSM2 token |
| `HEDWIG_USERS_FILE` | (none) | Path to hashed credentials JSON |
| `EARLY_ABORT` | `on` | Sequential early abort toggle: `on`/`off`/`true`/`false` |
| `DETECTION_TIERS` | `2` | Detection depth: `1` or `2` |
| `ESCALATION` | `fisher` | Escalation rule: `fisher`, `fisher_only`, `counter` |
| `HEDWIG_NOISE_PROFILE` | (none) | Force default channel: `ibm_fake`, `lossy` |
| `HEDWIG_IBM_MODE` | (none) | IBM channel mode: `calibrated` or `full` |
| `HEDWIG_ETA_LOSS` | `0.1` | Loss fraction when `HEDWIG_NOISE_PROFILE=lossy` |
| `IBM_QUANTUM_TOKEN` / `IBM_QUANTUM_CHANNEL` | (none) / `ibm_quantum_platform` | Hardware benchmark scripts only; never hardcode the token |

---

## 8. API Endpoints (Verified in `server.py`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET/HEAD` | `/health` | None | Liveness check |
| `GET` | `/` | None | Redirect to `/login` |
| `GET` | `/login` | None | Login page |
| `GET` | `/admin`, `/alice` | admin | Alice console |
| `GET` | `/bob` | bob | Bob console |
| `GET` | `/charlie` | charlie | Charlie console |
| `POST` | `/api/login` | None | Returns role cookie |
| `POST` | `/api/logout` | None | Deletes role cookie |
| `GET` | `/api/session` | None | Active usernames per role |
| `POST` | `/api/sign-and-send` | admin | Runs full QDS protocol |
| `POST` | `/api/dishonest-bob-forward` | bob | Simulates dishonest Bob forgery |
| `POST` | `/api/arm-threat` | admin | Sets active threat type for UI |
| `POST` | `/api/channel/reset` | admin | Resets quarantined link; issues signed reset cert |
| `GET` | `/api/channel` | any | QCB state for both links |
| `GET` | `/api/channel/transitions` | admin | Last 100 circuit-breaker transitions + policy |
| `GET` | `/api/topology` | any | Router hop states |
| `GET` | `/api/history` | any | Last 50 transmissions (role-filtered) |
| `GET` | `/api/verification/{tx_id}/{verifier}` | verifier-specific | Verifier own result |
| `GET` | `/api/audit/chain` | admin | Full hash chain (evidence stripped) |
| `GET` | `/api/incidents` | any | Last 50 incident certs (evidence stripped) |
| `GET` | `/api/audit/{artifact_id}` | any | Full or stripped Q-Cert download |
| `POST` | `/api/audit/verify` | None | Independent cert verification |
| `GET` | `/api/audit-public-key` | None | Active and retired public keys |
| `POST` | `/api/audit/rotate-key` | admin | Rotates Ed25519 audit key |
| `GET` | `/api/metrics` | admin | Latency, stats, QCB state, parameters |
| `GET` | `/results` | any | Experiment results page (ROC, ablations, baselines) |
| `GET` | `/api/security-events` | admin | Last 100 security events |
| `GET` | `/api/roster` | admin | Enrolled verifier pool, limits (N-verifier) |
| `GET` | `/api/sessions/{id}/events` | admin | Session roster + durable event history |
| `POST` | `/api/topology` | admin | Activate `{preset:"demo-multihop"}` or `{topology:…}` |
| `GET` | `/api/routing/refusals` | admin | Persisted preflight refusals |
| `GET` | `/api/routing/history` | authorized | Stored route plans/execution (recipient-filtered) |
| `GET` | `/api/sessions/{id}/routes` | authorized | Historical topology, plan, decisions, execution |
| `POST` | `/api/routing/fault` | admin | `attack` / `clear_attack` / `manual` (watch, quarantined) on an edge |
| `POST` | `/api/routing/probe` | admin | Edge probes, 64–4096 fresh tokens per edge |
| `POST` | `/api/routing/emergency` | admin | Emergency stop (`enabled`, reason); not cleared by ordinary reset |
| `WS` | `/ws/{role}` | role cookie | Full-duplex broadcast stream |

---

## 9. Development Setup

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install core dependencies
pip install -r requirements.txt

# (Optional) Install ML-DSA-65 post-quantum signing
pip install -r requirements-pq.txt

# Install development and test tools
pip install -r requirements-dev.txt

# Run the server
python server.py
# Browser: http://localhost:8000

# Windows one-click launcher:
run_v2.bat
```

### Running Tests

```bash
pytest -v                                     # verbose, all suites
pytest -q                                     # quiet fast run
pytest tests/test_enforcement_audit.py -v     # single suite
```

All tests use `Store(":memory:")` and `backend="statevector"` for speed.

### Running Experiments

```bash
python run_experiments.py --seed 2026            # full run (minutes)
python run_experiments.py --quick                # smoke test (~10 s)
python run_experiments.py --seed 2026 --resume   # skip completed steps
```

Outputs land in `experiments/results/`: `raw.jsonl`, `summary.csv`, `manifest.json`, `PPT_NUMBERS.md`.

---

## 10. Test Suite Reference

| File | What it tests |
|---|---|
| `test_teleportation.py` | Bell-pair fidelity; both backends agree |
| `test_cloning.py` | Universal + phase-covariant fidelity bounds |
| `test_detector_blind.py` | Blind threat detection (no ground-truth labels) |
| `test_enforcement_audit.py` | QCB state machine; Q-Cert hash chain integrity |
| `test_noise_readout.py` | Asymmetric readout error model |
| `test_loss.py` | Photon-loss (erasure) channel |
| `test_noise_damping.py` | Amplitude damping channel |
| `test_noise_ibm.py` | IBM fake-backend noise model |
| `test_partial_intercept.py` | Partial intercept-resend (opt-in) |
| `test_ablations.py` | Early-abort and 1-tier/2-tier toggles |
| `test_escalation_ablation.py` | Fisher vs counter escalation |
| `test_adaptive_allocation.py` | Adaptive test-token budget |
| `test_harness.py` | Experiment harness determinism |
| `test_make_roc.py` | ROC generation + AUC bootstrap |
| `test_api.py` | FastAPI endpoints, cookies, role enforcement |
| `test_c1_c2.py` | C1/C2 evidence allocation |
| `test_binding_tier2_schedule.py` | Commitment binding + Tier 2 + schedule |
| `test_elimination_symmetrisation.py` | Elimination table + keep-or-forward |
| `test_replay_binding.py` | Replay guard + nonce persistence |
| `test_thresholds.py` | Exact binomial threshold calculations |
| `test_statistics.py` | Statistical helper functions |
| `test_baselines.py` | QBER cutoff baseline comparisons |
| `test_run_experiments.py` | Experiment runner smoke test |
| `test_n_verifier.py` | N-verifier config, chains, forwarding attacks, transfer records, restart history |
| `test_multihop_routing.py` | Topology identity, rerouting, probes, recovery, loss, route-audit tampering |
| `test_routing_api.py` | Routing endpoints and authorization |
| `test_ibm_hardware.py` | Hardware scripts on local simulator (no token/QPU) |
| `test_sdk.py` | SDK via `httpx.MockTransport` (16 tests) |
| `conftest.py` | `FakeClock`, `rng` (seed 12345), `engine` (statevector, noiseless) |

---

## 11. Coding Conventions

### Naming

- Module-level constants: `UPPER_SNAKE` (e.g., `LINK_SIGNER`, `OPEN`, `QUARANTINED`).
- Dataclasses: `PascalCase`; frozen when immutable (`TeleportJob`, `SignedContext`).
- Private helpers: leading underscore (`_transition`, `_decisive_fail`).
- Test files: `test_<module_or_feature>.py`.

### Module Boundaries (enforced by design)

- `threats.py` imports from `binding`, `channel`, `enforcement`, `transcript` -- by design; injectors must manipulate the simulation.
- `detection.py` never imports `threats.py`. Ground truth is attached **after** `assess()` returns.
- `discriminator.py` is pure statistics: no imports from `enforcement.py`, `policy.py`, or `threats.py`.
- `store.py` imports only standard library.
- `server.py` imports from `auth`, `src.quantum_engine`, and standard library only.

### Error Handling

- `ChannelQuarantined(Exception)`: raised by `ChannelGuard.check_open()`; caught by server to return HTTP 423.
- `NoPackageToReplay(Exception)`: raised when replay injector has no prior accepted package; server sends an honest preamble first.
- `engine_lock` (`asyncio.Lock`): serialises all protocol runs; all `qds_engine` calls in `server.py` must be inside `async with engine_lock`.

### Adding a New Feature

1. Add parameter to the relevant dataclass or function with a default that preserves existing behaviour.
2. If user-facing, expose it as an env var in the appropriate module.
3. Write a test with a fixed seed that fails without the feature and passes with it.
4. If detection/enforcement metrics change, add or update an ablation in `experiments/`.

### Adding a New Attack

1. Add a member to `ThreatType` (str Enum) in `threats.py`.
2. Add a branch in `ThreatSuite` that modifies only what that adversary can touch.
3. Add to the detection decision tree in `detection.py` only if a new observable signature is needed.
4. Add a test in `tests/test_detector_blind.py` and/or a dedicated file.
5. Update the threat catalog in `README.md` with a result from a reproducible script.

---

## 12. Important Constraints and Pitfalls

| Pitfall | Detail |
|---|---|
| **Simulation only** | Never claim physical or information-theoretic security. `audit.py` embeds explicit disclaimers in every certificate. |
| **No ground truth in detection** | `QDSDetectionEngine.classify()` takes no scenario parameter. Ground truth attached to `QDSExecutionResult` only after `assess()` returns. Breaking this invalidates all blind-detection claims. |
| **Classical-only threats never escalate QCB** | `CLASSICAL_ONLY` set in `policy.py` explicitly excludes replay, impersonation, and message integrity from link responses. Changing this enables free DoS. |
| **`engine_lock` must be held** | All `qds_engine` calls in `server.py` must be inside `async with engine_lock`. The engine is not thread-safe for concurrent runs. |
| **Sessions not persisted across restart** | `DistributionRecord`s and `SigningSession`s live only in memory. Pre-restart sessions cannot be verified again. Audit records remain verifiable. |
| **Reserve bounded** | Reserve opens at most `max_reserve_openings` times, enforced inside `VerifierNode.verify()`. Never create new quantum evidence after reveal. |
| **ML-DSA-65 is optional** | `MLDSA65Signer.load_or_create()` returns `None` if no provider installed. Always check for `None`. |
| **`dilithium-py` is not production-safe** | Pure-Python reference; not side-channel hardened. Must be documented as demonstration-only wherever referenced. |
| **Early abort p-value validity** | Early abort valid only because errors only accumulate. Code stops only when `errors > k_strong`. Never weaken this stopping rule. |
| **`canonical.py` must be stable** | `canonical_json()` is the basis for all signatures and hash chains. Do not change its output format for any existing field. |
| **`HEDWIG_USERS_FILE` not set** | Server logs a warning and uses demo credentials. Do not expose beyond localhost without it. |
| **`data/` files must not be committed** | `hedwig.db` and `audit_ed25519.pem` are auto-generated and excluded by `.gitignore`. |
| **One Uvicorn worker only** | Live guards, hidden experimental attacks and quantum evidence are process-local; SQLite/Postgres durability gives no cross-process coordination. |
| **`INVALID_TRANSFER` is classical-only** | Like replay/impersonation, it must never lock a link (anyone can trigger it). |
| **No edge attribution from end-to-end evidence** | Only independent probes (`monitoring.py`) restrict individual edges; session evidence restricts recorded paths. Migration never fabricates edge attribution. |
| **Hardware scope** | Only the isolated teleportation circuit runs on IBM hardware. Never claim the QDS protocol ran on a QPU; cite only real `result_<timestamp>.json` files. |

---

## 13. Instructions for Future AI Coding Sessions

1. **Read before editing.** Read this file, `docs/GEMINI.md`, and the specific source module(s) for your task. Do not guess.

2. **Trace callers and callees.** Before changing a function signature or return type, search for all callers. Before changing a dataclass field, find every `to_dict()`, `from_dict()`, and test that references it.

3. **New behaviour is always opt-in.** Every change that alters detection, enforcement, or protocol behaviour must be gated by a new parameter (default: old behaviour) or environment variable. The Round 1 demo must continue to work unchanged.

4. **Test with a fixed seed.** Every new feature gets a test. Tests involving randomness must use a fixed `np.random.default_rng(seed)`. The shared `rng` fixture uses seed `12345`.

5. **Never invent numbers.** Any claim about detection rate, AUC, QBER, or latency must come from a script in `experiments/` that can be re-run to reproduce the number.

6. **Run `pytest -q` and report actual output.** Do not claim tests pass without running them.

7. **Do not touch `canonical.py` output format.** Existing signed records depend on its exact encoding.

8. **Do not break the ground-truth separation.** `detection.py` must never see `ThreatType` before returning its verdict. `threats.py` must only be imported on the injector side (`protocol.py`) and in tests.

9. **Preserve the `CLASSICAL_ONLY` set.** Replay, impersonation, and message integrity detections must never trigger QCB escalation.

10. **Keep disclaimers.** Any new documentation or comment must not claim real physical security, information-theoretic guarantees beyond the stated model, or hardware results unless a hardware result file exists.

11. **Minimal diffs.** Make the smallest coherent change. Avoid reformatting unrelated code, adding speculative features, or introducing new dependencies without explicit instruction.


---

## 14. Feature E55 — `hedwig-client` Python SDK

### Purpose

`hedwig_client/` is a **synchronous Python SDK** that wraps the HEDWIG REST
API so external scripts and tools can drive the server without a browser.
It does **not** change any server endpoint, response schema, or behaviour.

### New Files (do not break existing tests when editing these)

| File | Role |
|---|---|
| `hedwig_client/__init__.py` | Package root; re-exports `HedwigClient`, models, exceptions |
| `hedwig_client/client.py` | `HedwigClient` — `login`, `sign_and_send`, `get_audit`, `reset_link`, `topology` |
| `hedwig_client/models.py` | `@dataclass TransmissionResult`, `@dataclass AuditCertificate` |
| `hedwig_client/exceptions.py` | `HedwigError` → `AuthError` / `LinkQuarantinedError` / `APIError` |
| `pyproject.toml` | `setuptools.build_meta` build; `httpx>=0.24.0` dep; `pip install -e ".[dev]"` |
| `examples/quickstart.py` | 10-line demo (needs server on `:8000`) |
| `tests/test_sdk.py` | 16 pytest tests via `httpx.MockTransport` (no live server) |

### Exception ↔ HTTP Status Mapping

| HTTP Status | SDK Exception |
|---|---|
| 401 | `AuthError(401, message)` |
| 403 | `AuthError(403, message)` |
| 423 | `LinkQuarantinedError(detail_dict)` |
| other 4xx/5xx | `APIError(status, message)` |

### `HedwigClient` Method ↔ Endpoint Mapping

| Method | HTTP call | Auth required |
|---|---|---|
| `login()` | `POST /api/login` | None |
| `sign_and_send(message, L, scenario, noise_profile)` | `POST /api/sign-and-send` | `admin` |
| `get_audit(artifact_id)` | `GET /api/audit/{artifact_id}` | any |
| `reset_link(reason)` | `POST /api/channel/reset` | `admin` |
| `topology()` | `GET /api/topology` | any |

### Key Design Rules for AI Agents

- **Never change server endpoints or response shapes** to accommodate the SDK.
  Map the existing JSON to `TransmissionResult.from_api()` / `AuditCertificate.from_api()`.
- The `httpx.Client` in `HedwigClient.session` carries cookies automatically;
  do not manage cookies manually.
- `LinkQuarantinedError.detail` holds the **full** server JSON for 423 responses
  (includes `link`, `refusal_us`, etc.).
- `TransmissionResult.raw` preserves the complete server payload for callers
  that need fields not surfaced by the dataclass.
- All SDK tests use `httpx.MockTransport`; they do **not** import `server.py`
  or any quantum-engine module. Keep it that way.

### Demo Commands

```powershell
pip install -e ".[dev]"              # install SDK + dev deps
python examples/quickstart.py        # requires server running on :8000
pytest tests/test_sdk.py -v          # 16 tests, no live server needed
```

---

## 15. N-Verifier Extension (implemented; details in `N_VERIFIER_EXTENSION.md`)

- Optional; omitting the new request fields gives the original Alice + Bob + Charlie flow.
- `POST /api/sign-and-send` extra fields: `n_verifiers` or `roster`, `delivery` (`direct`|`chain`), `max_depth`, `dishonest_verifier`, `forward_alteration` (`message`|`signature`). Invalid configs raise `ConfigurationError` (HTTP 400).
- Pool: `bob, charlie, dave, erin, frank, grace, heidi, ivan, judy, kim`; N = 2–10; `direct` H = 1, `chain` 1 ≤ H ≤ N−1.
- Decision gates chosen: uniform final holder (N > 2; N = 2 keeps keep-or-forward), exact depth limits `k_fr + floor(l·(k_fa−k_fr)/H)` (`thresholds.depth_rule`; legacy `s_l` only under `threshold_policy="legacy"`), immutable linked `transfer` records.
- Transfer depth is derived from the verifier's own record + sender, never from the package; invalid transfers are judged at depth 0 → `INVALID_TRANSFER`.
- Reserve bound is now **per session across all channels**; one forwarded delivery per verifier per session.
- New scenarios: `dishonest_forwarder`, `forward_withheld`, `route_manipulation`, `forward_replay`, `unknown_forwarder` (admin threat cards 10–14).
- Session outcomes: `all_accepted`, `rejected`, `inconclusive`, `incomplete`, `distribution_aborted` (no majority rule).
- Recorded eval (seed 2026, 40 trials): altered package accepted 0/160; planned tokens at L=64 grow linearly (162 → 674 for N=2 → 10). Depth limits only separate from L ≈ 128; UI caps L at 64.
- Bob/Charlie terminals unchanged; extra verifiers are admin-only.

## 16. Multi-Hop Routing (implemented 2026-10-30; details in `MULTI_HOP_ROUTING_IMPLEMENTATION.md`)

| Module | Responsibility |
|---|---|
| `topology.py` | Bounded directed graphs, exactly one signer, immutable; canonical serialization/digest |
| `routing.py` | Deterministic bounded simple-path search; prunes blocked edges; priority OPEN > probation > permitted WATCH, then freshness, cost, edge ID; `RouteUnavailable(ChannelQuarantined)` → HTTP 423; exhausted budget = "incomplete search", not disconnection |
| `multihop.py` | Ordered per-hop channels; one Bell pair per edge attempt; heralded loss ends the token |
| `monitoring.py` | Independent edge probes; round r spends `alpha·6/(pi·r)²`; recovery needs ≥ 1024 surviving probe tests over ≥ 2 rounds after reset |
| `teleportation.py` | Per-hop Bell measurement + Pauli correction for both backends; no intermediate measurement |
| `protocol.py` | Freezes plans, preflights all recipients, rechecks scopes before each block and before reveal; a changed restriction aborts the session |

- Default topology stays `legacy-star/1`; `demo-multihop` = Alice → R1 → R2 → recipients with R3 bypass (supports Bob, Charlie, Dave, Erin).
- Per-hop channel order: loss → interception → Pauli channels → damping → Bell measurement → correction. Per-basis transfer: X `(1−4p/3)·sqrt(1−g)`, Z `(1−4p/3)·(1−g)`, multiplied along the route.
- IBM fake-backend calibration only supports the exact legacy star; custom topologies need `statevector`/`qiskit`.
- Assumptions: honest relays, authenticated classical channels; not a composable security proof.
- Eval: `python experiments/routing_eval.py --trials 10 --seed 2026 --output experiments/routing_results.json`. The checked-in sample (3 trials) is a smoke test only.

## 17. IBM Hardware Benchmark (`experiments/hardware/`)

- Runs only the 3-qubit **deferred-measurement** teleportation circuit (`build_deferred_teleportation_circuit`) for `|0>,|1>,|+>,|->` in one `SamplerV2` job. **Full QDS protocol is NOT run on hardware.**
- `qiskit-ibm-runtime` lives in `experiments/hardware/requirements-hardware.txt`, deliberately not in `requirements.txt`.
- Commands: `run_ibm_teleport.py --dry-run` (local Aer), `--shots N [--backend X]` (QPU), `--job-id` (recover without QPU time); `compare_hw_vs_sim.py result_<ts>.json`. If the fake provider is missing, the comparison falls back to a "generic surrogate" that must not be quoted as device calibration.

## 18. Open Items / Unverified

- Contradiction: README lists 11 core threat scenarios; `N_VERIFIER_EXTENSION.md` says "the original nine scenarios". Not reconciled against `ThreatType`.
- No real hardware result file was verified while these docs were updated; do not quote hardware numbers.
- The live demo URL (`qds.navyaa-dev.me`, Render) appears only in a personal note and is unverified.
- Blueprint/plan docs at the repo root predate implementation; treat the `*_IMPLEMENTATION.md` / `*_EXTENSION.md` files as authoritative.
