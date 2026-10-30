"""Optional N-verifier extension: roster, uniform-holder symmetrisation, depth rules, chain transfers, records."""
import copy

import numpy as np
import pytest

from src.quantum_engine import (
    AuditAuthority, ChannelModel, ConfigurationError, SessionConfig, Store, TeleportationQDS, ThreatClassification,
    ThreatScenarioConfig, ThreatType, UnknownParticipant, verify_certificate_report, verify_chain,
)
from src.quantum_engine.audit import build_evidence, build_record, evidence_digests
from src.quantum_engine.security import SecurityParameters
from src.quantum_engine.symmetrisation import UniformHolderAssignment
from src.quantum_engine.threats import ThreatSuite

P = SecurityParameters()


def _engine(clock, audit=False, store=None):
    store = store or Store(":memory:")
    return TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0), clock=clock, store=store,
                            audit=AuditAuthority(store=store, pq=False) if audit else None)


def chain(n, h=None):
    return SessionConfig.build(n_verifiers=n, delivery="chain", max_depth=h)


# ------------------------------------------------------------------ configuration
@pytest.mark.parametrize("kwargs", [
    dict(roster=["bob", "bob"]),                                   # duplicate identity
    dict(roster=["bob", "mallory"]),                               # not enrolled
    dict(n_verifiers=1), dict(n_verifiers=11),                     # outside the supported range
    dict(n_verifiers=4, delivery="chain", max_depth=4),            # H > N - 1
    dict(n_verifiers=4, delivery="chain", max_depth=0),
    dict(n_verifiers=3, delivery="direct", max_depth=2),           # direct mode supports one hop only
    dict(n_verifiers=3, delivery="broadcast"),
])
def test_invalid_configurations_are_rejected_before_distribution(kwargs):
    with pytest.raises(ConfigurationError):
        SessionConfig.build(**kwargs)


def test_dishonest_forwarder_needs_a_downstream_recipient():
    cfg = chain(4, 2)                                              # route bob -> charlie -> dave
    with pytest.raises(ConfigurationError):
        cfg.validate_dishonest("dave")                             # dave is at depth H: nobody to forward to
    with pytest.raises(ConfigurationError):
        ThreatSuite.validate(ThreatScenarioConfig(ThreatType.FORWARD_WITHHELD, dishonest_verifier="bob"),
                             SessionConfig.build(n_verifiers=3))   # chain-only scenario in direct mode
    cfg.validate_dishonest("charlie")


def test_default_config_is_the_original_two_verifier_session():
    cfg = SessionConfig.build()
    assert cfg.roster == ("bob", "charlie") and cfg.delivery == "direct" and cfg.max_depth == 1 and cfg.is_default


def test_roster_depth_and_route_are_committed_in_the_context(engine, rng):
    s = engine.distribute("alice", "m", 16, rng, config=chain(4))
    ctx = s.context
    assert ctx.verifiers == ["bob", "charlie", "dave", "erin"] and ctx.delivery == "chain" and ctx.max_depth == 3


