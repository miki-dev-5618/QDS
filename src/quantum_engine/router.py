"""
Simulated channel router: maps each logical link to the hops it uses and
reflects circuit-breaker state per hop.

Default topology (a star through one quantum relay, plus the classical transfer link):

    alice ──q── QR-1 ──q── bob
                  └───q── charlie
    bob ──────c────────── charlie     (forwarded signatures)

    q = quantum channel carrying teleportation Bell halves (+ classical corrections)
    c = authenticated classical channel

With a larger session roster (N-verifier extension) every roster member gets
its own ``QR-1->v`` quantum hop on the signer link, and every verifier-to-
verifier transfer edge that is actually used gets its own classical hop on
the transfer link. Distribution hops and transfer hops stay separate.

Isolation granularity: the breaker acts on the two *logical* links (signer
distribution, pooled verifier transfers), because the channel test is pooled
over the whole distribution stream and transfer evidence is classical. Hop
states mirror their link; per-hop counters show traffic but are not a basis
for per-edge attribution.

Hop states follow the link: ``up`` (open), ``degraded`` (watch), ``probation``
(reset pending) and ``down`` (quarantined). A ``down`` hop drops the
transmission before any token is prepared, so no Bell pairs are spent on a
quarantined link. This is a software model of routing decisions: no physical
fibre is switched and no physical qubit is destroyed.
"""
import threading
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

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
        self.routes: Dict[str, List[str]] = {k: list(v) for k, v in ROUTES.items()}
        self.hops: Dict[str, Hop] = {h: Hop(h, HOP_KIND[h]) for route in ROUTES.values() for h in route}
        self.active_signer_hops: List[str] = list(ROUTES[LINK_SIGNER])
        self.active_roster: List[str] = ["bob", "charlie"]
        self.active_forward_hops: List[str] = []
        self._link_state: Dict[str, str] = {}
        self._lock = threading.Lock()

    def _ensure(self, link: str, name: str, kind: str):
        if name not in self.hops:
            self.hops[name] = Hop(name, kind, _HOP_STATE.get(self._link_state.get(link, "open"), "up"))
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
                    "isolation": "per logical link (signer distribution / pooled verifier transfers); "
                                 "hop counters are not per-edge attribution",
                    "note": "Software routing model; no physical fibre or qubit is switched or destroyed."}
