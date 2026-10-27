"""
Compare a saved IBM hardware run against the matching Aer fake-backend noise model.

    python experiments/hardware/compare_hw_vs_sim.py experiments/hardware/result_20261026T120000Z.json
    python experiments/hardware/compare_hw_vs_sim.py result_<timestamp>.json --shots 4000 --seed 2026

The logical circuits are rebuilt from the ``states`` block of the result file
(so the states and bases compared are exactly the ones that ran), transpiled
once for the fake backend with the result file's ``optimization_level``, then
executed twice on Aer: once with ``NoiseModel.from_backend(fake_backend)`` and
once noiselessly for the ideal column.

The fake backend is resolved from the hardware backend name via
``src.quantum_engine.teleportation.get_fake_backend``. If ``qiskit_ibm_runtime``
(and therefore its calibration-backed fake provider) is not installed, a
generic surrogate backend is used and the header says so; the printed numbers
must not be described as that device's calibrated noise.

Exit codes: 0 = matrix printed, 1 = result file missing or unreadable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for entry in (HERE, ROOT):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from run_ibm_teleport import (  # noqa: E402
    DEFAULT_OPTIMIZATION_LEVEL,
    normalise_counts,
    success_count,
)

from src.quantum_engine.teleportation import (  # noqa: E402
    TeleportJob,
    build_deferred_teleportation_circuit,
    get_fake_backend,
)


# --------------------------------------------------------------------------
# Result file -> circuits
# --------------------------------------------------------------------------
def load_result(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        record = json.load(f)
    if not isinstance(record, dict) or not record.get("states"):
        raise ValueError("no 'states' entries in the result file")
    return record


def circuits_from_record(record: dict) -> List:
    """Rebuild the logical circuits that produced the stored counts."""
    circuits = []
    for index, state in enumerate(record["states"]):
        bit = int(state["bit"])
        basis = int(state.get("basis", 0))
        qc = build_deferred_teleportation_circuit(TeleportJob(bit=bit, basis=basis, meas_basis=basis))
        stored_name = (state.get("circuit") or {}).get("name")
        qc.name = stored_name or f"teleport_{index}"
        circuits.append(qc)
    return circuits


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------
def backend_name(backend) -> str:
    name = getattr(backend, "name", None)
    return name() if callable(name) else (name or "unknown")


def resolve_backend(requested: Optional[str]):
    """The fake backend that should reproduce the hardware backend's noise."""
    return get_fake_backend(requested)


def _device_stem(name: Optional[str]) -> str:
    """"ibm_fez" and "fake_fez" are the same device for matching purposes."""
    stem = (name or "").lower()
    for prefix in ("ibm_", "fake_"):
        while stem.startswith(prefix):
            stem = stem[len(prefix):]
    return stem


def noise_model_label(backend, requested: Optional[str]) -> str:
    name = backend_name(backend)
    if requested and _device_stem(requested) == _device_stem(name):
        return f"{name} (matching fake backend for {requested})"
    if name.startswith("generic_backend"):
        return (f"{name} (generic surrogate: the qiskit_ibm_runtime fake provider is not "
                f"installed, so this is NOT {requested or 'the device'} calibration)")
    return f"{name} (fallback fake backend; requested {requested or 'unknown'})"


def simulate(circuits: Sequence, backend, shots: int, seed: int,
             optimization_level: int = DEFAULT_OPTIMIZATION_LEVEL):
    """Run the same circuits on Aer with the fake backend's noise, and noiselessly."""
    from qiskit import transpile
    from qiskit_aer import AerSimulator

    noise_model = None
    try:
        from qiskit_aer.noise import NoiseModel

        noise_model = NoiseModel.from_backend(backend)
    except Exception as exc:  # no calibration data for this target
        print(f"warning: no noise model could be built from {backend_name(backend)} ({exc}); "
              "the simulated column is noiseless.")

    transpiled = transpile(circuits, backend=backend, optimization_level=optimization_level,
                           seed_transpiler=seed)
    noisy_sim = (AerSimulator(noise_model=noise_model, seed_simulator=seed) if noise_model is not None
                 else AerSimulator(seed_simulator=seed))
    ideal_sim = AerSimulator(seed_simulator=seed)
    noisy = noisy_sim.run(transpiled, shots=shots).result()
    ideal = ideal_sim.run(transpiled, shots=shots).result()
    sim_counts = [normalise_counts(noisy.get_counts(i)) for i in range(len(transpiled))]
    ideal_counts = [normalise_counts(ideal.get_counts(i)) for i in range(len(transpiled))]
    return sim_counts, ideal_counts, noise_model is not None


