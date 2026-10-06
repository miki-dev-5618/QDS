"""
Simulated channel router: maps each logical link to the hops it uses and
reflects circuit-breaker state per hop.

Topology (a star through one quantum relay, plus the classical transfer link):

    alice ──q── QR-1 ──q── bob
                  └───q── charlie
    bob ──────c────────── charlie     (forwarded signatures)

    q = quantum channel carrying teleportation Bell halves (+ classical corrections)
    c = authenticated classical channel

Hop states follow the link: ``up`` (open), ``degraded`` (watch), ``probation``
(reset pending) and ``down`` (quarantined). A ``down`` hop drops the
transmission before any token is prepared, so no Bell pairs are spent on a
quarantined link. This is a software model of routing decisions: no physical
fibre is switched and no physical qubit is destroyed.
"""
import threading
from dataclasses import dataclass, asdict
from typing import Dict, List

from .enforcement import LINK_FORWARD, LINK_SIGNER

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

    def to_dict(self):
        return asdict(self)


class SimulatedRouter:
    def __init__(self):
        self.hops: Dict[str, Hop] = {h: Hop(h, HOP_KIND[h]) for route in ROUTES.values() for h in route}
        self._lock = threading.Lock()

    def sync(self, link: str, link_state: str):
        with self._lock:
            for h in ROUTES.get(link, []):
                self.hops[h].state = _HOP_STATE.get(link_state, "down")

    def carry(self, link: str, tokens: int):
        with self._lock:
            for h in ROUTES.get(link, []):
                self.hops[h].tokens_carried += tokens
                self.hops[h].transmissions += 1

    def refuse(self, link: str):
        with self._lock:
            route = ROUTES.get(link, [])
            if route:
                self.hops[route[0]].dropped += 1

    def to_dict(self):
        with self._lock:
            return {"routes": ROUTES, "hops": {k: h.to_dict() for k, h in self.hops.items()},
                    "note": "Software routing model; no physical fibre or qubit is switched or destroyed."}
