# 🚀 Quantum Communication Simulator — FOR DUMMIES 💡

Welcome! If you are looking at quantum physics code for the first time and feel confused by terms like "Hadamard gates", "QBER", or "Qubits", **this guide is built specifically for you**.

---

## 🎯 The 30-Second Big Picture

Imagine you want to send a secret message over the internet:

1. **Normal Computing (Classical)**: You send 0s and 1s through regular electric wires. If a hacker (Eve) taps the wire, she can copy your data silently without leaving a trace.
2. **Quantum Computing (Our Project)**: You turn your 0s and 1s into **fragile quantum particles of light (photons/qubits)**.
3. **The Golden Rule of Quantum Physics**: If Eve tries to peek at or measure a quantum particle in transit, **she physically alters it**, corrupting the data and leaving obvious fingerprints!

This project represents **Stages 1 through 5**:
* **Stage 1**: Building the baseline simulator loop (Alice $\rightarrow$ Bob) and detecting full-scale eavesdropping.
* **Stage 2**: Adding physical noise (random channel fluctuations), error reconciliation (correcting minor noise errors), and privacy amplification (compressing keys so hackers are left with nothing!).
* **Stage 3**: Implementing **Quantum Digital Signatures (QDS)**, where Alice signs a contract in a way that Bob and Charlie can verify independently, preventing Alice from denying it or Bob from forging it.
* **Stage 4**: Multi-vector threat simulations (external forgeries, dishonest verifiers, repudiation, channel tampering) and protocol-aware threat classification.
* **Stage 5**: **Teleportation-Based QDS & Information-Theoretic Security Bounds**, using entangled Bell pairs, Bell-State Measurements (BSM), Pauli feed-forward corrections, and Chernoff-Hoeffding mathematical security guarantees!

---

## 🧩 The Project Lego Blocks (Simplified Architecture)

Instead of dumping everything into one huge file, our code is split into clean folders:

```text
src/quantum_sim/
├── core/         ---> 🎯 "The Qubit Launcher" (Turns bits into Qiskit circuits, Bell pairs & Teleportation)
├── channel/      ---> 🌐 "The Fiber Cable, Noise & Hacker" (Simulates transmission, noise & attacks)
├── nodes/        ---> 👤 "The People" (Classes for Alice, Bob & Charlie)
├── protocols/    ---> 📜 "The Rulebook" (Point-to-point, WDKA QDS, and Teleportation QDS pipelines)
├── attacks/      ---> 🦹 "The Threat Engine" (External forgeries, insider attacks, and repudiation scenarios)
├── detection/    ---> 🛡️ "The Detective" (Protocol-aware deterministic threat classifier)
├── network/      ---> 🔌 "The Internet Grid" (Multi-process asynchronous socket daemons)
└── utils/        ---> 🧮 "The Calculator" (Sifting, QBER metrics, Error Correction, & Chernoff Math Bounds)
```

---

## 🔑 Key Concepts Explained with Real-World Analogies

### 1. Quantum Bit (Qubit)
* **Normal Bit**: A regular light switch. It is strictly **OFF (0)** or **ON (1)**.
* **Qubit**: A spinning coin in the air. While spinning, it is in a **superposition** (both heads and tails at the same time!).

### 2. Quantum Bases (Polarized Sunglasses)
To send a qubit, Alice shoots light through polarized sunglasses:
* **Z-Basis (Straight Grid)**: Vertical light = `0`, Horizontal light = `1`.
* **X-Basis (Diagonal Grid)**: Diagonal left light = `0`, Diagonal right light = `1`.

> **The Physics Rule**:
> - If Bob uses the **SAME** sunglasses grid as Alice $\rightarrow$ Bob gets the **EXACT SAME bit (100% match)**.
> - If Bob uses the **WRONG** sunglasses grid $\rightarrow$ The light gets confused! Bob gets a **random 50/50 guess**, and the original signal is destroyed.

