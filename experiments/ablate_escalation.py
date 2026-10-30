"""
Ablation: Fisher escalation vs a simple k-alert counter (ESCALATION rule).

Rules compared on the SAME seeded runs (run i uses the same seed under every rule):

  fisher       default: quarantine when Fisher-combined p <= escalate_alpha OR k weak alerts
  fisher_only  Fisher-combined p only
  counter      quarantine after k weak alerts in the window, p-values ignored

Strong alerts (p <= strong_alpha) quarantine immediately under every rule, so
the rules differ only in how weak WATCH alerts accumulate.

(a) Honest long runs: `--transmissions` honest transmissions on one engine, repeated
    `--runs` times -> false-quarantine rate (Wilson CI).
(b) Attack runs: every transmission tapped by intercept-resend at rate f
    (f=0.2 weak partial, f=1.0 eve_intercept) -> transmissions until QUARANTINE
    (mean and median with seeded bootstrap CIs; runs that never quarantine
    within `--cap` are censored and counted at the cap).

A simulated clock advances `--interarrival` seconds per transmission, so the
WATCH window (900 s) spans about 15 transmissions at the default 60 s.

    python experiments/ablate_escalation.py                       # L = 16 32, 100 honest runs x 500
    python experiments/ablate_escalation.py --runs 20 --transmissions 200 --bits 16

Writes experiments/ablate_escalation.csv, .md and .png (chart needs matplotlib; skipped if absent).
"""
import argparse
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatType  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.policy import ResponsePolicy  # noqa: E402
from src.quantum_engine.security import SecurityParameters  # noqa: E402

RULES = ("fisher", "fisher_only", "counter")
LABELS = {"fisher": "Fisher + k-strike (default)", "fisher_only": "Fisher only", "counter": "k-alert counter"}
FIELDS = ("experiment", "L", "condition", "rule", "runs", "length", "quarantined", "rate", "rate_lo", "rate_hi",
          "mean_alerts", "mean_tx", "mean_lo", "mean_hi", "median_tx", "median_lo", "median_hi", "censored")


class SimClock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _engine(rule, k, depolarizing, clock):
    params = SecurityParameters()
    policy = ResponsePolicy(strong_alpha=params.strong_alpha, watch_strikes=k, escalation=rule)
    return TeleportationQDS(params=params, backend="statevector", channel=ChannelModel(depolarizing=depolarizing),
                            clock=clock, policy=policy)


def run_sequence(task):
    """
    One run on a fresh engine. task = (rule, n_bits, length, intercept_rate or None, seed_key, k,
    depolarizing, interarrival). Returns (transmissions until quarantine or None, weak alerts seen).
    """
    rule, n_bits, length, rate, seed_key, k, dep, interarrival = task
    rng = np.random.default_rng(seed_key)
    clock = SimClock()
    eng = _engine(rule, k, dep, clock)
    scenario = (ThreatScenarioConfig(threat_type=ThreatType.AUTHENTIC) if rate is None else
                ThreatScenarioConfig(threat_type=ThreatType.EVE_INTERCEPT, channel_intercept_rate=rate))
    alerts = 0
    for i in range(1, length + 1):
        clock.t += interarrival
        r = eng.execute_protocol("escalation ablation", n_bits, rng=rng, scenario=scenario)
        alerts += r.response.response_action == "watch"
        if r.enforcement["link_state"] == "quarantined":
            return i, alerts
    return None, alerts


