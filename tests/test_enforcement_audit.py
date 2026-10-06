"""Circuit breaker state machine, persistence, early abort, router, and signed audit records."""
import copy

import numpy as np
import pytest

from src.quantum_engine import (
    AuditAuthority, ChannelGuard, ChannelModel, ChannelQuarantined, LINK_FORWARD, LINK_SIGNER, ResponseDecision,
    ResponsePolicy, SimulatedRouter, Store, TeleportationQDS, ThreatClassification, ThreatScenarioConfig, ThreatType,
    build_record, pq_provider, verify_certificate, verify_certificate_report, verify_chain,
)
from src.quantum_engine.audit import build_evidence


def _intercept(engine, rng, n_bits=64):
    return engine.execute_protocol("m", n_bits, rng=rng,
                                   scenario=ThreatScenarioConfig(threat_type=ThreatType.EVE_INTERCEPT))


WEAK = ResponseDecision("reject", "watch", "weak", 0.05, "weak test alert")
STRONG = ResponseDecision("reject", "quarantine", "strong", 1e-6, "strong test alert")
NONE = ResponseDecision("accept", "none", "none", 1.0, "ok")


# ------------------------------------------------------------ state machine
def test_alert_quarantines_link_until_reset(engine):
    rng = np.random.default_rng(1)
    r = _intercept(engine, rng)
    assert r.threat_report.classification == ThreatClassification.EAVESDROPPING_TAMPERING
    assert r.enforcement["action"] == "link_quarantined"
    assert r.enforcement["incident_id"].startswith("INC-")
    with pytest.raises(ChannelQuarantined):
        engine.execute_protocol("follow-up", 32, rng=rng)
    engine.guard.reset(LINK_SIGNER, actor="admin", reason="test")
    assert engine.guard.state(LINK_SIGNER) == "reset_pending"
    after = engine.execute_protocol("after reset", 32, rng=rng)
    assert not after.threat_report.is_threat_detected
    assert after.enforcement["action"] == "probation_passed"
    assert engine.guard.state(LINK_SIGNER) == "open"


def test_quarantine_purges_pending_records(engine):
    rng = np.random.default_rng(2)
    engine.distribute("alice", "never revealed", 16, rng)
    r = _intercept(engine, rng)
    assert r.enforcement["purged_records"] >= 2  # pending session x 2 verifiers (+ the aborted one)
    assert all(not v.records for v in engine.verifiers.values())


def test_non_qualifying_rejection_leaves_link_open(engine, rng):
    r = engine.execute_protocol("m", 32, rng=rng,
                                scenario=ThreatScenarioConfig(threat_type=ThreatType.MESSAGE_TAMPERING))
    assert r.response.response_action == "none" and r.response.verdict == "reject"
    engine.guard.check_open(LINK_SIGNER)


def test_weak_alert_watches_then_second_weak_alert_quarantines(clock):
    g = ChannelGuard(ResponsePolicy(watch_strikes=2), clock=clock)
    assert g.apply(LINK_SIGNER, WEAK, "TX-1")["new_state"] == "watch"
    g.check_open(LINK_SIGNER)  # watch still carries traffic
    t = g.apply(LINK_SIGNER, WEAK, "TX-2")
    assert t["new_state"] == "quarantined" and t["incident_id"]
    with pytest.raises(ChannelQuarantined):
        g.check_open(LINK_SIGNER)


def _weak(p):
    return ResponseDecision("reject", "watch", "weak", p, f"weak p={p}")


def test_fisher_combination_values():
    from src.quantum_engine.policy import fisher_combined_p
    assert fisher_combined_p([0.15, 0.15]) == pytest.approx(0.108, abs=1e-3)
    assert fisher_combined_p([0.02, 0.02]) == pytest.approx(0.0035, abs=2e-4)
    assert fisher_combined_p([0.3]) == pytest.approx(0.3)


