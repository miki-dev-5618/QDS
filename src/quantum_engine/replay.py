"""
Verifier-side replay protection: a clock window plus a set of consumed nonces.

With a ``Store`` the consumed set is persistent and the consume step is an
atomic insert, so a nonce can be accepted at most once per verifier and
channel even across restarts.
"""
import threading
import time
from typing import Callable, Optional, Set, Tuple


class ReplayGuard:
    def __init__(self, window_seconds: float = 120.0, max_future_skew: float = 5.0,
                 clock: Callable[[], float] = time.time, store=None, owner: str = "verifier"):
        self.window_seconds = window_seconds
        self.max_future_skew = max_future_skew
        self.clock = clock
        self.store = store
        self.owner = owner
        self._consumed: Set[Tuple[str, str]] = set()
        self.lock = threading.RLock()

    def freshness(self, nonce: str, timestamp: float, channel: str = "direct") -> Tuple[bool, str]:
        """Check without consuming. Returns (fresh, reason)."""
        now = self.clock()
        if timestamp > now + self.max_future_skew:
            return False, "timestamp_in_future"
        if now - timestamp > self.window_seconds:
            return False, "expired"
        if self.is_consumed(nonce, channel):
            return False, "duplicate_nonce"
        return True, "ok"

    def consume(self, nonce: str, channel: str = "direct") -> bool:
        """Mark consumed; False if another request consumed it first."""
        with self.lock:
            if self.store is not None:
                ok = self.store.consume_nonce(self.owner, channel, nonce, self.clock())
            else:
                ok = (nonce, channel) not in self._consumed
            self._consumed.add((nonce, channel))
            return ok

    def is_consumed(self, nonce: str, channel: str = "direct") -> bool:
        if (nonce, channel) in self._consumed:
            return True
        return self.store is not None and self.store.nonce_consumed(self.owner, channel, nonce)
