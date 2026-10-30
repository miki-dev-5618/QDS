"""Operational routes: planning, real teleportation, evidence, aborts and history."""
import copy
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from src.quantum_engine import (AuditAuthority, ChannelModel, ChannelGuard, Store, TeleportationQDS,
    ResponseDecision, verify_certificate, verify_chain)
from src.quantum_engine.enforcement import LINK_FORWARD, LINK_SIGNER, edge_scope, path_scope
from src.quantum_engine.monitoring import probe_edges
from src.quantum_engine.routing import allocate, RoutingPolicy, RouteUnavailable
from src.quantum_engine.teleportation import (StatevectorTeleportationBackend, QiskitTeleportationBackend,
    TeleportJob, build_multihop_circuit)
from src.quantum_engine.topology import Topology, TopologyError, route_model


def demo(**kwargs):
    return TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0),
                             topology="demo-multihop", **kwargs)


def fault(engine, eid, state="quarantined"):
    return engine.guard.manual(edge_scope(eid, engine.topology.digest), state, "test-admin", "manual test")


def test_canonical_immutable_topology_and_scope_identity():
    original = Topology.preset("demo-multihop")
    document = original.to_dict()
    document["nodes"].reverse()
    document["edges"].reverse()
    assert Topology.from_dict(document).digest == original.digest
    with pytest.raises(TypeError):
        original.nodes["rogue"] = original.nodes["alice"]
    with pytest.raises((AttributeError, TypeError)):
        original.max_hops = 1
    with pytest.raises(TypeError):
        original._out["alice"] = ()
    assert path_scope(["a|b", "c"], "one") != path_scope(["a", "b|c"], "one")
    assert edge_scope("same", "one") != edge_scope("same", "two")


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(nodes={}), lambda d: d.update(edges={}), lambda d: d.update(nodes=[None]),
    lambda d: d.update(max_hops=True), lambda d: d["nodes"][0].update(label=3),
    lambda d: d["edges"][0].update(id=[]), lambda d: d["edges"][0].update(src=[]),
    lambda d: d["edges"][0].update(cost=float("inf")),
    lambda d: d["edges"][0].update(depolarizing=float("nan")),
    lambda d: d["nodes"].append({"id": "second-signer", "role": "signer"}),
])
def test_malformed_topologies_raise_domain_errors(mutate):
    document = Topology.preset("demo-multihop").to_dict()
    mutate(document)
    with pytest.raises(TopologyError):
        Topology.from_dict(document)


def test_primary_middle_edge_probe_quarantine_and_fresh_reroute(rng):
    engine = demo()
    first = engine.execute_protocol("baseline", 32, rng=rng)
    before = copy.deepcopy(first.to_dict()["routing"])
    assert before["plan"]["routes"]["bob"]["nodes"] == ["alice", "R1", "R2", "bob"]
    engine.edge_injections["R1->R2"] = ChannelModel(depolarizing=0, intercept_rate=1)
    observation = probe_edges(engine, ["R1->R2"], rng)[0]
    assert observation["decision"]["response_action"] == "quarantine"
    assert engine.guard.state(edge_scope("R1->R2", engine.topology.digest)) == "quarantined"
    after = engine.execute_protocol("fresh", 32, rng=rng).to_dict()
    assert after["routing"]["plan"]["routes"]["bob"]["nodes"] == ["alice", "R3", "bob"]
    assert after["routing"]["plan"]["routes"]["bob"]["rerouted"]
    assert "R1->R2" not in after["routing"]["execution"]["edges"]
    assert first.to_dict()["routing"] == before
    assert after["session_outcome"] == "all_accepted"


def test_all_blocked_refuses_before_preparing_any_state(monkeypatch, rng):
    engine = demo()
    fault(engine, "R1->R2")
    fault(engine, "alice->R3")
    def forbidden(*args, **kwargs):
        pytest.fail("Preparation must follow complete roster preflight")
    monkeypatch.setattr(engine, "_prepare", forbidden)
    with pytest.raises(RouteUnavailable) as error:
        engine.distribute("alice", "no route", 32, rng)
    assert set(error.value.info["affected_recipients"]) == {"bob", "charlie"}
    assert error.value.info["search_complete"]
    assert engine.store.route_history() == []


