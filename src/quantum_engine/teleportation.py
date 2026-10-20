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
    damping_gamma: float = 0.0        # amplitude damping parameter in [0, 1]
    phase_damping_gamma: float = 0.0  # optional phase damping parameter
    damping_target: str = "traveling" # "traveling" (q2), "teleported" (q0), "bell_pair" (q1, q2), "all"
    readout_p01: float = 0.0          # P(read=1 | true=0)
    readout_p10: float = 0.0          # P(read=0 | true=1)
    readout_location: str = "both"    # "verifier_measurement", "bell_measurement", "both"


def apply_readout_bit_flip(bit: int, p01: float, p10: float, rng: np.random.Generator) -> int:
    """Simulate single-bit asymmetric readout error."""
    if p01 <= 0.0 and p10 <= 0.0:
        return bit
    if bit == 0:
        return 1 if rng.random() < p01 else 0
    return 0 if rng.random() < p10 else 1


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

    def apply_kraus(self, kraus_ops: Sequence[np.ndarray], q: int, rng: np.random.Generator):
        """Apply a single-qubit Kraus channel via quantum trajectory statevector collapse."""
        if not kraus_ops:
            return
        if len(kraus_ops) == 1:
            self.apply(kraus_ops[0], q)
            norm = np.linalg.norm(self.psi)
            if norm > 0:
                self.psi /= norm
            return
        branch_states = []
        branch_probs = []
        for K in kraus_ops:
            branch_psi = self._lift(K, q) @ self.psi
            prob = float(np.real(branch_psi.conj() @ branch_psi))
            branch_states.append(branch_psi)
            branch_probs.append(prob)
        total_p = sum(branch_probs)
        if total_p <= 0:
            return
        p_arr = np.array(branch_probs) / total_p
        chosen_idx = int(rng.choice(len(kraus_ops), p=p_arr))
        chosen_state = branch_states[chosen_idx]
        norm = np.linalg.norm(chosen_state)
        self.psi = chosen_state / norm if norm > 0 else chosen_state

    def reduced_q2(self) -> np.ndarray:
        """Density matrix of qubit 2 (partial trace over q0, q1)."""
        t = self.psi.reshape(2, 2, 2)  # axes: q2, q1, q0
        return np.einsum("aij,bij->ab", t, t.conj())


