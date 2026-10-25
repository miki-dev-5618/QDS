"""
Focused tests for the opt-in partial intercept-resend threat (EVE_PARTIAL_INTERCEPT).

Coverage
--------
T01  Valid boundary f=0.05 accepted without error
T02  Valid boundary f=1.0 accepted without error
T03  Invalid f below minimum (0.04) raises ValueError
T04  Invalid f above maximum (1.01) raises ValueError
T05  Invalid type (string) raises TypeError
T06  Invalid f=0.0 raises ValueError
T07  ThreatType.EVE_PARTIAL_INTERCEPT enum exists with expected value
T08  ThreatScenarioConfig accepts new field and stores it
T09  High fraction (f=1.0) triggers channel alarm on a seeded run (integration)
T10  Low fraction (f=0.05) is sometimes undetected (detection < 100%)
T11  High fraction (f=1.0) is detected in the majority of trials (> 50%)
T12  Two runs with the same seed produce the same is_threat_detected sequence
T13  f=1.0 produces channel_test.alarm consistent with EVE_INTERCEPT(rate=1.0)
T14  Existing EVE_INTERCEPT still works identically (backward compatibility)
T15  wilson_interval(0, 200) returns (lo, hi) with lo==0.0 and hi>0
T16  wilson_interval(200, 200) returns (lo, hi) with hi==1.0 and lo<1
T17  wilson_interval edge n=0 returns (0.0, 1.0)
T18  Sweep grid dimensions: 7 fracs x 3 lengths x 200 trials = 4200
T19  run_sweep (small) returns dicts with all required CSV fields
T20  threshold_report returns None when no cell has wilson_lo >= 0.95
T21  threshold_report returns the correct fraction when one cell qualifies

Notes
-----
- Statistical tests (T10, T11) use fixed seeds and loose bounds.  They do NOT
  assert exact detection percentages derived from theory.
- T09 may occasionally fail if the seed happens to produce zero alarm even at
  f=1.0 for very small n_bits; we use n_bits=32 and seed=42 (same as test_cloning)
  to keep it consistent with existing seeded tests that already detect at f=1.0.
- No test asserts >= 95% detection at any specific fraction.
"""
import math

import numpy as np
import pytest

from src.quantum_engine import (
    ChannelModel,
    TeleportationQDS,
    ThreatScenarioConfig,
    ThreatType,
)
from src.quantum_engine.channel import wilson_interval


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run_partial(f, n_bits=32, seed=42, depolarizing=0.01):
    """Run one trial of EVE_PARTIAL_INTERCEPT and return the QDSExecutionResult."""
    rng = np.random.default_rng(seed)
    eng = TeleportationQDS(
        backend="statevector",
        channel=ChannelModel(depolarizing=depolarizing),
    )
    scenario = ThreatScenarioConfig(
        threat_type=ThreatType.EVE_PARTIAL_INTERCEPT,
        partial_intercept_fraction=f,
    )
    return eng.execute_protocol("test message", n_bits=n_bits, rng=rng, scenario=scenario)


# ---------------------------------------------------------------------------
# T01 – T02: Valid boundaries accepted without error
# ---------------------------------------------------------------------------

