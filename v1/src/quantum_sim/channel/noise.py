from abc import ABC, abstractmethod
import numpy as np
from qiskit import QuantumCircuit


class BaseNoise(ABC):
    @abstractmethod
    def apply(self, circuit: QuantumCircuit, rng: np.random.Generator = None) -> QuantumCircuit:
        pass


class BitFlipNoise(BaseNoise):
    def __init__(self, p_error: float = 0.05):
        self.p_error = float(p_error)

    def apply(self, circuit: QuantumCircuit, rng: np.random.Generator = None) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        noisy_qc = circuit.copy()
        n_qubits = circuit.num_qubits

        for i in range(n_qubits):
            if rng.random() <= self.p_error:
                noisy_qc.x(i)

        return noisy_qc


class PhaseFlipNoise(BaseNoise):
    def __init__(self, p_error: float = 0.05):
        self.p_error = float(p_error)

    def apply(self, circuit: QuantumCircuit, rng: np.random.Generator = None) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        noisy_qc = circuit.copy()
        n_qubits = circuit.num_qubits

        for i in range(n_qubits):
            if rng.random() <= self.p_error:
                noisy_qc.z(i)

        return noisy_qc


class DepolarizingNoise(BaseNoise):
    def __init__(self, p_error: float = 0.05):
        self.p_error = float(p_error)

    def apply(self, circuit: QuantumCircuit, rng: np.random.Generator = None) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        noisy_qc = circuit.copy()
        n_qubits = circuit.num_qubits

        for i in range(n_qubits):
            if rng.random() <= self.p_error:
                # Depolarizing channel: replace state with maximally mixed state.
                # In terms of Pauli operators, apply X, Y, or Z with equal probability (p_error / 3 each).
                operator = rng.choice(["X", "Y", "Z"])
                if operator == "X":
                    noisy_qc.x(i)
                elif operator == "Y":
                    noisy_qc.y(i)
                elif operator == "Z":
                    noisy_qc.z(i)

        return noisy_qc
