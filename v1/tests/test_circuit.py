import numpy as np
from quantum_sim.core.circuit import prepare_bb84_state, add_bb84_measurement


def test_prepare_bb84_state():
    bits = np.array([0, 1, 0, 1])
    bases = np.array([0, 0, 1, 1])
    qc = prepare_bb84_state(bits, bases)
    assert qc.num_qubits == 4
    assert qc.num_clbits == 4


def test_add_bb84_measurement():
    bits = np.array([0, 1])
    bases = np.array([0, 1])
    qc = prepare_bb84_state(bits, bases)
    measured_qc = add_bb84_measurement(qc, bases)
    assert measured_qc.num_qubits == 2
