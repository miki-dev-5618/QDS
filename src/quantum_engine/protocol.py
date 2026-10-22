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
     Evidence allocation (C2) is fixed before anything is sent, from
     observable inputs only (L, link state, heralded loss of the previous
     session): the Tier 1 test budget is the smallest count reaching the
     target detection power, and short signatures get an L-aware reserve of
     extra signature positions, distributed, symmetrised and measured exactly
     like the main copies and bound by a separate reserve commitment.
  2. Messaging: Alice reveals (message, context, signature, blinding) - only
     if the channel test passed. An aborted session is never revealed.
  3. Verification: each verifier checks independently (see verifier.py).
     If a verifier's stage-1 count is borderline it requests the reserve;
     Alice opens it (states + reserve blinding) only for her own revealed
     message, signature and context, so a substituted package never gains
     reserve evidence (and cannot use up the reserve of the genuine one). Each verifier evaluates a session's reserve at most
     ``max_reserve_openings`` times; no fresh quantum evidence is ever
     created after reveal.
  4. Assessment: the blind detector (Tier 1 + Tier 2) classifies the
     observations; the response policy chooses none / watch / quarantine; the
     circuit breaker applies it; incident and transaction records are signed
     immediately. The injected scenario (ground truth) is attached only after
     the detector returns.
