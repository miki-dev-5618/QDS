"""
Run the isolated 3-qubit teleportation benchmark on IBM Quantum hardware.

Scope: ONLY the deferred-measurement teleportation circuit for the four input
states |0>, |1>, |+>, |->, with Bob's qubit measured in the preparation basis.
The full HEDWIG QDS protocol is NOT run on hardware.

    export IBM_QUANTUM_TOKEN=...                                  # never hardcode the token
    python experiments/hardware/run_ibm_teleport.py --dry-run      # local Aer simulator, no QPU time
    python experiments/hardware/run_ibm_teleport.py --shots 2000
    python experiments/hardware/run_ibm_teleport.py --shots 4000 --backend ibm_torino
    python experiments/hardware/run_ibm_teleport.py --job-id <job-id>   # re-download a finished job

The ``--job-id`` mode recovers a run whose submitting process died (closed
terminal, crash): it fetches the already-completed job, extracts the same counts
and writes the same result file without spending any QPU time.

All four state circuits are transpiled with ``optimization_level=1`` and
submitted as ONE SamplerV2 job (one PUB per state). The run is persisted to
``experiments/hardware/result_<timestamp>.json`` with the job id, backend name,
timestamp, execution parameters and the raw counts of every state; use
``compare_hw_vs_sim.py`` to compare that file against a noisy simulation.

Exit codes: 0 = result file written, 2 = bad arguments, missing token, missing
qiskit-ibm-runtime or execution failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.quantum_engine.teleportation import (  # noqa: E402
    TeleportJob,
    build_deferred_teleportation_circuit,
)

TOKEN_ENV = "IBM_QUANTUM_TOKEN"
DEFAULT_SHOTS = 2000
DEFAULT_OPTIMIZATION_LEVEL = 1
DEFAULT_CHANNEL = "ibm_quantum_platform"
DEFAULT_OUTPUT_DIR = HERE
MIN_QUBITS = 3
NUM_CLBITS = 3
SCHEMA_VERSION = 1

# (label, bit, basis), basis 0 = Z {"|0>", "|1>"}, 1 = X {"|+>", "|->"}.
STATES = (("0", 0, 0), ("1", 1, 0), ("+", 0, 1), ("-", 1, 1))


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Run the 3-qubit teleportation benchmark on IBM Quantum hardware.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--shots", type=int, default=DEFAULT_SHOTS,
                    help=f"shots per state (default {DEFAULT_SHOTS})")
    ap.add_argument("--dry-run", action="store_true",
                    help="run the whole pipeline on a local Aer simulator, no QPU time")
    ap.add_argument("--job-id", default=None,
                    help="download the results of an already-completed job instead of submitting a new one "
                         "(no QPU time; --shots is taken from the job)")
    ap.add_argument("--backend", default=None,
                    help="IBM backend name; default is the least busy operational backend with >= 3 qubits")
    ap.add_argument("--channel", default=os.environ.get("IBM_QUANTUM_CHANNEL", DEFAULT_CHANNEL),
                    help=f"IBM Quantum channel (default {DEFAULT_CHANNEL})")
    ap.add_argument("--seed", type=int, default=2026,
                    help="seed for the --dry-run simulator and transpiler (default 2026)")
    ap.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                    help="directory for result_<timestamp>.json")
    args = ap.parse_args(argv)
    if args.shots <= 0:
        ap.error("--shots must be positive")
    if args.job_id and args.dry_run:
        ap.error("--job-id and --dry-run are mutually exclusive")
    return args


# --------------------------------------------------------------------------
# Credentials and backend selection
# --------------------------------------------------------------------------
def get_token(env: Optional[Dict[str, str]] = None) -> str:
    """Read the IBM Quantum token from IBM_QUANTUM_TOKEN only (never a file or CLI flag)."""
    env = os.environ if env is None else env
    token = (env.get(TOKEN_ENV) or "").strip()
    if not token:
        raise RuntimeError(
            f"{TOKEN_ENV} is not set. Export your IBM Quantum token first, e.g.\n"
            f"    export {TOKEN_ENV}='<your-token>'\n"
            "Tokens are read from the environment only; they are never hardcoded or stored."
        )
    return token


def connect(token: str, channel: str = DEFAULT_CHANNEL):
    """Open a QiskitRuntimeService session for the given token."""
    from qiskit_ibm_runtime import QiskitRuntimeService

    return QiskitRuntimeService(channel=channel, token=token)


def _pending_jobs(backend) -> float:
    """Queue depth used to pick the least busy backend.

    A live ``IBMBackend`` has no ``pending_jobs`` attribute; it exposes the queue
    through ``status().pending_jobs``. Without that fallback every candidate looks
    equally busy and the first backend in the list wins.
    """
    pending = getattr(backend, "pending_jobs", None)
    if pending is None:
        status = getattr(backend, "status", None)
        if callable(status):
            pending = getattr(status(), "pending_jobs", None)
    return float("inf") if pending is None else float(pending)


def select_backend(service, name: Optional[str] = None, min_qubits: int = MIN_QUBITS):
    """Pick the requested backend, or the least busy operational backend with >= min_qubits."""
    if name:
        backend = service.backend(name)
    else:
        candidates = [
            b for b in service.backends(min_num_qubits=min_qubits, operational=True, simulator=False)
            if b.num_qubits >= min_qubits
        ]
        if not candidates:
            raise RuntimeError(f"No operational IBM backend with at least {min_qubits} qubits is available.")
        backend = min(candidates, key=_pending_jobs)
    if backend.num_qubits < min_qubits:
        raise RuntimeError(
            f"backend {backend.name!r} has {backend.num_qubits} qubits; "
            f"the teleportation benchmark needs at least {min_qubits} qubits."
        )
    return backend


# --------------------------------------------------------------------------
# Circuits, execution, counts
# --------------------------------------------------------------------------
def build_state_circuits(states: Sequence[tuple] = STATES) -> list:
    """Four deferred-measurement teleportation circuits, Bob measuring in the preparation basis."""
    circuits = []
    for index, (_label, bit, basis) in enumerate(states):
        qc = build_deferred_teleportation_circuit(TeleportJob(bit=bit, basis=basis, meas_basis=basis))
        qc.name = f"teleport_{index}"
        circuits.append(qc)
    return circuits


def transpile_circuits(circuits: Sequence, backend, optimization_level: int = DEFAULT_OPTIMIZATION_LEVEL,
                       seed: Optional[int] = None):
    """Transpile every circuit for one backend so they can be submitted together."""
    from qiskit import transpile

    return transpile(circuits, backend=backend, optimization_level=optimization_level, seed_transpiler=seed)


def normalise_counts(counts: Dict[str, int]) -> Dict[str, int]:
    """Bitstring counts only: strip register separators and accept 0x-prefixed keys."""
    normalised: Dict[str, int] = {}
    for key, value in counts.items():
        bitstring = str(key).replace(" ", "")
        if bitstring[:2].lower() == "0x":
            bitstring = format(int(bitstring, 16), f"0{NUM_CLBITS}b")
        if len(bitstring) != NUM_CLBITS:
            raise ValueError(f"unexpected counts key {key!r}: expected a {NUM_CLBITS}-bit string")
        normalised[bitstring] = normalised.get(bitstring, 0) + int(value)
    return normalised


def outcome_bit(bitstring: str) -> int:
    """Bob's outcome is clbit 2, i.e. the leftmost character of the counts key."""
    return int(bitstring.replace(" ", "")[0])


