"""
Seeded repeated trials: rates are statistical, so the tests assert loose,
reproducible bounds rather than deterministic outcomes.
"""
import numpy as np
import pytest

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatType

TRIALS = 40


def _rates(threat, n_bits, seed, channel=ChannelModel()):
    rng = np.random.default_rng(seed)
    detected = accepted_both = 0
    for _ in range(TRIALS):
        eng = TeleportationQDS(backend="statevector", channel=channel)
        while threat == ThreatType.REPLAY and eng.last_accepted_package is None:
            eng.guard.reset()
            eng.execute_protocol("m", n_bits, rng=rng)
        eng.guard.reset()
        r = eng.execute_protocol("m", n_bits, rng=rng, scenario=ThreatScenarioConfig(threat_type=threat))
        detected += r.threat_report.is_threat_detected
        accepted_both += all(v.accepted for v in r.transcript.results)
    return detected / TRIALS, accepted_both / TRIALS


def test_honest_noisy_channel_mostly_accepted():
    detected, accepted = _rates(ThreatType.AUTHENTIC, 32, seed=10)
    assert accepted >= 0.85 and detected <= 0.15


@pytest.mark.parametrize("threat,min_rate", [
    (ThreatType.EVE_FORGERY, 0.95),
    (ThreatType.EVE_INTERCEPT, 0.90),
    (ThreatType.REPUDIATION, 0.80),
    (ThreatType.DISHONEST_BOB, 0.95),
    (ThreatType.MESSAGE_TAMPERING, 1.0),
    (ThreatType.REPLAY, 1.0),
    (ThreatType.IMPERSONATION, 1.0),
])
def test_attacks_detected_at_expected_rates(threat, min_rate):
    detected, _ = _rates(threat, 32, seed=20)
    assert detected >= min_rate


def test_small_signatures_can_miss_intercept():
    """With only 16 test tokens the channel test has ~80% power, so misses are expected sometimes."""
    rng = np.random.default_rng(99)
    alarms = 0
    for _ in range(60):
        eng = TeleportationQDS(backend="statevector")
        r = eng.execute_protocol("m", 16, rng=rng,
                                 scenario=ThreatScenarioConfig(threat_type=ThreatType.EVE_INTERCEPT))
        alarms += bool(r.transcript.channel_test.alarm)
    assert 0.5 <= alarms / 60 < 1.0
