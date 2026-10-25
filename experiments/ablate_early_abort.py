"""
Ablation: sequential early abort on vs off (EARLY_ABORT / SecurityParameters.early_abort).

Runs honest, eve_intercept and eve_forgery traffic for L = 16, 32, 64 with the
early abort switched on and off. Both settings use the same per-cell seeds as
the harness, so they see the same random draws until the streams diverge.

Reported per (setting, scenario, L), with 95% Wilson intervals where a rate:
  detection rate      flagged as a threat (attacks)
  false-abort rate    honest sessions whose channel test alarmed (signature never revealed)
  early-abort rate    sessions whose stream stopped before the last token
  tokens consumed     mean tokens actually sent / planned
  bandwidth saved     mean 1 - sent/planned

    python experiments/ablate_early_abort.py --quick
    python experiments/ablate_early_abort.py --trials 1000 --seed 2026

Writes experiments/results/ablate_early_abort.csv and ablate_early_abort.{png,svg}.
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

SCENARIOS = ("authentic", "eve_intercept", "eve_forgery")
SETTINGS = (("on", True), ("off", False))
FIELDS = ["early_abort", "scenario", "n_bits", "noise_profile", "seed", "trials",
          "detection_rate", "detection_ci_low", "detection_ci_high",
          "false_abort_rate", "false_abort_ci_low", "false_abort_ci_high",
          "early_abort_rate", "early_abort_ci_low", "early_abort_ci_high",
          "mean_tokens_sent", "mean_tokens_planned", "bandwidth_saved"]


def _rate(prefix, k, n):
    lo, hi = wilson_interval(k, n)
    return {f"{prefix}_rate": round(k / n, 4), f"{prefix}_ci_low": round(lo, 4), f"{prefix}_ci_high": round(hi, 4)}


def summarise(setting: str, cell: dict) -> dict:
    trials = cell["trials"]
    n = len(trials)
    ch = [t["channel"] for t in trials]
    sent = [c["tokens_sent"] for c in ch]
    planned = [c["tokens_planned"] for c in ch]
    row = {"early_abort": setting, "scenario": cell["scenario"], "n_bits": cell["n_bits"],
           "noise_profile": cell["noise_profile"], "seed": cell["seed"], "trials": n}
    if cell["scenario"] == "authentic":
        row.update(_rate("false_abort", sum(c["alarm"] for c in ch), n))
    else:
        row.update(_rate("detection", sum(t["flagged"] for t in trials), n))
    row.update(_rate("early_abort", sum(c["early_abort"] for c in ch), n))
    row["mean_tokens_sent"] = round(float(np.mean(sent)), 2)
    row["mean_tokens_planned"] = round(float(np.mean(planned)), 2)
    row["bandwidth_saved"] = round(float(np.mean([1 - s / p for s, p in zip(sent, planned)])), 4)
    return row


def run(seed, trials, bits, profile="depolarizing", workers=1):
    tasks = []
    for setting, flag in SETTINGS:
        params = replace(SecurityParameters(), early_abort=flag)
        tasks += harness.build_tasks(SCENARIOS, bits, [profile], seed, trials, params=params,
                                     variant=f"early_abort={setting}")
    cells = {c["key"]: c for c in harness.run_cells(tasks, workers)}
    rows = []
    for t in tasks:  # grid order, whatever order the workers finished in
        rows.append(summarise(t["variant"].split("=")[1], cells[t["key"]]))
    return rows


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def plot(rows, stem):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bits = sorted({r["n_bits"] for r in rows})
    fig, axes = plt.subplots(1, len(SCENARIOS), figsize=(4.2 * len(SCENARIOS), 3.6), sharey=True)
    width = 0.38
    x = np.arange(len(bits))
    for ax, scenario in zip(np.atleast_1d(axes), SCENARIOS):
        for i, (setting, _) in enumerate(SETTINGS):
            vals = [next(r["mean_tokens_sent"] for r in rows
                         if r["scenario"] == scenario and r["n_bits"] == b and r["early_abort"] == setting)
                    for b in bits]
            ax.bar(x + (i - 0.5) * width, vals, width, label=f"early abort {setting}")
        ax.set_xticks(x, [f"L={b}" for b in bits])
        ax.set_title(scenario)
        ax.grid(axis="y", alpha=0.3)
    np.atleast_1d(axes)[0].set_ylabel("mean tokens sent per session")
    np.atleast_1d(axes)[-1].legend(frameon=False)
    fig.suptitle("Sequential early abort: quantum tokens consumed")
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

    rows = run(args.seed, trials, args.bits, args.profile, args.workers)
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.join(args.out, "ablate_early_abort")
    write_csv(stem + ".csv", rows)
    plot(rows, stem)
    for r in rows:
        main_rate = (f"false abort {r['false_abort_rate']:.3f}" if r["scenario"] == "authentic"
                     else f"detected {r['detection_rate']:.3f}")
        print(f"early_abort={r['early_abort']:3s} L={r['n_bits']:<3} {r['scenario']:14s} {main_rate}  "
              f"tokens {r['mean_tokens_sent']:.1f}/{r['mean_tokens_planned']:.1f}  "
              f"saved {r['bandwidth_saved']:.1%}")
    print(f"Wrote {stem}.csv, {stem}.png, {stem}.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
