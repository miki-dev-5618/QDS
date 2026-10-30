"""
ROC curves for the verifier mismatch test, built only from the harness output (raw.jsonl).

Negatives are honest (authentic) runs, positives are runs of one attack type.
The score of a run is its verifier mismatch rate: the largest mismatches /
checked copies over every verification performed (direct or forwarded). A run
whose stream the channel test aborted reveals no signature, so no verifier
scores it; it is rejected regardless, and gets score 1.0 (the most suspicious
value). Sweeping the threshold t from 0 to 1 (flag iff score > t) gives one
ROC curve per attack; one figure per signature length L.

AUC (= P(score_attack > score_honest) + 0.5 P(tie)) carries a seeded bootstrap
95% percentile interval. The current operating points are marked:
  Hoeffding  reject iff mismatches > floor(s * n), s = s_a direct / s_v forwarded (security.py)
  exact      reject iff mismatches > smallest k with P(Bin(n, mu_h) > k) <= false_alarm_alpha
They are evaluated per run with its own n, so they can sit slightly off the
score curve (which uses one rate threshold for all n).

    python experiments/make_roc.py
    python experiments/make_roc.py --raw experiments/results/raw.jsonl --profile depolarizing --bootstrap 2000

Writes experiments/results/roc_points.csv, roc_auc.csv and roc_L<L>.{png,svg}.
"""
import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import harness  # noqa: E402
from harness import RESULTS_DIR, SecurityParameters  # noqa: E402
from src.quantum_engine.channel import critical_error_count  # noqa: E402

ATTACKS = ("eve_forgery", "eve_intercept", "cloning", "partial_ir", "dishonest_bob")
NEGATIVE = "authentic"
AUC_FIELDS = ["n_bits", "attack", "noise_profile", "n_positive", "n_negative", "auc", "auc_ci_low", "auc_ci_high",
              "hoeffding_fpr", "hoeffding_tpr", "exact_fpr", "exact_tpr"]
POINT_FIELDS = ["n_bits", "attack", "noise_profile", "threshold", "fpr", "tpr"]


# ------------------------------------------------------------------ scores and rules
def score(trial: dict) -> float:
    rates = [v["mismatches"] / v["n_checked"] for v in trial["verifications"] if v["n_checked"]]
    if not rates:
        return 1.0   # never revealed (channel abort) or nothing checkable: rejected anyway
    return max(rates)


def hoeffding_reject(trial: dict, params: SecurityParameters) -> bool:
    checked = [v for v in trial["verifications"] if v["n_checked"]]
    if not checked:
        return True
    return any(v["mismatches"] > (int(np.floor(params.s_v * v["n_checked"] + 1e-9))
                                  if v.get("mode") == "forwarded"
                                  else params.acceptance_limit(v["n_checked"]))
               for v in checked)


def exact_reject(trial: dict, params: SecurityParameters) -> bool:
    checked = [v for v in trial["verifications"] if v["n_checked"]]
    if not checked:
        return True
    return any(v["mismatches"] > critical_error_count(v["n_checked"], params.mu_honest, params.false_alarm_alpha)
               for v in checked)


