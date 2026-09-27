from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Dict, Optional
import time
import numpy as np

from .elimination import SYMBOL_MAP, REV_SYMBOL_MAP


class ThreatType(str, Enum):
    AUTHENTIC = "authentic"
    EVE_FORGERY = "eve_forgery"
    DISHONEST_BOB = "dishonest_bob"
    EVE_INTERCEPT = "eve_intercept"
    MESSAGE_TAMPERING = "message_tampering"
    REPUDIATION = "repudiation"
    REPLAY = "replay"
    IMPERSONATION = "impersonation"


@dataclass
class ThreatScenarioConfig:
    threat_type: ThreatType = ThreatType.AUTHENTIC
    channel_intercept_rate: float = 1.0
    tampered_message_text: Optional[str] = None
    replay_delay_seconds: float = 600.0
    claimed_sender: str = "Alice"


class ThreatSuite:
    """
    Simulates deterministic cyber and quantum attacks against the QDS protocol:
    1. Eve Classical Forgery: Random substitution of revealed signature bits.
    2. Dishonest Verifier Forgery: Bob crafting targeted counterfeit signatures using partial elimination knowledge.
    3. Eve MITM Channel Intercept: Intercept-resend collapse of quantum superpositions causing QBER spikes.
    4. Message Tampering: Modifying plaintext while keeping signature static.
    5. Alice Repudiation: Asymmetric state generation between verifiers.
    6. Replay Attack: Stale token re-broadcast with expired timestamp/nonce.
    7. Impersonation Attack: Rogue sender broadcasting unauthenticated credentials.
    """

    @staticmethod
    def generate_eve_counterfeit_signature(
        n_bits: int,
        rng: Optional[np.random.Generator] = None
    ) -> List[Tuple[int, int]]:
        """
        Eve randomly guesses the Pauli eigenstate pairs (bit, basis) without possessing the secret.
        Each guess has a 25% chance of falling into a verifier's eliminated set.
        """
        if rng is None:
            rng = np.random.default_rng()
        bits = rng.integers(0, 2, size=n_bits)
        bases = rng.integers(0, 2, size=n_bits)
        return [(int(b), int(ba)) for b, ba in zip(bits, bases)]

    @staticmethod
    def generate_dishonest_bob_forgery(
        n_bits: int,
        bob_eliminated: List[List[str]],
        rng: Optional[np.random.Generator] = None
    ) -> List[Tuple[int, int]]:
        """
        Bob attempts to forge Alice's signature to send to Charlie.
        Bob uses his own eliminated states to pick candidate states he believes might be valid.
        However, because of keep-or-forward symmetrisation, Bob has zero knowledge of
        states Charlie eliminated during independent measurements.
        """
        if rng is None:
            rng = np.random.default_rng()

        forged_sig: List[Tuple[int, int]] = []
        all_states = ['|0⟩', '|1⟩', '|+⟩', '|−⟩']

        for i in range(n_bits):
            elim = set(bob_eliminated[i]) if i < len(bob_eliminated) else set()
            candidates = [s for s in all_states if s not in elim]
            if candidates:
                chosen = str(rng.choice(candidates))
            else:
                chosen = str(rng.choice(all_states))
            forged_sig.append(REV_SYMBOL_MAP[chosen])

        return forged_sig

    @staticmethod
    def create_repudiation_asymmetric_states(
        n_bits: int,
        tamper_ratio: float = 0.5,
        rng: Optional[np.random.Generator] = None
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """
        Alice prepares asymmetric signatures for Bob vs Charlie.
        Returns:
            bob_states: List of (bit, basis)
            charlie_states: List of (bit, basis) with flipped values at tamper positions
        """
        if rng is None:
            rng = np.random.default_rng()

        bob_states = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
        charlie_states = list(bob_states)

        num_tamper = max(1, int(n_bits * tamper_ratio))
        tamper_indices = rng.choice(n_bits, size=num_tamper, replace=False)

        for idx in tamper_indices:
            b, ba = bob_states[idx]
            # Invert bit or basis to produce orthogonal mismatch
            charlie_states[idx] = (1 - b, ba)

        return bob_states, charlie_states
