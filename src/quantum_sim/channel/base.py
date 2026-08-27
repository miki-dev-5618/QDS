from typing import List, Optional
import numpy as np
from qiskit import QuantumCircuit
from quantum_sim.channel.attacks import BaseAttack
from quantum_sim.channel.noise import BaseNoise


class QuantumChannel:
    def __init__(
        self,
        attacks: Optional[List[BaseAttack]] = None,
        noises: Optional[List[BaseNoise]] = None
    ):
        self.attacks = attacks or []
        self.noises = noises or []

    def add_attack(self, attack: BaseAttack):
        self.attacks.append(attack)

    def add_noise(self, noise: BaseNoise):
        self.noises.append(noise)

    def transmit(self, circuit: QuantumCircuit, rng: Optional[np.random.Generator] = None) -> QuantumCircuit:
        if rng is None:
            rng = np.random.default_rng()

        current_circuit = circuit
        
        # Apply noise models
        for noise in self.noises:
            current_circuit = noise.apply(current_circuit, rng=rng)

        # Apply security/attack models
        for attack in self.attacks:
            current_circuit = attack.apply(current_circuit, rng=rng)
        
        return current_circuit