def test_borderline_alerts_do_not_escalate_but_moderate_ones_do(clock):
    g = ChannelGuard(clock=clock)
    g.apply(LINK_SIGNER, _weak(0.15), "TX-1")
    assert g.apply(LINK_SIGNER, _weak(0.15), "TX-2")["new_state"] == "watch"   # combined ~0.11
    assert g.links[LINK_SIGNER].strikes == 2
    assert g.apply(LINK_SIGNER, _weak(0.15), "TX-3")["new_state"] == "quarantined"  # strike limit (3)
    h = ChannelGuard(clock=clock)
    h.apply(LINK_SIGNER, _weak(0.02), "TX-1")
    t = h.apply(LINK_SIGNER, _weak(0.02), "TX-2")                             # combined ~0.0035
    assert t["new_state"] == "quarantined" and h.links[LINK_SIGNER].combined_p < 0.01


def test_watch_expires_after_window(clock):
    g = ChannelGuard(ResponsePolicy(watch_window_s=60), clock=clock)
    g.apply(LINK_SIGNER, WEAK, "TX-1")
    clock.advance(61)
    assert g.state(LINK_SIGNER) == "open"
    assert g.apply(LINK_SIGNER, WEAK, "TX-2")["new_state"] == "watch"  # fresh window, not an escalation


def test_strong_alert_quarantines_immediately_and_blocks_all_links(clock):
    g = ChannelGuard(clock=clock)
    g.apply(LINK_FORWARD, STRONG, "TX-1")
    assert g.state(LINK_SIGNER) == "open"
    for link in (LINK_SIGNER, LINK_FORWARD):
        with pytest.raises(ChannelQuarantined):
            g.check_open(link)
    g.request_reset(actor="admin")
    g.check_open(LINK_SIGNER)
    g.check_open(LINK_FORWARD)


def test_probation_failure_requarantines(clock):
    g = ChannelGuard(clock=clock)
    g.apply(LINK_SIGNER, STRONG, "TX-1")
    g.request_reset(LINK_SIGNER, "admin", "investigated")
    assert g.state(LINK_SIGNER) == "reset_pending"
    assert g.apply(LINK_SIGNER, WEAK, "TX-2")["new_state"] == "quarantined"


def test_transitions_are_logged_with_actor_and_policy(clock):
    g = ChannelGuard(clock=clock)
    g.apply(LINK_SIGNER, STRONG, "TX-9")
    g.request_reset(LINK_SIGNER, "admin", "false positive check")
    last = g.transitions[-1]
    assert last["actor"] == "admin" and last["reason"] == "false positive check"
    assert last["old_state"] == "quarantined" and last["new_state"] == "reset_pending"
    assert all(t["policy_version"] == "hedwig-qcb/2" for t in g.transitions)


def test_link_state_survives_restart(tmp_path, clock):
    path = str(tmp_path / "state.db")
    g = ChannelGuard(store=Store(path), clock=clock)
    g.apply(LINK_SIGNER, STRONG, "TX-1")
    g2 = ChannelGuard(store=Store(path), clock=clock)
    with pytest.raises(ChannelQuarantined):
        g2.check_open(LINK_SIGNER)
    assert Store(path).transitions()[0]["new_state"] == "quarantined"


def test_replay_nonce_survives_restart(tmp_path, clock, rng):
    path = str(tmp_path / "state.db")
    eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0), clock=clock,
                           store=Store(path))
    pkg = eng.reveal(eng.distribute("alice", "pay 5", 32, rng))
    assert all(r.accepted for r in eng.deliver(pkg))
    eng2 = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0), clock=clock,
                            store=Store(path))
    for v in eng2.verifiers.values():
        assert v.replay_guard.is_consumed(pkg.context.nonce, "direct")


def test_weak_small_l_noise_does_not_lock_the_link(clock):
    """Honest noisy runs at L=16 may be rejected, but a single one only puts the link on WATCH."""
    rng = np.random.default_rng(5)
    quarantined_after_one = 0
    for _ in range(80):
        eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.03), clock=clock)
        r = eng.execute_protocol("m", 16, rng=rng)
        quarantined_after_one += r.enforcement["action"] == "link_quarantined"
    assert quarantined_after_one <= 2


