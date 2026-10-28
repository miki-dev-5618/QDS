"""
Tight-threshold plot (B4): measured verifier mismatch rate of each tested attack
against the acceptance thresholds.

Step 1 (measure) runs seeded honest-signer transmissions under each attack and
counts per-copy elimination mismatches of the GENUINE signature, pooled over both
verifiers and all trials (95% Wilson CI). Written to tightness.csv.
Step 2 (plot) reads tightness.csv only and draws one figure: x = attack and strength,
y = mismatch rate, horizontal lines mu_h, s_a, s_v, p_min from SecurityParameters.
The caption (tightness.md, and under the figure) is generated from the data.

Attacks: cloning (universal, phase-covariant), partial intercept-resend (f),
collective ancilla probe (theta, B3). Each is one concrete attack; this plot is
not a proof against attacks that are not shown.

    python experiments/plot_tightness.py                     # measure + plot, 100 trials per point
    python experiments/plot_tightness.py --plot-only         # redraw from an existing tightness.csv

Writes tightness.csv, tightness.md, tightness.png and tightness.svg.
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatSuite, ThreatType  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.security import SecurityParameters  # noqa: E402
from sweep_collective import copy_mismatches  # noqa: E402

# (family, label, strength, scenario fields)
POINTS = (
    [("honest", "honest", 0.0, {"threat_type": ThreatType.AUTHENTIC})]
    + [("cloning", name, 1.0, {"threat_type": ThreatType.EVE_CLONING, "cloner_type": cloner})
       for name, cloner in (("universal", "universal"), ("phase-cov.", "phase_covariant"))]
    + [("partial IR", f"f={f:g}", f, {"threat_type": ThreatType.EVE_PARTIAL_INTERCEPT,
                                      "partial_intercept_fraction": f})
       for f in (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)]
    + [("collective", label, theta, {"threat_type": ThreatType.EVE_COLLECTIVE, "collective_theta": theta})
       for label, theta in (("θ=π/8", math.pi / 8), ("θ=π/4", math.pi / 4), ("θ=3π/8", 3 * math.pi / 8),
                            ("θ=π/2", math.pi / 2))]
)
FIELDS = ("family", "label", "strength", "mismatches", "copies", "rate", "lo", "hi")
FAMILY_COLOR = {"honest": "#52514e", "cloning": "#eb6834", "partial IR": "#2a78d6", "collective": "#1baf7a"}


def measure_point(scenario_fields, n_bits, trials, seed, depolarizing=0.01):
    """Pooled (mismatches, copies) of the genuine signature over `trials` attacked transmissions."""
    rng = np.random.default_rng(seed)
    channel = ChannelModel(depolarizing=depolarizing)
    m = n = 0
    for _ in range(trials):
        eng = TeleportationQDS(backend="statevector", channel=channel)
        tr = ThreatSuite.run(eng, ThreatScenarioConfig(**scenario_fields), "tightness", n_bits, "alice", rng, channel)
        mi, ni = copy_mismatches(eng, tr.session)
        m, n = m + mi, n + ni
    return m, n


def measure(n_bits, trials, seed):
    rows = []
    for i, (family, label, strength, fields) in enumerate(POINTS):
        m, n = measure_point(fields, n_bits, trials, [seed, n_bits, i])
        lo, hi = wilson_interval(m, n)
        rows.append({"family": family, "label": label, "strength": round(strength, 4), "mismatches": m,
                     "copies": n, "rate": round(m / n, 5), "lo": round(lo, 5), "hi": round(hi, 5)})
        print(f"{family:11s} {label:10s} mismatch {m / n:.4f} [{lo:.4f}, {hi:.4f}]  ({n} copies)", flush=True)
    return rows


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [{**r, **{k: float(r[k]) for k in ("strength", "rate", "lo", "hi")}} for r in csv.DictReader(f)]


def thresholds(params=None):
    p = params or SecurityParameters()
    return {"mu_h": p.mu_honest, "s_a": p.s_a, "s_v": p.s_v, "p_min": p.forger_min_mismatch}


def caption(rows, th):
    """Plain-text findings derived from the measured rows."""
    lines = []
    for family in [f for f in FAMILY_COLOR if f != "honest"]:
        pts = [r for r in rows if r["family"] == family]
        if not pts:
            continue
        above = [r for r in pts if r["lo"] > th["s_a"]]
        below = [r for r in pts if r["hi"] < th["s_a"]]
        if above:
            lines.append(f"{family}: 95% CI entirely above s_a = {th['s_a']:.4f} at "
                         + ", ".join(f"{r['label']} ({r['rate']:.4f})" for r in above) + ".")
        else:
            lines.append(f"{family}: no tested strength exceeds s_a = {th['s_a']:.4f}.")
        if below:
            close = max(below, key=lambda r: r["hi"])
            lines.append(f"  closest approach to s_a from below: {close['label']} at {close['rate']:.4f} "
                         f"(upper CI {close['hi']:.4f}, margin {th['s_a'] - close['hi']:.4f}).")
        straddle = [r["label"] for r in pts if r["lo"] <= th["s_a"] <= r["hi"]]
        if straddle:
            lines.append(f"  thin margin: CI contains s_a at {', '.join(straddle)}.")
    honest = next((r for r in rows if r["family"] == "honest"), None)
    if honest:
        lines.append(f"honest reference: {honest['rate']:.4f} [{honest['lo']:.4f}, {honest['hi']:.4f}] "
                     f"vs model mu_h = {th['mu_h']:.4f}.")
    lines.append("Rates below s_a are not caught by the elimination check alone; such attacks rely on the Tier 1 "
                 "test-token QBER test. s_a and s_v are the legacy per-copy rates (the default exact rule sets "
                 "integer limits per n). One concrete attack per family; not a proof against other attacks.")
    return lines


def plot(rows, th, base):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(12, 5.2))
    x = np.arange(len(rows))
    for i, r in enumerate(rows):
        ax.errorbar(i, r["rate"], yerr=[[r["rate"] - r["lo"]], [r["hi"] - r["rate"]]], fmt="o", ms=6, capsize=3,
                    color=FAMILY_COLOR[r["family"]], label=r["family"])
    for name, style in (("mu_h", ":"), ("s_a", "--"), ("s_v", "-."), ("p_min", "-")):
        ax.axhline(th[name], color="#52514e", lw=1, ls=style)
        ax.text(len(rows) - 0.4, th[name], f" {name} = {th[name]:.4f}", va="bottom", fontsize=8, color="#52514e")
    ax.set_xticks(x, [f"cloning\n{r['label']}" if r["family"] == "cloning" else r["label"] for r in rows],
                  fontsize=8)
    ax.set_xlim(-0.6, len(rows) + 1.6)
    ax.set_ylabel("verifier per-copy mismatch rate (95% CI)")
    handles, labels = ax.get_legend_handles_labels()
    uniq = dict(zip(labels, handles))
    ax.legend(uniq.values(), uniq.keys(), frameon=False, fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Measured mismatch rate of each tested attack vs acceptance thresholds", loc="left", fontsize=11)
    text = caption(rows, th)[:-1]
    fig.text(0.01, 0.01, "\n".join(text), fontsize=7, va="bottom", family="monospace")
    fig.tight_layout(rect=(0, 0.025 * len(text) + 0.02, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(f"{base}.{ext}", dpi=150)
    plt.close(fig)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=100, help="transmissions per attack point")
    ap.add_argument("--bits", type=int, default=32)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "tightness"))
    ap.add_argument("--plot-only", action="store_true", help="redraw from an existing tightness.csv")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, "tightness")

    if not args.plot_only:
        rows = measure(args.bits, args.trials, args.seed)
        with open(base + ".csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
    rows, th = read_csv(base + ".csv"), thresholds()
    text = caption(rows, th)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("# Tight-threshold plot\n\n"
                f"Seed {args.seed}, L={args.bits}, {args.trials} transmissions per point, depolarizing p=0.01. "
                "Per-copy elimination mismatches of the genuine signature, pooled over both verifiers.\n\n"
                + "\n".join(f"- {t}" for t in text) + "\n\n![tightness](tightness.png)\n")
    print("\n".join(text))
    print(f"Wrote {base}.csv, .md" + (", .png and .svg" if plot(rows, th, base) else " (no matplotlib: no chart)"))
    return rows


if __name__ == "__main__":
    main()
