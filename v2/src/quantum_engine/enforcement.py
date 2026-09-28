"""
Quantum Circuit Breaker (QCB): per-link state machine and latency measurement.

Unit of isolation: a *logical link* - the signer's distribution/reveal path
to its verifiers (``alice->verifiers``) or the verifier-to-verifier transfer
path (``bob->charlie``). An alert on one link never blocks the other.

States and transitions (every transition is atomic under one lock, logged
with actor, time, evidence id, old/new state and policy version, and
persisted when a Store is attached):

    OPEN --weak--> WATCH --more weak evidence within window--> QUARANTINED
                   (Fisher-combined p <= escalate_alpha, or watch_strikes alerts)
    OPEN/WATCH --strong--> QUARANTINED
    WATCH --window expires with no new alert--> OPEN
    QUARANTINED --admin reset (role + reason)--> RESET_PENDING
    RESET_PENDING --one fully accepted transmission--> OPEN
    RESET_PENDING --any quantum-evidence alert--> QUARANTINED

QUARANTINED refuses new transmissions. WATCH and RESET_PENDING carry traffic
with an increased test-token budget (adaptive test allocation). Entering
QUARANTINED allocates an incident id; the engine signs the incident record
at that moment, not at first download.
"""
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, List, Optional

from .policy import ResponseDecision, ResponsePolicy, fisher_combined_p

LINK_SIGNER = "alice->verifiers"
LINK_FORWARD = "bob->charlie"

OPEN, WATCH, QUARANTINED, RESET_PENDING = "open", "watch", "quarantined", "reset_pending"
CARRIES_TRAFFIC = {OPEN, WATCH, RESET_PENDING}


class ChannelQuarantined(Exception):
    def __init__(self, link: str, info: Dict[str, Any]):
        super().__init__(f"Link {link} is quarantined")
        self.link = link
        self.info = info


