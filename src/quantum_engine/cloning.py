"""
Quantum 1->2 state cloning circuits using Qiskit.

Two symmetric 1->2 cloners operating on the token + 2 ancillas:
1. Universal symmetric 1->2 (Buzek-Hillery):
   Theoretical fidelity F = 5/6 (~0.8333, error rate 1/6 ~ 16.67%) for any input state.
2. Phase-covariant BB84 (Bruss-Macchiavello):
   Theoretical fidelity F = 1/2 * (1 + 1/sqrt(2)) (~0.8536, error rate ~14.64%)
   specifically optimized for BB84 states {|0>, |1>, |+>, |->}.

Architecture:
- Input token qubit: q0 (carries the state to clone)
- Clone 1 (Eve retains): q0
- Clone 2 (forwarded to receiver): q1
- Ancilla: q2
Both q1 and q2 start in state |0>.
"""
import math
from typing import Tuple, Dict, Any, Optional
import numpy as np

from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector, DensityMatrix, state_fidelity, partial_trace

# Theoretical constants
UNIVERSAL_FIDELITY = 5.0 / 6.0
UNIVERSAL_ERROR = 1.0 / 6.0

PHASE_COVARIANT_FIDELITY = 0.5 * (1.0 + 1.0 / math.sqrt(2.0))
PHASE_COVARIANT_ERROR = 1.0 - PHASE_COVARIANT_FIDELITY


def build_buzek_hillery_unitary() -> np.ndarray:
    """
    3-qubit unitary matrix implementing the universal symmetric 1->2 Buzek-Hillery cloner.
    Basis ordering: q0 + 2*q1 + 4*q2 (|q2 q1 q0>).
    Inputs with q1=0, q2=0:
      |0,0,0> -> sqrt(2/3)|0,0,0> + sqrt(1/6)|0,1,1> + sqrt(1/6)|1,0,1>
      |1,0,0> -> sqrt(2/3)|1,1,1> + sqrt(1/6)|0,1,0> + sqrt(1/6)|1,0,0>
    """
    # Columns for |0,0,0> (index 0) and |1,0,0> (index 1)
    v0 = np.zeros(8, dtype=complex)
    v0[0] = math.sqrt(2.0 / 3.0)
    v0[6] = math.sqrt(1.0 / 6.0)  # q0=0, q1=1, q2=1 -> 6
    v0[5] = math.sqrt(1.0 / 6.0)  # q0=1, q1=0, q2=1 -> 5

    v1 = np.zeros(8, dtype=complex)
    v1[7] = math.sqrt(2.0 / 3.0)  # q0=1, q1=1, q2=1 -> 7
    v1[2] = math.sqrt(1.0 / 6.0)  # q0=0, q1=1, q2=0 -> 2
    v1[1] = math.sqrt(1.0 / 6.0)  # q0=1, q1=0, q2=0 -> 1

    # Complete into an 8x8 unitary via Gram-Schmidt
    cols = [v0, v1]
    # Standard basis vectors to complete the space
    for i in range(8):
        e = np.zeros(8, dtype=complex)
        e[i] = 1.0
        # Project out existing cols
        for c in cols:
            e -= np.vdot(c, e) * c
        norm = np.linalg.norm(e)
        if norm > 1e-10:
            cols.append(e / norm)
        if len(cols) == 8:
            break

    U = np.column_stack(cols)
    return U