"""
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .audit import build_evidence, build_incident_record, build_record, evidence_hash
from .binding import ReserveOpening, SignedContext, SignedPackage, commitment, new_blinding, reserve_commitment
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
    ibm_backend: Optional[str] = None
    calibration_date: Optional[str] = None
    effective_error_rate: Optional[float] = None

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
            "ibm_backend": self.ibm_backend,
            "calibration_date": self.calibration_date,
            "effective_error_rate": self.effective_error_rate,
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
            "allocation": session.allocation if session is not None else None,
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
        if channel is None:
            import os
            noise_env = os.environ.get("HEDWIG_NOISE_PROFILE")
            if noise_env == "ibm_fake" or (isinstance(backend, str) and "ibm_fake" in backend):
                from .channel import make_ibm_channel
                mode = "full" if (backend == "ibm_fake_full" or os.environ.get("HEDWIG_IBM_MODE") == "full") else "calibrated"
                self.default_channel = make_ibm_channel(mode=mode)
            elif noise_env == "lossy":
                from .channel import make_lossy_channel
                eta = float(os.environ.get("HEDWIG_ETA_LOSS", "0.1"))
                self.default_channel = make_lossy_channel(eta_loss=eta)
            else:
                self.default_channel = ChannelModel()
        else:
            self.default_channel = channel
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
        self.observed_loss = 0.0           # heralded loss fraction of the previous session (observable)
        self._signer_sessions: "OrderedDict[str, SigningSession]" = OrderedDict()  # Alice's own reserve state

    # ------------------------------------------------------------ helpers
    def allocation_plan(self, n_bits: int) -> Dict[str, Any]:
        """Evidence budget for the next session, from observable state only (never the injected scenario)."""
        state = self.guard.state(LINK_SIGNER)
        suspicious = state in (WATCH, RESET_PENDING)
        tests = self.params.test_token_plan(n_bits, suspicious, self.observed_loss)
        reserve = self.params.reserve_plan(n_bits, self.observed_loss)
        return {"link_state": state, "n_bits": n_bits, "observed_loss": round(self.observed_loss, 4),
                "test": tests, "reserve": reserve}

    def test_token_budget(self, n_bits: int) -> int:
        """Tier 1 test tokens for the next session (see ``allocation_plan``)."""
        return self.allocation_plan(n_bits)["test"]["test_tokens"]

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

        allocation = self.allocation_plan(n_bits)
        signature = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, n_bits), rng.integers(0, 2, n_bits))]
        bob_copy, charlie_copy = list(signature), list(signature)
        if prepare_copies is not None:  # only a dishonest signer uses this
            bob_copy, charlie_copy = prepare_copies(signature, rng)
        n_rsv = allocation["reserve"]["reserve_bits"]
        reserve = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, n_rsv), rng.integers(0, 2, n_rsv))]
        rsv_bob, rsv_charlie = list(reserve), list(reserve)
        if prepare_copies is not None and n_rsv:
            rsv_bob, rsv_charlie = prepare_copies(reserve, rng)

        ctx = SignedContext.new(sender, list(VERIFIERS), message, timestamp=self.clock(),
                                digest_alg=self.params.digest_alg)
        blinding = new_blinding()
        commit = commitment(ctx, signature, blinding)
        rsv_blinding = new_blinding()
        rsv_commit = reserve_commitment(ctx, reserve, rsv_blinding) if n_rsv else None

        (bob_actions, charlie_actions, bob_held, charlie_held,
         bob_desc, charlie_desc) = SymmetrisationManager.perform_symmetrisation_swap(bob_copy, charlie_copy, rng)
        held = {"bob": bob_held, "charlie": charlie_held}
        desc = {"bob": bob_desc, "charlie": charlie_desc}
        if n_rsv:
            _, _, rb_held, rc_held, _, _ = SymmetrisationManager.perform_symmetrisation_swap(rsv_bob, rsv_charlie, rng)
            rsv_held = {"bob": rb_held, "charlie": rc_held}
        else:
            rsv_held = {v: [] for v in VERIFIERS}

        slots: List[Slot] = []
        for v in VERIFIERS:
            for i, copies in enumerate(held[v]):
                for j, (b, ba) in enumerate(copies):
                    slots.append(Slot("sig", v, i, j, b, ba, self.schedule.basis(ctx, v, i, j, rng)))
            for i, copies in enumerate(rsv_held[v]):
                for j, (b, ba) in enumerate(copies):
                    # Reserve copies use basis indices after the main positions so schedules never repeat.
                    slots.append(Slot("rsv", v, i, j, b, ba, self.schedule.basis(ctx, v, n_bits + i, j, rng)))
        n_test = allocation["test"]["test_tokens"]
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
        total_lost = 0
        for block in np.array_split(np.arange(len(stream)), max(1, self.params.abort_chunks)):
            if len(block) == 0:
                continue
            jobs = []
            for i in block:
                # Lossy profile: token is lost with probability eta_loss (heralded erasure)
                is_lost = bool(channel.eta_loss > 0.0 and rng.random() < channel.eta_loss)
                jobs.append(
                    TeleportJob(
                        stream[i].bit,
                        stream[i].basis,
                        stream[i].meas_basis,
                        events[i][0],
                        events[i][1],
                        damping_gamma=(channel.amp_damping_gamma if channel.noise_profile == "amp_damping" or channel.amp_damping_gamma > 0 else 0.0),
                        phase_damping_gamma=channel.phase_damping_gamma,
                        damping_target=channel.damping_target,
                        readout_p01=(channel.readout_p01 if channel.noise_profile == "readout" or channel.readout_p01 > 0 else 0.0),
                        readout_p10=(channel.readout_p10 if channel.noise_profile == "readout" or channel.readout_p10 > 0 else 0.0),
                        readout_location=channel.readout_location,
                        is_lost=is_lost,
                    )
                )
            for i, out in zip(block, self.backend.run(jobs, rng)):
                outcomes.append(out)
                if out.is_lost:
                    total_lost += 1
                elif stream[i].kind == "test":
                    tested += 1
                    errors += int(out.outcome != stream[i].bit)
            if errors > k_strong and len(outcomes) < len(stream):
                break  # decisive: the remaining tokens are never sent
        sent = len(outcomes)
        if adversary is not None:
            adversary.observe(stream[:sent], outcomes)

        surviving_tokens = sent - total_lost

        channel_test = estimate_channel_qber(tested, errors, self.params.honest_qber, self.params.false_alarm_alpha,
                                             planned_count=n_test, strong_alpha=self.params.strong_alpha,
                                             tokens_sent=sent, tokens_planned=len(stream),
                                             tokens_received=surviving_tokens, tokens_lost=total_lost)

        insufficient_tokens = bool(
            not channel_test.alarm
            and total_lost > 0
            and len(stream) > 0
            and surviving_tokens < (self.params.min_surviving_ratio * len(stream))
        )

        eliminated: Dict[str, List[List[Optional[str]]]] = {
            v: [[None] * len(held[v][i]) for i in range(n_bits)] for v in VERIFIERS}
        for s, out in zip(stream[:sent], outcomes):
            if s.kind == "sig":
                if out.is_lost:
                    # Token lost: heralded erasure, receiver excludes it from eliminated states
                    eliminated[s.verifier][s.pos][s.copy] = None
                else:
                    eliminated[s.verifier][s.pos][s.copy] = OrthogonalEliminationEngine.eliminate_state_symbol(
                        s.meas_basis, out.outcome)
        rsv_elim: Dict[str, List[List[Optional[str]]]] = {
            v: [[None] * len(rsv_held[v][i]) for i in range(n_rsv)] for v in VERIFIERS}
        for s, out in zip(stream[:sent], outcomes):
            if s.kind == "rsv" and not out.is_lost:
                rsv_elim[s.verifier][s.pos][s.copy] = OrthogonalEliminationEngine.eliminate_state_symbol(
                    s.meas_basis, out.outcome)
        eliminated_clean = {v: [[e for e in row if e is not None] for row in eliminated[v]] for v in VERIFIERS}
        rsv_clean = {v: [[e for e in row if e is not None] for row in rsv_elim[v]] for v in VERIFIERS}
        self.observed_loss = (total_lost / sent) if sent else 0.0

        self.router.carry(LINK_SIGNER, sent)
        observation_ms = (time.perf_counter_ns() - t_start) / 1e6

        for v in VERIFIERS:
            self.verifiers[v].receive_distribution(DistributionRecord(
                session_id=ctx.session_id, sender=sender, commitment=commit,
                eliminated=eliminated_clean[v], held_desc=desc[v],
                channel_test=channel_test, aborted=channel_test.alarm,
                insufficient_tokens=insufficient_tokens,
                tokens_received=surviving_tokens, tokens_planned=len(stream),
                reserve_eliminated=rsv_clean[v], reserve_commitment=rsv_commit,
            ))

        session = SigningSession(
            context=ctx, message=message, signature=signature, blinding=blinding, commitment=commit,
            copies={"bob": bob_copy, "charlie": charlie_copy},
            bob_actions=bob_actions, charlie_actions=charlie_actions,
            channel_test=channel_test, channel_model=channel,
            observation_ms=round(observation_ms, 3), tokens_sent=sent, tokens_planned=len(stream),
            tokens_received=surviving_tokens, insufficient_tokens=insufficient_tokens,
            reserve=reserve, reserve_blinding=rsv_blinding if n_rsv else None, reserve_commitment=rsv_commit,
            allocation=allocation,
        )
        if n_rsv:
            self._signer_sessions[ctx.session_id] = session
            while len(self._signer_sessions) > 1000:
                self._signer_sessions.popitem(last=False)
        return session

    @staticmethod
    def reveal(session: SigningSession) -> SignedPackage:
        return SignedPackage(context=session.context, message=session.message,
                             revealed_signature=list(session.signature), blinding=session.blinding)

    @staticmethod
    def open_reserve(session: Optional[SigningSession], package: SignedPackage) -> Optional[ReserveOpening]:
        """
        Alice's answer to a borderline request: the reserve opening, but only for her own revealed
        message, signature and context. A package with any substituted field gets nothing.
        """
        if session is None or not session.reserve or session.reserve_blinding is None:
            return None
        if (package.context.to_dict() != session.context.to_dict() or package.message != session.message
                or [tuple(x) for x in package.revealed_signature] != [tuple(x) for x in session.signature]):
            return None
        return ReserveOpening(states=tuple(tuple(x) for x in session.reserve), blinding=session.reserve_blinding)

    def deliver(self, package: SignedPackage, to=VERIFIERS,
                session: Optional[SigningSession] = None) -> List[VerificationResult]:
        self.guard.check_open(LINK_SIGNER)
        results = [self.verifiers[v].verify(package, "direct") for v in to]
        for i, r in enumerate(results):
            if r.reserve_requested:
                signer = session or self._signer_sessions.get(package.context.session_id)
                opening = self.open_reserve(signer, package)
                if opening is not None:   # one bounded second look; the verifier enforces the limit
                    results[i] = self.verifiers[r.verifier].verify(package.copy(reserve=opening), "direct")
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
            note = ("Channel test alarm: signature never revealed." if session.channel_test.alarm
                    else f"INSUFFICIENT_TOKENS: surviving tokens {session.tokens_received}/{session.tokens_planned} below safety threshold.")
            return Transcript(kind="direct", link=LINK_SIGNER, n_bits=n_bits, package=package, results=[],
                              display={}, session=session, channel_test=session.channel_test,
                              channel_model=session.channel_model,
                              notes=[note])
        results = self.deliver(package, session=session)
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

        cm = transcript.channel_model or self.default_channel
        ibm_backend = getattr(self.backend, "backend_name", None) or getattr(cm, "ibm_backend", None)
        cal_date = getattr(self.backend, "calibration_date", None) or getattr(cm, "calibration_date", None)
        eff_err = getattr(self.backend, "effective_error_rate", None) or getattr(cm, "effective_error_rate", None)

        result = QDSExecutionResult(
            transmission_id=tx_id, timestamp=time.time(), transcript=transcript, threat_report=report,
            enforcement=enforcement, latency=latency, response=decision, backend=self.backend.name,
            ground_truth=dict(ground_truth or {}),
            ibm_backend=ibm_backend,
            calibration_date=cal_date,
            effective_error_rate=eff_err,
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