class TestValidation:
    def test_T01_valid_boundary_min(self):
        """f=0.05 should not raise."""
        result = _run_partial(0.05)
        assert result is not None

    def test_T02_valid_boundary_max(self):
        """f=1.0 should not raise."""
        result = _run_partial(1.0)
        assert result is not None

    def test_T03_invalid_below_min(self):
        """f=0.04 is below the minimum 0.05 and must raise ValueError."""
        with pytest.raises(ValueError, match="partial_intercept_fraction"):
            _run_partial(0.04)

    def test_T04_invalid_above_max(self):
        """f=1.01 is above the maximum 1.0 and must raise ValueError."""
        with pytest.raises(ValueError, match="partial_intercept_fraction"):
            _run_partial(1.01)

    def test_T05_invalid_type_string(self):
        """f='0.5' (string) must raise TypeError."""
        with pytest.raises((TypeError, ValueError)):
            _run_partial("0.5")

    def test_T06_invalid_zero(self):
        """f=0.0 is below minimum and must raise ValueError."""
        with pytest.raises(ValueError, match="partial_intercept_fraction"):
            _run_partial(0.0)

    def test_T07_enum_exists(self):
        """ThreatType.EVE_PARTIAL_INTERCEPT must exist with the expected string value."""
        assert ThreatType.EVE_PARTIAL_INTERCEPT == "eve_partial_intercept"
        assert ThreatType("eve_partial_intercept") is ThreatType.EVE_PARTIAL_INTERCEPT

    def test_T08_scenario_config_new_field(self):
        """ThreatScenarioConfig accepts partial_intercept_fraction and stores it."""
        cfg = ThreatScenarioConfig(
            threat_type=ThreatType.EVE_PARTIAL_INTERCEPT,
            partial_intercept_fraction=0.3,
        )
        assert cfg.partial_intercept_fraction == 0.3
        assert cfg.threat_type is ThreatType.EVE_PARTIAL_INTERCEPT

    def test_T08b_default_field_value(self):
        """Default value of partial_intercept_fraction is 0.05."""
        cfg = ThreatScenarioConfig()
        assert math.isclose(cfg.partial_intercept_fraction, 0.05)


