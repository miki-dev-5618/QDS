# HEDWIG — Teleportation-Based Quantum Digital Signatures with Threat Detection

**Team ATHENA**  
*Quantum-Inspired Cyber Threat Detection for Digital Signature Security*

---

## 🌟 Executive Summary

**HEDWIG** is a three-party **Quantum Digital Signature (QDS)** and cyber-threat mitigation platform engineered with **Qiskit quantum teleportation**, **two-tier blind statistical threat detection**, an **adaptive quantum circuit breaker**, and **tamper-evident, hybrid post-quantum audit certification (Q-Cert)**.

- **Alice (Signer)** signs an arbitrary-length message using quantum state tokens transmitted via simulated quantum teleportation.
- **Bob & Charlie (Verifiers)** independently verify the signature via orthogonal state elimination tables and keep-or-forward symmetrisation.
- **Threat Detection Layer:** An evidence-driven classifier detects eavesdropping, quantum forgery, message tampering, replay attacks, impersonation, repudiation, and dishonest verifiers without machine learning or prior attack labels.
- **Quantum Circuit Breaker (QCB):** Automatically quarantines corrupted quantum links upon detecting anomalies, enforces probationary recovery, and cuts off eavesdroppers dynamically via sequential early abort.
- **Q-Cert Audit Trail:** Emits append-only, SHA-256 hash-chained audit records signed with **Ed25519** and NIST FIPS 204 **ML-DSA-65 (Post-Quantum Dilithium)** for offline independent verification.

```
+---------------------------------------------------------------------------------------------------------+
|                                      HEDWIG PROTOCOL PIPELINE                                           |
|                                                                                                         |
|  [ Alice (Signer) ]                                                                                     |
|       |                                                                                                 |
|       | 1. Prepare Quantum Tokens & Secret Test States                                                  |
|       | 2. Teleport via Bell Pairs (Qiskit Aer / Statevector) =====> [ Bob & Charlie Verifiers ]       |
|       | 3. Send Context Commitment (SHA-256 / SHA3-512)              * Symmetrisation Keep/Forward Swap |
|       |                                                             * Random Basis Elimination Table    |
|       | 4. Channel Test & Sequential Early Abort Check              * Independent Verification Checks   |
|       | 5. Reveal Signature & Blinding Nonce                                      |                     |
|       +---------------------------------------------------------------------------+                     |
|                                                                                   |                     |
|                                                                                   v                     |
|                                                                   [ Blind Detection Engine ]            |
|                                                                   * Tier 1: Binomial Channel QBER       |
|                                                                   * Tier 2: Disturbance Attribution     |
|                                                                                   |                     |
|                                                                                   v                     |
|                                                                   [ Quantum Circuit Breaker (QCB) ]     |
|                                                                   * OPEN / WATCH / QUARANTINE / PROBATION|
|                                                                   * Fisher's Method Escalation          |
|                                                                                   |                     |
|                                                                                   v                     |
|                                                                   [ Q-Cert Audit Ledger ]               |
|                                                                   * SHA-256 Hash Chain                  |
|                                                                   * Ed25519 + ML-DSA-65 Hybrid Signing  |
+---------------------------------------------------------------------------------------------------------+
```

---

## 📑 Table of Contents

