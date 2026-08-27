from typing import List, Optional
import numpy as np
from qiskit import QuantumCircuit
from quantum_sim.channel.attacks import BaseAttack


class QuantumChannel:
    def __init__(self, attacks: Optional[List[BaseAttack]] = None):
        self.attacks = attacks or []

    def add_attack(self, attack: BaseAttack):
        self.attacks.append(attack)

    def transmit(self, circuit: QuantumCircuit, rng: Optional[np.random.Generator] = None) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        current_circuit = circuit
        for attack in self.attacks:
            current_circuit = attack.apply(current_circuit, rng=rng)
        
        return current_circuit
