from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
import numpy as np
from qiskit_aer import AerSimulator
from qiskit import QuantumCircuit

from quantum_sim.protocols.base import BaseProtocol
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.core.circuit import prepare_bb84_state, add_bb84_measurement


@dataclass
class QDSResult:
    n_bits: int
    alice_signatures: Dict[int, List[Tuple[int, int]]] # k -> list of (bit, basis)
    bob_actions: List[str] # 'K' or 'F' for each position
    charlie_actions: List[str] # 'K' or 'F' for each position
    bob_received_count: int
    charlie_received_count: int
    bob_aborted: bool
    charlie_aborted: bool
    bob_eliminated: List[List[str]] # position -> list of eliminated states
    charlie_eliminated: List[List[str]] # position -> list of eliminated states


class QDSProtocol(BaseProtocol):
    def __init__(
        self,
        alice: Node,
        bob: Node,
        charlie: Node,
        channel: QuantumChannel,
        shots: int = 1,
        abort_threshold_pct: float = 50.0
    ):
        self.alice = alice
        self.bob = bob
        self.charlie = charlie
        self.channel = channel
        self.shots = shots
        self.abort_threshold_pct = abort_threshold_pct
        
        # Internal state
        self.n_bits = 0
        self.alice_sigs = {}
        self.bob_actions = []
        self.charlie_actions = []
        self.bob_held = []
        self.charlie_held = []
        self.bob_eliminated = []
        self.charlie_eliminated = []

    def setup(self, n_bits: int, rng: Optional[np.random.Generator] = None) -> None:
        if rng is None:
            rng = np.random.default_rng()
        
        self.n_bits = n_bits
        
        # Alice generates random signature states for both message k=0 and k=1
        # represented as a list of (bit, basis) pairs
        self.alice_sigs = {
            0: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))],
            1: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
        }

    def transmit(self, rng: Optional[np.random.Generator] = None) -> None:
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
                b_held.append('Bob Original')
            else:
                c_held.append('Bob Forwarded')

            if self.charlie_actions[i] == 'K':
                c_held.append('Charlie Original')
            else:
                b_held.append('Charlie Forwarded')

            self.bob_held.append(b_held)
            self.charlie_held.append(c_held)

    def measure(self, rng: Optional[np.random.Generator] = None) -> None:
        if rng is None:
            rng = np.random.default_rng()

        backend = AerSimulator()
        self.bob_eliminated = [[] for _ in range(self.n_bits)]
        self.charlie_eliminated = [[] for _ in range(self.n_bits)]

        # We simulate the measurement of states for the primary message signature (k=0)
        active_sig = self.alice_sigs[0]

        for i in range(self.n_bits):
            bit, basis = active_sig[i]

            # Bob measurements
            bob_copies = len(self.bob_held[i])
            if bob_copies == 1:
                # 1 measurement in random basis
                chosen_basis = int(rng.integers(0, 2))
                eliminated = self._measure_and_eliminate(bit, basis, chosen_basis, backend, rng)
                self.bob_eliminated[i].append(eliminated)
            elif bob_copies == 2:
                # 2 measurements, one in Z (0), one in X (1)
                elim1 = self._measure_and_eliminate(bit, basis, 0, backend, rng)
                elim2 = self._measure_and_eliminate(bit, basis, 1, backend, rng)
                self.bob_eliminated[i].extend([elim1, elim2])

            # Charlie measurements
            charlie_copies = len(self.charlie_held[i])
            if charlie_copies == 1:
                chosen_basis = int(rng.integers(0, 2))
                eliminated = self._measure_and_eliminate(bit, basis, chosen_basis, backend, rng)
                self.charlie_eliminated[i].append(eliminated)
            elif charlie_copies == 2:
                elim1 = self._measure_and_eliminate(bit, basis, 0, backend, rng)
                elim2 = self._measure_and_eliminate(bit, basis, 1, backend, rng)
                self.charlie_eliminated[i].extend([elim1, elim2])

    def _measure_and_eliminate(
        self,
        src_bit: int,
        src_basis: int,
        meas_basis: int,
        backend: AerSimulator,
        rng: np.random.Generator
    ) -> str:
        # Prepare 1 qubit circuit
        qc = prepare_bb84_state(np.array([src_bit]), np.array([src_basis]))
        tx_qc = self.channel.transmit(qc, rng=rng)
        meas_qc = add_bb84_measurement(tx_qc, np.array([meas_basis]))

        # Execute
        result = backend.run(meas_qc, shots=self.shots).result()
        counts = result.get_counts()
        # Parse output bit (most common output)
        out_bit_str = max(counts, key=counts.get).strip()
        # Strip spaces or any non-binary chars if any, take last char
        out_bit = int(out_bit_str[-1])

        # State elimination rule
        if meas_basis == 0: # Z basis
            # Outcome 0 rules out |1>
            # Outcome 1 rules out |0>
            return '|1⟩' if out_bit == 0 else '|0⟩'
        else: # X basis
            # Outcome 0 (which is + in X basis) rules out |->
            # Outcome 1 (which is - in X basis) rules out |+>
            return '|−⟩' if out_bit == 0 else '|+⟩'

    def process(self, rng: Optional[np.random.Generator] = None) -> QDSResult:
        bob_rcv = sum(1 for h in self.bob_held if len(h) > 0)
        charlie_rcv = sum(1 for h in self.charlie_held if len(h) > 0)

        min_allowed = (self.abort_threshold_pct / 100.0) * self.n_bits
        bob_aborted = bob_rcv < min_allowed
        charlie_aborted = charlie_rcv < min_allowed

        return QDSResult(
            n_bits=self.n_bits,
            alice_signatures=self.alice_sigs,
            bob_actions=self.bob_actions,
            charlie_actions=self.charlie_actions,
            bob_received_count=bob_rcv,
            charlie_received_count=charlie_rcv,
            bob_aborted=bob_aborted,
            charlie_aborted=charlie_aborted,
            bob_eliminated=self.bob_eliminated,
            charlie_eliminated=self.charlie_eliminated
        )

    def run(self, n_bits: int, rng: Optional[np.random.Generator] = None) -> QDSResult:
        if rng is None:
            rng = np.random.default_rng()

        self.setup(n_bits, rng)
        self.transmit(rng)
        self.measure(rng)
        return self.process(rng)

    def verify_message(
        self,
        k: int,
        proposed_sig: List[Tuple[int, int]],
        recipient: str = 'bob'
    ) -> Tuple[bool, int, int]:
        """
        Verifies Alice's signature for message k.
        Returns: (is_valid, mismatch_count, total_checked)
        """
        elim_list = self.bob_eliminated if recipient == 'bob' else self.charlie_eliminated
        held_list = self.bob_held if recipient == 'bob' else self.charlie_held

        mismatches = 0
        total_checked = 0

        for i in range(self.n_bits):
            if len(held_list[i]) > 0:
                total_checked += 1
                # Map state to string symbol
                bit, basis = proposed_sig[i]
                if basis == 0:
                    state_symbol = '|0⟩' if bit == 0 else '|1⟩'
                else:
                    state_symbol = '|+⟩' if bit == 0 else '|−⟩'

                # If this state is in the eliminated list, it is a contradiction!
                if state_symbol in elim_list[i]:
                    mismatches += 1

        # In noise-free simulation, threshold is 0 mismatches
        is_valid = (mismatches == 0)
        return is_valid, mismatches, total_checked