def test_unrelated_edge_and_classical_quarantine_remain_local(rng):
    engine = demo()
    fault(engine, "R2->dave")
    engine.guard.manual(LINK_FORWARD, "quarantined", "admin", "forwarding fault")
    session = engine.distribute("alice", "unaffected", 32, rng)
    assert not session.aborted
    assert session.route_plan.to_dict()["routes"]["bob"]["nodes"] == ["alice", "R1", "R2", "bob"]


def test_watch_excluded_unless_explicit_fallback(rng):
    engine = demo()
    fault(engine, "R1->R2", "watch")
    fault(engine, "alice->R3", "watch")
    with pytest.raises(RouteUnavailable):
        engine.distribute("alice", "blocked", 32, rng)
    engine.routing_policy = RoutingPolicy(allow_watch=True)
    session = engine.distribute("alice", "explicit fallback", 32, rng)
    assert session.route_plan.to_dict()["routes"]["bob"]["watch_fallback"]
    assert session.allocation["test"]["suspicious"]


def test_search_prunes_blocked_edges_and_reports_work_exhaustion():
    topo = Topology.preset("demo-multihop")
    with pytest.raises(RouteUnavailable) as error:
        allocate(topo, ["bob", "charlie"], {}, 0, "bounded", 1, RoutingPolicy(max_expansions=1))
    assert error.value.info["reason"] == "search_incomplete"
    assert not error.value.info["search_complete"]
    states = {edge_scope("R1->R2", topo.digest): {"state": "quarantined"}}
    plan = allocate(topo, ["bob", "charlie"], states, 3, "fallback", 1).to_dict()
    assert plan["routes"]["bob"]["edges"] == ["alice->R3", "R3->bob"]


def test_eligible_path_beyond_old_64_candidate_cutoff_is_found():
    nodes = [{"id": "alice", "role": "signer"}, {"id": "bob", "role": "verifier"}]
    nodes += [{"id": f"{layer}{i}", "role": "relay"} for layer in ("a", "b") for i in range(10)]
    pairs = [("alice", f"a{i}") for i in range(10)] + [(f"a{i}", f"b{j}") for i in range(10) for j in range(10)] + [(f"b{j}", "bob") for j in range(10)]
    topology = Topology.from_dict({"version": "many-paths", "max_hops": 3, "nodes": nodes,
        "edges": [{"id": f"{a}->{b}", "src": a, "dst": b} for a, b in pairs]})
    paths = topology.simple_paths("alice", "bob", limit=200)
    assert len(paths) == 100
    states = {path_scope([e.id for e in path], topology.digest): {"state": "quarantined"} for path in paths[:99]}
    plan = allocate(topology, ["bob"], states, 0, "late-candidate", 0).to_dict()
    assert plan["routes"]["bob"]["edges"] == [e.id for e in paths[-1]]


def test_stale_monitoring_is_visible_and_can_be_excluded():
    topology = Topology.preset("demo-multihop")
    with pytest.raises(RouteUnavailable):
        allocate(topology, ["bob"], {}, 0, "unmonitored", 1000, RoutingPolicy(allow_unmonitored=False))
    probe = {edge_scope(e.id, topology.digest): {"timestamp": 1} for e in topology.edges.values()}
    plan = allocate(topology, ["bob"], {}, 0, "stale", 1000, probes=probe).to_dict()
    assert set(plan["routes"]["bob"]["monitoring"].values()) == {"stale"}
    engine = demo(routing_policy=RoutingPolicy(allow_unmonitored=False))
    fresh = {edge_scope(e.id, engine.topology.digest): {"timestamp": engine.clock()} for e in engine.topology.edges.values()}
    engine.store.put_json("edge_probes", fresh)
    session = engine.distribute("alice", "fresh probe", 32, np.random.default_rng(18))
    assert not session.aborted
    engine.store.put_json("edge_probes", {})
    assert engine.reveal(session).revealed_signature == []


def test_unreachable_recipient_is_distinct_from_restricted_route():
    topology = Topology.preset("demo-multihop")
    with pytest.raises(RouteUnavailable) as error:
        allocate(topology, ["bob", "kim"], {}, 0, "unreachable", 1)
    assert error.value.info["reason"] == "unreachable"
    assert error.value.info["affected_recipients"] == ["kim"]