# ------------------------------------------------------------------ ROC maths
def roc_curve(pos, neg):
    """(thresholds, fpr, tpr) for 'flag iff score > t', t from below 0 up to 1."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    thresholds = np.concatenate(([-np.inf], np.unique(np.concatenate((pos, neg, [0.0, 1.0])))))
    tpr = np.array([(pos > t).mean() for t in thresholds])
    fpr = np.array([(neg > t).mean() for t in thresholds])
    return thresholds, fpr, tpr


def auc(pos, neg) -> float:
    """Mann-Whitney AUC with ties counted as one half."""
    neg = np.sort(np.asarray(neg, float))
    pos = np.asarray(pos, float)
    below = np.searchsorted(neg, pos, side="left")
    ties = np.searchsorted(neg, pos, side="right") - below
    return float((below + 0.5 * ties).sum() / (len(pos) * len(neg)))


def bootstrap_auc_ci(pos, neg, n_boot: int, rng: np.random.Generator, level: float = 0.95):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    vals = [auc(rng.choice(pos, len(pos)), rng.choice(neg, len(neg))) for _ in range(n_boot)]
    a = (1 - level) / 2
    return float(np.quantile(vals, a)), float(np.quantile(vals, 1 - a))


# ------------------------------------------------------------------ analysis
def default_trials(cells, profile) -> int:
    """The largest per-cell trial count in the file for this profile (so a --quick run is not pooled in)."""
    counts = [c["n_trials"] for c in cells.values() if c["noise_profile"] == profile]
    return max(counts) if counts else 0


def group_trials(cells, profile, trials):
    """{n_bits: {scenario: [trial, ...]}} for one noise profile and per-cell trial count."""
    out = {}
    for cell in cells.values():
        if (cell["noise_profile"] != profile or cell.get("variant", "default") != "default"
                or cell["n_trials"] != trials):
            continue
        out.setdefault(cell["n_bits"], {}).setdefault(cell["scenario"], []).extend(cell["trials"])
    return out


def analyse(cells, profile, attacks, n_boot, seed, params, trials):
    groups = group_trials(cells, profile, trials)
    auc_rows, point_rows, curves = [], [], {}
    for n_bits in sorted(groups):
        by = groups[n_bits]
        if NEGATIVE not in by:
            continue
        neg_trials = by[NEGATIVE]
        neg = [score(t) for t in neg_trials]
        for attack in attacks:
            if attack not in by:
                continue
            pos_trials = by[attack]
            pos = [score(t) for t in pos_trials]
            th, fpr, tpr = roc_curve(pos, neg)
            # A fixed per-(L, attack) bootstrap seed keeps each CI independent of which other cells exist.
            rng = np.random.default_rng(harness.cell_seed(seed, attack, n_bits, profile))
            lo, hi = bootstrap_auc_ci(pos, neg, n_boot, rng)
            ops = {name: (float(np.mean([rule(t, params) for t in neg_trials])),
                          float(np.mean([rule(t, params) for t in pos_trials])))
                   for name, rule in (("hoeffding", hoeffding_reject), ("exact", exact_reject))}
            auc_rows.append({"n_bits": n_bits, "attack": attack, "noise_profile": profile,
                             "n_positive": len(pos), "n_negative": len(neg), "auc": round(auc(pos, neg), 4),
                             "auc_ci_low": round(lo, 4), "auc_ci_high": round(hi, 4),
                             "hoeffding_fpr": round(ops["hoeffding"][0], 4),
                             "hoeffding_tpr": round(ops["hoeffding"][1], 4),
                             "exact_fpr": round(ops["exact"][0], 4), "exact_tpr": round(ops["exact"][1], 4)})
            for t, f, p in zip(th, fpr, tpr):
                point_rows.append({"n_bits": n_bits, "attack": attack, "noise_profile": profile,
                                   "threshold": "-inf" if np.isinf(t) else round(float(t), 6),
                                   "fpr": round(float(f), 6), "tpr": round(float(p), 6)})
            curves.setdefault(n_bits, []).append((attack, fpr, tpr, auc_rows[-1], ops))
    return auc_rows, point_rows, curves


def plot(curves, out, profile):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    for n_bits, items in sorted(curves.items()):
        fig, ax = plt.subplots(figsize=(5.2, 5.0))
        ax.plot([0, 1], [0, 1], color="0.75", lw=1, ls="--")
        for i, (attack, fpr, tpr, row, ops) in enumerate(items):
            color = f"C{i}"
            ax.step(fpr, tpr, where="post", color=color, lw=1.6,
                    label=f"{attack}  AUC {row['auc']:.3f} [{row['auc_ci_low']:.3f}, {row['auc_ci_high']:.3f}]")
            ax.plot(*ops["hoeffding"], "o", color=color, ms=7, mfc="none", mew=1.6)
            ax.plot(*ops["exact"], "s", color=color, ms=6, mfc="none", mew=1.6)
        ax.plot([], [], "o", color="0.3", mfc="none", label="Hoeffding operating point")
        ax.plot([], [], "s", color="0.3", mfc="none", label="exact-binomial operating point")
        ax.set(xlim=(-0.02, 1.02), ylim=(-0.02, 1.02), xlabel="false-positive rate (honest runs flagged)",
               ylabel="true-positive rate (attacks flagged)",
               title=f"Verifier mismatch-rate ROC, L={n_bits}\n"
                     f"{profile} noise, {items[0][3]['n_negative']} honest runs")
        ax.grid(alpha=0.3)
        ax.legend(loc="lower right", fontsize=7, frameon=False)
        fig.tight_layout()
        stem = os.path.join(out, f"roc_L{n_bits}")
        fig.savefig(stem + ".png", dpi=150)
        fig.savefig(stem + ".svg", metadata={"Date": None})
        plt.close(fig)
        paths += [stem + ".png", stem + ".svg"]
    return paths


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=os.path.join(RESULTS_DIR, "raw.jsonl"))
    ap.add_argument("--profile", choices=harness.PROFILES, default="depolarizing")
    ap.add_argument("--attacks", nargs="+", default=list(ATTACKS),
                    help="attack scenarios to plot (missing ones are skipped)")
    ap.add_argument("--trials", type=int, default=None,
                    help="use cells run with this many trials (default: the largest count in the file)")
    ap.add_argument("--bootstrap", type=int, default=1000, help="bootstrap resamples for the AUC interval")
    ap.add_argument("--seed", type=int, default=2026, help="bootstrap seed")
    ap.add_argument("--out", default=RESULTS_DIR)
    args = ap.parse_args(argv)

    cells = harness.load_cells(args.raw)
    if not cells:
        print(f"No harness results in {args.raw}; run experiments/harness.py first.")
        return 1
    trials = args.trials or default_trials(cells, args.profile)
    print(f"Using {args.profile} cells with {trials} trials each from {args.raw}")
    auc_rows, point_rows, curves = analyse(cells, args.profile, args.attacks, args.bootstrap, args.seed,
                                           SecurityParameters(), trials)
    if not auc_rows:
        print(f"No '{NEGATIVE}' + attack cells for profile {args.profile} in {args.raw}.")
        return 1
    missing = sorted(set(args.attacks) - {r["attack"] for r in auc_rows})
    if missing:
        print(f"Skipped (no runs in {args.raw}): {', '.join(missing)}")

    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "roc_auc.csv"), AUC_FIELDS, auc_rows)
    write_csv(os.path.join(args.out, "roc_points.csv"), POINT_FIELDS, point_rows)
    paths = plot(curves, args.out, args.profile)
    for r in auc_rows:
        print(f"L={r['n_bits']:<3} {r['attack']:14s} AUC {r['auc']:.4f} [{r['auc_ci_low']:.4f}, {r['auc_ci_high']:.4f}]"
              f"  ({r['n_positive']} attack / {r['n_negative']} honest runs)  "
              f"Hoeffding FPR {r['hoeffding_fpr']:.3f} TPR {r['hoeffding_tpr']:.3f}  "
              f"exact FPR {r['exact_fpr']:.3f} TPR {r['exact_tpr']:.3f}")
    print(f"Wrote roc_auc.csv, roc_points.csv and {len(paths)} figures to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
