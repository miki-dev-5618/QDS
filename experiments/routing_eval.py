"""Reproducible availability/acceptance/resource evaluation of the multi-hop demo.

Run: python experiments/routing_eval.py --trials 10 --seed 2026 --output experiments/routing_results.json
Failures and inconclusive outcomes are retained, never silently retried away.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.quantum_engine import TeleportationQDS, ChannelModel, probe_edges
from src.quantum_engine.channel import wilson_interval
from src.quantum_engine.enforcement import edge_scope


def evaluate(trials=10, seed=2026):
    rows = []
    for index in range(trials):
        rng = np.random.default_rng(seed + index)
        engine = TeleportationQDS(backend="statevector", topology="demo-multihop", channel=ChannelModel(depolarizing=0))
        for phase in ("primary", "after_probe"):
            probe = None
            if phase == "after_probe":
                engine.edge_injections["R1->R2"] = ChannelModel(depolarizing=0, intercept_rate=1)
                probe = probe_edges(engine, ["R1->R2"], rng)[0]
            started = time.perf_counter()
            try:
                result = engine.execute_protocol("routing evaluation", 32, rng=rng).to_dict()
                routing = result["routing"]
                rows.append({"trial": index, "seed": seed+index, "phase": phase, "allocated": True,
                    "outcome": result["session_outcome"], "classification": result["threat_report"]["classification"],
                    "routes": {v: r["nodes"] for v, r in routing["plan"]["routes"].items()},
                    "predictions": {v: {k: r[k] for k in ("expected_qber", "survival", "cost", "hops")}
                                    for v, r in routing["plan"]["routes"].items()},
                    "execution": routing["execution"], "probe": probe,
                    "seconds": time.perf_counter()-started})
            except Exception as exc:
                rows.append({"trial": index, "seed": seed+index, "phase": phase, "allocated": False,
                    "outcome": "refused_or_failed", "reason": str(exc), "probe": probe,
                    "seconds": time.perf_counter()-started})
    summary = {}
    for phase in ("primary", "after_probe"):
        phase_rows = [r for r in rows if r["phase"] == phase]
        accepted = sum(r["outcome"] == "all_accepted" for r in phase_rows)
        summary[phase] = {"trials": trials, "allocated": sum(r["allocated"] for r in phase_rows),
            "accepted": accepted, "acceptance_wilson95": wilson_interval(accepted, trials),
            "via_R3": sum(any("R3" in p for p in r.get("routes", {}).values()) for r in phase_rows),
            "bell_pairs": sum(c["bell_pairs"] for r in phase_rows for c in r.get("execution", {}).get("edges", {}).values()),
            "lost": sum(c["lost"] for r in phase_rows for c in r.get("execution", {}).get("edges", {}).values()),
            "probe_bell_pairs": sum(c["bell_pairs"] for r in phase_rows for c in (r.get("probe") or {}).get("execution", {}).values())}
    return {"schema": "hedwig-routing-eval/1", "seed": seed, "signature_bits": 32,
        "backend": "statevector", "topology_digest": engine.topology.digest,
        "calibration": "bell-half-depolarizing-damping/1", "summary": summary, "trials": rows,
        "note": "Simulation under honest relays/authenticated classical communication. Allocation and verification acceptance are separate. Probe resources are separate from session resources. Intervals describe these trials only."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.trials <= 1000:
        parser.error("trials must be in 1..1000")
    result = evaluate(args.trials, args.seed)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
