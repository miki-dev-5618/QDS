import hashlib
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any


@dataclass
class QTHBResult:
    message_digest: str              # 512-bit SHA3-512 hex string
    digest_truncated: str            # First 16 chars for UI display
    basis_schedule: List[int]        # 0 = Z-basis (|0>, |1>), 1 = X-basis (|+>, |->)
    basis_symbols: List[str]         # ['Z', 'X', 'Z', ...]
    is_tampered: bool                # True if payload was altered in transit
    tampered_digest: str             # Digest of tampered payload if any
    desynchronized_indices: List[int]# Indices where basis schedule desynchronized
    desynchronization_rate: float    # Fraction of bases desynchronized (~50% on tamper)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_digest": self.message_digest,
            "digest_truncated": self.digest_truncated,
            "basis_schedule": self.basis_schedule,
            "basis_symbols": self.basis_symbols,
            "is_tampered": self.is_tampered,
            "tampered_digest": self.tampered_digest,
            "desynchronized_indices": self.desynchronized_indices,
            "desynchronization_rate": round(self.desynchronization_rate, 4),
        }


class QTHBEngine:
    """
    INNOVATION 1: Quantum-Tethered Hash Binding (Q-THB)
    
    Tethers arbitrary-length plaintext message payloads to the physical
    quantum projective measurement schedule.
    1. Computes SHA3-512 cryptographic digest H(M).
    2. Deterministically maps H(M) into the projective measurement basis schedule B in {Z, X}^N.
    3. If even a single character in M is altered in-flight, H(M) desynchronizes B,
       causing a catastrophic ~50% orthogonal state contradiction rate at verifier nodes.
    """

    @staticmethod
    def compute_digest(message: str) -> str:
        """Computes SHA3-512 digest of arbitrary plaintext string."""
        return hashlib.sha3_512(message.encode("utf-8")).hexdigest()

    @classmethod
    def generate_basis_schedule(cls, message_digest: str, n_bits: int) -> List[int]:
        """
        Deterministically expands the 512-bit digest into an N-bit measurement basis schedule.
        Each bit is mapped to 0 (Z-basis) or 1 (X-basis).
        """
        digest_bytes = bytes.fromhex(message_digest)
        schedule: List[int] = []

        # Linear congruential expansion over digest bytes
        seed = int.from_bytes(digest_bytes[:8], byteorder="big")
        a = 6364136223846793005
        c = 1442695040888963407
        m = 2**64

        current = seed
        for i in range(n_bits):
            byte_val = digest_bytes[i % len(digest_bytes)]
            current = (a * current + c + byte_val) % m
            schedule.append((current >> 32) & 1)

        return schedule

    @classmethod
    def bind_message(
        cls,
        original_message: str,
        n_bits: int,
        received_message: str = None
    ) -> QTHBResult:
        orig_digest = cls.compute_digest(original_message)
        orig_schedule = cls.generate_basis_schedule(orig_digest, n_bits)
        orig_symbols = ["Z" if b == 0 else "X" for b in orig_schedule]

        is_tampered = False
        tampered_digest = orig_digest
        desync_indices: List[int] = []
        desync_rate = 0.0

        if received_message is not None and received_message != original_message:
            is_tampered = True
            tampered_digest = cls.compute_digest(received_message)
            tampered_schedule = cls.generate_basis_schedule(tampered_digest, n_bits)

            for i in range(n_bits):
                if orig_schedule[i] != tampered_schedule[i]:
                    desync_indices.append(i)

            desync_rate = len(desync_indices) / n_bits if n_bits > 0 else 0.0

        return QTHBResult(
            message_digest=orig_digest,
            digest_truncated=orig_digest[:16] + "...",
            basis_schedule=orig_schedule,
            basis_symbols=orig_symbols,
            is_tampered=is_tampered,
            tampered_digest=tampered_digest,
            desynchronized_indices=desync_indices,
            desynchronization_rate=desync_rate,
        )