@pytest.mark.parametrize("backend", [StatevectorTeleportationBackend, QiskitTeleportationBackend])
def test_ordered_multihop_pauli_channels_accumulate(backend, rng):
    jobs = [[TeleportJob(bit, basis, basis, noise_pauli=p),
             TeleportJob(0, 0, basis, noise_pauli=q), TeleportJob(0, 0, basis, noise_pauli=r)]
            for bit, basis in ((0, 0), (1, 0), (0, 1), (1, 1))
            for p, q, r in (("X", "X", None), ("X", "Z", "Y"), ("Z", None, None))]
    results = backend().run_routes(jobs, rng)
    for route, outcome in zip(jobs, results):
        initial = route[0]
        flips = sum(j.noise_pauli in (("X", "Y") if initial.basis == 0 else ("Z", "Y")) for j in route)
        assert outcome.outcome == (initial.bit ^ (flips % 2))


def test_end_to_end_alarm_restricts_paths_without_fabricating_edge_attribution(rng):
    engine = demo()
    result = engine.execute_protocol("disturbed", 32, rng=rng, channel=ChannelModel(depolarizing=0, intercept_rate=1))
    assert result.transcript.session.aborted
    restricted = {scope for scope, state in engine.guard.to_dict().items() if state["state"] in ("watch", "quarantined")}
    assert restricted and all(scope.startswith("path:") for scope in restricted)
    assert engine.guard.state(LINK_SIGNER) == "open"
    assert result.to_dict()["revealed"] is False


@pytest.mark.parametrize("backend", [StatevectorTeleportationBackend, QiskitTeleportationBackend])
def test_multihop_bell_corrections_preserve_all_bb84_states(backend, rng):
    routes = [[TeleportJob(bit, basis, basis)] + [TeleportJob(0, 0, basis) for _ in range(hops-1)]
              for hops in (2, 3, 4) for bit, basis in ((0, 0), (1, 0), (0, 1), (1, 1)) for _ in range(3)]
    results = backend().run_routes(routes, rng)
    assert all(out.outcome == jobs[0].bit for jobs, out in zip(routes, results))
    circuit = build_multihop_circuit(routes[-1])
    assert sum(inst.operation.name == "if_else" for inst in circuit.data) == 8


