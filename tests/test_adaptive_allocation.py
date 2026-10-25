"""D5 fixed-vs-adaptive ablation (experiments/ablate_adaptive.py); the allocation itself is C2's."""
import csv
import os
import sys

import pytest

from src.quantum_engine import ThreatType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
import ablate_adaptive  # noqa: E402

needs_c2 = pytest.mark.skipif(not ablate_adaptive.c2_available(), reason="C2 not merged yet")


@pytest.mark.skipif(ablate_adaptive.c2_available(), reason="C2 is merged")
def test_without_c2_writes_nothing(tmp_path):
    assert ablate_adaptive.main(["--trials", "2", "--bits", "16", "--out", str(tmp_path)]) == []
    assert list(tmp_path.iterdir()) == []


@needs_c2
def test_cells_are_seeded_and_forgery_caught_in_both_modes():
    for mode in ablate_adaptive.MODES:
        a = ablate_adaptive.run_cell(ThreatType.EVE_FORGERY, 16, mode, trials=4, seed=1)
        assert a == ablate_adaptive.run_cell(ThreatType.EVE_FORGERY, 16, mode, trials=4, seed=1)
        assert a["rejected"] == 1.0


@needs_c2
def test_main_writes_csv(tmp_path):
    rows = ablate_adaptive.main(["--trials", "2", "--bits", "16", "--seed", "1", "--out", str(tmp_path)])
    assert len(rows) == len(ablate_adaptive.SCENARIOS) * len(ablate_adaptive.MODES)
    with open(tmp_path / "ablate_adaptive.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(rows)
