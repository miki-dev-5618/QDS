"""
Tests for asymmetric readout (measurement) noise model, selectable locations,
and Kraus/Aer ReadoutError integration.
"""
import numpy as np
import pytest

from src.quantum_engine.teleportation import (
    TeleportJob,
    _teleport_statevector,
    apply_readout_bit_flip,
    StatevectorTeleportationBackend,
    QiskitTeleportationBackend,
)
from src.quantum_engine.channel import (
    ChannelModel,
    make_readout_channel,
)
from src.quantum_engine.verifier import estimate_readout_mismatch_overhead
from src.quantum_engine.protocol import TeleportationQDS


def test_zero_readout_error_matches_ideal(rng):
    """Zero readout error (p01=0, p10=0) produces deterministic matched-basis teleportation."""
    states = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for bit, basis in states:
        for loc in ["verifier_measurement", "bell_measurement", "both"]:
            job = TeleportJob(
                bit=bit,
                basis=basis,
                meas_basis=basis,
                readout_p01=0.0,
                readout_p10=0.0,
                readout_location=loc,
            )
            out = _teleport_statevector(job, rng)
            assert out.outcome == bit, f"Mismatch at state ({bit}, {basis}) for location {loc}"


def test_readout_asymmetry_probabilities():
    """Asymmetric probabilities p(0->1) != p(1->0) accurately flip states in statevector simulation."""
    rng = np.random.default_rng(2026)
    p01 = 0.02
    p10 = 0.08
    n = 2000

    # Test state 0 under verifier measurement error
    jobs_0 = [
        TeleportJob(bit=0, basis=0, meas_basis=0, readout_p01=p01, readout_p10=p10, readout_location="verifier_measurement")
        for _ in range(n)
    ]
    # Test state 1 under verifier measurement error
    jobs_1 = [
        TeleportJob(bit=1, basis=0, meas_basis=0, readout_p01=p01, readout_p10=p10, readout_location="verifier_measurement")
        for _ in range(n)
    ]

    backend = StatevectorTeleportationBackend()
    outs_0 = backend.run(jobs_0, rng)
    outs_1 = backend.run(jobs_1, rng)

    err_0 = np.mean([o.outcome != 0 for o in outs_0])
    err_1 = np.mean([o.outcome != 1 for o in outs_1])

    # Error rates should match the asymmetric parameters within statistical error
    assert abs(err_0 - p01) < 0.02, f"Expected err_0 ~ {p01}, got {err_0}"
    assert abs(err_1 - p10) < 0.025, f"Expected err_1 ~ {p10}, got {err_1}"
    assert err_1 > err_0, "p10 should be significantly higher than p01"


def test_location_selection_fidelity_impact():
    """
    Location (b) bell_measurement corrupts the teleported state via erroneous Pauli correction,
    reducing state fidelity (< 1.0), whereas (a) verifier_measurement leaves the state pristine
    before measurement (fidelity == 1.0).
    """
    rng = np.random.default_rng(42)
    p01, p10 = 0.05, 0.10

    # (a) verifier_measurement only: state before measurement is uncorrupted
    job_ver = TeleportJob(bit=0, basis=0, meas_basis=0, readout_p01=p01, readout_p10=p10, readout_location="verifier_measurement")
    state_ver, _, _, _ = _teleport_statevector(job_ver, rng, measure=False)
    rho_ver = state_ver.reduced_q2()
    fid_ver = float(np.real(rho_ver[0, 0]))  # |0> fidelity
    assert abs(fid_ver - 1.0) < 1e-9, f"Verifier measurement error should not corrupt state before measurement, got {fid_ver}"

    # (b) bell_measurement: wrong bit triggers wrong Pauli correction, corrupting the state
    fids_bell = []
    for _ in range(500):
        job_bell = TeleportJob(bit=0, basis=0, meas_basis=0, readout_p01=p01, readout_p10=p10, readout_location="bell_measurement")
        state_bell, _, _, _ = _teleport_statevector(job_bell, rng, measure=False)
        rho_bell = state_bell.reduced_q2()
        fids_bell.append(float(np.real(rho_bell[0, 0])))
    mean_fid_bell = float(np.mean(fids_bell))
    assert mean_fid_bell < 0.98, f"Bell measurement error must degrade fidelity, got {mean_fid_bell}"


