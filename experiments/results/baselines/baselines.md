# Baselines: HEDWIG vs simpler alternatives

Seed 2026, statevector backend, depolarizing p=0.01. 5 trials per per-transmission cell; 2 sequences of 10 transmissions (60 s apart) per sequence cell. Generated 2026-10-30 18:04:39.

Systems: (a) fixed 11% QBER cutoff; (b) HEDWIG, no circuit breaker; (c) full HEDWIG. Per-transmission rows are identical for (b) and (c): the breaker only changes later traffic.

*Best* lists every system whose 95% CI overlaps the best system's CI (a tie is reported as a tie).

## L = 16

| metric | scenario | better | (a) fixed 11% QBER cutoff | (b) HEDWIG, no circuit breaker | (c) full HEDWIG | best |
|---|---|---|---|---|---|---|
| honest false alarm | honest | lower | 0.200 [0.036, 0.625] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | all tied |
| attack caught | eve_forgery | higher | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | all tied |
| correct attribution | eve_forgery | higher | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | all tied |
| attack caught | eve_intercept | higher | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | all tied |
| correct attribution | eve_intercept | higher | 0.800 [0.376, 0.964] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | all tied |
| tokens sent per attacked tx | eve_intercept | lower | 48.0 [48.0, 48.0] | 59.6 [48.08, 71.12] | 59.6 [48.08, 71.12] | (a) |
| attack caught | weak_intercept_f0.2 | higher | 0.800 [0.376, 0.964] | 0.400 [0.118, 0.769] | 0.400 [0.118, 0.769] | all tied |
| correct attribution | weak_intercept_f0.2 | higher | 0.400 [0.118, 0.769] | 0.200 [0.036, 0.625] | 0.200 [0.036, 0.625] | all tied |
| tokens sent per attacked tx | weak_intercept_f0.2 | lower | 48.0 [48.0, 48.0] | 98.0 [98.0, 98.0] | 98.0 [98.0, 98.0] | (a) |
| attack caught | repudiation | higher | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | all tied |
| correct attribution | repudiation | higher | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | all tied |
| correct attribution | all attacks | higher | 0.800 [0.584, 0.919] | 0.800 [0.584, 0.919] | 0.800 [0.584, 0.919] | all tied |
| honest blocked after one forged package (DoS) | forgery_injection | lower | 0.100 [0.018, 0.404] | 0.000 [0.000, 0.278] | 1.000 [0.723, 1.000] | (a), (b) |
| signer tx accepted while tapped (exposure) | tapped_f0.2 | lower | 0.250 [0.112, 0.469] | 0.550 [0.342, 0.742] | 0.050 [0.009, 0.236] | (a), (c) |

Where a baseline wins, the table says so: the circuit breaker trades availability (honest traffic blocked after an attack) for exposure (traffic accepted on a tapped link). No admin reset is modelled inside a sequence, so a quarantine blocks the rest of it.
