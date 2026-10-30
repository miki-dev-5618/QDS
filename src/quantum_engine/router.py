"""Simulation resource counters for topology-specific quantum edges.

Session plans choose actual routes. Each edge records attempted/received/lost
copies and consume-on-attempt Bell pairs; loss ends traversal. Restrictions
are independent edge/path/signer/classical scopes. Probe traffic is reported
separately by monitoring.py. Legacy named-hop counters remain for clients.
"""
import threading
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

from .enforcement import LINK_FORWARD, LINK_SIGNER, edge_scope

_HOP_STATE = {"open": "up", "watch": "degraded", "reset_pending": "probation", "quarantined": "down"}

ROUTES: Dict[str, List[str]] = {
    LINK_SIGNER: ["alice->QR-1", "QR-1->bob", "QR-1->charlie"],
    LINK_FORWARD: ["bob->charlie"],
}
HOP_KIND = {"alice->QR-1": "quantum", "QR-1->bob": "quantum", "QR-1->charlie": "quantum",
            "bob->charlie": "classical"}


@dataclass
class Hop:
    name: str
    kind: str
    state: str = "up"
    tokens_carried: int = 0
    transmissions: int = 0
    dropped: int = 0
    attempted: int = 0
    received: int = 0
    lost: int = 0
    bell_pairs: int = 0

    def to_dict(self):
        return asdict(self)


class SimulatedRouter:
    def __init__(self):
        self.routes: Dict[str, List[str]] = {k: list(v) for k, v in ROUTES.items()}
        self.hops: Dict[str, Hop] = {h: Hop(h, HOP_KIND[h]) for route in ROUTES.values() for h in route}
        self.active_signer_hops: List[str] = list(ROUTES[LINK_SIGNER])
        self.active_roster: List[str] = ["bob", "charlie"]
        self.active_forward_hops: List[str] = []
        self._link_state: Dict[str, str] = {}
        self._lock = threading.Lock()
        self.topology = None
        self.latest_plan = None

    def configure_topology(self, topology, plan=None):
        with self._lock:
            if self.topology is None or self.topology.digest != topology.digest:
                self.latest_plan = None
                self.active_signer_hops = []
                self.active_roster = []
            self.topology = topology
            for edge in topology.edges.values():
                self._ensure(LINK_SIGNER, edge_scope(edge.id, topology.digest), "quantum")
            if plan:
                self.latest_plan = plan.to_dict()
                self.active_roster = list(self.latest_plan["roster"])
                self.active_signer_hops = list(dict.fromkeys(s for r in self.latest_plan["routes"].values()
                                                              for s in r["edge_scopes"]))

    def traverse(self, edge, lost, digest):
        with self._lock:
            name = edge_scope(edge.id, digest)
            self._ensure(LINK_SIGNER, name, "quantum")
            h = self.hops[name]
            h.attempted += 1
            h.bell_pairs += 1
            h.lost += int(lost)
            h.received += int(not lost)
            h.tokens_carried += int(not lost)
            h.transmissions += 1
            # Preserve the legacy named-hop counters for existing clients.
            if edge.id in self.hops and edge.id != name:
                old = self.hops[edge.id]
                old.attempted += 1
                old.bell_pairs += 1
                old.lost += int(lost)
                old.received += int(not lost)
                old.tokens_carried += int(not lost)
                old.transmissions += 1

    def _ensure(self, link: str, name: str, kind: str):
        if name not in self.hops:
            self.hops[name] = Hop(name, kind, _HOP_STATE.get(self._link_state.get(name, self._link_state.get(link, "open")), "up"))
        if name not in self.routes[link]:
            self.routes[link].append(name)

    def configure(self, roster: Sequence[str]):
        """Make the signer route of the next session the star to exactly this roster."""
        with self._lock:
            for v in roster:
                self._ensure(LINK_SIGNER, f"QR-1->{v}", "quantum")
            self.active_roster = list(roster)
            self.active_signer_hops = ["alice->QR-1"] + [f"QR-1->{v}" for v in roster]
            self.active_forward_hops = []

    def sync(self, link: str, link_state: str):
        with self._lock:
            self._link_state[link] = link_state
            if link in self.hops:
                self.hops[link].state = _HOP_STATE.get(link_state, "down")
            for h in self.routes.get(link, []):
                self.hops[h].state = _HOP_STATE.get(link_state, "down")

    def carry(self, link: str, tokens: int, hops: Optional[List[str]] = None):
        with self._lock:
            if hops is None:
                hops = self.active_signer_hops if link == LINK_SIGNER else self.routes.get(link, [])
            for h in hops:
                self.hops[h].tokens_carried += tokens
                self.hops[h].transmissions += 1

    def carry_edge(self, sender: str, recipient: str):
        """One classical package transfer sender -> recipient on the pooled transfer link."""
        name = f"{sender}->{recipient}"
        with self._lock:
            self._ensure(LINK_FORWARD, name, "classical")
            if name not in self.active_forward_hops:
                self.active_forward_hops.append(name)
            h = self.hops[name]
            h.tokens_carried += 1
            h.transmissions += 1

    def refuse(self, link: str):
        with self._lock:
            route = self.routes.get(link, [])
            if route:
                self.hops[route[0]].dropped += 1

    def to_dict(self):
        with self._lock:
            return {"routes": {k: list(v) for k, v in self.routes.items()},
                    "hops": {k: h.to_dict() for k, h in self.hops.items()},
                    "active": {"roster": list(self.active_roster), "signer_hops": list(self.active_signer_hops),
                               "forward_hops": list(self.active_forward_hops)},
                    "isolation": "topology-specific quantum edges and exact paths; separate signer and classical forwarding scopes",
                    "topology": self.topology.to_dict() if self.topology else None,
                    "latest_plan": self.latest_plan,
                    "note": "Software routing model; no physical fibre or qubit is switched or destroyed."}