# --------------------------------------------------------------------------
# Matrix
# --------------------------------------------------------------------------
def _rate(counts: Dict[str, int], bit: int):
    total = sum(counts.values())
    return (success_count(counts, bit) / total) if total else None


def comparison_rows(record: dict, sim_counts: Sequence[Dict[str, int]],
                    ideal_counts: Sequence[Dict[str, int]]) -> List[dict]:
    rows = []
    for state, simulated, ideal in zip(record["states"], sim_counts, ideal_counts):
        bit = int(state["bit"])
        rows.append({
            "state": f"|{state['label']}>",
            "hardware": _rate(state["counts"], bit),
            "simulated": _rate(simulated, bit),
            "ideal": _rate(ideal, bit),
        })
    return rows


def format_matrix(rows: Sequence[dict]) -> str:
    header = ("State", "Hardware Success Rate", "Simulated Success Rate", "Ideal Success Rate")
    widths = (8, 23, 23, 18)

    def cell(value, width):
        return ("n/a" if value is None else f"{value:.4f}").ljust(width)

    lines = [
        " | ".join(label.ljust(width) for label, width in zip(header, widths)).rstrip(),
        "-+-".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(" | ".join((
            row["state"].ljust(widths[0]),
            cell(row["hardware"], widths[1]),
            cell(row["simulated"], widths[2]),
            cell(row["ideal"], widths[3]),
        )).rstrip())
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Compare a saved IBM hardware teleportation run with an Aer fake-backend simulation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("result", help="result_<timestamp>.json written by run_ibm_teleport.py")
    ap.add_argument("--shots", type=int, default=None,
                    help="simulator shots per state (default: the hardware run's shots)")
    ap.add_argument("--seed", type=int, default=2026, help="Aer and transpiler seed (default 2026)")
    ap.add_argument("--backend", default=None,
                    help="fake backend to use instead of the one derived from the result file")
    args = ap.parse_args(argv)
    if args.shots is not None and args.shots <= 0:
        ap.error("--shots must be positive")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not os.path.exists(args.result):
        print(f"error: result file not found: {args.result}")
        return 1
    try:
        record = load_result(args.result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {args.result}: {exc}")
        return 1

    execution = record.get("execution") or {}
    shots = args.shots if args.shots is not None else int(execution.get("shots") or 0)
    if shots <= 0:
        print("error: the result file has no shot count; pass --shots")
        return 1
    optimization_level = int(execution.get("optimization_level", DEFAULT_OPTIMIZATION_LEVEL))

    circuits = circuits_from_record(record)
    requested = args.backend or record.get("backend_name")
    backend = resolve_backend(requested)
    sim_counts, ideal_counts, has_noise = simulate(circuits, backend, shots, args.seed, optimization_level)
    rows = comparison_rows(record, sim_counts, ideal_counts)

    print(f"Hardware result: {args.result}")
    print(f"  mode         : {record.get('mode', 'unknown')}")
    print(f"  backend      : {record.get('backend_name')} "
          f"({record.get('timestamp')}, {execution.get('shots')} shots/state, "
          f"job {record.get('job_id') or 'n/a'})")
    print(f"  noise model  : {noise_model_label(backend, requested)}"
          f"{'' if has_noise else ' [NOISELESS]'}")
    print(f"  simulation   : {shots} shots/state, seed {args.seed}, "
          f"optimization_level {optimization_level}")
    if record.get("mode") != "hardware":
        print("WARNING: this result was not produced on hardware "
              f"(mode={record.get('mode')!r}); the 'Hardware' column is simulated.")
    print()
    print(format_matrix(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