def bootstrap_ci(values, stat, rng, n_boot=2000):
    if len(values) < 2:
        v = float(stat(values)) if len(values) else float("nan")
        return v, v
    arr = np.asarray(values, dtype=float)
    boots = [stat(arr[rng.integers(0, len(arr), len(arr))]) for _ in range(n_boot)]
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def summarise(experiment, n_bits, condition, rule, length, results, seed):
    runs = len(results)
    hits = [t for t, _ in results if t is not None]
    lo, hi = wilson_interval(len(hits), runs)
    row = {"experiment": experiment, "L": n_bits, "condition": condition, "rule": rule, "runs": runs,
           "length": length, "quarantined": len(hits), "rate": round(len(hits) / runs, 4),
           "rate_lo": round(lo, 4), "rate_hi": round(hi, 4),
           "mean_alerts": round(float(np.mean([a for _, a in results])), 3),
           "censored": runs - len(hits)}
    if experiment == "attack":
        ttq = [t if t is not None else length for t, _ in results]  # censored runs counted at the cap
        brng = np.random.default_rng([seed, n_bits, RULES.index(rule), 99])
        mlo, mhi = bootstrap_ci(ttq, np.mean, brng)
        dlo, dhi = bootstrap_ci(ttq, np.median, brng)
        row.update(mean_tx=round(float(np.mean(ttq)), 3), mean_lo=round(mlo, 3), mean_hi=round(mhi, 3),
                   median_tx=float(np.median(ttq)), median_lo=dlo, median_hi=dhi)
    else:
        row.update(mean_tx=None, mean_lo=None, mean_hi=None, median_tx=None, median_lo=None, median_hi=None)
    return row


