# 🚀 Stage 5: Teleportation-Based QDS, Pure Statistical Diagnostics & Chernoff Security Bounds

Welcome to **Stage 5**! This module fulfills the core objectives of the **Quantum-Inspired Cyber Threat Detection for Digital Signature Security** framework.

---

## 🎯 What is Stage 5?

Stage 5 bridges the gap between prepare-and-measure quantum communication and **Teleportation-Based Quantum Digital Signatures (QDS)** backed by **Information-Theoretic Security (ITS)** proofs.

### 🌟 Core Capabilities Introduced:
1. **Entangled Quantum Public Key Distribution**: Prepares $|\Phi^+\rangle = \frac{|00\rangle + |11\rangle}{\sqrt{2}}$ Bell pairs shared between the signer (Alice) and verifiers (Bob and Charlie).
2. **Quantum Teleportation & Pauli Feed-Forward**: Alice executes Bell-State Measurements (BSM), generating 2 classical syndrome bits $(m_1, m_2)$. Verifiers apply Pauli correction operators ($X^{m_2} Z^{m_1}$) to recover the signature states with $100\%$ theoretical fidelity.
3. **Pure Statistical Non-AI Threat Detection Engine**: Classifies attacks purely through quantum error clustering, asymmetry divergence, and freshness registries—**with zero heuristic cheat hints**.
4. **Complete Threat Vector Coverage**:
   - 🔴 *External Signature Forgery* (Eve blind guessing)
   - 🟠 *Dishonest Verifier Forgery* (Bob insider state filtering)
   - ⚡ *Quantum Channel Interception / MITM* ($QBER > 11\%$)
   - 🟣 *Dishonest Signer Repudiation* (Alice discordant states)
   - 🟡 *Replay & Stale Token Attack* (Nonce/timestamp reuse)
   - 👤 *Sender Impersonation* (Unauthenticated credentials)
   - ⚪ *Benign Environmental Fiber Noise* (Filtered below $s_a$)
5. **Chernoff-Hoeffding Insecurity Bounds**: Calculates exact analytical upper bounds on forgery probabilities ($P_{\text{forge}} \le e^{-2\delta^2 L}$) and generates verifiable **Security Certificates**.

---

## 🔬 Teleportation Workflow Breakdown

```text
 1. STATE PREP (Alice)
    Alice generates private signature tokens:
    |ψ⟩ ∈ {|0⟩, |1⟩, |+⟩, |−⟩} for message k ∈ {0, 1}

 2. BELL PAIR ENTANGLEMENT
    Alice and Verifiers share Bell pairs:
    |Φ⁺⟩ = (|00⟩ + |11⟩) / √2

 3. BELL-STATE MEASUREMENT (Alice)
    Alice interacts |ψ⟩ with her half of the Bell pair:
    CNOT(q_sig, q_A) ──► H(q_sig) ──► Measure (m₁, m₂)

 4. PAULI FEED-FORWARD (Verifiers)
    Alice transmits (m₁, m₂) over standard classical channel.
    Verifier rotates their qubit by X^{m₂} Z^{m₁}:
    - (0, 0) ──► Apply I (No flip)
    - (0, 1) ──► Apply X (Bit flip)
    - (1, 0) ──► Apply Z (Phase flip)
    - (1, 1) ──► Apply XZ = -iY (Both flips)
    Receiver's qubit is now IDENTICAL to |ψ⟩!

 5. SYMMETRISATION SWAP
    Bob and Charlie randomly Keep (K) or Forward (F) tokens.

 6. PROJECTIVE MEASUREMENT VERIFICATION
    Verifiers measure in the announced basis and verify 0 contradictions.
```

---

## 📊 Chernoff-Hoeffding Mathematical Bounds

Instead of heuristic guesses, security is proven mathematically:

### 1. Acceptance Threshold ($s_a$) & Verification Threshold ($s_v$):
$$s_a = e_0 + \delta, \quad s_v = p_{\text{forg\_min}} - \delta \quad \text{where } \delta = \frac{p_{\text{forg\_min}} - e_0}{3}$$

- **$s_a$ (Acceptance Threshold $\approx 9.67\%$)**: Honest signatures with minor fiber noise ($e_0 = 2\%$) are accepted.
- **$s_v$ (Verification Threshold $\approx 17.33\%$)**: Any error rate above $s_v$ is mathematically flagged as an attack.
- **$\delta$ (Safety Margin $\approx 0.0767$)**: The mathematical buffer between honest noise and forgery.

### 2. Analytical Security Formulas:
- **Probability of Successful Forgery**:
  $$P_{\text{forge}} \le \exp\left(-2 \delta^2 L\right)$$
- **False Rejection Rate (FRR)**:
  $$P_{\text{FRR}} \le \exp\left(-2 \delta^2 L\right)$$
- **Repudiation Insecurity Bound**:
  $$P_{\text{rep}} \le 2 \exp\left(-\frac{1}{2}(s_v - s_a)^2 L\right)$$
- **Minimum Required Signature Length**:
  $$L_{\text{min}} \ge \left\lceil \frac{\ln(1/\epsilon)}{2 \delta^2} \right\rceil$$

---

## 💻 How to Run Stage 5 Demos & Tests

### 1. Run Interactive CLI Demonstration:
```powershell
python examples/stage5_demo.py
```

### 2. Run Automated Batch Suite:
```powershell
python examples/stage5_demo.py --batch
```

### 3. Launch Interactive Web Visualizer:
Open `visualizer/index.html` in any modern web browser.

### 4. Run Pytest Test Suite:
```powershell
pytest tests/test_teleportation_qds.py tests/test_security_bounds.py tests/test_stage4_threats.py -v
```
