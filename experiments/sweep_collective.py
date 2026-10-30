"""
Sweep ONE concrete collective (ancilla-probe) attack, EVE_COLLECTIVE (B3).

This is one specific collective attack (same controlled-Ry(theta) probe on every
token, ancillas measured individually after basis announcement). It is NOT a
proof of security against collective attacks in general.

For theta in [0, pi/2] and L = 16/32/64 it runs seeded honest-signer transmissions
with every token probed and records, per cell (95% Wilson intervals):

  mismatch_rate   verifier per-copy elimination mismatches of the genuine signature
                  (pooled over both verifiers and all trials) - the disturbance
  eve_accuracy    Eve's per-copy bit-guess accuracy from her ancillas - the information
  detection_rate  share of transmissions the blind detector flags

    python experiments/sweep_collective.py                    # 200 trials per cell
    python experiments/sweep_collective.py --trials 50 --bits 32

Writes sweep_collective.csv, .md (detection table) and .png (trade-off + detection).
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatSuite  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.elimination import OrthogonalEliminationEngine  # noqa: E402

THETAS = tuple(round(k * math.pi / 16, 4) for k in range(9))  # 0 .. pi/2
FIELDS = ("L", "theta", "trials", "mismatches", "copies", "mismatch_rate", "mismatch_lo", "mismatch_hi",
          "eve_correct", "eve_guesses", "eve_accuracy", "eve_lo", "eve_hi",
          "detected", "detection_rate", "detection_lo", "detection_hi")


def copy_mismatches(engine, session):
    """(mismatches, copies) of the genuine signature against both verifiers' eliminated records."""
    m = n = 0
    for verifier in engine.verifiers.values():
        record = verifier.records.get(session.context.session_id)
        if record is not None:
            mi, ni, _ = OrthogonalEliminationEngine.count_mismatches(session.signature, record.eliminated)
            m, n = m + mi, n + ni
    return m, n


def _rate(k, n, prefix):
    lo, hi = wilson_interval(k, n)
    return {f"{prefix}_rate" if prefix != "eve" else "eve_accuracy": round(k / n, 4) if n else None,
            f"{prefix}_lo": round(lo, 4), f"{prefix}_hi": round(hi, 4)}


def run_cell(theta, n_bits, trials, seed, depolarizing=0.01):
    rng = np.random.default_rng([seed, n_bits, int(round(theta * 1e4))])
    channel = ChannelModel(depolarizing=depolarizing)
    mism = copies = correct = guesses = detected = 0
    for _ in range(trials):
        eng = TeleportationQDS(backend="statevector", channel=channel)
        transcript, eve = ThreatSuite.eve_collective(eng, theta, "collective sweep", n_bits, "alice", rng, channel)
        m, n = copy_mismatches(eng, transcript.session)  # before assess(): a quarantine purges the records
        mism, copies = mism + m, copies + n
        correct, guesses = correct + sum(eve.guess_correct), guesses + len(eve.guess_correct)
        detected += eng.assess(transcript).threat_report.is_threat_detected
    return {"L": n_bits, "theta": theta, "trials": trials, "mismatches": mism, "copies": copies,
            **_rate(mism, copies, "mismatch"), "eve_correct": correct, "eve_guesses": guesses,
            **_rate(correct, guesses, "eve"), "detected": detected, **_rate(detected, trials, "detection")}


def write_markdown(rows, path, seed):
    bits = sorted({r["L"] for r in rows})
    lines = ["# One collective (ancilla-probe) attack: EVE_COLLECTIVE", "",
             "**Scope:** one concrete collective attack (the same controlled-Ry(theta) probe on every token, "
             "ancillas measured individually after the bases are announced). This is not a proof of security "
             "against collective attacks in general.", "",
             f"Seed {seed}, {rows[0]['trials']} trials per cell, statevector backend, depolarizing p=0.01. "
             "Rates with 95% Wilson intervals.", "",
             "## Detection rate", "", "| theta | " + " | ".join(f"L={L}" for L in bits) + " |",
             "|---|" + "---|" * len(bits)]
    by = {(r["theta"], r["L"]): r for r in rows}
    for theta in sorted({r["theta"] for r in rows}):
        lines.append(f"| {theta:.4f} | " + " | ".join(
            f"{by[(theta, L)]['detection_rate']:.3f} [{by[(theta, L)]['detection_lo']:.3f}, "
            f"{by[(theta, L)]['detection_hi']:.3f}]" for L in bits) + " |")
    lines += ["", "## Disturbance vs information (pooled over L)", "",
              "| theta | verifier mismatch rate | Eve bit-guess accuracy |", "|---|---|---|"]
    for theta in sorted({r["theta"] for r in rows}):
        cell = [r for r in rows if r["theta"] == theta]
        m, n = sum(r["mismatches"] for r in cell), sum(r["copies"] for r in cell)
        k, g = sum(r["eve_correct"] for r in cell), sum(r["eve_guesses"] for r in cell)
        (ml, mh), (el, eh) = wilson_interval(m, n), wilson_interval(k, g)
        lines.append(f"| {theta:.4f} | {m / n:.4f} [{ml:.4f}, {mh:.4f}] | {k / g:.4f} [{el:.4f}, {eh:.4f}] |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def plot(rows, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    colors = ("#2a78d6", "#eb6834", "#1baf7a")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    for color, L in zip(colors, sorted({r["L"] for r in rows})):
        rs = sorted((r for r in rows if r["L"] == L), key=lambda r: r["theta"])
        a1.errorbar([r["mismatch_rate"] for r in rs], [r["eve_accuracy"] for r in rs],
                    xerr=[[r["mismatch_rate"] - r["mismatch_lo"] for r in rs],
                          [r["mismatch_hi"] - r["mismatch_rate"] for r in rs]],
                    marker="o", ms=4, lw=1.5, color=color, label=f"L={L}")
        a2.errorbar([r["theta"] for r in rs], [r["detection_rate"] for r in rs],
                    yerr=[[r["detection_rate"] - r["detection_lo"] for r in rs],
                          [r["detection_hi"] - r["detection_rate"] for r in rs]],
                    marker="o", ms=4, lw=1.5, capsize=3, color=color, label=f"L={L}")
    a1.set(xlabel="verifier mismatch rate (disturbance)", ylabel="Eve bit-guess accuracy (information)",
           title="Disturbance vs information")
    a2.set(xlabel="probe strength theta (rad)", ylabel="detection rate", title="Detection vs theta", ylim=(0, 1.05))
    for ax in (a1, a2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("One concrete collective (ancilla-probe) attack - not a general proof", x=0.01, ha="left",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--bits", type=int, nargs="+", default=[16, 32, 64])
    ap.add_argument("--thetas", type=float, nargs="+", default=list(THETAS))
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args(argv)

    rows = []
    for n_bits in args.bits:
        for theta in args.thetas:
            rows.append(run_cell(theta, n_bits, args.trials, args.seed))
            r = rows[-1]
            print(f"L={n_bits:<3} theta={theta:.4f}  mismatch {r['mismatch_rate']:.4f}  "
                  f"eve {r['eve_accuracy']:.4f}  detected {r['detection_rate']:.3f}", flush=True)
    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, "sweep_collective")
    with open(base + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    write_markdown(rows, base + ".md", args.seed)
    print(f"Wrote {base}.csv, .md" + (" and .png" if plot(rows, base + ".png") else " (no matplotlib: no chart)"))
    return rows


if __name__ == "__main__":
    main()
