from dataclasses import dataclass
from typing import Optional, List
import numpy as np
from qiskit_aer import AerSimulator

from quantum_sim.protocols.base import BaseProtocol
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.utils.metrics import sift_bases, extract_bits_from_counts, estimate_qber
from quantum_sim.utils.post_processing import reconcile_keys, amplify_privacy


@dataclass
class SecureProtocolResult:
    n_sent: int
    n_sifted: int
    sifted_bits_alice: np.ndarray
    sifted_bits_bob: np.ndarray
    qber: float
    reconciled_bits_alice: np.ndarray
    reconciled_bits_bob: np.ndarray
    errors_corrected: int
    final_key_alice: np.ndarray
    final_key_bob: np.ndarray
    eve_detected: bool


class SecurePointToPointProtocol(BaseProtocol):
    def __init__(
        self,
        alice: Node,
        bob: Node,
        channel: QuantumChannel,
        shots: int = 1024,
        qber_threshold: float = 0.15,
        batch_size: int = 20,
        reconciliation_block_size: int = 8
    ):
        self.alice = alice
        self.bob = bob
        self.channel = channel
        self.shots = shots
        self.qber_threshold = qber_threshold
        self.batch_size = batch_size
        self.reconciliation_block_size = reconciliation_block_size

    def setup(self, n_bits: int, rng: Optional[np.random.Generator] = None):
        pass

    def transmit(self, rng: Optional[np.random.Generator] = None):
        pass

    def measure(self, rng: Optional[np.random.Generator] = None):
        pass

    def process(self, sample_ratio: float = 0.5, rng: Optional[np.random.Generator] = None) -> SecureProtocolResult:
        pass

    def run(
        self,
        n_bits: int,
        sample_ratio: float = 0.5,
        rng: Optional[np.random.Generator] = None
    ) -> SecureProtocolResult:
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

        # Sift matching bases
        sifted_idx = sift_bases(alice_bases_arr, bob_bases_arr)
        sifted_alice = alice_bits_arr[sifted_idx]
        sifted_bob = bob_bits_arr[sifted_idx]

        # QBER Estimation
        qber = estimate_qber(
            alice_bits_arr,
            bob_bits_arr,
            sifted_idx,
            sample_ratio=sample_ratio,
            rng=rng
        )

        # For post-processing, Alice and Bob only use sifted keys.
        # But during QBER estimation, some of these bits might be disclosed/discarded.
        # To simplify the simulation, we correct errors on the sifted keys,
        # then apply privacy amplification.
        
        # 1. Information Reconciliation (Error Correction)
        reconciled_bob, errors_corrected = reconcile_keys(
            sifted_alice,
            sifted_bob,
            block_size=self.reconciliation_block_size
        )

        # 2. Privacy Amplification (Universal Hashing)
        # Create a new RNG with same seed to ensure Alice and Bob apply the exact same hashing matrix!
        hash_seed = rng.integers(0, 2**32 - 1)
        rng_alice = np.random.default_rng(hash_seed)
        rng_bob = np.random.default_rng(hash_seed)

        final_key_alice = amplify_privacy(sifted_alice, qber, rng=rng_alice)
        final_key_bob = amplify_privacy(reconciled_bob, qber, rng=rng_bob)

        eve_detected = qber > self.qber_threshold

        return SecureProtocolResult(
            n_sent=n_bits,
            n_sifted=len(sifted_idx),
            sifted_bits_alice=sifted_alice,
            sifted_bits_bob=sifted_bob,
            qber=qber,
            reconciled_bits_alice=sifted_alice,
            reconciled_bits_bob=reconciled_bob,
            errors_corrected=errors_corrected,
            final_key_alice=final_key_alice,
            final_key_bob=final_key_bob,
            eve_detected=eve_detected
        )