### 3. Sifting & Sifted Key Length (The Post-Transmission Phone Call)
After sending qubits, Alice and Bob call each other on the normal phone line to compare sunglasses grids:
> *"For Qubit #1, I used Z-basis. What did you use?"*
> - Both used Z-basis? $\rightarrow$ **KEEP THE BIT!**
> - Alice used Z, Bob used X? $\rightarrow$ **THROW IT AWAY!**

* 📐 **Sifted Key Length**: This is the count of bits left *after* discarding mismatched basis choices. Because Bob guesses the grid randomly, he is correct 50% of the time. Consequently, the sifted key length is usually around **50% of the total transmitted qubits** (e.g., ~100 bits sifted from 200 sent).

### 4. Estimated QBER (Quantum Bit Error Rate)
Before using the sifted key, Alice and Bob compare a random sample of it to check for tampering.
* 🧮 **Estimated QBER**: The percentage of bit discrepancies found in that sample.
  * **QBER = 0%**: Perfect, pristine channel with zero noise or intruders.
  * **QBER = 1% - 5%**: Normal physical noise (e.g., dust in the fiber).
  * **QBER $\ge$ 15% (or ~25% theoretical)**: **Hacker Alert!** Eve is intercepting and resending the qubits, which collapses their states and introduces high error rates.

### 5. Noise & Error Reconciliation (Stage 2)
Real glass fiber cables have dust or temperature fluctuations that randomly flip qubits (**Channel Noise**).
* Alice and Bob run **Information Reconciliation** (error correction). They divide their keys into blocks and compare parities (whether the sum of bits is odd or even). If there's a discrepancy, they run a quick game of "Twenty Questions" (binary search bisection) to find the exact bit that flipped and correct it.

### 6. Privacy Amplification (Stage 2)
Alice and Bob compress their shared keys using **Universal Hashing** (multiplying the key by a random binary matrix). This shrinks the key to a smaller size, reducing Eve's knowledge of the key to virtually zero!

### 7. Symmetrisation & State Elimination (Stage 3 QDS)
* 📜 **Quantum Digital Signature**: Unlike standard signatures, a QDS signs documents using fragile quantum states. Bob and Charlie can verify that Alice wrote the signature, but neither can alter it.
* 🔄 **Symmetrisation (Keep or Forward)**: To prevent Alice from sending different states to Bob and Charlie (cheating/repudiation), Bob and Charlie decide independently to **Keep** their copy or **Forward** it to the other. By swapping elements, Alice cannot predict who holds which state, meaning she cannot bias her transmission to cheat one receiver over the other.
* ❌ **State Elimination**: In quantum mechanics, you cannot always read a state perfectly. However, by measuring it, you can prove what state it **could not possibly be**. Bob and Charlie store a list of these *impossible states*.
* 🔍 **Verification**: When Alice publishes her signature, Bob and Charlie check if the states Alice claims to have sent contradict their lists of impossible states. If Alice tries to forge or lie, Bob/Charlie immediately notice the contradictions and reject the signature.

### 8. Quantum Teleportation & Pauli Corrections (Stage 5)
How do we send quantum states without physically mailing them through an untrusted fiber?
* 🎲 **Entangled Bell Pairs (The Twin Magic Dice)**: Alice and Bob share a pair of connected quantum particles.
* 🔬 **Bell-State Measurement (The Scan & Destroy)**: Alice interacts her secret signature particle with her half of the twin die. This destroys the particle on Alice's side and gives two simple classical numbers $(m_1, m_2)$.
* 🎛️ **Pauli Corrections (The Adjustment Dial)**: Alice sends $(m_1, m_2)$ over normal Wi-Fi to Bob. Bob turns his quantum dial ($X$ flip or $Z$ phase rotate) based on those numbers, and his twin die instantly transforms into the exact original signature state!

### 9. Chernoff-Hoeffding Security Bounds (Stage 5 Math)
Instead of guessing error cutoffs, we use **Chernoff-Hoeffding Bounds**:
* 🛡️ **Mathematical Proof of Security**: It calculates an exact mathematical upper bound on the chance that an attacker could ever cheat ($P_{\text{forge}} \le e^{-2\delta^2 L}$).
* 📏 **Dynamic Safety Line ($s_a$ & $s_v$)**: Automatically calculates the exact passing and failing grades based on channel noise.
* 🔢 **Security Level in Bits**: Tells you how many cryptographic bits of protection your signature currently has (e.g., 128-bit or 256-bit security).

