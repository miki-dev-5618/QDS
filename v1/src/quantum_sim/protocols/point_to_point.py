from dataclasses import dataclass
from typing import Optional, List
import numpy as np
from qiskit_aer import AerSimulator

from quantum_sim.protocols.base import BaseProtocol
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.utils.metrics import sift_bases, extract_bits_from_counts, estimate_qber


@dataclass
class ProtocolResult:
    n_sent: int
    n_sifted: int
    sifted_bits_alice: np.ndarray
    sifted_bits_bob: np.ndarray
    qber: float
    eve_detected: bool


class PointToPointProtocol(BaseProtocol):
    def __init__(
        self,
        alice: Node,
        bob: Node,
        channel: QuantumChannel,
        shots: int = 1024,
        qber_threshold: float = 0.15,
        batch_size: int = 20
    ):
        self.alice = alice
        self.bob = bob
        self.channel = channel
        self.shots = shots
        self.qber_threshold = qber_threshold
        self.batch_size = batch_size

    def setup(self, n_bits: int, rng: Optional[np.random.Generator] = None):
        pass

    def transmit(self, rng: Optional[np.random.Generator] = None):
        pass

    def measure(self, rng: Optional[np.random.Generator] = None):
        pass

    def process(self, sample_ratio: float = 0.5, rng: Optional[np.random.Generator] = None) -> ProtocolResult:
        pass

    def run(self, n_bits: int, sample_ratio: float = 0.5, rng: Optional[np.random.Generator] = None) -> ProtocolResult:
        if rng is None:
            rng = np.random.default_rng()

        backend = AerSimulator()
        all_alice_bits: List[int] = []
        all_alice_bases: List[int] = []
        all_bob_bases: List[int] = []
        all_bob_bits: List[int] = []

        remaining = n_bits
        while remaining > 0:
            chunk_len = min(remaining, self.batch_size)
            
            prep_qc = self.alice.prepare_bb84_transmission(chunk_len, rng=rng)
            tx_qc = self.channel.transmit(prep_qc, rng=rng)
            meas_qc = self.bob.apply_bb84_measurement(tx_qc, n_bits=chunk_len, rng=rng)

            result = backend.run(meas_qc, shots=self.shots).result()
            counts = result.get_counts()
            bob_chunk_bits = extract_bits_from_counts(counts, chunk_len)

            all_alice_bits.extend(self.alice.bits)
            all_alice_bases.extend(self.alice.bases)
            all_bob_bases.extend(self.bob.bases)
            all_bob_bits.extend(bob_chunk_bits)

            remaining -= chunk_len

        alice_bits_arr = np.array(all_alice_bits, dtype=int)
        alice_bases_arr = np.array(all_alice_bases, dtype=int)
        bob_bases_arr = np.array(all_bob_bases, dtype=int)
        bob_bits_arr = np.array(all_bob_bits, dtype=int)

        self.alice.bits = alice_bits_arr
        self.alice.bases = alice_bases_arr
        self.bob.bases = bob_bases_arr
        self.bob.bits = bob_bits_arr

        sifted_idx = sift_bases(alice_bases_arr, bob_bases_arr)
        qber = estimate_qber(
            alice_bits_arr,
            bob_bits_arr,
            sifted_idx,
            sample_ratio=sample_ratio,
            rng=rng
        )

        sifted_alice = alice_bits_arr[sifted_idx]
        sifted_bob = bob_bits_arr[sifted_idx]
        eve_detected = qber > self.qber_threshold

        return ProtocolResult(
            n_sent=n_bits,
            n_sifted=len(sifted_idx),
            sifted_bits_alice=sifted_alice,
            sifted_bits_bob=sifted_bob,
            qber=qber,
            eve_detected=eve_detected
        )
