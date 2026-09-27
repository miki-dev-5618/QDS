import time
import secrets
from enum import Enum
from typing import Set, Dict, Optional, Tuple


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    REPLAY_DUPLICATE_NONCE = "REPLAY_DUPLICATE_NONCE"
    EXPIRED_TIMESTAMP = "EXPIRED_TIMESTAMP"
    INVALID_SEQUENCE = "INVALID_SEQUENCE"


class FreshnessTracker:
    """
    Session Nonce and Timestamp Freshness Tracking Engine.
    Prevents Replay Attacks and Double-Spending of Quantum Signature Tokens.
    """
    def __init__(self, max_window_seconds: float = 300.0):
        self.max_window_seconds = max_window_seconds
        self.consumed_nonces: Set[str] = set()
        self.last_seq_by_sender: Dict[str, int] = {}

    @staticmethod
    def generate_nonce(num_bytes: int = 16) -> str:
        """Generates a cryptographically secure hex nonce."""
        return secrets.token_hex(num_bytes)

    def verify_and_consume(
        self,
        sender: str,
        nonce: str,
        timestamp: float,
        seq_num: Optional[int] = None,
        current_time: Optional[float] = None
    ) -> Tuple[bool, FreshnessStatus]:
        """
        Validates freshness of a signature message.
        If fresh, registers the nonce as consumed.
        """
        if current_time is None:
            current_time = time.time()

        # 1. Timestamp age validation (sliding window)
        time_diff = abs(current_time - timestamp)
        if time_diff > self.max_window_seconds:
            return False, FreshnessStatus.EXPIRED_TIMESTAMP

        # 2. Duplicate Nonce check
        if nonce in self.consumed_nonces:
            return False, FreshnessStatus.REPLAY_DUPLICATE_NONCE

        # 3. Monotonic sequence counter check if provided
        if seq_num is not None:
            last_seq = self.last_seq_by_sender.get(sender, -1)
            if seq_num <= last_seq:
                return False, FreshnessStatus.INVALID_SEQUENCE
            self.last_seq_by_sender[sender] = seq_num

        # Register nonce as consumed
        self.consumed_nonces.add(nonce)
        return True, FreshnessStatus.FRESH

    def reset(self) -> None:
        """Clears consumed nonces and sequence history."""
        self.consumed_nonces.clear()
        self.last_seq_by_sender.clear()
