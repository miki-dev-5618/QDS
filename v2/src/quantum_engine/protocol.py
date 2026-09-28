"""
Three-party teleportation-based QDS engine (Alice signs; Bob and Charlie verify).

Stages
  1. Distribution: Alice prepares random Pauli eigenstates; Bob and Charlie
     keep-or-forward their copies (symmetrisation); every held copy is
     teleported through the channel and measured in the verifier's basis,
     giving one eliminated state per copy. Sacrificed test tokens are
     interleaved at secret random stream positions and measured in their
     (later disclosed) preparation basis to estimate the channel QBER.
     The stream is sent in blocks; after each block the verifiers update the
     running test-error count and abort the rest of the stream as soon as the
     count is decisive (sequential early abort, see channel.py). Alice sends
     each verifier a commitment to (context, signature).
  2. Messaging: Alice reveals (message, context, signature, blinding) - only
     if the channel test passed. An aborted session is never revealed.
  3. Verification: each verifier checks independently (see verifier.py).
  4. Assessment: the blind detector (Tier 1 + Tier 2) classifies the
     observations; the response policy chooses none / watch / quarantine; the
     circuit breaker applies it; incident and transaction records are signed
     immediately. The injected scenario (ground truth) is attached only after
     the detector returns.
"""
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .audit import build_evidence, build_incident_record, build_record, evidence_hash
from .binding import SignedContext, SignedPackage, commitment, new_blinding
from .channel import ChannelModel, estimate_channel_qber
from .detection import QDSDetectionEngine, ThreatReport
from .elimination import OrthogonalEliminationEngine, SYMBOL_MAP
from .enforcement import (ChannelGuard, LatencyStats, LINK_FORWARD, LINK_SIGNER, OPEN, QUARANTINED,
                          RESET_PENDING, WATCH)
from .policy import ResponseDecision, ResponsePolicy, decide
from .router import SimulatedRouter
from .schedule import RandomSchedule
from .security import SecurityParameters
from .store import Store
from .symmetrisation import SymmetrisationManager
from .teleportation import TeleportJob, make_backend
from .transcript import SigningSession, Transcript
from .verifier import DistributionRecord, VerificationResult, VerifierNode

VERIFIERS = ("bob", "charlie")


@dataclass(frozen=True)
class Slot:
    """One token in the distribution stream."""
    kind: str                 # "sig" (signature copy) or "test" (sacrificed test token)
    verifier: Optional[str]   # holder of a signature copy
    pos: int                  # signature position (sig) or test index (test)
    copy: int                 # copy index within the position
    bit: int
    basis: int
    meas_basis: int


@dataclass
class QDSExecutionResult:
    transmission_id: str
    timestamp: float
    transcript: Transcript
    threat_report: ThreatReport
    enforcement: Dict[str, Any]
    latency: Dict[str, Any]
    response: Optional[ResponseDecision] = None
    backend: str = ""
    ground_truth: Dict[str, Any] = field(default_factory=dict)
    audit_cert: Optional[Dict[str, Any]] = None
    incident_cert: Optional[Dict[str, Any]] = None

    @property
    def channel_qber(self) -> float:
        ct = self.transcript.channel_test
        return ct.qber_estimate if ct else 0.0

    def to_dict(self) -> Dict[str, Any]:
        t = self.transcript
        session = t.session
        d: Dict[str, Any] = {
            "transmission_id": self.transmission_id,
            "timestamp": self.timestamp,
            "kind": t.kind,
            "link": t.link,
            "n_bits": t.n_bits,
            "backend": self.backend,
            "message_text": t.package.message,
            "context": t.package.context.to_dict(),
            "package": t.package.to_dict(),
            "revealed": bool(t.results),
            "alice": None,
            "channel": t.channel_test.to_dict() if t.channel_test else None,
            "symmetrisation": None,
            "bob": t.display["bob"].to_dict() if "bob" in t.display else None,
            "charlie": t.display["charlie"].to_dict() if "charlie" in t.display else None,
            "additional_verifications": [r.to_dict() for r in t.results
                                         if r not in t.display.values()],
            "threat_report": self.threat_report.to_dict(),
            "response": self.response.to_dict() if self.response else None,
            "enforcement": self.enforcement,
            "latency": self.latency,
            "ground_truth": self.ground_truth,
            "notes": t.notes,
            "audit": None if self.audit_cert is None else {
                "artifact_id": self.transmission_id,
                "payload_sha256": self.audit_cert["payload_sha256"],
                "chain_seq": self.audit_cert["record"]["chain"]["seq"],
                "post_quantum": any(s["post_quantum"] for s in self.audit_cert["signatures"]),
                "assurance": self.audit_cert["record"]["assurance"]["level"],
            },
        }
        if session is not None:
            d["alice"] = {
                "signed_message": session.message,
                "prepared_states": [list(s) for s in session.signature],
                "state_symbols": [SYMBOL_MAP[s] for s in session.signature],
            }
            d["symmetrisation"] = {"bob_actions": session.bob_actions, "charlie_actions": session.charlie_actions}
        return d