@dataclass
class LinkState:
    state: str = OPEN
    reason: Optional[str] = None
    transmission_id: Optional[str] = None
    since: Optional[float] = None
    purged_records: int = 0
    strikes: int = 0
    watch_until: Optional[float] = None
    incident_id: Optional[str] = None
    reset_by: Optional[str] = None
    reset_reason: Optional[str] = None
    refused: int = 0
    watch_evidence: List[float] = field(default_factory=list)   # p-values of weak alerts in the window
    combined_p: Optional[float] = None                          # Fisher combination of watch_evidence

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ChannelGuard:
    def __init__(self, policy: Optional[ResponsePolicy] = None, store=None, router=None,
                 clock: Callable[[], float] = time.time):
        self.policy = policy or ResponsePolicy()
        self.store = store
        self.router = router
        self.clock = clock
        self.links: Dict[str, LinkState] = {LINK_SIGNER: LinkState(), LINK_FORWARD: LinkState()}
        self.transitions: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        if store is not None:
            saved = store.get_json("links")
            if saved:
                for name, d in saved.items():
                    self.links[name] = LinkState(**d)
        if router is not None:
            for name, st in self.links.items():
                router.sync(name, st.state)

    # ------------------------------------------------------------ internals
    def _transition(self, link: str, new: LinkState, actor: str, reason: str,
                    evidence_id: Optional[str]) -> Dict[str, Any]:
        old = self.links.get(link, LinkState())
        self.links[link] = new
        entry = {"ts": self.clock(), "link": link, "old_state": old.state, "new_state": new.state,
                 "actor": actor, "reason": reason, "evidence_id": evidence_id,
                 "policy_version": self.policy.version, "incident_id": new.incident_id
                 if new.state == QUARANTINED and old.state != QUARANTINED else None}
        self.transitions.append(entry)
        del self.transitions[:-500]
        if self.store is not None:
            self.store.save_link_transition({k: v.to_dict() for k, v in self.links.items()}, entry)
        if self.router is not None:
            self.router.sync(link, new.state)
        return entry

    def _expire_watch(self, link: str):
        st = self.links.setdefault(link, LinkState())
        if st.state == WATCH and st.watch_until is not None and self.clock() > st.watch_until:
            self._transition(link, LinkState(since=self.clock()), "system", "watch window expired", None)

    # ---------------------------------------------------------------- public
    def state(self, link: str) -> str:
        with self._lock:
            self._expire_watch(link)
            return self.links[link].state

    def check_open(self, link: str):
        with self._lock:
            self._expire_watch(link)
            st = self.links[link]
            if st.state not in CARRIES_TRAFFIC:
                st.refused += 1
                if self.router is not None:
                    self.router.refuse(link)
                raise ChannelQuarantined(link, st.to_dict())

    def apply(self, link: str, decision: ResponseDecision, transmission_id: str, purged: int = 0,
              accepted: bool = False, actor: str = "detector") -> Optional[Dict[str, Any]]:
        """Apply one decision to a link. Returns the transition entry, or None if the state did not change."""
        with self._lock:
            self._expire_watch(link)
            cur = self.links[link]
            now = self.clock()
            action = decision.response_action

            if action == "none":
                if cur.state == RESET_PENDING and accepted:
                    return self._transition(link, LinkState(since=now), actor,
                                            "probation passed: fully accepted transmission", transmission_id)
                return None

            evidence = (cur.watch_evidence if cur.state == WATCH else []) + [decision.evidence_p]
            combined = fisher_combined_p(evidence)
            strikes = len(evidence)
            escalate = (action == "quarantine" or cur.state == RESET_PENDING or
                        (cur.state == WATCH and (combined <= self.policy.escalate_alpha
                                                 or strikes >= self.policy.watch_strikes)))
            if escalate:
                if cur.state == QUARANTINED:
                    return None
                if action == "quarantine":
                    why = decision.reason
                elif cur.state == RESET_PENDING:
                    why = "probation failed: " + decision.reason
                else:
                    why = (f"escalated: {strikes} weak alerts within {self.policy.watch_window_s:.0f} s, "
                           f"Fisher-combined p = {combined:.2e}; " + decision.reason)
                new = LinkState(QUARANTINED, why, transmission_id, now, purged, strikes=strikes,
                                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                                watch_evidence=evidence, combined_p=combined)
                return self._transition(link, new, actor, why, transmission_id)

            # weak alert on OPEN, or on WATCH without enough accumulated evidence
            new = LinkState(WATCH, decision.reason, transmission_id, now, 0, strikes=strikes,
                            watch_until=now + self.policy.watch_window_s,
                            watch_evidence=evidence, combined_p=combined)
            return self._transition(link, new, actor, decision.reason, transmission_id)

    def request_reset(self, link: Optional[str] = None, actor: str = "admin",
                      reason: str = "") -> List[Dict[str, Any]]:
        """Admin reset: QUARANTINED -> RESET_PENDING (probation); WATCH -> OPEN."""
        out = []
        with self._lock:
            for name in ([link] if link else list(self.links)):
                cur = self.links.setdefault(name, LinkState())
                now = self.clock()
                if cur.state == QUARANTINED:
                    out.append(self._transition(name, LinkState(RESET_PENDING, "probation after reset", None, now,
                                                                 reset_by=actor, reset_reason=reason),
                                                actor, reason, cur.incident_id))
                elif cur.state == WATCH:
                    out.append(self._transition(name, LinkState(since=now, reset_by=actor, reset_reason=reason),
                                                actor, reason, cur.transmission_id))
        return out

    def reset(self, link: Optional[str] = None, actor: str = "system", reason: str = "harness reset"):
        return self.request_reset(link, actor, reason)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            for name in list(self.links):
                self._expire_watch(name)
            return {k: v.to_dict() for k, v in self.links.items()}


class LatencyStats:
    """Rolling samples per named interval; medians and high percentiles."""
    NOTES = {
        "channel_observation_ms": "teleport + measure all transmitted tokens (the simulator run)",
        "detection_us": "blind classifier: observations in, verdict out",
        "enforcement_us": "post-verdict: policy + atomic state transition + buffer purge (+ persistence)",
        "incident_signing_us": "build and sign the incident record at quarantine time",
        "audit_signing_us": "build and sign the transaction audit record",
        "protocol_ms": "whole transmission, request to recorded result",
        "refusal_us": "API: request arrival to HTTP 423 refusal on a quarantined link",
    }

    def __init__(self, keep: int = 2000):
        self.series: Dict[str, List[float]] = {k: [] for k in self.NOTES}
        self.keep = keep

    def add(self, **values: Optional[float]):
        for k, v in values.items():
            if v is None:
                continue
            arr = self.series.setdefault(k, [])
            arr.append(float(v))
            del arr[:-self.keep]

    @staticmethod
    def _summary(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"count": 0}
        s = sorted(values)
        pick = lambda q: s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]
        return {"count": len(s), "p50": round(pick(0.5), 2), "p95": round(pick(0.95), 2),
                "p99": round(pick(0.99), 2), "max": round(s[-1], 2)}

    @property
    def detection_us(self) -> List[float]:
        return self.series["detection_us"]

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {k: self._summary(v) for k, v in self.series.items()}
        out["intervals"] = self.NOTES
        out["note"] = ("Measured with time.perf_counter_ns on this host. Post-verdict enforcement latency is NOT "
                       "attack-to-isolation time: the verdict exists only after the channel observation "
                       "(simulator run) completes, or after an early abort.")
        return out
