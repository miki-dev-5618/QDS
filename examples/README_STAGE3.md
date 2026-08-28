# Stage 3 QDS Demo: Walkthrough and Explanation

This directory contains the demonstration script for the **Quantum Digital Signature (QDS)** protocol based on multi-party state distribution, Keep/Forward symmetrisation, state elimination, and verification thresholds.

---

## Protocol Overview

### 1. Generation (Alice)
Alice prepares two private signatures: one for message $k=0$ and another for $k=1$. Each signature consists of $N$ randomly prepared quantum states chosen from the standard BB84 set:
- $|0\rangle$ (basis: Z, bit: 0)
- $|1\rangle$ (basis: Z, bit: 1)
- $|+\rangle$ (basis: X, bit: 0)
- $|-\rangle$ (basis: X, bit: 1)

### 2. Distribution & Symmetrisation
To sign a message and ensure non-repudiation (meaning Alice cannot deny sending the signature, and Bob cannot forge it to fool Charlie):
- Alice sends a copy of each state to Bob and Charlie.
- **Symmetrisation Swap**: Bob and Charlie randomly choose to **KEEP** their received state or **FORWARD** it to the other player.
  - If both Keep: each has 1 copy.
  - If one Keeps and one Forwards: the Keeper receives the other's copy (now has 2 copies), and the Forwarder has 0 copies.
  - If both Forward: they swap copies, ending up with 1 copy each.

### 3. Measurement & State Elimination
Each receiver measures whatever copies they hold:
- **0 copies**: No measurement. No states are eliminated.
- **1 copy**: Measure in a randomly selected basis (Z or X).
  - If measured in Z and outcome is 0: state $|1\rangle$ is eliminated.
  - If measured in Z and outcome is 1: state $|0\rangle$ is eliminated.
  - If measured in X and outcome is 0 (representing $+$): state $|-\rangle$ is eliminated.
  - If measured in X and outcome is 1 (representing $-$): state $|+\rangle$ is eliminated.
- **2 copies**: Measure one copy in the Z basis and the other in the X basis. This eliminates exactly 2 states (one from $\{|0\rangle, |1\rangle\}$ and one from $\{|+\rangle, |-\rangle\}$), providing more information.

### 4. Abort Verification
Before proceeding, Bob and Charlie verify if they received at least a threshold (e.g., 50%) of elements. If the received count is below this minimum, they abort to prevent eavesdropping or cheating.

### 5. Messaging & Verification Stage
Alice announces she is signing message $k \in \{0, 1\}$ and sends the classical description of the states.
- Bob and Charlie check if the states Alice claims she sent contradict any of their stored **eliminated states**.
- If a claimed state matches an eliminated state, it counts as a mismatch (contradiction).
- In ideal conditions, a correct message signature results in **0 mismatches**. A forged message signature (which is random relative to the receiver's measurements) will yield multiple mismatches and be rejected.

---

## How to Run the Demo

To run the Stage 3 simulation, run the following command in your terminal:

```powershell
python examples/stage3_demo.py
```

To run the automated tests for this stage:

```powershell
pytest tests/test_qds.py
```
