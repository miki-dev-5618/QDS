# One-tier vs two-tier attribution sweep

Seed 2026, 5 trials per cell, statevector backend. Generated 2026-10-30 18:03:50. Both rules label the same runs; rejection decisions are identical, only attribution differs.

*Correct* = label matches ground truth (honest: accepted; intercept: channel; dishonest signer: signature). *Wrong attribution* = a confident label of the wrong cause (for honest runs: any attack label). *Undetermined* = V2.2 abstains (still rejected, response WATCH unless evidence is strong).

| L | condition | V2.1 correct | V2.2 correct | V2.1 wrong attribution | V2.2 wrong attribution | V2.2 undetermined | quarantined (V2.2 policy) |
|---|---|---|---|---|---|---|---|
| 16 | honest p=0.005 | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] |
| 16 | honest p=0.01 | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] |
| 16 | honest p=0.03 (QBER=e0) | 0.800 [0.376, 0.964] | 0.800 [0.376, 0.964] | 0.200 [0.036, 0.624] | 0.000 [0.000, 0.434] | 0.200 [0.036, 0.624] | 0.000 [0.000, 0.434] |
| 16 | honest + bursts | 0.800 [0.376, 0.964] | 0.800 [0.376, 0.964] | 0.200 [0.036, 0.624] | 0.200 [0.036, 0.624] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] |
| 16 | intercept 25% | 0.200 [0.036, 0.624] | 0.400 [0.118, 0.769] | 0.200 [0.036, 0.624] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] |
| 16 | intercept 50% | 0.200 [0.036, 0.624] | 0.400 [0.118, 0.769] | 0.600 [0.231, 0.882] | 0.000 [0.000, 0.434] | 0.400 [0.118, 0.769] | 0.200 [0.036, 0.624] |
| 16 | intercept 100% | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.800 [0.376, 0.964] |
| 16 | dishonest signer | 0.800 [0.376, 0.964] | 0.800 [0.376, 0.964] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.800 [0.376, 0.964] |

Benefit of Tier 2 = fewer wrong attributions; cost = abstentions where V2.1 guessed (sometimes correctly). Both are shown; neither is hidden.
