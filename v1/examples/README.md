# 📊 Stage 1 Demo Explanation — Line-by-Line Guide

This file explains **exactly what is happening** inside [`examples/stage1_demo.py`](file:///e:/2026-2/sih%202026/examples/stage1_demo.py).

---

## 💡 Overview of the Demo Script

`stage1_demo.py` runs **two live experiments** side-by-side:

1. **Scenario 1**: Alice sends 200 qubits to Bob through an **Ideal Optical Fiber** (no hacker).
2. **Scenario 2**: Alice sends 200 qubits to Bob through an **Eavesdropped Optical Fiber** (Eve is intercepting 100% of qubits).

---

## 🔍 Line-by-Line Code Walkthrough

```python
# Lines 1-8: Dynamic Path Setup
import sys
from pathlib import Path

src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
```
* **What this does**: Tells Python where to find our custom `quantum_sim` package inside the `src/` folder, preventing `ModuleNotFoundError`.

---

```python
# Lines 22-24: Actor & Generator Setup
alice = Node("Alice")
bob = Node("Bob")
rng = np.random.default_rng(12345)
```
* **What this does**:
  * Creates `Alice` (the sender) and `Bob` (the receiver).
  * Sets a reproducible random seed (`12345`) so every time you run the script, you get consistent results.

---

### 🟢 Scenario 1: Ideal Channel (No Eavesdropper)

```python
# Lines 26-29
ideal_channel = QuantumChannel()
ideal_protocol = PointToPointProtocol(alice, bob, ideal_channel, batch_size=20)
res_ideal = ideal_protocol.run(n_bits=200, sample_ratio=0.5, rng=rng)
```
* **What happens behind the scenes**:
  1. **State Preparation**: Alice generates 200 random secret bits and 200 random bases (Z or X basis).
  2. **Transmission**: `ideal_channel` passes the quantum circuits untouched.
  3. **Bob Measurement**: Bob generates 200 random bases and measures incoming qubits.
  4. **Simulation**: `AerSimulator` runs the quantum circuits in batches of 20.
  5. **Sifting**: Alice & Bob compare bases. Roughly ~100 bits match (since basis match probability is 50%).
  6. **QBER Estimation**: Samples 50% of matching bits to count errors.

#### Expected Output for Scenario 1:
```text
--- Scenario 1: Ideal Channel (No Eavesdropper) ---
Total Qubits Transmitted: 200
Sifted Key Length       : ~100 bits
Estimated QBER          : 0.00%
Eve Detected Status     : False
Alice Sifted Bits (First 15): [1 0 1 1 0 0 1 0 1 1 0 1 0 0 1]
Bob Sifted Bits   (First 15): [1 0 1 1 0 0 1 0 1 1 0 1 0 0 1]
```
> **Notice**: **QBER is exactly 0.00%**! Alice's sifted bits match Bob's sifted bits 100%.

---

### 🔴 Scenario 2: Eavesdropped Channel (Full Attack)

```python
# Lines 38-44
attack = InterceptResendAttack(p_intercept=1.0)
eavesdropped_channel = QuantumChannel(attacks=[attack])
eavesdropped_protocol = PointToPointProtocol(
    alice, bob, eavesdropped_channel, qber_threshold=0.15, batch_size=20
)
res_attack = eavesdropped_protocol.run(n_bits=200, sample_ratio=0.5, rng=rng)
```
* **What happens behind the scenes**:
  1. Eve places an `InterceptResendAttack` on the fiber channel with 100% interception probability ($p=1.0$).
  2. For every qubit sent by Alice, Eve measures it in a **random basis** before resending it to Bob.
  3. **The Quantum Collapse**: When Eve measures in the wrong basis, she destroys Alice's quantum state.
  4. When Bob measures in the matching basis, there is now a **25% chance of error**!

#### Expected Output for Scenario 2:
```text
--- Scenario 2: Intercept-Resend Attack (Full Eavesdropping) ---
Total Qubits Transmitted: 200
Sifted Key Length       : ~100 bits
Estimated QBER          : ~25.00%
Eve Detected Status     : True
Alice Sifted Bits (First 15): [0 1 1 0 1 0 1 1 0 0 1 1 0 1 0]
Bob Sifted Bits   (First 15): [0 1 0 0 1 0 1 1 1 0 1 1 0 1 1]
```
> **Notice**: **QBER jumps to ~25%**, mismatching bit values appear, and `Eve Detected Status` becomes **`True`** (alarm triggered because QBER $> 15\%$).

---

## 🚀 How to Run the Demo

From your terminal in the project directory:

```powershell
python examples/stage1_demo.py
```
