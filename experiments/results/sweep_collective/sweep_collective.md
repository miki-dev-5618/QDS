# One collective (ancilla-probe) attack: EVE_COLLECTIVE

**Scope:** one concrete collective attack (the same controlled-Ry(theta) probe on every token, ancillas measured individually after the bases are announced). This is not a proof of security against collective attacks in general.

Seed 2026, 3 trials per cell, statevector backend, depolarizing p=0.01. Rates with 95% Wilson intervals.

## Detection rate

| theta | L=16 |
|---|---|
| 0.0000 | 0.000 [0.000, 0.561] |
| 1.5708 | 0.667 [0.208, 0.939] |

## Disturbance vs information (pooled over L)

| theta | verifier mismatch rate | Eve bit-guess accuracy |
|---|---|---|
| 0.0000 | 0.0000 [0.0000, 0.0385] | 0.4688 [0.3721, 0.5678] |
| 1.5708 | 0.0312 [0.0107, 0.0879] | 0.7083 [0.6108, 0.7898] |
