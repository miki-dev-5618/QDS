"""
Ablation: fixed vs adaptive allocation (C2).

  fixed     SecurityParameters(allocation_policy="legacy", reserve_policy="off"):
            max(16, L) test tokens, no reserve (the pre-C2 rule)
  adaptive  C2 defaults: power-targeted test budget + L-aware reserve

For honest, eve_forgery, eve_intercept and repudiation at each L, both modes run
the SAME seeded trials. Reported with 95% Wilson CIs: rejected (honest: false
rejection; attacks: detection), UNDETERMINED rate, and mean tokens sent.

    python experiments/ablate_adaptive.py                  # 200 trials, L = 16 32 64

Writes experiments/ablate_adaptive.csv and .png. Needs C2 (SecurityParameters
.allocation_policy); before C2 is merged it prints a notice and writes nothing.
"""
import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatType  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.security import SecurityParameters  # noqa: E402

SCENARIOS = (ThreatType.AUTHENTIC, ThreatType.EVE_FORGERY, ThreatType.EVE_INTERCEPT, ThreatType.REPUDIATION)
MODES = {"fixed": {"allocation_policy": "legacy", "reserve_policy": "off"}, "adaptive": {}}
FIELDS = ("L", "scenario", "mode", "trials", "rejected", "rejected_lo", "rejected_hi",
          "undetermined", "undetermined_lo", "undetermined_hi", "mean_tokens")


def c2_available() -> bool:
    return "allocation_policy" in SecurityParameters.__dataclass_fields__


def run_cell(threat, n_bits, mode, trials, seed):
    params = SecurityParameters(**MODES[mode])
    rng = np.random.default_rng([seed, n_bits, SCENARIOS.index(threat)])  # same stream for both modes
    rejected = undetermined = 0
    tokens = []
    for _ in range(trials):
        eng = TeleportationQDS(params=params, backend="statevector", channel=ChannelModel(depolarizing=0.01))
        r = eng.execute_protocol("ablation", n_bits, rng=rng, scenario=ThreatScenarioConfig(threat_type=threat))
        rejected += r.threat_report.is_threat_detected
        undetermined += r.threat_report.classification.value == "UNDETERMINED_DISTURBANCE"
        tokens.append(r.transcript.session.tokens_sent)
    rlo, rhi = wilson_interval(rejected, trials)
    ulo, uhi = wilson_interval(undetermined, trials)
    return {"L": n_bits, "scenario": threat.value, "mode": mode, "trials": trials,
            "rejected": round(rejected / trials, 4), "rejected_lo": round(rlo, 4), "rejected_hi": round(rhi, 4),
            "undetermined": round(undetermined / trials, 4), "undetermined_lo": round(ulo, 4),
            "undetermined_hi": round(uhi, 4), "mean_tokens": round(float(np.mean(tokens)), 2)}


def plot(rows, path):
    """Grouped bars: one panel per scenario (rejected rate) plus honest tokens; fixed vs adaptive side by side."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    bits = sorted({r["L"] for r in rows})
    by = {(r["L"], r["scenario"], r["mode"]): r for r in rows}
    panels = [(t.value, "rejected") for t in SCENARIOS] + [("authentic", "mean_tokens")]
    fig, axes = plt.subplots(1, len(panels), figsize=(3.6 * len(panels), 3.8))
    x = np.arange(len(bits))
    for ax, (scen, key) in zip(axes, panels):
        for k, (mode, color) in enumerate((("fixed", "#2a78d6"), ("adaptive", "#eb6834"))):
            rs = [by[(L, scen, mode)] for L in bits]
            vals = [r[key] for r in rs]
            err = None if key == "mean_tokens" else [[v - r["rejected_lo"] for v, r in zip(vals, rs)],
                                                     [r["rejected_hi"] - v for v, r in zip(vals, rs)]]
            ax.bar(x + (k - 0.5) * 0.4, vals, 0.38, yerr=err, capsize=3, color=color, label=mode)
        ax.set_title(("tokens sent: " if key == "mean_tokens" else
                      "false rejection: " if scen == "authentic" else "detection: ") + scen, fontsize=9, loc="left")
        ax.set_xticks(x, [f"L={L}" for L in bits])
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--bits", type=int, nargs="+", default=[16, 32, 64])
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args(argv)
    if not c2_available():
        print("C2 is not merged yet (SecurityParameters has no allocation_policy). Nothing to ablate.")
        return []

    rows = [run_cell(t, L, mode, args.trials, args.seed) for L in args.bits for t in SCENARIOS for mode in MODES]
    for r in rows:
        print(f"L={r['L']:<3} {r['scenario']:14s} {r['mode']:8s} rejected {r['rejected']:.3f} "
              f"[{r['rejected_lo']:.3f}, {r['rejected_hi']:.3f}]  undetermined {r['undetermined']:.3f}  "
              f"tokens {r['mean_tokens']}")
    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, "ablate_adaptive")
    with open(base + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {base}.csv" + (f" and {base}.png" if plot(rows, base + ".png") else " (no matplotlib: no chart)"))
    return rows


if __name__ == "__main__":
    main()
