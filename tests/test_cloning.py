"""
Tests for opt-in Eve cloning attack and 1->2 quantum cloner fidelities.

Verifies:
1. Universal symmetric 1->2 cloner fidelity against theory (5/6 ~ 0.8333).
2. Phase-covariant BB84 cloner fidelity against theory (1/2*(1 + 1/sqrt(2)) ~ 0.8536).
3. Both clone 1 (Eve) and clone 2 (receiver) are symmetric (equal fidelities).
4. Full protocol execution under opt-in ThreatType.EVE_CLONING:
   - Channel test QBER detection
   - Verifier elimination mismatches
   - Eve signature forgery failure
"""
import math
import numpy as np
import pytest

from src.quantum_engine.cloning import (
    build_cloning_circuit,
    measure_cloner_fidelity,
    simulate_eve_cloning_step,
    UNIVERSAL_FIDELITY,
    UNIVERSAL_ERROR,
    PHASE_COVARIANT_FIDELITY,
    PHASE_COVARIANT_ERROR,
)
from src.quantum_engine import (
    TeleportationQDS,
    ThreatScenarioConfig,
    ThreatType,
    ChannelModel,
    make_cloning_channel,
)


BB84_STATES = [
    (0, 0, "|0>"),
    (1, 0, "|1>"),
    (0, 1, "|+>"),
    (1, 1, "|->"),
]


class TestQuantumClonerFidelities:
    """Verify cloner circuit fidelities against analytical theoretical limits."""

    @pytest.mark.parametrize("bit,basis,label", BB84_STATES)
    def test_universal_cloner_fidelity_against_theory(self, bit, basis, label):
        """Universal cloner must achieve F = 5/6 (~0.8333) for all BB84 states on both clones."""
        f0, f1 = measure_cloner_fidelity(bit, basis, cloner_type="universal")
        # Exact statevector calculation matches theoretical fidelity within 1e-6
        assert math.isclose(f0, UNIVERSAL_FIDELITY, rel_tol=1e-5), f"Clone 1 for {label} got {f0}, expected {UNIVERSAL_FIDELITY}"
        assert math.isclose(f1, UNIVERSAL_FIDELITY, rel_tol=1e-5), f"Clone 2 for {label} got {f1}, expected {UNIVERSAL_FIDELITY}"
        # Symmetry: clone 1 and clone 2 must be identical
        assert math.isclose(f0, f1, abs_tol=1e-6)

    @pytest.mark.parametrize("bit,basis,label", BB84_STATES)
    def test_phase_covariant_cloner_fidelity_against_theory(self, bit, basis, label):
        """Phase-covariant cloner must achieve F ~ 0.8536 for all BB84 states on both clones."""
        f0, f1 = measure_cloner_fidelity(bit, basis, cloner_type="phase_covariant")
        assert math.isclose(f0, PHASE_COVARIANT_FIDELITY, rel_tol=1e-5), f"Clone 1 for {label} got {f0}, expected {PHASE_COVARIANT_FIDELITY}"
        assert math.isclose(f1, PHASE_COVARIANT_FIDELITY, rel_tol=1e-5), f"Clone 2 for {label} got {f1}, expected {PHASE_COVARIANT_FIDELITY}"
        assert math.isclose(f0, f1, abs_tol=1e-6)

    def test_phase_covariant_higher_fidelity_than_universal(self):
        """Phase-covariant cloner achieves strictly higher fidelity (~0.854 vs ~0.833) on BB84 states."""
        assert PHASE_COVARIANT_FIDELITY > UNIVERSAL_FIDELITY
        assert math.isclose(PHASE_COVARIANT_FIDELITY, 0.853553, abs_tol=1e-4)
        assert math.isclose(UNIVERSAL_FIDELITY, 5.0 / 6.0, abs_tol=1e-4)

    def test_statistical_sampling_error_rates(self):
        """Statistical simulation of single steps matches theoretical cloner error within tolerance."""
        rng = np.random.default_rng(12345)
        n_trials = 2000

        # Test Universal cloner error: expected ~16.7%
        u_errs = 0
        for _ in range(n_trials):
            bit = int(rng.integers(0, 2))
            basis = int(rng.integers(0, 2))
            step = simulate_eve_cloning_step(bit, basis, meas_basis_receiver=basis, cloner_type="universal", rng=rng)
            if step["is_mismatch"]:
                u_errs += 1
        measured_u_err = u_errs / n_trials
        # 3-sigma tolerance for Binomial(2000, 1/6) -> std ~ sqrt(2000 * 1/6 * 5/6)/2000 ~ 0.0083
        assert abs(measured_u_err - UNIVERSAL_ERROR) < 0.03, f"Measured universal error {measured_u_err} differs from {UNIVERSAL_ERROR}"

        # Test Phase-covariant cloner error: expected ~14.6%
        pc_errs = 0
        for _ in range(n_trials):
            bit = int(rng.integers(0, 2))
            basis = int(rng.integers(0, 2))
            step = simulate_eve_cloning_step(bit, basis, meas_basis_receiver=basis, cloner_type="phase_covariant", rng=rng)
            if step["is_mismatch"]:
                pc_errs += 1
        measured_pc_err = pc_errs / n_trials
        assert abs(measured_pc_err - PHASE_COVARIANT_ERROR) < 0.03, f"Measured PC error {measured_pc_err} differs from {PHASE_COVARIANT_ERROR}"


