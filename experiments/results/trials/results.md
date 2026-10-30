# HEDWIG V2.2 experiment results

Seed 2026, 5 trials per cell, backend `statevector`, honest depolarising p=0.01 (expected QBER 0.0067). Generated 2026-10-30 18:03:47.

Rates are fractions with 95% Wilson intervals. *Injected* is the scenario the attack generator ran; *flagged* and *correct class* are what the blind detector concluded from observations. *Abstained* counts `UNDETERMINED_DISTURBANCE` (rejected, cause not attributable at this size). *Elimination rejects* counts runs where at least one verifier's quantum elimination check failed on its own (separate from the classical binding/replay checks). *Watch/quarantine* is the response policy's action for future traffic; the transmission itself is rejected whenever it is flagged.

## Detection, attribution and response

| L | injected | flagged as threat | correct class | abstained | elimination rejects | Bob accepts | Charlie accepts | watch | quarantine | early abort (tokens saved) | detect µs p50 | classes seen |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | authentic | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 89.3 | BENIGN_AUTHENTIC: 4, CHANNEL_NOISE: 1 |
| 16 | eve_forgery | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 100.7 | EXTERNAL_FORGERY: 5 |
| 16 | dishonest_bob | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 69.3 | DISHONEST_VERIFIER_FORGERY: 5 |
| 16 | eve_intercept | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.600 [0.231, 0.882] (24%) | 71.2 | EAVESDROPPING_TAMPERING: 5 |
| 16 | message_tampering | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 87.4 | MESSAGE_INTEGRITY_VIOLATION: 5 |
| 16 | repudiation | 0.800 [0.376, 0.964] | 0.800 [0.376, 0.964] | 0.000 [0.000, 0.434] | 0.800 [0.376, 0.964] | 0.200 [0.036, 0.624] | 0.200 [0.036, 0.624] | 0.200 [0.036, 0.624] | 0.600 [0.231, 0.882] | 0.000 [0.000, 0.434] | 89.9 | REPUDIATION_ATTEMPT: 4, BENIGN_AUTHENTIC: 1 |
| 16 | replay | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.400 [0.118, 0.769] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 32.5 | REPLAY_ATTACK: 5 |
| 16 | impersonation | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 31.4 | IMPERSONATION_ATTACK: 5 |
| 16 | eve_loss_exploit | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.400 [0.118, 0.769] | 0.600 [0.231, 0.882] | 1.000 [0.566, 1.000] | 67.4 | EAVESDROPPING_TAMPERING: 4, INSUFFICIENT_TOKENS: 1 |
| 16 | eve_cloning | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.200 [0.036, 0.624] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 0.800 [0.376, 0.964] (37%) | 84.9 | EAVESDROPPING_TAMPERING: 4, EXTERNAL_FORGERY: 1 |
| 16 | eve_partial_intercept | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 93.6 | CHANNEL_NOISE: 5 |
| 16 | eve_collective | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 1.000 [0.566, 1.000] | 1.000 [0.566, 1.000] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 0.000 [0.000, 0.434] | 92.2 | CHANNEL_NOISE: 4, BENIGN_AUTHENTIC: 1 |

For `authentic`, *flagged as threat* is the false-rejection rate and *quarantine* the immediate false lock-out rate. For attacks, 1 − flagged is the miss rate.

## False lock-out over honest sequences

Each trial sends 3 honest transmissions in a row on one engine (so WATCH escalation can occur). Reported: fraction of sequences in which the link was ever quarantined.

| L | trials | runs per trial | ever quarantined |
|---|---|---|---|
| 16 | 3 | 3 | 0.000 [0.000, 0.562] |

Zero observed events in N trials bounds the rate only to about 3/N (95%); these tables are empirical rates, not the 10⁻⁶ guarantees of the original innovation claims.