# -------------------------------------------------------------- early abort
def test_full_intercept_aborts_early_and_is_not_revealed(engine):
    r = _intercept(engine, np.random.default_rng(3))
    ct = r.transcript.channel_test
    assert ct.alarm and ct.early_abort and ct.tokens_sent < ct.tokens_planned
    assert ct.p_value <= engine.params.strong_alpha
    assert r.transcript.results == [] and r.to_dict()["revealed"] is False


def test_honest_runs_send_the_whole_stream(engine, rng):
    for _ in range(5):
        ct = engine.execute_protocol("m", 32, rng=rng).transcript.channel_test
        assert not ct.early_abort and ct.tokens_sent == ct.tokens_planned


def test_watch_doubles_test_token_budget(engine, rng):
    base = engine.test_token_budget(32)
    engine.guard.apply(LINK_SIGNER, WEAK, "TX-1")
    assert engine.test_token_budget(32) == base * engine.params.watch_test_multiplier


# ------------------------------------------------------------------- router
def test_router_drops_quarantined_link(clock):
    router = SimulatedRouter()
    g = ChannelGuard(router=router, clock=clock)
    g.apply(LINK_SIGNER, STRONG, "TX-1")
    assert router.hops["alice->QR-1"].state == "down" and router.hops["bob->charlie"].state == "up"
    with pytest.raises(ChannelQuarantined):
        g.check_open(LINK_SIGNER)
    assert router.hops["alice->QR-1"].dropped == 1


def test_router_counts_tokens(engine, rng):
    engine.execute_protocol("m", 16, rng=rng)
    assert engine.router.hops["alice->QR-1"].tokens_carried > 0


def test_latency_is_measured(engine, rng):
    r = engine.execute_protocol("m", 16, rng=rng)
    assert r.latency["detection_us"] > 0 and r.latency["protocol_ms"] > 0
    assert r.latency["channel_observation_ms"] > 0
    assert engine.latency.to_dict()["detection_us"]["count"] == 1


# -------------------------------------------------------------------- audit
@pytest.fixture
def authority(tmp_path):
    return AuditAuthority(str(tmp_path / "k.pem"), pq=False)


@pytest.fixture
def cert(engine, rng, authority):
    tx = engine.execute_protocol("audited", 32, rng=rng).to_dict()
    ev = build_evidence(tx)
    return authority, authority.sign(build_record(tx, engine.params.to_dict(), evidence=ev), ev)


def test_audit_record_verifies(cert):
    authority, c = cert
    assert verify_certificate(c, authority.trusted_keys())
    rec = c["record"]
    assert rec["version"] == "hedwig-audit/2" and len(rec["evidence_digests"]["full_evidence_sha256"]) == 64
    assert set(rec["evidence_digests"]["elimination_sha3_256"]) == {"bob/direct", "charlie/direct"}
    assert rec["evidence_digests"]["symmetrisation_actions_sha3_256"]
    assert rec["message"]["plaintext_included"] is False
    assert rec["fidelity"]["status"].startswith("model-based") and "estimate" in rec["fidelity"]
    assert rec["channel_test"]["test_count"] >= 16 and "p_value" in rec["channel_test"]
    assert all("forgery_accept" in b["values"] for b in rec["bounds"]["per_verifier"].values())
    assert rec["assurance"]["level"] in ("ACCEPTED - DEMONSTRATION GRADE", "ACCEPTED - BOUNDS MEET TARGET")


@pytest.mark.parametrize("path,value", [
    (("outcome", "verdict"), "SOMETHING ELSE"), (("nonce",), "00"), (("outcome", "classification"), "X"),
    (("fidelity", "status"), "measured"),
])
def test_audit_record_fails_after_any_change(cert, path, value):
    authority, c = cert
    tampered = copy.deepcopy(c)
    target = tampered["record"]
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = value
    assert not verify_certificate(tampered, authority.trusted_keys())


def test_evidence_tampering_is_detected(cert):
    authority, c = cert
    tampered = copy.deepcopy(c)
    v = tampered["evidence"]["verifications"]["bob"]
    v["eliminated_states"][0] = ["|0⟩"] * len(v["eliminated_states"][0])
    rep = verify_certificate_report(tampered, authority.trusted_keys())
    assert rep["checks"]["all_signatures_valid"] and not rep["checks"]["evidence_digests_match"]
    assert not rep["valid"]


