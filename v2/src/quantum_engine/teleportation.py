"""
Bell-state teleportation of a single Pauli eigenstate, followed by a verifier's
projective measurement.

Circuit (qubit 0 = Alice's token, qubits 1/2 = Bell pair |Phi+>, qubit 2 travels):

    q0: prep(bit, basis) ──■── H ── M -> m1
    q1: H ──■─────────────  X ─────── M -> m2
    q2: ────X ── [channel] ──── X^m2 ── Z^m1 ── (H if X-basis) ── M -> outcome

The channel acts on the travelling Bell half (q2):
  * intercept-resend: Eve measures q2 in a random Pauli basis and forwards the
    collapsed qubit;
  * depolarising noise: with probability p a uniformly random Pauli (X, Y, Z)
    is applied.

Channel randomness (Eve's basis, noise Pauli) is sampled classically from the
caller's RNG so that both backends execute the *same* circuit instance.

Two interchangeable backends execute that circuit:
  * ``QiskitTeleportationBackend``   - Qiskit circuit with mid-circuit measurement
    and classical feed-forward (``if_test``), run on AerSimulator.
  * ``StatevectorTeleportationBackend`` - a direct 3-qubit statevector
    simulation of the identical gate sequence; used for fast bulk experiments.
``tests/test_teleportation.py`` checks that both agree and that the teleported
state has unit fidelity on a noiseless channel.
"""
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

_SQ2 = 1.0 / np.sqrt(2.0)
_I = np.eye(2, dtype=complex)
_H = np.array([[1, 1], [1, -1]], dtype=complex) * _SQ2
_X = np.array([[0, 1], [1, 0]], dtype=complex)
_Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
_Z = np.array([[1, 0], [0, -1]], dtype=complex)
_PAULIS = {"X": _X, "Y": _Y, "Z": _Z}


@dataclass(frozen=True)
class TeleportJob:
    """One teleported token plus the channel events that hit it."""
    bit: int
    basis: int            # 0 = Z basis {|0>,|1>}, 1 = X basis {|+>,|->}
    meas_basis: int       # verifier's measurement basis
    eve_basis: Optional[int] = None   # None = not intercepted
    noise_pauli: Optional[str] = None  # None, "X", "Y" or "Z"


@dataclass(frozen=True)
class TeleportOutcome:
    outcome: int          # verifier's measurement result
    m1: int               # Alice's Bell-measurement bits (classical feed-forward)
    m2: int
    eve_outcome: Optional[int] = None


def sample_channel_events(
    n: int,
    rng: np.random.Generator,
    depolarizing: float,
    intercept_rate: float,
) -> List[tuple]:
    """Draw per-token (eve_basis, noise_pauli) from the hidden channel parameters."""
    events = []
    for _ in range(n):
        eve_basis = int(rng.integers(0, 2)) if rng.random() < intercept_rate else None
        noise = str(rng.choice(["X", "Y", "Z"])) if rng.random() < depolarizing else None
        events.append((eve_basis, noise))
    return events


# --------------------------------------------------------------------------
# Statevector backend
# --------------------------------------------------------------------------
class _ThreeQubitState:
    """Little-endian 3-qubit statevector (index = q0 + 2*q1 + 4*q2)."""

    def __init__(self):
        self.psi = np.zeros(8, dtype=complex)
        self.psi[0] = 1.0

    @staticmethod
    def _lift(U: np.ndarray, q: int) -> np.ndarray:
        ops = [_I, _I, _I]
        ops[2 - q] = U  # kron order is q2 (x) q1 (x) q0
        return np.kron(np.kron(ops[0], ops[1]), ops[2])

    def apply(self, U: np.ndarray, q: int):
        self.psi = self._lift(U, q) @ self.psi

    def cx(self, control: int, target: int):
        new = self.psi.copy()
        for i in range(8):
            if (i >> control) & 1:
                new[i] = self.psi[i ^ (1 << target)]
        self.psi = new

    def measure(self, q: int, rng: np.random.Generator) -> int:
        mask = np.array([(i >> q) & 1 for i in range(8)])
        p1 = float(np.sum(np.abs(self.psi[mask == 1]) ** 2))
        result = 1 if rng.random() < p1 else 0
        self.psi = np.where(mask == result, self.psi, 0)
        self.psi = self.psi / np.linalg.norm(self.psi)
        return result

    def reduced_q2(self) -> np.ndarray:
        """Density matrix of qubit 2 (partial trace over q0, q1)."""
        t = self.psi.reshape(2, 2, 2)  # axes: q2, q1, q0
        return np.einsum("aij,bij->ab", t, t.conj())


def _prep(state: _ThreeQubitState, bit: int, basis: int):
    if bit:
        state.apply(_X, 0)
    if basis:
        state.apply(_H, 0)


