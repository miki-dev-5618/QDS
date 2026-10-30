"""
Versioned network topology for multi-hop distribution (routing extension).

A topology is a reviewable JSON document (``config/topologies/*.json``) that
declares participants, relays and the *directed quantum-distribution* edges
between them. It is validated before activation and frozen per session: a
session records the version and digest of the topology it was planned on,
and applying a new topology only affects later sessions.

Edge semantics
  * Every edge is a quantum teleportation hop: the edge's two endpoints share
    one Bell pair per token; the upstream node Bell-measures and sends the
    two correction bits to the downstream node.
  * Correction bits, the signer's reveal, symmetrisation and verifier
    forwarding use an authenticated classical channel that is ASSUMED to be
    available between all participants. It is not modelled as edges and is
    not part of quantum route preflight (forwarding keeps its own enforceable
    scope, ``bob->charlie``).
  * Declared edge parameters (``depolarizing``, ``eta_loss``,
    ``damping_gamma``) are the honest, calibrated channel of that hop. They
    feed both the simulation and route-aware evidence planning. They are
    configuration, not attack ground truth.

Structural rules (rejected at validation)
  unknown node / role, duplicate ids, self-edges, parallel edges (same
  ordered endpoints), edges into a signer, edges out of a verifier (a verifier
  is never a relay), probabilities outside their range, non-positive cost.
  Directed cycles among relays are allowed: routes are simple paths of at
  most ``max_hops`` edges. Unreachable verifiers are allowed (reported by
  ``reachability``); sessions requiring them fail preflight.

Trust model (first release): relays are honest-but-curious operators. They
run teleportation and monitoring probes faithfully and never receive the
signer's preparation labels; no security against malicious or colluding
relays is claimed.
"""
import hashlib
import json
import math
import os
from dataclasses import dataclass, asdict, field
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .roster import VERIFIER_POOL, ConfigurationError

TOPOLOGY_SCHEMA = "hedwig-topology/1"
ROLES = ("signer", "relay", "verifier")
MAX_SUPPORTED_HOPS = 8
MAX_NODES, MAX_EDGES = 64, 256
TOPOLOGY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "config", "topologies")


class TopologyError(ConfigurationError):
    """An invalid topology document (rejected before activation)."""


def pauli_flip(depolarizing: float) -> float:
    """Matched-basis flip probability of a depolarising hop (two of the three Paulis flip a basis)."""
    return 2.0 * depolarizing / 3.0


def compose_flips(flips: Iterable[float]) -> float:
    """Ordered composition of independent bit-flip channels: e <- e + f - 2 e f (not a sum of percentages)."""
    e = 0.0
    for f in flips:
        e = e + f - 2.0 * e * f
    return e


@dataclass(frozen=True)
class Node:
    id: str
    role: str
    label: Optional[str] = None