def get_damping_kraus_ops(gamma: float, phase_gamma: float = 0.0) -> List[np.ndarray]:
    """
    Construct Kraus operators for amplitude damping with parameter gamma in [0, 1],
    optionally combined with phase damping with parameter phase_gamma in [0, 1].
    """
    if gamma <= 0.0 and phase_gamma <= 0.0:
        return [np.eye(2, dtype=complex)]

    gamma = min(1.0, max(0.0, float(gamma)))
    phase_gamma = min(1.0, max(0.0, float(phase_gamma)))

    # Amplitude damping Kraus operators:
    # E0 = [[1, 0], [0, sqrt(1 - gamma)]]
    # E1 = [[0, sqrt(gamma)], [0, 0]]
    if gamma > 0.0 and phase_gamma <= 0.0:
        E0 = np.array([[1.0, 0.0], [0.0, np.sqrt(1.0 - gamma)]], dtype=complex)
        E1 = np.array([[0.0, np.sqrt(gamma)], [0.0, 0.0]], dtype=complex)
        return [E0, E1]

    # If phase damping is combined:
    # Phase damping Kraus operators:
    # P0 = [[1, 0], [0, sqrt(1 - phase_gamma)]]
    # P1 = [[0, 0], [0, sqrt(phase_gamma)]]
    if gamma <= 0.0 and phase_gamma > 0.0:
        P0 = np.array([[1.0, 0.0], [0.0, np.sqrt(1.0 - phase_gamma)]], dtype=complex)
        P1 = np.array([[0.0, 0.0], [0.0, np.sqrt(phase_gamma)]], dtype=complex)
        return [P0, P1]

    # Both: compose Pi @ Ej
    E0 = np.array([[1.0, 0.0], [0.0, np.sqrt(1.0 - gamma)]], dtype=complex)
    E1 = np.array([[0.0, np.sqrt(gamma)], [0.0, 0.0]], dtype=complex)
    P0 = np.array([[1.0, 0.0], [0.0, np.sqrt(1.0 - phase_gamma)]], dtype=complex)
    P1 = np.array([[0.0, 0.0], [0.0, np.sqrt(phase_gamma)]], dtype=complex)
    ops = [P0 @ E0, P0 @ E1, P1 @ E0, P1 @ E1]
    return [op for op in ops if np.any(np.abs(op) > 1e-12)]


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
    # Amplitude / phase damping noise channel
    if job.damping_gamma > 0.0 or job.phase_damping_gamma > 0.0:
        kraus = get_damping_kraus_ops(job.damping_gamma, job.phase_damping_gamma)
        target = job.damping_target.lower()
        if target in ("traveling", "travelling", "q2"):
            s.apply_kraus(kraus, 2, rng)
        elif target in ("teleported", "token", "q0"):
            s.apply_kraus(kraus, 0, rng)
        elif target in ("bell_pair", "q1_q2"):
            s.apply_kraus(kraus, 1, rng)
            s.apply_kraus(kraus, 2, rng)
        elif target in ("all", "all_qubits"):
            s.apply_kraus(kraus, 0, rng)
            s.apply_kraus(kraus, 1, rng)
            s.apply_kraus(kraus, 2, rng)
        else:
            s.apply_kraus(kraus, 2, rng)
    # Alice's Bell measurement
    s.cx(0, 1)
    s.apply(_H, 0)
    m1 = s.measure(0, rng)
    m2 = s.measure(1, rng)

    has_bell_ro = (job.readout_p01 > 0.0 or job.readout_p10 > 0.0) and job.readout_location.lower() in (
        "bell_measurement", "bell", "both", "all"
    )
    if has_bell_ro:
        m1_eff = apply_readout_bit_flip(m1, job.readout_p01, job.readout_p10, rng)
        m2_eff = apply_readout_bit_flip(m2, job.readout_p01, job.readout_p10, rng)
    else:
        m1_eff, m2_eff = m1, m2

    # Classical feed-forward Pauli correction X^m2 Z^m1 using the bits Alice reported
    if m2_eff:
        s.apply(_X, 2)
    if m1_eff:
        s.apply(_Z, 2)
    if not measure:
        return s, m1_eff, m2_eff, eve_outcome
    if job.meas_basis:
        s.apply(_H, 2)
    outcome = s.measure(2, rng)

    has_ver_ro = (job.readout_p01 > 0.0 or job.readout_p10 > 0.0) and job.readout_location.lower() in (
        "verifier_measurement", "verifier", "both", "all"
    )
    if has_ver_ro:
        outcome = apply_readout_bit_flip(outcome, job.readout_p01, job.readout_p10, rng)

    return TeleportOutcome(outcome=outcome, m1=m1_eff, m2=m2_eff, eve_outcome=eve_outcome)


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
    if job.damping_gamma > 0.0 or job.phase_damping_gamma > 0.0:
        target = job.damping_target.lower()
        kraus = get_damping_kraus_ops(job.damping_gamma, job.phase_damping_gamma)
        from qiskit.quantum_info import Kraus
        k_channel = Kraus(kraus)
        if target in ("traveling", "travelling", "q2"):
            qc.append(k_channel, [2])
        elif target in ("teleported", "token", "q0"):
            qc.append(k_channel, [0])
        elif target in ("bell_pair", "q1_q2"):
            qc.append(k_channel, [1])
            qc.append(k_channel, [2])
        elif target in ("all", "all_qubits"):
            qc.append(k_channel, [0])
            qc.append(k_channel, [1])
            qc.append(k_channel, [2])
        else:
            qc.append(k_channel, [2])
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
        has_damping = any(j.damping_gamma > 0.0 or j.phase_damping_gamma > 0.0 for j in jobs)
        has_readout = any(j.readout_p01 > 0.0 or j.readout_p10 > 0.0 for j in jobs)
        circuits = [build_teleportation_circuit(j) for j in jobs]
        seed = int(rng.integers(0, 2**31 - 1))
        if has_readout:
            from qiskit_aer import AerSimulator
            from qiskit_aer.noise import NoiseModel, ReadoutError
            p01 = max(j.readout_p01 for j in jobs)
            p10 = max(j.readout_p10 for j in jobs)
            loc = jobs[0].readout_location.lower() if jobs else "both"
            ro_error = ReadoutError([[1.0 - p01, p01], [p10, 1.0 - p10]])
            noise_model = NoiseModel()
            if loc in ("verifier_measurement", "verifier"):
                noise_model.add_readout_error(ro_error, [2])
            elif loc in ("bell_measurement", "bell"):
                noise_model.add_readout_error(ro_error, [0])
                noise_model.add_readout_error(ro_error, [1])
            else:  # "both" or "all"
                noise_model.add_readout_error(ro_error, [0])
                noise_model.add_readout_error(ro_error, [1])
                noise_model.add_readout_error(ro_error, [2])
            sim = AerSimulator(noise_model=noise_model, method="density_matrix" if has_damping else "automatic")
            result = sim.run(circuits, shots=1, memory=True, seed_simulator=seed).result()
        elif has_damping:
            from qiskit_aer import AerSimulator
            sim = AerSimulator(method="density_matrix")
            result = sim.run(circuits, shots=1, memory=True, seed_simulator=seed).result()
        else:
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


