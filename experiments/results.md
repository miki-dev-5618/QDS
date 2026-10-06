# HEDWIG V2.2 experiment results

Seed 2026, 200 trials per cell, backend `statevector`, honest depolarising p=0.01 (expected QBER 0.0067). Generated 2026-09-28 19:34:43.

Rates are fractions with 95% Wilson intervals. *Injected* is the scenario the attack generator ran; *flagged* and *correct class* are what the blind detector concluded from observations. *Abstained* counts `UNDETERMINED_DISTURBANCE` (rejected, cause not attributable at this size). *Elimination rejects* counts runs where at least one verifier's quantum elimination check failed on its own (separate from the classical binding/replay checks). *Watch/quarantine* is the response policy's action for future traffic; the transmission itself is rejected whenever it is flagged.

## Detection, attribution and response

| L | injected | flagged as threat | correct class | abstained | elimination rejects | Bob accepts | Charlie accepts | watch | quarantine | early abort (tokens saved) | detect µs p50 | classes seen |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | authentic | 0.030 [0.014, 0.064] | 0.970 [0.936, 0.986] | 0.030 [0.014, 0.064] | 0.030 [0.014, 0.064] | 0.980 [0.950, 0.992] | 0.990 [0.964, 0.997] | 0.030 [0.014, 0.064] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 147.4 | BENIGN_AUTHENTIC: 168, CHANNEL_NOISE: 26, UNDETERMINED_DISTURBANCE: 6 |
| 16 | eve_forgery | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.050 [0.027, 0.090] | 0.950 [0.910, 0.973] | 0.000 [0.000, 0.019] | 197.2 | EXTERNAL_FORGERY: 200 |
| 16 | dishonest_bob | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.880 [0.828, 0.918] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 78.4 | DISHONEST_VERIFIER_FORGERY: 200 |
| 16 | eve_intercept | 0.985 [0.957, 0.995] | 0.910 [0.862, 0.942] | 0.075 [0.046, 0.120] | 0.200 [0.150, 0.261] | 0.050 [0.027, 0.090] | 0.050 [0.027, 0.090] | 0.335 [0.273, 0.403] | 0.650 [0.582, 0.713] | 0.285 [0.227, 0.351] (33%) | 65.2 | EAVESDROPPING_TAMPERING: 182, UNDETERMINED_DISTURBANCE: 15, CHANNEL_NOISE: 3 |
| 16 | message_tampering | 1.000 [0.981, 1.000] | 0.965 [0.930, 0.983] | 0.000 [0.000, 0.019] | 0.035 [0.017, 0.070] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.035 [0.017, 0.070] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 68.2 | MESSAGE_INTEGRITY_VIOLATION: 193, EXTERNAL_FORGERY: 7 |
| 16 | repudiation | 0.985 [0.957, 0.995] | 0.365 [0.301, 0.434] | 0.615 [0.546, 0.680] | 0.985 [0.957, 0.995] | 0.180 [0.133, 0.239] | 0.170 [0.124, 0.228] | 0.335 [0.273, 0.403] | 0.650 [0.582, 0.713] | 0.000 [0.000, 0.019] | 90.2 | UNDETERMINED_DISTURBANCE: 123, REPUDIATION_ATTEMPT: 73, BENIGN_AUTHENTIC: 2, EAVESDROPPING_TAMPERING: 1, CHANNEL_NOISE: 1 |
| 16 | replay | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 27.4 | REPLAY_ATTACK: 200 |
| 16 | impersonation | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 25.4 | IMPERSONATION_ATTACK: 200 |
| 32 | authentic | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 80.1 | BENIGN_AUTHENTIC: 129, CHANNEL_NOISE: 71 |
| 32 | eve_forgery | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.005 [0.001, 0.028] | 0.995 [0.972, 0.999] | 0.000 [0.000, 0.019] | 117.7 | EXTERNAL_FORGERY: 200 |
| 32 | dishonest_bob | 1.000 [0.981, 1.000] | 0.995 [0.972, 0.999] | 0.000 [0.000, 0.019] | 0.955 [0.917, 0.976] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.005 [0.001, 0.028] | 0.995 [0.972, 0.999] | 0.000 [0.000, 0.019] | 86.7 | DISHONEST_VERIFIER_FORGERY: 199, EAVESDROPPING_TAMPERING: 1 |
| 32 | eve_intercept | 1.000 [0.981, 1.000] | 0.985 [0.957, 0.995] | 0.000 [0.000, 0.019] | 0.015 [0.005, 0.043] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.045 [0.024, 0.083] | 0.955 [0.917, 0.976] | 0.765 [0.702, 0.818] (39%) | 69.1 | EAVESDROPPING_TAMPERING: 197, REPUDIATION_ATTEMPT: 3 |
| 32 | message_tampering | 1.000 [0.981, 1.000] | 0.995 [0.972, 0.999] | 0.000 [0.000, 0.019] | 0.005 [0.001, 0.028] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.005 [0.001, 0.028] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 79.6 | MESSAGE_INTEGRITY_VIOLATION: 199, EXTERNAL_FORGERY: 1 |
| 32 | repudiation | 0.985 [0.957, 0.995] | 0.905 [0.856, 0.938] | 0.075 [0.046, 0.120] | 0.985 [0.957, 0.995] | 0.125 [0.086, 0.178] | 0.105 [0.070, 0.155] | 0.080 [0.050, 0.126] | 0.905 [0.856, 0.938] | 0.000 [0.000, 0.019] | 117.9 | REPUDIATION_ATTEMPT: 181, UNDETERMINED_DISTURBANCE: 15, CHANNEL_NOISE: 3, EAVESDROPPING_TAMPERING: 1 |
| 32 | replay | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 29.1 | REPLAY_ATTACK: 200 |
| 32 | impersonation | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 25.4 | IMPERSONATION_ATTACK: 200 |
| 64 | authentic | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 108.0 | CHANNEL_NOISE: 121, BENIGN_AUTHENTIC: 79 |
| 64 | eve_forgery | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 168.1 | EXTERNAL_FORGERY: 200 |
| 64 | dishonest_bob | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.985 [0.957, 0.995] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 114.8 | DISHONEST_VERIFIER_FORGERY: 200 |
| 64 | eve_intercept | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.975 [0.943, 0.989] (46%) | 82.7 | EAVESDROPPING_TAMPERING: 200 |
| 64 | message_tampering | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 108.5 | MESSAGE_INTEGRITY_VIOLATION: 200 |
| 64 | repudiation | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.020 [0.008, 0.050] | 0.050 [0.027, 0.090] | 0.000 [0.000, 0.019] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 174.4 | REPUDIATION_ATTEMPT: 200 |
| 64 | replay | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 29.8 | REPLAY_ATTACK: 200 |
| 64 | impersonation | 1.000 [0.981, 1.000] | 1.000 [0.981, 1.000] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 0.000 [0.000, 0.019] | 25.2 | IMPERSONATION_ATTACK: 200 |

For `authentic`, *flagged as threat* is the false-rejection rate and *quarantine* the immediate false lock-out rate. For attacks, 1 − flagged is the miss rate.

## False lock-out over honest sequences

Each trial sends 10 honest transmissions in a row on one engine (so WATCH escalation can occur). Reported: fraction of sequences in which the link was ever quarantined.

| L | trials | runs per trial | ever quarantined |
|---|---|---|---|
| 16 | 200 | 10 | 0.040 [0.020, 0.077] |
| 32 | 200 | 10 | 0.000 [0.000, 0.019] |
| 64 | 200 | 10 | 0.000 [0.000, 0.019] |

Zero observed events in N trials bounds the rate only to about 3/N (95%); these tables are empirical rates, not the 10⁻⁶ guarantees of the original innovation claims.
