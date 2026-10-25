"""ESCALATION toggle (fisher | fisher_only | counter) and experiments/ablate_escalation.py."""
import csv
import os
import sys

import pytest

from src.quantum_engine import ChannelGuard, LINK_SIGNER, ResponseDecision, ResponsePolicy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
import ablate_escalation  # noqa: E402


def weak(p):
    return ResponseDecision("reject", "watch", "weak", p, "weak test alert")


def strikes_to_quarantine(policy, clock, p_values):
    guard = ChannelGuard(policy, clock=clock)
    for i, p in enumerate(p_values, start=1):
        guard.apply(LINK_SIGNER, weak(p), f"TX-{i}")
        if guard.state(LINK_SIGNER) == "quarantined":
            return i
    return None


# ------------------------------------------------------------ policy toggle
def test_default_is_fisher_and_policy_dict_unchanged(monkeypatch):
    monkeypatch.delenv("ESCALATION", raising=False)
    p = ResponsePolicy()
    assert p.escalation == "fisher"
    assert "escalation" not in p.to_dict()
    assert set(p.to_dict()) == {"version", "strong_alpha", "watch_window_s", "watch_strikes", "escalate_alpha"}


def test_env_var_selects_rule(monkeypatch):
    monkeypatch.setenv("ESCALATION", "Counter")
    p = ResponsePolicy()
    assert p.escalation == "counter"
    assert p.to_dict()["escalation"] == "counter"


def test_explicit_rule_overrides_env(monkeypatch):
    monkeypatch.setenv("ESCALATION", "counter")
    assert ResponsePolicy(escalation="fisher_only").escalation == "fisher_only"


def test_unknown_rule_rejected():
    with pytest.raises(ValueError):
        ResponsePolicy(escalation="vote")


def test_borderline_alerts_counter_quarantines_fisher_only_does_not(clock):
    borderline = [0.15] * 6  # honest-noise-like alerts: Fisher of three is ~0.07 > 0.01
    assert strikes_to_quarantine(ResponsePolicy(escalation="counter"), clock, borderline) == 3
    assert strikes_to_quarantine(ResponsePolicy(escalation="fisher"), clock, borderline) == 3  # strike backstop
    assert strikes_to_quarantine(ResponsePolicy(escalation="fisher_only"), clock, borderline) is None


def test_strong_evidence_fisher_escalates_before_counter(clock):
    moderate = [0.02, 0.02, 0.02]  # Fisher of two is ~0.004 <= 0.01
    assert strikes_to_quarantine(ResponsePolicy(escalation="fisher_only"), clock, moderate) == 2
    assert strikes_to_quarantine(ResponsePolicy(escalation="fisher"), clock, moderate) == 2
    assert strikes_to_quarantine(ResponsePolicy(escalation="counter"), clock, moderate) == 3


def test_counter_k_is_watch_strikes(clock):
    assert strikes_to_quarantine(ResponsePolicy(escalation="counter", watch_strikes=5), clock, [0.5] * 6) == 5


def test_window_expiry_resets_counter(clock):
    guard = ChannelGuard(ResponsePolicy(escalation="counter"), clock=clock)
    guard.apply(LINK_SIGNER, weak(0.5), "TX-1")
    guard.apply(LINK_SIGNER, weak(0.5), "TX-2")
    clock.advance(901)
    guard.apply(LINK_SIGNER, weak(0.5), "TX-3")
    assert guard.state(LINK_SIGNER) == "watch"


# ------------------------------------------------------------ ablation script
def test_run_sequence_is_seeded():
    task = ("counter", 16, 30, None, [1, 16, 0, 0], 3, 0.01, 60.0)
    assert ablate_escalation.run_sequence(task) == ablate_escalation.run_sequence(task)


def test_full_intercept_quarantines_fast_under_every_rule():
    for rule in ablate_escalation.RULES:
        t, _ = ablate_escalation.run_sequence((rule, 16, 20, 1.0, [2, 16, 1, 0], 3, 0.01, 60.0))
        assert t is not None and t <= 3


def test_summarise_counts_censored_at_cap():
    row = ablate_escalation.summarise("attack", 16, "intercept f=0.2", "counter", 10,
                                      [(2, 1), (None, 4), (4, 2)], seed=1)
    assert row["censored"] == 1 and row["quarantined"] == 2
    assert row["mean_tx"] == pytest.approx((2 + 10 + 4) / 3, abs=1e-3)
    assert row["median_tx"] == 4
    assert row["mean_lo"] <= row["mean_tx"] <= row["mean_hi"]


def test_main_writes_outputs(tmp_path):
    rows = ablate_escalation.main(["--bits", "16", "--runs", "2", "--transmissions", "10", "--attack-runs", "2",
                                   "--cap", "10", "--workers", "1", "--seed", "1", "--out", str(tmp_path)])
    assert len(rows) == len(ablate_escalation.RULES) * 3  # honest + two intercept rates
    with open(tmp_path / "ablate_escalation.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(rows)
    md = (tmp_path / "ablate_escalation.md").read_text()
    assert "false quarantine" in md and "transmissions until QUARANTINE" in md