def test_audit_record_fails_under_other_key(cert, tmp_path):
    _, c = cert
    other = AuditAuthority(str(tmp_path / "other.pem"), pq=False)
    assert not verify_certificate(c, other.trusted_keys())
    assert not verify_certificate(c, other.public_key_pem)


def test_audit_key_persists(tmp_path):
    p = str(tmp_path / "k.pem")
    assert AuditAuthority(p, pq=False).public_key_pem == AuditAuthority(p, pq=False).public_key_pem


def test_old_records_verify_after_key_rotation(cert, tmp_path):
    authority, c = cert
    authority.rotate()
    reloaded = AuditAuthority(authority.key_path, pq=False)
    assert reloaded.public_key_pem != c["public_keys"][c["signatures"][0]["key_id"]]["public_key"]
    assert verify_certificate(c, reloaded.trusted_keys())


def test_ed25519_only_record_is_never_reported_post_quantum(cert):
    authority, c = cert
    rep = verify_certificate_report(c, authority.trusted_keys())
    assert rep["valid"] and not rep["checks"]["post_quantum_signed"]
    assert not verify_certificate_report(c, authority.trusted_keys(), require_pq=True)["valid"]


@pytest.mark.skipif(pq_provider() is None, reason="no ML-DSA provider installed (pip install dilithium-py)")
def test_hybrid_post_quantum_signature(engine, rng, tmp_path):
    auth = AuditAuthority(str(tmp_path / "pq.pem"), pq=True)
    tx = engine.execute_protocol("pq", 16, rng=rng).to_dict()
    c = auth.sign(build_record(tx, engine.params.to_dict()))
    assert {s["algorithm"] for s in c["signatures"]} == {"Ed25519", "ML-DSA-65"}
    assert verify_certificate_report(c, auth.trusted_keys(), require_pq=True)["valid"]
    stripped = copy.deepcopy(c)
    stripped["signatures"] = [s for s in stripped["signatures"] if s["algorithm"] == "Ed25519"]
    assert not verify_certificate(stripped, auth.trusted_keys())  # downgrade to classical-only is detected


def test_incident_is_signed_at_quarantine_time(clock, tmp_path):
    store = Store(str(tmp_path / "a.db"))
    auth = AuditAuthority(str(tmp_path / "k.pem"), pq=False, store=store)
    eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0), clock=clock,
                           store=store, audit=auth)
    r = _intercept(eng, np.random.default_rng(4))
    assert r.incident_cert is not None and r.latency["incident_signing_us"] > 0
    inc = r.incident_cert["record"]
    assert inc["kind"] == "incident" and inc["link"] == LINK_SIGNER
    assert inc["incident_id"] == r.enforcement["incident_id"]
    assert verify_certificate(r.incident_cert, auth.trusted_keys())
    assert store.get_audit(inc["incident_id"]) is not None
    assert r.audit_cert["record"]["response"]["response_action"] == "quarantine"


def test_every_transaction_gets_one_chained_record(clock, tmp_path):
    store = Store(str(tmp_path / "a.db"))
    auth = AuditAuthority(str(tmp_path / "k.pem"), pq=False, store=store)
    eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0), clock=clock,
                           store=store, audit=auth)
    rng = np.random.default_rng(6)
    ids = [eng.execute_protocol(f"m{i}", 16, rng=rng).transmission_id for i in range(4)]
    chain = store.audit_chain()
    assert [c["record"]["transmission_id"] for c in chain] == ids
    assert verify_chain(chain, auth.trusted_keys())["valid"]
    broken = chain[:1] + chain[2:]
    assert not verify_chain(broken, auth.trusted_keys())["valid"]
    # records remain verifiable after a "restart" (new authority object, same key file and database)
    auth2 = AuditAuthority(str(tmp_path / "k.pem"), pq=False, store=Store(str(tmp_path / "a.db")))
    assert verify_chain(Store(str(tmp_path / "a.db")).audit_chain(), auth2.trusted_keys())["valid"]
