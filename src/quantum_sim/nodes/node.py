from typing import Optional
import numpy as np
from qiskit import QuantumCircuit
from quantum_sim.core.circuit import prepare_bb84_state, add_bb84_measurement


class Node:
    def __init__(self, name: str):
        self.name = name
        self.bits: Optional[np.ndarray] = None
        self.bases: Optional[np.ndarray] = None

    def prepare_bb84_transmission(
        self, n_bits: int, rng: Optional[np.random.Generator] = None
    ) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        self.bits = rng.integers(0, 2, size=n_bits)
        self.bases = rng.integers(0, 2, size=n_bits)
        return prepare_bb84_state(self.bits, self.bases)

    def apply_bb84_measurement(
        self,
        circuit: QuantumCircuit,
        n_bits: Optional[int] = None,
        rng: Optional[np.random.Generator] = None
    ) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        count = n_bits if n_bits is not None else circuit.num_qubits
        self.bases = rng.integers(0, 2, size=count)
        return add_bb84_measurement(circuit, self.bases)
