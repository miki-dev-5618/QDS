# HEDWIG — Teleportation-Based Quantum Digital Signatures with Threat Detection

**Team ATHENA · Smart India Hackathon 2026 · Problem Statement PS 26141**
*Quantum-Inspired Cyber Threat Detection for Digital Signature Security*

HEDWIG simulates a three-party **quantum digital signature (QDS)** system:
- **Alice** signs a message; **Bob** and **Charlie** verify it independently.
- The signature's quantum tokens travel by **quantum teleportation**, simulated in Qiskit.
- A threat-detection layer decides from the evidence alone whether something went wrong: eavesdropping, forgery, tampering, replay, impersonation, a dishonest verifier, or a signer denying their own signature. It then responds, up to isolating the link, and writes a signed, tamper-evident audit record of every decision.

No AI or machine learning is used. Every decision is a fixed statistical rule whose counts and p-values are shown.

> **Current version: V2.2** (in [`v2/`](v2/)). For the change history see [`v2/V2.2_IMPLEMENTATION_REPORT.md`](v2/V2.2_IMPLEMENTATION_REPORT.md), and for item-by-item status see [`v2/STATUS.md`](v2/STATUS.md). Live deployment: configured for [Render.com](https://render.com) via [`render.yaml`](render.yaml).

---

## Contents

1. [Repository layout](#1-repository-layout)
2. [What you need](#2-what-you-need)
3. [Quick start](#3-quick-start)
4. [Cloud deployment (Render)](#4-cloud-deployment-render)
5. [How it works](#5-how-it-works)
6. [The three dashboards](#6-the-three-dashboards)
7. [Attacks you can simulate](#7-attacks-you-can-simulate)
8. [Detection: two statistical tiers](#8-detection-two-statistical-tiers)
9. [Response: the Quantum Circuit Breaker](#9-response-the-quantum-circuit-breaker)
10. [Audit records (Q-Cert)](#10-audit-records-q-cert)
11. [Demo script for judges](#11-demo-script-for-judges)
12. [Configuration](#12-configuration)
13. [API reference](#13-api-reference)
14. [Testing and experiments](#14-testing-and-experiments)
15. [Measured results](#15-measured-results)
16. [What we claim, and what we don't](#16-what-we-claim-and-what-we-dont)
17. [Troubleshooting](#17-troubleshooting)
18. [Glossary](#18-glossary)

---

## 1. Repository layout

```
QDS/
├── read-jashan.md                     ← this guide
├── render.yaml                        ← Render.com blueprint (auto-detects v2/, sets health check)
├── HEDWIG_V2_Implementation_and_Innovation_Roadmap.md   ← the plan V2.2 implements
├── INNOVATIONS_TEAM_ATHENA_V2.2.md    ← corrected innovation claims (use this for slides)
├── INNOVATIONS_TEAM_ATHENA.md         ← original claims, kept for history (contains unsupported claims)
├── .github/workflows/v2-tests.yml     ← CI: tests, post-quantum tests, experiment smoke runs
├── v1/                                ← earlier prototype (BB84, network daemons, visualiser); not used by V2
└── v2/                                ← the current system
    ├── server.py                      ← FastAPI web server, API, WebSockets
    ├── auth.py                        ← logins, roles, hashed passwords
    ├── Procfile                       ← Render start command (uvicorn 0.0.0.0:$PORT)
    ├── runtime.txt                    ← Python 3.11.10 pin for Render build
    ├── run_v2.bat                     ← one-click Windows launcher
    ├── requirements.txt / -dev.txt / -pq.txt
    ├── src/quantum_engine/            ← the engine (see §5)
    ├── templates/, static/            ← dashboards (HTML/CSS/JS)
    ├── tests/                         ← 150 automated tests
    ├── experiments/                   ← seeded experiments and their results
    ├── tools/verify_audit.py          ← offline audit-record checker
    ├── data/                          ← created at runtime: database and keys (git-ignored)
    ├── README.md                      ← technical reference
    ├── STATUS.md                      ← status per innovation item
    └── V2.2_IMPLEMENTATION_REPORT.md  ← what changed and which problems were solved
```

### Engine modules (`v2/src/quantum_engine/`)

| Module | Role |
| :--- | :--- |
| `teleportation.py` | Bell-state teleportation circuit, run on Qiskit Aer or on an equivalent fast statevector simulator |
| `symmetrisation.py`, `elimination.py` | Keep-or-forward swapping of copies; orthogonal-state elimination and mismatch counting |
| `binding.py`, `canonical.py` | Signing context, message digest, commitment, canonical encoding |
| `protocol.py` | Runs a transmission: distribution stream, early abort, reveal, verification, assessment |
| `verifier.py`, `replay.py` | Bob's/Charlie's independent checks; replay protection |
| `channel.py` | Hidden channel model (noise, eavesdropper, bursts) and the observable Tier 1 channel test |
| `discriminator.py` | Tier 2: channel vs. signer attribution |
| `detection.py` | Blind classifier (never sees the attack label) |
| `security.py` | Thresholds and Hoeffding bounds, with their assumptions |
| `policy.py`, `enforcement.py` | Response policy and circuit-breaker state machine; timing |
| `router.py` | Simulated network router with per-hop state |
| `audit.py`, `signers.py` | Signed, hash-chained audit records; Ed25519 and optional ML-DSA-65 |
| `store.py` | SQLite persistence |
| `threats.py` | Attack injectors, used only to *generate* attacks for demos and experiments |
| `schedule.py` | Measurement-basis schedules (experiment only) |

---

## 2. What you need

| Requirement | Notes |
| :--- | :--- |
| **Python 3.10 or newer** | Developed on 3.13; CI uses 3.11 and 3.12 |
| **pip packages** | `v2/requirements.txt`: FastAPI, Uvicorn, WebSockets, Jinja2, NumPy, Qiskit ≥ 1.0, Qiskit Aer, cryptography |
| For tests | `v2/requirements-dev.txt` (adds pytest, httpx) |
| Optional: post-quantum signatures | `v2/requirements-pq.txt` (adds `dilithium-py`), or install `liboqs-python` |
| A modern browser | Chrome, Edge or Firefox; the three dashboards open in separate tabs |
| OS | Windows (launcher provided), Linux or macOS (start the server manually) |

No GPU, quantum hardware, database server or internet connection is needed. SQLite is part of Python.

---

## 3. Quick start

### Windows, one click
```powershell
cd QDS-main\v2
.\run_v2.bat
```
This installs the requirements, starts the server on `http://127.0.0.1:8000`, and opens the Admin, Bob and Charlie pages.

### Any OS, manual
```bash
cd QDS-main/v2
pip install -r requirements.txt
# optional: hybrid post-quantum audit signatures
pip install -r requirements-pq.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```
Then open these pages:
- <http://127.0.0.1:8000/admin>
- <http://127.0.0.1:8000/bob>
- <http://127.0.0.1:8000/charlie>

### Demo logins (localhost only)

| Page | Username | Password |
| :--- | :--- | :--- |
| `/admin` (Alice, the signer) | `admin` | `admin2026` |
| `/bob` | `bob` | `quantum2026` |
| `/charlie` | `charlie` | `quantum2026` |

Each role has its own session cookie, so one browser can be signed in as all three. **Before running anywhere other than your own machine**, create real accounts:
```powershell
python auth.py add-user users.json alice admin
python auth.py add-user users.json bob bob
python auth.py add-user users.json charlie charlie
$env:HEDWIG_USERS_FILE = "users.json"
```

### Starting from a clean state
All state lives in `v2/data/`:
- `hedwig.db` holds link states, used nonces and audit records;
- `audit_ed25519.pem*` holds the signing keys.

To reset everything, stop the server and delete `data/hedwig.db`. If you delete the key files too, every existing audit record becomes unverifiable.

---

## 4. Cloud deployment (Render)

The repository is fully configured for one-click deployment to [Render.com](https://render.com) via the [`render.yaml`](render.yaml) blueprint.

### What's included

| File | Purpose |
| :--- | :--- |
| [`render.yaml`](render.yaml) | Render blueprint: root dir = `v2`, build command, start command, health check at `/health` |
| [`v2/Procfile`](v2/Procfile) | `web: uvicorn server:app --host 0.0.0.0 --port $PORT` |
| [`v2/runtime.txt`](v2/runtime.txt) | `python-3.11.10` — pins to a version with pre-built `qiskit-aer` wheels (avoids C++ build timeout) |
| `/health` endpoint | Returns `{"status": "ok", "version": "2.2"}` — used by Render's health probe |

### Deploy steps

1. Push the repo to GitHub (already done on the `new-new-feat` branch).
2. Log into [Render.com](https://render.com) → **New + → Web Service**.
3. Connect the repo. Render auto-detects `render.yaml` and fills in the settings.
4. *(Optional)* Set environment variables in the Render dashboard:
   - `HEDWIG_USERS_FILE` — upload a `users.json` created with `auth.py add-user` (if not set, demo credentials are used with a warning)
   - `HEDWIG_AUDIT_PQ` — `off` / `auto` / `require` (default `auto`)
5. Click **Deploy**.

> [!WARNING]
> The `data/` folder is **git-ignored** and ephemeral on Render's free tier. Link states and audit records are lost on each redeploy or restart unless you attach a Render Disk or use an external database. Use the service for demos; for persistent audit trails, run locally or on a paid plan with a mounted disk.

### Environment variables for Render

| Variable | Render default | Notes |
| :--- | :--- | :--- |
| `PORT` | Set by Render | The app reads this automatically via `os.environ.get("PORT", 8000)` |
| `HEDWIG_BACKEND` | `qiskit` | Use `statevector` for faster responses (no Qiskit overhead) |
| `HEDWIG_USERS_FILE` | *(unset)* | Demo accounts active if not set |
| `HEDWIG_DB` | `v2/data/hedwig.db` | Point to a mounted disk path for persistence |
| `HEDWIG_AUDIT_PQ` | `auto` | `off` recommended unless you add `dilithium-py` to `requirements.txt` |

---

## 5. How it works

### 4.1 The protocol in five steps

```
 ALICE (signer)                         BOB                        CHARLIE
     │ 1. prepare random quantum states │                            │
     │    (|0⟩ |1⟩ |+⟩ |−⟩), one copy    │                            │
     │    per verifier                   │ ◄── keep-or-forward ──►    │
     │                                   │    (symmetrisation swap)    │
     │ 2. TELEPORT each copy + secret test tokens (interleaved stream) │
     │ ════════ Bell pair + Bell measurement + X^m2 Z^m1 ═══════════► │
     │                                   │ measure in own basis;       │
     │                                   │ record the state ruled out  │
     │                                   │ ("elimination table")       │
     │   test tokens checked block by block → STOP EARLY if decisive   │
     │ 3. commitment C = H(context ‖ signature ‖ r) ─────────────────► │ stored
     │                                                                  │
     │ 4. REVEAL: message, context, signature, r  (only if not aborted)│
     │ ───────────────────────────────────────────────────────────────► │
     │                                   │ 5. VERIFY independently:    │
     │                                   │  record exists? addressed?  │
     │                                   │  fresh nonce/time?          │
     │                                   │  mismatches ≤ limit?        │
     │                                   │  digest & commitment match? │
```

1. **Preparation.** For each signature position Alice picks a random state from `{|0⟩, |1⟩, |+⟩, |−⟩}`. Each verifier receives a copy. Bob and Charlie randomly keep or swap copies (*symmetrisation*), so a dishonest Alice cannot target one verifier.
2. **Teleportation and measurement.** Each copy is teleported through a Bell pair: a Bell measurement, two classical bits, then an `X^m2 Z^m1` correction. The verifier measures it in a random basis. The outcome rules out one state, which is recorded in the verifier's **elimination table**. **Test tokens** are mixed into the stream at secret positions. Their states are disclosed afterwards, so errors on them measure the channel's error rate (QBER).
3. **Commitment.** Alice sends each verifier a hash commitment binding the *context* (session, sender, verifiers, nonce, timestamp, message digest) to the signature. The message itself can be any length.
4. **Reveal.** Alice sends the message, context, signature and blinding value, but only if the channel test passed.
5. **Verification.** Bob and Charlie each check the package on their own. A genuine signature almost never matches a state they ruled out. A forged one does about ¼ of the time. The commitment check catches any change to the message or context.

### 4.2 After verification: assess → respond → record

```
 verifier observations ──► BLIND DETECTOR ──► verdict (accept / reject + reason + p-values)
 + channel test            Tier 1 + Tier 2          │
                                                     ▼
                                    RESPONSE POLICY: none / watch / quarantine
                                                     │
                                                     ▼
                           CIRCUIT BREAKER (per link) + ROUTER hop states
                                                     │
                                                     ▼
                    SIGNED AUDIT RECORD (+ incident record if quarantined), hash-chained
```

The attack you choose in the admin console drives an **injector** only. The detector's input is only what the verifiers saw, and a test enforces that it never receives the attack label. The label is attached afterwards so the dashboards and experiments can score the detector.

### 4.3 The simulation layer
- **Qiskit Aer** runs the real teleportation circuit, with mid-circuit measurement and classical feed-forward. This is the default in the live app.
- A **3-qubit statevector** simulator runs the identical gate sequence faster. It is used by tests and experiments, and tests check that both backends agree.
- The hidden `ChannelModel` contains depolarising noise, an intercept-resend eavesdropper and optional noise bursts. It drives the simulation, but **no verifier or detector ever reads it**.

---

## 6. The three dashboards

| Page | Who | What you see and can do |
| :--- | :--- | :--- |
| **Admin / Alice** `/admin` | Signer and operator | Compose and sign a message, choose the signature length L (16–64), and arm an attack. Watch transmissions arrive with verdict, p-values, Tier 2 attribution, response, and audit/incident links. Link states (OPEN / WATCH / QUARANTINED / PROBATION), the **router diagram**, the latency breakdown, the **audit-chain check** and the **incident list**. Reset links (a reason is required). Security event log. |
| **Bob** `/bob` | Verifier 1 | His own verdict, every check with pass/fail, elimination table vs. revealed signature, bounds with assumptions, Tier 1 / Tier 2 / response cards, and a download link for the signed record. He can act as a **dishonest Bob** and forward a forged signature to Charlie. |
| **Charlie** `/charlie` | Verifier 2 | The same, including checks of packages forwarded by Bob |

A banner on every page shows any link that is not OPEN, with the reason, the incident id or evidence strength, and what happens next.

---

## 7. Attacks you can simulate

Choose one in the admin console before sending:

| Attack | What the injector does | How it is caught | Typical response |
| :--- | :--- | :--- | :--- |
| `authentic` | Nothing; light channel noise | — (accepted) | none |
| `eve_forgery` | Replaces the signature with random guesses | Elimination mismatches **and** commitment mismatch | quarantine |
| `eve_intercept` | Eve intercept-resends every travelling qubit | Tier 1 channel alarm (often an **early abort**), or Tier 2 channel attribution | quarantine / watch |
| `message_tampering` | Changes the message after signing | Message digest ≠ committed digest | reject only |
| `repudiation` | Dishonest Alice sends Charlie inconsistent states | Her own committed signature contradicts the distributed states; Tier 2 attributes it to the signer, or says "undetermined" | quarantine / watch |
| `replay` | Re-sends a previously accepted package | Nonce already used | reject only |
| `impersonation` | A rogue sender claims to be Alice | No distribution record for that sender | reject only |
| `dishonest_bob` (also a button on Bob's page) | Bob forges a signature from his own records and forwards it | Charlie's stricter forwarded-signature check plus commitment | quarantine of `bob->charlie` |

"Reject only" attacks never lock a link. Anyone can send garbage, so letting that lock the link would let an outsider shut out the honest signer.

---

## 8. Detection: two statistical tiers

**Tier 1 — channel test.** The disclosed test tokens give `k` errors out of `n`. The alarm fires if `k` exceeds the smallest threshold with `P(Binomial(n, e0) > threshold) ≤ α`, with `e0 = 2%` honest QBER and `α = 0.01`. The dashboard shows `k/n`, the exact p-value, the exact false-alarm level, and the Chernoff–KL bound beside it.

**Elimination check (per verifier).** A signature is accepted if its mismatches are at most `floor(s · n)`. The limit `s` sits between the honest mismatch rate (`e0/2`) and the forger's minimum rate (1/6–1/4). A stricter limit applies to direct delivery than to forwarded delivery. Hoeffding bounds for this rule are shown with their inputs and assumptions.

**Tier 2 — who caused the contradictions?** Tier 2 applies when the elimination check fails but the commitment is fine, which is ambiguous between channel trouble and a dishonest signer. Channel noise causes test-token errors at rate `q` and signature contradictions at rate `q/2`. So, given the total `D` of both, the contradiction count follows Binomial(D, π) with `π = (n/2)/(t + n/2)`, whatever `q` is.
- **Too many contradictions** (p ≤ 0.05) → **signer / forger** (`REPUDIATION_ATTEMPT`)
- else **test errors elevated** (p ≤ 0.10) → **channel** (`EAVESDROPPING_TAMPERING`, via Tier 2)
- else → **`UNDETERMINED_DISTURBANCE`**: still rejected, but the system does not pretend to know why

Tier 2 never rejects a signature by itself; it only explains a rejection. A KL-divergence figure is shown as a diagnostic.

---

## 9. Response: the Quantum Circuit Breaker

Each link (`alice->verifiers` and `bob->charlie`) has its own state:

```
          weak alert                       more weak evidence (Fisher p ≤ 0.01) or 3 alerts
  OPEN ─────────────► WATCH ───────────────────────────────────────────────► QUARANTINED
   ▲  ◄──────────────   │  (window expires, 15 min)                              │   ▲
   │                    └───────── strong alert (p ≤ 0.001) ─────────────────────┤   │ any quantum
   │   one clean transmission                                                    │   │ alert
   └──────────────────────────── RESET_PENDING (probation) ◄── admin reset ──────┘   │
                                         └───────────────────────────────────────────┘
```

- **Strong vs weak** is decided by the evidence p-value: how unlikely the observation is for an honest run.
- **Evidence accumulation:** weak alerts within 15 minutes are combined with Fisher's method.
- **WATCH and probation** keep the link working, but with **twice the test tokens** (adaptive test allocation).
- **QUARANTINED** refuses new sends (HTTP 423). Pending unaccepted records from that sender are purged; these are software records, since there are no physical qubits. A signed **incident record** is created immediately, and the router shows the hops as *down*.
- **Resetting** needs the admin role and a written reason. It is signed into the audit chain, and the link goes on **probation** rather than straight back to OPEN.
- **Sequential early abort:** the stream is sent in four blocks. Once test-token errors are decisive, the rest is never sent, which saves 33–46% of tokens on attacked links.
- **Timing** is measured and reported separately: channel observation, detection, enforcement, incident signing, audit signing, refusal and the whole run (`/api/metrics`).
- **Persistence:** link states, the transition log, used nonces and audit records survive a server restart.

---

## 10. Audit records (Q-Cert)

Every transmission, incident and reset produces a record at the moment it happens. Download one from any dashboard, or with `GET /api/audit/{id}`.

**What a transaction record contains**
- The signer, the verifiers, nonce, and created/expiry times.
- The message digest; the plaintext is **not** included.
- The verdict, how it was decided, and the evidence p-value.
- The response and incident id.
- Each verifier's checks, plus SHA3-256 digests of its elimination table and of the keep/forward actions.
- The channel test (`k/n`, p₀, α, p-value, bounds) and the Tier 2 statistics.
- The actual forgery, false-reject and repudiation bounds, with their inputs and assumptions.
- A fidelity estimate valid only under the stated noise model (otherwise "not reported").
- An assurance level computed from the bounds, and disclaimers.

**Tamper evidence**
- Records form a **hash chain**; each one includes the hash of the previous one, so deleting or reordering a record is detected.
- The evidence is attached and bound by the digests; changing it is detected.

**Signatures**
- Ed25519 by default. This is classical and **not** post-quantum.
- With `requirements-pq.txt` installed, every record is **hybrid-signed with Ed25519 + ML-DSA-65** (NIST FIPS 204). It verifies only if both signatures do, and removing the post-quantum signature is detected.
- Keys can be rotated; old records stay verifiable.

**Verifying without trusting the server**
```powershell
# 1. save the keyring from http://127.0.0.1:8000/api/audit-public-key as keyring.json
python tools/verify_audit.py hedwig-audit-TX-XXXXXXXX.json --keys keyring.json
python tools/verify_audit.py chain.json --chain --keys keyring.json      # chain export from /api/audit/chain
python tools/verify_audit.py cert.json --keys keyring.json --require-pq  # insist on ML-DSA-65
```
The tool exits with 0 if valid and 1 if invalid, and prints each individual check.

---

## 11. Demo script for judges

Use **L = 32 or 64**; L = 16 is deliberately shown to be weak.

1. **Honest transaction.** Arm `authentic` and send. On Bob's page show the checks, the elimination table, Tier 1 `k/n` and p-value, and the bounds with assumptions. Download the audit record and run `tools/verify_audit.py` on it.
2. **Tampering.** Arm `message_tampering` and change one character. The rejection comes from the digest/commitment check, with zero quantum contradictions, and the link stays OPEN because this is a classical rejection.
3. **Forgery.** Arm `eve_forgery`. Show the mismatches in the elimination table. The link is quarantined, and an incident appears in the admin list.
4. **Eavesdropping.** Reset with a reason, then arm `eve_intercept`. Show the early abort ("stream stopped after N/M tokens"), the Tier 1 p-value and the quarantine. Try another send and show the HTTP 423 refusal and the router hop going *down*. Reset with a reason and show *probation*, then send honestly to reopen the link.
5. **Noise vs attack.** Send honest messages at L = 16 until one is rejected. It is labelled `UNDETERMINED_DISTURBANCE` and the link only goes on WATCH. Then show the experiment tables (§14), including honest false-rejection rates.
6. **Audit chain.** Press **Verify chain**. Every transaction, incident and reset is signed and linked.

---

## 12. Configuration

| Environment variable | Default | Meaning |
| :--- | :--- | :--- |
| `HEDWIG_BACKEND` | `qiskit` | `qiskit` (real circuit) or `statevector` (faster) |
| `HEDWIG_USERS_FILE` | *(unset → demo accounts)* | Hashed credentials file created with `auth.py add-user` |
| `HEDWIG_DB` | `v2/data/hedwig.db` | SQLite state file |
| `HEDWIG_AUDIT_KEY` | `v2/data/audit_ed25519.pem` | Audit signing key (the ML-DSA key and retired keys are stored beside it) |
| `HEDWIG_AUDIT_PQ` | `auto` | `auto` = hybrid when a provider is installed · `off` · `require` = refuse to start without one |

Protocol parameters are in `SecurityParameters` (`security.py`), and response parameters in `ResponsePolicy` (`policy.py`):

| Parameter | Value |
| :--- | :--- |
| Assumed honest QBER `e0` | 0.02 |
| Tier 1 α | 0.01 |
| Immediate-quarantine level | 0.001 |
| Tier 2 α₂ / β | 0.05 / 0.10 |
| Freshness window | 120 s |
| Watch window | 900 s |
| Escalation | Fisher p ≤ 0.01 or 3 alerts |
| Minimum test tokens | 16 |
| Stream blocks | 4 |
| Digest | `sha256` (or `sha3-512`) |

---

## 13. API reference

All routes except login and the public audit-key/verify routes need a signed-in session. Roles are checked on the server.

| Method and path | Role | Purpose |
| :--- | :--- | :--- |
| `POST /api/login`, `POST /api/logout?role=` | — | Session management |
| `POST /api/sign-and-send` | admin | Run one transmission (`message_text`, `n_bits`, `threat_type`, `tampered_text`) |
| `POST /api/arm-threat` | admin | Set the injector scenario shown in the UI |
| `POST /api/dishonest-bob-forward` | bob | Bob forwards a forged signature to Charlie |
| `POST /api/channel/reset` | admin | Body `{"reason": "...", "link": optional}`; quarantined → probation |
| `GET /api/channel`, `/api/channel/transitions` | any / admin | Link states; transition log and policy |
| `GET /api/topology` | any | Router hops and link states |
| `GET /api/history` | any | Recent transmissions (verifiers never see the attack label) |
| `GET /api/verification/{tx}/{verifier}` | that verifier | Its own verification (other attempts are logged as security events) |
| `GET /api/audit/{id}` | any | Stored record for a transaction, incident (`INC-…`) or reset (`RST-…`); `?evidence=false` to strip evidence |
| `GET /api/audit/chain` | admin | Whole chain plus the server-side chain check |
| `GET /api/incidents` | any | Signed incident records |
| `POST /api/audit/verify` | public | Per-check verification report against the server keyring |
| `GET /api/audit-public-key` | public | Keyring (active and retired keys), post-quantum status |
| `POST /api/audit/rotate-key` | admin | Retire the active Ed25519 key |
| `GET /api/metrics` | admin | Latency intervals, stats, policy, parameters, backend |
| `GET /api/security-events` | admin | Failed logins, forbidden requests, unauthorised verification attempts |
| `WS /ws/{role}` | that role | Live updates |

---

## 14. Testing and experiments

```bash
cd v2
pip install -r requirements-dev.txt
python -m pytest tests -q                         # 150 pass

python experiments/run_trials.py --trials 200 --bits 16 32 64       # detection, response, early abort, lock-outs
python experiments/sweep_tiers.py --trials 200                      # one-tier vs two-tier attribution
python experiments/basis_schedule.py --trials 200 --bits 32         # basis-schedule security experiment
python experiments/run_trials.py --backend qiskit --trials 30 --bits 32   # same engine through Qiskit
```

The tests cover:
- teleportation correctness on both backends;
- that the detector is blind to attack labels (checked by inspecting the source);
- binding and replay;
- Tier 2 cases;
- every circuit-breaker transition;
- persistence across restarts;
- early abort and the router;
- audit contents, tampering, key rotation, hybrid signatures and the chain;
- the whole HTTP API, including authorisation.

CI runs all of this, plus smoke runs of the three experiments, on every change under `v2/`.

Each experiment writes a Markdown table and a JSON file into `v2/experiments/`. All experiments are seeded (seed 2026), so results are reproducible.

---

## 15. Measured results

Seed 2026, 200 trials per cell, statevector backend, honest noise p = 0.01. Brackets are 95% confidence intervals.

| | L = 16 | L = 32 | L = 64 |
| :--- | :-- | :-- | :-- |
| Honest runs wrongly rejected | 3.0% [1.4, 6.4] | 0% [0, 1.9] | 0% [0, 1.9] |
| Honest runs that lock the link | 0% | 0% | 0% |
| Honest 10-run sequences that ever lock the link | 4.0% [2.0, 7.7] | 0% | 0% |
| Forgery / tampering / replay / impersonation caught | 100% | 100% | 100% |
| Dishonest Bob caught (quantum check alone) | 100% (88%) | 100% (95.5%) | 100% (98.5%) |
| Eavesdropping caught (labelled correctly) | 98.5% (91%) | 100% (98.5%) | 100% (100%) |
| Eavesdropping stopped early (tokens saved) | 28.5% (33%) | 76.5% (39%) | 97.5% (46%) |
| Dishonest signer caught (labelled / undetermined) | 98.5% (36.5% / 61.5%) | 98.5% (90.5% / 7.5%) | 100% (100% / 0%) |

**Basis-schedule experiment** (L = 32). Deriving the verifiers' measurement bases publicly from the message lets an eavesdropper drive the forgery's contradiction rate from 0.23 to 0.005, defeating the quantum check. The channel test and the commitment still stop it. A secret-keyed schedule performs like random bases. HEDWIG therefore keeps random bases.

**Timing** depends on the machine. Detection takes about 60–380 µs. Qiskit channel observation takes about 320 ms per honest L = 32 run, and about 160 ms when stopped early.

Full tables:
- [`v2/experiments/results.md`](v2/experiments/results.md)
- [`v2/experiments/sweep_tiers.md`](v2/experiments/sweep_tiers.md)
- [`v2/experiments/basis_schedule.md`](v2/experiments/basis_schedule.md)

---

## 16. What we claim, and what we don't

**We claim**
- A working three-party teleportation QDS simulation with independent verifiers.
- Blind, evidence-based detection with published counts, p-values and assumptions.
- A two-tier discriminator that attributes cause, or abstains.
- An evidence-driven circuit breaker with controlled recovery.
- Automatic, hash-chained, offline-verifiable audit records, with optional hybrid post-quantum signatures.
- Every number above, which comes from seeded, reproducible experiments.

**We do not claim**
- **Information-theoretic security end to end.** The message commitment and audit signatures are computational.
- **False-alarm rates of 10⁻⁶.** That needs thousands of tokens or millions of trials. Our bounds are illustrative finite-sample bounds, not a composable proof, and they do not cover coherent attacks.
- **Physical results.** This is a simulation; nothing here says anything about real photonic hardware.
- **"Zero-knowledge" records.** They disclose their evidence.
- **"Post-quantum" signing** unless an ML-DSA-65 signature is present and verifies.

See [`INNOVATIONS_TEAM_ATHENA_V2.2.md`](INNOVATIONS_TEAM_ATHENA_V2.2.md) for the corrected innovation claims and the list of removed claims.

---

## 17. Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `ModuleNotFoundError: qiskit_aer` (or another package) | `pip install -r v2/requirements.txt` |
| Dashboards redirect to the login page | Log in for that role; each role has its own session |
| Every send returns **HTTP 423** | The link is quarantined, possibly from an earlier run, since state persists. Use **Reset links** on the admin page and enter a reason. |
| Link stays on WATCH / PROBATION | Expected: send an honest transmission (probation), or wait out the 15-minute window (WATCH) |
| Honest sends at L = 16 sometimes rejected | Expected (about 3%). Use L ≥ 32 for demos. |
| Sends are slow (about 0.3–0.5 s) | That is the Qiskit simulator. Set `HEDWIG_BACKEND=statevector` for speed. |
| Records show only Ed25519 | No ML-DSA provider is installed: `pip install -r v2/requirements-pq.txt` and restart |
| Old audit records fail to verify | The key files in `data/` were deleted or replaced. Keep them; use `/api/audit/rotate-key` to change keys safely. |
| Want a completely fresh start | Stop the server and delete `v2/data/hedwig.db` (keep the key files if old downloaded records must stay verifiable) |
| Port 8000 already in use | `python -m uvicorn server:app --port 8001` |

---

## 18. Glossary

| Term | Meaning |
| :--- | :--- |
| **QDS** | Quantum digital signature: a signature whose unforgeability rests on quantum measurement rather than only on hard maths problems |
| **Teleportation** | Transferring a qubit's state using a shared Bell pair, a Bell measurement, and two classical bits |
| **Elimination table** | For each copy, the one state the verifier's measurement ruled out; a genuine signature almost never equals it |
| **Symmetrisation** | Random keep-or-swap of copies between Bob and Charlie, so the signer cannot treat them differently |
| **QBER** | Quantum bit error rate, estimated from the disclosed test tokens |
| **Test tokens** | Sacrificed tokens at secret positions, used only to measure the channel |
| **Commitment** | A hash, sent in advance, that binds the message context and signature so that neither can be changed later |
| **p-value** | How likely an observation at least this extreme would be if everything were honest; small means suspicious |
| **Fisher's method** | A standard way to combine several p-values into one |
| **WATCH / QUARANTINED / PROBATION** | Circuit-breaker states: suspicious but working / blocked / reopened on trial |
| **Early abort** | Stopping the transmission as soon as the test-token errors already prove an alarm |
| **Hash chain** | Each audit record includes the hash of the previous one, so removals are detectable |
| **ML-DSA-65** | NIST's standard post-quantum digital signature (FIPS 204) |
| **L** | Signature length, i.e. the number of signature positions (16, 32 or 64 in the UI) |