# --------------------------------------------------------------------------
# Deferred-measurement teleportation & IBM fake backend integration
# --------------------------------------------------------------------------
def build_deferred_teleportation_circuit(job: TeleportJob):
    """
    Deferred-measurement teleportation circuit without mid-circuit classical feed-forward.
    Replaces conditional classical feed-forward with coherent CX and CZ gates prior
    to measurement, allowing the exact circuit to execute on real IBM hardware.
    """
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3, 4 if job.eve_basis is not None else 3)
    if job.bit:
        qc.x(0)
    if job.basis:
        qc.h(0)
    # Bell pair preparation on q1, q2
    qc.h(1)
    qc.cx(1, 2)
    # Optional Eve eavesdropping on travelling qubit q2
    if job.eve_basis is not None:
        if job.eve_basis:
            qc.h(2)
        qc.measure(2, 3)
        if job.eve_basis:
            qc.h(2)
    # Channel Pauli noise
    if job.noise_pauli == "X":
        qc.x(2)
    elif job.noise_pauli == "Y":
        qc.y(2)
    elif job.noise_pauli == "Z":
        qc.z(2)
    if job.damping_gamma > 0.0 or job.phase_damping_gamma > 0.0:
        target = job.damping_target.lower()
        kraus = get_damping_kraus_ops(job.damping_gamma, job.phase_damping_gamma)
        from qiskit.quantum_info import Kraus
        k_channel = Kraus(kraus)
        if target in ("traveling", "travelling", "q2"):
            qc.append(k_channel, [2])
        elif target in ("teleported", "token", "q0"):
            qc.append(k_channel, [0])
        elif target in ("bell_pair", "q1_q2"):
            qc.append(k_channel, [1])
            qc.append(k_channel, [2])
        elif target in ("all", "all_qubits"):
            qc.append(k_channel, [0])
            qc.append(k_channel, [1])
            qc.append(k_channel, [2])
        else:
            qc.append(k_channel, [2])
    # Alice's Bell basis rotation
    qc.cx(0, 1)
    qc.h(0)
    # Coherent deferred feed-forward (controlled gates):
    # m2 (from q1) controls X on q2 -> CX(1, 2)
    # m1 (from q0) controls Z on q2 -> CZ(0, 2)
    qc.cx(1, 2)
    qc.cz(0, 2)
    # Measurements at circuit termination
    qc.measure(0, 0)
    qc.measure(1, 1)
    if job.meas_basis:
        qc.h(2)
    qc.measure(2, 2)
    return qc


