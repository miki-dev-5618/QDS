"""
Quantum Circuit Breaker (QCB): per-scope state machine and latency measurement.

Units of isolation (scopes), each with its own independent state:
  * ``alice->verifiers`` - signer scope: signer/session-level findings that are
    not quantum-channel faults (authenticated signer/repudiation evidence). Quarantine
    blocks the signer's distribution and reveal.
  * ``bob->charlie``     - pooled verifier-to-verifier classical forwarding.
  * ``edge:<digest>``   - one topology-specific quantum-distribution edge
    topology. Moved ONLY by independent edge-monitoring probes
    (``monitoring.py``) or by an admin action labelled as manual failure
    injection; never by pooled end-to-end evidence.
  * ``path:<digest>`` - one topology-specific ordered end-to-end route. Pooled end-to-end channel
    evidence of a session moves the scopes of the routes that session used;
    it does not single out any edge on them.

A quarantined scope refuses only the operations that need it: there is no
implicit global stop. An explicit, separately logged emergency stop (admin)
refuses everything until it is cleared.

States and transitions (every transition is atomic under one lock, logged
with actor, time, evidence id, old/new state and policy version, and
persisted when a Store is attached):

    OPEN --weak--> WATCH --more weak evidence within window--> QUARANTINED
                   (Fisher-combined p <= escalate_alpha, or watch_strikes alerts)
    OPEN/WATCH --strong--> QUARANTINED
    WATCH --window expires with no new alert--> OPEN
    QUARANTINED --admin reset--> RESET_PENDING
    RESET_PENDING --accepted session (signer/path) or monitored edge recovery--> OPEN
    RESET_PENDING --any quantum-evidence alert--> QUARANTINED

QUARANTINED refuses new transmissions. WATCH and RESET_PENDING carry traffic
with an increased test-token budget (adaptive test allocation); a route
through a WATCH scope is used only under an explicit fallback policy
(``routing.py``). Entering QUARANTINED allocates an incident id; the engine
signs the incident record at that moment, not at first download.

Migration: link tables saved before scoped isolation existed are loaded
unchanged (an active quarantine is never cleared) and labelled with their
original pooled scope; no per-edge observation is invented for them.
"""
import threading
import time
import uuid
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, List, Optional

from .policy import ResponseDecision, ResponsePolicy, fisher_combined_p

LINK_SIGNER = "alice->verifiers"
LINK_FORWARD = "bob->charlie"
EMERGENCY = "*emergency-stop*"
SCOPES_SCHEMA = "hedwig-scopes/1"
LEGACY_NOTE = ("legacy pooled logical-link isolation (pre-routing); preserved by migration, "
               "not attributed to any edge")


def edge_scope(edge_id: str, topology_digest: str = "") -> str:
    return "edge:" + hashlib.sha256(json.dumps([topology_digest, edge_id], separators=(",", ":")).encode()).hexdigest()


def path_scope(edge_ids, topology_digest: str = "") -> str:
    return "path:" + hashlib.sha256(json.dumps([topology_digest, list(edge_ids)], separators=(",", ":")).encode()).hexdigest()


def scope_kind(scope: str) -> str:
    if scope.startswith("edge:"):
        return "edge"
    if scope.startswith("path:"):
        return "path"
    return {LINK_SIGNER: "signer", LINK_FORWARD: "forward"}.get(scope, "other")

OPEN, WATCH, QUARANTINED, RESET_PENDING = "open", "watch", "quarantined", "reset_pending"
CARRIES_TRAFFIC = {OPEN, WATCH, RESET_PENDING}


class ChannelQuarantined(Exception):
    """A required scope refuses traffic (HTTP 423)."""
    status = "quarantined"

    def __init__(self, link: str, info: Dict[str, Any], message: Optional[str] = None):
        super().__init__(message or f"Scope {link} is quarantined")
        self.link = link
        self.info = info

    def payload(self) -> Dict[str, Any]:
        return {"status": self.status, "link": self.link, "detail": self.info, "message": str(self)}