def run_ablation(bits, runs, transmissions, attack_runs, cap, rates, seed, k=3, depolarizing=0.01,
                 interarrival=60.0, workers=1):
    plan = []  # (experiment, L, condition, rule, length, tasks)
    for n_bits in bits:
        for rule in RULES:
            plan.append(("honest", n_bits, "honest", rule, transmissions,
                         [(rule, n_bits, transmissions, None, [seed, n_bits, 0, i], k, depolarizing, interarrival)
                          for i in range(runs)]))
            for j, rate in enumerate(rates, start=1):
                cond = f"intercept f={rate:g}"
                plan.append(("attack", n_bits, cond, rule, cap,
                             [(rule, n_bits, cap, rate, [seed, n_bits, j, i], k, depolarizing, interarrival)
                              for i in range(attack_runs)]))
    flat = [t for *_, tasks in plan for t in tasks]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            out = list(pool.map(run_sequence, flat, chunksize=4))
    else:
        out = [run_sequence(t) for t in flat]
    rows, pos = [], 0
    for experiment, n_bits, cond, rule, length, tasks in plan:
        row = summarise(experiment, n_bits, cond, rule, length, out[pos:pos + len(tasks)], seed)
        pos += len(tasks)
        rows.append(row)
        extra = (f"false quarantine {row['rate']:.3f} [{row['rate_lo']:.3f}, {row['rate_hi']:.3f}]"
                 if experiment == "honest" else
                 f"tx to quarantine mean {row['mean_tx']} [{row['mean_lo']}, {row['mean_hi']}] "
                 f"median {row['median_tx']:g} censored {row['censored']}")
        print(f"L={n_bits:<3} {cond:16s} {rule:12s} {extra}", flush=True)
    return rows


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def write_markdown(rows, path, meta):
    lines = [
        "# Ablation: Fisher escalation vs simple counter", "",
        f"Seed {meta['seed']}, statevector backend, depolarizing p={meta['depolarizing']}, k={meta['k']}, "
        f"{meta['interarrival']:g} s between transmissions (WATCH window 900 s). Generated {meta['generated']}. "
        "Every rule sees the same seeded runs.", "",
        "## Honest long runs: false quarantine", "",
        "| L | rule | runs x transmissions | false quarantine [95% Wilson] | mean weak alerts / run |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        if r["experiment"] == "honest":
            lines.append(f"| {r['L']} | {LABELS[r['rule']]} | {r['runs']} x {r['length']} | "
                         f"{r['rate']:.3f} [{r['rate_lo']:.3f}, {r['rate_hi']:.3f}] | {r['mean_alerts']} |")
    lines += ["", "## Attack runs: transmissions until QUARANTINE", "",
              f"Censored runs (no quarantine within the cap of {meta['cap']}) are counted at the cap, "
              "so means/medians with censored runs are lower bounds. CIs: seeded bootstrap (2000 resamples).", "",
              "| L | condition | rule | runs | mean [95% CI] | median [95% CI] | censored |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["experiment"] == "attack":
            lines.append(f"| {r['L']} | {r['condition']} | {LABELS[r['rule']]} | {r['runs']} | "
                         f"{r['mean_tx']} [{r['mean_lo']}, {r['mean_hi']}] | "
                         f"{r['median_tx']:g} [{r['median_lo']:g}, {r['median_hi']:g}] | {r['censored']} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(rows, path):
    """False-quarantine rate and median time-to-quarantine per rule, with CIs. Returns False if no matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    colors = {"fisher": "#2a78d6", "fisher_only": "#1baf7a", "counter": "#eb6834"}  # categorical slots 1, 3, 2
    bits = sorted({r["L"] for r in rows})
    conds = sorted({r["condition"] for r in rows if r["experiment"] == "attack"})
    by = {(r["experiment"], r["L"], r["condition"], r["rule"]): r for r in rows}
    panels = [("honest", "honest", "Honest false-quarantine rate")] + \
             [("attack", c, f"Median transmissions to quarantine: {c}") for c in conds]
    fig, axes = plt.subplots(1, len(panels), figsize=(4.6 * len(panels), 4.2), squeeze=False)
    x = np.arange(len(bits))
    w = 0.8 / len(RULES)
    for ax, (exp, cond, title) in zip(axes[0], panels):
        for k, rule in enumerate(RULES):
            rs = [by.get((exp, L, cond, rule)) for L in bits]
            key = ("rate", "rate_lo", "rate_hi") if exp == "honest" else ("median_tx", "median_lo", "median_hi")
            vals = [r[key[0]] if r else 0 for r in rs]
            err = [[v - (r[key[1]] if r else 0) for v, r in zip(vals, rs)],
                   [(r[key[2]] if r else 0) - v for v, r in zip(vals, rs)]]
            ax.bar(x + (k - (len(RULES) - 1) / 2) * w, vals, w - 0.02, yerr=err, capsize=3, color=colors[rule],
                   error_kw={"elinewidth": 1, "ecolor": "#52514e"}, label=LABELS[rule])
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_xticks(x, [f"L={L}" for L in bits])
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", color="#e5e4df", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0][0].legend(frameon=False, fontsize=8)
    fig.suptitle("Fisher escalation vs k-alert counter (95% CIs)", x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, nargs="+", default=[16, 32])
    ap.add_argument("--runs", type=int, default=100, help="honest long runs per (L, rule)")
    ap.add_argument("--transmissions", type=int, default=500, help="honest transmissions per run")
    ap.add_argument("--attack-runs", type=int, default=100)
    ap.add_argument("--cap", type=int, default=200, help="max transmissions per attack run")
    ap.add_argument("--rates", type=float, nargs="+", default=[0.2, 1.0], help="intercept-resend fractions")
    ap.add_argument("--k", type=int, default=3, help="alerts for the counter rule (and the default backstop)")
    ap.add_argument("--interarrival", type=float, default=60.0, help="simulated seconds between transmissions")
    ap.add_argument("--depolarizing", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--trials", type=int, default=None, help="shorthand: sets --runs and --attack-runs")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args(argv)
    if args.trials is not None:
        args.runs = args.attack_runs = args.trials

    rows = run_ablation(args.bits, args.runs, args.transmissions, args.attack_runs, args.cap, args.rates,
                        args.seed, args.k, args.depolarizing, args.interarrival, args.workers)
    meta = {"seed": args.seed, "depolarizing": args.depolarizing, "k": args.k, "interarrival": args.interarrival,
            "cap": args.cap, "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, "ablate_escalation")
    write_csv(rows, base + ".csv")
    write_markdown(rows, base + ".md", meta)
    print(f"\nWrote {base}.csv and {base}.md")
    if plot(rows, base + ".png"):
        print(f"Wrote {base}.png")
    else:
        print("matplotlib not installed: chart skipped (pip install matplotlib).")
    return rows


if __name__ == "__main__":
    main()
