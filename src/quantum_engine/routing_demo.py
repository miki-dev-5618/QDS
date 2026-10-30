"""Repeatable isolated failover proof using the actual planner and simulator."""
import numpy as np

from .channel import ChannelModel
from .enforcement import edge_scope, QUARANTINED, RESET_PENDING
from .monitoring import probe_edges


def run_failover_demo(backend="statevector", params=None):
    from .protocol import TeleportationQDS
    if backend not in ("statevector", "qiskit"):
        raise ValueError("The failover test requires the statevector or qiskit backend")
    engine = TeleportationQDS(backend=backend, params=params, topology="demo-multihop",
                             channel=ChannelModel(depolarizing=0))
    rng = np.random.default_rng(2026)
    try:
        before = engine.execute_protocol("Failover test: original route", 64, rng=rng).to_dict()
        engine.edge_injections["R1->R2"] = ChannelModel(depolarizing=0, intercept_rate=1)
        probe = probe_edges(engine, ["R1->R2"], rng, count=512)[0]
        after = engine.execute_protocol("Failover test: fresh preparation on alternate route", 64, rng=rng).to_dict()
        middle_state = engine.guard.state(edge_scope("R1->R2", engine.topology.digest))
        execution = after["routing"]["execution"]
        checks = {
            "baseline_used_R1_R2": all("R1" in r["nodes"] and "R2" in r["nodes"] for r in before["routing"]["plan"]["routes"].values()),
            "probe_quarantined_middle_edge": probe["transition"] is not None and probe["transition"]["new_state"] == QUARANTINED,
            "new_session_used_R3": all("R3" in r["nodes"] for r in after["routing"]["plan"]["routes"].values()),
            "alternate_carried_tokens": execution["edges"].get("alice->R3", {}).get("attempted", 0) > 0,
            "blocked_edge_carried_zero_new_tokens": execution["edges"].get("R1->R2", {}).get("attempted", 0) == 0,
            "failed_edge_still_quarantined": middle_state == QUARANTINED,
            "no_reset_performed": not any(t["new_state"] == RESET_PENDING or
                (t["old_state"] == QUARANTINED and t["new_state"] == "open") for t in engine.guard.transitions),
            "new_distribution_completed": execution["status"] == "completed",
        }
        return {"status": "passed" if all(checks.values()) else "failed", "isolated": True,
            "backend": backend, "seed": 2026, "checks": checks,
            "before": before["routing"], "probe": probe, "after": after["routing"],
            "blocked_edge": "R1->R2", "blocked_edge_after_send": middle_state,
            "verification_outcome": after["session_outcome"], "reset_calls": 0,
            "note": "Isolated test using the actual routing/teleportation code. Your active topology, restrictions and live sessions were not changed."}
    finally:
        engine.store.close()
