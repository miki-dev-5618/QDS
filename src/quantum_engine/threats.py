"""
Attack injectors (test/demo generator side only).

Each injector drives the public protocol stages and alters only what that
adversary could alter: a signature or message on the wire, the physical
channel, a dishonest party's own preparation, or a previously observed
package. Scenario names never leave this module except as experiment ground
truth attached after detection.

N-verifier scenarios (one selected dishonest verifier; collusion is not modelled):
  dishonest_forwarder  the selected verifier receives the genuine package, then
                       alters the message or signature and forwards it anyway
  forward_withheld     the selected verifier accepts but never forwards (chain)
  route_manipulation   the selected verifier forwards the genuine package but
                       claims a deeper level than its edge has (chain)
  forward_replay       a recipient that already verified a forwarded copy is
                       sent it again (another sender in direct mode)
  unknown_forwarder    an unenrolled identity forwards the genuine package

Eve channel scenarios restored from the adversaries track:
  eve_cloning           1->2 quantum cloner on every token, then a forgery from Eve's clone
  eve_partial_intercept intercept-resend on a tuned fraction f of tokens
  eve_collective        one concrete ancilla-probe (controlled-Ry) collective attack
"""
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np

from .binding import SignedContext, SignedPackage, message_digest, new_blinding
from .channel import ChannelModel
from .elimination import REV_SYMBOL_MAP
from .enforcement import LINK_FORWARD, LINK_SIGNER
from .roster import ConfigurationError, SessionConfig
from .transcript import Transcript

UNENROLLED_IDENTITY = "mallory"


class ThreatType(str, Enum):
    AUTHENTIC = "authentic"
    EVE_FORGERY = "eve_forgery"
    DISHONEST_BOB = "dishonest_bob"
    EVE_INTERCEPT = "eve_intercept"
    MESSAGE_TAMPERING = "message_tampering"
    REPUDIATION = "repudiation"
    REPLAY = "replay"
    IMPERSONATION = "impersonation"
    EVE_LOSS_EXPLOIT = "eve_loss_exploit"
    DISHONEST_FORWARDER = "dishonest_forwarder"
    FORWARD_WITHHELD = "forward_withheld"
    ROUTE_MANIPULATION = "route_manipulation"
    FORWARD_REPLAY = "forward_replay"
    UNKNOWN_FORWARDER = "unknown_forwarder"
    EVE_CLONING = "eve_cloning"
    EVE_PARTIAL_INTERCEPT = "eve_partial_intercept"  # opt-in partial intercept-resend
    EVE_COLLECTIVE = "eve_collective"                # one concrete ancilla-probe attack


FORWARDING_THREATS = {ThreatType.DISHONEST_FORWARDER, ThreatType.FORWARD_WITHHELD, ThreatType.ROUTE_MANIPULATION,
                      ThreatType.FORWARD_REPLAY, ThreatType.UNKNOWN_FORWARDER}
CHAIN_ONLY_THREATS = {ThreatType.FORWARD_WITHHELD, ThreatType.ROUTE_MANIPULATION}


@dataclass
class ThreatScenarioConfig:
    threat_type: ThreatType = ThreatType.AUTHENTIC
    channel_intercept_rate: float = 1.0
    tampered_message_text: Optional[str] = None
    claimed_sender: str = "alice"
    repudiation_tamper_ratio: float = 0.5
    loss_exploit_block_rate: float = 0.5
    dishonest_verifier: Optional[str] = None     # forwarding scenarios: the one dishonest roster member
    forward_alteration: str = "message"          # dishonest_forwarder: "message" | "signature"
    attack_edge: Optional[str] = None            # eve_intercept: the quantum link Eve taps (None = whole send)
    cloner_type: str = "universal"       # eve_cloning: "universal" or "phase_covariant"
    cloning_rate: float = 1.0            # eve_cloning: fraction of tokens cloned by Eve
    partial_intercept_fraction: float = 0.05  # eve_partial_intercept: f in [0.05, 1.0]
    collective_theta: float = math.pi / 4     # eve_collective: probe strength in [0, pi]


class NoPackageToReplay(Exception):
    """Replay needs a previously accepted package observed on the wire."""


class EveLossExploitAdversary:
    """
    Adversary exploiting channel erasure / loss.
    Eve intercepts tokens; when her measurement introduces disturbance or when she
    cannot copy the state reliably, she blocks the token (simulating channel photon loss).
    Under the fair-sampling assumption, receivers assume photon loss is independent
    of the quantum state/basis; an adversary exploiting loss selectively breaks fair sampling.
    """
    def __init__(self, block_rate: float = 0.5):
        self.block_rate = block_rate
        self.events = []

    def tap(self, stream, schedule_public, rng):
        self.events = []
        for s in stream:
            # Eve intercepts in random basis
            eve_basis = int(rng.integers(0, 2))
            self.events.append((eve_basis, None))
        return self.events

    def observe(self, sent, outcomes):
        pass


