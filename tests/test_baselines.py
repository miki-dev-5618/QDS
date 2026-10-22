"""experiments/baselines.py: fixed-QBER-cutoff baseline, HEDWIG without circuit breaker, full HEDWIG."""
import csv
import os
import sys
from types import SimpleNamespace

import numpy as np

from src.quantum_engine import ThreatType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
import baselines  # noqa: E402


def _tx(errors, tests, results=()):
    return SimpleNamespace(channel_test=SimpleNamespace(error_count=errors, test_count=tests), results=list(results))


def _res(accepted=True, binding=True, elim=True):
    return SimpleNamespace(mode="direct", accepted=accepted, binding_pass=binding, elimination_pass=elim)


def test_cutoff_rule():
    assert baselines.cutoff_outcome(_tx(4, 32, [_res(), _res()])) == (False, "channel")  # 12.5% > 11%
    assert baselines.cutoff_outcome(_tx(3, 32, [_res(), _res()])) == (True, "accepted")  # 9.4%
    assert baselines.cutoff_outcome(_tx(0, 32, [_res(False, binding=False), _res()])) == (False, "forgery")
    assert baselines.cutoff_outcome(_tx(0, 32, [_res(False, elim=False), _res()])) == (False, "signature")


def test_cutoff_engine_never_alarms_or_aborts_early():
    eng = baselines.make_engine("qber_cutoff", 0.01)
    r = eng.execute_protocol("m", 16, rng=np.random.default_rng(0),
                             scenario=baselines.ThreatScenarioConfig(threat_type=ThreatType.EVE_INTERCEPT))
    ct = r.transcript.channel_test
    assert not ct.alarm and not ct.early_abort
    assert r.transcript.session.tokens_sent == r.transcript.session.tokens_planned


def test_no_breaker_guard_keeps_link_open():
    eng = baselines.make_engine("hedwig_no_cb", 0.01)
    rng = np.random.default_rng(0)
    out = baselines.transmit(eng, "hedwig_no_cb", 16, rng, ThreatType.EVE_FORGERY, None)
    assert out is not None and out[0] is False
    assert eng.guard.state("alice->verifiers") == "open"
    assert baselines.transmit(eng, "hedwig_no_cb", 16, rng, ThreatType.AUTHENTIC, None) is not None


def test_full_hedwig_refuses_after_forgery():
    seq = baselines.sequence("hedwig", 32, "forgery_injection", 0, 6, 2, 1, 0.01, 60.0)
    assert seq[1][0] is False and seq[1][1][0] is False  # the forged package is rejected
    assert all(o is None for _, o in seq[2:])            # strong evidence: quarantined, later traffic refused


def test_per_transmission_is_seeded_and_paired():
    a = baselines.per_transmission("hedwig", 16, 1, 3, 5, 0.01)
    b = baselines.per_transmission("hedwig", 16, 1, 3, 5, 0.01)
    assert a == b and all(not acc for acc, _, _ in a)


def test_winners_reports_ties():
    rows = [{"system": s, "direction": "higher", "value": v, "lo": lo, "hi": hi}
            for s, v, lo, hi in (("qber_cutoff", 0.5, 0.4, 0.6), ("hedwig_no_cb", 0.9, 0.85, 0.95),
                                 ("hedwig", 0.88, 0.8, 0.93))]
    assert baselines.winners(rows) == ["hedwig_no_cb", "hedwig"]


def test_main_writes_outputs(tmp_path):
    rows = baselines.main(["--bits", "16", "--trials", "3", "--seq-runs", "1", "--seq-length", "6",
                           "--attack-at", "2", "--seed", "1", "--out", str(tmp_path)])
    systems = {r["system"] for r in rows}
    assert systems == set(baselines.SYSTEMS)
    with open(tmp_path / "baselines.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(rows)
    md = (tmp_path / "baselines.md").read_text()
    assert "(a) fixed 11% QBER cutoff" in md and "| best |" in md