@dataclass(frozen=True)
class Edge:
    id: str
    src: str
    dst: str
    kind: str = "quantum"
    depolarizing: float = 0.0
    eta_loss: float = 0.0
    damping_gamma: float = 0.0
    cost: float = 1.0

    @property
    def honest_flip(self) -> float:
        """Uniform BB84 error of the Bell-half channel, averaged over correction bits."""
        return route_model((self,))["expected_qber"]

    @property
    def survival(self) -> float:
        return 1.0 - self.eta_loss

    @property
    def is_noiseless(self) -> bool:
        return self.depolarizing == 0 and self.eta_loss == 0 and self.damping_gamma == 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Topology:
    version: str
    nodes: Dict[str, Node]
    edges: Dict[str, Edge]
    max_hops: int = 4
    description: str = ""
    schema: str = TOPOLOGY_SCHEMA
    _out: Dict[str, List[Edge]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "nodes", MappingProxyType(dict(self.nodes)))
        object.__setattr__(self, "edges", MappingProxyType(dict(self.edges)))
        object.__setattr__(self, "_out", MappingProxyType({n: tuple(sorted(
            (e for e in self.edges.values() if e.src == n), key=lambda e: e.id)) for n in self.nodes}))

    @property
    def signer(self):
        return next(n.id for n in self.nodes.values() if n.role == "signer")

    # ------------------------------------------------------------ construction
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Topology":
        if not isinstance(d, dict):
            raise TopologyError("Topology must be a JSON object.")
        if d.get("schema", TOPOLOGY_SCHEMA) != TOPOLOGY_SCHEMA:
            raise TopologyError(f"Unsupported topology schema {d.get('schema')!r}; expected {TOPOLOGY_SCHEMA}.")
        version = d.get("version")
        if not isinstance(version, str) or not version.strip():
            raise TopologyError("Topology needs a non-empty 'version'.")
        for key, bound in (("nodes", MAX_NODES), ("edges", MAX_EDGES)):
            if not isinstance(d.get(key), list) or len(d[key]) > bound:
                raise TopologyError(f"{key} must be an array with at most {bound} entries.")
        if len(version) > 128 or not isinstance(d.get("description", ""), str) or len(d.get("description", "")) > 2000:
            raise TopologyError("Invalid version or description length/type.")
        nodes: Dict[str, Node] = {}
        for n in d["nodes"]:
            if not isinstance(n, dict):
                raise TopologyError("Each node must be an object.")
            nid, role = n.get("id"), n.get("role")
            if not isinstance(nid, str) or not nid.strip() or len(nid) > 128:
                raise TopologyError(f"Node without a valid id: {n!r}")
            if nid in nodes:
                raise TopologyError(f"Duplicate node id {nid!r}.")
            if role not in ROLES:
                raise TopologyError(f"Node {nid!r} has unknown role {role!r} (allowed: {', '.join(ROLES)}).")
            if role == "verifier" and nid not in VERIFIER_POOL:
                raise TopologyError(f"Verifier node {nid!r} is not an enrolled verifier identity.")
            if role != "verifier" and nid in VERIFIER_POOL:
                raise TopologyError(f"Enrolled verifier {nid!r} cannot take the role {role!r}.")
            if n.get("label") is not None and (not isinstance(n["label"], str) or len(n["label"]) > 128):
                raise TopologyError("Node labels must be strings of at most 128 characters.")
            nodes[nid] = Node(nid, role, n.get("label"))
        if sum(n.role == "signer" for n in nodes.values()) != 1:
            raise TopologyError("Topology needs exactly one signer node.")
        edges: Dict[str, Edge] = {}
        pairs = set()
        for e in d.get("edges") or []:
            edge = cls._edge(e, nodes)
            if edge.id in edges:
                raise TopologyError(f"Duplicate edge id {edge.id!r}.")
            if (edge.src, edge.dst) in pairs:
                raise TopologyError(f"Parallel edge {edge.src}->{edge.dst} ({edge.id!r}) is not supported.")
            pairs.add((edge.src, edge.dst))
            edges[edge.id] = edge
        max_hops = d.get("max_hops", 4)
        if type(max_hops) is not int or not 1 <= max_hops <= MAX_SUPPORTED_HOPS:
            raise TopologyError(f"max_hops must be an integer in 1..{MAX_SUPPORTED_HOPS}.")
        topo = cls(version=version.strip(), nodes=nodes, edges=edges, max_hops=max_hops,
                   description=str(d.get("description", "")))
        return topo

    @staticmethod
    def _edge(e: Dict[str, Any], nodes: Dict[str, Node]) -> Edge:
        if not isinstance(e, dict):
            raise TopologyError(f"Edge must be an object: {e!r}")
        src, dst = e.get("src"), e.get("dst")
        eid = e.get("id", f"{src}->{dst}")
        if not isinstance(eid, str) or not eid.strip() or len(eid) > 128:
            raise TopologyError("Edge id must be a nonempty string of at most 128 characters.")
        if not isinstance(src, str) or not isinstance(dst, str) or src not in nodes or dst not in nodes:
            raise TopologyError(f"Edge {eid!r} references an unknown node ({src!r} -> {dst!r}).")
        if src == dst:
            raise TopologyError(f"Self-edge {eid!r} is not supported.")
        if "kind" in e and e["kind"] != "quantum":
            raise TopologyError(f"Edge {eid!r}: only 'quantum' edges are modelled; the authenticated classical "
                                f"channel is assumed available and is not declared as edges.")
        if nodes[dst].role == "signer":
            raise TopologyError(f"Edge {eid!r} points into signer {dst!r}; distribution edges leave the signer.")
        if nodes[src].role == "verifier":
            raise TopologyError(f"Edge {eid!r} leaves verifier {src!r}; verifiers are never relays.")
        vals = {}
        for key, lo, hi in (("depolarizing", 0.0, 1.0), ("eta_loss", 0.0, 0.99), ("damping_gamma", 0.0, 1.0)):
            v = e.get(key, 0.0)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not (lo <= float(v) <= hi):
                raise TopologyError(f"Edge {eid!r}: {key} must be a number in [{lo}, {hi}].")
            vals[key] = float(v)
        cost = e.get("cost", 1.0)
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not (cost > 0 and math.isfinite(cost)):
            raise TopologyError(f"Edge {eid!r}: cost must be a positive finite number.")
        return Edge(eid, src, dst, "quantum", vals["depolarizing"], vals["eta_loss"], vals["damping_gamma"],
                    float(cost))

    @classmethod
    def load(cls, path: str) -> "Topology":
        try:
            with open(path, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError) as exc:
            raise TopologyError(f"Cannot read topology {path!r}: {exc}") from exc

    @classmethod
    def preset(cls, name: str) -> "Topology":
        """A bundled topology by name ('star' = the legacy single-relay star)."""
        if name in ("star", "legacy-star"):
            return legacy_star()
        safe = os.path.basename(name).removesuffix(".json")
        path = os.path.join(TOPOLOGY_DIR, safe + ".json")
        if not os.path.exists(path):
            raise TopologyError(f"Unknown topology preset {name!r}.")
        return cls.load(path)

    # ----------------------------------------------------------------- export
    def to_dict(self) -> Dict[str, Any]:
        return {"schema": self.schema, "version": self.version, "description": self.description,
                "max_hops": self.max_hops,
                "nodes": [{"id": n.id, "role": n.role, **({"label": n.label} if n.label else {})}
                          for n in sorted(self.nodes.values(), key=lambda n: n.id)],
                "edges": [e.to_dict() for e in sorted(self.edges.values(), key=lambda x: x.id)]}

    @property
    def digest(self) -> str:
        canon = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()

    # ------------------------------------------------------------------ paths
    def simple_paths(self, src: str, dst: str, limit: int = 64) -> List[Tuple[Edge, ...]]:
        """Every simple directed path src -> dst with at most max_hops edges (deterministic order)."""
        if src not in self.nodes or dst not in self.nodes:
            return []
        out: List[Tuple[Edge, ...]] = []
        stack: List[Tuple[str, Tuple[Edge, ...], frozenset]] = [(src, (), frozenset([src]))]
        expansions = 0
        while stack and len(out) < limit:
            expansions += 1
            if expansions > 10000:
                raise TopologyError("Path search incomplete: expansion budget exhausted.")
            node, path, seen = stack.pop()
            if node == dst and path:
                out.append(path)
                continue
            if len(path) >= self.max_hops:
                continue
            for e in reversed(self._out.get(node, [])):
                if e.dst in seen:
                    continue
                if self.nodes[e.dst].role == "verifier" and e.dst != dst:
                    continue          # never traverse another verifier
                stack.append((e.dst, path + (e,), seen | {e.dst}))
        return out

    def reachability(self, signer: Optional[str] = None) -> Dict[str, bool]:
        """Physical reachability in O(nodes + edges), respecting the hop bound."""
        signer = signer or self.signer
        depths = {signer: 0}
        queue = [signer]
        for node in queue:
            if depths[node] >= self.max_hops:
                continue
            for edge in self._out.get(node, ()):
                if edge.dst not in depths:
                    depths[edge.dst] = depths[node] + 1
                    queue.append(edge.dst)
        return {n.id: n.id in depths for n in self.nodes.values() if n.role == "verifier"}

    def summary(self) -> Dict[str, Any]:
        return {"version": self.version, "digest": self.digest, "max_hops": self.max_hops,
                "nodes": len(self.nodes), "edges": len(self.edges)}