# ------------------------------------------------------------------ symmetrisation
@pytest.mark.parametrize("n", [3, 5, 10])
def test_uniform_holder_conserves_every_copy(n):
    roster = [f"v{i}" for i in range(n)]
    L = 40
    initial = {v: [(i % 2, (i // 2) % 2) for i in range(L)] for v in roster}
    dest, held, _, source = UniformHolderAssignment.assign(initial, roster, np.random.default_rng(1))
    for i in range(L):
        assert sum(len(held[v][i]) for v in roster) == n                      # nothing duplicated or lost
        assert sorted(s for v in roster for s in source[v][i]) == sorted(roster)  # each source copy exactly once
        for src in roster:
            assert src in source[dest[src][i]][i]                             # unambiguous final holder


def test_uniform_holder_probabilities_match_keep_or_forward_at_two():
    rng = np.random.default_rng(3)
    initial = {"a": [(0, 0)] * 20000, "b": [(0, 0)] * 20000}
    dest, _, _, _ = UniformHolderAssignment.assign(initial, ["a", "b"], rng)
    kept = np.mean([d == "a" for d in dest["a"]])
    assert abs(kept - 0.5) < 0.02                                             # P(keep) = 1/2, as keep-or-forward


def test_uniform_holder_is_uniform_for_larger_groups():
    rng = np.random.default_rng(4)
    roster = ["a", "b", "c", "d", "e"]
    dest, _, _, _ = UniformHolderAssignment.assign({v: [(0, 0)] * 8000 for v in roster}, roster, rng)
    counts = {v: sum(d == v for src in roster for d in dest[src]) for v in roster}
    assert all(abs(c / 40000 - 0.2) < 0.01 for c in counts.values())


def test_each_verifier_holds_only_its_assigned_evidence(engine, rng):
    s = engine.distribute("alice", "m", 24, rng, config=SessionConfig.build(n_verifiers=5))
    total = 0
    for v in s.config.roster:
        rec = engine.verifiers[v].records[s.context.session_id]
        assert len(rec.eliminated) == 24
        total += sum(len(row) for row in rec.eliminated)
    assert total == 5 * 24                                                     # one copy per recipient per position
    assert s.signature == engine.reveal(s).revealed_signature


# ------------------------------------------------------------------ depth rules
@pytest.mark.parametrize("n", [16, 64, 128, 256])
def test_depth_one_of_one_reproduces_the_original_rules(n):
    assert P.elimination_rule(n, depth=0, max_depth=1).a1 == P.elimination_rule(n, False).a1
    assert P.elimination_rule(n, depth=1, max_depth=1).a1 == P.elimination_rule(n, True).a1


@pytest.mark.parametrize("n,h", [(128, 3), (128, 9), (256, 5), (64, 4), (24, 3)])
def test_depth_limits_are_monotone_bounded_and_each_meets_the_targets(n, h):
    rules = [P.elimination_rule(n, depth=l, max_depth=h) for l in range(h + 1)]
    limits = [r.a1 for r in rules]
    assert limits == sorted(limits)                                             # non-decreasing in depth
    assert limits[0] == P.elimination_rule(n, False).a1 and limits[-1] == P.elimination_rule(n, True).a1
    for r in rules:
        assert r.depth <= h and r.max_depth == h
        if rules[0].sufficient and rules[-1].sufficient:
            assert r.sufficient and r.false_reject <= P.fr_target and r.forgery_accept <= P.fa_target


def test_short_samples_do_not_invent_distinct_depth_thresholds():
    rules = [P.elimination_rule(32, n_reserve=16, depth=l, max_depth=4) for l in range(5)]
    assert len({(r.a1, r.r1, r.a2) for r in rules}) == 1                         # evidence too thin: no margin granted


def test_legacy_depth_schedule_is_labelled_experimental():
    legacy = SecurityParameters(threshold_policy="legacy")
    assert abs(legacy.limit_rate(False, 0, 1) - legacy.s_a) < 1e-12
    assert abs(legacy.limit_rate(True, 1, 1) - legacy.s_v) < 1e-12
    b = legacy.bounds(100, 0, True, rule=legacy.elimination_rule(100, depth=2, max_depth=3))
    assert "experimental" in b["schedule_status"]


# ------------------------------------------------------------------ delivery
@pytest.mark.parametrize("n", [2, 3, 5, 10])
def test_honest_direct_delivery_to_every_recipient(clock, n):
    eng = _engine(clock)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(n), config=SessionConfig.build(n_verifiers=n))
    d = res.to_dict()
    assert len(res.transcript.results) == n
    assert {r.verifier for r in res.transcript.results} == set(SessionConfig.build(n_verifiers=n).roster)
    assert all(r.accepted for r in res.transcript.results)
    assert d["session_outcome"] == "all_accepted" and len(d["participants"]) == n
    assert not res.threat_report.is_threat_detected


@pytest.mark.parametrize("n", [3, 5, 10])
def test_honest_chain_reaches_everyone_at_its_validated_depth(clock, n):
    eng = _engine(clock)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(n), config=chain(n))
    results = res.transcript.results
    assert [r.verifier for r in results] == list(chain(n).roster)
    assert [r.depth for r in results] == list(range(n))
    assert all(r.accepted and r.transfer_valid for r in results)
    assert all(r.parent_event_id == results[i].event_id for i, r in enumerate(results[1:]))
    assert res.to_dict()["session_outcome"] == "all_accepted"


def test_depth_bound_leaves_later_members_outside_the_route(clock):
    eng = _engine(clock)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(2), config=chain(5, 2))
    d = res.to_dict()
    status = {r["verifier"]: r["status"] for r in d["participants"]}
    assert [r.verifier for r in res.transcript.results] == ["bob", "charlie", "dave"]
    assert status["erin"] == status["frank"] == "outside_depth"
    assert d["session_outcome"] == "all_accepted"


# ------------------------------------------------------------------ attacks
@pytest.mark.parametrize("alteration", ["message", "signature"])
def test_dishonest_forwarder_is_caught_by_the_next_honest_recipient(clock, alteration):
    eng = _engine(clock)
    sc = ThreatScenarioConfig(ThreatType.DISHONEST_FORWARDER, dishonest_verifier="charlie",
                              forward_alteration=alteration)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(5), config=chain(5), scenario=sc)
    by = {r.verifier: r for r in res.transcript.results}
    assert by["bob"].accepted and by["charlie"].accepted                       # honest until the dishonest hop
    assert not by["dave"].accepted and not by["dave"].binding_pass
    # The commitment covers context + signature; the message is bound through the context digest.
    assert by["dave"].digest_matches is (alteration != "message")
    assert by["dave"].commitment_matches is (alteration == "message")
    status = {r["verifier"]: r["status"] for r in res.to_dict()["participants"]}
    assert status["erin"] == "not_reached"                                       # stopped, not rejected
    assert res.threat_report.classification == ThreatClassification.DISHONEST_VERIFIER_FORGERY
    assert res.to_dict()["session_outcome"] == "rejected"


