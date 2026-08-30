import numpy as np
from qiskit import QuantumCircuit, ClassicalRegister, QuantumRegister


def prepare_bb84_state(bits: np.ndarray, bases: np.ndarray) -> QuantumCircuit:
    """Prepares single-qubit BB84 states for given bits and bases."""
    n = len(bits)
    qc = QuantumCircuit(n, n)
    for i in range(n):
        if bits[i] == 1:
            qc.x(i)
        if bases[i] == 1:
            qc.h(i)
    return qc


def add_bb84_measurement(qc: QuantumCircuit, bases: np.ndarray) -> QuantumCircuit:
    """Appends measurement in Z (basis=0) or X (basis=1) to an existing circuit."""
    n = len(bases)
    measured_qc = qc.copy()
    for i in range(n):
        if bases[i] == 1:
            measured_qc.h(i)
        measured_qc.measure(i, i)
    return measured_qc


def create_bell_pair(qc: QuantumCircuit, q0: int, q1: int) -> None:
    """
    Creates an entangled Bell pair |Phi+> = (|00> + |11>) / sqrt(2)
    between qubits q0 and q1 in-place.
    """
    qc.h(q0)
    qc.cx(q0, q1)


def build_teleportation_step_circuit(
    state_bit: int,
    state_basis: int,
    measure_basis: int = 0
) -> QuantumCircuit:
    """
    Constructs a complete single-qubit teleportation verification circuit:
    - Qubit 0: Input signature state |psi(bit, basis)>
    - Qubit 1: Alice's half of entangled Bell pair
    - Qubit 2: Receiver's half of entangled Bell pair
    
    Workflow:
    1. Prepare Bell pair on (q1, q2)
    2. Prepare signature state |psi> on q0
    3. Alice performs Bell State Measurement (BSM) on (q0, q1): CNOT(q0, q1) -> H(q0) -> measure
    4. Classical feed-forward Pauli corrections on q2:
       - If q1 measurement m2 == 1: apply X to q2
       - If q0 measurement m1 == 1: apply Z to q2
    5. Receiver measures q2 in the verification basis (0 = Z, 1 = X).
    """
    qr = QuantumRegister(3, name="q")
    cr_bsm = ClassicalRegister(2, name="bsm") # c[0]=m1 (from q0), c[1]=m2 (from q1)
    cr_meas = ClassicalRegister(1, name="out") # c[2]=receiver measurement
    
    qc = QuantumCircuit(qr, cr_bsm, cr_meas)
    
    # 1. Bell pair generation between Alice (q1) and Receiver (q2)
    create_bell_pair(qc, 1, 2)
    qc.barrier()
    
    # 2. State preparation of signature qubit q0
    if state_bit == 1:
        qc.x(0)
    if state_basis == 1:
        qc.h(0)
    qc.barrier()
    
    # 3. Bell State Measurement (BSM) by Alice
    qc.cx(0, 1)
    qc.h(0)
    qc.measure(0, cr_bsm[0]) # m1 (Z-correction syndrome)
    qc.measure(1, cr_bsm[1]) # m2 (X-correction syndrome)
    qc.barrier()
    
    # 4. Pauli feed-forward corrections on Receiver's qubit q2
    # In Qiskit, conditional execution or dynamic circuits apply corrections:
    # If m2 == 1 -> X(q2); if m1 == 1 -> Z(q2)
    qc.cx(1, 2) # X correction controlled by q1 pre-measurement / syndrome
    qc.cz(0, 2) # Z correction controlled by q0 pre-measurement / syndrome
    qc.barrier()
    
    # 5. Receiver projective measurement in desired basis
    if measure_basis == 1:
        qc.h(2)
    qc.measure(2, cr_meas[0])
    
    return qc

