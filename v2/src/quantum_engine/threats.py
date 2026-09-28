"""
Attack injectors (test/demo generator side only).

Each injector drives the public protocol stages and alters only what that
adversary could alter: a signature or message on the wire, the physical
channel, a dishonest party's own preparation, or a previously observed
package. Scenario names never leave this module except as experiment ground
truth attached after detection.
"""
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np

from .binding import SignedContext, SignedPackage, message_digest, new_blinding
from .channel import ChannelModel
from .elimination import REV_SYMBOL_MAP
from .enforcement import LINK_FORWARD, LINK_SIGNER
from .transcript import Transcript


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
    claimed_sender: str = "alice"
    repudiation_tamper_ratio: float = 0.5


class NoPackageToReplay(Exception):
    """Replay needs a previously accepted package observed on the wire."""


class ThreatSuite:
    # ------------------------------------------------------------ primitives
    @staticmethod
    def generate_eve_counterfeit_signature(n_bits: int, rng: np.random.Generator) -> List[Tuple[int, int]]:
        """Uniform guess of each (bit, basis) - Eve has no information about the states."""
        return [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, n_bits), rng.integers(0, 2, n_bits))]

    @staticmethod
    def generate_dishonest_bob_forgery(n_bits: int, bob_eliminated: List[List[str]],
                                       rng: np.random.Generator) -> List[Tuple[int, int]]:
        """Bob picks, per position, a state not in his own eliminated set; he has no view of Charlie's."""
        all_states = ['|0⟩', '|1⟩', '|+⟩', '|−⟩']
        forged = []
        for i in range(n_bits):
            elim = set(bob_eliminated[i]) if i < len(bob_eliminated) else set()
            candidates = [s for s in all_states if s not in elim] or all_states
            forged.append(REV_SYMBOL_MAP[str(rng.choice(candidates))])
        return forged

    @staticmethod
    def asymmetric_preparation(tamper_ratio: float):
        """Dishonest Alice: Charlie's copy has orthogonal states at a fraction of positions."""
        def prepare(signature, rng):
            bob_copy, charlie_copy = list(signature), list(signature)
            k = max(1, int(len(signature) * tamper_ratio))
            for idx in rng.choice(len(signature), size=k, replace=False):
                b, ba = signature[idx]
                charlie_copy[idx] = (1 - b, ba)
            return bob_copy, charlie_copy
        return prepare

    # ---------------------------------------------------------- dishonest Bob
    @classmethod
    def dishonest_bob_forward(cls, engine, session_id: str, message: str,
                              rng: np.random.Generator) -> Transcript:
        """
        Bob forwards to Charlie a signature for a message of his choosing, built
        only from Bob's own distribution-stage records for `session_id`.
        """
        record = engine.verifiers["bob"].records.get(session_id)
        if record is None:
            raise NoPackageToReplay("Bob holds no distribution record to forge from.")
        n_bits = len(record.eliminated)
        forged_ctx = SignedContext(
            session_id=session_id, sender=record.sender, verifiers=["bob", "charlie"],
            nonce=SignedContext.new(record.sender, [], message).nonce,
            timestamp=engine.clock(), message_digest=message_digest(message),
        )
        package = SignedPackage(context=forged_ctx, message=message,
                                revealed_signature=cls.generate_dishonest_bob_forgery(n_bits, record.eliminated, rng),
                                blinding=new_blinding())
        fwd = engine.forward(package, "bob", "charlie")
        return Transcript(kind="forward", link=LINK_FORWARD, n_bits=n_bits,
                          package=package.copy(forwarded_by="bob"), results=[fwd], display={"charlie": fwd},
                          notes=[f"Bob forwarded a package for session {session_id} to Charlie."])

    # --------------------------------------------------------------- runner
    @classmethod
    def run(cls, engine, scenario: ThreatScenarioConfig, message: str, n_bits: int, sender: str,
            rng: np.random.Generator, channel: Optional[ChannelModel] = None) -> Transcript:
        t = scenario.threat_type
        channel = channel or engine.default_channel

        if t == ThreatType.AUTHENTIC:
            return engine.transmit(sender, message, n_bits, rng, channel)

        if t == ThreatType.EVE_INTERCEPT:
            tapped = ChannelModel(depolarizing=channel.depolarizing, intercept_rate=scenario.channel_intercept_rate)
            return engine.transmit(sender, message, n_bits, rng, tapped)

        if t == ThreatType.REPUDIATION:
            session = engine.distribute(sender, message, n_bits, rng, channel,
                                        prepare_copies=cls.asymmetric_preparation(scenario.repudiation_tamper_ratio))
            package = engine.reveal(session)
            return cls._delivered(engine, package, n_bits, session)

        if t in (ThreatType.EVE_FORGERY, ThreatType.MESSAGE_TAMPERING):
            session = engine.distribute(sender, message, n_bits, rng, channel)
            package = engine.reveal(session)
            if t == ThreatType.EVE_FORGERY:
                package = package.copy(revealed_signature=cls.generate_eve_counterfeit_signature(n_bits, rng))
            else:
                package = package.copy(message=scenario.tampered_message_text
                                       or message + " [ALTERED IN TRANSIT]")
            return cls._delivered(engine, package, n_bits, session)

        if t == ThreatType.REPLAY:
            package = engine.last_accepted_package
            if package is None:
                raise NoPackageToReplay("No previously accepted package has been observed yet.")
            return cls._delivered(engine, package.copy(), len(package.revealed_signature), None,
                                  notes=["Identical copy of a previously accepted package re-sent."])

        if t == ThreatType.IMPERSONATION:
            ctx = SignedContext.new(scenario.claimed_sender or "alice", ["bob", "charlie"], message,
                                    timestamp=engine.clock())
            package = SignedPackage(context=ctx, message=message,
                                    revealed_signature=cls.generate_eve_counterfeit_signature(n_bits, rng),
                                    blinding=new_blinding())
            return cls._delivered(engine, package, n_bits, None,
                                  notes=["Rogue sender transmitted without any distribution stage."])

        if t == ThreatType.DISHONEST_BOB:
            session = engine.distribute(sender, message, n_bits, rng, channel)
            tr = cls.dishonest_bob_forward(
                engine, session.context.session_id,
                scenario.tampered_message_text or "[FORWARDED BY BOB] " + message, rng)
            tr.session, tr.channel_test, tr.channel_model = session, session.channel_test, session.channel_model
            return tr

        raise ValueError(f"Unknown scenario {t}")

    @staticmethod
    def _delivered(engine, package, n_bits, session, notes=None) -> Transcript:
        if session is not None and session.aborted:
            # The channel test aborted distribution: the signer never reveals, so nothing reaches the verifiers.
            return Transcript(kind="direct", link=LINK_SIGNER, n_bits=n_bits, package=package, results=[],
                              display={}, session=session, channel_test=session.channel_test,
                              channel_model=session.channel_model,
                              notes=list(notes or []) + ["Channel test alarm: signature never revealed."])
        results = engine.deliver(package)
        return Transcript(kind="direct", link=LINK_SIGNER, n_bits=n_bits, package=package, results=results,
                          display={r.verifier: r for r in results}, session=session,
                          channel_test=session.channel_test if session else None,
                          channel_model=session.channel_model if session else None,
                          notes=list(notes or []))
