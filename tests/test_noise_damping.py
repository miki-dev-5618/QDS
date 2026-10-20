"""
Tests for amplitude damping noise model and Kraus quantum trajectory simulation.
"""
import numpy as np
import pytest

from src.quantum_engine.teleportation import (
    TeleportJob,
    _teleport_statevector,
    build_teleportation_circuit,
    get_damping_kraus_ops,
    StatevectorTeleportationBackend,
    QiskitTeleportationBackend,
)
from src.quantum_engine.channel import ChannelModel, make_amplitude_damping_channel
from src.quantum_engine.protocol import TeleportationQDS


def test_kraus_ops_gamma_zero_is_identity():
    """At gamma=0 and phase_gamma=0, Kraus operator is identity."""
    ops = get_damping_kraus_ops(gamma=0.0, phase_gamma=0.0)
    assert len(ops) == 1
    assert np.allclose(ops[0], np.eye(2, dtype=complex))


def test_gamma_zero_identical_to_ideal(rng):
    """At gamma=0, teleportation matched-basis measurement is deterministic and error-free."""
    states = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for bit, basis in states:
        job = TeleportJob(bit=bit, basis=basis, meas_basis=basis, damping_gamma=0.0)
        out = _teleport_statevector(job, rng)
        assert out.outcome == bit


@pytest.mark.parametrize("target_qubit", ["traveling", "teleported", "bell_pair"])
def test_gamma_greater_than_zero_error_rises(target_qubit):
    """As gamma increases above zero, honest matched-basis error increases."""
    rng = np.random.default_rng(2026)
    n = 1500

    # Low vs higher damping on bit=1, basis=0 (|1> state decays to |0>)
    errs = []
    gammas = [0.0, 0.05, 0.15]
    for g in gammas:
        jobs = [
            TeleportJob(bit=1, basis=0, meas_basis=0, damping_gamma=g, damping_target=target_qubit)
            for _ in range(n)
        ]
        backend = StatevectorTeleportationBackend()
        outs = backend.run(jobs, rng)
        err_rate = np.mean([o.outcome != 1 for o in outs])
        errs.append(err_rate)

    # gamma=0 has zero error
    assert errs[0] == 0.0
    # gamma=0.05 has non-zero error
    assert errs[1] > 0.01
    # gamma=0.15 has higher error than gamma=0.05
    assert errs[2] > errs[1]


def test_amplitude_damping_asymmetry():
    """
    Amplitude damping is asymmetric:
    On the teleported token (|0> vs |1>), |0> does not decay, whereas |1> decays to |0>.
    On traveling qubit (Bell-pair half), damping biases measurements toward 0.
    """
    rng = np.random.default_rng(42)
    gamma = 0.12
    n = 2000

    # Direct damping on token (teleported qubit q0)
    jobs_0 = [TeleportJob(bit=0, basis=0, meas_basis=0, damping_gamma=gamma, damping_target="teleported") for _ in range(n)]
    jobs_1 = [TeleportJob(bit=1, basis=0, meas_basis=0, damping_gamma=gamma, damping_target="teleported") for _ in range(n)]

    backend = StatevectorTeleportationBackend()
    outs_0 = backend.run(jobs_0, rng)
    outs_1 = backend.run(jobs_1, rng)

    err_0 = np.mean([o.outcome != 0 for o in outs_0])
    err_1 = np.mean([o.outcome != 1 for o in outs_1])

    # In Z-basis, prepared |0> never decays to |1> under amplitude damping
    assert err_0 == 0.0
    # prepared |1> decays to |0> with probability gamma
    assert abs(err_1 - gamma) < 0.03


def test_qiskit_and_statevector_backends_agree_on_damping(rng):
    """Statevector and Qiskit density-matrix backends exhibit consistent error rates under damping."""
    gamma = 0.08
    n = 250
    jobs = [
        TeleportJob(bit=1, basis=0, meas_basis=0, damping_gamma=gamma, damping_target="traveling")
        for _ in range(n)
    ]
    sv_backend = StatevectorTeleportationBackend()
    qk_backend = QiskitTeleportationBackend()

    rng1 = np.random.default_rng(101)
    rng2 = np.random.default_rng(101)

    sv_outs = sv_backend.run(jobs, rng1)
    qk_outs = qk_backend.run(jobs, rng2)

    sv_err = np.mean([o.outcome != 1 for o in sv_outs])
    qk_err = np.mean([o.outcome != 1 for o in qk_outs])

    se = np.sqrt(gamma * (1.0 - gamma) / n)
    assert abs(sv_err - qk_err) < 3.5 * se


def test_protocol_execution_with_amp_damping():
    """TeleportationQDS executes end-to-end with make_amplitude_damping_channel."""
    rng = np.random.default_rng(42)
    chan = make_amplitude_damping_channel(gamma=0.02)
    engine = TeleportationQDS(channel=chan)

    res = engine.execute_protocol("TEST_ORDERS_AMP", n_bits=16, rng=rng)
    assert res.transmission_id is not None
    assert res.transcript.n_bits == 16
    # With small gamma=0.02, honest transmission should still succeed
    assert res.transcript.display["bob"].accepted
    assert res.transcript.display["charlie"].accepted