def test_withholding_marks_downstream_not_reached_without_alleging_forgery(clock):
    eng = _engine(clock)
    sc = ThreatScenarioConfig(ThreatType.FORWARD_WITHHELD, dishonest_verifier="charlie")
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(6), config=chain(4), scenario=sc)
    d = res.to_dict()
    assert d["session_outcome"] == "incomplete"
    assert [r["status"] for r in d["participants"]] == ["accepted", "accepted", "not_reached", "not_reached"]
    assert not res.threat_report.is_threat_detected                              # withholding is not forgery


def test_depth_manipulation_is_refused_before_a_looser_rule_applies(clock):
    eng = _engine(clock)
    sc = ThreatScenarioConfig(ThreatType.ROUTE_MANIPULATION, dishonest_verifier="bob")
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(7), config=chain(4), scenario=sc)
    victim = res.transcript.results[1]
    assert victim.claimed_depth == 2 and not victim.transfer_valid and not victim.accepted
    assert victim.depth == 0                                                       # evaluated at the strictest level
    assert res.threat_report.classification == ThreatClassification.INVALID_TRANSFER
    assert res.response.response_action == "none"                                  # classical: no lock-out


def test_unknown_forwarder_is_rejected(clock):
    eng = _engine(clock)
    sc = ThreatScenarioConfig(ThreatType.UNKNOWN_FORWARDER)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(8), config=SessionConfig.build(n_verifiers=3),
                               scenario=sc)
    bad = res.transcript.results[-1]
    assert bad.forwarded_by == "mallory" and not bad.transfer_valid and not bad.accepted
    assert res.threat_report.classification == ThreatClassification.INVALID_TRANSFER


def test_forward_to_unenrolled_recipient_raises(engine, rng):
    s = engine.distribute("alice", "m", 16, rng)
    with pytest.raises(UnknownParticipant):
        engine.forward(engine.reveal(s), "bob", "mallory")


@pytest.mark.parametrize("cfg", [SessionConfig.build(n_verifiers=3), chain(3)])
def test_repeated_forwarding_is_bounded_and_never_overwrites(clock, cfg):
    eng = _engine(clock)
    sc = ThreatScenarioConfig(ThreatType.FORWARD_REPLAY, dishonest_verifier="bob")
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(9), config=cfg, scenario=sc)
    dup = res.transcript.results[-1]
    assert dup.duplicate and not dup.accepted
    assert dup.freshness_reason in ("duplicate_delivery", "duplicate_nonce")   # same sender: nonce already spent
    assert dup.decision_stage == 1 and not dup.reserve_requested                 # no further evidence spent
    events = eng.ledger.events(res.transcript.package.context.session_id)
    assert len({e["event_id"] for e in events}) == len(events) == len(res.transcript.results)
    assert res.threat_report.classification == ThreatClassification.REPLAY_ATTACK


def test_forger_cannot_claim_a_parent_of_another_participant(engine, rng):
    s = engine.distribute("alice", "m", 32, rng, config=chain(3))
    pkg = engine.reveal(s)
    first = engine.deliver(pkg, session=s)[0]                                    # bob, depth 0
    # charlie never verified, yet names bob's event as its parent on the (permitted) edge charlie -> dave
    stolen = engine.forward(pkg, "charlie", "dave", parent_event_id=first.event_id)
    assert not stolen.transfer_valid and not stolen.accepted
    assert any("substituted parent" in r for r in stolen.transfer_reasons)
    invented = engine.forward(pkg, "bob", "charlie", parent_event_id="EV-NOT-REAL")
    assert not invented.transfer_valid and not invented.accepted


