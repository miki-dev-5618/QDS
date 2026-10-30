"""D1: experiment harness - seeded per-cell RNG, resumable JSONL, Wilson summary."""
import csv
import os
import sys

import pytest

EXPERIMENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments")
if EXPERIMENTS not in sys.path:
    sys.path.insert(0, EXPERIMENTS)

import harness  # noqa: E402

SMALL = ["--trials", "5", "--bits", "16", "--profiles", "depolarizing",
         "--only", "authentic", "eve_forgery", "replay", "--workers", "1"]


def _raw(out):
    return harness.load_cells(os.path.join(out, "raw.jsonl"))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_same_seed_gives_identical_output(tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    harness.main(SMALL + ["--out", a])
    harness.main(SMALL + ["--out", b])
    assert _raw(a) == _raw(b)
    assert _read(os.path.join(a, "summary.csv")) == _read(os.path.join(b, "summary.csv"))


def test_different_seed_changes_cell_seeds():
    assert harness.cell_seed(1, "authentic", 16, "depolarizing") != harness.cell_seed(2, "authentic", 16, "depolarizing")
    assert harness.cell_seed(1, "authentic", 16, "depolarizing") != harness.cell_seed(1, "authentic", 32, "depolarizing")


def test_every_scenario_has_an_expected_verdict():
    # a new ThreatType without an EXPECTED entry would crash summarise_cell after the whole cell has run
    assert set(harness.SCENARIOS) <= set(harness.EXPECTED)


def test_cell_results_do_not_depend_on_grid_order(tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    harness.main(SMALL + ["--out", a])
    harness.main(["--trials", "5", "--bits", "16", "--profiles", "depolarizing",
                  "--only", "eve_forgery", "--workers", "1", "--out", b])
    key = harness.cell_key("eve_forgery", 16, "depolarizing", 2026, 5)
    assert _raw(a)[key]["trials"] == _raw(b)[key]["trials"]


def test_restart_skips_finished_cells_and_recovers_from_a_cut_line(tmp_path, capsys):
    out = str(tmp_path / "r")
    harness.main(SMALL + ["--out", out])
    raw_path = os.path.join(out, "raw.jsonl")
    with open(raw_path, encoding="utf-8") as f:
        lines = f.readlines()
    # Simulate a kill mid-write: the last cell is only half written.
    with open(raw_path, "w", encoding="utf-8") as f:
        f.writelines(lines[:-1] + [lines[-1][: len(lines[-1]) // 2]])
    capsys.readouterr()
    harness.main(SMALL + ["--out", out])
    assert "2 already in" in capsys.readouterr().out and len(_raw(out)) == 3
    before = _read(raw_path)
    harness.main(SMALL + ["--out", out])
    assert _read(raw_path) == before          # nothing rerun


def test_parallel_workers_match_single_worker(tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    harness.main(SMALL + ["--out", a])
    harness.main(SMALL[:-2] + ["--workers", "2", "--out", b])
    assert _raw(a) == _raw(b)


def test_summary_has_rates_and_wilson_intervals(tmp_path):
    out = str(tmp_path / "s")
    harness.main(SMALL + ["--out", out])
    with open(os.path.join(out, "summary.csv"), encoding="utf-8") as f:
        rows = {r["scenario"]: r for r in csv.DictReader(f)}
    assert set(rows) == {"authentic", "eve_forgery", "replay"}
    honest, forged = rows["authentic"], rows["eve_forgery"]
    assert honest["detection_rate"] == "" and honest["false_reject_rate"] != ""
    assert forged["false_reject_rate"] == ""
    lo, rate, hi = float(forged["detection_ci_low"]), float(forged["detection_rate"]), float(forged["detection_ci_high"])
    assert 0.0 <= lo <= rate <= hi <= 1.0 and hi - lo > 0  # 5 trials -> a wide interval
    assert int(forged["trials"]) == 5


def test_dry_run_writes_nothing(tmp_path, capsys):
    out = str(tmp_path / "d")
    harness.main(SMALL + ["--dry-run", "--out", out])
    assert "Estimated runtime" in capsys.readouterr().out
    assert not os.path.exists(out)


def test_quick_flag_uses_100_trials():
    assert harness.parse_args(["--quick"]).trials == 100
    assert harness.parse_args([]).trials == 1000
    assert harness.parse_args(["--quick", "--trials", "7"]).trials == 7


@pytest.mark.parametrize("profile", harness.PROFILES)
def test_every_noise_profile_runs(profile, tmp_path):
    out = str(tmp_path / profile)
    harness.main(["--trials", "2", "--bits", "16", "--profiles", profile, "--only", "authentic",
                  "--workers", "1", "--out", out])
    (cell,) = _raw(out).values()
    assert cell["noise_profile"] == profile and len(cell["trials"]) == 2