class EmergencyStop(ChannelQuarantined):
    status = "emergency_stop"


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
    scope_note: Optional[str] = None                            # e.g. legacy pooled scope, manual injection
    reset_epoch: Optional[str] = None                            # unique recovery window, independent of clock precision

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
        self.policy_corrections: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self.revision = 0
        self._assessed = {(t["link"], t["evidence_id"]) for t in store.transitions(1000000)} if store else set()
        if store is not None:
            self.revision = len(store.transitions(1000000))
            saved = store.get_json("links")
            if saved:
                for name, d in saved.items():
                    self.links[name] = LinkState(**d)
            if not store.get_json("scopes_schema"):
                for st in self.links.values():
                    if st.state != OPEN:
                        st.scope_note = LEGACY_NOTE
                store.put_json("links", {k: v.to_dict() for k, v in self.links.items()})
                store.put_json("scopes_schema", SCOPES_SCHEMA)
            # Correct only an unambiguous single detector finding from the old
            # policy. Mixed evidence, manual stops and real signer findings stay.
            st = self.links[LINK_SIGNER]
            original = next((t for t in store.transitions(1000000) if t["link"] == LINK_SIGNER), None)
            if (self.policy.version == "hedwig-qcb/3" and st.state in (WATCH, QUARANTINED)
                    and (st.reason or "").startswith("EXTERNAL_FORGERY:") and st.strikes == 1
                    and original and original["actor"] == "detector"
                    and original["evidence_id"] == st.transmission_id):
                why = "Policy correction: external classical forgery rejects its package; it does not establish a signer or quantum-edge fault."
                self.policy_corrections.append(self._transition(LINK_SIGNER,
                    LinkState(since=self.clock(), reason=why, scope_note="audited correction of former classical-forgery isolation"),
                    "policy_migration", why, st.transmission_id))
        if router is not None:
            for name, st in self.links.items():
                router.sync(name, st.state)

    # ------------------------------------------------------------ internals
    def _transition(self, link: str, new: LinkState, actor: str, reason: str,
                    evidence_id: Optional[str]) -> Dict[str, Any]:
        old = self.links.get(link, LinkState())
        self.links[link] = new
        self.revision += 1
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
        """Check the required scope and the explicit emergency stop only."""
        with self._lock:
            self._expire_watch(link)
            st = self.links[link]
            broken = EMERGENCY if self.links.get(EMERGENCY, LinkState()).state == QUARANTINED else (
                link if st.state not in CARRIES_TRAFFIC else None)
            if broken is not None:
                st.refused += 1
                if self.router is not None:
                    self.router.refuse(link)
                raise (EmergencyStop if broken == EMERGENCY else ChannelQuarantined)(broken, self.links[broken].to_dict())

    @contextmanager
    def snapshot(self):
        """Process-local synchronization; one transmission block may already be in flight."""
        with self._lock:
            yield self.to_dict(), self.revision

    def check_scopes(self, scopes, allow_watch=False, allow_probation=True):
        with self._lock:
            for scope in scopes:
                self.check_open(scope)
                if self.state(scope) == WATCH and not allow_watch:
                    raise ChannelQuarantined(scope, self.links[scope].to_dict(), "Required route is on WATCH")
                if self.state(scope) == RESET_PENDING and not allow_probation:
                    raise ChannelQuarantined(scope, self.links[scope].to_dict(), "Required route is on probation")

    def manual(self, scope, state, actor, reason):
        if state not in (WATCH, QUARANTINED):
            raise ValueError("Manual faults must be watch or quarantined")
        with self._lock:
            return self._transition(scope, LinkState(state=state, reason=reason, since=self.clock(),
                scope_note="manual fault injection; not detector evidence", incident_id=(
                    f"INC-{uuid.uuid4().hex[:8].upper()}" if state == QUARANTINED else None)), actor, reason, None)

    def emergency(self, enabled, actor, reason):
        with self._lock:
            return self._transition(EMERGENCY, LinkState(state=QUARANTINED if enabled else OPEN,
                since=self.clock(), reason=reason), actor, reason, None)

    def apply(self, link: str, decision: ResponseDecision, transmission_id: str, purged: int = 0,
              accepted: bool = False, actor: str = "detector") -> Optional[Dict[str, Any]]:
        """Apply one decision to a link. Returns the transition entry, or None if the state did not change."""
        with self._lock:
            key = (link, transmission_id)
            if key in self._assessed:
                return None
            self._assessed.add(key)
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
                        (cur.state == WATCH and self.policy.should_escalate(combined, strikes)))
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
            for name in ([link] if link and link != EMERGENCY else [n for n in self.links if n != EMERGENCY]):
                cur = self.links.setdefault(name, LinkState())
                now = self.clock()
                if cur.state == QUARANTINED:
                    out.append(self._transition(name, LinkState(RESET_PENDING, "probation after reset", None, now,
                                                                 reset_by=actor, reset_reason=reason, reset_epoch=uuid.uuid4().hex),
                                                actor, reason, cur.incident_id))
                elif cur.state == WATCH:
                    out.append(self._transition(name, LinkState(state=RESET_PENDING if name.startswith("edge:") else OPEN,
                                                               since=now, reset_by=actor, reset_reason=reason,
                                                               reset_epoch=uuid.uuid4().hex),
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