def test_reserve_is_bounded_per_session_across_channels(clock):
    from src.quantum_engine.binding import ReserveOpening, SignedContext, SignedPackage, commitment, new_blinding, \
        reserve_commitment
    from src.quantum_engine.channel import estimate_channel_qber
    from src.quantum_engine.verifier import DistributionRecord, VerifierNode
    cfg = SessionConfig.build(n_verifiers=3)
    v = VerifierNode("charlie", P, clock=clock)
    ctx = SignedContext.new("alice", list(cfg.roster), "m", timestamp=clock())
    sig, b = [(0, 0)] * 30, new_blinding()
    rsv, rb = [(0, 0)] * 30, new_blinding()
    elim = [['|0⟩'] if i < 1 else ['|1⟩'] for i in range(30)]                  # one mismatch: borderline
    v.receive_distribution(DistributionRecord(
        ctx.session_id, "alice", commitment(ctx, sig, b), elim, [[]] * 30,
        estimate_channel_qber(64, 0, P.honest_qber, P.false_alarm_alpha), False,
        reserve_eliminated=[['|1⟩']] * 30, reserve_commitment=reserve_commitment(ctx, rsv, rb), config=cfg))
    pkg = SignedPackage(ctx, "m", sig, b, reserve=ReserveOpening(tuple(rsv), rb))
    first = v.verify(pkg)
    assert first.decision_stage == 2
    parent = {"event_id": first.event_id, "session_id": ctx.session_id, "verifier": "bob", "depth": 0}
    second = v.verify(pkg.copy(forwarded_by="bob", parent_event_id="EV-X"), "forwarded", parent=parent)
    assert second.decision_stage == 1                                             # reserve not opened twice


# ------------------------------------------------------------------ records and access
def test_chain_records_are_linked_immutable_and_verify(clock):
    eng = _engine(clock, audit=True)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(10), config=chain(4))
    tx_cert = res.audit_cert
    assert tx_cert["record"]["version"] == "hedwig-audit/3"
    assert tx_cert["record"]["session"]["config"]["roster"] == ["bob", "charlie", "dave", "erin"]
    assert len(res.transfer_records) == 3
    certs = [eng.store.get_audit(t["artifact_id"]) for t in res.transfer_records]
    parents = [c["record"]["parent_record"]["artifact_id"] for c in certs]
    assert parents == [res.transmission_id, certs[0]["record"]["event_id"], certs[1]["record"]["event_id"]]
    assert certs[0]["record"]["parent_record"]["payload_sha256"] == tx_cert["payload_sha256"]
    for c in certs:
        assert c["record"]["kind"] == "transfer"
        assert c["record"]["signed_context"]["sender"] == "alice"                # original context preserved
        assert verify_certificate_report(c, eng.audit.trusted_keys())["valid"]
    assert verify_chain(eng.store.audit_chain(), eng.audit.trusted_keys())["valid"]


def test_events_survive_restart_as_history_only(clock, tmp_path):
    path = str(tmp_path / "h.db")
    eng = _engine(clock, store=Store(path))
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(11), config=chain(3))
    sid = res.transcript.package.context.session_id
    eng.store.close()
    fresh = TeleportationQDS(backend="statevector", clock=clock, store=Store(path))
    events = fresh.ledger.events(sid)
    assert [e["verifier"] for e in events] == ["bob", "charlie", "dave"]
    assert all(e["transmission_id"] == res.transmission_id for e in events)
    assert fresh.store.get_session(sid)["config"]["delivery"] == "chain"
    # The one-time quantum evidence is not persisted: re-verification after restart fails clearly.
    again = fresh.deliver(res.transcript.package, to=["bob"])[0]
    assert not again.accepted and not again.record_found


def test_v2_certificates_remain_verifiable(clock):
    eng = _engine(clock, audit=True)
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(12))
    tx = res.to_dict()
    ev = build_evidence(tx)
    ev.pop("session_config")
    for v in ev["verifications"].values():
        v.pop("event_id", None)
    old = build_record(tx, eng.params.to_dict(), eng.policy.to_dict(), ev)
    old["version"] = "hedwig-audit/2"
    old["evidence_digests"] = evidence_digests(ev, "hedwig-audit/2")
    cert = eng.audit.sign(old, ev)
    cert["format"] = "hedwig-audit/2"
    rep = verify_certificate_report(cert, eng.audit.trusted_keys())
    assert rep["valid"] and rep["checks"]["schema_version"] == "hedwig-audit/2"
    tampered = copy.deepcopy(cert)
    tampered["evidence"]["channel_test"] = {"forged": True}
    assert not verify_certificate_report(tampered, eng.audit.trusted_keys())["valid"]


def test_detector_inputs_exclude_ground_truth(clock):
    eng = _engine(clock)
    sc = ThreatScenarioConfig(ThreatType.DISHONEST_FORWARDER, dishonest_verifier="bob")
    res = eng.execute_protocol("order", 32, rng=np.random.default_rng(13), config=chain(3), scenario=sc)
    assert res.ground_truth["dishonest_verifier"] == "bob"
    t = res.transcript
    again = eng.detector.classify(t.results, t.channel_test)
    assert again.classification == res.threat_report.classification
