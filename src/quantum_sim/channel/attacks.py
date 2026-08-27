from abc import ABC, abstractmethod
import numpy as np
from qiskit import QuantumCircuit, ClassicalRegister


class BaseAttack(ABC):
    @abstractmethod
    def apply(self, circuit: QuantumCircuit, rng: np.random.Generator = None) -> QuantumCircuit:
        pass


class InterceptResendAttack(BaseAttack):
    def __init__(self, p_intercept: float = 1.0):
        self.p_intercept = float(p_intercept)

    def apply(self, circuit: QuantumCircuit, rng: np.random.Generator = None) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        attacked_qc = circuit.copy()
        n_qubits = circuit.num_qubits
        
        eve_reg = ClassicalRegister(n_qubits, name="eve")
        attacked_qc.add_register(eve_reg)

        for i in range(n_qubits):
            if rng.random() <= self.p_intercept:
                eve_basis = int(rng.integers(0, 2))
                if eve_basis == 1:
                    attacked_qc.h(i)
                attacked_qc.measure(i, eve_reg[i])
                if eve_basis == 1:
                    attacked_qc.h(i)

        return attacked_qc
