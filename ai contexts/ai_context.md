# AI Context: Quantum Communication & QDS Simulator

This document provides complete system context, design patterns, codebase architecture, and instructions for AI agents working on the Quantum Communication & Quantum Digital Signature (QDS) Simulator.

---

## 📌 Project Overview
We are building a modular, student-oriented prototype simulator for **Quantum Communication, Secure Quantum Communication, Quantum Digital Signatures (QDS)**, and **threat simulation/detection**.

The project is structured in stages to ensure a solid foundation:
* **Stage 1 (Current):** Modular Quantum Communication Simulator (BB84/QKD point-to-point base).
* **Stage 2:** Secure Quantum Communication Simulator (adding advanced noise, authentication, and state verification).
* **Stage 3:** Quantum Digital Signature (QDS) Protocol implementation.
* **Stage 4:** Threat simulation, detection logic, and a frontend dashboard.

---

## 🛠️ Technology Stack
* **Language:** Python 3.10+
* **Quantum Library:** Qiskit 2.x
* **Simulation Backend:** Qiskit Aer (`AerSimulator`)
* **Testing:** `pytest`
* **Numerical Processing:** NumPy

---

## 📁 Directory Structure
```text
sih 2026/
├── pyproject.toml                     # Dependency & packaging configuration
├── README.md                          # Main developer & user guide
├── README_FOR_DUMMIES.md              # Simplified guide for beginners
├── ai_context.md                      # This AI context file
├── docs/                              # System documentation & analysis
│   ├── AI CONTEXT 1.md                # (Old context - Ignore)
│   ├── qkd_lab_codebase_analysis.md   # Analysis of Qiskit QKD Lab patterns
│   └── quantum_sim_for_beginners.md   # General quantum guide
├── src/
│   └── quantum_sim/
│       ├── __init__.py                # Package entrypoint
│       ├── core/                      # Low-level Qiskit circuit building
│       │   ├── __init__.py
│       │   └── circuit.py             # Quantum state prep & measurement gates
│       ├── channel/                   # Quantum channel models & attacks
│       │   ├── __init__.py
│       │   ├── base.py                # QuantumChannel class
│       │   └── attacks.py             # InterceptResendAttack class
│       ├── nodes/                     # Network actor abstractions
│       │   ├── __init__.py
│       │   └── node.py                # Node class (Alice, Bob, Charlie)
│       ├── protocols/                 # Protocol execution workflows
│       │   ├── __init__.py
│       │   ├── base.py                # BaseProtocol abstract interface
│       │   └── point_to_point.py      # Point-to-Point BB84 protocol runner
│       └── utils/                     # Parsing & statistical metrics
│       │   ├── __init__.py
│       │   └── metrics.py             # Bit extraction & QBER calculation
├── tests/                             # Automated unit testing suite
│   ├── test_circuit.py
│   ├── test_metrics.py
│   ├── test_channel.py
│   └── test_protocol.py
└── examples/                          # Demonstration scripts
    └── stage1_demo.py
```

---

## 🏗️ Codebase Architecture & API Reference

### 1. Quantum Circuit Manipulation (`src/quantum_sim/core/circuit.py`)
Responsible for interacting with Qiskit to construct qubits and append measurements.
* [`prepare_bb84_state(bits, bases)`](file:///e:/2026-2/sih%202026/src/quantum_sim/core/circuit.py#L5): Prepares a `QuantumCircuit` using Alice's classical bits and bases (0 = Z-basis, 1 = X-basis).
* [`add_bb84_measurement(qc, bases)`](file:///e:/2026-2/sih%202026/src/quantum_sim/core/circuit.py#L16): Appends H-gates (where basis is X) and measurement gates to the circuit.

### 2. Physical Quantum Channel & Threats (`src/quantum_sim/channel/`)
* [`QuantumChannel`](file:///e:/2026-2/sih%202026/src/quantum_sim/channel/base.py#L7): Handles qubit transmission. Passes circuits through sequential `BaseAttack` instances.
* [`BaseAttack`](file:///e:/2026-2/sih%202026/src/quantum_sim/channel/attacks.py#L6): Abstract base class for security attacks.
* [`InterceptResendAttack(p_intercept)`](file:///e:/2026-2/sih%202026/src/quantum_sim/channel/attacks.py#L12): Simulates Eve's intercept-resend behavior by adding a classical register, measuring the qubits in random bases, and sending them onward.

### 3. Network Nodes (`src/quantum_sim/nodes/node.py`)
* [`Node`](file:///e:/2026-2/sih%202026/src/quantum_sim/nodes/node.py#L7): Represents a network participant (Alice, Bob, etc.).
  * `prepare_bb84_transmission(n_bits, rng)`: Alice generates random bits and bases and builds the `QuantumCircuit`.
  * `apply_bb84_measurement(circuit, n_bits, rng)`: Bob generates random bases and adds measurements.

### 4. Protocols (`src/quantum_sim/protocols/`)
* [`BaseProtocol`](file:///e:/2026-2/sih%202026/src/quantum_sim/protocols/base.py): Abstract framework establishing `setup()`, `transmit()`, `measure()`, `process()`, and `run()` workflows.
* [`PointToPointProtocol`](file:///e:/2026-2/sih%202026/src/quantum_sim/protocols/point_to_point.py#L22): Simulates the full BB84 flow using `AerSimulator`. Manages chunked batch-by-batch execution, error-rate calculation (QBER), and security thresholds.

### 5. Statistics & Utilities (`src/quantum_sim/utils/metrics.py`)
* `extract_bits_from_counts(counts, n_qubits)`: Translates raw simulator outcomes into clean NumPy array bits.
* `sift_bases(alice_bases, bob_bases)`: Matches bases and returns the sifted index positions.
* `estimate_qber(alice_bits, bob_bits, sifted_indices, sample_ratio)`: Evaluates errors in a randomly sampled fraction of the sifted keys.

---

## 🤖 Guidelines for AI Code Modifications

### 1. Maintain Modular Architecture
Keep physical layers separate from application logic:
* Do not embed protocol-specific details into `QuantumChannel` or `BaseAttack`.
* Ensure Qiskit dependencies remain decoupled inside `core/circuit.py` and the execution backend inside protocol classes.

### 2. Random Number Generation
Always accept an optional `rng` parameter of type `np.random.Generator`. Avoid calling global `np.random` methods directly to ensure reproducible tests.

### 3. Preserving API & Documentation
* Preserve docstrings and class initializers.
* Write unit tests under the `tests/` directory for any new features.

---

## 🚀 How to Execute Commands

### Running Tests
To execute all test suites:
```powershell
pytest
```

### Running the Demo
To run the default point-to-point simulator demo:
```powershell
python examples/stage1_demo.py
```
