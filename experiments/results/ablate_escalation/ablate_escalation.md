# Ablation: Fisher escalation vs simple counter

Seed 2026, statevector backend, depolarizing p=0.01, k=3, 60 s between transmissions (WATCH window 900 s). Generated 2026-10-30 18:04:32. Every rule sees the same seeded runs.

## Honest long runs: false quarantine

| L | rule | runs x transmissions | false quarantine [95% Wilson] | mean weak alerts / run |
|---|---|---|---|---|
| 16 | Fisher + k-strike (default) | 4 x 40 | 0.000 [0.000, 0.490] | 0.0 |
| 16 | Fisher only | 4 x 40 | 0.000 [0.000, 0.490] | 0.0 |
| 16 | k-alert counter | 4 x 40 | 0.000 [0.000, 0.490] | 0.0 |

## Attack runs: transmissions until QUARANTINE

Censored runs (no quarantine within the cap of 40) are counted at the cap, so means/medians with censored runs are lower bounds. CIs: seeded bootstrap (2000 resamples).

| L | condition | rule | runs | mean [95% CI] | median [95% CI] | censored |
|---|---|---|---|---|---|---|
| 16 | intercept f=0.2 | Fisher + k-strike (default) | 4 | 5.0 [3.25, 7.75] | 4 [3, 9] | 0 |
| 16 | intercept f=1 | Fisher + k-strike (default) | 4 | 1.0 [1.0, 1.0] | 1 [1, 1] | 0 |
| 16 | intercept f=0.2 | Fisher only | 4 | 5.0 [3.25, 7.75] | 4 [3, 9] | 0 |
| 16 | intercept f=1 | Fisher only | 4 | 1.0 [1.0, 1.0] | 1 [1, 1] | 0 |
| 16 | intercept f=0.2 | k-alert counter | 4 | 7.0 [5.25, 9.75] | 6 [5, 11] | 0 |
| 16 | intercept f=1 | k-alert counter | 4 | 1.0 [1.0, 1.0] | 1 [1, 1] | 0 |
