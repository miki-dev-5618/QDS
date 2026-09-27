# HEDWIG V2: Quantum Digital Signature (QDS) & Threat Detection Framework

**Team ATHENA | Smart India Hackathon (SIH 2026)**  
**Problem Statement:** PS 26141 — Quantum-Inspired Cyber Threat Detection for Digital Signature Security

---

## 1. Overview
HEDWIG V2 is an interactive, multi-party secure communication application backed by a physics-accurate **Teleportation-based Quantum Digital Signature (QDS)** system and a **deterministic cyber-threat detection engine**.

It demonstrates:
- **No AI / No Machine Learning**: 100% deterministic decision rules grounded in quantum physics (No-Cloning Theorem, Heisenberg Uncertainty Principle) and projective measurement theory.
- **Bell-State Teleportation**: Distribution of signature tokens via Bell states $|\Phi^+\rangle$ with classical Pauli feed-forward corrections ($X^{m_2} Z^{m_1}$).
- **Orthogonal State Elimination**: Verifiers construct tables of impossible states through projective measurements in Pauli $Z$ and $X$ bases.
- **Keep-or-Forward Symmetrisation**: Verifiers randomly swap token copies to mathematically eliminate signer repudiation and dishonest verifier forgery.
- **Full Threat Injection Studio**: Alice/Admin can arm and inject 8 realistic cyber and quantum attacks on demand.
- **Chernoff-Hoeffding Security Proofs**: Evaluates information-theoretic security bounds $P_{forge} \le \exp(-2\Delta^2 L)$ in real time.

---

## 2. Participant Terminology & Roles

| Node | Portal URL | Credentials | Responsibilities |
| :--- | :--- | :--- | :--- |
| **Alice (Admin / Signer)** | `/admin` or `/alice` | `admin` / `admin2026`<br/>`alice` / `quantum2026` | Message composer, bit depth selector ($L=16, 32, 64$), Pauli eigenstate generator, Threat Injection Studio, live channel telemetry. |
| **Bob (Verifier 1)** | `/bob` | `bob` / `quantum2026` | Primary verifier; receives teleported tokens, performs symmetrisation swap, measures & eliminates states, displays verification verdict. Can simulate Dishonest Bob forward. |
| **Charlie (Verifier 2)** | `/charlie` | `charlie` / `quantum2026` | Independent auditor; holds cross-symmetrised tokens, independently verifies Alice's signatures, and detects Dishonest Bob counterfeits or Alice repudiation. |

---

## 3. Threat Injection Suite (Armable in Alice/Admin Console)

1. **Authentic Baseline**:
   - Honest Bell state teleportation, noise-free orthogonal state elimination.
   - Outcome: **Bob: VERIFIED** (0 errors) | **Charlie: VERIFIED** (0 errors).
2. **Eve Classical Forgery**:
   - External adversary intercepts classical revelation and injects random Pauli state guesses.
   - Outcome: **QUENCHED (~25% orthogonal state contradictions)**.
3. **Dishonest Bob Attack**:
   - Bob attempts to forge Alice's signature to Charlie using Bob's partial eliminated state table.
   - Outcome: **Charlie catches the forgery** because Bob does not possess Charlie's symmetrised states.
4. **Eve MITM Channel Intercept**:
   - Adversary taps quantum channel, measuring qubits mid-transit and collapsing superpositions.
   - Outcome: **Spikes QBER $> 25\%$**, tripping the physical Chernoff security bound.
5. **Plaintext Message Tampering**:
   - Adversary modifies the plaintext message payload in transit while the quantum signature remains unchanged.
   - Outcome: **INTEGRITY REJECTED (Hash / token binding mismatch)**.
6. **Alice Repudiation**:
   - Alice generates asymmetric quantum states between Bob and Charlie to attempt selective denial.
   - Outcome: **QUENCHED** via Keep-or-Forward cross-symmetrisation discrepancy.
7. **Replay Attack**:
   - Stale signature re-broadcast with expired timestamp or duplicate nonce.
   - Outcome: **REJECTED** by coherence window validator.
8. **Impersonation Attack**:
   - Rogue sender transmits without holding shared quantum entanglement.
   - Outcome: **REJECTED (Unauthenticated credentials)**.

---

## 4. Quick Start & Execution

### One-Click Launch:
Double-click `run_v2.bat` in Windows Explorer or run:
```powershell
.\run_v2.bat
```

### Manual Command Line:
```powershell
cd "e:\2026-2\sih 2026\v2"
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser to:
- **Login Portal**: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login)
- **Alice / Admin Console**: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- **Bob Verifier**: [http://127.0.0.1:8000/bob](http://127.0.0.1:8000/bob)
- **Charlie Auditor**: [http://127.0.0.1:8000/charlie](http://127.0.0.1:8000/charlie)

---

## 5. Technology Stack
- **Backend**: Python 3.10+, FastAPI, Uvicorn, WebSockets.
- **Quantum Simulation**: Qiskit Aer, NumPy (physics-accurate Pauli operations, Bell state measurements, Pauli feed-forward gates).
- **Frontend**: Clean HTML5, Cyber-Physical Glassmorphism CSS, Vanilla ES6+ JavaScript, KaTeX for mathematical notation.