---

## 📁 What Every File Does in Plain English

| File | What it actually does |
| :--- | :--- |
| **`src/quantum_sim/core/circuit.py`** | Builds Qiskit circuits, prepares BB84 states, Bell pairs, and Teleportation circuits. |
| **`src/quantum_sim/channel/noise.py`** | Simulates random physical cable noise (e.g., bit flips, depolarizing noise). |
| **`src/quantum_sim/channel/attacks.py`** | Simulates Eve catching qubits mid-fiber, measuring them, and resending them. |
| **`src/quantum_sim/channel/base.py`** | Represents the fiber optical cable connecting Alice to Bob. |
| **`src/quantum_sim/nodes/node.py`** | Creates `Alice`, `Bob`, and `Charlie` network participants. |
| **`src/quantum_sim/protocols/point_to_point.py`** | Orchestrates basic point-to-point state transmission. |
| **`src/quantum_sim/protocols/secure_point_to_point.py`** | Orchestrates Stage 2 secure point-to-point protocol (with error correction and hashing). |
| **`src/quantum_sim/protocols/qds.py`** | Simulates Stage 3 WDKA prepare-and-measure QDS protocol. |
| **`src/quantum_sim/protocols/teleportation_qds.py`** | Simulates Stage 5 **Teleportation-Based QDS** with Bell pairs, BSM, and Pauli corrections. |
| **`src/quantum_sim/attacks/qds_threats.py`** | Threat engine simulating signature forgeries, dishonest verifiers, and repudiation. |
| **`src/quantum_sim/detection/engine.py`** | Detective engine classifying threats deterministically with security certificates. |
| **`src/quantum_sim/utils/security_analysis.py`** | Chernoff-Hoeffding statistical security bound calculator and certificate generator. |
| **`examples/stage1_demo.py`** | Demonstration of Stage 1 transmission and intercept detection. |
| **`examples/stage2_demo.py`** | Demonstration of Stage 2 error correction and privacy amplification under noisy conditions. |
| **`examples/stage3_demo.py`** | Demonstration of Stage 3 QDS signature generation and verification. |
| **`examples/stage4_demo.py`** | Demonstration of Stage 4 multi-vector threat simulation and diagnostic engine. |
| **`examples/stage5_teleportation_demo.py`** | Demonstration of Stage 5 **Teleportation-Based QDS** with live Chernoff security bounds. |

---

## ⚡ How to Run It

Open your terminal in the project directory (`e:\2026-2\sih 2026`):

1. **Install requirements**:
   ```powershell
   pip install -r requirements.txt
   ```

2. **Run Stage 1 Demo (Basic Quantum Loop)**:
   ```powershell
   python examples/stage1_demo.py
   ```

3. **Run Stage 2 Demo (Noise & Privacy Hashing)**:
   ```powershell
   python examples/stage2_demo.py
   ```

4. **Run Stage 3 Demo (Prepare-and-Measure QDS)**:
   ```powershell
   python examples/stage3_demo.py
   ```

5. **Run Stage 4 Demo (Threat & Attack Simulator)**:
   ```powershell
   python examples/stage4_demo.py
   ```

6. **Run Stage 5 Demo (Teleportation QDS & Chernoff Bounds)**:
   ```powershell
   python examples/stage5_teleportation_demo.py
   ```

7. **Launch the Interactive Web Visualizer**:
   Simply open `visualizer/index.html` in any web browser to explore:
   - Interactive 5-step Quantum Teleportation simulator.
   - Cyber Threat & Attack Lab with real-time observables.
   - Deterministic Non-AI Threat Detection Engine dashboard.
   - Interactive Chernoff-Hoeffding security bound curve plotter.
   - 3-Qubit quantum circuit & Pauli truth table inspector.

8. **Run the Automated Test Suite**:
   ```powershell
   pytest
   ```