def success_count(counts: Dict[str, int], bit: int) -> int:
    """Shots whose measured bit matches the prepared basis state."""
    return sum(n for key, n in counts.items() if outcome_bit(key) == int(bit))


def extract_counts(pub_result, circuit) -> Dict[str, int]:
    """Pull the BitArray of the circuit's classical register out of a SamplerV2 pub result."""
    fields = list(pub_result.data.keys())
    if not fields:
        raise RuntimeError("SamplerV2 returned no classical data for a teleportation circuit.")
    creg_names = [creg.name for creg in getattr(circuit, "cregs", [])]
    field = next((candidate for candidate in creg_names if candidate in fields), fields[0])
    return normalise_counts(pub_result.data[field].get_counts())


def fetch_completed_job(service, job_id: str):
    """Retrieve an already-submitted job and refuse to proceed unless it finished."""
    try:
        job = service.job(job_id)
    except Exception as exc:  # unknown job id, wrong instance, expired retention
        raise RuntimeError(f"cannot retrieve job {job_id!r}: {exc}") from exc
    status = job.status()
    label = getattr(status, "name", str(status))
    if label.upper() != "DONE":
        raise RuntimeError(
            f"job {job_id} is {label}, not DONE. Wait for it to finish and re-run with the same --job-id."
        )
    return job


