"""D3/D4: EARLY_ABORT and DETECTION_TIERS toggles (opt-in, default unchanged) and their ablation scripts."""
import csv
import os
import sys

import numpy as np
import pytest

from src.quantum_engine import (
    ChannelModel, SecurityParameters, TeleportationQDS, ThreatClassification, ThreatScenarioConfig, ThreatType,
)

EXPERIMENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments")
if EXPERIMENTS not in sys.path:
    sys.path.insert(0, EXPERIMENTS)

import ablate_early_abort  # noqa: E402
import ablate_tiers  # noqa: E402


def _run(threat, params, seed, n_bits=32):
    eng = TeleportationQDS(params=params, backend="statevector", channel=ChannelModel())
    return eng.execute_protocol("m", n_bits, rng=np.random.default_rng(seed),
                                scenario=ThreatScenarioConfig(threat_type=threat))


# ------------------------------------------------------------------ toggles
def test_defaults_keep_existing_behaviour(monkeypatch):
    monkeypatch.delenv("EARLY_ABORT", raising=False)
    monkeypatch.delenv("DETECTION_TIERS", raising=False)
    p = SecurityParameters()
    assert p.early_abort is True and p.detection_tiers == 2


def test_env_vars_select_the_ablation(monkeypatch):
    monkeypatch.setenv("EARLY_ABORT", "off")
    monkeypatch.setenv("DETECTION_TIERS", "1")
    p = SecurityParameters()
    assert p.early_abort is False and p.detection_tiers == 1
    assert p.to_dict()["early_abort"] is False and p.to_dict()["detection_tiers"] == 1


@pytest.mark.parametrize("name,value", [("EARLY_ABORT", "maybe"), ("DETECTION_TIERS", "3")])
def test_bad_env_values_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        SecurityParameters()


def test_bad_tier_parameter_is_rejected():
    with pytest.raises(ValueError):
        SecurityParameters(detection_tiers=0)


def test_early_abort_off_always_sends_the_whole_stream():
    on, off = SecurityParameters(early_abort=True), SecurityParameters(early_abort=False)
    aborted_on = 0
    for seed in range(10):
        ct_on = _run(ThreatType.EVE_INTERCEPT, on, seed, 64).transcript.channel_test
        r_off = _run(ThreatType.EVE_INTERCEPT, off, seed, 64)
        ct_off = r_off.transcript.channel_test
        aborted_on += ct_on.early_abort
        assert not ct_off.early_abort and ct_off.tokens_sent == ct_off.tokens_planned
        assert ct_off.alarm and r_off.threat_report.is_threat_detected  # still detected, just later
    assert aborted_on > 0  # the default really does abort intercepted streams early


def test_tier1_only_blames_the_channel_for_repudiation():
    seen = set()
    for seed in range(10):
        r1 = _run(ThreatType.REPUDIATION, SecurityParameters(detection_tiers=1), seed, 64)
        assert r1.threat_report.classification != ThreatClassification.REPUDIATION_ATTEMPT
        assert r1.threat_report.tier2["applicable"] is False
        seen.add(r1.threat_report.classification)
    assert seen == {ThreatClassification.EAVESDROPPING_TAMPERING}
    r2 = _run(ThreatType.REPUDIATION, SecurityParameters(detection_tiers=2), 0, 64)
    assert r2.threat_report.classification == ThreatClassification.REPUDIATION_ATTEMPT


def test_tier_setting_does_not_change_honest_or_forgery_verdicts():
    for threat in (ThreatType.AUTHENTIC, ThreatType.EVE_FORGERY):
        for seed in range(5):
            a = _run(threat, SecurityParameters(detection_tiers=1), seed)
            b = _run(threat, SecurityParameters(detection_tiers=2), seed)
            assert a.threat_report.classification == b.threat_report.classification


# ------------------------------------------------------------------ scripts
def _csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_early_abort_ablation_outputs(tmp_path):
    out = str(tmp_path)
    ablate_early_abort.main(["--trials", "5", "--bits", "32", "--workers", "1", "--out", out])
    rows = _csv(os.path.join(out, "ablate_early_abort.csv"))
    assert {(r["early_abort"], r["scenario"]) for r in rows} == {
        (s, sc) for s in ("on", "off") for sc in ablate_early_abort.SCENARIOS}
    honest = [r for r in rows if r["scenario"] == "authentic"]
    assert all(r["false_abort_rate"] != "" and r["false_abort_ci_high"] != "" for r in honest)
    for r in rows:
        if r["early_abort"] == "off":
            assert float(r["bandwidth_saved"]) == 0.0 and float(r["early_abort_rate"]) == 0.0
    for ext in ("png", "svg"):
        assert os.path.getsize(os.path.join(out, f"ablate_early_abort.{ext}")) > 0


def test_tier_ablation_outputs(tmp_path):
    out = str(tmp_path)
    ablate_tiers.main(["--trials", "5", "--bits", "64", "--workers", "1", "--out", out])
    rows = {(int(r["tiers"]), r["scenario"]): r for r in _csv(os.path.join(out, "ablate_tiers.csv"))}
    assert float(rows[(1, "repudiation")]["accuracy"]) == 0.0
    assert float(rows[(1, "repudiation")]["wrong_blame_rate"]) > 0.0
    for r in rows.values():
        assert 0.0 <= float(r["accuracy_ci_low"]) <= float(r["accuracy"]) <= float(r["accuracy_ci_high"]) <= 1.0
    confusion = _csv(os.path.join(out, "ablate_tiers_confusion.csv"))
    assert len(confusion) == 2 * len(ablate_tiers.SCENARIOS)
    assert all(sum(int(c[lab]) for lab in ablate_tiers.LABELS) == 5 for c in confusion)
    for ext in ("png", "svg"):
        assert os.path.getsize(os.path.join(out, f"ablate_tiers.{ext}")) > 0


def test_ablation_scripts_are_reproducible(tmp_path):
    a, b = str(tmp_path / "a"), str(tmp_path / "b")
    for out in (a, b):
        ablate_tiers.main(["--trials", "3", "--bits", "16", "--workers", "1", "--out", out])
    with open(os.path.join(a, "ablate_tiers.csv"), encoding="utf-8") as fa, \
            open(os.path.join(b, "ablate_tiers.csv"), encoding="utf-8") as fb:
        assert fa.read() == fb.read()
