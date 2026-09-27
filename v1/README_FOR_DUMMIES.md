# 🚀 Quantum Communication Simulator — FOR DUMMIES 💡

Welcome! If you are looking at quantum physics and cryptography code for the first time and feel confused by terms like "Hadamard gates", "QBER", "Bell pairs", or "Chernoff Bounds", **this guide was written specifically for you**.

---

## 🎯 The 30-Second Big Picture

Imagine you want to send a super-secure digital signature over the internet:

1. **Normal Computing (Classical)**: You send 0s and 1s through electrical wires or Wi-Fi. If a hacker taps the wire, they can silently copy your data without leaving a single trace. Furthermore, future quantum supercomputers running *Shor's Algorithm* will easily break standard RSA/ECDSA cryptography!
2. **Quantum Computing (Our Project)**: Instead of regular electrical pulses, you turn your signature bits into **fragile quantum particles of light (photons/qubits)**.
3. **The Golden Rule of Quantum Physics**: If an eavesdropper (Eve) tries to peek at or measure a quantum particle in transit, **she physically alters its quantum state**. This corrupts the data, leaving obvious physical fingerprints that are impossible to hide!
4. **Information-Theoretic Security**: Our security is not based on solving hard math puzzles (which computers might solve one day). It is guaranteed by the **laws of physics** (Heisenberg's Uncertainty Principle and the Quantum No-Cloning Theorem).

---

## 🗺️ What This Project Covers (Stages 1 through 5)

* 🟢 **Stage 1 (The Basic Quantum Loop)**: Alice sends qubits to Bob over a quantum channel. We measure the errors to catch eavesdroppers (Eve) immediately.
* 🟡 **Stage 2 (Noisy Channels & Privacy Hashing)**: Real fiber cables have noise. We use **Cascade Error Correction** (fixing flipped bits like a game of 20 Questions) and **Privacy Amplification** (shrinking keys with math hashing so Eve ends up with zero information).
* 🔵 **Stage 3 (Prepare-and-Measure QDS)**: Alice signs a document using quantum states. Bob and Charlie swap copies (**Keep or Forward symmetrisation**) and perform **State Elimination** (ruling out impossible states) to prove Alice signed it and stop anyone from forging or denying it.
* 🟣 **Stage 4 (Multi-Vector Threat Simulator & Detective)**: Simulating real-world cyberattacks (forgeries, dishonest verifiers framing Alice, repudiation, and replay attacks) and catching them using a **100% deterministic (No AI/ML) threat detection engine**.
* 🔴 **Stage 5 (Quantum Teleportation & Mathematical Security Proofs)**: Teleporting quantum signature tokens using entangled **Bell pairs**, **Bell-State Measurements (BSM)**, and **Pauli feed-forward corrections** ($X^{m_2} Z^{m_1}$), backed by **Chernoff-Hoeffding mathematical security bounds**!
* 🌐 **Distributed Socket Daemon Network**: A multi-process network of 5 autonomous daemons talking over TCP sockets (Alice Signer, Bob Verifier, Charlie Verifier, Channel Router Proxy, and Threat Detector).
* 🖥️ **Interactive Web Visualizer**: A beautiful dark-mode browser interface to interactively test teleportation, inject attacks, and plot live security curves!

---

## 🧩 The Project Lego Blocks (Directory Guide)

```text
src/quantum_sim/
├── core/         ---> 🎯 "The Qubit Launcher" (Qiskit circuits, Bell pairs & Teleportation)
├── channel/      ---> 🌐 "The Fiber Cable, Noise & Hacker" (Simulates cables, noise & attacks)
├── nodes/        ---> 👤 "The People" (Classes for Alice, Bob & Charlie)
├── protocols/    ---> 📜 "The Rulebook" (Point-to-point, WDKA QDS, & Teleportation QDS pipelines)
├── attacks/      ---> 🦹 "The Threat Engine" (External forgeries, insider attacks, and repudiation)
├── detection/    ---> 🛡️ "The Detective" (Deterministic threat classifier & security certificates)
├── network/      ---> 🔌 "The Distributed Grid" (5 asynchronous TCP socket daemons)
└── utils/        ---> 🧮 "The Calculator" (Sifting, QBER metrics, Error Correction, & Chernoff Math Bounds)
```

---

## 🔑 Key Concepts Explained with Real-World Analogies

### 1. Classical Bit vs. Quantum Bit (Qubit)
* **Normal Bit**: A regular light switch. It is strictly **OFF (0)** or **ON (1)**.
* **Qubit**: A spinning coin on a table. While spinning, it is in a **superposition** (both Heads and Tails at the exact same time!). Once you slap your hand on it to look (measurement), it collapses into either 0 or 1.

### 2. Quantum Bases (Polarized Sunglasses 🕶️)
To send a qubit, Alice shoots polarized light through special filters:
* **Z-Basis (Straight Grid ➕)**: Vertical light = `0`, Horizontal light = `1`.
* **X-Basis (Diagonal Grid ✖️)**: Diagonal left light = `0`, Diagonal right light = `1`.

> **The Physics Rule**:
> - If Bob wears the **SAME** sunglasses grid as Alice $\rightarrow$ Bob gets the **EXACT SAME bit (100% match)**.
> - If Bob wears the **WRONG** sunglasses grid $\rightarrow$ The photon gets scrambled! Bob gets a **random 50/50 coin flip**, and the original state is permanently destroyed.

### 3. Sifting & Sifted Key Length (The Post-Transmission Phone Call 📞)
After sending qubits, Alice and Bob call each other over standard internet/phone to compare sunglasses grids:
> *"For Qubit #1, I used Z-basis. What did you use?"*
> - Both used Z-basis? $\rightarrow$ **KEEP THE BIT!**
> - Alice used Z, Bob used X? $\rightarrow$ **THROW IT AWAY!**

* 📐 **Sifted Key Length**: The number of bits kept after throwing away mismatched guesses. Because Bob guesses randomly, he matches Alice ~50% of the time. If Alice sends 200 qubits, their sifted key length will be around ~100 bits.

### 4. QBER (Quantum Bit Error Rate — The Hacker Alarm 🚨)
Alice and Bob compare a small random sample of their sifted bits:
* 🧮 **Estimated QBER**: The percentage of mismatches found in that sample.
  * **QBER = 0%**: Perfect, pristine channel with zero noise and no eavesdropper.
  * **QBER = 1% - 5%**: Normal physical noise (e.g., dust in the fiber).
  * **QBER $\ge$ 15% (theoretical 25%)**: **Hacker Alert!** Eve is intercepting and resending qubits mid-fiber, collapsing their quantum states and triggering alarms.

### 5. Cascade Error Correction (The 20-Questions Game 🧩)
Even without hackers, tiny temperature fluctuations in fiber cables flip bits occasionally.
* Alice and Bob divide their sifted keys into blocks and compare their **parity** (is the sum of bits odd or even?).
* If a block parity doesn't match, they know an odd number of errors occurred. They bisect the block (divide in half) repeatedly — like playing **"20 Questions"** — until they pinpoint the exact flipped bit and flip it back!

### 6. Privacy Amplification (The Shrink Wrap 🔒)
During error correction, Eve might have overheard some parity information over the phone line.
* Alice and Bob pass their reconciled key through **Universal Hashing** (multiplying by a random matrix).
* This compresses the key down (e.g., from 100 bits to 64 bits), mathematically squeezing out any residual information Eve might have gained until her knowledge is virtually zero.

### 7. Symmetrisation & State Elimination (Stage 3 QDS)
* 📜 **Quantum Digital Signature (QDS)**: Allows Alice to sign a digital message in a way that Bob and Charlie can both verify, preventing Bob from forging Alice's signature and preventing Alice from denying she signed it (**non-repudiation**).
* 🔄 **Symmetrisation (Keep or Forward)**: To stop Alice from cheating by sending different quantum states to Bob and Charlie, Bob and Charlie randomly **Keep** half of their tokens and **Forward** the other half to each other. Because Alice doesn't know who holds which tokens, she cannot bias her signature to cheat one receiver over the other!
* ❌ **State Elimination**: In quantum physics, you cannot always know what an unknown state *is*, but measuring in a chosen basis tells you what state it **CANNOT POSSIBLY BE** (the eliminated state). Bob and Charlie store a table of these impossible states.
* 🔍 **Verification**: When Alice announces her signature, Bob and Charlie check if Alice's claimed states conflict with their eliminated state tables. If mismatches exceed the acceptance threshold $s_a$, the signature is rejected!

### 8. Quantum Teleportation & Pauli Corrections (Stage 5 🚀)
How do you send a quantum state across a noisy or untrusted fiber without physically shooting the fragile particle across the line? **Quantum Teleportation!**
* 🎲 **Entangled Bell Pairs (The Twin Magic Dice)**: Alice and Bob share an entangled pair of qubits $|\Phi^+\rangle = \frac{|00\rangle + |11\rangle}{\sqrt{2}}$. What happens to Alice's qubit instantly influences Bob's qubit!
* 🔬 **Bell-State Measurement (BSM)**: Alice takes her secret signature qubit and her half of the twin die, performs a joint quantum measurement (`CX` + `H`), and gets two classical numbers $(m_1, m_2)$. This measurement destroys the original particle on Alice's side.
* 🎛️ **Pauli Feed-Forward Corrections (The Adjustment Dial)**: Alice sends $(m_1, m_2)$ over normal Wi-Fi to Bob. Bob turns his quantum dial ($X^{m_2} Z^{m_1}$) on his half of the twin die. Instantly, Bob's qubit transforms into the **exact replica of Alice's original signature qubit**!

### 9. Chernoff-Hoeffding Security Bounds (The Mathematical Seatbelt 🛡️)
Instead of guessing safety thresholds, we use **Chernoff-Hoeffding Statistical Bounds**:
* 📐 **Strict Mathematical Proof**: Calculates an exact upper bound on the probability of an attacker ever succeeding in forging a signature:
  $$P_{\text{forge}} \le e^{-2\delta^2 L}$$
* 📏 **Dynamic Safety Thresholds ($s_a$ & $s_v$)**: Automatically sets the passing grade ($s_a$) and failing grade ($s_v$) based on measured channel noise.
* 🔢 **Security Bits**: Tells you the exact cryptographic strength of your signature (e.g., 128-bit or 256-bit security).

### 10. Deterministic Threat Detection (The Non-AI Detective 🕵️‍♂️)
Unlike "black-box" AI/ML models that can hallucinate or make false assumptions:
* Our **Detection Engine** uses strict mathematical rules, quantum error thresholds, asymmetry differences ($|e_B - e_C|$), and freshness nonces to classify threats with 100% explainability.

---

## 📁 What Every File Does in Plain English

| File | What it actually does |
| :--- | :--- |
| **`src/quantum_sim/core/circuit.py`** | Builds Qiskit circuits: prepares BB84 states, entangled Bell pairs, and 3-qubit teleportation circuits with Pauli corrections. |
| **`src/quantum_sim/channel/noise.py`** | Simulates real-world fiber noise (bit-flip, phase-flip, and depolarizing noise). |
| **`src/quantum_sim/channel/attacks.py`** | Simulates Eve catching qubits mid-fiber, measuring them, and resending them. |
| **`src/quantum_sim/channel/base.py`** | Represents the fiber optic cable connecting parties. |
| **`src/quantum_sim/nodes/node.py`** | Creates `Alice`, `Bob`, and `Charlie` network actors. |
| **`src/quantum_sim/protocols/point_to_point.py`** | Runs Stage 1 basic point-to-point BB84 transmission. |
| **`src/quantum_sim/protocols/secure_point_to_point.py`** | Runs Stage 2 secure point-to-point protocol (Cascade error correction + privacy hashing). |
| **`src/quantum_sim/protocols/qds.py`** | Runs Stage 3 WDKA prepare-and-measure 3-party QDS protocol. |
| **`src/quantum_sim/protocols/teleportation_qds.py`** | Runs Stage 5 **Teleportation-Based QDS** with Bell pairs, BSM, and Pauli corrections. |
| **`src/quantum_sim/attacks/qds_threats.py`** | Threat engine simulating signature forgeries, dishonest verifiers, repudiation, and replay attacks. |
| **`src/quantum_sim/detection/engine.py`** | Detective engine classifying cyber threats deterministically and issuing security certificates. |
| **`src/quantum_sim/utils/metrics.py`** | Extracts bits from Qiskit measurement counts and calculates QBER. |
| **`src/quantum_sim/utils/post_processing.py`** | Performs Cascade parity error correction and universal hash key compression. |
| **`src/quantum_sim/utils/freshness.py`** | Anti-replay validator tracking cryptographic nonces and timestamps. |
| **`src/quantum_sim/utils/security_analysis.py`** | Calculates Chernoff-Hoeffding security bounds, optimal thresholds ($s_a, s_v$), and certificates. |
| **`src/quantum_sim/network/socket_node.py`** | Base TCP asynchronous socket server/client. |
| **`src/quantum_sim/network/messages.py`** | Standard JSON communication message formats for the network daemons. |
| **`src/quantum_sim/network/channel_proxy.py`** | **Port 8000**: Simulates the physical quantum router and attacker proxy. |
| **`src/quantum_sim/network/alice_daemon.py`** | **Port 8001**: Alice signer background service. |
| **`src/quantum_sim/network/verifier_daemon.py`** | **Ports 8002 & 8003**: Bob and Charlie verifier background services. |
| **`src/quantum_sim/network/detector_daemon.py`** | **Port 8004**: Central cyber threat monitoring and diagnostic daemon. |
| **`launch_network.py` / `launch_cluster.bat`** | Orchestrator scripts that launch all 5 socket daemons simultaneously. |
| **`examples/stage1_demo.py`** | Demo: BB84 state transmission and catching Eve intercepting qubits. |
| **`examples/stage2_demo.py`** | Demo: Fiber noise, Cascade error correction, and privacy amplification. |
| **`examples/stage3_demo.py`** | Demo: Prepare-and-measure 3-party QDS signature generation and verification. |
| **`examples/stage4_demo.py`** | Demo: Multi-vector cyber threat attacks and deterministic detection engine verdicts. |
| **`examples/stage5_teleportation_demo.py`** | Demo: Teleportation QDS with live Chernoff-Hoeffding mathematical security bounds. |
| **`examples/trigger_client.py`** | CLI tool to send a signing trigger command to the live distributed socket cluster. |
| **`visualizer/index.html`** | Interactive browser visualizer with animated circuits, attack lab, and live plots. |

---

## ⚡ How to Run Everything (Step-by-Step)

Open your terminal in the project directory (`e:\2026-2\sih 2026`):

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 2. Run All Automated Tests
To verify all 33 unit tests pass:
```powershell
pytest
```

### 3. Run Any CLI Demo Script

* **Stage 1 (Basic Quantum Loop & Intercept Attack)**:
  ```powershell
  python examples/stage1_demo.py
  ```

* **Stage 2 (Noise, Error Correction & Privacy Hashing)**:
  ```powershell
  python examples/stage2_demo.py
  ```

* **Stage 3 (Prepare-and-Measure QDS)**:
  ```powershell
  python examples/stage3_demo.py
  ```

* **Stage 4 (Threat Simulation & Diagnostic Detective)**:
  ```powershell
  python examples/stage4_demo.py
  ```

* **Stage 5 (Teleportation QDS & Chernoff Bounds)**:
  ```powershell
  python examples/stage5_teleportation_demo.py
  ```

### 4. Run the 5-Daemon Distributed Socket Network

Launch the full distributed quantum network cluster:
```powershell
# Method A: Using Python
python launch_network.py

# Method B: Using Windows Batch file (opens 5 separate daemon windows)
.\launch_cluster.bat
```

In a second terminal window, trigger an end-to-end QDS signing session:
```powershell
python examples/trigger_client.py --message 1 --length 128
```

### 5. Launch the Interactive Web Visualizer
Double click or open `visualizer/index.html` in any web browser (Chrome, Edge, Firefox, Safari) to explore:
* 🎬 **Interactive 5-Step Quantum Teleportation Walkthrough** with state-vector inspectors.
* 🦹 **Cyber Threat & Attack Lab**: Inject Eve eavesdropping, Alice repudiation, or Bob framing live.
* 🛡️ **Deterministic Detection Engine Dashboard**: Watch the non-AI detective diagnose attacks in real time.
* 📈 **Interactive Chernoff-Hoeffding Curve Plotter**: Adjust signature lengths and noise sliders to view security bound curves.
* 🎛️ **Pauli Feed-Forward Truth Table**: Inspect how $(m_1, m_2)$ syndromes map to $X^{m_2} Z^{m_1}$ gates.

---

## 🎓 Summary Cheat Sheet

| Question | Short Plain-English Answer |
| :--- | :--- |
| **Why Quantum?** | Quantum states cannot be copied (*No-Cloning*) and looking at them creates errors (*Uncertainty Principle*). |
| **What is QDS?** | A digital signature that cannot be forged, altered, or denied, backed by quantum physics. |
| **Why Teleportation?** | Avoids sending fragile signature qubits over raw fibers by using entangled Bell pairs and Pauli corrections. |
| **What is Symmetrisation?** | Bob and Charlie randomly swap tokens so Alice doesn't know who has what, preventing her from cheating. |
| **What are Chernoff Bounds?** | A rigorous mathematical formula proving that the chance of an attacker breaking the signature is virtually zero ($P \le e^{-2\delta^2 L}$). |
| **Is this using AI?** | No! The detection engine is 100% deterministic, explainable, and based directly on quantum statistics and physics principles. |
