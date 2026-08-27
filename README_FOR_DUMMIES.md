# 🚀 Quantum Communication Simulator — FOR DUMMIES 💡

Welcome! If you are looking at quantum physics code for the first time and feel confused by terms like "Hadamard gates", "QBER", or "Qubits", **this guide is built specifically for you**.

---

## 🎯 The 30-Second Big Picture

Imagine you want to send a secret message over the internet:

1. **Normal Computing (Classical)**: You send 0s and 1s through regular electric wires. If a hacker (Eve) taps the wire, she can copy your data silently without leaving a trace.
2. **Quantum Computing (Our Project)**: You turn your 0s and 1s into **fragile quantum particles of light (photons/qubits)**.
3. **The Golden Rule of Quantum Physics**: If Eve tries to peek at or measure a quantum particle in transit, **she physically alters it**, corrupting the data and leaving obvious fingerprints!

This project is **Stage 1**: building a simulator on your computer using **Qiskit** that fires qubits from **Alice** to **Bob** over an optical fiber, and detects if **Eve** is eavesdropping!

---

## 🧩 The Project Lego Blocks (Simplified Architecture)

Instead of dumping everything into one huge file, our code is split into 5 small, clean folders:

```text
src/quantum_sim/
├── core/         ---> 🎯 "The Qubit Launcher" (Turns 0s & 1s into Qiskit Quantum Circuits)
├── channel/      ---> 🌐 "The Fiber Cable & Hacker" (Simulates transmission & Eve's attack)
├── nodes/        ---> 👤 "The People" (Classes for Alice & Bob)
├── protocols/    ---> 📜 "The Rulebook" (Runs the step-by-step transmission pipeline)
└── utils/        ---> 🧮 "The Calculator" (Compares bits & calculates Quantum Bit Error Rate)
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

### 3. Sifting (The Post-Transmission Phone Call)
After sending 200 qubits, Alice and Bob call each other on the normal phone line and say:
> *"For Qubit #1, I used Z-basis. What did you use?"*
> - Both used Z-basis? $\rightarrow$ **KEEP THE BIT!**
> - Alice used Z, Bob used X? $\rightarrow$ **THROW IT AWAY!**

### 4. QBER (Quantum Bit Error Rate)
Alice and Bob compare a small sample of their kept bits:
* **QBER = 0%**: Channel is clean! Alice and Bob have identical secret data.
* **QBER $\approx$ 25%**: **HACKER ALERT!** Eve intercepted the qubits!

---

## 📁 What Every File Does in Plain English

| File | What it actually does |
| :--- | :--- |
| **`src/quantum_sim/core/circuit.py`** | Builds Qiskit circuits. Applies `X` gates (bit flip) and `H` gates (basis change). |
| **`src/quantum_sim/channel/attacks.py`** | Simulates Eve catching qubits mid-fiber, measuring them in a random basis, and resending them. |
| **`src/quantum_sim/channel/base.py`** | Represents the fiber optical cable connecting Alice to Bob. |
| **`src/quantum_sim/nodes/node.py`** | Creates `Alice` and `Bob` objects that pick random bits and bases. |
| **`src/quantum_sim/protocols/point_to_point.py`** | Orchestrates state prep $\rightarrow$ fiber transmission $\rightarrow$ Bob measurement $\rightarrow$ error calculation. |
| **`src/quantum_sim/utils/metrics.py`** | Reads simulator counts, filters matching bases, and calculates error percentage. |
| **`examples/stage1_demo.py`** | The runnable demonstration script showing Ideal Channel vs Eavesdropped Channel. |

---

## ⚡ How to Run It in 2 Commands

Open your terminal in the project directory (`e:\2026-2\sih 2026`):

1. **Install requirements**:
   ```powershell
   pip install -r requirements.txt
   ```

2. **Run the Live Demo**:
   ```powershell
   python examples/stage1_demo.py
   ```

3. **Run the Automated Tests**:
   ```powershell
   pytest
   ```