def get_fake_backend(backend_name: Optional[str] = None):
    """
    Resolve and return a fake backend. Configurable via HEDWIG_IBM_FAKE_BACKEND.
    Supports qiskit_ibm_runtime.fake_provider if installed, otherwise uses
    qiskit.providers.fake_provider.GenericBackendV2.
    """
    import os
    target = backend_name or os.environ.get("HEDWIG_IBM_FAKE_BACKEND")

    # 1. Try qiskit_ibm_runtime.fake_provider if available
    try:
        from qiskit_ibm_runtime import fake_provider  # type: ignore
        if target and hasattr(fake_provider, target):
            cls = getattr(fake_provider, target)
            return cls()
        for cand in ["FakeManila", "FakeSherbrooke", "FakeBrisbane", "FakeTorino"]:
            if hasattr(fake_provider, cand):
                return getattr(fake_provider, cand)()
    except ImportError:
        pass

    # 2. Try qiskit.providers.fake_provider
    try:
        from qiskit.providers.fake_provider import GenericBackendV2
        return GenericBackendV2(num_qubits=5, seed=42)
    except ImportError:
        pass

    raise RuntimeError("No fake backend provider found. Please install qiskit or qiskit-ibm-runtime.")


def calibrate_ibm_backend(
    backend_name: Optional[str] = None,
    shots: int = 5000,
    cache_dir: str = "experiments/calibration",
    force: bool = False,
    seed: int = 42,
) -> dict:
    """
    Calibrate the IBM fake backend by running deferred teleportation circuits on AerSimulator
    (~5,000 shots per state) to estimate effective per-token error and confusion matrix.
    Saves calibration to experiments/calibration/ibm_<backend>.json.
    """
    import json
    import os
    import time
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel

    backend = get_fake_backend(backend_name)
    safe_name = backend.name.lower().replace(" ", "_")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"ibm_{safe_name}.json")

    if os.path.exists(cache_file) and not force:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    noise_model = NoiseModel.from_backend(backend)
    sim = AerSimulator(noise_model=noise_model)

    # 4 input states: |0> (bit=0, basis=0), |1> (bit=1, basis=0),
    #                 |+> (bit=0, basis=1), |-> (bit=1, basis=1)
    test_states = [
        ("0", 0, 0),
        ("1", 1, 0),
        ("+", 0, 1),
        ("-", 1, 1),
    ]

    confusion_matrix = {}
    error_rates = []

    for label, bit, basis in test_states:
        job = TeleportJob(bit=bit, basis=basis, meas_basis=basis)
        qc = build_deferred_teleportation_circuit(job)
        tqc = transpile(qc, backend=backend, seed_transpiler=seed)
        counts = sim.run(tqc, shots=shots, seed_simulator=seed).result().get_counts()

        total = sum(counts.values())
        correct = 0
        p0 = p1 = 0.0
        for bitstring, count in counts.items():
            bits = bitstring.replace(" ", "")[::-1]
            out = int(bits[2])
            if out == 0:
                p0 += count
            else:
                p1 += count
            if out == bit:
                correct += count

        err_rate = (total - correct) / total
        error_rates.append(err_rate)
        confusion_matrix[label] = {
            "p0": round(p0 / total, 4),
            "p1": round(p1 / total, 4),
            "error_rate": round(err_rate, 4),
        }

    effective_error_rate = float(np.mean(error_rates))
    calibration_data = {
        "backend_name": backend.name,
        "calibration_date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "shots_per_state": shots,
        "effective_error_rate": round(effective_error_rate, 4),
        "fidelity": round(1.0 - effective_error_rate, 4),
        "confusion_matrix": confusion_matrix,
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(calibration_data, f, indent=2)

    return calibration_data


class IBMFakeTeleportationBackend:
    name = "ibm_fake"

    def __init__(self, backend_name: Optional[str] = None, mode: str = "calibrated", shots: int = 5000):
        self.backend = get_fake_backend(backend_name)
        self.backend_name = self.backend.name
        self.mode = mode.lower()
        self.calibration_data = calibrate_ibm_backend(backend_name=self.backend_name, shots=shots)
        self.effective_error_rate = self.calibration_data["effective_error_rate"]
        self.calibration_date = self.calibration_data["calibration_date"]

        if self.mode == "full":
            from qiskit_aer import AerSimulator
            from qiskit_aer.noise import NoiseModel
            self._noise_model = NoiseModel.from_backend(self.backend)
            self._sim = AerSimulator(noise_model=self._noise_model)
        else:
            self._noise_model = None
            self._sim = None

    def run(self, jobs: Sequence[TeleportJob], rng: np.random.Generator) -> List[TeleportOutcome]:
        if not jobs:
            return []

        if self.mode == "full":
            from qiskit import transpile
            circuits = [build_deferred_teleportation_circuit(j) for j in jobs]
            seed_sim = int(rng.integers(0, 2**31 - 1))
            seed_tr = int(rng.integers(0, 2**31 - 1))
            tcircs = [transpile(qc, backend=self.backend, seed_transpiler=seed_tr) for qc in circuits]
            result = self._sim.run(tcircs, shots=1, memory=True, seed_simulator=seed_sim).result()
            outcomes = []
            for i, job in enumerate(jobs):
                bits = result.get_memory(i)[0][::-1]
                eve_bit = int(bits[3]) if (job.eve_basis is not None and len(bits) > 3) else None
                outcomes.append(TeleportOutcome(
                    outcome=int(bits[2]),
                    m1=int(bits[0]),
                    m2=int(bits[1]),
                    eve_outcome=eve_bit,
                ))
            return outcomes

        # CALIBRATED mode: fast effective channel matching calibration confusion matrix
        outcomes = []
        cm = self.calibration_data["confusion_matrix"]
        state_keys = {(0, 0): "0", (1, 0): "1", (0, 1): "+", (1, 1): "-"}

        for job in jobs:
            # Check intercept-resend, noise Pauli, damping noise, or readout error if present
            if (
                job.eve_basis is not None
                or job.noise_pauli is not None
                or job.damping_gamma > 0.0
                or job.phase_damping_gamma > 0.0
                or job.readout_p01 > 0.0
                or job.readout_p10 > 0.0
            ):
                # Fallback to statevector simulation for active attack interception or direct noise
                from .teleportation import _teleport_statevector
                outcomes.append(_teleport_statevector(job, rng))
                continue

            # Matched basis measurement
            key = state_keys.get((job.bit, job.basis), "0")
            p_err = cm[key]["error_rate"]
            m1 = int(rng.integers(0, 2))
            m2 = int(rng.integers(0, 2))

            if job.basis == job.meas_basis:
                flipped = rng.random() < p_err
                outcome = (1 - job.bit) if flipped else job.bit
            else:
                outcome = int(rng.integers(0, 2))

            outcomes.append(TeleportOutcome(outcome=outcome, m1=m1, m2=m2, eve_outcome=None))
        return outcomes


def make_backend(name: str = "qiskit", mode: str = "calibrated"):
    if name == "qiskit":
        return QiskitTeleportationBackend()
    if name == "statevector":
        return StatevectorTeleportationBackend()
    if name in ("ibm_fake", "ibm_fake_calibrated"):
        return IBMFakeTeleportationBackend(mode="calibrated")
    if name == "ibm_fake_full":
        return IBMFakeTeleportationBackend(mode="full")
    raise ValueError(f"Unknown teleportation backend: {name}")

