# 🚀 Quantum Communication & QDS Simulator (Stage 1)

Welcome to the **Quantum Communication Simulator**! This repository provides a modular, Qiskit 2.x-based simulator for quantum state preparation, quantum channel transmission, eavesdropping simulation, and point-to-point protocols.

If you are new to quantum computing and Python development, this guide will walk you through every single folder, file, class, and function in this project!

---

## 📁 Directory Structure

```text
sih 2026/
├── pyproject.toml                     # Python package & dependency configuration
├── README.md                          # Project guide & beginner documentation
├── src/
│   └── quantum_sim/
│       ├── __init__.py                # Package root marker
│       ├── core/                      # Low-level Qiskit circuit manipulation
│       │   ├── __init__.py
│       │   └── circuit.py             # Quantum state prep & measurement gates
│       ├── channel/                   # Channel models, noise & attacks
│       │   ├── __init__.py
│       │   ├── base.py                # QuantumChannel class
│       │   ├── noise.py               # BitFlip, PhaseFlip, & Depolarizing noise
│       │   └── attacks.py             # InterceptResendAttack class
│       ├── nodes/                     # Network actor abstractions
│       │   ├── __init__.py
│       │   └── node.py                # Node class (Alice, Bob, Charlie)
│       ├── protocols/                 # Protocol execution workflows
│       │   ├── __init__.py
│       │   ├── base.py                # BaseProtocol abstract interface
│       │   ├── point_to_point.py      # Point-to-Point BB84 protocol runner
│       │   └── secure_point_to_point.py # Secure protocol runner (with post-processing)
│       └── utils/                     # Parsing & statistical metrics
│           ├── __init__.py
│           ├── metrics.py             # Bit extraction, sifting, & QBER estimation
│           └── post_processing.py     # Information reconciliation & privacy amplification
├── tests/                             # Automated Pytest test suite
│   ├── test_circuit.py
│   ├── test_metrics.py
│   ├── test_channel.py
│   ├── test_protocol.py
│   └── test_stage2.py
└── examples/                          # Runnable CLI demonstration scripts
    ├── stage1_demo.py
    └── stage2_demo.py
```

---

## 📖 File-by-File & Function Breakdown

### 1. `src/quantum_sim/core/circuit.py`
This module handles all interaction with **Qiskit** to build quantum circuits.

* **`prepare_bb84_state(bits, bases)`**:
  * **What it does**: Takes Alice's classical bit array (0s and 1s) and basis array (0 = Z-basis, 1 = X-basis) and creates a `QuantumCircuit`.
  * **Gates used**:
    * `qc.x(i)`: Bit-flip gate applied if bit is `1` (prepares state $|1\rangle$).
    * `qc.h(i)`: Hadamard gate applied if basis is `1` (transforms state to $|+\rangle$ or $|-\rangle$).

* **`add_bb84_measurement(qc, bases)`**:
  * **What it does**: Appends Bob's measurement choices to the transmitted quantum circuit.
  * **Gates used**:
    * `qc.h(i)`: Applied prior to measurement if Bob measures in the X-basis (basis = 1).
    * `qc.measure(i, i)`: Measures qubit `i` into classical bit `i`.

---

### 2. `src/quantum_sim/utils/metrics.py`
This module translates raw Qiskit simulator outcomes into classical bit lists and computes error stats.

* **`extract_bits_from_counts(counts, n_qubits)`**:
  * **What it does**: Parses Qiskit backend result dictionary (e.g. `{"0101": 1024}`) and extracts the most probable bit string into a 1D NumPy integer array.

* **`sift_bases(alice_bases, bob_bases)`**:
  * **What it does**: Compares Alice's and Bob's basis choices and returns the index array where `alice_bases == bob_bases`.

* **`estimate_qber(alice_bits, bob_bits, sifted_indices, sample_ratio=0.5, rng=None)`**:
  * **What it does**: Randomly samples a fraction (default 50%) of the sifted indices to calculate the **Quantum Bit Error Rate** ($QBER = \frac{\text{mismatches}}{\text{sample\_size}}$).

