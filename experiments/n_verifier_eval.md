# N-verifier extension: evaluation

Seed 2026, 40 trials per configuration, statevector backend, ChannelModel() default depolarising. Chain mode uses H = N - 1.

## Honest sessions

| L | N | delivery | events accepted (95% CI) | rejected | inconclusive | session outcomes | tokens planned | reserve | copies/verifier (min-max) | dist ms p50 | total ms p50 | audit bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 32 | 2 | direct | 0.9875 (0.9325, 0.9978) | 1 | 0 | all_accepted 39, rejected 1 | 154.0 | 28.0 | 32.0 (26-38) | 86.46 | 91.0 | 9088 |
| 32 | 2 | chain | 0.9873 (0.9317, 0.9978) | 1 | 0 | all_accepted 39, rejected 1 | 154.0 | 28.0 | 32.0 (26-38) | 85.49 | 94.28 | 11688 |
| 32 | 3 | direct | 1.0 (0.969, 1.0) | 0 | 0 | all_accepted 40 | 214.0 | 28.0 | 32.0 (20-43) | 116.98 | 123.17 | 10750 |
| 32 | 3 | chain | 1.0 (0.969, 1.0) | 0 | 0 | all_accepted 40 | 214.0 | 28.0 | 32.0 (20-43) | 112.07 | 124.33 | 16227 |
| 32 | 5 | direct | 0.995 (0.9722, 0.9991) | 1 | 0 | all_accepted 39, rejected 1 | 334.0 | 28.0 | 32.0 (22-46) | 179.03 | 188.32 | 14100 |
| 32 | 5 | chain | 0.995 (0.9722, 0.9991) | 1 | 0 | all_accepted 39, rejected 1 | 334.0 | 28.0 | 32.0 (22-46) | 177.56 | 197.93 | 25131 |
| 32 | 10 | direct | 1.0 (0.9905, 1.0) | 0 | 0 | all_accepted 40 | 634.0 | 28.0 | 32.0 (17-51) | 348.02 | 362.84 | 22406 |
| 32 | 10 | chain | 1.0 (0.9905, 1.0) | 0 | 0 | all_accepted 40 | 634.0 | 28.0 | 32.0 (17-51) | 336.43 | 374.12 | 48086 |
| 64 | 2 | direct | 1.0 (0.9542, 1.0) | 0 | 0 | all_accepted 40 | 162.0 | 0.0 | 64.0 (51-77) | 89.0 | 94.43 | 8877 |
| 64 | 2 | chain | 1.0 (0.9542, 1.0) | 0 | 0 | all_accepted 40 | 162.0 | 0.0 | 64.0 (51-77) | 100.49 | 106.89 | 11512 |
| 64 | 3 | direct | 1.0 (0.969, 1.0) | 0 | 0 | all_accepted 40 | 226.0 | 0.0 | 64.0 (47-80) | 151.63 | 157.55 | 10445 |
| 64 | 3 | chain | 1.0 (0.969, 1.0) | 0 | 0 | all_accepted 40 | 226.0 | 0.0 | 64.0 (47-80) | 146.95 | 156.53 | 15788 |
| 64 | 5 | direct | 1.0 (0.9812, 1.0) | 0 | 0 | all_accepted 40 | 354.0 | 0.0 | 64.0 (43-86) | 235.44 | 243.66 | 13586 |
| 64 | 5 | chain | 1.0 (0.9812, 1.0) | 0 | 0 | all_accepted 40 | 354.0 | 0.0 | 64.0 (43-86) | 237.84 | 252.92 | 24355 |
| 64 | 10 | direct | 1.0 (0.9905, 1.0) | 0 | 0 | all_accepted 40 | 674.0 | 0.0 | 64.0 (45-87) | 473.5 | 492.47 | 21389 |
| 64 | 10 | chain | 1.0 (0.9905, 1.0) | 0 | 0 | all_accepted 40 | 674.0 | 0.0 | 64.0 (45-87) | 494.95 | 522.64 | 46468 |

## Dishonest forwarder (first chain member alters, then forwards)

| N | alteration | altered package accepted by next recipient | rejection cause | classifications |
|---|---|---|---|---|
| 3 | message | 0/40 | {'digest': 40} | {'DISHONEST_VERIFIER_FORGERY': 40} |
| 3 | signature | 0/40 | {'commitment': 40} | {'DISHONEST_VERIFIER_FORGERY': 40} |
| 10 | message | 0/40 | {'digest': 40} | {'DISHONEST_VERIFIER_FORGERY': 40} |
| 10 | signature | 0/40 | {'commitment': 40} | {'DISHONEST_VERIFIER_FORGERY': 40} |

## Applied stage-1 limits by depth (exact policy)

| checked copies | H | limits for depth 0..H | all levels meet targets |
|---|---|---|---|
| 32 | 1 | [0, 0] | False |
| 32 | 3 | [0, 0, 0, 0] | False |
| 32 | 9 | [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] | False |
| 64 | 1 | [3, 3] | True |
| 64 | 3 | [3, 3, 3, 3] | True |
| 64 | 9 | [3, 3, 3, 3, 3, 3, 3, 3, 3, 3] | True |
| 128 | 1 | [4, 11] | True |
| 128 | 3 | [4, 6, 8, 11] | True |
| 128 | 9 | [4, 4, 5, 6, 7, 7, 8, 9, 10, 11] | True |
| 256 | 1 | [7, 28] | True |
| 256 | 3 | [7, 14, 21, 28] | True |
| 256 | 9 | [7, 9, 11, 14, 16, 18, 21, 23, 25, 28] | True |

## Notes

- Per-event statistics only; no session-level aggregate risk is claimed.
- Zero accepted attacks in finite trials is not a proof of zero forgery probability.
- Latency is simulator wall time on this host (statevector backend), not hardware timing.
