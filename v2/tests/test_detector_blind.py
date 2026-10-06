"""Issue 1: detection is computed from observations only, never from the scenario label."""
import ast
import inspect
import pathlib

import numpy as np
import pytest

from src.quantum_engine import (
    ChannelModel, QDSDetectionEngine, TeleportationQDS, ThreatClassification, ThreatScenarioConfig, ThreatType,
)

ENGINE_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "quantum_engine"


def test_detector_has_no_scenario_parameter():
    params = inspect.signature(QDSDetectionEngine.classify).parameters
    assert set(params) == {"self", "observations", "channel_test"}


@pytest.mark.parametrize("module", ["detection.py", "verifier.py", "security.py", "channel.py", "binding.py",
                                    "discriminator.py", "policy.py", "enforcement.py"])
def test_decision_modules_do_not_reference_attack_labels(module):
    tree = ast.parse((ENGINE_DIR / module).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
            {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    assert "threats" not in imported
    assert not {"ThreatType", "ThreatScenarioConfig", "scenario", "threat_type"} & names


def _run(threat, seed=7):
    eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0))
    rng = np.random.default_rng(seed)
    if threat == ThreatType.REPLAY:
        eng.execute_protocol("m", 32, rng=rng)
    return eng.execute_protocol("m", 32, scenario=ThreatScenarioConfig(threat_type=threat), rng=rng)


@pytest.mark.parametrize("threat", list(ThreatType))
def test_same_observations_give_same_verdict(threat):
    result = _run(threat)
    t = result.transcript
    fresh = QDSDetectionEngine().classify(t.results, t.channel_test)
    assert fresh.classification == result.threat_report.classification
    assert fresh.verdict == result.threat_report.verdict


def test_label_cannot_change_verdict():
    """Feed the observations of an honest run to the detector while the menu says 'eve_forgery'."""
    honest = _run(ThreatType.AUTHENTIC)
    t = honest.transcript
    report = QDSDetectionEngine().classify(t.results, t.channel_test)
    assert not report.is_threat_detected
    assert honest.ground_truth["injected_scenario"] == "authentic"


@pytest.mark.parametrize("seed", range(10))
def test_honest_noiseless_runs_are_accepted(seed):
    r = _run(ThreatType.AUTHENTIC, seed)
    assert r.threat_report.classification == ThreatClassification.BENIGN_AUTHENTIC
    assert all(v.accepted for v in r.transcript.results)


def test_message_tampering_is_found_by_digest_not_label():
    r = _run(ThreatType.MESSAGE_TAMPERING)
    assert r.threat_report.classification == ThreatClassification.MESSAGE_INTEGRITY_VIOLATION
    for v in r.transcript.results:
        assert v.elimination_pass and not v.digest_matches and not v.accepted


def test_impersonation_is_found_by_missing_distribution_record():
    r = _run(ThreatType.IMPERSONATION)
    assert r.threat_report.classification == ThreatClassification.IMPERSONATION_ATTACK
    assert all(not v.record_found for v in r.transcript.results)
