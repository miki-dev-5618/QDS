"""
Session and verification-event ledger (N-verifier extension).

Every verification is an *event* with its own id, linked to its session and,
for a transfer, to the parent event it was forwarded from. Events are never
keyed by verifier + mode alone, so repeated deliveries cannot overwrite each
other. The ledger is part of the simulation's authenticated infrastructure:
a verifier resolves the parent a forwarder names through it, but a parent's
*claimed* depth or sender is always checked against the verifier's own record.

With a ``Store`` the session roster and every event survive restarts (audit
history only: the one-time quantum evidence does not, so a session distributed
before a restart cannot be verified afterwards).

Session-level outcome (all-recipient workflow; no majority rule):
  all_accepted          every required recipient accepted
  rejected              at least one reached recipient rejected
  inconclusive          none rejected, at least one inconclusive
  incomplete            none rejected or inconclusive, some required recipient not reached
  distribution_aborted  the signature was never revealed
Required recipients: the whole roster (direct) or the chain up to depth H (chain).
"""
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional

from .roster import SessionConfig


def event_summary(result, sender: Optional[str], ts: Optional[float] = None) -> Dict[str, Any]:
    """Compact, evidence-free description of one verification event."""
    b = result.bounds or {}
    values = b.get("values") or {}
    return {
        "event_id": result.event_id,
        "session_id": result.session_id,
        "verifier": result.verifier,
        "sender": sender,
        "mode": result.mode,
        "depth": result.depth,
        "max_depth": result.max_depth,
        "parent_event_id": result.parent_event_id,
        "status": result.status,
        "accepted": result.accepted,
        "n_checked": result.n_checked,
        "mismatches": result.mismatches,
        "acceptance_limit": result.acceptance_limit,
        "decision_rule": b.get("decision_rule"),
        "decision_stage": result.decision_stage,
        "reserve": {"available": result.reserve_available, "requested": result.reserve_requested,
                    "opened": result.decision_stage == 2, "checked": result.reserve_checked},
        "evidence_status": result.evidence_status,
        "risk": {"false_reject": values.get("false_reject"), "forgery_accept": values.get("forgery_accept"),
                 "scope": "per-event, within the stated i.i.d. model"},
        "transfer_valid": result.transfer_valid,
        "duplicate": result.duplicate,
        "binding_pass": result.binding_pass,
        "reasons": list(result.reasons),
        "ts": time.time() if ts is None else ts,
    }


def _route_role(cfg: SessionConfig, v: str) -> str:
    if cfg.delivery == "direct":
        return "direct recipient"
    i = cfg.roster.index(v)
    if i > cfg.max_depth:
        return f"beyond depth H = {cfg.max_depth}"
    return "first recipient (depth 0)" if i == 0 else f"chain position {i} (depth {i})"


def participant_matrix(cfg: SessionConfig, events: Iterable[Dict[str, Any]], aborted: bool = False
                       ) -> List[Dict[str, Any]]:
    """One row per roster member: route role, latest decision, and its full event history."""
    by_v: Dict[str, List[Dict[str, Any]]] = {v: [] for v in cfg.roster}
    for e in events:
        by_v.setdefault(e["verifier"], []).append(e)
    rows = []
    for v in list(cfg.roster) + [x for x in by_v if x not in cfg.roster]:
        hist = by_v.get(v, [])
        last = hist[-1] if hist else None
        if v not in cfg.roster:
            role = "not in roster"
        else:
            role = _route_role(cfg, v)
        if last is not None:
            status = last["status"]
        elif aborted:
            status = "distribution_aborted"
        elif cfg.delivery == "chain" and cfg.roster.index(v) > cfg.max_depth:
            status = "outside_depth"
        else:
            status = "not_reached"
        rows.append({
            "verifier": v, "route_role": role, "status": status,
            "received_from": last["sender"] if last else None,
            "depth": last["depth"] if last else None,
            "mismatches": last["mismatches"] if last else None,
            "checked": last["n_checked"] if last else None,
            "acceptance_limit": last["acceptance_limit"] if last else None,
            "decision_stage": last["decision_stage"] if last else None,
            "reserve": last["reserve"] if last else None,
            "evidence_status": last["evidence_status"] if last else None,
            "reason": (last["reasons"][0] if last and last["reasons"] else None),
            "event_count": len(hist),
            "event_ids": [e["event_id"] for e in hist],
        })
    return rows


def session_outcome(cfg: SessionConfig, rows: List[Dict[str, Any]], aborted: bool = False) -> str:
    if aborted:
        return "distribution_aborted"
    required = set(cfg.roster if cfg.delivery == "direct" else cfg.chain_route())
    status = {r["verifier"]: r["status"] for r in rows}
    reached = [s for s in status.values() if s not in ("not_reached", "outside_depth")]
    if any(s in ("rejected", "distribution_aborted") for s in reached):
        return "rejected"
    if any(s == "inconclusive" for s in reached):
        return "inconclusive"
    if all(status.get(v) == "accepted" for v in required):
        return "all_accepted"
    return "incomplete"


class EventLedger:
    def __init__(self, store=None, keep_sessions: int = 1000):
        self.store = store
        self.keep = keep_sessions
        self._sessions: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._events: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def register_session(self, session_id: str, sender: str, cfg: SessionConfig, created: float):
        with self._lock:
            self._sessions[session_id] = {"session_id": session_id, "sender": sender, "config": cfg,
                                          "created": created, "events": []}
            while len(self._sessions) > self.keep:
                _, old = self._sessions.popitem(last=False)
                for eid in old["events"]:
                    self._events.pop(eid, None)
        if self.store is not None:
            self.store.save_session(session_id, sender, created, cfg.to_dict())

    def config(self, session_id: str) -> Optional[SessionConfig]:
        s = self._sessions.get(session_id)
        return s["config"] if s else None

    def record(self, result, sender: Optional[str]) -> Dict[str, Any]:
        summary = event_summary(result, sender)
        with self._lock:
            self._events[summary["event_id"]] = summary
            s = self._sessions.get(result.session_id)
            if s is not None:
                s["events"].append(summary["event_id"])
        if self.store is not None:
            self.store.save_event(summary)
        return summary

    def get(self, event_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not event_id:
            return None
        e = self._events.get(event_id)
        if e is None and self.store is not None:
            e = self.store.get_event(event_id)
        return e

    def latest(self, session_id: str, verifier: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            s = self._sessions.get(session_id)
            for eid in reversed(s["events"] if s else []):
                e = self._events.get(eid)
                if e and e["verifier"] == verifier:
                    return e
        return None

    def events(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is not None:
                return [self._events[e] for e in s["events"] if e in self._events]
        return self.store.session_events(session_id) if self.store is not None else []

    def attach_transmission(self, event_ids: List[str], transmission_id: str):
        if self.store is not None and event_ids:
            self.store.attach_events(event_ids, transmission_id)
