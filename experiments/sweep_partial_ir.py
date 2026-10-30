"""
Sweep partial intercept-resend attack (EVE_PARTIAL_INTERCEPT) across
interception fractions and token lengths.

Grid
----
  Interception fractions : 0.05, 0.10, 0.20, 0.30, 0.50, 0.75, 1.00
  Token lengths (n_bits) : 16, 32, 64
  Trials per cell        : 200   (default)
  Total trials           : 7 x 3 x 200 = 4 200

Outputs
-------
  experiments/sweep_partial_ir.csv   -- one row per (n_bits, fraction) cell
  experiments/sweep_partial_ir.png   -- detection rate vs fraction, one series
                                        per token length with Wilson CI bars
                                        (requires matplotlib; skipped if absent)

Metrics
-------
  detection_rate   : proportion of trials where threat_report.is_threat_detected
                     is True (protocol classified outcome as outside BENIGN).
  wilson_lo/hi     : 95% Wilson score CI for the detection proportion, computed
                     with wilson_interval() from channel.py (no new dependency).
  qber_*           : statistics of the test-token QBER across trials.
                     Denominator = test_count (measured sacrificed test tokens,
                     not all tokens, not sifted key bits).
  info_gain_proxy  : the configured interception fraction f.  This is the
                     expected fraction of tokens Eve measures, not a full
                     mutual-information quantity.
  expected_qber    : ChannelModel(intercept_rate=f).expected_qber() -- an
                     analytical expectation, not a measured value.

Threshold report
----------------
  For each token length the script reports the smallest *tested* fraction
  whose lower Wilson bound is >= 0.95.  If no tested fraction qualifies,
  "no tested fraction qualifies" is reported.

Usage
-----
  python experiments/sweep_partial_ir.py
  python experiments/sweep_partial_ir.py --trials 200 --bits 16 32 64 --seed 2026
  python experiments/sweep_partial_ir.py --fractions 0.05 0.1 0.5 1.0 --out .

Statistical note
----------------
  Random-basis intercept-resend produces an expected QBER of approximately
  0.25 * f (plus background depolarizing noise) under BB84-style assumptions.
  This is an expectation; observed values fluctuate.  For small token lengths
  (n_bits=16) and small f (0.05), the expected QBER is near the honest threshold
  (e0=0.02) and many trials will not trigger the channel alarm.

  This script is a simulation.  It does not claim physical hardware security
  guarantees.
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import (  # noqa: E402
    ChannelModel,
    TeleportationQDS,
    ThreatScenarioConfig,
    ThreatType,
)
from src.quantum_engine.channel import wilson_interval  # noqa: E402

# ---------------------------------------------------------------------------
# Default grid
# ---------------------------------------------------------------------------
DEFAULT_FRACTIONS = [0.05, 0.10, 0.20, 0.30, 0.50, 0.75, 1.00]
DEFAULT_BITS = [16, 32, 64]
DEFAULT_TRIALS = 200
DEFAULT_SEED = 2026


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_nan(x):
    """Return True if x is a float NaN."""
    try:
        return x != x
    except TypeError:
        return False


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def run_sweep(
    fractions=None,
    lengths=None,
    trials_per_cell=DEFAULT_TRIALS,
    seed=DEFAULT_SEED,
    depolarizing=0.01,
):
    """
    Run the partial intercept-resend sweep and return a list of result dicts.

    Randomness convention
    ---------------------
    A single np.random.Generator is created from *seed* and threaded
    sequentially through all trials (outer loop: n_bits; inner: fraction;
    innermost: trial index).  This matches sweep_tiers.py and sweep_damping.py.

    Returns
    -------
    list of dict, one dict per (n_bits, fraction) cell.
    """
    if fractions is None:
        fractions = DEFAULT_FRACTIONS
    if lengths is None:
        lengths = DEFAULT_BITS

    rng = np.random.default_rng(seed)
    results = []

    total = len(lengths) * len(fractions) * trials_per_cell
    print(
        "sweep_partial_ir: %d lengths x %d fractions x %d trials = %d trials total"
        % (len(lengths), len(fractions), trials_per_cell, total)
    )
    hdr = "%-8s | %-6s | %-9s | %-9s | %-10s | %-10s | %-10s | %-13s"
    print(hdr % ("n_bits", "f", "det/N", "det_rate", "wilson_lo", "wilson_hi",
                 "qber_mean", "expected_qber"))
    print("-" * 90)

    for n_bits in lengths:
        for f in fractions:
            det_count = 0
            qbers = []

            for trial_idx in range(trials_per_cell):
                # Fresh engine per trial: avoids circuit-breaker state leaking.
                eng = TeleportationQDS(
                    backend="statevector",
                    channel=ChannelModel(depolarizing=depolarizing),
                )
                scenario = ThreatScenarioConfig(
                    threat_type=ThreatType.EVE_PARTIAL_INTERCEPT,
                    partial_intercept_fraction=f,
                )
                try:
                    res = eng.execute_protocol(
                        message_text="PIR_%d_%s_%d" % (n_bits, f, trial_idx),
                        n_bits=n_bits,
                        rng=rng,
                        scenario=scenario,
                    )
                except Exception:
                    # Quarantine or enforcement blocker counts as detected.
                    det_count += 1
                    continue

                if res.threat_report.is_threat_detected:
                    det_count += 1

                ct = res.transcript.channel_test
                if ct is not None:
                    qbers.append(ct.qber_estimate)

            n = trials_per_cell
            det_rate = det_count / n
            lo, hi = wilson_interval(det_count, n)

            qber_mean = float(np.mean(qbers)) if qbers else float("nan")
            qber_std  = float(np.std(qbers))  if qbers else float("nan")
            qber_min  = float(np.min(qbers))  if qbers else float("nan")
            qber_max  = float(np.max(qbers))  if qbers else float("nan")

            expected_q = ChannelModel(
                depolarizing=depolarizing, intercept_rate=f
            ).expected_qber()

            row = {
                "n_bits": n_bits,
                "intercept_fraction": f,
                "depolarizing": depolarizing,
                "trials": n,
                "detection_count": det_count,
                "detection_rate": round(det_rate, 6),
                "wilson_lo": round(lo, 6),
                "wilson_hi": round(hi, 6),
                "qber_mean": round(qber_mean, 6) if not _is_nan(qber_mean) else "",
                "qber_std":  round(qber_std,  6) if not _is_nan(qber_std)  else "",
                "qber_min":  round(qber_min,  6) if not _is_nan(qber_min)  else "",
                "qber_max":  round(qber_max,  6) if not _is_nan(qber_max)  else "",
                "expected_qber": round(expected_q, 6),
                "info_gain_proxy_configured": f,
            }
            results.append(row)

            print(
                "%-8d | %-6.2f | %d/%-6d | %-9.4f | %-10.4f | %-10.4f | %-10.4f | %-13.6f"
                % (n_bits, f, det_count, n, det_rate, lo, hi, qber_mean, expected_q)
            )

    return results


# ---------------------------------------------------------------------------
# Threshold report
# ---------------------------------------------------------------------------

def threshold_report(results, lengths):
    """
    For each token length, return the smallest tested interception fraction
    whose lower Wilson 95% CI bound is >= 0.95.

    Returns dict mapping n_bits -> fraction or None.
    """
    report = {}
    for n_bits in lengths:
        rows = [r for r in results if r["n_bits"] == n_bits]
        qualifying = [
            r["intercept_fraction"]
            for r in rows
            if isinstance(r["wilson_lo"], (int, float)) and r["wilson_lo"] >= 0.95
        ]
        report[n_bits] = min(qualifying) if qualifying else None
    return report


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "n_bits",
    "intercept_fraction",
    "depolarizing",
    "trials",
    "detection_count",
    "detection_rate",
    "wilson_lo",
    "wilson_hi",
    "qber_mean",
    "qber_std",
    "qber_min",
    "qber_max",
    "expected_qber",
    "info_gain_proxy_configured",
]


def write_csv(results, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print("Saved CSV to: %s" % path)


# ---------------------------------------------------------------------------
# Optional plot (requires matplotlib)
# ---------------------------------------------------------------------------

def write_plot(results, lengths, fractions, path):
    """Plot detection rate vs f with Wilson CI bars (one series per n_bits)."""
    try:
        import matplotlib
        matplotlib.use("Agg")          # headless; must be before pyplot import
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "WARNING: matplotlib is not installed. "
            "Install it to generate the PNG plot."
        )
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    markers = ["o", "s", "^"]
    colors  = ["#1f77b4", "#ff7f0e", "#2ca02c"]

    for i, n_bits in enumerate(lengths):
        rows = [r for r in results if r["n_bits"] == n_bits]
        xs  = [r["intercept_fraction"] for r in rows]
        ys  = [r["detection_rate"]     for r in rows]
        los = [r["detection_rate"] - r["wilson_lo"] for r in rows]
        his = [r["wilson_hi"] - r["detection_rate"] for r in rows]
        ax.errorbar(
            xs, ys, yerr=[los, his],
            fmt=markers[i % len(markers)] + "-",
            color=colors[i % len(colors)],
            capsize=4,
            label="n_bits=%d" % n_bits,
            linewidth=1.5,
            markersize=6,
        )

    ax.axhline(0.95, color="black", linestyle="--", linewidth=1, label="95% threshold")
    ax.set_xlabel("Interception fraction f", fontsize=12)
    ax.set_ylabel("Detection rate (%d trials)" % DEFAULT_TRIALS, fontsize=12)
    ax.set_title(
        "Partial Intercept-Resend: Detection Rate vs Interception Fraction\n"
        "(Wilson 95%% CI bars; statevector simulation, depolarizing=0.01)",
        fontsize=11,
    )
    ax.set_xlim(0, 1.05)
    ax.set_ylim(-0.05, 1.10)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close(fig)
    print("Saved plot to: %s" % path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Sweep partial intercept-resend attack across fractions and token lengths."
    )
    ap.add_argument("--trials", type=int, default=DEFAULT_TRIALS,
                    help="Trials per cell (default: 200)")
    ap.add_argument("--bits", type=int, nargs="+", default=DEFAULT_BITS,
                    help="Token lengths (default: 16 32 64)")
    ap.add_argument("--fractions", type=float, nargs="+", default=DEFAULT_FRACTIONS,
                    help="Interception fractions (default: 0.05 0.1 0.2 0.3 0.5 0.75 1.0)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="Master random seed (default: 2026)")
    ap.add_argument("--depolarizing", type=float, default=0.01,
                    help="Background depolarizing noise (default: 0.01)")
    ap.add_argument("--out", type=str, default=HERE,
                    help="Output directory for CSV and PNG (default: experiments/)")
    args = ap.parse_args()

    t_start = time.time()
    results = run_sweep(
        fractions=args.fractions,
        lengths=args.bits,
        trials_per_cell=args.trials,
        seed=args.seed,
        depolarizing=args.depolarizing,
    )

    csv_path = os.path.join(args.out, "sweep_partial_ir.csv")
    png_path = os.path.join(args.out, "sweep_partial_ir.png")
    write_csv(results, csv_path)
    write_plot(results, args.bits, args.fractions, png_path)

    thr = threshold_report(results, args.bits)
    print("\n--- Per-length threshold (smallest f with Wilson-lo >= 0.95) ---")
    for n_bits, fq in thr.items():
        if fq is None:
            print("  n_bits=%d: no tested fraction qualifies" % n_bits)
        else:
            print("  n_bits=%d: smallest qualifying tested fraction = %s" % (n_bits, fq))

    elapsed = time.time() - t_start
    print("\nDone in %.1fs.  Total cells: %d." % (elapsed, len(results)))


if __name__ == "__main__":
    main()