def legacy_star(roster: Sequence[str] = VERIFIER_POOL) -> Topology:
    """The original topology: one quantum relay QR-1, one leaf edge per enrolled verifier, noiseless edges."""
    d = {"schema": TOPOLOGY_SCHEMA, "version": "legacy-star/1", "max_hops": 2,
         "description": "Original star through one quantum relay (compatibility default).",
         "nodes": [{"id": "alice", "role": "signer"}, {"id": "QR-1", "role": "relay"}]
                  + [{"id": v, "role": "verifier"} for v in roster],
         "edges": [{"id": "alice->QR-1", "src": "alice", "dst": "QR-1"}]
                  + [{"id": f"QR-1->{v}", "src": "QR-1", "dst": v} for v in roster]}
    return Topology.from_dict(d)


def route_model(edges) -> Dict[str, float]:
    """Diagonal Bloch transfer of depolarization then Bell-half damping per hop.

    Teleportation averages the Bell resource over Pauli corrections (a unital
    channel). Compose X/Z transfer coefficients, never scalar damping QBERs.
    Labels and descriptions are included in the topology digest.
    """
    lx = lz = survival = 1.0
    cost = 0.0
    for e in edges:
        dep = 1.0 - 4.0 * e.depolarizing / 3.0
        lx *= dep * math.sqrt(1.0 - e.damping_gamma)
        lz *= dep * (1.0 - e.damping_gamma)
        survival *= e.survival
        cost += e.cost
    x, z = (1.0 - lx) / 2.0, (1.0 - lz) / 2.0
    return {"qber_x": x, "qber_z": z, "expected_qber": (x + z) / 2.0,
            "qber_bound": max(x, z), "survival": survival, "cost": cost}
