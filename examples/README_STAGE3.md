# Stage 3 QDS Demo: Walkthrough and Visual Explanation

This directory contains the demonstration script and architecture for the **Quantum Digital Signature (QDS)** protocol based on multi-party state distribution, Keep/Forward symmetrisation, state elimination, and threshold-based verification.

---

## 🎨 Interactive Visualizer

We built a dedicated browser-based visualizer for this stage! You can open and interact with the UI directly:
- **Location:** [`QDS PROTOCL EXPLAINED/index.html`](file:///e:/2026-2/sih%202026/QDS%20PROTOCL%20EXPLAINED/index.html)
- **Features:** Interactive step-by-step execution, Keep/Forward decision trees, element-by-element quantum journey inspector, and live abort/verification gauges.

---

## 🗺️ High-Level Protocol Architecture & Flow

```
                      ┌─────────────────────────┐
                      │      Alice (Sender)     │
                      │  Generates Signatures:  │
                      │   Sig(k=0) & Sig(k=1)   │
                      │  States: |0⟩,|1⟩,|+⟩,|−⟩ │
                      └────────────┬────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
     [Copy 1 to Bob]                           [Copy 2 to Charlie]
              │                                         │
              ▼                                         ▼
   ┌────────────────────┐                    ┌────────────────────┐
   │    Bob (Receiver)  │ ◄── Swap Channel ──► │  Charlie (Receiver)│
   │  Decides: Keep (K) │  (Symmetrisation)  │  Decides: Keep (K) │
   │   or Forward (F)   │                    │   or Forward (F)   │
   └──────────┬─────────┘                    └──────────┬─────────┘
              │                                         │
              ▼                                         ▼
   ┌────────────────────┐                    ┌────────────────────┐
   │  Measurement &     │                    │  Measurement &     │
   │  State Elimination │                    │  State Elimination │
   │  (Holds 0, 1, or 2)│                    │  (Holds 0, 1, or 2)│
   └──────────┬─────────┘                    └──────────┬─────────┘
              │                                         │
              ▼                                         ▼
   ┌────────────────────┐                    ┌────────────────────┐
   │ Check Min Received │                    │ Check Min Received │
   │ Threshold (e.g. 50%)│                   │ Threshold (e.g. 50%)│
   └──────────┬─────────┘                    └──────────┬─────────┘
              │                                         │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼
                      ┌─────────────────────────┐
                      │  Alice Signs Message k  │
                      │ Broadcasts description  │
                      └────────────┬────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   ┌────────────────────┐                    ┌────────────────────┐
   │ Bob verifies:      │                    │ Charlie verifies:  │
   │ Claimed ∈ Elim?    │                    │ Claimed ∈ Elim?    │
   │ 0 mismatches: PASS │                    │ 0 mismatches: PASS │
   │ > threshold: REJECT│                    │ > threshold: REJECT│
   └────────────────────┘                    └────────────────────┘
```

---

## 🔬 Step-by-Step Breakdown

### 1. Quantum State Preparation (Alice)

Alice chooses $N$ random quantum states for message $k=0$ and $N$ random quantum states for message $k=1$ from the standard BB84 set:

| Basis | Bit Value | Quantum State | Ket Notation | Vector Representation |
| :---: | :---: | :---: | :---: | :---: |
| **Z** (Computational) | `0` | $|0\rangle$ | `|0⟩` | $\begin{pmatrix} 1 \\ 0 \end{pmatrix}$ |
| **Z** (Computational) | `1` | $|1\rangle$ | `|1⟩` | $\begin{pmatrix} 0 \\ 1 \end{pmatrix}$ |
| **X** (Hadamard) | `0` | $|+\rangle = \frac{\|0\rangle + \|1\rangle}{\sqrt{2}}$ | `|+⟩` | $\frac{1}{\sqrt{2}}\begin{pmatrix} 1 \\ 1 \end{pmatrix}$ |
| **X** (Hadamard) | `1` | $|-\rangle = \frac{\|0\rangle - \|1\rangle}{\sqrt{2}}$ | `|−⟩` | $\frac{1}{\sqrt{2}}\begin{pmatrix} 1 \\ -1 \end{pmatrix}$ |

---

### 2. Symmetrisation & Keep / Forward Routing

To prevent repudiation (Alice sending mismatched states to Bob vs Charlie) and forgery (Bob guessing what Charlie received), Bob and Charlie independently choose whether to **Keep (K)** or **Forward (F)** their received copy.

```
 Case 1: Keep / Keep          Case 2: Keep / Forward
  Alice ──► Bob   [Holds 1]    Alice ──► Bob   [Holds 2] (receives Charlie's)
  Alice ──► Charlie [Holds 1]  Alice ──► Charlie ──► Bob [Holds 0]

 Case 3: Forward / Keep       Case 4: Forward / Forward (Swap)
  Alice ──► Bob ──► Charlie   Alice ──► Bob ────► Charlie [Holds 1]
  Alice ──► Charlie [Holds 2]  Alice ──► Charlie ──► Bob  [Holds 1]
```

#### Deterministic Distribution Summary Table:

| Bob Action | Charlie Action | Bob Receives Copies | Charlie Receives Copies | Total States in System |
| :---: | :---: | :---: | :---: | :---: |
| **Keep (K)** | **Keep (K)** | 1 copy | 1 copy | 2 copies |
| **Keep (K)** | **Forward (F)** | 2 copies | 0 copies | 2 copies |
| **Forward (F)** | **Keep (K)** | 0 copies | 2 copies | 2 copies |
| **Forward (F)** | **Forward (F)** | 1 copy (from Charlie) | 1 copy (from Bob) | 2 copies (Swapped) |

---

### 3. Measurement & State Elimination Rules

Each receiver measures the copies in their possession. Instead of trying to detect the exact state (which is impossible without knowing the basis), the receiver uses quantum mechanics to **rule out states that are orthogonal** to the measured outcome:

```
                      ┌───────────────────────┐
                      │  Measure in Basis Z   │
                      └──────────┬────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
          Outcome = |0⟩                   Outcome = |1⟩
     (Eliminates state |1⟩)          (Eliminates state |0⟩)

                      ┌───────────────────────┐
                      │  Measure in Basis X   │
                      └──────────┬────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
          Outcome = |+⟩                   Outcome = |−⟩
     (Eliminates state |−⟩)          (Eliminates state |+⟩)
```

#### Elimination Rules by Number of Copies Held:

- **0 copies held:** No measurement performed. **0 states eliminated** (`[]`).
- **1 copy held:** Measure in a randomly chosen basis ($Z$ or $X$). **1 state eliminated**.
  - Measured in $Z \rightarrow$ outcome $|0\rangle \implies$ eliminate $|1\rangle$.
  - Measured in $Z \rightarrow$ outcome $|1\rangle \implies$ eliminate $|0\rangle$.
  - Measured in $X \rightarrow$ outcome $|+\rangle \implies$ eliminate $|-\rangle$.
  - Measured in $X \rightarrow$ outcome $|-\rangle \implies$ eliminate $|+\rangle$.
- **2 copies held:** Measure copy 1 in basis $Z$ and copy 2 in basis $X$. **2 states eliminated** (one from $\{|0\rangle, |1\rangle\}$ and one from $\{|+\rangle, |-\rangle\}$).

---

### 4. Abort Verification Condition

```
                    ┌───────────────────────────────┐
                    │ Count Valid Received Elements │
                    └───────────────┬───────────────┘
                                    │
                         Ratio = Count(held) / N
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
        Ratio ≥ Min Threshold                 Ratio < Min Threshold
             (e.g., ≥ 50%)                         (e.g., < 50%)
                 │                                     │
                 ▼                                     ▼
          [CONTINUE PROTOCOL]                   [ABORT PROTOCOL]
                                          (Potential eavesdropping/drop)
```

If an eavesdropper intercepts or drops states, or if too many packets are lost, the ratio of received copies falls below the threshold and the protocol aborts immediately.

---

### 5. Verification Phase (Checking Contradictions)

When Alice announces message $k$, she releases the classical state descriptions.

$$\text{Mismatch Condition: } \text{Alice's Claimed State } \in \text{Receiver's Eliminated States}$$

```
 Example for Element #i:
  Alice Claims State:   |+⟩
  Bob's Eliminated:     [ |1⟩, |−⟩ ]
  Contradiction Check:  |+⟩ is NOT in [ |1⟩, |−⟩ ]  ──► Valid (0 Mismatches) ✅

 If Bob or Attacker Forged:
  Claimed Fake State:   |−⟩
  Bob's Eliminated:     [ |1⟩, |−⟩ ]
  Contradiction Check:  |−⟩ IS in [ |1⟩, |−⟩ ]      ──► MISMATCH (Cheating Detected!) ❌
```

---

## 💻 How to Run the Demo & Tests

To run the Stage 3 simulation script:

```powershell
python examples/stage3_demo.py
```

To run the automated tests:

```powershell
pytest tests/test_qds.py
```

