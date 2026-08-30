from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
import numpy as np
from qiskit_aer import AerSimulator
from qiskit import QuantumCircuit

from quantum_sim.protocols.base import BaseProtocol
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.core.circuit import build_teleportation_step_circuit
from quantum_sim.utils.security_analysis import QDSSecurityBounds, SecurityCertificate


@dataclass
class TeleportationQDSResult:
    n_bits: int
    alice_signatures: Dict[int, List[Tuple[int, int]]] # k -> list of (bit, basis)
    bob_actions: List[str] # 'K' or 'F' for each position
    charlie_actions: List[str] # 'K' or 'F' for each position
    bob_teleportation_syndromes: List[Tuple[int, int]] # (m1, m2) per position
    charlie_teleportation_syndromes: List[Tuple[int, int]] # (m1, m2) per position
    bob_received_count: int
    charlie_received_count: int
    bob_aborted: bool
    charlie_aborted: bool
    bob_eliminated: List[List[str]] # position -> list of eliminated states
    charlie_eliminated: List[List[str]] # position -> list of eliminated states


class TeleportationQDSProtocol(BaseProtocol):
    """
    Teleportation-Based Quantum Digital Signature (QDS) Protocol.
    
    Combines:
    1. Bell-state entanglement distribution (|Phi+>).
    2. Quantum Teleportation of signature tokens with Bell State Measurements (BSM).
    3. Feed-forward classical Pauli correction operations (X^{m2} Z^{m1}).
    4. Classical/Quantum symmetrisation (Keep/Forward) for non-repudiation.
    5. Pauli projective measurements for deterministic signature verification.
    6. Formal Information-Theoretic Security Certificate evaluation via Chernoff-Hoeffding bounds.
    """
    def __init__(
        self,
        alice: Node,
        bob: Node,
        charlie: Node,
        channel: QuantumChannel,
        shots: int = 1,
        abort_threshold_pct: float = 50.0,
        baseline_channel_noise: float = 0.02
    ):
        self.alice = alice
        self.bob = bob
        self.charlie = charlie
        self.channel = channel
        self.shots = shots
        self.abort_threshold_pct = abort_threshold_pct
        self.baseline_channel_noise = baseline_channel_noise

        # Internal protocol state
        self.n_bits = 0
        self.alice_sigs = {}
        self.bob_actions = []
        self.charlie_actions = []
        self.bob_held = []
        self.charlie_held = []
        self.bob_syndromes = []
        self.charlie_syndromes = []
        self.bob_eliminated = []
        self.charlie_eliminated = []

    def setup(self, n_bits: int, rng: Optional[np.random.Generator] = None) -> None:
        """
        Step 1: Alice generates random private signature sequences for messages k=0 and k=1.
        Each token is a Pauli eigenstate characterized by (bit, basis):
        (0, 0) -> |0>, (1, 0) -> |1>, (0, 1) -> |+>, (1, 1) -> |->
        """
        if rng is None:
            rng = np.random.default_rng()

        self.n_bits = n_bits
        self.alice_sigs = {
            0: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))],
            1: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
        }

    def transmit(self, rng: Optional[np.random.Generator] = None) -> None:
        """
        Step 2: Symmetrisation decision and distribution via Quantum Teleportation.
        Alice teleports copies of her signature tokens to Bob and Charlie.
        """
        if rng is None:
            rng = np.random.default_rng()

        self.bob_actions = [str(rng.choice(['K', 'F'])) for _ in range(self.n_bits)]
        self.charlie_actions = [str(rng.choice(['K', 'F'])) for _ in range(self.n_bits)]

        self.bob_held = []
        self.charlie_held = []

        for i in range(self.n_bits):
            b_held = []
            c_held = []

            # Bob starts with copy 1, Charlie with copy 2
            if self.bob_actions[i] == 'K':
                b_held.append('Bob Original (Teleported)')
            else:
                c_held.append('Bob Forwarded (Teleported)')

            if self.charlie_actions[i] == 'K':
                c_held.append('Charlie Original (Teleported)')
            else:
                b_held.append('Charlie Forwarded (Teleported)')

            self.bob_held.append(b_held)
            self.charlie_held.append(c_held)

    def measure(self, rng: Optional[np.random.Generator] = None) -> None:
        """
        Step 3: Execute quantum teleportation circuits, BSM, Pauli corrections,
        and receiver projective measurements for orthogonal state elimination.
        """
        if rng is None:
            rng = np.random.default_rng()

        backend = AerSimulator()
        self.bob_eliminated = [[] for _ in range(self.n_bits)]
        self.charlie_eliminated = [[] for _ in range(self.n_bits)]
        self.bob_syndromes = []
        self.charlie_syndromes = []

        active_sig = self.alice_sigs[0]

        for i in range(self.n_bits):
            bit, basis = active_sig[i]

            # 1. Teleport copy to Bob and record BSM syndromes & elimination
            bob_copies = len(self.bob_held[i])
            if bob_copies == 1:
                chosen_basis = int(rng.integers(0, 2))
                elim, syn = self._execute_teleportation_step(bit, basis, chosen_basis, backend, rng)
                self.bob_eliminated[i].append(elim)
                self.bob_syndromes.append(syn)
            elif bob_copies == 2:
                elim1, syn1 = self._execute_teleportation_step(bit, basis, 0, backend, rng)
                elim2, _ = self._execute_teleportation_step(bit, basis, 1, backend, rng)
                self.bob_eliminated[i].extend([elim1, elim2])
                self.bob_syndromes.append(syn1)
            else:
                self.bob_syndromes.append((0, 0))

            # 2. Teleport copy to Charlie and record BSM syndromes & elimination
            charlie_copies = len(self.charlie_held[i])
            if charlie_copies == 1:
                chosen_basis = int(rng.integers(0, 2))
                elim, syn = self._execute_teleportation_step(bit, basis, chosen_basis, backend, rng)
                self.charlie_eliminated[i].append(elim)
                self.charlie_syndromes.append(syn)
            elif charlie_copies == 2:
                elim1, syn1 = self._execute_teleportation_step(bit, basis, 0, backend, rng)
                elim2, _ = self._execute_teleportation_step(bit, basis, 1, backend, rng)
                self.charlie_eliminated[i].extend([elim1, elim2])
                self.charlie_syndromes.append(syn1)
            else:
                self.charlie_syndromes.append((0, 0))

    def _execute_teleportation_step(
        self,
        src_bit: int,
        src_basis: int,
        meas_basis: int,
        backend: AerSimulator,
        rng: np.random.Generator
    ) -> Tuple[str, Tuple[int, int]]:
        """
        Runs the 3-qubit Teleportation circuit with Pauli feed-forward correction
        and projective measurement.
        """
        qc = build_teleportation_step_circuit(
            state_bit=src_bit,
            state_basis=src_basis,
            measure_basis=meas_basis
        )
        
        # Channel noise / attack transit if configured
        tx_qc = self.channel.transmit(qc, rng=rng)
        
        result = backend.run(tx_qc, shots=self.shots).result()
        counts = result.get_counts()
        
        # Parse output string (e.g. "out bsm" format in Qiskit counts: "meas m2 m1" -> "r m2m1")
        most_frequent = max(counts, key=counts.get).replace(" ", "")
        
        # Output layout: bit 0 is receiver measurement, bits 1,2 are BSM outcomes
        out_bit = int(most_frequent[0])
        m2 = int(most_frequent[1]) if len(most_frequent) > 1 else 0
        m1 = int(most_frequent[2]) if len(most_frequent) > 2 else 0

        # State elimination rule based on receiver's measurement outcome
        if meas_basis == 0: # Z basis
            elim_symbol = '|1⟩' if out_bit == 0 else '|0⟩'
        else: # X basis
            elim_symbol = '|−⟩' if out_bit == 0 else '|+⟩'

        return elim_symbol, (m1, m2)

    def process(self, rng: Optional[np.random.Generator] = None) -> TeleportationQDSResult:
        bob_rcv = sum(1 for h in self.bob_held if len(h) > 0)
        charlie_rcv = sum(1 for h in self.charlie_held if len(h) > 0)

        min_allowed = (self.abort_threshold_pct / 100.0) * self.n_bits
        bob_aborted = bob_rcv < min_allowed
        charlie_aborted = charlie_rcv < min_allowed

        return TeleportationQDSResult(
            n_bits=self.n_bits,
            alice_signatures=self.alice_sigs,
            bob_actions=self.bob_actions,
            charlie_actions=self.charlie_actions,
            bob_teleportation_syndromes=self.bob_syndromes,
            charlie_teleportation_syndromes=self.charlie_syndromes,
            bob_received_count=bob_rcv,
            charlie_received_count=charlie_rcv,
            bob_aborted=bob_aborted,
            charlie_aborted=charlie_aborted,
            bob_eliminated=self.bob_eliminated,
            charlie_eliminated=self.charlie_eliminated
        )

    def run(self, n_bits: int, rng: Optional[np.random.Generator] = None) -> TeleportationQDSResult:
        if rng is None:
            rng = np.random.default_rng()

        self.setup(n_bits, rng)
        self.transmit(rng)
        self.measure(rng)
        return self.process(rng)

    def verify_signature(
        self,
        k: int,
        proposed_sig: List[Tuple[int, int]],
        recipient: str = 'bob'
    ) -> Tuple[bool, int, int, SecurityCertificate]:
        """
        Verifies Alice's signature for message k.
        Returns:
            (is_valid, mismatch_count, total_checked, security_certificate)
        """
        elim_list = self.bob_eliminated if recipient == 'bob' else self.charlie_eliminated
        held_list = self.bob_held if recipient == 'bob' else self.charlie_held

        mismatches = 0
        total_checked = 0

        for i in range(self.n_bits):
            if len(held_list[i]) > 0:
                total_checked += 1
                bit, basis = proposed_sig[i]
                if basis == 0:
                    state_symbol = '|0⟩' if bit == 0 else '|1⟩'
                else:
                    state_symbol = '|+⟩' if bit == 0 else '|−⟩'

                # Contradiction check: if proposed state was eliminated by measurement
                if state_symbol in elim_list[i]:
                    mismatches += 1

        # Generate formal Information-Theoretic Security Certificate
        cert = QDSSecurityBounds.generate_security_certificate(
            signature_length=self.n_bits,
            channel_error_rate=self.baseline_channel_noise,
            mismatches=mismatches,
            total_checked=total_checked
        )

        is_valid = cert.is_securely_accepted
        return is_valid, mismatches, total_checked, cert