class TestEveCloningProtocolIntegration:
    """Verify QDS protocol behavior under opt-in eve_cloning threat scenario."""

    def test_cloning_threat_triggers_channel_alarm_and_rejects_forgery(self):
        """Under full-rate cloning (QBER ~15-17%), honest threshold e0=0.02 causes channel alarm and rejection."""
        rng = np.random.default_rng(42)
        eng = TeleportationQDS()
        scenario = ThreatScenarioConfig(
            threat_type=ThreatType.EVE_CLONING,
            cloner_type="universal",
            cloning_rate=1.0,
        )
        res = eng.execute_protocol("test message for cloning", n_bits=32, rng=rng, scenario=scenario)

        # Transcript and channel test must reflect elevated QBER (~16.7%)
        assert res.transcript.channel_test is not None
        assert res.transcript.channel_test.alarm is True
        assert res.threat_report.is_threat_detected is True
        # Eve's counterfeit signature should not be accepted
        assert not (res.transcript.display.get("bob") and res.transcript.display["bob"].accepted)

    def test_phase_covariant_cloning_threat(self):
        """Phase-covariant cloner is also detected by channel testing and verifier elimination."""
        rng = np.random.default_rng(42)
        eng = TeleportationQDS()
        scenario = ThreatScenarioConfig(
            threat_type=ThreatType.EVE_CLONING,
            cloner_type="phase_covariant",
            cloning_rate=1.0,
        )
        res = eng.execute_protocol("test message pc cloning", n_bits=64, rng=rng, scenario=scenario)
        assert res.transcript.channel_test.alarm is True
        assert res.threat_report.is_threat_detected is True
        assert not (res.transcript.display.get("bob") and res.transcript.display["bob"].accepted)

    def test_partial_cloning_rate_channel_model(self):
        """Expected QBER scales with cloning rate."""
        ch_full = make_cloning_channel("universal", cloning_rate=1.0)
        assert math.isclose(ch_full.expected_qber(), UNIVERSAL_ERROR, abs_tol=1e-4)

        ch_half = make_cloning_channel("universal", cloning_rate=0.5)
        assert math.isclose(ch_half.expected_qber(), 0.5 * UNIVERSAL_ERROR, abs_tol=1e-4)

        ch_pc = make_cloning_channel("phase_covariant", cloning_rate=1.0)
        assert math.isclose(ch_pc.expected_qber(), PHASE_COVARIANT_ERROR, abs_tol=1e-4)