---

### 3. `src/quantum_sim/channel/`

#### `channel/attacks.py`
* **`BaseAttack`**: Abstract base class defining the `apply(circuit, rng)` interface for channel security threats.
* **`InterceptResendAttack(p_intercept=1.0)`**:
  * **What it does**: Simulates an eavesdropper (Eve) intercepting qubits with probability `p_intercept`.
  * **Quantum physical implementation**:
    * Adds an auxiliary classical register `c_eve` to the circuit.
    * Eve picks a random measurement basis $e_i \in \{0, 1\}$.
    * Applies `H` if $e_i=1$, measures qubit into `c_eve[i]` (collapsing the qubit state), and applies `H` if $e_i=1$ to resend it to Bob.

#### `channel/base.py`
* **`QuantumChannel(attacks=[...])`**:
  * **What it does**: Represents the physical fiber channel connecting parties. It takes Alice's `QuantumCircuit`, passes it through all configured channel attacks/noise models, and returns the modified circuit.

---

### 4. `src/quantum_sim/nodes/node.py`
* **`Node(name)`**:
  * **What it does**: Represents a network participant (e.g., Alice, Bob, or Charlie).
  * **Methods**:
    * `prepare_bb84_transmission(n_bits, rng)`: Alice generates random bits and bases, then returns the prepared `QuantumCircuit`.
    * `apply_bb84_measurement(circuit, n_bits, rng)`: Bob generates random bases and appends measurement gates to the circuit.

---

### 5. `src/quantum_sim/protocols/`

#### `protocols/base.py`
* **`BaseProtocol`**: Abstract lifecycle interface standardizing protocol workflows (`setup()`, `transmit()`, `measure()`, `process()`, `run()`).

#### `protocols/point_to_point.py`
* **`ProtocolResult`**: Dataclass storing results (`n_sent`, `n_sifted`, `sifted_bits_alice`, `sifted_bits_bob`, `qber`, `eve_detected`).
* **`PointToPointProtocol(alice, bob, channel)`**:
  * **What it does**: Executes the full point-to-point BB84 transmission pipeline on `AerSimulator`.

#### `protocols/secure_point_to_point.py`
* **`SecureProtocolResult`**: Dataclass storing results including `reconciled_bits` and `final_key` outputs.
* **`SecurePointToPointProtocol(alice, bob, channel)`**:
  * **What it does**: Performs secure point-to-point key agreement using error reconciliation and privacy amplification.

---

### 6. `src/quantum_sim/utils/post_processing.py`
* **`reconcile_keys(alice_bits, bob_bits, block_size)`**: Simplified Cascade parity-check error correction.
* **`amplify_privacy(bits, qber)`**: Universal hashing privacy amplification.

---

### 7. `tests/`
Automated test suite using `pytest`:
* **`test_circuit.py`**: Verifies quantum circuit gate allocations.
* **`test_metrics.py`**: Verifies bit array conversion and QBER sampling logic.
* **`test_channel.py`**: Verifies ideal channel, noise application, and attack register insertion.
* **`test_protocol.py`**: Validates Point-to-Point protocol under ideal and eavesdropped channels.
* **`test_stage2.py`**: Validates Stage 2 features (Noise, Post-processing, Secure Protocol).

---

### 8. `examples/`
* **`stage1_demo.py`**: Point-to-point transmission under ideal and eavesdropped channels.
* **`stage2_demo.py`**: Stage 2 Secure point-to-point communication showing key agreement under noisy channels.

---

## 💻 How to Run standard commands in your Terminal

### 1. Install Dependencies
Install all required libraries using `requirements.txt`:
```powershell
pip install -r requirements.txt
```


### 2. Run the Unit Test Suite
To verify all 15 tests pass:
```powershell
pytest
```

### 3. Run the Stage 1 Demo
To see the Stage 1 simulator:
```powershell
python examples/stage1_demo.py
```

### 4. Run the Stage 2 Demo
To see the Stage 2 simulator with error correction and privacy amplification:
```powershell
python examples/stage2_demo.py
```
