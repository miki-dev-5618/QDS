# 🚀 Quantum Communication Simulator — FOR DUMMIES 💡

Welcome! If you are looking at quantum physics code for the first time and feel confused by terms like "Hadamard gates", "QBER", or "Qubits", **this guide is built specifically for you**.

---

## 🎯 The 30-Second Big Picture

Imagine you want to send a secret message over the internet:

1. **Normal Computing (Classical)**: You send 0s and 1s through regular electric wires. If a hacker (Eve) taps the wire, she can copy your data silently without leaving a trace.
2. **Quantum Computing (Our Project)**: You turn your 0s and 1s into **fragile quantum particles of light (photons/qubits)**.
3. **The Golden Rule of Quantum Physics**: If Eve tries to peek at or measure a quantum particle in transit, **she physically alters it**, corrupting the data and leaving obvious fingerprints!

This project represents **Stage 1, Stage 2, & Stage 3**:
* **Stage 1**: Building the baseline simulator loop (Alice $\rightarrow$ Bob) and detecting full-scale eavesdropping.
* **Stage 2**: Adding physical noise (random channel fluctuations), error reconciliation (correcting minor noise errors), and privacy amplification (compressing keys so hackers are left with nothing!).
* **Stage 3**: Implementing **Quantum Digital Signatures (QDS)**, where Alice signs a contract in a way that Bob and Charlie can verify independently, preventing Alice from denying it or Bob from forging it.

---

## 🧩 The Project Lego Blocks (Simplified Architecture)

Instead of dumping everything into one huge file, our code is split into clean folders:

```text
src/quantum_sim/
├── core/         ---> 🎯 "The Qubit Launcher" (Turns 0s & 1s into Qiskit circuits)
├── channel/      ---> 🌐 "The Fiber Cable, Noise & Hacker" (Simulates transmission, noise & attacks)
├── nodes/        ---> 👤 "The People" (Classes for Alice & Bob)
├── protocols/    ---> 📜 "The Rulebook" (Orchestrates normal and secure transmission pipelines)
└── utils/        ---> 🧮 "The Calculator" (Sifting, QBER metrics, Error Correction, & Privacy Hashing)
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

#### 🔍 How Parity Reconciliation Works (Step-by-Step)
Instead of Alice sending her entire key to Bob (which would let Eve steal it!), they use **Parity Check Bisection** to fix errors privately:

1. **Split into Blocks:** Alice and Bob divide their matching sifted keys into blocks of 8 bits.
2. **Check the Parity:** 
   * The **parity** of a block is simply whether the number of `1`s is even (0) or odd (1).
   * Alice and Bob compare their parities for each block.
   * If Alice's block parity is `1` (odd) and Bob's is `0` (even), they know **exactly one bit is mismatched** in that block.
3. **Play "Twenty Questions" (Bisection Binary Search):**
   * Alice and Bob split the mismatched 8-bit block in half (left 4 bits, right 4 bits).
   * They compare the parity of the **left half**.
   * *If the left parities match:* The error is in the **right half**.
   * *If the left parities mismatch:* The error is in the **left half**.
   * They split the erroneous half again (down to 2 bits) and compare parities.
   * Within 3 rounds of halving, they pinpoint the **exact bit index** that was flipped.
4. **Flip the Bit:** Bob flips that bit in his key, and now their keys match perfectly!


### 6. Privacy Amplification (Stage 2)
Alice and Bob compress their shared keys using **Universal Hashing** (multiplying the key by a random binary matrix). This shrinks the key to a smaller size, reducing Eve's knowledge of the key to virtually zero!

### 7. Symmetrisation & State Elimination (Stage 3 QDS)
* 📜 **Quantum Digital Signature**: Unlike standard signatures, a QDS signs documents using fragile quantum states. Bob and Charlie can verify that Alice wrote the signature, but neither can alter it.
* 🔄 **Symmetrisation (Keep or Forward)**: To prevent Alice from sending different states to Bob and Charlie (cheating/repudiation), Bob and Charlie decide independently to **Keep** their copy or **Forward** it to the other. By swapping elements, Alice cannot predict who holds which state, meaning she cannot bias her transmission to cheat one receiver over the other.
* ❌ **State Elimination**: In quantum mechanics, you cannot always read a state perfectly. However, by measuring it, you can prove what state it **could not possibly be**. Bob and Charlie store a list of these *impossible states*.
* 🔍 **Verification**: When Alice publishes her signature, Bob and Charlie check if the states Alice claims to have sent contradict their lists of impossible states. If Alice tries to forge or lie, Bob/Charlie immediately notice the contradictions and reject the signature.

---

## 📁 What Every File Does in Plain English

| File | What it actually does |
| :--- | :--- |
| **`src/quantum_sim/core/circuit.py`** | Builds Qiskit circuits. Applies `X` gates (bit flip) and `H` gates (basis change). |
| **`src/quantum_sim/channel/noise.py`** | Simulates random physical cable noise (e.g., bit flips, depolarizing noise). |
| **`src/quantum_sim/channel/attacks.py`** | Simulates Eve catching qubits mid-fiber, measuring them, and resending them. |
| **`src/quantum_sim/channel/base.py`** | Represents the fiber optical cable connecting Alice to Bob. |
| **`src/quantum_sim/nodes/node.py`** | Creates `Alice` and `Bob` objects that pick random bits and bases. |
| **`src/quantum_sim/protocols/point_to_point.py`** | Orchestrates basic point-to-point state transmission. |
| **`src/quantum_sim/protocols/secure_point_to_point.py`** | Orchestrates Stage 2 secure point-to-point protocol (with error correction and hashing). |
| **`src/quantum_sim/protocols/qds.py`** | Simulates Stage 3 QDS protocol (Alice preparing states, Keep/Forward swaps, measurements, and verification checks). |
| **`src/quantum_sim/utils/metrics.py`** | Calculates matching bases and QBER (error percentage). |
| **`src/quantum_sim/utils/post_processing.py`** | Implements the bisection error corrector and privacy amplifier. |
| **`examples/stage1_demo.py`** | Demonstration of Stage 1 transmission and intercept detection. |
| **`examples/stage2_demo.py`** | Demonstration of Stage 2 error correction and privacy amplification under noisy conditions. |
| **`examples/stage3_demo.py`** | Demonstration of Stage 3 QDS signature generation and verification. |
| **`examples/README_STAGE3.md`** | A detailed non-technical breakdown of the QDS simulation. |

---

## ⚡ How to Run It

Open your terminal in the project directory (`e:\2026-2\sih 2026`):

1. **Install requirements**:
   ```powershell
   pip install -r requirements.txt
   ```

2. **Run Stage 1 Demo**:
   ```powershell
   python examples/stage1_demo.py
   ```

3. **Run Stage 2 Demo**:
   ```powershell
   python examples/stage2_demo.py
   ```

4. **Run Stage 3 Demo (QDS)**:
   ```powershell
   python examples/stage3_demo.py
   ```

5. **Run the Automated Tests**:
   ```powershell
   pytest
   ```