def build_phase_covariant_bb84_unitary() -> np.ndarray:
    """
    3-qubit unitary matrix implementing the symmetric 1->2 Phase-Covariant cloner
    for equatorial / BB84 states.
    For states on the equator of the Bloch sphere (|0> + e^{i phi}|1>)/sqrt(2),
    or BB84 states rotated appropriately.
    For the BB84 meridian (XZ plane: |0>, |1>, |+>, |->):
    We rotate the standard phase-covariant transformation by Ry(pi/4) or apply it
    in the meridian basis.
    Let's construct the unitary such that for |0>, |1>, |+>, |->,
    F = 1/2 * (1 + 1/sqrt(2)) ~ 0.85355 on both clone qubits.
    """
    # In standard phase-covariant cloner (Bruß-Macchiavello):
    # |0,0,0> -> 1/sqrt(2)|0,0,0> + 1/2(|0,1,1> + |1,0,1>)
    # |1,0,0> -> 1/sqrt(2)|1,1,1> + 1/2(|0,1,0> + |1,0,0>)
    # For this standard mapping, states on the XY equator (|0> + e^{i phi}|1>)/sqrt(2)
    # achieve fidelity 0.85355.
    # To achieve 0.85355 on the BB84 states (Z and X bases: |0>, |1>, |+>, |->),
    # notice the BB84 states lie on the XZ circle (phi = 0 or pi, theta arbitrary).
    # A rotation Ry(pi/2) maps the Z axis to X axis and X to -Z.
    # The optimal cloner for the XZ plane is obtained by rotating the cloner by
    # a basis transformation that maps XZ to XY:
    # A single-qubit transformation R that maps:
    # |0> -> (|0> + i|1>)/sqrt(2), |1> -> (|0> - i|1>)/sqrt(2) (equatorial),
    # or more simply R = exp(-i pi/4 X) = (I - i X)/sqrt(2).
    # Under R:
    # |0> -> (|0> - i|1>)/sqrt(2)  (on the XY equator!)
    # |1> -> (-i|0> + |1>)/sqrt(2) = -i(|0> + i|1>)/sqrt(2) (on the XY equator!)
    # |+> = (|0>+|1>)/sqrt(2) -> (1-i)/2 |0> + (1-i)/2 |1> = (1-i)/sqrt(2) |+> (on the equator!)
    # |-> = (|0>-|1>)/sqrt(2) -> (1+i)/2 |0> - (1+i)/2 |1> = (1+i)/sqrt(2) |-> (on the equator!)
    # Every one of the 4 BB84 states maps to the equator under R!
    # Therefore, applying R on input and R^dagger on both output clones produces
    # EXACTLY the optimal phase-covariant fidelity 0.85355 for all 4 BB84 states!

    # Standard equatorial Bruss unitary:
    u0 = np.zeros(8, dtype=complex)
    u0[0] = 1.0 / math.sqrt(2.0)
    u0[6] = 0.5  # |0,1,1>
    u0[5] = 0.5  # |1,0,1>

    u1 = np.zeros(8, dtype=complex)
    u1[7] = 1.0 / math.sqrt(2.0)
    u1[2] = 0.5  # |0,1,0>
    u1[1] = 0.5  # |1,0,0>

    cols = [u0, u1]
    for i in range(8):
        e = np.zeros(8, dtype=complex)
        e[i] = 1.0
        for c in cols:
            e -= np.vdot(c, e) * c
        norm = np.linalg.norm(e)
        if norm > 1e-10:
            cols.append(e / norm)
        if len(cols) == 8:
            break

    U_xy = np.column_stack(cols)

    # R = exp(-i * pi/4 * X) = [[1, -1j], [-1j, 1]] / sqrt(2)
    R = np.array([[1.0, -1j], [-1j, 1.0]], dtype=complex) / math.sqrt(2.0)
    R_dag = R.conj().T

    # On 3 qubits:
    # Input has R on q0 (the state to be cloned), and identity on q1, q2
    # Output has R_dag on q0 (clone 1) and q1 (clone 2), identity on q2
    R_in = np.kron(np.eye(4, dtype=complex), R)  # q2 (x) q1 (x) R_q0
    R_out_dag = np.kron(np.kron(np.eye(2, dtype=complex), R_dag), R_dag)

    U_bb84 = R_out_dag @ U_xy @ R_in
    return U_bb84


_BH_UNITARY = build_buzek_hillery_unitary()
_PC_UNITARY = build_phase_covariant_bb84_unitary()


def get_cloner_unitary(cloner_type: str = "universal") -> np.ndarray:
    """Return the 8x8 unitary for the chosen cloner type."""
    ctype = cloner_type.lower()
    if ctype in ("universal", "buzek_hillery", "bh"):
        return _BH_UNITARY
    elif ctype in ("phase_covariant", "bb84", "pc"):
        return _PC_UNITARY
    else:
        raise ValueError(f"Unknown cloner_type: {cloner_type}. Expected 'universal' or 'phase_covariant'.")


