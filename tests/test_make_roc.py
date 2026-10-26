"""D2: ROC curves, AUC with bootstrap CI and operating points, computed from harness raw.jsonl only."""
import csv
import os
import sys

import numpy as np
import pytest

EXPERIMENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments")
if EXPERIMENTS not in sys.path:
    sys.path.insert(0, EXPERIMENTS)

import harness  # noqa: E402
import make_roc  # noqa: E402
from src.quantum_engine import SecurityParameters  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _trial(m, n, mode="direct"):
    return {"verifications": [{"verifier": "bob", "mode": mode, "mismatches": m, "n_checked": n, "accepted": True}]}


def test_auc_extremes_and_ties():
    assert make_roc.auc([0.5, 0.6], [0.1, 0.2]) == 1.0
    assert make_roc.auc([0.1, 0.2], [0.5, 0.6]) == 0.0
    assert make_roc.auc([0.3, 0.3], [0.3, 0.3]) == 0.5


def test_auc_matches_brute_force():
    rng = np.random.default_rng(3)
    pos, neg = rng.integers(0, 5, 40) / 4, rng.integers(0, 5, 30) / 4
    brute = np.mean([(p > q) + 0.5 * (p == q) for p in pos for q in neg])
    assert make_roc.auc(pos, neg) == pytest.approx(brute)


def test_roc_curve_runs_from_all_flagged_to_none_flagged():
    _, fpr, tpr = make_roc.roc_curve([0.2, 0.4], [0.0, 0.1])
    assert (fpr[0], tpr[0]) == (1.0, 1.0) and (fpr[-1], tpr[-1]) == (0.0, 0.0)
    assert np.all(np.diff(fpr) <= 0) and np.all(np.diff(tpr) <= 0)


def test_bootstrap_ci_is_seeded_and_brackets_the_auc():
    pos, neg = [0.3, 0.2, 0.25, 0.1, 0.4], [0.0, 0.05, 0.1, 0.0, 0.2]
    a = make_roc.bootstrap_auc_ci(pos, neg, 200, np.random.default_rng(1))
    b = make_roc.bootstrap_auc_ci(pos, neg, 200, np.random.default_rng(1))
    assert a == b and a[0] <= make_roc.auc(pos, neg) <= a[1]


def test_score_and_operating_point_rules():
    p = SecurityParameters()
    assert make_roc.score(_trial(3, 12)) == 0.25
    assert make_roc.score({"verifications": []}) == 1.0           # aborted: never revealed
    assert make_roc.hoeffding_reject({"verifications": []}, p) and make_roc.exact_reject({"verifications": []}, p)
    n = 40
    limit = int(p.s_a * n)                      # Hoeffding: floor(s_a * n), whatever threshold_policy says
    assert make_roc.hoeffding_limit(n, False, p) == limit
    assert not make_roc.hoeffding_reject(_trial(limit, n), p)
    assert make_roc.hoeffding_reject(_trial(limit + 1, n), p)
    # forwarded signatures are judged against the looser s_v limit
    assert make_roc.hoeffding_limit(n, True, p) == int(p.s_v * n) > limit
    assert not make_roc.hoeffding_reject(_trial(limit + 1, n, "forwarded"), p)


def test_make_roc_end_to_end_from_harness_output(tmp_path):
    out = str(tmp_path)
    harness.main(["--trials", "8", "--bits", "16", "32", "--profiles", "depolarizing", "--workers", "1",
                  "--only", "authentic", "eve_forgery", "dishonest_bob", "--out", out])
    assert make_roc.main(["--raw", os.path.join(out, "raw.jsonl"), "--bootstrap", "50", "--out", out]) == 0
    with open(os.path.join(out, "roc_auc.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert {(r["n_bits"], r["attack"]) for r in rows} == {
        (b, a) for b in ("16", "32") for a in ("eve_forgery", "dishonest_bob")}
    for r in rows:
        assert 0.0 <= float(r["auc_ci_low"]) <= float(r["auc"]) <= float(r["auc_ci_high"]) <= 1.0
        assert r["hoeffding_fpr"] != "" and r["exact_tpr"] != ""
        assert int(r["n_positive"]) == 8 and int(r["n_negative"]) == 8
    for b in (16, 32):
        for ext in ("png", "svg"):
            assert os.path.getsize(os.path.join(out, f"roc_L{b}.{ext}")) > 0
    first = _read(os.path.join(out, "roc_auc.csv"))
    make_roc.main(["--raw", os.path.join(out, "raw.jsonl"), "--bootstrap", "50", "--out", out])
    assert _read(os.path.join(out, "roc_auc.csv")) == first   # same seed, same CI


def test_quick_and_full_runs_in_one_file_are_not_pooled(tmp_path):
    out = str(tmp_path)
    common = ["--bits", "16", "--profiles", "depolarizing", "--workers", "1",
              "--only", "authentic", "eve_forgery", "--out", out]
    harness.main(["--trials", "5"] + common)
    harness.main(["--trials", "8"] + common)          # appended to the same raw.jsonl
    raw = os.path.join(out, "raw.jsonl")
    make_roc.main(["--raw", raw, "--bootstrap", "20", "--out", out])
    with open(os.path.join(out, "roc_auc.csv"), encoding="utf-8") as f:
        (row,) = list(csv.DictReader(f))
    assert int(row["n_positive"]) == 8 and int(row["n_negative"]) == 8     # largest count, not 13
    make_roc.main(["--raw", raw, "--trials", "5", "--bootstrap", "20", "--out", out])
    with open(os.path.join(out, "roc_auc.csv"), encoding="utf-8") as f:
        (row,) = list(csv.DictReader(f))
    assert int(row["n_positive"]) == 5


def test_missing_raw_file_is_reported(tmp_path, capsys):
    assert make_roc.main(["--raw", str(tmp_path / "nope.jsonl"), "--out", str(tmp_path)]) == 1
    assert "run experiments/harness.py first" in capsys.readouterr().out
