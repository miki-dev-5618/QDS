"""
Ablation: Tier 1 only vs Tier 1 + Tier 2 attribution (DETECTION_TIERS / SecurityParameters.detection_tiers).

Runs repudiation, eve_intercept and eve_forgery for L = 16, 32, 64 under both
settings (same per-cell seeds as the harness) and maps each verdict to the
cause it blames:

  channel       EAVESDROPPING_TAMPERING (Tier 1 alarm, Tier 2 channel attribution, or Tier-1-only fallback)
  signature     REPUDIATION_ATTEMPT
  forgery       EXTERNAL_FORGERY
  undetermined  UNDETERMINED_DISTURBANCE
  accepted      BENIGN_AUTHENTIC / CHANNEL_NOISE (a miss)
  other         anything else

Ground truth: repudiation -> signature, eve_intercept -> channel, eve_forgery -> forgery.
Reported with 95% Wilson intervals: attribution accuracy, UNDETERMINED rate and
wrong-blame rate (a confident label of the wrong cause), plus a confusion matrix
per (setting, L).

    python experiments/ablate_tiers.py --quick
    python experiments/ablate_tiers.py --trials 1000 --seed 2026

Writes experiments/results/ablate_tiers.csv, ablate_tiers_confusion.csv and ablate_tiers.{png,svg}.
"""
import argparse
import csv
import os
import sys
from dataclasses import replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import harness  # noqa: E402
from harness import RESULTS_DIR, SecurityParameters, wilson_interval  # noqa: E402

SCENARIOS = ("repudiation", "eve_intercept", "eve_forgery")
TRUTH = {"repudiation": "signature", "eve_intercept": "channel", "eve_forgery": "forgery"}
LABELS = ("channel", "signature", "forgery", "undetermined", "accepted", "other")
CONFIDENT = {"channel", "signature", "forgery"}
TIERS = (1, 2)
FIELDS = ["tiers", "scenario", "truth", "n_bits", "noise_profile", "seed", "trials",
          "accuracy", "accuracy_ci_low", "accuracy_ci_high",
          "undetermined_rate", "undetermined_ci_low", "undetermined_ci_high",
          "wrong_blame_rate", "wrong_blame_ci_low", "wrong_blame_ci_high"]


def blame(classification: str) -> str:
    return {"EAVESDROPPING_TAMPERING": "channel", "REPUDIATION_ATTEMPT": "signature",
            "EXTERNAL_FORGERY": "forgery", "UNDETERMINED_DISTURBANCE": "undetermined",
            "BENIGN_AUTHENTIC": "accepted", "CHANNEL_NOISE": "accepted"}.get(classification, "other")


def _rate(prefix, k, n):
    lo, hi = wilson_interval(k, n)
    return {f"{prefix}_rate" if prefix != "accuracy" else "accuracy": round(k / n, 4),
            f"{prefix}_ci_low": round(lo, 4), f"{prefix}_ci_high": round(hi, 4)}


def summarise(tiers: int, cell: dict):
    labels = [blame(t["classification"]) for t in cell["trials"]]
    n, truth = len(labels), TRUTH[cell["scenario"]]
    row = {"tiers": tiers, "scenario": cell["scenario"], "truth": truth, "n_bits": cell["n_bits"],
           "noise_profile": cell["noise_profile"], "seed": cell["seed"], "trials": n}
    row.update(_rate("accuracy", sum(lab == truth for lab in labels), n))
    row.update(_rate("undetermined", labels.count("undetermined"), n))
    row.update(_rate("wrong_blame", sum(lab in CONFIDENT and lab != truth for lab in labels), n))
    counts = {lab: labels.count(lab) for lab in LABELS}
    return row, counts


def run(seed, trials, bits, profile="depolarizing", workers=1):
    tasks = []
    for tiers in TIERS:
        params = replace(SecurityParameters(), detection_tiers=tiers)
        tasks += harness.build_tasks(SCENARIOS, bits, [profile], seed, trials, params=params,
                                     variant=f"tiers={tiers}")
    cells = {c["key"]: c for c in harness.run_cells(tasks, workers)}
    rows, confusion = [], []
    for t in tasks:
        tiers = int(t["variant"].split("=")[1])
        row, counts = summarise(tiers, cells[t["key"]])
        rows.append(row)
        confusion.append({"tiers": tiers, "n_bits": t["n_bits"], "truth": row["truth"], **counts})
    return rows, confusion


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def plot(confusion, stem):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bits = sorted({c["n_bits"] for c in confusion})
    truths = [TRUTH[s] for s in SCENARIOS]
    fig, axes = plt.subplots(len(TIERS), len(bits), figsize=(3.9 * len(bits), 3.2 * len(TIERS)), squeeze=False)
    for i, tiers in enumerate(TIERS):
        for j, b in enumerate(bits):
            ax = axes[i][j]
            m = np.array([[next(c[lab] for c in confusion
                                if c["tiers"] == tiers and c["n_bits"] == b and c["truth"] == truth)
                           for lab in LABELS] for truth in truths], dtype=float)
            frac = m / m.sum(axis=1, keepdims=True)
            ax.imshow(frac, vmin=0, vmax=1, cmap="Blues")
            for (r, c), v in np.ndenumerate(frac):
                ax.text(c, r, f"{v:.2f}", ha="center", va="center", fontsize=8,
                        color="white" if v > 0.6 else "black")
            ax.set_xticks(range(len(LABELS)), LABELS, rotation=45, ha="right", fontsize=8)
            ax.set_yticks(range(len(truths)), truths if j == 0 else [], fontsize=8)
            ax.set_title(f"{'Tier 1 only' if tiers == 1 else 'Tier 1 + 2'}, L={b}", fontsize=9)
    fig.supxlabel("label assigned by the detector")
    fig.supylabel("ground truth")
    fig.tight_layout()
    fig.savefig(stem + ".png", dpi=150)
    fig.savefig(stem + ".svg", metadata={"Date": None})
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--trials", type=int, default=None, help=f"default {harness.DEFAULT_TRIALS}")
    ap.add_argument("--quick", action="store_true", help=f"{harness.QUICK_TRIALS} trials per cell")
    ap.add_argument("--bits", type=int, nargs="+", default=list(harness.BITS))
    ap.add_argument("--profile", choices=harness.PROFILES, default="depolarizing")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default=RESULTS_DIR)
    args = ap.parse_args(argv)
    trials = args.trials or (harness.QUICK_TRIALS if args.quick else harness.DEFAULT_TRIALS)

    rows, confusion = run(args.seed, trials, args.bits, args.profile, args.workers)
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.join(args.out, "ablate_tiers")
    write_csv(stem + ".csv", FIELDS, rows)
    write_csv(stem + "_confusion.csv", ["tiers", "n_bits", "truth", *LABELS], confusion)
    plot(confusion, stem)
    for r in rows:
        print(f"tiers={r['tiers']} L={r['n_bits']:<3} {r['scenario']:14s} accuracy {r['accuracy']:.3f} "
              f"[{r['accuracy_ci_low']:.3f}, {r['accuracy_ci_high']:.3f}]  undetermined {r['undetermined_rate']:.3f}  "
              f"wrong blame {r['wrong_blame_rate']:.3f}")
    print(f"Wrote {stem}.csv, {stem}_confusion.csv, {stem}.png, {stem}.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
