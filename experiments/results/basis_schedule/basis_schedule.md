# Basis-schedule experiment (exploratory)

Seed 2026, 5 trials per cell, depolarising p=0.01, equal qubit budgets. Generated 2026-10-30 18:03:53. See the module docstring of `experiments/basis_schedule.py` for the adversary model.

| L | schedule | Eve tap fraction | Tier 1 alarm | binding rejects forgery | quantum layer rejects | quantum layer alone would accept | mean contradiction rate |
|---|---|---|---|---|---|---|---|
| 32 | random | 0.0 | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.2219 |
| 32 | random | 0.25 | 0.200 [0.036, 0.624] | 1.000 [0.510, 1.000] | 1.000 [0.510, 1.000] | 0.000 [0.000, 0.490] | 0.2695 |
| 32 | random | 0.5 | 0.400 [0.118, 0.769] | 1.000 [0.438, 1.000] | 1.000 [0.438, 1.000] | 0.000 [0.000, 0.562] | 0.2656 |
| 32 | random | 1.0 | 1.000 [0.566, 1.000] | — | — | — | None |
| 32 | public_hash | 0.0 | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.2219 |
| 32 | public_hash | 0.25 | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.1531 |
| 32 | public_hash | 0.5 | 0.800 [0.376, 0.964] | 1.000 [0.207, 1.000] | 1.000 [0.207, 1.000] | 0.000 [0.000, 0.793] | 0.125 |
| 32 | public_hash | 1.0 | 1.000 [0.566, 1.000] | — | — | — | None |
| 32 | keyed_hmac | 0.0 | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.2219 |
| 32 | keyed_hmac | 0.25 | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.1969 |
| 32 | keyed_hmac | 0.5 | 0.800 [0.376, 0.964] | 1.000 [0.207, 1.000] | 1.000 [0.207, 1.000] | 0.000 [0.000, 0.793] | 0.2969 |
| 32 | keyed_hmac | 1.0 | 1.000 [0.566, 1.000] | — | — | — | None |

Rates for the forgery columns are over runs that were not aborted by Tier 1.
