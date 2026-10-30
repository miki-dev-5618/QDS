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

Optional N-verifier extension (``roster.py``): a session may name a fixed,
ordered roster of 2-10 pre-enrolled verifiers (default: Bob and Charlie), a
delivery mode (direct-to-all or one linear chain) and a maximum forwarding
depth H, all fixed before distribution and bound into the commitment. Alice
prepares one copy per roster member per position; with more than two
recipients each copy is reassigned to a uniformly random final holder
(``UniformHolderAssignment``). Chain forwarding is classical package
transfer: every downstream recipient checks against its own initial evidence
at its validated depth. Each verification is a ledger event with a unique id
and parent link (``ledger.py``); forwarding events after the reveal are
signed as separate audit records linked to their parent record.
"""
import time
import uuid
import copy
from collections import OrderedDict, deque
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .audit import build_evidence, build_incident_record, build_record, build_transfer_record, evidence_hash
from .binding import ReserveOpening, SignedContext, SignedPackage, commitment, new_blinding, reserve_commitment
from .channel import ChannelModel, estimate_channel_qber
from .detection import QDSDetectionEngine, ThreatReport, ThreatClassification
import inspect

from .elimination import OrthogonalEliminationEngine, SYMBOL_MAP
from .ledger import EventLedger, participant_matrix, session_outcome
from .enforcement import (ChannelGuard, LatencyStats, LINK_FORWARD, LINK_SIGNER, OPEN, QUARANTINED,
                          RESET_PENDING, WATCH, ChannelQuarantined, edge_scope, path_scope)
from .topology import Topology, legacy_star
from .routing import allocate, RoutingPolicy, RoutePlan, RouteUnavailable, required_scopes, freshness
from .multihop import hop_jobs, count_traversal
from .policy import ResponseDecision, ResponsePolicy, decide
from .roster import DEFAULT_CONFIG, VERIFIER_POOL, ConfigurationError, SessionConfig
from .router import SimulatedRouter
from .schedule import RandomSchedule
from .security import SecurityParameters
from .store import Store
from .symmetrisation import SymmetrisationManager, UniformHolderAssignment
from .teleportation import TeleportJob, make_backend
from .transcript import SigningSession, Transcript
from .verifier import DistributionRecord, VerificationResult, VerifierNode

VERIFIERS = ("bob", "charlie")   # the default roster; see roster.py for the enrolled pool


class UnknownParticipant(ConfigurationError):
    """A transfer addressed to an identity that is not an enrolled verifier."""


ForwardHook = Callable[[str, str, SignedPackage, VerificationResult], Tuple[str, SignedPackage, Optional[str]]]


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
    transfer_records: List[Dict[str, Any]] = field(default_factory=list)   # linked forwarding audit records

    @property
    def channel_qber(self) -> float:
        ct = self.transcript.channel_test
        return ct.qber_estimate if ct else 0.0

    def to_dict(self) -> Dict[str, Any]:
        t = self.transcript
        session = t.session
        cfg = t.config or (session.config if session is not None else DEFAULT_CONFIG)
        aborted = bool(session is not None and session.aborted)
        from .ledger import event_summary
        rows = participant_matrix(cfg, [event_summary(r, r.forwarded_by or r.claimed_sender) for r in t.results],
                                  aborted)
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
                                         if r is not t.display.get("bob") and r is not t.display.get("charlie")],
            "session_config": cfg.to_dict(),
            "session_outcome": session_outcome(cfg, rows, aborted),
            "participants": rows,
            "events": [{"event_id": r.event_id, "verifier": r.verifier, "mode": r.mode, "depth": r.depth,
                        "sender": r.forwarded_by or r.claimed_sender, "parent_event_id": r.parent_event_id,
                        "status": r.status} for r in t.results],
            "transfer_records": self.transfer_records,
            "threat_report": self.threat_report.to_dict(),
            "response": self.response.to_dict() if self.response else None,
            "enforcement": self.enforcement,
            "latency": self.latency,
            "ground_truth": self.ground_truth,
            "notes": t.notes,
            "allocation": session.allocation if session is not None else None,
            "routing": {"plan": session.route_plan.to_dict(), "execution": copy.deepcopy(session.route_execution)}
                       if session is not None and session.route_plan else None,
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
            if not cfg.is_default:
                d["symmetrisation"]["model"] = ("keep-or-forward" if cfg.n == 2 else "uniform final holder")
                d["symmetrisation"]["actions"] = session.actions
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
        topology=None,
        routing_policy=None,
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
        saved_topology = self.store.get_json("active_topology")
        self.topology = (Topology.preset(topology) if isinstance(topology, str) else topology) or (
            Topology.from_dict(saved_topology) if saved_topology else legacy_star())
        self.routing_policy = routing_policy or RoutingPolicy()
        self.edge_injections = {}  # simulator ground truth, never a planner input
        self.router.configure_topology(self.topology)
        # Nodes of the default roster exist from the start; other enrolled identities get one when a
        # roster first includes them (see ``node``).
        self.verifiers: Dict[str, VerifierNode] = {
            n: VerifierNode(n, self.params, clock, store=self.store) for n in VERIFIERS}
        self.ledger = EventLedger(self.store)
        self.default_config: SessionConfig = DEFAULT_CONFIG
        self.detector = QDSDetectionEngine(self.params)
        self.schedule = schedule or RandomSchedule()
        self.audit = audit
        if self.audit:
            for correction in self.guard.policy_corrections:
                from .audit import AUDIT_VERSION
                self.audit.issue({"version": AUDIT_VERSION, "kind": "policy_correction", "issued_at": self.clock(),
                    "transition": correction}, "POLICY-" + uuid.uuid4().hex)
        self.latency = LatencyStats()
        self.last_accepted_package: Optional[SignedPackage] = None
        self.recent_packages: deque = deque(maxlen=50)
        self.observed_loss = 0.0           # heralded loss fraction of the previous session (observable)
        self._signer_sessions: "OrderedDict[str, SigningSession]" = OrderedDict()  # Alice's own reserve state

    def activate_topology(self, document, actor="admin"):
        topology = Topology.from_dict(document)
        self.store.put_json("active_topology", topology.to_dict())
        self.store.put_json("topology_activation:" + str(uuid.uuid4()),
            {"digest": topology.digest, "actor": actor, "timestamp": self.clock()})
        self.topology = topology
        self.edge_injections = {}
        self.router.configure_topology(topology)
        if self.audit:
            from .audit import AUDIT_VERSION
            self.audit.issue({"version": AUDIT_VERSION, "kind": "topology_activation", "issued_at": self.clock(),
                "topology": topology.to_dict(), "digest": topology.digest, "actor": actor}, "TOPO-" + uuid.uuid4().hex)
        return topology

    def preview_routes(self, config=None):
        """Plan the next send without preparing tokens or recording a session."""
        cfg = config or self.default_config
        cfg.validate()
        with self.guard.snapshot() as (states, revision):
            try:
                plan = allocate(self.topology, cfg.roster, states, revision, "PREVIEW", self.clock(),
                    self.routing_policy, self.store.get_json("edge_probes", {}))
                return {"status": "ready", "plan": plan.to_dict(), "prepared_tokens": 0}
            except RouteUnavailable as exc:
                return {**exc.payload(), "prepared_tokens": 0}

    def _check_plan(self, plan):
        document = plan.to_dict()
        policy = RoutingPolicy(**document["policy"])
        self.guard.check_scopes(required_scopes(plan), allow_watch=policy.allow_watch, allow_probation=policy.allow_probation)
        if not policy.allow_unmonitored:
            probes = self.store.get_json("edge_probes", {})
            for route in document["routes"].values():
                for scope in route["edge_scopes"]:
                    if freshness(probes.get(scope), self.clock(), policy) != "fresh":
                        raise ChannelQuarantined(scope, {"reason": "monitoring_required"}, "Required edge monitoring is missing or stale")

    def _abort_route(self, session, reason, scope=None):
        session.route_abort = reason
        session.route_execution.update(status="aborted", abort_reason=reason, stopping_scope=scope,
                                       reveal_allowed=False)
        for v in session.config.roster:
            record = self.node(v).records.get(session.context.session_id)
            if record:
                record.aborted = True
        self.store.save_route_execution(session.context.session_id, session.route_execution)

    # ------------------------------------------------------------ helpers
    def node(self, name: str) -> VerifierNode:
        """The verifier node of an enrolled identity (created on first use)."""
        if name not in VERIFIER_POOL:
            raise UnknownParticipant(f"'{name}' is not an enrolled verifier.")
        if name not in self.verifiers:
            self.verifiers[name] = VerifierNode(name, self.params, self.clock, store=self.store)
        return self.verifiers[name]

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
        config: Optional[SessionConfig] = None,
    ) -> SigningSession:
        cfg = config or self.default_config
        cfg.validate()                       # invalid configurations never reach evidence preparation
        roster = list(cfg.roster)
        self.guard.check_open(LINK_SIGNER)
        channel = channel or self.default_channel
        t_start = time.perf_counter_ns()
        topology = self.topology
        injections = dict(self.edge_injections)
        if sender != topology.signer:
            raise ConfigurationError("Authenticated signer does not match topology signer")
        legacy = topology.digest == legacy_star().digest
        if not hasattr(self.backend, "run_routes") and (not legacy or injections):
            raise ConfigurationError("This backend has no multi-hop calibration; use statevector or qiskit")
        ctx = SignedContext.new(sender, roster, message, timestamp=self.clock(),
                                digest_alg=self.params.digest_alg, delivery=cfg.delivery, max_depth=cfg.max_depth)
        with self.guard.snapshot() as (states, revision):
            try:
                route_plan = allocate(topology, roster, states, revision, ctx.session_id, self.clock(),
                    self.routing_policy, self.store.get_json("edge_probes", {}))
            except RouteUnavailable as exc:
                self.store.put_json("route_refusal:" + ctx.session_id,
                    {**exc.payload(), "timestamp": self.clock(), "session_id": ctx.session_id})
                raise
        plan = route_plan.to_dict()
        previous = next((row["plan"] for row in self.store.route_history()
                         if row["plan"]["roster"] == roster and row["plan"]["signer"] == sender), None)
        if previous:
            plan["previous_session_id"] = previous["session_id"]
            for v, route in plan["routes"].items():
                old = previous["routes"][v]
                route["previous_route"] = {"session_id": previous["session_id"], "edges": old["edges"], "nodes": old["nodes"]}
                route["rerouted"] = old["route_id"] != route["route_id"]
        import json
        route_plan = RoutePlan(json.dumps(plan, sort_keys=True))
        self.store.save_route_plan(plan)
        self.router.configure_topology(topology, route_plan)
        route_edges = {v: [topology.edges[e] for e in r["edges"]] for v, r in plan["routes"].items()}
        # A per-basis upper envelope stochastically dominates the heterogeneous
        # honest Bernoulli errors; never test a heterogeneous stream at its mean.
        route_params = {v: replace(self.params, honest_qber=(self.params.honest_qber + r["qber_bound"]
                                    - 2*self.params.honest_qber*r["qber_bound"]))
                        for v, r in plan["routes"].items()}
        params = replace(self.params, honest_qber=max(p.honest_qber for p in route_params.values()))
        expected_loss = max(1-r["survival"] for r in plan["routes"].values())
        suspicious = any(states.get(s, {}).get("state") in (WATCH, RESET_PENDING) for s in required_scopes(plan))
        allocation = {"link_state": self.guard.state(LINK_SIGNER), "n_bits": n_bits,
            "observed_loss": self.observed_loss, "expected_route_loss": expected_loss,
            "test": params.test_token_plan(n_bits, suspicious, max(expected_loss, self.observed_loss)),
            "reserve": params.reserve_plan(n_bits, max(expected_loss, self.observed_loss)),
            "route_honest_qber_bound": params.honest_qber}
        signature = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, n_bits), rng.integers(0, 2, n_bits))]
        copies = self._prepare(signature, rng, roster, prepare_copies)
        n_rsv = allocation["reserve"]["reserve_bits"]
        reserve = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, n_rsv), rng.integers(0, 2, n_rsv))]
        rsv_copies = self._prepare(reserve, rng, roster, prepare_copies if n_rsv else None)

        blinding = new_blinding()
        commit = commitment(ctx, signature, blinding)
        rsv_blinding = new_blinding()
        rsv_commit = reserve_commitment(ctx, reserve, rsv_blinding) if n_rsv else None

        actions, held, desc = self._symmetrise(copies, roster, rng)
        if n_rsv:
            _, rsv_held, _ = self._symmetrise(rsv_copies, roster, rng)
        else:
            rsv_held = {v: [] for v in roster}

        slots: List[Slot] = []
        for v in roster:
            for i, copies in enumerate(held[v]):
                for j, (b, ba) in enumerate(copies):
                    slots.append(Slot("sig", v, i, j, b, ba, self.schedule.basis(ctx, v, i, j, rng)))
            for i, copies in enumerate(rsv_held[v]):
                for j, (b, ba) in enumerate(copies):
                    # Reserve copies use basis indices after the main positions so schedules never repeat.
                    slots.append(Slot("rsv", v, i, j, b, ba, self.schedule.basis(ctx, v, n_bits + i, j, rng)))
        n_test = allocation["test"]["test_tokens"]
        if not legacy:
            allocation["test"]["tokens_per_route"] = n_test
            n_test *= len(roster)
            allocation["test"]["test_tokens"] = n_test
        for j in range(n_test):
            b, ba = int(rng.integers(0, 2)), int(rng.integers(0, 2))
            slots.append(Slot("test", roster[j % len(roster)], j, 0, b, ba, ba))

        # Verifiers pick the test-token positions secretly: the stream is a random interleaving.
        stream = [slots[i] for i in rng.permutation(len(slots))]
        events = (adversary.tap(stream, self.schedule.public, rng) if adversary is not None
                  else channel.sample_events(len(stream), rng))

        family_divisor = 1 if legacy else 2  # pooled + route-test families
        k_strong = estimate_channel_qber(n_test, 0, params.honest_qber, params.false_alarm_alpha / family_divisor,
                                         strong_alpha=params.strong_alpha / family_divisor).strong_threshold_errors
        outcomes: List[Any] = []
        tested = errors = 0
        total_lost = 0
        counters = {}
        route_abort = stopping_scope = None
        route_stats = {v: {"planned": sum(s.verifier == v for s in stream), "attempted": 0,
            "received": 0, "lost": 0, "test_planned": sum(s.kind == "test" and s.verifier == v for s in stream),
            "tested": 0, "errors": 0, "edges": {}} for v in roster}
        for block in np.array_split(np.arange(len(stream)), max(1, self.params.abort_chunks)):
            if len(block) == 0:
                continue
            try:
                with self.guard.snapshot():
                    self._check_plan(route_plan)
                    jobs = [hop_jobs(stream[i], route_edges[stream[i].verifier], events[i], channel,
                                     injections, rng) for i in block]
                    block_outcomes = (self.backend.run_routes(jobs, rng) if hasattr(self.backend, "run_routes")
                                      else self.backend.run([j[0] for j in jobs], rng))
                    for i, hop_stream, out in zip(block, jobs, block_outcomes):
                        slot = stream[i]
                        stats = route_stats[slot.verifier]
                        count_traversal(route_edges[slot.verifier], hop_stream, counters, self.router, topology.digest)
                        count_traversal(route_edges[slot.verifier], hop_stream, stats["edges"])
                        stats["attempted"] += 1
                        stats["received"] += int(not out.is_lost)
                        stats["lost"] += int(out.is_lost)
                        outcomes.append(out)
                        if out.is_lost:
                            total_lost += 1
                        elif slot.kind == "test":
                            tested += 1
                            err = int(out.outcome != slot.bit)
                            errors += err
                            stats["tested"] += 1
                            stats["errors"] += err
            except ChannelQuarantined as exc:
                route_abort, stopping_scope = str(exc), exc.link
                break
            if errors > k_strong and len(outcomes) < len(stream):
                break  # decisive: the remaining tokens are never sent
        sent = len(outcomes)
        if adversary is not None:
            adversary.observe(stream[:sent], outcomes)

        surviving_tokens = sent - total_lost

        channel_test = estimate_channel_qber(tested, errors, params.honest_qber, params.false_alarm_alpha / family_divisor,
                                             planned_count=n_test, strong_alpha=params.strong_alpha / family_divisor,
                                             tokens_sent=sent, tokens_planned=len(stream),
                                             tokens_received=surviving_tokens, tokens_lost=total_lost)

        insufficient_tokens = bool(
            not channel_test.alarm
            and total_lost > 0
            and len(stream) > 0
            and surviving_tokens < (self.params.min_surviving_ratio * len(stream))
        )
        # Bonferroni route tests, with fixed planned counts under losses/early
        # stopping. A missing recipient cannot hide behind global survival.
        route_tests = {}
        for v, stats in route_stats.items():
            rp = route_params[v]
            rt = estimate_channel_qber(stats["tested"], stats["errors"], rp.honest_qber,
                params.false_alarm_alpha / (family_divisor * len(roster)), planned_count=stats["test_planned"],
                strong_alpha=params.strong_alpha / (family_divisor * len(roster)),
                tokens_sent=stats["attempted"], tokens_planned=stats["planned"],
                tokens_received=stats["received"], tokens_lost=stats["lost"])
            route_tests[v] = rt.to_dict()
            if rt.alarm and not channel_test.alarm:
                route_abort = "Route-specific channel test alarm: " + v
            if (stats["received"] < params.min_surviving_ratio * stats["planned"] or
                    stats["tested"] < max(1, params.min_surviving_ratio * stats["test_planned"])):
                insufficient_tokens = True

        eliminated: Dict[str, List[List[Optional[str]]]] = {
            v: [[None] * len(held[v][i]) for i in range(n_bits)] for v in roster}
        for s, out in zip(stream[:sent], outcomes):
            if s.kind == "sig":
                if out.is_lost:
                    # Token lost: heralded erasure, receiver excludes it from eliminated states
                    eliminated[s.verifier][s.pos][s.copy] = None
                else:
                    eliminated[s.verifier][s.pos][s.copy] = OrthogonalEliminationEngine.eliminate_state_symbol(
                        s.meas_basis, out.outcome)
        rsv_elim: Dict[str, List[List[Optional[str]]]] = {
            v: [[None] * len(rsv_held[v][i]) for i in range(n_rsv)] for v in roster}
        for s, out in zip(stream[:sent], outcomes):
            if s.kind == "rsv" and not out.is_lost:
                rsv_elim[s.verifier][s.pos][s.copy] = OrthogonalEliminationEngine.eliminate_state_symbol(
                    s.meas_basis, out.outcome)
        eliminated_clean = {v: [[e for e in row if e is not None] for row in eliminated[v]] for v in roster}
        rsv_clean = {v: [[e for e in row if e is not None] for row in rsv_elim[v]] for v in roster}
        self.observed_loss = (total_lost / sent) if sent else 0.0

        observation_ms = (time.perf_counter_ns() - t_start) / 1e6

        for v in roster:
            self.node(v).receive_distribution(DistributionRecord(
                session_id=ctx.session_id, sender=sender, commitment=commit,
                eliminated=eliminated_clean[v], held_desc=desc[v],
                channel_test=channel_test, aborted=channel_test.alarm or route_abort is not None,
                insufficient_tokens=insufficient_tokens,
                tokens_received=route_stats[v]["received"], tokens_planned=route_stats[v]["planned"],
                reserve_eliminated=rsv_clean[v], reserve_commitment=rsv_commit,
                config=cfg,
                security_params=route_params[v],
            ))
        self.ledger.register_session(ctx.session_id, sender, cfg, ctx.timestamp)

        session = SigningSession(
            context=ctx, message=message, signature=signature, blinding=blinding, commitment=commit,
            copies=copies,
            bob_actions=actions.get("bob", []), charlie_actions=actions.get("charlie", []),
            config=cfg, actions=actions,
            channel_test=channel_test, channel_model=channel,
            observation_ms=round(observation_ms, 3), tokens_sent=sent, tokens_planned=len(stream),
            tokens_received=surviving_tokens, insufficient_tokens=insufficient_tokens,
            reserve=reserve, reserve_blinding=rsv_blinding if n_rsv else None, reserve_commitment=rsv_commit,
            allocation=allocation,
            route_plan=route_plan, route_tests=route_tests, route_abort=route_abort, security_params=params,
            edge_ground_truth={eid: dict(cm.__dict__) for eid, cm in injections.items()},
            route_execution={"status": "aborted" if channel_test.alarm or route_abort or insufficient_tokens else "completed",
                "timestamp": self.clock(), "recipients": route_stats, "edges": counters,
                "abort_reason": route_abort or ("channel_alarm" if channel_test.alarm else (
                    "insufficient_recipient_evidence" if insufficient_tokens else None)),
                "stopping_scope": stopping_scope, "attempted": sent, "planned": len(stream),
                "reveal_allowed": not (channel_test.alarm or route_abort or insufficient_tokens),
                "route_tests": route_tests, "resource_convention": "one Bell pair consumed per edge attempt",
                "backend": self.backend.name},
        )
        self.store.save_route_execution(ctx.session_id, session.route_execution)
        if n_rsv:
            self._signer_sessions[ctx.session_id] = session
            while len(self._signer_sessions) > 1000:
                self._signer_sessions.popitem(last=False)
        return session

    @staticmethod
    def _prepare(states: List[Tuple[int, int]], rng: np.random.Generator, roster: List[str],
                 prepare_copies=None) -> Dict[str, List[Tuple[int, int]]]:
        """One initial copy per roster member; a dishonest signer's hook may make them differ."""
        if prepare_copies is None:
            return {v: list(states) for v in roster}
        if "roster" in inspect.signature(prepare_copies).parameters:
            return prepare_copies(states, rng, roster=roster)
        first, second = prepare_copies(states, rng)          # original two-recipient hook
        if len(roster) != 2:
            raise ConfigurationError("This preparation hook supports exactly two recipients.")
        return {roster[0]: first, roster[1]: second}

    @staticmethod
    def _symmetrise(copies: Dict[str, List[Tuple[int, int]]], roster: List[str], rng: np.random.Generator):
        """(actions, held, desc). Two recipients: keep-or-forward; more: uniform final holder."""
        if len(roster) == 2:
            a, b = roster
            a_act, b_act, a_held, b_held, a_desc, b_desc = SymmetrisationManager.perform_symmetrisation_swap(
                copies[a], copies[b], rng)
            if (a, b) != ("bob", "charlie"):
                rename = lambda d: [[x.replace("Bob", a.capitalize()).replace("Charlie", b.capitalize())
                                     for x in row] for row in d]
                a_desc, b_desc = rename(a_desc), rename(b_desc)
            return {a: a_act, b: b_act}, {a: a_held, b: b_held}, {a: a_desc, b: b_desc}
        dest, held, desc, _ = UniformHolderAssignment.assign(copies, roster, rng)
        actions = {v: ["K" if d == v else d for d in dest[v]] for v in roster}
        return actions, held, desc

    def reveal(self, session: SigningSession) -> SignedPackage:
        with self.guard.snapshot():
            if session.route_plan and not session.aborted:
                try:
                    self._check_plan(session.route_plan)
                except ChannelQuarantined as exc:
                    self._abort_route(session, str(exc), exc.link)
            if session.aborted:
                return SignedPackage(context=session.context, message=session.message,
                                     revealed_signature=[], blinding="")
            return SignedPackage(context=session.context, message=session.message,
                                 revealed_signature=list(session.signature), blinding=session.blinding)

    @staticmethod
    def open_reserve(session: Optional[SigningSession], package: SignedPackage) -> Optional[ReserveOpening]:
        """
        Alice's answer to a borderline request: the reserve opening, but only for her own revealed
        message, signature and context. A package with any substituted field gets nothing.
        """
        if session is None or session.aborted or not session.reserve or session.reserve_blinding is None:
            return None
        if (package.context.to_dict() != session.context.to_dict() or package.message != session.message
                or [tuple(x) for x in package.revealed_signature] != [tuple(x) for x in session.signature]):
            return None
        return ReserveOpening(states=tuple(tuple(x) for x in session.reserve), blinding=session.reserve_blinding)

    def config_for(self, package: SignedPackage) -> SessionConfig:
        """The configuration the signer fixed for this session (from the ledger), else the context's own claim."""
        cfg = self.ledger.config(package.context.session_id)
        if cfg is not None:
            return cfg
        ctx = package.context
        try:
            return SessionConfig.build([v for v in ctx.verifiers if v in VERIFIER_POOL] or list(VERIFIERS),
                                       delivery=getattr(ctx, "delivery", "direct"),
                                       max_depth=getattr(ctx, "max_depth", 1))
        except ConfigurationError:
            return self.default_config

    def _resolve_reserve(self, result: VerificationResult, package: SignedPackage, mode: str,
                         session: Optional[SigningSession], parent: Optional[Dict[str, Any]] = None
                         ) -> VerificationResult:
        if not result.reserve_requested:
            return result
        signer = session or self._signer_sessions.get(package.context.session_id)
        opening = self.open_reserve(signer, package)
        if opening is None:   # Alice unavailable or package substituted: the result stays inconclusive
            return result
        # One bounded second look; the verifier enforces the per-session limit across channels.
        return self.verifiers[result.verifier].verify(package.copy(reserve=opening), mode, parent=parent)

    def deliver(self, package: SignedPackage, to=None,
                session: Optional[SigningSession] = None) -> List[VerificationResult]:
        """Alice's reveal to ``to`` (default: the session's depth-0 recipients)."""
        self.guard.check_open(LINK_SIGNER)
        stored = self.store.route_session(package.context.session_id)
        if stored:
            self._check_plan(RoutePlan(__import__("json").dumps(stored["plan"])))
        if session is not None and session.aborted:
            return []
        to = list(to) if to is not None else self.config_for(package).first_recipients()
        results = []
        for v in to:
            r = self._resolve_reserve(self.node(v).verify(package, "direct"), package, "direct", session)
            self.ledger.record(r, package.context.sender)
            results.append(r)
        self.recent_packages.append(package)
        return results

    def forward(self, package: SignedPackage, from_verifier: str, to_verifier: str,
                parent_event_id: Optional[str] = "auto", depth: Optional[int] = None,
                session: Optional[SigningSession] = None) -> VerificationResult:
        """
        Classical transfer of a package between verifiers. ``parent_event_id="auto"`` names the
        forwarder's latest event for the session (what an honest forwarder sends); ``depth`` is the
        forwarder's claim (default: parent depth + 1). The recipient validates both itself.
        """
        recipient = self.node(to_verifier)     # raises UnknownParticipant for an unenrolled recipient
        self.guard.check_open(LINK_FORWARD)
        self.router.carry_edge(from_verifier, to_verifier)
        sid = package.context.session_id
        if parent_event_id == "auto":
            latest = self.ledger.latest(sid, from_verifier)
            parent_event_id = latest["event_id"] if latest else None
        parent = self.ledger.get(parent_event_id)
        if depth is None:
            depth = package.depth if package.depth is not None else (
                int(parent["depth"]) + 1 if parent is not None else None)
        pkg = package.copy(forwarded_by=from_verifier, parent_event_id=parent_event_id, depth=depth, reserve=None)
        r = recipient.verify(pkg, "forwarded", parent=parent)
        r = self._resolve_reserve(r, pkg, "forwarded", session, parent)
        self.ledger.record(r, from_verifier)
        return r

    @staticmethod
    def honest_forwarding(holder: str, nxt: str, package: SignedPackage, result: VerificationResult
                          ) -> Tuple[str, SignedPackage, Optional[str]]:
        """Default chain behaviour: forward the unchanged package only after a local acceptance."""
        if result.accepted:
            return "forward", package, None
        why = "rejected" if result.status == "rejected" else result.status
        return "stop", package, f"Forwarding stopped at {holder}: local verification {why}; " \
                                f"downstream recipients are not reached."

    def deliver_session(self, package: SignedPackage, session: Optional[SigningSession],
                        config: Optional[SessionConfig] = None, on_hop: Optional[ForwardHook] = None
                        ) -> Tuple[List[VerificationResult], List[str]]:
        """Reveal under the session's delivery mode. Chain: forward hop by hop until a stop or depth H."""
        cfg = config or (session.config if session is not None else self.config_for(package))
        if cfg.delivery == "direct":
            return self.deliver(package, to=cfg.first_recipients(), session=session), []
        on_hop = on_hop or self.honest_forwarding
        notes: List[str] = []
        holder = cfg.roster[0]
        results = self.deliver(package, to=[holder], session=session)
        current = results[0]
        while True:
            nxt = cfg.next_hop(holder)
            if nxt is None:
                if cfg.downstream_of(holder):
                    notes.append(f"Chain ended at depth H = {cfg.max_depth}; "
                                 f"{', '.join(cfg.downstream_of(holder))} not reached.")
                break
            action, out_pkg, note = on_hop(holder, nxt, package, current)
            if note:
                notes.append(note)
            if action != "forward":
                break
            current = self.forward(out_pkg, holder, nxt, session=session)
            results.append(current)
            package, holder = out_pkg.copy(depth=None), nxt
        return results, notes

    def transmit(self, sender: str, message: str, n_bits: int, rng: np.random.Generator,
                 channel: Optional[ChannelModel] = None, config: Optional[SessionConfig] = None) -> Transcript:
        """Honest end-to-end flow. An aborted session is not revealed."""
        session = self.distribute(sender, message, n_bits, rng, channel, config=config)
        package = self.reveal(session)
        kind = "chain" if session.config.delivery == "chain" else "direct"
        if session.aborted:
            note = session.route_abort or ("Channel test alarm: signature never revealed." if session.channel_test.alarm
                    else "INSUFFICIENT_TOKENS: a required recipient has too little surviving evidence; signature never revealed.")
            return Transcript(kind=kind, link=LINK_SIGNER, n_bits=n_bits, package=package, results=[],
                              display={}, session=session, channel_test=session.channel_test,
                              channel_model=session.channel_model,
                              notes=[note], config=session.config)
        results, notes = self.deliver_session(package, session)
        return Transcript(kind=kind, link=LINK_SIGNER, n_bits=n_bits, package=package, results=results,
                          display={r.verifier: r for r in results}, session=session,
                          channel_test=session.channel_test, channel_model=session.channel_model,
                          notes=notes, config=session.config)

    # ------------------------------------------------------------- assessment
    def assess(self, transcript: Transcript, ground_truth: Optional[Dict[str, Any]] = None,
               started_ns: Optional[int] = None) -> QDSExecutionResult:
        tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
        link = transcript.link

        t0 = time.perf_counter_ns()
        session = transcript.session
        detector = QDSDetectionEngine(session.security_params) if session and session.security_params else self.detector
        report = detector.classify(transcript.results, transcript.channel_test)
        route_alarms = {v: t for v, t in (session.route_tests if session else {}).items() if t["alarm"]}
        is_routed = session and session.route_plan and session.route_plan.to_dict()["topology_digest"] != legacy_star().digest
        if is_routed and transcript.channel_test and transcript.channel_test.alarm:
            report.evidence_p = min(1.0, report.evidence_p * 2)
        if route_alarms and not (transcript.channel_test and transcript.channel_test.alarm):
            report = ThreatReport(ThreatClassification.EAVESDROPPING_TAMPERING, "REJECTED",
                "Route-specific test alarm; edge attribution is unknown.", True, decided_by="route_tests",
                evidence_p=min(1.0, min(t["p_value"] for t in route_alarms.values()) * len(session.config.roster) * (2 if is_routed else 1)))
        elif session and session.insufficient_tokens and not (transcript.channel_test and transcript.channel_test.alarm):
            report = ThreatReport(ThreatClassification.INSUFFICIENT_TOKENS, "REJECTED",
                "Insufficient surviving evidence at a required recipient; no signature revealed.", False,
                decided_by="recipient_evidence", evidence_p=1.0)
        elif session and session.route_abort and not route_alarms and not (transcript.channel_test and transcript.channel_test.alarm):
            report = ThreatReport(ThreatClassification.INCONCLUSIVE_EVIDENCE, "INCONCLUSIVE",
                "Distribution/reveal interrupted by a required scope restriction.", False,
                decided_by="route_abort", evidence_p=1.0)
        t1 = time.perf_counter_ns()

        decision = decide(report, self.policy)
        if transcript.kind == "chain":
            cfg = transcript.config or DEFAULT_CONFIG
            from .ledger import event_summary
            rows = participant_matrix(cfg, [event_summary(r, r.forwarded_by or r.claimed_sender)
                                            for r in transcript.results])
            all_accepted = session_outcome(cfg, rows) == "all_accepted"
        else:
            direct = [r for r in transcript.results if r.mode == "direct"]
            all_accepted = transcript.kind == "direct" and bool(direct) and all(r.accepted for r in direct)
        all_accepted = all_accepted and not (session and session.aborted)
        route_transitions = []
        custom_routes = session and session.route_plan and session.route_plan.to_dict()["topology_digest"] != legacy_star().digest
        channel_finding = report.classification in (ThreatClassification.EAVESDROPPING_TAMPERING,
                                                     ThreatClassification.INSUFFICIENT_TOKENS)
        assessment_id = evidence_hash({"session": transcript.package.context.session_id,
            "events": [r.event_id for r in transcript.results],
            "channel": transcript.channel_test.to_dict() if transcript.channel_test else None})
        if custom_routes and channel_finding:
            plan_routes = session.route_plan.to_dict()["routes"]
            targets = list(route_alarms) or list(plan_routes)
            for v in targets:
                scope = plan_routes[v]["route_id"]
                local_decision = decision
                if v in route_alarms:
                    adjusted = min(1.0, route_alarms[v]["p_value"] * 2 * len(plan_routes))
                    strong = adjusted <= self.policy.strong_alpha
                    local_decision = ResponseDecision("reject", "quarantine" if strong else "watch",
                        "strong" if strong else "weak", adjusted,
                        f"Route-specific test for {v}; family-adjusted p={adjusted:.3g}; no edge localization")
                change = self.guard.apply(scope, local_decision, assessment_id,
                    actor="route_observation (no edge localization)")
                if change:
                    route_transitions.append(change)
            transition = next((t for t in route_transitions if t["new_state"] == QUARANTINED),
                              route_transitions[0] if route_transitions else None)
            link = transition["link"] if transition else plan_routes[targets[0]]["route_id"]
        else:
            transition = self.guard.apply(link, decision, assessment_id,
                accepted=all_accepted and not report.is_threat_detected)
        if custom_routes and all_accepted and not channel_finding:
            for r in session.route_plan.to_dict()["routes"].values():
                self.guard.apply(r["route_id"], ResponseDecision("accept", "none", "none", 1.0, "route passed"),
                                 assessment_id, accepted=True)
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
            "route_transitions": route_transitions,
            "attribution": "route observation; no edge localization" if custom_routes and channel_finding else None,
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
        if session and session.route_plan:
            session.route_execution["session_outcome"] = result.to_dict()["session_outcome"]

        if self.audit is not None:
            tx = result.to_dict()
            evidence = build_evidence(tx)
            if enforcement["incident_id"]:
                t3 = time.perf_counter_ns()
                inc = build_incident_record(enforcement["incident_id"], transition, tx, evidence_hash(evidence),
                                            self.policy.to_dict())
                result.incident_cert = self.audit.issue(inc, enforcement["incident_id"])
                for extra_transition in route_transitions:
                    if extra_transition.get("incident_id") and extra_transition["incident_id"] != enforcement["incident_id"]:
                        extra = build_incident_record(extra_transition["incident_id"], extra_transition, tx,
                            evidence_hash(evidence), self.policy.to_dict())
                        self.audit.issue(extra, extra_transition["incident_id"])
                latency["incident_signing_us"] = round((time.perf_counter_ns() - t3) / 1000, 2)
            t4 = time.perf_counter_ns()
            record = build_record(result.to_dict(), self.params.to_dict(), self.policy.to_dict(), evidence,
                                  self.params.freshness_window_s)
            result.audit_cert = self.audit.issue(record, tx_id, evidence)
            if transcript.kind == "chain":
                self._issue_transfer_records(result, transcript)
            latency["audit_signing_us"] = round((time.perf_counter_ns() - t4) / 1000, 2)
        self.ledger.attach_transmission([r.event_id for r in transcript.results], tx_id)

        if started_ns:
            latency["protocol_ms"] = round((time.perf_counter_ns() - started_ns) / 1e6, 2)
        self.latency.add(**{k: v for k, v in latency.items() if isinstance(v, (int, float))})
        enforcement["channel_state"] = self.guard.to_dict()
        if session and session.route_plan:
            self.store.save_route_execution(session.context.session_id, session.route_execution, sealed=True)
        return result

    def _issue_transfer_records(self, result: QDSExecutionResult, transcript: Transcript):
        """
        The transaction record covers distribution and the reveal (depth-0) event. Every later
        forwarding event gets its own immutable signed record that names its parent event and the
        artifact id + payload hash of the record holding that parent. Nothing signed is ever changed.
        """
        tx_id = result.transmission_id
        holder: Dict[str, Tuple[str, str]] = {}   # event_id -> (artifact_id, payload_sha256)
        for r in transcript.results:
            if r.mode != "forwarded":
                holder[r.event_id] = (tx_id, result.audit_cert["payload_sha256"])
                continue
            parent_art = holder.get(r.parent_event_id or "", (tx_id, result.audit_cert["payload_sha256"]))
            record = build_transfer_record(tx_id, r.to_dict(), transcript.package.context.to_dict(),
                                           (transcript.config or DEFAULT_CONFIG).to_dict(),
                                           {"artifact_id": parent_art[0], "payload_sha256": parent_art[1]},
                                           self.params.to_dict())
            cert = self.audit.issue(record, r.event_id)
            holder[r.event_id] = (r.event_id, cert["payload_sha256"])
            result.transfer_records.append({"artifact_id": r.event_id, "event_id": r.event_id,
                                            "verifier": r.verifier, "depth": r.depth,
                                            "parent_artifact_id": parent_art[0],
                                            "payload_sha256": cert["payload_sha256"],
                                            "chain_seq": cert["record"]["chain"]["seq"]})

    def execute_protocol(self, message_text: str, n_bits: int = 16, sender: str = "alice",
                         scenario=None, rng: Optional[np.random.Generator] = None,
                         channel: Optional[ChannelModel] = None,
                         config: Optional[SessionConfig] = None) -> QDSExecutionResult:
        """Run one transmission, optionally through an attack injector, then assess it blind."""
        from .threats import ThreatScenarioConfig, ThreatSuite, ThreatType

        rng = rng or np.random.default_rng()
        scenario = scenario or ThreatScenarioConfig(threat_type=ThreatType.AUTHENTIC)
        cfg = config or self.default_config
        cfg.validate()
        ThreatSuite.validate(scenario, cfg)
        started = time.perf_counter_ns()
        transcript = ThreatSuite.run(self, scenario, message_text, n_bits, sender, rng, channel, config=cfg)
        result = self.assess(transcript, started_ns=started)
        # Ground truth is attached only after the detector has returned.
        cm = transcript.channel_model
        result.ground_truth = {
            "injected_scenario": scenario.threat_type.value,
            "dishonest_verifier": scenario.dishonest_verifier,
            "edge_injections": transcript.session.edge_ground_truth if transcript.session else {},
            "traversed_injected_edges": [eid for eid in (transcript.session.edge_ground_truth if transcript.session else {})
                if transcript.session.route_execution["edges"].get(eid, {}).get("attempted", 0)],
            "hidden_channel": None if cm is None else {
                "depolarizing": cm.depolarizing, "intercept_rate": cm.intercept_rate,
                "expected_qber": round(cm.expected_qber(), 4)},
            "note": "Set by the attack injector for experiment reporting; never passed to verifiers or detector.",
        }
        return result
