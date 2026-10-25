"""
Resumable, reproducible experiment harness for HEDWIG V2.

Runs the grid  scenario x L x noise profile x trials  by calling the protocol
layer directly (no web server, no audit signing). Every cell gets its own RNG
seeded from SHA-256(global seed, scenario, L, profile), so a cell's numbers do
not depend on run order or on how many worker processes are used. Each
finished cell is appended to raw.jsonl at once; on restart, cells already in
the file are skipped. summary.csv is rebuilt from raw.jsonl with 95% Wilson
intervals.

    python experiments/harness.py --quick                 # 100 trials/cell smoke test
    python experiments/harness.py                         # 1,000 trials/cell, all cores
    python experiments/harness.py --dry-run               # estimated runtime, writes nothing
    python experiments/harness.py --only eve_forgery authentic --bits 32 --profiles depolarizing

Writes experiments/results/raw.jsonl and experiments/results/summary.csv.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from src.quantum_engine import (  # noqa: E402
    ChannelModel, SecurityParameters, TeleportationQDS, ThreatScenarioConfig, ThreatType,
    make_lossy_channel, make_readout_channel,
)
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.teleportation import calibrate_ibm_backend  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")
CALIBRATION_DIR = os.path.join(HERE, "calibration")
BITS = (16, 32, 64)
PROFILES = ("depolarizing", "ibm_calibrated", "readout", "lossy")
SCENARIOS = tuple(t.value for t in ThreatType)
DEFAULT_TRIALS = 1000
QUICK_TRIALS = 100
MAX_REPLAY_PREAMBLES = 100

EXPECTED = {  # classifications that count as the correct verdict for each injected scenario
    "authentic": {"BENIGN_AUTHENTIC", "CHANNEL_NOISE"},
    "eve_forgery": {"EXTERNAL_FORGERY"},
    "dishonest_bob": {"DISHONEST_VERIFIER_FORGERY"},
    "eve_intercept": {"EAVESDROPPING_TAMPERING"},
    "message_tampering": {"MESSAGE_INTEGRITY_VIOLATION"},
    "repudiation": {"REPUDIATION_ATTEMPT"},
    "replay": {"REPLAY_ATTACK"},
    "impersonation": {"IMPERSONATION_ATTACK"},
    "eve_loss_exploit": {"INSUFFICIENT_TOKENS", "EXTERNAL_FORGERY", "EAVESDROPPING_TAMPERING"},
    "eve_cloning": {"EAVESDROPPING_TAMPERING"},
    "eve_partial_intercept": {"EAVESDROPPING_TAMPERING"},
}

SUMMARY_FIELDS = [
    "scenario", "n_bits", "noise_profile", "seed", "trials",
    "detection_rate", "detection_ci_low", "detection_ci_high",
    "false_reject_rate", "false_reject_ci_low", "false_reject_ci_high",
    "correct_class_rate", "correct_class_ci_low", "correct_class_ci_high",
    "early_abort_rate", "quarantine_rate", "mean_tokens_sent", "mean_tokens_planned",
]


# ------------------------------------------------------------------ grid
def cell_seed(seed: int, scenario: str, n_bits: int, profile: str) -> int:
    """Per-cell seed from a hash of the cell parameters: independent of run order."""
    digest = hashlib.sha256(f"HEDWIG-harness|{seed}|{scenario}|{n_bits}|{profile}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def cell_key(scenario: str, n_bits: int, profile: str, seed: int, trials: int) -> str:
    return f"{scenario}|L{n_bits}|{profile}|seed{seed}|n{trials}"


def make_channel(profile: str) -> ChannelModel:
    if profile == "depolarizing":
        return ChannelModel()
    if profile == "ibm_calibrated":
        # Fast calibrated mode (A1): the cached confusion-matrix error rate drives a depolarising-equivalent channel.
        cal = calibrate_ibm_backend(cache_dir=CALIBRATION_DIR)
        return ChannelModel(noise_profile="ibm_fake", ibm_backend=cal["backend_name"], ibm_mode="calibrated",
                            effective_error_rate=cal["effective_error_rate"],
                            calibration_date=cal["calibration_date"], depolarizing=cal["effective_error_rate"])
    if profile == "readout":
        return make_readout_channel(p01=0.01, p10=0.03, location="both")
    if profile == "lossy":
        return make_lossy_channel(eta_loss=0.1)
    raise ValueError(f"Unknown noise profile {profile}")


# ------------------------------------------------------------------ trials
def _trial_record(r) -> dict:
    """The observable outcome of one trial (no timings, so equal seeds give equal records)."""
    t, report = r.transcript, r.threat_report
    ct = t.channel_test
    direct = [v for v in t.results if v.mode == "direct"]
    return {
        "classification": report.classification.value,
        "flagged": bool(report.is_threat_detected),
        "decided_by": report.decided_by,
        "accepted": bool(direct) and all(v.accepted for v in direct),
        "revealed": bool(t.results),
        "response": r.response.response_action if r.response else None,
        "tier2_attribution": report.tier2.get("attribution") if report.tier2 else None,
        "verifications": [{"verifier": v.verifier, "mode": v.mode, "mismatches": v.mismatches,
                           "n_checked": v.n_checked, "accepted": bool(v.accepted)} for v in t.results],
        "channel": None if ct is None else {
            "test_count": ct.test_count, "error_count": ct.error_count, "alarm": bool(ct.alarm),
            "early_abort": bool(ct.early_abort), "tokens_sent": ct.tokens_sent,
            "tokens_planned": ct.tokens_planned, "tokens_lost": ct.tokens_lost},
    }


def run_trial(scenario: str, n_bits: int, channel: ChannelModel, rng: np.random.Generator,
              params: SecurityParameters) -> dict:
    threat = ThreatType(scenario)
    eng = TeleportationQDS(params=params, backend="statevector", channel=channel)
    if threat == ThreatType.REPLAY:
        # Replay needs a genuinely accepted package; honest preambles are occasionally rejected by noise.
        for _ in range(MAX_REPLAY_PREAMBLES):
            eng.guard.reset()
            eng.execute_protocol("genuine", n_bits, rng=rng, channel=channel)
            if eng.last_accepted_package is not None:
                break
        else:
            raise RuntimeError(f"No honest preamble accepted in {MAX_REPLAY_PREAMBLES} tries (L={n_bits})")
        eng.guard.reset()
    r = eng.execute_protocol("experiment message", n_bits, rng=rng, channel=channel,
                             scenario=ThreatScenarioConfig(threat_type=threat))
    return _trial_record(r)


def run_cell(task: dict) -> dict:
    """Run every trial of one cell. Top-level so worker processes can import it."""
    params = task.get("params") or SecurityParameters()
    channel = make_channel(task["noise_profile"])
    rng = np.random.default_rng(task["cell_seed"])
    trials = [run_trial(task["scenario"], task["n_bits"], channel, rng, params) for _ in range(task["trials"])]
    out = {k: task[k] for k in ("key", "scenario", "n_bits", "noise_profile", "seed", "cell_seed")}
    out["variant"] = task.get("variant", "default")
    out["n_trials"] = task["trials"]
    out["trials"] = trials
    return out


def build_tasks(scenarios, bits, profiles, seed, trials, params=None, variant="default"):
    tasks = []
    for profile in profiles:
        for n_bits in bits:
            for scenario in scenarios:
                tasks.append({"key": cell_key(scenario, n_bits, profile, seed, trials) +
                                     ("" if variant == "default" else f"|{variant}"),
                              "scenario": scenario, "n_bits": n_bits, "noise_profile": profile, "seed": seed,
                              "cell_seed": cell_seed(seed, scenario, n_bits, profile), "trials": trials,
                              "params": params, "variant": variant})
    return tasks


def run_cells(tasks, workers: int = 1):
    """Yield finished cells as they complete (any order)."""
    if workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            yield run_cell(task)
        return
    with Pool(min(workers, len(tasks))) as pool:
        yield from pool.imap_unordered(run_cell, tasks)


# ------------------------------------------------------------------ persistence
def load_cells(path: str) -> dict:
    """Finished cells by key. A line cut short by a kill mid-write is ignored (that cell is rerun)."""
    cells = {}
    if not os.path.exists(path):
        return cells
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                cell = json.loads(line)
            except json.JSONDecodeError:
                continue
            cells[cell["key"]] = cell
    return cells


def append_cell(path: str, cell: dict):
    line = json.dumps(cell, sort_keys=True) + "\n"
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":   # a kill left a partial line: start a fresh one after it
                line = "\n" + line
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


# ------------------------------------------------------------------ summary
def _rate(k: int, n: int):
    lo, hi = wilson_interval(k, n)
    return round(k / n, 4) if n else None, round(lo, 4), round(hi, 4)


def summarise_cell(cell: dict) -> dict:
    trials = cell["trials"]
    n = len(trials)
    flagged = sum(t["flagged"] for t in trials)
    correct = sum(t["classification"] in EXPECTED[cell["scenario"]] for t in trials)
    channels = [t["channel"] for t in trials if t["channel"]]
    row = {"scenario": cell["scenario"], "n_bits": cell["n_bits"], "noise_profile": cell["noise_profile"],
           "seed": cell["seed"], "trials": n}
    det = _rate(flagged, n)
    if cell["scenario"] == "authentic":   # a flagged honest run is a false rejection
        row.update(dict(zip(("false_reject_rate", "false_reject_ci_low", "false_reject_ci_high"), det)))
    else:
        row.update(dict(zip(("detection_rate", "detection_ci_low", "detection_ci_high"), det)))
    row.update(dict(zip(("correct_class_rate", "correct_class_ci_low", "correct_class_ci_high"), _rate(correct, n))))
    row["early_abort_rate"] = round(sum(c["early_abort"] for c in channels) / n, 4)
    row["quarantine_rate"] = round(sum(t["response"] == "quarantine" for t in trials) / n, 4)
    row["mean_tokens_sent"] = round(float(np.mean([c["tokens_sent"] for c in channels])), 2) if channels else None
    row["mean_tokens_planned"] = round(float(np.mean([c["tokens_planned"] for c in channels])), 2) if channels else None
    return row


def write_summary(path: str, cells: list):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
        w.writeheader()
        for cell in cells:
            w.writerow(summarise_cell(cell))


# ------------------------------------------------------------------ dry run
def estimate_seconds(tasks, workers: int, sample: int = 3) -> float:
    """Time a few honest trials per L and scale to the pending grid (rough: attacks cost about the same)."""
    per_trial = {}
    for n_bits in sorted({t["n_bits"] for t in tasks}):
        rng = np.random.default_rng(0)
        start = time.perf_counter()
        for _ in range(sample):
            run_trial("authentic", n_bits, ChannelModel(), rng, SecurityParameters())
        per_trial[n_bits] = (time.perf_counter() - start) / sample
    total = sum(per_trial[t["n_bits"]] * t["trials"] for t in tasks)
    return total / max(1, min(workers, len(tasks)))


# ------------------------------------------------------------------ main
def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--trials", type=int, default=None, help=f"trials per cell (default {DEFAULT_TRIALS})")
    ap.add_argument("--quick", action="store_true", help=f"smoke test: {QUICK_TRIALS} trials per cell")
    ap.add_argument("--dry-run", action="store_true", help="print the estimated runtime and exit")
    ap.add_argument("--only", nargs="+", choices=SCENARIOS, metavar="SCENARIO", help="run only these scenarios")
    ap.add_argument("--bits", type=int, nargs="+", default=list(BITS))
    ap.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default=RESULTS_DIR)
    args = ap.parse_args(argv)
    if args.trials is None:
        args.trials = QUICK_TRIALS if args.quick else DEFAULT_TRIALS
    return args


def main(argv=None):
    args = parse_args(argv)
    tasks = build_tasks(args.only or SCENARIOS, args.bits, args.profiles, args.seed, args.trials)
    raw_path = os.path.join(args.out, "raw.jsonl")
    done = load_cells(raw_path)
    pending = [t for t in tasks if t["key"] not in done]
    print(f"{len(tasks)} cells x {args.trials} trials (seed {args.seed}); "
          f"{len(tasks) - len(pending)} already in {raw_path}, {len(pending)} to run.", flush=True)

    if args.dry_run:
        secs = estimate_seconds(pending, args.workers) if pending else 0.0
        print(f"Estimated runtime on {args.workers} worker(s): {secs / 60:.1f} min ({secs:.0f} s).")
        return 0

    os.makedirs(args.out, exist_ok=True)
    start = time.perf_counter()
    for i, cell in enumerate(run_cells(pending, args.workers), 1):
        append_cell(raw_path, cell)
        done[cell["key"]] = cell
        row = summarise_cell(cell)
        rate = row.get("false_reject_rate") if cell["scenario"] == "authentic" else row.get("detection_rate")
        label = "false reject" if cell["scenario"] == "authentic" else "detected"
        print(f"[{i}/{len(pending)}] {cell['noise_profile']:14s} L={cell['n_bits']:<3} {cell['scenario']:18s} "
              f"{label} {rate:.3f}  correct {row['correct_class_rate']:.3f}", flush=True)

    summary_path = os.path.join(args.out, "summary.csv")
    write_summary(summary_path, [done[t["key"]] for t in tasks])
    print(f"Wrote {summary_path} ({time.perf_counter() - start:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