def _teleport_statevector(job: TeleportJob, rng: np.random.Generator, measure: bool = True):
    s = _ThreeQubitState()
    _prep(s, job.bit, job.basis)
    # Bell pair |Phi+> on q1,q2
    s.apply(_H, 1)
    s.cx(1, 2)
    # Channel acting on the travelling half
    eve_outcome = None
    if job.eve_basis is not None:
        if job.eve_basis:
            s.apply(_H, 2)
        eve_outcome = s.measure(2, rng)
        if job.eve_basis:
            s.apply(_H, 2)
    if job.noise_pauli:
        s.apply(_PAULIS[job.noise_pauli], 2)
    # Alice's Bell measurement
    s.cx(0, 1)
    s.apply(_H, 0)
    m1 = s.measure(0, rng)
    m2 = s.measure(1, rng)
    # Classical feed-forward Pauli correction X^m2 Z^m1
    if m2:
        s.apply(_X, 2)
    if m1:
        s.apply(_Z, 2)
    if not measure:
        return s, m1, m2, eve_outcome
    if job.meas_basis:
        s.apply(_H, 2)
    outcome = s.measure(2, rng)
    return TeleportOutcome(outcome=outcome, m1=m1, m2=m2, eve_outcome=eve_outcome)


def teleported_state_fidelity(bit: int, basis: int, rng: np.random.Generator) -> float:
    """Fidelity <psi|rho_q2|psi> of the teleported state on a noiseless channel."""
    s, _, _, _ = _teleport_statevector(TeleportJob(bit, basis, 0), rng, measure=False)
    target = np.array([1, 0], dtype=complex) if bit == 0 else np.array([0, 1], dtype=complex)
    if basis:
        target = _H @ target
    rho = s.reduced_q2()
    return float(np.real(target.conj() @ rho @ target))


class StatevectorTeleportationBackend:
    name = "statevector"

    def run(self, jobs: Sequence[TeleportJob], rng: np.random.Generator) -> List[TeleportOutcome]:
        return [_teleport_statevector(job, rng) for job in jobs]


# --------------------------------------------------------------------------
# Qiskit backend
# --------------------------------------------------------------------------
def build_teleportation_circuit(job: TeleportJob, save_density_matrix: bool = False):
    """Qiskit circuit for one job, with mid-circuit Bell measurement and feed-forward."""
    from qiskit import QuantumCircuit

    # clbits: 0 = m1, 1 = m2, 2 = verifier outcome, 3 = Eve's outcome
    qc = QuantumCircuit(3, 4)
    if job.bit:
        qc.x(0)
    if job.basis:
        qc.h(0)
    qc.h(1)
    qc.cx(1, 2)
    if job.eve_basis is not None:
        if job.eve_basis:
            qc.h(2)
        qc.measure(2, 3)
        if job.eve_basis:
            qc.h(2)
    if job.noise_pauli == "X":
        qc.x(2)
    elif job.noise_pauli == "Y":
        qc.y(2)
    elif job.noise_pauli == "Z":
        qc.z(2)
    qc.cx(0, 1)
    qc.h(0)
    qc.measure(0, 0)
    qc.measure(1, 1)
    with qc.if_test((qc.clbits[1], 1)):
        qc.x(2)
    with qc.if_test((qc.clbits[0], 1)):
        qc.z(2)
    if save_density_matrix:
        qc.save_density_matrix([2])
        return qc
    if job.meas_basis:
        qc.h(2)
    qc.measure(2, 2)
    return qc


class QiskitTeleportationBackend:
    name = "qiskit"

    def __init__(self):
        from qiskit_aer import AerSimulator
        self._sim = AerSimulator()

    def run(self, jobs: Sequence[TeleportJob], rng: np.random.Generator) -> List[TeleportOutcome]:
        if not jobs:
            return []
        circuits = [build_teleportation_circuit(j) for j in jobs]
        seed = int(rng.integers(0, 2**31 - 1))
        result = self._sim.run(circuits, shots=1, memory=True, seed_simulator=seed).result()
        outcomes = []
        for i, job in enumerate(jobs):
            bits = result.get_memory(i)[0][::-1]  # clbit 0 first
            outcomes.append(TeleportOutcome(
                outcome=int(bits[2]),
                m1=int(bits[0]),
                m2=int(bits[1]),
                eve_outcome=int(bits[3]) if job.eve_basis is not None else None,
            ))
        return outcomes


def make_backend(name: str = "qiskit"):
    if name == "qiskit":
        return QiskitTeleportationBackend()
    if name == "statevector":
        return StatevectorTeleportationBackend()
    raise ValueError(f"Unknown teleportation backend: {name}")