# Composition of the background Pauli with the probe's phase flip (global phases dropped).
_TIMES_Z = {None: "Z", "X": "Y", "Y": "X", "Z": None}


def probe_flip_probability(theta: float, basis: int) -> float:
    """P(token flipped in its own basis) after Eve's controlled-Ry(theta) probe; basis 0 = Z, 1 = X."""
    return 0.0 if basis == 0 else (1.0 - math.cos(theta / 2.0)) / 2.0


def probe_guess_probability(theta: float, basis: int) -> float:
    """P(Eve guesses the token bit) from her ancilla alone (Helstrom), once the basis is announced."""
    return (1.0 + math.sin(theta / 2.0)) / 2.0 if basis == 0 else 0.5


class EveCollectiveAdversary:
    """
    ONE concrete collective (ancilla-probe) attack - not a proof against all collective attacks.

    For every token Eve prepares an ancilla |0>, applies the same controlled-Ry(theta)
    (token = control, ancilla = target), forwards the token and keeps the ancilla. After
    the bases are announced she measures each ancilla individually (Helstrom measurement)
    to guess the token's bit. She probes the travelling qubit; with the public
    teleportation corrections this is equivalent to probing the token itself.

    Effect on the token: Z-basis states are untouched; X-basis states lose coherence by a
    factor cos(theta/2), i.e. a phase flip with probability (1 - cos(theta/2)) / 2. That
    flip is composed with the channel's own noise event. Eve's information: Helstrom
    success (1 + sin(theta/2)) / 2 on Z-basis tokens, 1/2 on X-basis tokens.
    """

    def __init__(self, theta: float, channel: ChannelModel):
        if not 0.0 <= theta <= math.pi:
            raise ValueError(f"collective_theta must be in [0, pi], got {theta!r}")
        self.theta = theta
        self.channel = channel
        self.guess_correct: List[bool] = []   # one entry per signature copy that reached the verifiers

    def tap(self, stream, schedule_public, rng):
        events = []
        for (eve_basis, noise), s in zip(self.channel.sample_events(len(stream), rng), stream):
            if rng.random() < probe_flip_probability(self.theta, s.basis):
                noise = _TIMES_Z[noise]
            events.append((eve_basis, noise))
        self._guesses = [rng.random() < probe_guess_probability(self.theta, s.basis) for s in stream]
        return events

    def observe(self, sent, outcomes):
        self.guess_correct = [g for s, g in zip(sent, self._guesses) if s.kind == "sig"]

    @property
    def guess_accuracy(self) -> float:
        return sum(self.guess_correct) / len(self.guess_correct) if self.guess_correct else float("nan")


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
        """
        Dishonest Alice: the copies prepared for the second half of the roster (Charlie when N = 2)
        have orthogonal states at a fraction of positions. Symmetrisation then spreads them over holders.
        """
        def prepare(signature, rng, roster=("bob", "charlie")):
            roster = list(roster)
            copies = {v: list(signature) for v in roster}
            k = max(1, int(len(signature) * tamper_ratio))
            for v in roster[len(roster) // 2:]:
                for idx in rng.choice(len(signature), size=k, replace=False):
                    b, ba = signature[idx]
                    copies[v][idx] = (1 - b, ba)
            return copies
        return prepare

    @staticmethod
    def alter(package: SignedPackage, alteration: str, rng: np.random.Generator, holder: str) -> SignedPackage:
        """What a dishonest forwarder can change: the message, or the revealed signature."""
        if alteration == "signature":
            sig = list(package.revealed_signature)
            k = max(1, len(sig) // 4)
            for idx in rng.choice(len(sig), size=k, replace=False):
                b, ba = sig[idx]
                sig[idx] = (1 - b, ba)
            return package.copy(revealed_signature=sig)
        return package.copy(message=f"[ALTERED BY {holder.upper()}] " + package.message)

    # ------------------------------------------------------------ validation
    @staticmethod
    def validate(scenario: "ThreatScenarioConfig", cfg: SessionConfig) -> None:
        """Unsupported scenario/configuration combinations are configuration errors, raised before distribution."""
        t = scenario.threat_type
        if t == ThreatType.DISHONEST_BOB and not {"bob", "charlie"} <= set(cfg.roster):
            raise ConfigurationError("The dishonest_bob scenario needs Bob and Charlie in the roster.")
        if t in CHAIN_ONLY_THREATS and cfg.delivery != "chain":
            raise ConfigurationError(f"Scenario {t.value} needs chain delivery.")
        if t in FORWARDING_THREATS - {ThreatType.UNKNOWN_FORWARDER}:
            cfg.validate_dishonest(scenario.dishonest_verifier)
        if t == ThreatType.UNKNOWN_FORWARDER and scenario.dishonest_verifier is not None:
            cfg.validate_dishonest(scenario.dishonest_verifier)
        if scenario.forward_alteration not in ("message", "signature"):
            raise ConfigurationError("forward_alteration must be 'message' or 'signature'.")

    @staticmethod
    def _target(cfg: SessionConfig, verifier: str) -> str:
        """The next recipient after ``verifier``: its chain successor, or the next roster member (direct)."""
        nxt = cfg.next_hop(verifier)
        if nxt is not None:
            return nxt
        return cfg.roster[(cfg.roster.index(verifier) + 1) % cfg.n]

    # ------------------------------------------------------ forwarding attacks
    @classmethod
    def forwarding_attack(cls, engine, scenario: "ThreatScenarioConfig", session, package: SignedPackage,
                          cfg: SessionConfig, rng: np.random.Generator) -> Tuple[List, List[str]]:
        t = scenario.threat_type
        d = scenario.dishonest_verifier
        notes: List[str] = []

        def hook(holder, nxt, pkg, result):
            if holder != d:
                return engine.honest_forwarding(holder, nxt, pkg, result)
            if t == ThreatType.DISHONEST_FORWARDER:
                notes.append(f"{d} altered the {scenario.forward_alteration} and forwarded it to {nxt}.")
                return "forward", cls.alter(pkg, scenario.forward_alteration, rng, d), None
            if t == ThreatType.FORWARD_WITHHELD:
                return "stop", pkg, (f"{d} did not forward the package; downstream recipients are not reached "
                                     f"(withholding is not a signature forgery).")
            if t == ThreatType.ROUTE_MANIPULATION:
                return "forward", pkg.copy(depth=cfg.roster.index(nxt) + 1), \
                    f"{d} forwarded to {nxt} claiming depth {cfg.roster.index(nxt) + 1} (validated depth " \
                    f"{cfg.roster.index(nxt)})."
            return engine.honest_forwarding(holder, nxt, pkg, result)

        if cfg.delivery == "chain" and t in (ThreatType.DISHONEST_FORWARDER, ThreatType.FORWARD_WITHHELD,
                                             ThreatType.ROUTE_MANIPULATION):
            results, chain_notes = engine.deliver_session(package, session, cfg, on_hop=hook)
            return results, notes + chain_notes

        results, chain_notes = engine.deliver_session(package, session, cfg)
        notes.extend(chain_notes)
        if t == ThreatType.DISHONEST_FORWARDER:          # direct mode: alter after the reveal, then forward
            target = cls._target(cfg, d)
            results.append(engine.forward(cls.alter(package, scenario.forward_alteration, rng, d), d, target,
                                          session=session))
            notes.append(f"{d} altered the {scenario.forward_alteration} and forwarded it to {target}.")
        elif t == ThreatType.FORWARD_REPLAY:
            target = cls._target(cfg, d)
            if cfg.delivery == "direct":
                results.append(engine.forward(package, d, target, session=session))
                other = next(v for v in cfg.roster if v not in (d, target)) if cfg.n > 2 else d
                results.append(engine.forward(package, other, target, session=session))
                notes.append(f"The package reached {target} from {d}, then again from {other}.")
            else:
                results.append(engine.forward(package, d, target, session=session))
                notes.append(f"{d} re-sent the already forwarded package to {target}.")
        elif t == ThreatType.UNKNOWN_FORWARDER:
            target = cls._target(cfg, d) if d else (cfg.roster[1] if cfg.n > 1 else cfg.roster[0])
            results.append(engine.forward(package, UNENROLLED_IDENTITY, target, parent_event_id=None,
                                          session=session))
            notes.append(f"Unenrolled identity '{UNENROLLED_IDENTITY}' forwarded the package to {target}.")
        return results, notes

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
        roster = list(record.config.roster) if record.config is not None else ["bob", "charlie"]
        forged_ctx = SignedContext(
            session_id=session_id, sender=record.sender, verifiers=roster,
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
            rng: np.random.Generator, channel: Optional[ChannelModel] = None,
            config: Optional[SessionConfig] = None) -> Transcript:
        t = scenario.threat_type
        channel = channel or engine.default_channel
        cfg = config or engine.default_config

        if t == ThreatType.AUTHENTIC:
            return engine.transmit(sender, message, n_bits, rng, channel, config=cfg)

        if t == ThreatType.EVE_INTERCEPT and scenario.attack_edge:
            # Eve sits on one link; execute_protocol installs her there as an edge injection.
            return engine.transmit(sender, message, n_bits, rng, channel, config=cfg)

        if t == ThreatType.EVE_INTERCEPT:
            tapped = ChannelModel(depolarizing=channel.depolarizing, intercept_rate=scenario.channel_intercept_rate)
            return engine.transmit(sender, message, n_bits, rng, tapped, config=cfg)

        if t in FORWARDING_THREATS:
            session = engine.distribute(sender, message, n_bits, rng, channel, config=cfg)
            package = engine.reveal(session)
            if session.aborted:
                return cls._delivered(engine, package, n_bits, session)
            results, notes = cls.forwarding_attack(engine, scenario, session, package, cfg, rng)
            return Transcript(kind="chain" if cfg.delivery == "chain" else "direct", link=LINK_SIGNER,
                              n_bits=n_bits, package=package, results=results,
                              display={r.verifier: r for r in results}, session=session,
                              channel_test=session.channel_test, channel_model=session.channel_model,
                              notes=notes, config=cfg)

        if t == ThreatType.EVE_PARTIAL_INTERCEPT:
            return cls._eve_partial_intercept(engine, scenario, message, n_bits, sender, rng, channel, cfg)

        if t == ThreatType.EVE_COLLECTIVE:
            return cls.eve_collective(engine, scenario.collective_theta, message, n_bits, sender, rng, channel,
                                      config=cfg)[0]

        if t == ThreatType.REPUDIATION:
            session = engine.distribute(sender, message, n_bits, rng, channel, config=cfg,
                                        prepare_copies=cls.asymmetric_preparation(scenario.repudiation_tamper_ratio))
            package = engine.reveal(session)
            return cls._delivered(engine, package, n_bits, session)

        if t in (ThreatType.EVE_FORGERY, ThreatType.MESSAGE_TAMPERING):
            session = engine.distribute(sender, message, n_bits, rng, channel, config=cfg)
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
            ctx = SignedContext.new(scenario.claimed_sender or "alice", list(cfg.roster), message,
                                    timestamp=engine.clock(), delivery=cfg.delivery, max_depth=cfg.max_depth)
            package = SignedPackage(context=ctx, message=message,
                                    revealed_signature=cls.generate_eve_counterfeit_signature(n_bits, rng),
                                    blinding=new_blinding())
            return cls._delivered(engine, package, n_bits, None,
                                  notes=["Rogue sender transmitted without any distribution stage."])

        if t == ThreatType.EVE_LOSS_EXPLOIT:
            lossy = ChannelModel(
                depolarizing=channel.depolarizing,
                intercept_rate=scenario.channel_intercept_rate,
                eta_loss=max(channel.eta_loss, scenario.loss_exploit_block_rate),
                noise_profile="lossy",
            )
            session = engine.distribute(sender, message, n_bits, rng, lossy, config=cfg)
            package = engine.reveal(session)
            package = package.copy(revealed_signature=cls.generate_eve_counterfeit_signature(n_bits, rng))
            return cls._delivered(engine, package, n_bits, session,
                                  notes=["Eve intercepted and blocked poorly measured tokens exploiting loss."])

        if t == ThreatType.EVE_CLONING:
            from .cloning import simulate_eve_cloning_step
            # Eve clones tokens with specified cloner
            cloning_ch = ChannelModel(
                depolarizing=channel.depolarizing,
                noise_profile="cloning",
                cloner_type=scenario.cloner_type,
                cloning_rate=scenario.cloning_rate,
            )
            session = engine.distribute(sender, message, n_bits, rng, cloning_ch, config=cfg)
            package = engine.reveal(session)

            # Eve uses her measurements on Clone 1 to build a counterfeit signature.
            # For each position in signature, Eve measured her retained clone.
            # With probability = cloner fidelity when basis matches, her measurement matches Alice's bit.
            # When Eve's basis doesn't match Alice's, outcome is random (50%).
            # Overall accuracy on Alice's bit: 1/2 * F + 1/2 * 0.5.
            eve_forged_sig = []
            for b, ba in session.signature:
                eve_basis = int(rng.integers(0, 2))
                # Eve measures her clone
                step = simulate_eve_cloning_step(b, ba, meas_basis_receiver=ba,
                                                cloner_type=scenario.cloner_type, rng=rng)
                eve_guess_bit = step["eve_outcome"]
                eve_forged_sig.append((eve_guess_bit, eve_basis))

            # Eve attempts forgery using her measured clone information
            forged_package = package.copy(revealed_signature=eve_forged_sig)
            tr = cls._delivered(engine, forged_package, n_bits, session,
                                notes=[f"Eve cloned tokens using {scenario.cloner_type} cloner and attempted signature forgery."])
            return tr

        if t == ThreatType.DISHONEST_BOB:
            session = engine.distribute(sender, message, n_bits, rng, channel, config=cfg)
            tr = cls.dishonest_bob_forward(
                engine, session.context.session_id,
                scenario.tampered_message_text or "[FORWARDED BY BOB] " + message, rng)
            tr.session, tr.channel_test, tr.channel_model = session, session.channel_test, session.channel_model
            return tr

        raise ValueError(f"Unknown scenario {t}")

    # ------------------------------------------------ partial intercept-resend
    @staticmethod
    def _eve_partial_intercept(
        engine,
        scenario: "ThreatScenarioConfig",
        message: str,
        n_bits: int,
        sender: str,
        rng: np.random.Generator,
        channel: Optional[ChannelModel],
        cfg: Optional[SessionConfig] = None,
    ) -> "Transcript":
        """
        Opt-in partial intercept-resend attack.

        Eve independently intercepts each transmitted token with probability *f*
        (per-token Bernoulli sampling), measures it in a randomly chosen basis,
        and resends the post-measurement state.  Non-intercepted tokens pass
        through untouched.

        The realised interception count is Binomial(n_stream, f) — it fluctuates
        around f * n_stream.  The configured fraction *f* is reported as the
        information-gain proxy (not a mutual-information calculation).

        When f = 1.0, every token is intercepted; this is mathematically
        equivalent to EVE_INTERCEPT with channel_intercept_rate = 1.0 when the
        background depolarizing rate is the same.

        Parameters
        ----------
        scenario.partial_intercept_fraction : float
            Must be in [0.05, 1.0] (inclusive).  Values outside this range
            raise ValueError.
        """
        f = scenario.partial_intercept_fraction
        if not isinstance(f, (int, float)):
            raise TypeError(
                f"partial_intercept_fraction must be a float in [0.05, 1.0], got {type(f).__name__!r}"
            )
        f = float(f)
        if f < 0.05 or f > 1.0:
            raise ValueError(
                f"partial_intercept_fraction must be in [0.05, 1.0], got {f!r}"
            )
        tapped = ChannelModel(
            depolarizing=channel.depolarizing,
            intercept_rate=f,
        )
        return engine.transmit(sender, message, n_bits, rng, tapped, config=cfg)

    @classmethod
    def eve_collective(cls, engine, theta: float, message: str, n_bits: int, sender: str,
                       rng: np.random.Generator, channel: ChannelModel,
                       config: Optional[SessionConfig] = None) -> Tuple[Transcript, EveCollectiveAdversary]:
        """Honest signer, every token probed by EveCollectiveAdversary. Returns the transcript and Eve's record."""
        eve = EveCollectiveAdversary(theta, channel)
        session = engine.distribute(sender, message, n_bits, rng, channel, config=config, adversary=eve)
        return cls._delivered(engine, engine.reveal(session), n_bits, session,
                              notes=[f"Eve probed every token with controlled-Ry(theta={theta:.3f})."]), eve

    @staticmethod
    def _delivered(engine, package, n_bits, session, notes=None) -> Transcript:
        cfg = session.config if session is not None else engine.config_for(package)
        kind = "chain" if cfg.delivery == "chain" else "direct"
        if session is not None and session.aborted:
            # The channel test aborted distribution: the signer never reveals, so nothing reaches the verifiers.
            return Transcript(kind=kind, link=LINK_SIGNER, n_bits=n_bits, package=package, results=[],
                              display={}, session=session, channel_test=session.channel_test,
                              channel_model=session.channel_model,
                              notes=list(notes or []) + ["Channel test alarm: signature never revealed."],
                              config=cfg)
        results, chain_notes = engine.deliver_session(package, session, cfg)
        return Transcript(kind=kind, link=LINK_SIGNER, n_bits=n_bits, package=package, results=results,
                          display={r.verifier: r for r in results}, session=session,
                          channel_test=session.channel_test if session else None,
                          channel_model=session.channel_model if session else None,
                          notes=list(notes or []) + chain_notes, config=cfg)
