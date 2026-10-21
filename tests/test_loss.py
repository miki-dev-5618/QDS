"""
Tests for heralded photon loss (erasure channel model), surviving token threshold recalculation,
INSUFFICIENT_TOKENS abort handling, and the eve_loss_exploit threat scenario.
"""
import os
import numpy as np
import pytest

from src.quantum_engine import (
    ChannelModel,
    TeleportationQDS,
    SecurityParameters,
    ThreatSuite,
    ThreatType,
    ThreatScenarioConfig,
    ThreatClassification,
    make_lossy_channel,
)
from src.quantum_engine.enforcement import WATCH, QUARANTINED, OPEN


def test_loss_zero_equals_old_behaviour():
    """Verify that eta_loss=0 matches standard baseline behaviour."""
    seed = 42
    rng = np.random.default_rng(seed)
    channel = make_lossy_channel(eta_loss=0.0, depolarizing=0.01)

    eng = TeleportationQDS(backend="statevector", channel=channel)
    transcript = eng.transmit("alice", "baseline message", n_bits=32, rng=rng)
    exec_res = eng.assess(transcript)

    assert transcript.channel_test is not None
    assert transcript.channel_test.tokens_lost == 0
    assert transcript.channel_test.tokens_received == transcript.channel_test.tokens_planned
    assert not transcript.channel_test.alarm
    # Both verifiers accept
    for res in transcript.results:
        assert res.accepted
        assert not res.insufficient_tokens
        assert res.n_checked > 0
    assert exec_res.response.verdict == "accept"
    assert exec_res.response.response_action == "none"


def test_moderate_loss_still_accepts_honest_runs():
    """Verify that moderate loss (e.g., eta_loss=0.15) excludes lost tokens from mismatches and still accepts."""
    seed = 101
    rng = np.random.default_rng(seed)
    channel = make_lossy_channel(eta_loss=0.15, depolarizing=0.01)

    eng = TeleportationQDS(backend="statevector", channel=channel)
    transcript = eng.transmit("alice", "moderate loss message", n_bits=32, rng=rng)
    exec_res = eng.assess(transcript)

    ct = transcript.channel_test
    assert ct.tokens_lost > 0
    assert ct.tokens_received < ct.tokens_planned
    # Ratio should still be above 60% default min_surviving_ratio
    assert ct.tokens_received >= 0.6 * ct.tokens_planned

    # Mismatches should be small and bounds computed with n_surviving
    for res in transcript.results:
        assert res.accepted
        assert not res.insufficient_tokens
        assert res.n_checked <= 32  # some copies lost, so n_checked <= 32
        assert res.acceptance_limit == eng.params.acceptance_limit(res.n_checked, forwarded=(res.mode == "forwarded"))
    assert exec_res.response.verdict == "accept"


def test_extreme_loss_gives_insufficient_tokens_and_watch_not_quarantine():
    """Verify that high loss (e.g. eta_loss=0.6) triggers INSUFFICIENT_TOKENS and sets link to WATCH, never QUARANTINE."""
    seed = 2026
    rng = np.random.default_rng(seed)
    # High loss where < 60% tokens survive
    channel = make_lossy_channel(eta_loss=0.6, depolarizing=0.01)

    eng = TeleportationQDS(backend="statevector", channel=channel)
    transcript = eng.transmit("alice", "high loss message", n_bits=32, rng=rng)
    exec_res = eng.assess(transcript)

    # Session aborted at distribution or verifier
    assert transcript.session.insufficient_tokens or transcript.session.aborted
    assert exec_res.threat_report.classification == ThreatClassification.INSUFFICIENT_TOKENS
    assert exec_res.response.verdict == "reject"
    assert exec_res.response.response_action == "watch"
    assert exec_res.enforcement["channel_state"]["alice->verifiers"]["state"] == WATCH
    assert exec_res.enforcement["channel_state"]["alice->verifiers"]["state"] != QUARANTINED


def test_eve_loss_exploit_threat_scenario():
    """Verify eve_loss_exploit threat: Eve blocks poorly measured tokens and attempts forgery."""
    seed = 999
    rng = np.random.default_rng(seed)
    channel = make_lossy_channel(eta_loss=0.2, depolarizing=0.01)

    eng = TeleportationQDS(backend="statevector", channel=channel)
    scenario = ThreatScenarioConfig(
        threat_type=ThreatType.EVE_LOSS_EXPLOIT,
        channel_intercept_rate=1.0,
        loss_exploit_block_rate=0.3,
    )
    transcript = ThreatSuite.run(eng, scenario, "exploited payload", n_bits=32, sender="alice", rng=rng)
    exec_res = eng.assess(transcript)

    # Either detected as INSUFFICIENT_TOKENS (if loss was high) or caught by EXTERNAL_FORGERY / EAVESDROPPING
    report = exec_res.threat_report
    assert report.is_threat_detected or report.classification == ThreatClassification.INSUFFICIENT_TOKENS
    # Verifiers should reject counterfeit signature
    for res in transcript.results:
        assert not res.accepted


def test_loss_experiment_table():
    """Run sweep experiment: eta_loss vs honest accept rate vs eve_forgery detection rate."""
    seed = 1234
    rng = np.random.default_rng(seed)
    eta_levels = [0.0, 0.1, 0.25, 0.55]
    n_trials = 10
    n_bits = 24

    results_table = []
    for eta in eta_levels:
        honest_accepts = 0
        eve_detected = 0
        for _ in range(n_trials):
            # Honest run
            ch = make_lossy_channel(eta_loss=eta, depolarizing=0.01)
            eng = TeleportationQDS(backend="statevector", channel=ch)
            tr = eng.transmit("alice", "test", n_bits=n_bits, rng=rng)
            exec_res = eng.assess(tr)
            if exec_res.response.verdict == "accept":
                honest_accepts += 1

            # Eve forgery run
            sc = ThreatScenarioConfig(threat_type=ThreatType.EVE_FORGERY)
            tr_eve = ThreatSuite.run(eng, sc, "test", n_bits=n_bits, sender="alice", rng=rng, channel=ch)
            exec_eve = eng.assess(tr_eve)
            if exec_eve.threat_report.is_threat_detected:
                eve_detected += 1

        results_table.append({
            "eta_loss": eta,
            "honest_accept_rate": honest_accepts / n_trials,
            "eve_detection_rate": eve_detected / n_trials,
        })

    # Print experiment table
    print("\n--- Photon Loss Erasure Experiment Table ---")
    print(f"{'eta_loss':<10} | {'Honest Accept Rate':<20} | {'Eve Detection Rate':<20}")
    print("-" * 56)
    for row in results_table:
        print(f"{row['eta_loss']:<10.2f} | {row['honest_accept_rate']:<20.2f} | {row['eve_detection_rate']:<20.2f}")

    # Baseline eta=0 must have 100% honest accept and 100% eve detection
    assert results_table[0]["honest_accept_rate"] == 1.0
    assert results_table[0]["eve_detection_rate"] == 1.0
    # Extreme eta=0.55 should abort honest runs (honest_accept_rate == 0.0) due to INSUFFICIENT_TOKENS
    assert results_table[-1]["honest_accept_rate"] == 0.0
