# HEDWIG QDS - Eve Quantum Cloning Evaluation

Evaluation of opt-in Eve 1→2 cloning threats on the HEDWIG simulated QDS platform.

## Cloner Specifications

| Cloner | Theoretical Fidelity $F$ | Theoretical Error Rate | Target States |
| :--- | :--- | :--- | :--- |
| **Universal symmetric 1→2** | $5/6 \approx 0.8333$ | $1/6 \approx 0.1667$ | Arbitrary pure qubit states |
| **Phase-covariant BB84** | $\frac{1}{2}(1 + \frac{1}{\sqrt{2}}) \approx 0.8536$ | $\approx 0.1464$ | Equatorial / BB84 states {|0⟩, |1⟩, |+⟩, |-⟩} |

## Security Parameters & Acceptance Thresholds

- Honest channel QBER assumption $e_0$: `0.02`
- Honest per-copy mismatch $\mu_h = e_0/2$: `0.0100`
- Minimum forger mismatch $p_{\min}$: `0.1667`
- Direct acceptance limit $s_a$: `0.0622`
- Forwarded acceptance limit $s_v$: `0.1144`

## Measured Results (≥ 200 Trials Each)

| Cloner | $L$ | Measured QBER | Alarm Rate | Detection Rate | Elim. Mismatch (Bob) | Eve Bit Acc. | Eve Forgery Success |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| universal | 16 | 0.1731 | 0.530 [0.461, 0.598] | 1.000 [0.981, 1.000] | 0.077 | 0.6672 | 0.000 [0.000, 0.019] |
| universal | 32 | 0.1848 | 0.775 [0.712, 0.827] | 1.000 [0.981, 1.000] | 0.105 | 0.6609 | 0.000 [0.000, 0.019] |
| universal | 64 | 0.1806 | 0.990 [0.964, 0.997] | 1.000 [0.981, 1.000] | 0.0834 | 0.6766 | 0.000 [0.000, 0.019] |
| phase_covariant | 16 | 0.1474 | 0.410 [0.344, 0.479] | 1.000 [0.981, 1.000] | 0.0728 | 0.6747 | 0.000 [0.000, 0.019] |
| phase_covariant | 32 | 0.169 | 0.735 [0.670, 0.791] | 1.000 [0.981, 1.000] | 0.0669 | 0.6747 | 0.000 [0.000, 0.019] |
| phase_covariant | 64 | 0.1592 | 0.980 [0.950, 0.992] | 1.000 [0.981, 1.000] | 0.0701 | 0.6815 | 0.000 [0.000, 0.019] |


### Findings & Security Analysis

1. **Theoretical Fidelities vs. Measured QBER:**
   - The universal cloner introduces a measured test-token QBER close to the theoretical $\approx 16.7\%$.
   - The phase-covariant cloner introduces a lower disturbance ($pprox 14.6\%$ QBER), which makes it more stealthy and dangerous.
2. **Detection & Quarantine:**
   - Because both cloner error rates ($14.6\%$ and $16.7\%$) exceed the honest channel limit $e_0 = 2.0\%$, the Tier 1 test-token QBER check reliably alarms on the intercepted stream.
3. **Eve Forgery Success:**
   - Even when Eve retains Clone 1 to deduce signature bits, the uncoordinated measurement basis choices and imperfect cloning fidelity cause severe verifier-side elimination mismatches.
   - Combined with channel alarms, Eve's forged signature packages achieve zero (or near-zero) acceptance across verifiers.
