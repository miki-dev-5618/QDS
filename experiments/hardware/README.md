# IBM hardware benchmark: 3-qubit teleportation

**Scope:** this directory runs *only* the isolated 3-qubit deferred-measurement
teleportation circuit for the four input states `|0>`, `|1>`, `|+>`, `|->`.
**The full HEDWIG QDS protocol is NOT run on hardware.** The protocol layer keeps
running on the simulator (`statevector`, `qiskit`, `ibm_fake`) exactly as before;
nothing in `src/quantum_engine/` changes behaviour because of these scripts.

## What is executed

Four circuits, one per input state, all built by
`src.quantum_engine.teleportation.build_deferred_teleportation_circuit`:

```
q0: prep(bit, basis) --■-- H -- ... -- M
q1: H --■------------------- ... -- M
q2: ----X -- CX(1,2) -- CZ(0,2) -- (H if X basis) -- M   <- Bob's outcome
```

The corrections `X^m2 Z^m1` are applied as coherent `CX`/`CZ` gates *before*
measurement (deferred measurement), so the circuit contains no mid-circuit
measurement and no classical feed-forward. That makes it executable on current
IBM hardware. Bob measures in the preparation basis: a Hadamard is applied to
`q2` for `|+>` and `|->`.

Each circuit is transpiled with `optimization_level=1`. All four are submitted
in **one** `SamplerV2` job (one PUB per state).

## Setup (hardware mode only)

```bash
python -m pip install -r experiments/hardware/requirements-hardware.txt
```

`qiskit-ibm-runtime` is intentionally **not** added to the project's main
`requirements.txt`, so the simulation demo keeps its existing dependency set.
Install a `qiskit-ibm-runtime` release that supports the pinned `qiskit` 2.5.2.

The token is read from the environment only — never hardcoded, never passed on
the command line:

```bash
export IBM_QUANTUM_TOKEN='<your-token>'          # bash / Git Bash / Linux / macOS
# $env:IBM_QUANTUM_TOKEN = "<your-token>"        # PowerShell
```

Optional: `IBM_QUANTUM_CHANNEL` (default `ibm_quantum_platform`) or `--channel`.

## 1. Dry run (no QPU time, no token)

Rehearses the whole pipeline - transpile, one multi-circuit `SamplerV2` run,
count extraction, JSON write - on an ideal local Aer simulator, seeded and
therefore reproducible:

```bash
python experiments/hardware/run_ibm_teleport.py --dry-run --shots 2000
```

Writes `experiments/hardware/result_<timestamp>.json` with `"mode": "dry-run"`
and `"job_id": null`. Dry-run guesses are ideal, so success rates are ~1.0; that
verifies plumbing, not hardware.

## 2. Hardware run

```bash
python experiments/hardware/run_ibm_teleport.py --shots 2000
python experiments/hardware/run_ibm_teleport.py --shots 4000 --backend ibm_torino
```

Without `--backend` the script queries `QiskitRuntimeService.backends(
min_num_qubits=3, operational=True, simulator=False)` and picks the one with the
fewest pending jobs.

### Recovering a finished job (no QPU time)

If the submitting process dies (closed terminal, crash) before it writes the JSON,
the job itself still finishes on IBM's side. Download it instead of resubmitting:

```bash
python experiments/hardware/run_ibm_teleport.py --job-id <job-id>
```

This fetches the completed job, extracts the same counts, and writes the same
`result_<timestamp>.json` (timestamped with the job's creation time). It spends no
QPU time, and it fails with exit code 2 if the job is not `DONE` yet.

## 3. Hardware vs simulation

```bash
python experiments/hardware/compare_hw_vs_sim.py experiments/hardware/result_<timestamp>.json
```

Rebuilds the logical circuits from the result file's `states` block, resolves
the fake backend from the stored `backend_name`
(`src.quantum_engine.teleportation.get_fake_backend`), transpiles once with the
stored `optimization_level`, and runs the same circuits on Aer twice: with
`NoiseModel.from_backend(fake_backend)` and noiselessly.

If `qiskit_ibm_runtime` is not installed its calibration-backed fake provider is
missing; the script then falls back to a generic surrogate backend and prints
`generic surrogate ... NOT <device> calibration` in the header. Never quote that
column as the device's calibrated noise.

## Comparison matrix template

`compare_hw_vs_sim.py` prints exactly this layout (filled from the run, never
hand-written):

```
State    | Hardware Success Rate | Simulated Success Rate | Ideal Success Rate
---------+-----------------------+------------------------+-------------------
|0>      | <hw>                  | <sim>                  | <ideal>
|1>      | <hw>                  | <sim>                  | <ideal>
|+>      | <hw>                  | <sim>                  | <ideal>
|->      | <hw>                  | <sim>                  | <ideal>
```

"Success rate" = fraction of shots whose measured `q2` bit equals the encoded
bit of the state (`|0>` -> 0, `|1>` -> 1, `|+>` -> 0, `|->` -> 1) with Bob
measuring in the matching basis. Ideal is 1.0 per state.

The same table in Markdown:

| State | Hardware Success Rate | Simulated Success Rate | Ideal Success Rate |
|-------|-----------------------|------------------------|--------------------|
| \|0>  | `<hw>`                | `<sim>`                | `<ideal>`          |
| \|1>  | `<hw>`                | `<sim>`                | `<ideal>`          |
| \|+>  | `<hw>`                | `<sim>`                | `<ideal>`          |
| \|->  | `<hw>`                | `<sim>`                | `<ideal>`          |

## Result file schema

```json
{
  "schema_version": 1,
  "mode": "hardware",
  "job_id": "cw...",
  "backend_name": "ibm_torino",
  "timestamp": "2026-10-26T12:00:00Z",
  "timestamp_compact": "20261026T120000Z",
  "scope": "isolated 3-qubit teleportation benchmark; full QDS protocol NOT run on hardware",
  "execution": {
    "shots": 2000,
    "optimization_level": 1,
    "sampler": "SamplerV2",
    "channel": "ibm_quantum_platform",
    "seed": null,
    "transpile_backend": "ibm_torino"
  },
  "states": [
    {
      "label": "0", "bit": 0, "basis": 0, "measurement_basis": 0,
      "counts": {"000": 1900, "001": 30, "010": 40, "011": 30},
      "shots": 2000, "success_count": 1930, "success_rate": 0.965,
      "circuit": {"name": "teleport_0", "num_qubits": 3, "num_clbits": 3, "depth": 9, "size": 12}
    }
  ],
  "total_shots": 8000
}
```

`basis` is 0 (Z: `|0>`, `|1>`) or 1 (X: `|+>`, `|->`). Counts keys are
3-bit strings, `c2 c1 c0`, where the leftmost bit `c2` is Bob's outcome.
`mode` is `"dry-run"` for simulated runs. All numbers in the sample document
(counts, success count, depth, size) illustrate the schema only - never cite
them; only a real `result_<timestamp>.json` is evidence.

## Hardware claim disclaimer template

> Teleportation of 4 input states was run on IBM `<backend>` on `<date>`
> (`<N>` shots); measured success rates were `<...>`. The full QDS protocol was
> NOT run on hardware.

## Tests

```bash
python -m pytest tests/test_ibm_hardware.py -q
```

The tests cover token handling, backend selection, circuit/shape invariants,
`--dry-run` reproducibility, JSON serialisation and the comparison matrix. They
use the local simulator only: no token, no network, no QPU time.
