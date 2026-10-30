"""B4: experiments/plot_tightness.py (measure -> tightness.csv -> plot + data-driven caption)."""
import csv
import os
import sys

from src.quantum_engine import ThreatType
from src.quantum_engine.security import SecurityParameters

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
import plot_tightness as pt  # noqa: E402


def _row(family, label, rate, lo, hi):
    return {"family": family, "label": label, "strength": 0.0, "rate": rate, "lo": lo, "hi": hi}


def test_thresholds_come_from_security_parameters():
    p = SecurityParameters(honest_qber=0.04)
    th = pt.thresholds(p)
    assert th == {"mu_h": p.mu_honest, "s_a": p.s_a, "s_v": p.s_v, "p_min": p.forger_min_mismatch}
    assert th["mu_h"] < th["s_a"] < th["s_v"] < th["p_min"]


def test_caption_is_derived_from_the_rows():
    th = {"mu_h": 0.01, "s_a": 0.06, "s_v": 0.11, "p_min": 0.17}
    rows = [_row("honest", "honest", 0.002, 0.001, 0.004),
            _row("partial IR", "f=0.2", 0.03, 0.02, 0.04),
            _row("partial IR", "f=0.5", 0.06, 0.05, 0.07),
            _row("partial IR", "f=1", 0.13, 0.12, 0.14),
            _row("collective", "θ=π/2", 0.04, 0.035, 0.045)]
    text = "\n".join(pt.caption(rows, th))
    assert "partial IR: 95% CI entirely above s_a = 0.0600 at f=1 (0.1300)." in text
    assert "closest approach to s_a from below: f=0.2 at 0.0300 (upper CI 0.0400, margin 0.0200)" in text
    assert "thin margin: CI contains s_a at f=0.5" in text
    assert "collective: no tested strength exceeds s_a" in text
    assert "cloning" not in text  # families without rows are not mentioned


def test_measure_point_is_seeded_and_counts_copies():
    fields = {"threat_type": ThreatType.EVE_PARTIAL_INTERCEPT, "partial_intercept_fraction": 1.0}
    a = pt.measure_point(fields, 16, 3, seed=5)
    assert a == pt.measure_point(fields, 16, 3, seed=5)
    assert a[1] > 0 and a[0] > 0


def test_main_measures_then_redraws_from_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(pt, "POINTS", pt.POINTS[:2])  # honest + one cloner keeps the test fast
    rows = pt.main(["--trials", "2", "--bits", "16", "--out", str(tmp_path)])
    for ext in ("csv", "md", "png", "svg"):
        assert (tmp_path / f"tightness.{ext}").stat().st_size > 0
    with open(tmp_path / "tightness.csv", newline="") as f:
        saved = list(csv.DictReader(f))
    saved[0].update(rate="0.5", lo="0.4", hi="0.6")  # --plot-only must use the CSV, not re-measure
    with open(tmp_path / "tightness.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pt.FIELDS)
        w.writeheader()
        w.writerows(saved)
    redrawn = pt.main(["--plot-only", "--out", str(tmp_path)])
    assert redrawn[0]["rate"] == 0.5 and len(redrawn) == len(rows)