class TeleportationQDS:
    def __init__(
        self,
        params: Optional[SecurityParameters] = None,
        backend: Any = "qiskit",
        channel: Optional[ChannelModel] = None,
        clock: Callable[[], float] = time.time,
        store: Optional[Store] = None,
        audit=None,
        policy: Optional[ResponsePolicy] = None,
        schedule=None,
    ):
        self.params = params or SecurityParameters()
        self.backend = make_backend(backend) if isinstance(backend, str) else backend
        self.default_channel = channel or ChannelModel()
        self.clock = clock
        self.store = store or Store(":memory:")
        self.router = SimulatedRouter()
        self.policy = policy or ResponsePolicy(strong_alpha=self.params.strong_alpha)
        self.guard = ChannelGuard(self.policy, self.store, self.router, clock)
        self.verifiers: Dict[str, VerifierNode] = {
            n: VerifierNode(n, self.params, clock, store=self.store) for n in VERIFIERS}
        self.detector = QDSDetectionEngine(self.params)
        self.schedule = schedule or RandomSchedule()
        self.audit = audit
        self.latency = LatencyStats()
        self.last_accepted_package: Optional[SignedPackage] = None
        self.recent_packages: deque = deque(maxlen=50)

    # ------------------------------------------------------------ helpers
    def test_token_budget(self, n_bits: int) -> int:
        """Adaptive test allocation: more test tokens while the signer link is under suspicion."""
        base = max(self.params.min_test_tokens, n_bits)
        if self.guard.state(LINK_SIGNER) in (WATCH, RESET_PENDING):
            base *= self.params.watch_test_multiplier
        return base

    # ------------------------------------------------------------------ stages
    def distribute(
        self,
        sender: str,
        message: str,
        n_bits: int,
        rng: np.random.Generator,
        channel: Optional[ChannelModel] = None,
        prepare_copies: Optional[Callable[[List[Tuple[int, int]], np.random.Generator],
                                          Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]]] = None,
        adversary=None,
    ) -> SigningSession:
        self.guard.check_open(LINK_SIGNER)
        channel = channel or self.default_channel
        t_start = time.perf_counter_ns()

        signature = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, n_bits), rng.integers(0, 2, n_bits))]
        bob_copy, charlie_copy = list(signature), list(signature)
        if prepare_copies is not None:  # only a dishonest signer uses this
            bob_copy, charlie_copy = prepare_copies(signature, rng)

        ctx = SignedContext.new(sender, list(VERIFIERS), message, timestamp=self.clock(),
                                digest_alg=self.params.digest_alg)
        blinding = new_blinding()
        commit = commitment(ctx, signature, blinding)

        (bob_actions, charlie_actions, bob_held, charlie_held,
         bob_desc, charlie_desc) = SymmetrisationManager.perform_symmetrisation_swap(bob_copy, charlie_copy, rng)
        held = {"bob": bob_held, "charlie": charlie_held}
        desc = {"bob": bob_desc, "charlie": charlie_desc}

        slots: List[Slot] = []
        for v in VERIFIERS:
            for i, copies in enumerate(held[v]):
                for j, (b, ba) in enumerate(copies):
                    slots.append(Slot("sig", v, i, j, b, ba, self.schedule.basis(ctx, v, i, j, rng)))
        n_test = self.test_token_budget(n_bits)
        for j in range(n_test):
            b, ba = int(rng.integers(0, 2)), int(rng.integers(0, 2))
            slots.append(Slot("test", None, j, 0, b, ba, ba))

        # Verifiers pick the test-token positions secretly: the stream is a random interleaving.
        stream = [slots[i] for i in rng.permutation(len(slots))]
        events = (adversary.tap(stream, self.schedule.public, rng) if adversary is not None
                  else channel.sample_events(len(stream), rng))

        k_strong = estimate_channel_qber(n_test, 0, self.params.honest_qber, self.params.false_alarm_alpha,
                                         strong_alpha=self.params.strong_alpha).strong_threshold_errors
        outcomes: List[Any] = []
        tested = errors = 0
        for block in np.array_split(np.arange(len(stream)), max(1, self.params.abort_chunks)):
            if len(block) == 0:
                continue
            jobs = [TeleportJob(stream[i].bit, stream[i].basis, stream[i].meas_basis, *events[i]) for i in block]
            for i, out in zip(block, self.backend.run(jobs, rng)):
                outcomes.append(out)
                if stream[i].kind == "test":
                    tested += 1
                    errors += int(out.outcome != stream[i].bit)
            if errors > k_strong and len(outcomes) < len(stream):
                break  # decisive: the remaining tokens are never sent
        sent = len(outcomes)
        if adversary is not None:
            adversary.observe(stream[:sent], outcomes)

        eliminated: Dict[str, List[List[Optional[str]]]] = {
            v: [[None] * len(held[v][i]) for i in range(n_bits)] for v in VERIFIERS}
        for s, out in zip(stream[:sent], outcomes):
            if s.kind == "sig":
                eliminated[s.verifier][s.pos][s.copy] = OrthogonalEliminationEngine.eliminate_state_symbol(
                    s.meas_basis, out.outcome)
        eliminated_clean = {v: [[e for e in row if e is not None] for row in eliminated[v]] for v in VERIFIERS}

        channel_test = estimate_channel_qber(tested, errors, self.params.honest_qber, self.params.false_alarm_alpha,
                                             planned_count=n_test, strong_alpha=self.params.strong_alpha,
                                             tokens_sent=sent, tokens_planned=len(stream))
        self.router.carry(LINK_SIGNER, sent)
        observation_ms = (time.perf_counter_ns() - t_start) / 1e6

        for v in VERIFIERS:
            self.verifiers[v].receive_distribution(DistributionRecord(
                session_id=ctx.session_id, sender=sender, commitment=commit,
                eliminated=eliminated_clean[v], held_desc=desc[v],
                channel_test=channel_test, aborted=channel_test.alarm,
            ))

        return SigningSession(
            context=ctx, message=message, signature=signature, blinding=blinding, commitment=commit,
            copies={"bob": bob_copy, "charlie": charlie_copy},
            bob_actions=bob_actions, charlie_actions=charlie_actions,
            channel_test=channel_test, channel_model=channel,
            observation_ms=round(observation_ms, 3), tokens_sent=sent, tokens_planned=len(stream),
        )

    @staticmethod
    def reveal(session: SigningSession) -> SignedPackage:
        return SignedPackage(context=session.context, message=session.message,
                             revealed_signature=list(session.signature), blinding=session.blinding)

    def deliver(self, package: SignedPackage, to=VERIFIERS) -> List[VerificationResult]:
        self.guard.check_open(LINK_SIGNER)
        results = [self.verifiers[v].verify(package, "direct") for v in to]
        self.recent_packages.append(package)
        return results

    def forward(self, package: SignedPackage, from_verifier: str, to_verifier: str) -> VerificationResult:
        self.guard.check_open(LINK_FORWARD)
        self.router.carry(LINK_FORWARD, 1)
        return self.verifiers[to_verifier].verify(package.copy(forwarded_by=from_verifier), "forwarded")

    def transmit(self, sender: str, message: str, n_bits: int, rng: np.random.Generator,
                 channel: Optional[ChannelModel] = None) -> Transcript:
        """Honest end-to-end flow. An aborted session is not revealed."""
        session = self.distribute(sender, message, n_bits, rng, channel)
        package = self.reveal(session)
        if session.aborted:
            return Transcript(kind="direct", link=LINK_SIGNER, n_bits=n_bits, package=package, results=[],
                              display={}, session=session, channel_test=session.channel_test,
                              channel_model=session.channel_model,
                              notes=["Channel test alarm: signature never revealed."])
        results = self.deliver(package)
        return Transcript(kind="direct", link=LINK_SIGNER, n_bits=n_bits, package=package, results=results,
                          display={r.verifier: r for r in results}, session=session,
                          channel_test=session.channel_test, channel_model=session.channel_model)

    # ------------------------------------------------------------- assessment
    def assess(self, transcript: Transcript, ground_truth: Optional[Dict[str, Any]] = None,
               started_ns: Optional[int] = None) -> QDSExecutionResult:
        tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
        link = transcript.link

        t0 = time.perf_counter_ns()
        report = self.detector.classify(transcript.results, transcript.channel_test)
        t1 = time.perf_counter_ns()

        decision = decide(report, self.policy)
        direct = [r for r in transcript.results if r.mode == "direct"]
        all_accepted = transcript.kind == "direct" and bool(direct) and all(r.accepted for r in direct)
        transition = self.guard.apply(link, decision, tx_id, accepted=all_accepted and not report.is_threat_detected)
        purged = 0
        new_state = transition["new_state"] if transition else self.guard.state(link)
        if transition and new_state == QUARANTINED and link == LINK_SIGNER:
            sender = transcript.package.context.sender
            purged = sum(v.purge_pending(sender) for v in self.verifiers.values())
            self.guard.links[link].purged_records = purged
        t2 = time.perf_counter_ns()

        if all_accepted:
            self.last_accepted_package = transcript.package

        if transition and new_state == QUARANTINED:
            action = "link_quarantined"
        elif transition and new_state == WATCH:
            action = "link_watch"
        elif transition and transition["old_state"] == RESET_PENDING and new_state == OPEN:
            action = "probation_passed"
        elif report.is_threat_detected:
            action = "package_rejected"
        else:
            action = "none"
        enforcement: Dict[str, Any] = {
            "action": action, "link": link, "link_state": new_state, "purged_records": purged,
            "transition": transition,
            "incident_id": transition.get("incident_id") if transition else None,
        }

        session = transcript.session
        latency: Dict[str, Any] = {
            "channel_observation_ms": session.observation_ms if session else None,
            "detection_us": round((t1 - t0) / 1000, 2),
            "enforcement_us": round((t2 - t1) / 1000, 2),
            "incident_signing_us": None,
            "audit_signing_us": None,
            "protocol_ms": None,
            "early_abort": None if transcript.channel_test is None or not transcript.channel_test.early_abort else {
                "tokens_sent": transcript.channel_test.tokens_sent,
                "tokens_planned": transcript.channel_test.tokens_planned},
        }

        result = QDSExecutionResult(
            transmission_id=tx_id, timestamp=time.time(), transcript=transcript, threat_report=report,
            enforcement=enforcement, latency=latency, response=decision, backend=self.backend.name,
            ground_truth=dict(ground_truth or {}),
        )

        if self.audit is not None:
            tx = result.to_dict()
            evidence = build_evidence(tx)
            if enforcement["incident_id"]:
                t3 = time.perf_counter_ns()
                inc = build_incident_record(enforcement["incident_id"], transition, tx, evidence_hash(evidence),
                                            self.policy.to_dict())
                result.incident_cert = self.audit.issue(inc, enforcement["incident_id"])
                latency["incident_signing_us"] = round((time.perf_counter_ns() - t3) / 1000, 2)
            t4 = time.perf_counter_ns()
            record = build_record(result.to_dict(), self.params.to_dict(), self.policy.to_dict(), evidence,
                                  self.params.freshness_window_s)
            result.audit_cert = self.audit.issue(record, tx_id, evidence)
            latency["audit_signing_us"] = round((time.perf_counter_ns() - t4) / 1000, 2)

        if started_ns:
            latency["protocol_ms"] = round((time.perf_counter_ns() - started_ns) / 1e6, 2)
        self.latency.add(**{k: v for k, v in latency.items() if isinstance(v, (int, float))})
        enforcement["channel_state"] = self.guard.to_dict()
        return result

    def execute_protocol(self, message_text: str, n_bits: int = 16, sender: str = "alice",
                         scenario=None, rng: Optional[np.random.Generator] = None,
                         channel: Optional[ChannelModel] = None) -> QDSExecutionResult:
        """Run one transmission, optionally through an attack injector, then assess it blind."""
        from .threats import ThreatScenarioConfig, ThreatSuite, ThreatType

        rng = rng or np.random.default_rng()
        scenario = scenario or ThreatScenarioConfig(threat_type=ThreatType.AUTHENTIC)
        started = time.perf_counter_ns()
        transcript = ThreatSuite.run(self, scenario, message_text, n_bits, sender, rng, channel)
        result = self.assess(transcript, started_ns=started)
        # Ground truth is attached only after the detector has returned.
        cm = transcript.channel_model
        result.ground_truth = {
            "injected_scenario": scenario.threat_type.value,
            "hidden_channel": None if cm is None else {
                "depolarizing": cm.depolarizing, "intercept_rate": cm.intercept_rate,
                "expected_qber": round(cm.expected_qber(), 4)},
            "note": "Set by the attack injector for experiment reporting; never passed to verifiers or detector.",
        }
        return result