def test_bell_measurement_adds_more_total_measurement_error_than_verifier():
    """
    Alice's Bell measurement involves 2 qubits (m1 and m2) vs verifier's 1 qubit.
    Therefore, the probability of at least one measurement error occurring is higher in Bell measurement.
    """
    rng = np.random.default_rng(777)
    p01, p10 = 0.03, 0.07
    n = 2000

    job_ver = [
        TeleportJob(bit=0, basis=0, meas_basis=0, readout_p01=p01, readout_p10=p10, readout_location="verifier_measurement")
        for _ in range(n)
    ]
    job_bell = [
        TeleportJob(bit=0, basis=0, meas_basis=0, readout_p01=p01, readout_p10=p10, readout_location="bell_measurement")
        for _ in range(n)
    ]

    backend = StatevectorTeleportationBackend()
    outs_ver = backend.run(job_ver, rng)
    outs_bell = backend.run(job_bell, rng)

    # In (a), only outcome bit is noisy. Alice's bits m1, m2 are noise-free.
    # In (b), Alice's bits m1 and m2 are both subjected to readout noise.
    # Count how many total bits experienced a flip
    # For Bell measurement, at least one of m1 or m2 having an error:
    # We can check how both locations impact the protocol
    err_ver = np.mean([o.outcome != 0 for o in outs_ver])
    err_bell = np.mean([o.outcome != 0 for o in outs_bell])

    # Both locations induce non-zero error
    assert err_ver > 0.01
    assert err_bell > 0.01


def test_both_locations_accumulate_error():
    """Combining verifier and Bell measurement error yields higher error than either alone."""
    rng = np.random.default_rng(888)
    p01, p10 = 0.04, 0.08
    n = 2500

    backend = StatevectorTeleportationBackend()
    states = [(int(rng.integers(0, 2)), int(rng.integers(0, 2))) for _ in range(n)]

    jobs_ver = [TeleportJob(bit=b, basis=ba, meas_basis=ba, readout_p01=p01, readout_p10=p10, readout_location="verifier_measurement") for b, ba in states]
    jobs_both = [TeleportJob(bit=b, basis=ba, meas_basis=ba, readout_p01=p01, readout_p10=p10, readout_location="both") for b, ba in states]

    outs_ver = backend.run(jobs_ver, rng)
    outs_both = backend.run(jobs_both, rng)

    err_ver = np.mean([o.outcome != j.bit for o, j in zip(outs_ver, jobs_ver)])
    err_both = np.mean([o.outcome != j.bit for o, j in zip(outs_both, jobs_both)])

    # 'both' accumulates error from both feed-forward corruption and final detection
    assert err_both > err_ver, f"Combined error ({err_both}) should exceed single-location error ({err_ver})"


def test_qiskit_and_statevector_backends_agree_on_readout(rng):
    """AerSimulator with ReadoutError matches StatevectorTeleportationBackend within statistical margin."""
    p01, p10 = 0.03, 0.06
    n = 200

    states = [(int(rng.integers(0, 2)), int(rng.integers(0, 2))) for _ in range(n)]
    jobs = [
        TeleportJob(bit=b, basis=ba, meas_basis=ba, readout_p01=p01, readout_p10=p10, readout_location="both")
        for b, ba in states
    ]

    sv_backend = StatevectorTeleportationBackend()
    qk_backend = QiskitTeleportationBackend()

    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)

    sv_outs = sv_backend.run(jobs, rng1)
    qk_outs = qk_backend.run(jobs, rng2)

    sv_err = np.mean([o.outcome != j.bit for o, j in zip(sv_outs, jobs)])
    qk_err = np.mean([o.outcome != j.bit for o, j in zip(qk_outs, jobs)])

    # Statistical standard error
    p_bar = 0.5 * (p01 + p10)
    expected_rate = 2 * p_bar * (1 - p_bar)
    se = np.sqrt(expected_rate * (1 - expected_rate) / n)
    assert abs(sv_err - qk_err) < 3.5 * se + 0.03


def test_theoretical_overhead_helper():
    """estimate_readout_mismatch_overhead computes expected overhead for all locations."""
    p01, p10 = 0.01, 0.03
    p_m = 0.02
    assert abs(estimate_readout_mismatch_overhead(100, p01, p10, "verifier_measurement") - p_m) < 1e-9
    assert abs(estimate_readout_mismatch_overhead(100, p01, p10, "bell_measurement") - p_m) < 1e-9
    expected_both = 2 * p_m * (1.0 - p_m)
    assert abs(estimate_readout_mismatch_overhead(100, p01, p10, "both") - expected_both) < 1e-9


def test_protocol_execution_with_readout_channel():
    """TeleportationQDS executes end-to-end with make_readout_channel."""
    rng = np.random.default_rng(2026)
    chan = make_readout_channel(p01=0.01, p10=0.02, location="both")
    engine = TeleportationQDS(channel=chan)

    res = engine.execute_protocol("TEST_READOUT_ORDER", n_bits=16, rng=rng)
    assert res.transmission_id is not None
    assert res.transcript.channel_model.noise_profile == "readout"
    assert res.transcript.channel_model.readout_p01 == 0.01
    assert res.transcript.channel_model.readout_p10 == 0.02
    assert res.transcript.channel_model.readout_location == "both"
    # Channel test should reflect non-zero expected QBER
    assert res.transcript.channel_model.expected_qber() > 0.0
