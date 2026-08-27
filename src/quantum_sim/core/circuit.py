import numpy as np
from qiskit import QuantumCircuit


def prepare_bb84_state(bits: np.ndarray, bases: np.ndarray) -> QuantumCircuit:
    n = len(bits)
    qc = QuantumCircuit(n, n)
    for i in range(n):
        if bits[i] == 1:
            qc.x(i)
        if bases[i] == 1:
            qc.h(i)
    return qc


def add_bb84_measurement(qc: QuantumCircuit, bases: np.ndarray) -> QuantumCircuit:
    n = len(bases)
    measured_qc = qc.copy()
    for i in range(n):
        if bases[i] == 1:
            measured_qc.h(i)
        measured_qc.measure(i, i)
    return measured_qc