def counts_from_finished_job(job, circuits: Sequence, backend,
                             optimization_level: int = DEFAULT_OPTIMIZATION_LEVEL):
    """Extract one counts dict per state from a job that already ran on hardware."""
    transpiled = transpile_circuits(circuits, backend, optimization_level)
    result = job.result()
    if len(result) != len(transpiled):
        raise RuntimeError(
            f"job returned {len(result)} results for {len(transpiled)} circuits; "
            "was it submitted by this script?"
        )
    counts = [extract_counts(result[i], transpiled[i]) for i in range(len(transpiled))]
    return counts, transpiled


def job_timestamps(job) -> Optional[tuple]:
    """The job's creation time as (iso, compact) in UTC, or None if IBM does not report it."""
    from datetime import timezone

    created = getattr(job, "creation_date", None)
    if created is None:
        return None
    if created.tzinfo is None:  # IBM reports the creation date in local time
        created = created.astimezone()
    created = created.astimezone(timezone.utc)
    return created.strftime("%Y-%m-%dT%H:%M:%SZ"), created.strftime("%Y%m%dT%H%M%SZ")


def run_hardware(circuits: Sequence, backend, shots: int,
                 optimization_level: int = DEFAULT_OPTIMIZATION_LEVEL):
    """Submit all four state circuits as ONE SamplerV2 job and wait for the counts."""
    from qiskit_ibm_runtime import SamplerV2

    transpiled = transpile_circuits(circuits, backend, optimization_level)
    sampler = SamplerV2(mode=backend)
    job = sampler.run(transpiled, shots=shots)
    job_id = job.job_id()
    print(f"Submitted ONE SamplerV2 job {job_id} with {len(transpiled)} circuits "
          f"({shots} shots each); waiting for results...", flush=True)
    result = job.result()
    counts = [extract_counts(result[i], transpiled[i]) for i in range(len(transpiled))]
    return job_id, counts, transpiled


def local_reference_backend(seed: int = 42):
    """Generic local backend used only to rehearse transpilation during --dry-run.

    The width is exactly ``MIN_QUBITS`` (the 3 qubits the circuit needs): a wider
    surrogate would pad every transpiled circuit with idle qubits, so the recorded
    circuit metadata would no longer describe the teleportation circuit.
    """
    from qiskit.providers.fake_provider import GenericBackendV2

    return GenericBackendV2(num_qubits=MIN_QUBITS, seed=seed)


def run_local(circuits: Sequence, shots: int, seed: int,
              optimization_level: int = DEFAULT_OPTIMIZATION_LEVEL):
    """Rehearse the pipeline (transpile -> SamplerV2 -> counts) on an ideal local simulator."""
    from qiskit_aer.primitives import SamplerV2 as AerSampler

    backend = local_reference_backend(seed=seed)
    transpiled = transpile_circuits(circuits, backend, optimization_level, seed=seed)
    sampler = AerSampler(seed=seed, default_shots=shots)
    result = sampler.run(transpiled, shots=shots).result()
    counts = [extract_counts(result[i], transpiled[i]) for i in range(len(transpiled))]
    return counts, transpiled, backend.name


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
def utc_timestamps() -> tuple:
    now = time.gmtime()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", now), time.strftime("%Y%m%dT%H%M%SZ", now)


def summarise_state(label: str, bit: int, basis: int, circuit, counts: Dict[str, int]) -> dict:
    total = sum(counts.values())
    successes = success_count(counts, bit)
    return {
        "label": label,
        "bit": int(bit),
        "basis": int(basis),              # 0 = Z, 1 = X
        "measurement_basis": int(basis),  # Bob measures in the preparation basis
        "counts": {key: int(value) for key, value in sorted(counts.items())},
        "shots": int(total),
        "success_count": int(successes),
        "success_rate": round(successes / total, 6) if total else None,
        "circuit": {
            "name": circuit.name,
            "num_qubits": int(circuit.num_qubits),
            "num_clbits": int(circuit.num_clbits),
            "depth": int(circuit.depth()),
            "size": int(circuit.size()),
        },
    }