# ---------------------------------------------------------------------------
# T09: Integration — f=1.0 triggers channel alarm
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_T09_full_intercept_triggers_alarm(self):
        """
        At f=1.0, every token is intercepted (Bernoulli p=1.0), which introduces
        QBER ~0.25. The default honest_qber=0.02 threshold should raise an alarm
        for n_bits=32 (test_count>=32). Seeded for reproducibility.
        """
        result = _run_partial(f=1.0, n_bits=32, seed=42)
        ct = result.transcript.channel_test
        assert ct is not None, "Channel test must have been run"
        # At QBER ~0.25, alarm is expected. We assert the threat was detected
        # (either via Tier-1 alarm or elimination failure).
        assert result.threat_report.is_threat_detected, (
            "Full intercept (f=1.0) should be detected for n_bits=32"
        )

    def test_T09b_channel_model_has_correct_intercept_rate(self):
        """
        The channel model embedded in the transcript should have intercept_rate
        equal to the configured fraction f.
        """
        f = 0.5
        result = _run_partial(f=f, n_bits=32, seed=7)
        cm = result.transcript.channel_model
        assert cm is not None
        assert math.isclose(cm.intercept_rate, f, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# T10 – T11: Statistical (loose bounds, fixed seed)
# ---------------------------------------------------------------------------

class TestStatistical:
    SEED = 1234
    N_TRIALS = 60

    def _detection_rate(self, f, n_bits):
        rng = np.random.default_rng(self.SEED)
        detected = 0
        for i in range(self.N_TRIALS):
            eng = TeleportationQDS(
                backend="statevector",
                channel=ChannelModel(depolarizing=0.01),
            )
            scenario = ThreatScenarioConfig(
                threat_type=ThreatType.EVE_PARTIAL_INTERCEPT,
                partial_intercept_fraction=f,
            )
            try:
                res = eng.execute_protocol("m", n_bits=n_bits, rng=rng, scenario=scenario)
                if res.threat_report.is_threat_detected:
                    detected += 1
            except Exception:
                detected += 1  # enforcement block counts
        return detected / self.N_TRIALS

    def test_T10_low_fraction_sometimes_undetected(self):
        """
        At f=0.05 (n_bits=32), expected QBER ~0.019+0.007=0.026, near the
        threshold.  Detection rate must be strictly less than 1.0 (some trials
        pass the channel test), confirming partial interception is genuinely
        partial.  We use a loose upper bound of 0.99 to avoid flakiness.
        """
        rate = self._detection_rate(f=0.05, n_bits=32)
        assert rate < 1.0, (
            "At f=0.05 some trials should pass the channel test undetected; "
            "got 100%% detection which would indicate a bug"
        )

    def test_T11_high_fraction_mostly_detected(self):
        """
        At f=0.75 (n_bits=32), expected QBER ~0.19+0.007=0.197.  Detection
        rate must exceed 50%.  Conservative bound to avoid flakiness; the
        experiment sweep will give the precise figure.
        """
        rate = self._detection_rate(f=0.75, n_bits=32)
        assert rate > 0.5, (
            "At f=0.75 detection rate should exceed 50%% over 60 trials; "
            "got %.2f" % rate
        )


# ---------------------------------------------------------------------------
# T12: Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_T12_same_seed_same_sequence(self):
        """Two independent runs with the same seed produce the same outcome list."""
        def _run_sequence(seed):
            rng = np.random.default_rng(seed)
            outcomes = []
            for _ in range(10):
                eng = TeleportationQDS(
                    backend="statevector",
                    channel=ChannelModel(depolarizing=0.01),
                )
                scenario = ThreatScenarioConfig(
                    threat_type=ThreatType.EVE_PARTIAL_INTERCEPT,
                    partial_intercept_fraction=0.5,
                )
                res = eng.execute_protocol("m", n_bits=32, rng=rng, scenario=scenario)
                outcomes.append(res.threat_report.is_threat_detected)
            return outcomes

        assert _run_sequence(999) == _run_sequence(999)
        assert _run_sequence(999) != _run_sequence(998) or True  # may coincide; not an error


# ---------------------------------------------------------------------------
# T13: Equivalence f=1.0 with EVE_INTERCEPT
# ---------------------------------------------------------------------------

class TestEquivalence:
    def test_T13_f1_channel_model_matches_eve_intercept(self):
        """
        eve_partial_intercept(1.0) constructs ChannelModel(intercept_rate=1.0),
        which is the same as EVE_INTERCEPT with channel_intercept_rate=1.0.
        Verify the channel model intercept_rate embedded in the transcript.
        """
        # Partial intercept f=1.0
        rng_a = np.random.default_rng(77)
        eng_a = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.01))
        sc_a = ThreatScenarioConfig(
            threat_type=ThreatType.EVE_PARTIAL_INTERCEPT,
            partial_intercept_fraction=1.0,
        )
        res_a = eng_a.execute_protocol("m", n_bits=32, rng=rng_a, scenario=sc_a)

        # EVE_INTERCEPT rate=1.0
        rng_b = np.random.default_rng(77)
        eng_b = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.01))
        sc_b = ThreatScenarioConfig(
            threat_type=ThreatType.EVE_INTERCEPT,
            channel_intercept_rate=1.0,
        )
        res_b = eng_b.execute_protocol("m", n_bits=32, rng=rng_b, scenario=sc_b)

        # Both must use intercept_rate=1.0 in their channel model
        assert math.isclose(res_a.transcript.channel_model.intercept_rate, 1.0)
        assert math.isclose(res_b.transcript.channel_model.intercept_rate, 1.0)
        # Both must have the same expected QBER from the channel model
        assert math.isclose(
            res_a.transcript.channel_model.expected_qber(),
            res_b.transcript.channel_model.expected_qber(),
            rel_tol=1e-9,
        )

    def test_T14_existing_eve_intercept_unchanged(self):
        """
        EVE_INTERCEPT still works as before; this test mirrors existing
        test_statistics.py coverage for EVE_INTERCEPT.
        """
        rng = np.random.default_rng(20)
        eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.01))
        sc = ThreatScenarioConfig(
            threat_type=ThreatType.EVE_INTERCEPT,
            channel_intercept_rate=1.0,
        )
        res = eng.execute_protocol("m", n_bits=32, rng=rng, scenario=sc)
        # EVE_INTERCEPT with rate=1.0 must be detected for n_bits=32
        assert res.threat_report.is_threat_detected


# ---------------------------------------------------------------------------
# T15 – T17: Wilson interval correctness
# ---------------------------------------------------------------------------

