"""Issue 5: the executed path really teleports (Bell pair, Bell measurement, feed-forward, correction)."""
import numpy as np
import pytest

from src.quantum_engine.teleportation import (
    QiskitTeleportationBackend,
    StatevectorTeleportationBackend,
    TeleportJob,
    build_teleportation_circuit,
    teleported_state_fidelity,
)

STATES = [(0, 0), (1, 0), (0, 1), (1, 1)]


@pytest.mark.parametrize("bit,basis", STATES)
def test_statevector_teleportation_has_unit_fidelity(bit, basis, rng):
    for _ in range(20):  # every Bell-measurement branch
        assert teleported_state_fidelity(bit, basis, rng) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("bit,basis", STATES)
def test_qiskit_circuit_teleports_with_unit_fidelity(bit, basis):
    from qiskit_aer import AerSimulator
    from qiskit.quantum_info import Statevector, state_fidelity

    qc = build_teleportation_circuit(TeleportJob(bit, basis, basis), save_density_matrix=True)
    sim = AerSimulator(method="density_matrix")
    target = Statevector.from_label({(0, 0): "0", (1, 0): "1", (0, 1): "+", (1, 1): "-"}[(bit, basis)])
    for seed in range(8):
        rho = sim.run(qc, shots=1, seed_simulator=seed).result().data(0)["density_matrix"]
        assert state_fidelity(rho, target) == pytest.approx(1.0, abs=1e-9)


def test_circuit_contains_feed_forward():
    qc = build_teleportation_circuit(TeleportJob(1, 1, 0))
    names = [inst.operation.name for inst in qc.data]
    assert names.count("if_else") == 2 and "measure" in names and "cx" in names


@pytest.mark.parametrize("backend_cls", [StatevectorTeleportationBackend, QiskitTeleportationBackend])
def test_noiseless_matched_basis_is_deterministic(backend_cls, rng):
    backend = backend_cls()
    jobs = [TeleportJob(b, ba, ba) for b, ba in STATES for _ in range(10)]
    assert all(o.outcome == j.bit for o, j in zip(backend.run(jobs, rng), jobs))


@pytest.mark.parametrize("backend_cls,n", [(StatevectorTeleportationBackend, 2000), (QiskitTeleportationBackend, 600)])
def test_intercept_resend_gives_quarter_error_rate(backend_cls, n, rng):
    backend = backend_cls()
    jobs = [TeleportJob(int(rng.integers(2)), ba, ba, eve_basis=int(rng.integers(2))) for ba in [0, 1] * (n // 2)]
    outs = backend.run(jobs, rng)
    rate = np.mean([o.outcome != j.bit for o, j in zip(outs, jobs)])
    se = np.sqrt(0.25 * 0.75 / n)
    assert abs(rate - 0.25) < 4 * se


def test_backends_agree_on_noisy_jobs(rng):
    jobs = []
    for i in range(600):
        b, ba, mb = int(rng.integers(2)), int(rng.integers(2)), int(rng.integers(2))
        jobs.append(TeleportJob(b, ba, mb, noise_pauli=["X", "Y", "Z", None][i % 4]))
    a = np.array([o.outcome == j.bit for o, j in zip(StatevectorTeleportationBackend().run(jobs, rng), jobs)])
    q = np.array([o.outcome == j.bit for o, j in zip(QiskitTeleportationBackend().run(jobs, rng), jobs)])
    matched = np.array([j.basis == j.meas_basis for j in jobs])
    # Matched-basis outcomes are deterministic given the Pauli, so they must agree exactly.
    assert (a[matched] == q[matched]).all()
