"""
Calibration sweep: one-tier (V2.1) vs two-tier (V2.2) attribution on the SAME observations.

For each condition (signature length L, honest noise, burst noise, intercept
strength, dishonest signer) it runs seeded trials and labels every run twice:

  V2.1 rule  Tier 1 alarm -> channel; else elimination fail with binding ok
             -> signature (repudiation); else accepted.
  V2.2 rule  the blind detector: Tier 1 alarm -> channel; else Tier 2 decides
             channel / signature / undetermined; else accepted.

Rejection is identical under both rules (Tier 2 never rejects on its own), so
the comparison isolates what Tier 2 changes: attribution and response.

    python experiments/sweep_tiers.py                  # default grid, 200 trials
    python experiments/sweep_tiers.py --trials 500 --bits 16 32

Writes experiments/sweep_tiers.md and sweep_tiers.json.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatType  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402

LABELS = ("accepted", "channel", "signature", "undetermined", "other")


def v21_label(t):
    ct = t.channel_test
    if ct is not None and ct.alarm:
        return "channel"
    if all(r.accepted for r in t.results) and t.results:
        return "accepted"
    if any(not r.binding_pass for r in t.results):
        return "other"
    return "signature" if any(not r.elimination_pass for r in t.results) else "other"


def v22_label(report):
    c = report.classification.value
    return {"BENIGN_AUTHENTIC": "accepted", "CHANNEL_NOISE": "accepted", "EAVESDROPPING_TAMPERING": "channel",
            "REPUDIATION_ATTEMPT": "signature", "UNDETERMINED_DISTURBANCE": "undetermined"}.get(c, "other")


def conditions():
    yield "honest p=0.005", ThreatType.AUTHENTIC, ChannelModel(depolarizing=0.005), "accepted"
    yield "honest p=0.01", ThreatType.AUTHENTIC, ChannelModel(depolarizing=0.01), "accepted"
    yield "honest p=0.03 (QBER=e0)", ThreatType.AUTHENTIC, ChannelModel(depolarizing=0.03), "accepted"
    yield "honest + bursts", ThreatType.AUTHENTIC, ChannelModel(depolarizing=0.01, burst_rate=0.01,
                                                                burst_depolarizing=0.5, burst_length=8), "accepted"
    for rate in (0.25, 0.5, 1.0):
        yield f"intercept {rate:.0%}", ThreatType.EVE_INTERCEPT, (ChannelModel(depolarizing=0.01), rate), "channel"
    yield "dishonest signer", ThreatType.REPUDIATION, ChannelModel(depolarizing=0.01), "signature"


def wrong(counts, truth):
    """Confident labels of the wrong cause (for honest runs: any attack label)."""
    return sum(counts[k] for k in ("channel", "signature") if k != truth)


def fmt(k, n):
    lo, hi = wilson_interval(k, n)
    return f"{k / n:.3f} [{lo:.3f}, {hi:.3f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--bits", type=int, nargs="+", default=[16, 32, 64])
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    rows = []
    for n_bits in args.bits:
        for name, threat, chan, truth in conditions():
            rate = None
            if isinstance(chan, tuple):
                chan, rate = chan
            v21, v22, resp = Counter(), Counter(), Counter()
            for _ in range(args.trials):
                eng = TeleportationQDS(backend="statevector", channel=chan)
                cfg = ThreatScenarioConfig(threat_type=threat)
                if rate is not None:
                    cfg.channel_intercept_rate = rate
                r = eng.execute_protocol("sweep", n_bits, rng=rng, scenario=cfg)
                v21[v21_label(r.transcript)] += 1
                v22[v22_label(r.threat_report)] += 1
                resp[r.response.response_action] += 1
            n = args.trials
            rows.append({
                "L": n_bits, "condition": name, "truth": truth, "trials": n,
                "v21": {k: v21[k] for k in LABELS}, "v22": {k: v22[k] for k in LABELS},
                "response": dict(resp),
                "v21_correct": fmt(v21[truth], n), "v22_correct": fmt(v22[truth], n),
                "v21_wrong_attribution": fmt(wrong(v21, truth), n),
                "v22_wrong_attribution": fmt(wrong(v22, truth), n),
                "v22_undetermined": fmt(v22["undetermined"], n),
                "quarantine": fmt(resp["quarantine"], n),
            })
            print(f"L={n_bits:<3} {name:24s} v2.1 correct {rows[-1]['v21_correct']}  "
                  f"v2.2 correct {rows[-1]['v22_correct']}  undetermined {rows[-1]['v22_undetermined']}", flush=True)

    meta = {"trials": args.trials, "bits": args.bits, "seed": args.seed, "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(args.out, "sweep_tiers.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rows": rows}, f, indent=2)

    lines = [
        "# One-tier vs two-tier attribution sweep", "",
        f"Seed {args.seed}, {args.trials} trials per cell, statevector backend. Generated {meta['generated']}. "
        "Both rules label the same runs; rejection decisions are identical, only attribution differs.", "",
        "*Correct* = label matches ground truth (honest: accepted; intercept: channel; dishonest signer: signature). "
        "*Wrong attribution* = a confident label of the wrong cause (for honest runs: any attack label). "
        "*Undetermined* = V2.2 abstains (still rejected, response WATCH unless evidence is strong).", "",
        "| L | condition | V2.1 correct | V2.2 correct | V2.1 wrong attribution | V2.2 wrong attribution "
        "| V2.2 undetermined | quarantined (V2.2 policy) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['L']} | {r['condition']} | {r['v21_correct']} | {r['v22_correct']} | "
                     f"{r['v21_wrong_attribution']} | {r['v22_wrong_attribution']} | {r['v22_undetermined']} | "
                     f"{r['quarantine']} |")
    lines += ["", "Benefit of Tier 2 = fewer wrong attributions; cost = abstentions where V2.1 guessed "
              "(sometimes correctly). Both are shown; neither is hidden."]
    with open(os.path.join(args.out, "sweep_tiers.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {os.path.join(args.out, 'sweep_tiers.md')}")


if __name__ == "__main__":
    main()