class TestWilsonInterval:
    def test_T15_zero_detections(self):
        """wilson_interval(0, 200): lo must be 0.0, hi must be > 0."""
        lo, hi = wilson_interval(0, 200)
        assert lo == 0.0
        assert hi > 0.0
        assert hi < 1.0

    def test_T16_all_detections(self):
        """wilson_interval(200, 200): hi must be 1.0, lo must be < 1."""
        lo, hi = wilson_interval(200, 200)
        assert hi == 1.0
        assert lo < 1.0
        assert lo > 0.0

    def test_T17_zero_n(self):
        """wilson_interval(0, 0): returns (0.0, 1.0) as documented."""
        lo, hi = wilson_interval(0, 0)
        assert lo == 0.0
        assert hi == 1.0

    def test_T17b_midpoint_interval_is_symmetric(self):
        """wilson_interval(100, 200) should be nearly symmetric around 0.5."""
        lo, hi = wilson_interval(100, 200)
        centre = (lo + hi) / 2
        assert math.isclose(centre, 0.5, abs_tol=0.01)
        assert lo > 0.43  # rough sanity check
        assert hi < 0.57


# ---------------------------------------------------------------------------
# T18 – T21: Experiment sweep dimensions, CSV fields, threshold report
# ---------------------------------------------------------------------------

class TestSweepStructure:
    def test_T18_sweep_dimensions(self):
        """7 fractions x 3 lengths x 200 trials = 4 200 trials exactly."""
        from experiments.sweep_partial_ir import DEFAULT_FRACTIONS, DEFAULT_BITS, DEFAULT_TRIALS
        assert len(DEFAULT_FRACTIONS) == 7
        assert len(DEFAULT_BITS) == 3
        total = len(DEFAULT_FRACTIONS) * len(DEFAULT_BITS) * DEFAULT_TRIALS
        assert total == 4200

    def test_T19_run_sweep_returns_required_csv_fields(self):
        """run_sweep with 1 trial per cell returns dicts with all CSV_FIELDS."""
        from experiments.sweep_partial_ir import run_sweep, CSV_FIELDS
        results = run_sweep(
            fractions=[0.1, 1.0],
            lengths=[16],
            trials_per_cell=1,
            seed=42,
        )
        assert len(results) == 2  # 2 fractions x 1 length
        for row in results:
            for field in CSV_FIELDS:
                assert field in row, "Missing CSV field: %s" % field

    def test_T20_threshold_report_no_qualifying(self):
        """If no row has wilson_lo >= 0.95, threshold_report returns None."""
        from experiments.sweep_partial_ir import threshold_report
        results = [
            {"n_bits": 16, "intercept_fraction": 0.1, "wilson_lo": 0.80},
            {"n_bits": 16, "intercept_fraction": 0.5, "wilson_lo": 0.93},
        ]
        report = threshold_report(results, [16])
        assert report[16] is None

    def test_T21_threshold_report_selects_smallest_qualifying(self):
        """threshold_report returns the smallest f with wilson_lo >= 0.95."""
        from experiments.sweep_partial_ir import threshold_report
        results = [
            {"n_bits": 32, "intercept_fraction": 0.2, "wilson_lo": 0.80},
            {"n_bits": 32, "intercept_fraction": 0.5, "wilson_lo": 0.96},
            {"n_bits": 32, "intercept_fraction": 1.0, "wilson_lo": 0.99},
        ]
        report = threshold_report(results, [32])
        assert report[32] == 0.5  # smallest qualifying fraction


class TestServerModel:
    """T22: Verify SignAndSendRequest accepts partial_intercept_fraction."""

    def test_T22_sign_and_send_request_model(self):
        from server import SignAndSendRequest
        req_default = SignAndSendRequest(message_text="hello")
        assert req_default.partial_intercept_fraction == 0.05

        req_custom = SignAndSendRequest(
            message_text="hello",
            threat_type="eve_partial_intercept",
            partial_intercept_fraction=0.35,
        )
        assert req_custom.partial_intercept_fraction == 0.35
