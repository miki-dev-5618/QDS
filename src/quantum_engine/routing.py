"""Pure bounded route allocation, frozen before quantum preparation."""
import heapq
import itertools
import json
from dataclasses import dataclass

from .enforcement import (ChannelQuarantined, LINK_SIGNER, EMERGENCY, OPEN, WATCH,
                          RESET_PENDING, edge_scope, path_scope)
from .topology import route_model


class RouteUnavailable(ChannelQuarantined):
    status = "route_unavailable"


@dataclass(frozen=True)
class RoutingPolicy:
    version: str = "hedwig-routing/1"
    allow_watch: bool = False
    allow_unmonitored: bool = True
    allow_probation: bool = True
    max_qber: float = 0.08
    min_survival: float = 0.6
    max_expansions: int = 10000
    probe_ttl: float = 300.0


@dataclass(frozen=True)
class RoutePlan:
    """JSON bytes enforce deep immutability; readers always receive a fresh copy."""
    payload: str

    def to_dict(self):
        return json.loads(self.payload)


def required_scopes(plan):
    d = plan.to_dict() if isinstance(plan, RoutePlan) else plan
    scopes = [LINK_SIGNER]
    for r in d["routes"].values():
        scopes.extend([r["route_id"], *r["edge_scopes"]])
    return list(dict.fromkeys(scopes))


def allocate(topology, roster, states, revision, session_id, now, policy=None, probes=None):
    policy = policy or RoutingPolicy()
    probes = probes or {}
    digest = topology.digest
    routes, decisions, failed = {}, {}, []
    physical = topology.reachability()
    for global_scope in (EMERGENCY, LINK_SIGNER):
        if states.get(global_scope, {}).get("state", OPEN) == "quarantined":
            raise RouteUnavailable(global_scope, {"operation": "distribution", "reason": "scope_restricted",
                "topology_digest": digest, "affected_recipients": list(roster), "search_complete": True})
    allowed_states = {OPEN}
    if policy.allow_watch:
        allowed_states.add(WATCH)
    if policy.allow_probation:
        allowed_states.add(RESET_PENDING)
    for recipient in roster:
        if not physical.get(recipient, False):
            decisions[recipient] = {"reason": "unreachable", "rejected": [], "expansions": 0, "search_complete": True}
            failed.append(recipient)
            continue
        rejected, selected, expansions = [], None, 0
        counter = itertools.count()
        # Cost-aware simple-path search. Blocked edges are pruned BEFORE expansion.
        queue = [(0, 0, 0.0, (), next(counter), topology.signer, (), frozenset([topology.signer]))]
        while queue and expansions < policy.max_expansions:
            risk, monitor_class, cost, ids, _, node, path, seen = heapq.heappop(queue)
            expansions += 1
            if node == recipient:
                model = route_model(path)
                scope = path_scope(ids, digest)
                path_state = states.get(scope, {}).get("state", OPEN)
                path_risk = {OPEN: 0, RESET_PENDING: 1, WATCH: 2}.get(path_state, 3)
                if path_state in allowed_states and path_risk > risk:
                    heapq.heappush(queue, (path_risk, monitor_class, cost, ids, next(counter), node, path, seen))
                    continue
                reason = None
                if states.get(scope, {}).get("state", OPEN) not in allowed_states:
                    reason = "path_restricted"
                elif model["qber_bound"] > policy.max_qber:
                    reason = "excessive_expected_error"
                elif model["survival"] < policy.min_survival:
                    reason = "insufficient_expected_survival"
                if reason:
                    rejected.append({"edges": list(ids), "reason": reason, "model": model})
                    continue
                selected = {"recipient": recipient, "route_id": scope, "edges": list(ids),
                    "nodes": [topology.signer] + [e.dst for e in path], "hops": len(path), **model,
                    "edge_scopes": [edge_scope(e.id, digest) for e in path],
                    "monitoring": {e.id: freshness(probes.get(edge_scope(e.id, digest)), now, policy) for e in path},
                    "fallback": bool(rejected), "reason": "Preferred state/freshness class, then lowest eligible cost" + (
                        "; excluded candidates/scopes recorded" if rejected else ""),
                    "watch_fallback": any(states.get(s, {}).get("state") == WATCH for s in
                        [scope] + [edge_scope(e.id, digest) for e in path])}
                break
            if len(path) >= topology.max_hops:
                continue
            for e in topology._out.get(node, ()):
                if e.dst in seen or (topology.nodes[e.dst].role == "verifier" and e.dst != recipient):
                    continue
                scope = edge_scope(e.id, digest)
                state = states.get(scope, {}).get("state", OPEN)
                fresh = freshness(probes.get(scope), now, policy)
                if state not in allowed_states or (not policy.allow_unmonitored and fresh != "fresh"):
                    rejected.append({"edge": e.id, "scope": scope, "state": state,
                        "monitoring": fresh, "reason": "edge_restricted" if state not in allowed_states else "monitoring_required"})
                    continue
                heapq.heappush(queue, (max(risk, {OPEN: 0, RESET_PENDING: 1, WATCH: 2}[state]),
                                      max(monitor_class, {"fresh": 0, "unmonitored": 1, "stale": 2}[fresh]),
                                      cost + e.cost, ids + (e.id,), next(counter), e.dst,
                                      path + (e,), seen | {e.dst}))
        complete = not queue
        decisions[recipient] = {"rejected": rejected, "expansions": expansions,
            "search_complete": complete, "selection_proven_optimal": selected is not None,
            "search": "bounded simple paths; prefer OPEN, fresh monitoring, lowest cost, stable edge IDs"}
        if selected:
            routes[recipient] = selected
        else:
            failed.append(recipient)
    if failed:
        reason = "unreachable" if any(decisions[v].get("reason") == "unreachable" for v in failed) else (
            "search_incomplete" if any(not decisions[v]["search_complete"] for v in failed) else "no_eligible_route")
        raise RouteUnavailable(LINK_SIGNER, {"operation": "distribution", "reason": reason,
            "topology_digest": digest, "affected_recipients": failed, "candidates": decisions,
            "search_complete": all(decisions[v]["search_complete"] for v in failed)},
            "No eligible quantum route for " + ", ".join(failed) + "; " + reason)
    return RoutePlan(json.dumps({"schema": "hedwig-route-plan/1", "session_id": session_id,
        "created_at": now, "signer": topology.signer, "roster": list(roster), "topology": topology.to_dict(),
        "topology_digest": digest, "policy": policy.__dict__, "state_revision": revision,
        "edge_scope_map": {e.id: edge_scope(e.id, digest) for e in topology.edges.values()},
        "monitoring_snapshot": {e.id: freshness(probes.get(edge_scope(e.id, digest)), now, policy) for e in topology.edges.values()},
        "scope_snapshot": states, "routes": routes, "candidates": decisions}, sort_keys=True))


def freshness(probe, now, policy):
    return "unmonitored" if not probe else "fresh" if now - probe["timestamp"] <= policy.probe_ttl else "stale"
