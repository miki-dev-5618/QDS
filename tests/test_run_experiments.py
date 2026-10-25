"""run_experiments.py: step registry, unavailable/skip handling, resume, manifest and PPT_NUMBERS.md."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run_experiments as rx  # noqa: E402

TOY = '''
import argparse, json, os
ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int)
ap.add_argument("--out")
ap.add_argument("--trials", type=int, default=7)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
json.dump({"seed": a.seed, "trials": a.trials}, open(os.path.join(a.out, "toy.json"), "w"))
with open(os.path.join(a.out, "calls.txt"), "a") as f:
    f.write("x")
raise SystemExit(2 if a.trials == 13 else 0)
'''


def _toy_headlines(out):
    d = json.load(open(os.path.join(out, "toy.json")))
    return [("toy trials", str(d["trials"]), os.path.join(out, "toy.json"))]


@pytest.fixture
def toy(tmp_path, monkeypatch):
    script = tmp_path / "toy.py"
    script.write_text(TOY)
    monkeypatch.setattr(rx, "STEPS", [
        rx.Step("toy", "DX", "Toy step", str(script),
                args=lambda a, out: ["--seed", str(a.seed), "--out", out] + rx._trials(a),
                quick_args=lambda out: ["--trials", "2"], headlines=_toy_headlines),
        rx.Step("missing", "DY", "Not written yet", str(tmp_path / "nope.py")),
        rx.Step("blocked", "DZ", "Dependency missing", str(script), available=lambda: (False, "needs C9")),
        rx.Step("hw", "-", "Hardware", str(script), hardware=True),
    ])
    return tmp_path / "results"


def _run(out, *flags):
    m = rx.main([*flags, "--skip-hardware", "--out", str(out)])
    return {s["name"]: s["status"] for s in m["steps"]}


def _toy(out):
    return json.loads((out / "toy" / "toy.json").read_text())


def test_statuses_manifest_and_ppt_numbers(toy):
    assert _run(toy, "--seed", "11") == {"toy": "ok", "missing": "unavailable", "blocked": "unavailable",
                                         "hw": "skipped"}
    m = json.loads((toy / "manifest.json").read_text())
    assert m["seed"] == 11 and m["git"]["commit"] and m["machine"]["cpu_count"] and "numpy" in m["packages"]
    assert _toy(toy) == {"seed": 11, "trials": 7}
    ppt = (toy / "PPT_NUMBERS.md").read_text()
    assert "| toy trials | 7 |" in ppt and "needs C9" in ppt and "nope.py does not exist yet" in ppt


def test_trials_override_and_quick(toy):
    _run(toy, "--trials", "5")
    assert _toy(toy)["trials"] == 5
    _run(toy, "--quick")
    assert _toy(toy)["trials"] == 2


def test_resume_skips_identical_settings_only(toy):
    _run(toy)
    assert _run(toy, "--resume")["toy"] == "cached"
    assert _run(toy, "--resume", "--seed", "3")["toy"] == "ok"
    assert (toy / "toy" / "calls.txt").read_text() == "xx"


def test_failed_step_is_reported_and_not_checkpointed(toy):
    assert _run(toy, "--trials", "13")["toy"] == "failed"
    assert not (toy / "toy" / ".done.json").exists()