def build_payload(*, mode: str, backend_name: str, job_id: Optional[str], timestamp: str,
                  timestamp_compact: str, shots: int, optimization_level: int,
                  channel: Optional[str], seed: Optional[int], transpile_backend: Optional[str],
                  states: Sequence[dict]) -> dict:
    """The full result document: provenance first, then raw counts per state."""
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,  # "hardware" or "dry-run"
        "job_id": job_id,
        "backend_name": backend_name,
        "timestamp": timestamp,
        "timestamp_compact": timestamp_compact,
        "scope": "isolated 3-qubit teleportation benchmark; full QDS protocol NOT run on hardware",
        "execution": {
            "shots": int(shots),
            "optimization_level": int(optimization_level),
            "sampler": "SamplerV2",
            "channel": channel,
            "seed": seed,
            "transpile_backend": transpile_backend,
        },
        "states": list(states),
        "total_shots": int(sum(state["shots"] for state in states)),
    }


def write_result(payload: dict, output_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    """Write result_<timestamp>.json, never overwriting an earlier run."""
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, f"result_{payload['timestamp_compact']}")
    path = f"{base}.json"
    suffix = 2
    while os.path.exists(path):
        path = f"{base}_{suffix}.json"
        suffix += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return path


def print_report(payload: dict, path: str) -> None:
    print()
    print(f"Mode: {payload['mode']}  backend: {payload['backend_name']}  "
          f"job: {payload['job_id'] or 'n/a'}")
    print(f"Shots per state: {payload['execution']['shots']}")
    print(f"{'State':<10}{'Success rate':>14}{'Successes':>12}")
    for state in payload["states"]:
        rate = "n/a" if state["success_rate"] is None else f"{state['success_rate']:.4f}"
        print(f"|{state['label']}>".ljust(10) + f"{rate:>14}{state['success_count']:>12}")
    print(f"Saved {path}")
    if payload["mode"] != "hardware":
        print("NOTE: simulated result (no QPU time used); do not cite it as hardware evidence.")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    circuits = build_state_circuits()
    timestamp, timestamp_compact = utc_timestamps()
    shots = args.shots

    try:
        if args.job_id:
            service = connect(get_token(), args.channel)
            job = fetch_completed_job(service, args.job_id)
            backend = job.backend()
            print(f"Resuming finished job {args.job_id} on {backend.name}; no new QPU time used.", flush=True)
            counts, transpiled = counts_from_finished_job(job, circuits, backend)
            shots = max(sum(state_counts.values()) for state_counts in counts)
            mode, backend_name, job_id = "hardware", backend.name, args.job_id
            channel, seed, transpile_backend = args.channel, None, backend.name
            timestamp, timestamp_compact = job_timestamps(job) or (timestamp, timestamp_compact)
        elif args.dry_run:
            counts, transpiled, transpile_backend = run_local(
                circuits, args.shots, args.seed, DEFAULT_OPTIMIZATION_LEVEL)
            mode, backend_name, job_id, channel, seed = "dry-run", "aer_simulator", None, None, args.seed
        else:
            service = connect(get_token(), args.channel)
            backend = select_backend(service, args.backend)
            print(f"Selected backend {backend.name} ({backend.num_qubits} qubits, "
                  f"{_pending_jobs(backend)} pending jobs).", flush=True)
            job_id, counts, transpiled = run_hardware(circuits, backend, args.shots)
            mode, backend_name, channel, seed = "hardware", backend.name, args.channel, None
            transpile_backend = backend.name
    except ImportError as exc:
        print(f"error: hardware mode needs qiskit-ibm-runtime ({exc}).\n"
              "    python -m pip install -r experiments/hardware/requirements-hardware.txt",
              file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    states = [
        summarise_state(label, bit, basis, circuit, state_counts)
        for (label, bit, basis), circuit, state_counts in zip(STATES, transpiled, counts)
    ]
    payload = build_payload(
        mode=mode,
        backend_name=backend_name,
        job_id=job_id,
        timestamp=timestamp,
        timestamp_compact=timestamp_compact,
        shots=shots,
        optimization_level=DEFAULT_OPTIMIZATION_LEVEL,
        channel=channel,
        seed=seed,
        transpile_backend=transpile_backend,
        states=states,
    )
    path = write_result(payload, args.output_dir)
    print_report(payload, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