1. [System Architecture & Protocol Design](#1-system-architecture--protocol-design)
2. [Repository Structure & Codebase Overview](#2-repository-structure--codebase-overview)
3. [Prerequisites & System Requirements](#3-prerequisites--system-requirements)
4. [Step-by-Step Setup & Installation](#4-step-by-step-setup--installation)
5. [Live Dashboards & Web Interface](#5-live-dashboards--web-interface)
6. [Simulated Threat Catalog & Detection Mechanics](#6-simulated-threat-catalog--detection-mechanics)
7. [Mathematical Foundation & Statistical Detection](#7-mathematical-foundation--statistical-detection)
8. [Quantum Circuit Breaker & Incident Response](#8-quantum-circuit-breaker--incident-response)
9. [Q-Cert Audit Chain & Post-Quantum Signatures](#9-q-cert-audit-chain--post-quantum-signatures)
10. [Step-by-Step Demo Script for Judges](#10-step-by-step-demo-script-for-judges)
11. [Configuration & Environment Variables](#11-configuration--environment-variables)
12. [REST API & WebSocket Reference](#12-rest-api--websocket-reference)
13. [Automated Testing & Empirical Benchmarks](#13-automated-testing--empirical-benchmarks)
14. [Submission Hygiene & Clean Repo Checklist](#14-submission-hygiene--clean-repo-checklist)
15. [Troubleshooting & FAQ](#15-troubleshooting--faq)
16. [Glossary](#16-glossary)

---

## 1. System Architecture & Protocol Design

### 1.1 The Five-Step Protocol Execution

```
ALICE (Signer)                               BOB (Verifier 1)               CHARLIE (Verifier 2)
     │                                              │                                 │
     │ 1. State Prep: {|0⟩, |1⟩, |+⟩, |−⟩}          │                                 │
     │    Two copies per signature position         │ ◄──── Keep-or-Forward Swap ───► │
     │                                              │      (Symmetrisation)           │
     │ 2. Teleportation Stream (Qiskit Bell Pairs)  │                                 │
     │ ════════════════════════════════════════════►│                                 │
     │                                              │ Measure in random basis         │
     │                                              │ Build Elimination Table         │
     │    Interleaved secret test tokens checked    │                                 │
     │    block-by-block (Early Abort if QBER high) │                                 │
     │                                              │                                 │
     │ 3. Send Context Commitment:                  │                                 │
     │    C = H(Context ‖ Signature ‖ Nonce ‖ Salt) │                                 │
     │ ────────────────────────────────────────────►│ (Stored before reveal)          │
     │                                              │                                 │
     │ 4. Reveal Phase (Only if channel tests pass):│                                 │
     │    Send Message, Context, Signature & Salt   │                                 │
     │ ────────────────────────────────────────────►│                                 │
     │                                              │ 5. Independent Verification:    │
     │                                              │    * Freshness (Nonce/Time)     │
     │                                              │    * Mismatches ≤ Threshold     │
     │                                              │    * Commitment & Digest Match  │
```

1. **State Preparation & Symmetrisation:**
   For signature length $L$, Alice prepares pairs of random Pauli eigenstates $\{|0\rangle, |1\rangle, |+\rangle, |-\rangle\}$. Bob and Charlie execute random keep-or-forward swaps so Alice cannot predict which verifier holds which physical state, preventing selective forgery.
2. **Teleportation & Elimination:**
   Tokens travel across simulated Bell channels $(|\Phi^+\rangle = \frac{|00\rangle+|11\rangle}{\sqrt{2}})$ with Bell-state measurements and classical feed-forward Pauli corrections ($X^{m_2} Z^{m_1}$). Verifiers measure received qubits in random bases ($\{|0\rangle,|1\rangle\}$ or $\{|+\rangle,|-\rangle\}$) and record the orthogonal state ruled out.
3. **Commitment Binding:**
   Alice publishes a cryptographically bound commitment $C = \text{Hash}(\text{Context} \parallel \text{Signature} \parallel \text{Salt})$ where Context specifies version, session ID, sender, recipient verifiers, nonce, expiry timestamp, and domain-separated message digest.
4. **Channel Testing & Early Abort:**
   Secret test tokens interleaved in the stream are revealed. If error counts exceed the threshold in early stream blocks, transmission aborts immediately to conserve quantum bandwidth and isolate malicious channels.
5. **Independent Verification:**
   Verifiers evaluate mismatch rates against Hoeffding security limits $s_a$ (direct delivery) and $s_v$ (forwarded delivery), recompute context digests, and cross-reference commitments.

---

## 2. Repository Structure & Codebase Overview

```
QDS/
├── server.py                      ← FastAPI web application, REST API & WebSocket server
├── auth.py                        ← Authentication, role-based access control, PBKDF2 hashing
├── render.yaml                    ← Render.com cloud deployment blueprint
├── Procfile                       ← Production process launcher
├── runtime.txt                    ← Python 3.11.10 runtime specification
├── run_v2.bat                     ← One-click Windows launch script
├── requirements.txt               ← Core production dependencies
├── requirements-dev.txt           ← Development & testing suite (pytest, httpx)
├── requirements-pq.txt            ← Post-quantum signature provider (ML-DSA-65 / Dilithium)
├── README.md                      ← Master technical documentation & guide
├── STATUS.md                      ← Feature checklist & innovation status
├── V2.2_IMPLEMENTATION_REPORT.md  ← Detailed architectural changelog & implementation report
│
├── src/quantum_engine/            ← Core Quantum & Security Engine
│   ├── teleportation.py           ← Qiskit Aer & Statevector quantum teleportation circuits
│   ├── channel.py                 ← Quantum channel simulation (depolarising noise, Eve intercept)
│   ├── symmetrisation.py          ← Keep-or-forward swap logic between verifiers
│   ├── elimination.py             ← Orthogonal measurement elimination & mismatch counting
│   ├── binding.py                 ← Canonical context serialization & commitment generation
│   ├── canonical.py               ← RFC-compliant deterministic JSON serialization
│   ├── protocol.py                ← End-to-end transmission orchestrator with early abort
│   ├── verifier.py                ← Independent Bob/Charlie verification engines
│   ├── replay.py                  ← Nonce cache, sliding-window replay protection
│   ├── security.py                ← Statistical thresholds, Hoeffding & Chernoff bounds
│   ├── discriminator.py           ← Tier 2 disturbance attribution (Channel vs. Signer)
│   ├── detection.py               ← Blind threat detection engine
│   ├── policy.py                  ← Circuit breaker rules & Fisher's p-value combination
│   ├── enforcement.py             ← Circuit breaker state machine & incident triggering
│   ├── circuit_breaker.py         ← Per-link quantum circuit breaker controller
│   ├── router.py                  ← Star topology quantum router simulation
│   ├── signers.py                 ← Ed25519 & ML-DSA-65 cryptographic signing engines
│   ├── audit.py                   ← Q-Cert tamper-evident hash-chained audit engine
│   ├── store.py                   ← SQLite persistent state management
│   ├── threats.py                 ← Threat injection harnesses (simulation only)
│   └── schedule.py                ← Basis scheduling & security evaluation
│
├── static/                        ← Front-End Assets
│   ├── css/                       ← Modern glassmorphic styles & design tokens
│   └── js/                        ← Real-time dashboard clients & WebSocket handlers
├── templates/                     ← Jinja2 HTML5 Dashboards (admin.html, bob.html, charlie.html, login.html)
├── tests/                         ← Comprehensive Automated Test Suite (150 test cases)
├── experiments/                   ← Reproducible Seeded Experiment Suites & Data
└── tools/                         ← Standalone Audit Verifier (verify_audit.py)
```

---

## 3. Prerequisites & System Requirements

| Requirement | Details |
| :--- | :--- |
| **Operating System** | Windows 10/11, Ubuntu 20.04+, Debian 11+, macOS 12+ |
| **Python Version** | Python 3.10, 3.11, 3.12, or 3.13 (Tested on 3.11 & 3.13) |
| **Hardware** | Standard modern CPU, 4 GB RAM (No quantum hardware or GPU required) |
| **Database** | Embedded SQLite3 (Included with standard Python) |
| **Web Browser** | Chrome, Edge, Firefox, or Safari with WebSocket support |

---

## 4. Step-by-Step Setup & Installation

### Option A: Windows (One-Click Automated Launcher)

Double-click `run_v2.bat` or run:
```powershell
.\run_v2.bat
```
*This installs all requirements, initializes the SQLite database, launches the FastAPI server at `http://127.0.0.1:8000`, and opens the Admin, Bob, and Charlie dashboards.*

---

### Option B: Manual Setup (Windows / Linux / macOS)

1. **Clone the Repository & Navigate to Root:**
   ```bash
   git clone https://github.com/miki-dev-5618/QDS.git
   cd QDS
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate

   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt

   # (Optional) Install Post-Quantum Cryptography support:
   pip install -r requirements-pq.txt

   # (Optional) Install Test & Dev tools:
   pip install -r requirements-dev.txt
   ```

4. **Launch the FastAPI Server:**
   ```bash
   python -m uvicorn server:app --host 127.0.0.1 --port 8000
   ```

5. **Access the Dashboards:**
   - **Admin / Alice Console:** [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
   - **Bob Verifier Dashboard:** [http://127.0.0.1:8000/bob](http://127.0.0.1:8000/bob)
   - **Charlie Verifier Dashboard:** [http://127.0.0.1:8000/charlie](http://127.0.0.1:8000/charlie)

---

### Option C: Cloud Deployment (Render.com)

The repository includes a ready-to-deploy [`render.yaml`](render.yaml) blueprint:
1. Connect your repository to **Render.com**.
2. Create a new **Web Service** using the blueprint.
3. Render automatically detects Python 3.11, builds dependencies, and runs `uvicorn server:app --host 0.0.0.0 --port $PORT` with health checks at `/health`.

---

### 4.1 Demo Accounts & Authentication

| Role | Default Username | Default Password | Description |
| :--- | :--- | :--- | :--- |
| **Admin / Alice** | `admin` | `admin2026` | Message composition, threat injection, link resets |
| **Bob** | `bob` | `quantum2026` | Verifier 1, dishonest forwarding |
| **Charlie** | `charlie` | `quantum2026` | Verifier 2, forwarded verification |

*Each role uses isolated `HttpOnly`, `SameSite=Strict` cookies (`hedwig_admin`, `hedwig_bob`, `hedwig_charlie`), enabling simultaneous multi-party sessions in a single browser.*

**Creating Production Users:**
```bash
python auth.py add-user users.json alice admin
python auth.py add-user users.json bob bob
python auth.py add-user users.json charlie charlie
export HEDWIG_USERS_FILE="users.json"
```

---

## 5. Live Dashboards & Web Interface

```
+-----------------------------------------------------------------------------------------------+
| HEDWIG QDS SECURE COMM SUITE                    [ Link: OPEN ] [ Circuit Breaker: Active ]   |
+-----------------------------------------------------------------------------------------------+
|  ADMIN (Alice) CONSOLE           |  BOB (Verifier 1)               |  CHARLIE (Verifier 2)    |
|  - Compose & Sign Payload        |  - Verification Verdict (Pass)  |  - Forwarded Verification|
|  - Arm Threat Scenario           |  - Elimination Table Visualizer |  - Elimination Table     |
|  - Quantum Router Topology       |  - Tier 1 & Tier 2 Diagnostics  |  - Security Bounds Card  |
|  - Circuit Breaker Controller    |  - Download Signed Q-Cert Audit |  - Dishonest Bob Warning |
|  - Hash Chain Ledger Inspection  |  - Action: Dishonest Forward    |  - Download Audit Record |
+-----------------------------------------------------------------------------------------------+
```

- **Admin Console (`/admin`):** Allows the operator (Alice) to input message text, adjust quantum token length ($L \in \{16, 32, 64\}$), arm attack injectors, monitor real-time router link states, review incident logs, and trigger administrative link resets.
- **Bob's Terminal (`/bob`):** Displays Bob's verification decision, elimination matrix, binomial channel tests, and signed Q-Cert certificate. Provides a **Dishonest Bob Forward** button to test forged forwarding to Charlie.
- **Charlie's Terminal (`/charlie`):** Independently evaluates direct signatures from Alice or forwarded payloads from Bob with specialized threshold limits.

---

## 6. Simulated Threat Catalog & Detection Mechanics

HEDWIG includes 8 realistic threat simulation scenarios:

| Attack Scenario | Injected Mechanism | Observable Evidence | System Verdict & Response |
| :--- | :--- | :--- | :--- |
| **`authentic`** | Honest transmission under typical depolarising channel noise ($p=0.01$). | $k \le \text{Threshold}$, Mismatches $\le \lfloor s_a n \rfloor$. | **ACCEPTED** (Link: `OPEN`) |
| **`eve_forgery`** | Adversary replaces Alice's quantum signature with random states. | Massive elimination mismatches ($\approx 25\%$) + commitment mismatch. | **EXTERNAL_FORGERY** (Immediate `QUARANTINE`) |
| **`eve_intercept`** | Eve intercept-resends Bell qubits during teleportation. | Disclosed test tokens show elevated QBER ($\approx 25\%$). Early abort triggered. | **EAVESDROPPING_TAMPERING** (`QUARANTINE`) |
| **`message_tampering`**| Classical message content modified in transit after signing. | Recomputed message digest $\neq$ committed context digest. | **MESSAGE_INTEGRITY_VIOLATION** (Reject; Link remains `OPEN`) |
| **`repudiation`** | Dishonest Alice sends orthogonal states to Charlie to deny her signature. | Commitment holds, but signature contradicts distributed elimination states. | **REPUDIATION_ATTEMPT** (`QUARANTINE` / `WATCH`) |
| **`replay`** | Adversary re-sends a previously accepted signature payload. | Session nonce found in consumed nonce replay registry. | **REPLAY_ATTACK** (Reject; Link remains `OPEN`) |
| **`impersonation`** | Rogue party attempts verification without a valid distribution record. | Missing session distribution mapping in verifier memory. | **IMPERSONATION_ATTACK** (Reject; Link remains `OPEN`) |
| **`dishonest_bob`** | Bob tampers with a signature and forwards it to Charlie. | Fails Charlie's forwarded threshold $s_v$ and commitment validation. | **DISHONEST_VERIFIER_FORGERY** (Quarantine `bob->charlie`) |

---

## 7. Mathematical Foundation & Statistical Detection

### 7.1 Statistical Thresholds & Bounds

Let $e_0 = 0.02$ denote the baseline honest channel QBER, and $p_{\min} = 1/6$ the minimum theoretical mismatch rate of an unauthorized verifier.

- **Direct Acceptance Threshold ($s_a$):**
  $$s_a = \mu_h + \frac{p_{\min} - \mu_h}{3} \quad \text{where } \mu_h = \frac{e_0}{2}$$
- **Forwarded Acceptance Threshold ($s_v$):**
  $$s_v = \mu_h + \frac{2(p_{\min} - \mu_h)}{3}$$

**Finite-Sample Hoeffding Security Bounds:**
- **False Rejection Probability:**
  $$P(\text{False Reject}) \le \exp\left(-2 (s_a - \mu_h)^2 n\right)$$
- **Forgery Acceptance Probability:**
  $$P(\text{Forgery Accepted}) \le \exp\left(-2 (p_{\min} - s_a)^2 n\right)$$
- **Repudiation Bound:**
  $$P(\text{Repudiation}) \le 2 \exp\left(-\frac{(s_v - s_a)^2 n}{2}\right)$$

### 7.2 Two-Tier Blind Threat Discrimination

1. **Tier 1 (Binomial Channel Test):** Evaluates test token errors $k$ out of $n$ against Binomial distribution $B(n, e_0)$ at significance level $\alpha = 0.01$.
2. **Tier 2 (Disturbance Attribution):** Given total errors $D = e_{\text{test}} + m_{\text{sig}}$, computes conditional contradiction probability $\pi = \frac{n/2}{t + n/2}$:
   - If $P(B(D, \pi) \ge m) \le 0.05 \implies$ **Signer Inconsistency / Repudiation**
   - Else if $P(B(t, e_0) \ge e) \le 0.10 \implies$ **Channel Disturbance / Eavesdropping**
   - Else $\implies$ **`UNDETERMINED_DISTURBANCE`** (abstains from false attribution).

---

## 8. Quantum Circuit Breaker & Incident Response

The Quantum Circuit Breaker (QCB) manages link state transitions deterministically:

```
          Weak Alert (p ≤ 0.05)            Fisher Combined p ≤ 0.01 or 3 Alerts
  OPEN ───────────────────────────► WATCH ──────────────────────────────────────► QUARANTINED
   ▲   ◄───────────────────────────   │  (15-min Window Decay)                         │   ▲
   │                                  └──────── Strong Alert (p ≤ 0.001) ──────────────┤   │
   │                                                                                   │   │ Any
   │   1 Clean Transmission                                                            │   │ Alert
   └─────────────────────────────── RESET_PENDING (Probation) ◄── Admin Reset (Reason) ┘   │
                                             └─────────────────────────────────────────────┘
```

- **Fisher's Method for Evidence Accumulation:**
  Combinative test statistic: $-2 \sum_{i=1}^k \ln(p_i) \sim \chi^2_{2k}$
- **Adaptive Test Allocation:** While in `WATCH` or `PROBATION`, the system automatically doubles the number of test tokens allocated to future transmissions.
- **Sequential Early Abort:** Streams are evaluated in 4 blocks. Malicious channels with high QBER abort after 1 or 2 blocks, saving **33% to 46% of quantum bandwidth**.

---

## 9. Q-Cert Audit Chain & Post-Quantum Signatures

Every transmission, circuit breaker isolation, and administrator reset is permanently sealed into an immutable, hash-chained ledger:

```
[ Audit Record N-1 ] ── SHA-256 Hash ──► [ Audit Record N ] ── SHA-256 Hash ──► [ Audit Record N+1 ]
  - Payload Digest                         - Prev Record Hash                      - Prev Record Hash
  - Verifier Elimination Tables            - Payload Digest                        - Payload Digest
  - Statistical P-Values & Bounds          - Verifier Observations                 - Incident Details
  - Hybrid Signature:                      - Hybrid Signature:                     - Hybrid Signature:
    * Ed25519 (Classical)                    * Ed25519 (Classical)                   * Ed25519 (Classical)
    * ML-DSA-65 (NIST FIPS 204 PQ)           * ML-DSA-65 (NIST FIPS 204 PQ)          * ML-DSA-65 (NIST FIPS 204)
```

### Independent Offline Verification Tool

Audit certificates can be verified independently without connecting to the server:
```bash
# 1. Download active public keyring from running server:
curl http://127.0.0.1:8000/api/audit-public-key -o keyring.json

# 2. Verify a single transaction record:
python tools/verify_audit.py hedwig-audit-TX-XXXXXXXX.json --keys keyring.json

# 3. Verify the complete hash chain integrity:
python tools/verify_audit.py chain.json --chain --keys keyring.json

# 4. Enforce strict Post-Quantum ML-DSA-65 verification:
python tools/verify_audit.py hedwig-audit-TX-XXXXXXXX.json --keys keyring.json --require-pq
```

---

## 10. Step-by-Step Demo Script for Judges

To showcase the system during Hackathon presentations, follow this recommended walkthrough (use token length **$L = 32$ or $64$**):

1. **Honest Signature Demonstration:**
   - On `/admin`, select $L = 32$, keep threat as `authentic`, and click **Sign & Teleport Signature**.
   - Switch to `/bob`: show green **VERIFIED** badge, 0 elimination mismatches, and binomial channel confidence.
   - Click **Download Audit Certificate (Q-Cert)** and run `tools/verify_audit.py` in terminal to prove cryptographic authenticity.
2. **Message Tampering Detection:**
   - On `/admin`, select `message_tampering` and enter modified text.
   - Show on `/bob` that the message digest mismatch is flagged instantly while quantum links remain `OPEN` (preventing denial-of-service lockout).
3. **Quantum Forgery & Circuit Breaker Quarantine:**
   - On `/admin`, arm `eve_forgery` and submit.
   - Show elimination table contradictions ($\approx 25\%$), immediate detection of `EXTERNAL_FORGERY`, and automatic transition to **QUARANTINED** (HTTP 423 block on subsequent sends).
4. **Eavesdropping Intercept & Early Abort:**
   - In Admin console, perform an administrative reset with reason `"Clearing test incident"`.
   - Arm `eve_intercept` and submit.
   - Highlight the **Sequential Early Abort** notice (*"Stream aborted after Block 2/4"*), demonstrating 39%+ token conservation under active cyber attack.
5. **Post-Quantum Audit Chain Verification:**
   - In the Admin console, click **Verify Audit Chain**.
   - Show that all transaction records, incidents, and administrative resets form a continuous, untampered SHA-256 hash chain with dual Ed25519 and ML-DSA-65 signatures.

---

## 11. Configuration & Environment Variables

| Variable | Default Value | Options | Description |
| :--- | :--- | :--- | :--- |
| `PORT` | `8000` | Integer | Application HTTP port |
| `HEDWIG_BACKEND` | `qiskit` | `qiskit`, `statevector` | Quantum simulation engine backend |
| `HEDWIG_USERS_FILE` | *(None)* | Path to JSON | Path to PBKDF2 hashed credentials file |
| `HEDWIG_DB` | `data/hedwig.db`| Path to SQLite DB | Persistent database file path |
| `HEDWIG_AUDIT_KEY` | `data/audit_ed25519.pem`| Path to PEM | Master audit signing key location |
| `HEDWIG_AUDIT_PQ` | `auto` | `auto`, `off`, `require`| Post-quantum ML-DSA-65 signature policy |

---

## 12. REST API & WebSocket Reference

| Method & Endpoint | Auth Role | Description |
| :--- | :--- | :--- |
| `POST /api/login` | Public | Authenticates user and sets role-scoped session cookie |
| `POST /api/logout` | Public | Invalidates active user session |
| `POST /api/sign-and-send` | Admin | Initiates QDS generation, teleportation, and verification |
| `POST /api/arm-threat` | Admin | Configures active threat injection scenario |
| `POST /api/dishonest-bob-forward` | Bob | Triggers forged forwarded signature transmission to Charlie |
| `POST /api/channel/reset` | Admin | Resets quarantined link to probation (Requires mandatory reason) |
| `GET /api/topology` | Any | Returns real-time quantum router and link state graph |
| `GET /api/history` | Any | Fetches historical transmissions (Hides ground-truth attack labels) |
| `GET /api/verification/{tx}/{verifier}`| Verifier | Retrieves verifier-specific measurement and elimination records |
| `GET /api/audit/{id}` | Any | Retrieves signed Q-Cert audit certificate |
| `GET /api/audit/chain` | Admin | Exports full cryptographic audit chain with validity check |
| `GET /api/audit-public-key` | Public | Keyring endpoint with active and retired public keys |
| `POST /api/audit/verify` | Public | Server-side offline certificate verification endpoint |
| `GET /api/metrics` | Admin | Performance, latency breakdown (p50/p95/p99), and throughput |
| `GET /api/security-events` | Admin | Security audit log (failed logins, forbidden queries) |
| `WS /ws/{role}` | Role-Specific | Full-duplex WebSocket stream for real-time UI updates |

---

## 13. Automated Testing & Empirical Benchmarks

### 13.1 Running the Automated Test Suite

The test suite includes **150 automated tests** covering quantum teleportation fidelity, blind threat discrimination, replay defenses, circuit breaker transitions, and hybrid cryptographic signatures:

```bash
python -m pytest tests -v
```

### 13.2 Empirical Benchmark Results

*Evaluated with seed 2026, 200 trials per cell on Statevector backend ($p = 0.01$ channel noise, 95% Wilson confidence intervals):*

| Metric / Scenario | $L = 16$ | $L = 32$ | $L = 64$ |
| :--- | :--- | :--- | :--- |
| **Honest False Rejection Rate** | 3.0% [1.4, 6.4] | **0.0% [0.0, 1.9]** | **0.0% [0.0, 1.9]** |
| **Honest Single-Run False Quarantine** | **0.0%** | **0.0%** | **0.0%** |
| **Eve Forgery Detection Rate** | **100.0%** | **100.0%** | **100.0%** |
| **Dishonest Bob Caught (Overall)** | **100.0%** | **100.0%** | **100.0%** |
| *(Quantum Elimination Check Alone)* | 88.0% | 95.5% | 98.5% |
| **Eve Intercept Caught & Identified** | 98.5% (91.0%) | **100.0% (98.5%)** | **100.0% (100.0%)** |
| **Sequential Early Abort Bandwidth Saved** | 28.5% (33% tokens) | **76.5% (39% tokens)**| **97.5% (46% tokens)**|
| **Repudiation Caught & Attributed** | 98.5% (36.5% / 61.5%)| **98.5% (90.5% / 7.5%)**| **100.0% (100.0% / 0%)**|

---

## 14. Submission Hygiene & Clean Repo Checklist

Before final submission to the hackathon portal, verify the repository cleanliness:

- [x] **No hardcoded secrets or sensitive keys** in git history (All keys generated dynamically in `data/` and git-ignored).
- [x] **No compiled bytecode artifacts** (`__pycache__`, `.pyc`, `.pytest_cache` excluded in `.gitignore`).
- [x] **All 150 automated tests pass** (`python -m pytest tests -q`).
- [x] **Redundant/Duplicate files cleaned up**:
  - `message.md` & `read-jashan.md` are consolidated into this master `README.md`.
  - Stale `v1/` legacy prototype files and temporary scratch files (`1.json`, `PPT GAP.md`) can be safely archived/removed.

---

## 15. Troubleshooting & FAQ

- **Q: Why does the dashboard show HTTP 423 (Locked)?**  
  *A:* A link was quarantined due to a detected attack. Click **Reset Links** in `/admin`, provide a mandatory reason, and submit an honest transmission to return the link to `OPEN`.
- **Q: Why are L=16 honest transmissions occasionally rejected (~3%)?**  
  *A:* Finite-sample binomial variance causes occasional statistical overlap at small signature lengths. The system classifies these as `UNDETERMINED_DISTURBANCE` and places the link on `WATCH` rather than immediate quarantine. Use $L \ge 32$ for high assurance.
- **Q: How to reset the database and start completely fresh?**  
  *A:* Stop the server and delete `data/hedwig.db`.

---

## 16. Glossary

- **QDS (Quantum Digital Signatures):** Signatures offering unforgeability based on the fundamental laws of quantum physics rather than computational hardness.
- **Bell Pair ($|\Phi^+\rangle$):** Maximally entangled two-qubit quantum state used as a resource channel for quantum teleportation.
- **Quantum Teleportation:** Technique to transfer an unknown quantum state using a shared Bell pair and classical transmission.
- **Symmetrisation:** Random swapping of quantum copies between verifiers to prevent the signer from treating verifiers unequally.
- **Elimination Table:** Verifier record of orthogonal states ruled out by quantum measurements.
- **QCB (Quantum Circuit Breaker):** Automated multi-state security mechanism enforcing adaptive testing, link quarantine, and controlled probation.
- **ML-DSA-65:** NIST FIPS 204 standard Module-Lattice-Based Post-Quantum Digital Signature Algorithm (Dilithium).