def test_damping_composes_bloch_coefficients_and_matches_simulation(rng):
    doc = Topology.preset("star").to_dict()
    for e in doc["edges"]:
        e["damping_gamma"] = 0.2
    topology = Topology.from_dict(doc)
    edges = [topology.edges["alice->QR-1"], topology.edges["QR-1->bob"]]
    single = route_model(edges[:1])
    assert single["expected_qber"] == pytest.approx((0.2 + 1 - math.sqrt(0.8))/4)
    model = route_model(edges)
    assert model["qber_z"] == pytest.approx((1 - 0.8**2)/2)
    jobs = [[TeleportJob(i % 2, i % 4 // 2, i % 4 // 2, damping_gamma=.2),
             TeleportJob(0, 0, i % 4 // 2, damping_gamma=.2)] for i in range(3000)]
    outs = StatevectorTeleportationBackend().run_routes(jobs, rng)
    error = np.mean([out.outcome != js[0].bit for out, js in zip(outs, jobs)])
    assert error == pytest.approx(model["expected_qber"], abs=.025)


def test_upstream_loss_never_counts_downstream_and_recipient_insufficiency(rng):
    engine = demo()
    engine.edge_injections["R2->bob"] = ChannelModel(depolarizing=0, eta_loss=1)
    session = engine.distribute("alice", "one recipient lost", 32, rng)
    assert session.insufficient_tokens and session.aborted
    assert not session.channel_test.early_abort  # loss is distinct from an interrupted stream
    assert session.route_execution["recipients"]["bob"]["received"] == 0
    assert session.route_execution["recipients"]["charlie"]["received"] > 0
    assert engine.reveal(session).revealed_signature == []
    engine = demo()
    engine.edge_injections["alice->R1"] = ChannelModel(depolarizing=0, eta_loss=1)
    session = engine.distribute("alice", "upstream loss", 32, rng)
    assert set(session.route_execution["edges"]) == {"alice->R1"}
    assert session.route_execution["edges"]["alice->R1"]["received"] == 0


def test_mid_distribution_restriction_aborts_frozen_plan_without_reveal(rng):
    engine = demo()
    backend = engine.backend
    class RestrictAfterBlock:
        name = "restriction-test"
        def run_routes(self, jobs, rng):
            result = backend.run_routes(jobs, rng)
            fault(engine, "R1->R2")
            return result
    engine.backend = RestrictAfterBlock()
    session = engine.distribute("alice", "blocked in flight", 32, rng)
    assert session.aborted and session.tokens_sent < session.tokens_planned
    assert session.route_execution["stopping_scope"] == edge_scope("R1->R2", engine.topology.digest)
    assert engine.reveal(session).revealed_signature == []
    assert session.route_plan.to_dict()["routes"]["bob"]["nodes"] == ["alice", "R1", "R2", "bob"]
    assert all(r.aborted for v in engine.verifiers.values() for r in v.records.values())


def test_quarantine_between_distribution_and_reveal_is_checked(rng):
    engine = demo()
    session = engine.distribute("alice", "reveal gate", 32, rng)
    assert not session.aborted
    fault(engine, "R1->R2")
    assert engine.reveal(session).revealed_signature == []
    assert session.route_execution["status"] == "aborted"
    assert not session.route_execution["reveal_allowed"]


def test_edge_recovery_requires_new_monitored_probation_evidence(rng):
    engine = demo(clock=lambda: 1000.0)
    fault(engine, "R1->R2")
    scope = edge_scope("R1->R2", engine.topology.digest)
    engine.guard.request_reset(scope)
    probe_edges(engine, ["R1->R2"], rng, count=1024)
    assert engine.guard.state(scope) == "reset_pending"  # at least two rounds
    probe_edges(engine, ["R1->R2"], rng, count=1024)
    assert engine.guard.state(scope) == "open"
    fault(engine, "R1->R2")
    engine.guard.request_reset(scope)
    probe_edges(engine, ["R1->R2"], rng, count=1024)
    assert engine.guard.state(scope) == "reset_pending"  # old recovery evidence cannot cross reset epochs


def test_restart_preserves_topology_restrictions_history_and_signed_routes(tmp_path, rng):
    store = Store(str(tmp_path / "routing.db"))
    authority = AuditAuthority(str(tmp_path / "key.pem"), store=store, pq=False)
    engine = demo(store=store, audit=authority)
    result = engine.execute_protocol("signed baseline", 32, rng=rng)
    cert = result.audit_cert
    assert verify_certificate(cert)
    corrupt = copy.deepcopy(cert)
    corrupt["record"]["routing"]["plan_sha256"] = "invented"
    assert not verify_certificate(corrupt)
    corrupt = copy.deepcopy(cert)
    corrupt["evidence"]["routing"]["plan"]["routes"]["bob"]["edges"] = ["invented"]
    assert not verify_certificate(corrupt)
    corrupt = copy.deepcopy(cert)
    corrupt["evidence"]["routing"]["execution"]["attempted"] += 1
    assert not verify_certificate(corrupt)
    saved = store.route_session(result.transcript.session.context.session_id)
    fault(engine, "R1->R2")
    engine.activate_topology(Topology.preset("star").to_dict())
    restarted = TeleportationQDS(backend="statevector", store=Store(store.path))
    assert restarted.topology.version == "legacy-star/1"
    assert restarted.guard.state(edge_scope("R1->R2", saved["plan"]["topology_digest"])) == "quarantined"
    assert restarted.store.route_session(saved["plan"]["session_id"]) == saved
    assert verify_chain(store.audit_chain())["valid"]


def test_duplicate_assessment_is_idempotent_and_emergency_is_explicit(tmp_path):
    store = Store(str(tmp_path / "states.db"))
    guard = ChannelGuard(store=store)
    weak = ResponseDecision("reject", "watch", "weak", .05, "probe observation")
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda _: guard.apply("edge:test", weak, "PROBE-same"), range(8)))
    assert guard.links["edge:test"].strikes == 1
    assert ChannelGuard(store=Store(store.path)).apply("edge:test", weak, "PROBE-same") is None
    guard.emergency(True, "admin", "maintenance")
    guard.request_reset()
    with pytest.raises(Exception, match="emergency"):
        guard.check_open(LINK_SIGNER)
    guard.emergency(False, "admin", "maintenance complete")
    guard.check_open(LINK_SIGNER)