def build_cloning_circuit(bit: int, basis: int, cloner_type: str = "universal") -> QuantumCircuit:
    """
    Build a 3-qubit Qiskit QuantumCircuit that prepares the BB84 state on q0,
    attaches 2 ancillas on q1, q2, and applies the cloner unitary.
    q0: Clone 1 (Eve)
    q1: Clone 2 (forwarded to receiver)
    q2: Machine ancilla
    """
    from qiskit.circuit.library import UnitaryGate
    qc = QuantumCircuit(3)
    # Prepare input state on q0
    if bit:
        qc.x(0)
    if basis:
        qc.h(0)

    # Apply 3-qubit cloner unitary
    U = get_cloner_unitary(cloner_type)
    gate = UnitaryGate(U, label=f"Clone_{cloner_type[:4]}")
    qc.append(gate, [0, 1, 2])
    return qc


def measure_cloner_fidelity(bit: int, basis: int, cloner_type: str = "universal") -> Tuple[float, float]:
    """
    Analytically compute the fidelities of Clone 1 (q0) and Clone 2 (q1)
    relative to the ideal input state.
    """
    qc = build_cloning_circuit(bit, basis, cloner_type)
    sv = Statevector.from_instruction(qc)
    dm = DensityMatrix(sv)

    # Ideal target statevector on 1 qubit
    qc_ideal = QuantumCircuit(1)
    if bit:
        qc_ideal.x(0)
    if basis:
        qc_ideal.h(0)
    psi_ideal = Statevector.from_instruction(qc_ideal)

    # Trace out q2 and q1 to get rho(q0) [Clone 1]
    rho_q0 = partial_trace(dm, [1, 2])
    # Trace out q2 and q0 to get rho(q1) [Clone 2]
    rho_q1 = partial_trace(dm, [0, 2])

    f0 = state_fidelity(psi_ideal, rho_q0)
    f1 = state_fidelity(psi_ideal, rho_q1)
    return float(f0), float(f1)


def simulate_eve_cloning_step(
    bit: int,
    basis: int,
    meas_basis_receiver: int,
    cloner_type: str = "universal",
    rng: Optional[np.random.Generator] = None,
) -> Dict[str, Any]:
    """
    Simulate a single token intercepted by Eve using a 1->2 cloner.
    Eve clones the token into Clone 1 (Eve) and Clone 2 (forwarded to receiver).
    Eve measures Clone 1 in a chosen basis (random Z or X basis) to extract signature info.
    Receiver measures Clone 2 in meas_basis_receiver.

    Returns:
        eve_meas_basis: basis Eve measured in
        eve_outcome: Eve's measurement bit on Clone 1
        receiver_outcome: Receiver's measurement bit on Clone 2
        is_clone_mismatch: whether receiver's outcome differs from prepared bit when bases match
    """
    if rng is None:
        rng = np.random.default_rng()

    eve_basis = int(rng.integers(0, 2))
    qc = build_cloning_circuit(bit, basis, cloner_type)

    # Eve measures q0 in eve_basis
    # Receiver measures q1 in meas_basis_receiver
    qc_meas = qc.copy()
    from qiskit import ClassicalRegister
    cr = ClassicalRegister(2, "c")
    qc_meas.add_register(cr)

    if eve_basis:
        qc_meas.h(0)
    qc_meas.measure(0, cr[0])  # Eve outcome in cr[0]

    if meas_basis_receiver:
        qc_meas.h(1)
    qc_meas.measure(1, cr[1])  # Receiver outcome in cr[1]

    sv = Statevector.from_instruction(qc)
    # Compute probabilities of the 4 outcomes: (eve, receiver)
    # Basis transformations on the statevector before standard measurement
    sv_meas = sv.copy()
    if eve_basis:
        from qiskit.circuit.library import HGate
        sv_meas = sv_meas.evolve(HGate(), [0])
    if meas_basis_receiver:
        from qiskit.circuit.library import HGate
        sv_meas = sv_meas.evolve(HGate(), [1])

    probs = sv_meas.probabilities([0, 1])  # order: (q0, q1)
    # outcome index: q0 + 2*q1
    outcome_idx = rng.choice(4, p=probs)
    eve_outcome = outcome_idx & 1
    receiver_outcome = (outcome_idx >> 1) & 1

    is_mismatch = (meas_basis_receiver == basis) and (receiver_outcome != bit)

    return {
        "eve_basis": eve_basis,
        "eve_outcome": eve_outcome,
        "receiver_outcome": receiver_outcome,
        "is_mismatch": is_mismatch,
    }
