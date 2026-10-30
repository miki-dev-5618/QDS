"""Independent edge probes with lifetime alpha spending and monitored recovery.

Each round uses fresh BB84 states; user evidence is never reused. Round r
spends alpha * 6/(pi*r)^2 across all tested edges. The sum over all rounds
and edges is at most alpha under the declared independent channel model.
"""
import math
import uuid
from types import SimpleNamespace

from .channel import ChannelModel, estimate_channel_qber
from .enforcement import edge_scope, RESET_PENDING
from .multihop import hop_jobs, count_traversal
from .policy import ResponseDecision
from .topology import route_model


def probe_edges(engine, edge_ids, rng, count=512):
    if not hasattr(engine.backend, "run_routes"):
        raise ValueError("Independent edge probes require statevector or qiskit")
    if type(count) is not int or not 64 <= count <= 4096:
        raise ValueError("Probe count must be an integer in 64..4096")
    topology = engine.topology
    if not edge_ids or any(e not in topology.edges for e in edge_ids) or len(set(edge_ids)) != len(edge_ids):
        raise ValueError("Select distinct edges from the active topology")
    round_id = int(engine.store.get_json("probe_round", 0)) + 1
    engine.store.put_json("probe_round", round_id)
    alpha = engine.params.false_alarm_alpha * 6 / (math.pi * round_id) ** 2 / len(edge_ids)
    strong = engine.params.strong_alpha * 6 / (math.pi * round_id) ** 2 / len(edge_ids)
    latest = engine.store.get_json("edge_probes", {})
    recovery = engine.store.get_json("edge_recovery", {})
    observations = []
    for eid in edge_ids:
        edge = topology.edges[eid]
        scope = edge_scope(eid, topology.digest)
        probe_id = "PROBE-" + uuid.uuid4().hex
        jobs, slots = [], []
        for _ in range(count):
            bit, basis = int(rng.integers(2)), int(rng.integers(2))
            slot = SimpleNamespace(bit=bit, basis=basis, meas_basis=basis)
            slots.append(slot)
            jobs.append(hop_jobs(slot, [edge], (None, None), ChannelModel(depolarizing=0),
                                 engine.edge_injections, rng))
        outcomes = engine.backend.run_routes(jobs, rng)
        tested = sum(not out.is_lost for out in outcomes)
        errors = sum(not out.is_lost and out.outcome != slot.bit for slot, out in zip(slots, outcomes))
        test = estimate_channel_qber(tested, errors, route_model([edge])["qber_bound"],
            alpha, planned_count=count, strong_alpha=strong, tokens_sent=count, tokens_planned=count,
            tokens_received=tested, tokens_lost=count-tested)
        # Loss is an availability observation, not a fabricated mismatch.
        availability_bad = tested < engine.routing_policy.min_survival * count
        action = "quarantine" if test.p_value <= strong and test.alarm else (
            "watch" if test.alarm or availability_bad else "none")
        decision = ResponseDecision("reject" if action != "none" else "accept", action,
            "strong" if action == "quarantine" else "weak" if action == "watch" else "none",
            test.p_value if test.alarm else 1.0, "Independent edge probe: " + (
                "excess matched-basis errors" if test.alarm else "insufficient survival" if availability_bad else "passed"))
        # Recovery must use NEW evidence gathered after reset, with >=1024
        # surviving tests over >=2 rounds. Earlier observations do not count.
        state = engine.guard.to_dict().get(scope, {})
        marker = (state.get("reset_epoch") or state.get("since")) if state.get("state") == RESET_PENDING else None
        rec = recovery.get(scope, {})
        if rec.get("reset_since") != marker or "tested" not in rec:
            rec = {"reset_since": marker, "tested": 0, "rounds": 0}
        if action == "none" and marker is not None:
            rec["tested"] += tested
            rec["rounds"] += 1
        elif action != "none":
            rec.update(tested=0, rounds=0)
        recovery[scope] = rec
        change = engine.guard.apply(scope, decision, probe_id, actor="independent_edge_probe",
            accepted=action == "none" and rec["tested"] >= 1024 and rec["rounds"] >= 2)
        counters = {}
        for js in jobs:
            count_traversal([edge], js, counters)
        observation = {"schema": "hedwig-edge-probe/1", "probe_id": probe_id,
            "edge": eid, "scope": scope, "topology_digest": topology.digest, "timestamp": engine.clock(),
            "calibration": "bell-half-depolarizing-damping/1", "round": round_id,
            "alpha_spending": {"round_alpha_per_edge": alpha, "lifetime_alpha": engine.params.false_alarm_alpha},
            "test": test.to_dict(), "execution": counters, "decision": decision.to_dict(),
            "transition": change, "recovery": rec, "evidence_source": "independent_edge_probe"}
        latest[scope] = observation
        engine.store.put_json("probe:" + probe_id, observation)
        if engine.audit:
            from .audit import AUDIT_VERSION
            engine.audit.issue({"version": AUDIT_VERSION, "kind": "edge_probe", "issued_at": engine.clock(),
                "observation": observation}, probe_id)
            if change and change.get("incident_id"):
                engine.audit.issue({"version": AUDIT_VERSION, "kind": "incident", "issued_at": engine.clock(),
                    "incident_id": change["incident_id"], "link": scope, "scope_label": eid,
                    "trigger": {"classification": "INDEPENDENT_EDGE_PROBE", "evidence_p": test.p_value},
                    "observation": observation}, change["incident_id"])
        observations.append(observation)
    engine.store.put_json("edge_probes", latest)
    engine.store.put_json("edge_recovery", recovery)
    return observations
