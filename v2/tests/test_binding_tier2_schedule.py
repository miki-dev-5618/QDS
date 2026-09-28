"""V2.2: hardened binding, Tier 2 attribution, policy decisions, and basis schedules."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from src.quantum_engine import (
    ChannelModel, QDSDetectionEngine, ResponsePolicy, SecurityParameters, SignedContext, TeleportationQDS,
    ThreatClassification, decide, estimate_channel_qber, tier_two,
)
from src.quantum_engine.binding import commitment, message_digest
from src.quantum_engine.canonical import canonical_json
from src.quantum_engine.channel import binomial_upper_tail, chernoff_kl_tail_bound, critical_error_count
from src.quantum_engine.schedule import KeyedSchedule, PublicHashSchedule
from src.quantum_engine.teleportation import StatevectorTeleportationBackend, TeleportJob


# ------------------------------------------------------------------ binding
def _pkg(engine, rng, msg="transfer 10"):
    return engine.reveal(engine.distribute("alice", msg, 32, rng))


@pytest.mark.parametrize("field,value", [
    ("sender", "mallory"), ("verifiers", ["bob"]), ("nonce", "11" * 16), ("timestamp", 1.0),
    ("digest_alg", "sha3-512"), ("version", "HEDWIG-QDS-v1"),
])
def test_any_context_change_is_rejected_without_labels(engine, rng, field, value):
    pkg = _pkg(engine, rng)
    bad = pkg.copy()
    setattr(bad.context, field, value)
    results = engine.deliver(bad)
    assert not any(r.accepted for r in results)
    assert all(not r.commitment_matches or not r.sender_matches or not r.fresh or not r.addressed_to_verifier
               for r in results)


def test_signature_cannot_be_transplanted_to_another_session(engine, rng):
    a, b = _pkg(engine, rng, "pay A"), _pkg(engine, rng, "pay B")
    moved = b.copy(revealed_signature=a.revealed_signature, blinding=a.blinding)
    assert not any(r.accepted for r in engine.deliver(moved))
    assert all(r.accepted for r in engine.deliver(b))


def test_sha3_512_digest_option(clock, rng):
    eng = TeleportationQDS(SecurityParameters(digest_alg="sha3-512"), backend="statevector",
                           channel=ChannelModel(depolarizing=0.0), clock=clock)
    pkg = _pkg(eng, rng, "hello")
    assert pkg.context.digest_alg == "sha3-512" and len(pkg.context.message_digest) == 128
    assert all(r.accepted for r in eng.deliver(pkg))
    assert not any(r.accepted for r in eng.deliver(pkg.copy(message="hellp")))


def test_message_digest_is_domain_separated_and_not_normalised():
    import hashlib
    assert message_digest("x") != hashlib.sha256(b"x").hexdigest()
    assert message_digest("café") != message_digest("café")  # NFC vs NFD are different messages


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"x": math.nan})


def test_commitment_rejects_malformed_blinding(engine, rng):
    pkg = _pkg(engine, rng)
    results = engine.deliver(pkg.copy(blinding="not-hex"))
    assert not any(r.accepted for r in results) and not any(r.commitment_matches for r in results)


# --------------------------------------------------------------- statistics
def test_chernoff_kl_bound_dominates_exact_tail():
    for n, p in [(16, 0.02), (64, 0.02), (128, 0.05)]:
        k = critical_error_count(n, p, 0.01)
        assert chernoff_kl_tail_bound(n, p, k + 1) >= binomial_upper_tail(n, p, k + 1)


def test_channel_test_reports_p_value_and_early_abort_fields():
    ct = estimate_channel_qber(10, 6, 0.02, 0.01, planned_count=32, tokens_sent=40, tokens_planned=96)
    assert ct.early_abort and ct.alarm and ct.p_value == pytest.approx(binomial_upper_tail(32, 0.02, 6))
    d = ct.to_dict()
    assert d["planned_test_count"] == 32 and d["exact_false_alarm_level"] <= 0.01


def _obs(n, m, verifier="bob"):
    return SimpleNamespace(verifier=verifier, mode="direct", record_found=True, n_checked=n, mismatches=m)


def test_tier2_attributes_excess_contradictions_to_the_signature():
    ct = estimate_channel_qber(32, 0, 0.02, 0.01)
    t2 = tier_two([_obs(32, 5), _obs(32, 4, "charlie")], ct)
    assert t2.attribution == "signature_inconsistency" and t2.p_excess <= 0.05


def test_tier2_attributes_proportional_disturbance_to_the_channel():
    ct = estimate_channel_qber(16, 2, 0.02, 0.01)  # below the Tier 1 alarm, above baseline
    t2 = tier_two([_obs(16, 2), _obs(16, 2, "charlie")], ct)
    assert not ct.alarm and t2.attribution == "channel_disturbance"


def test_tier2_is_undetermined_for_a_single_small_l_mismatch():
    ct = estimate_channel_qber(16, 0, 0.02, 0.01)
    t2 = tier_two([_obs(16, 1), _obs(16, 0, "charlie")], ct)
    assert t2.attribution == "undetermined" and t2.kl_nats >= 0


def test_tier2_share_matches_the_thinning_model():
    ct = estimate_channel_qber(16, 0, 0.02, 0.01)
    t2 = tier_two([_obs(32, 1)], ct)
    assert t2.pi_contradiction_share == pytest.approx(16 / (16 + 16))


def _result(n, m, verifier="bob"):
    return SimpleNamespace(verifier=verifier, mode="direct", forwarded_by=None, record_found=True,
                           sender_matches=True, fresh=True, freshness_reason="ok", n_checked=n, mismatches=m,
                           acceptance_limit=0, accepted=m == 0, binding_pass=True, elimination_pass=m == 0,
                           digest_matches=True, commitment_matches=True)


def test_detector_labels_small_l_single_mismatch_undetermined_and_policy_watches():
    ct = estimate_channel_qber(16, 0, 0.02, 0.01)
    report = QDSDetectionEngine().classify([_result(16, 1), _result(16, 0, "charlie")], ct)
    assert report.classification == ThreatClassification.UNDETERMINED_DISTURBANCE
    assert report.is_threat_detected
    d = decide(report, ResponsePolicy())
    assert d.verdict == "reject" and d.response_action == "watch"


def test_strong_evidence_quarantines():
    ct = estimate_channel_qber(64, 0, 0.02, 0.01)
    report = QDSDetectionEngine().classify([_result(64, 10), _result(64, 9, "charlie")], ct)
    assert report.classification == ThreatClassification.REPUDIATION_ATTEMPT
    assert decide(report, ResponsePolicy()).response_action == "quarantine"


# ---------------------------------------------------------------- schedules
def test_keyed_schedule_is_reproducible_with_the_key_and_differs_without_it():
    ctx = SignedContext.new("alice", ["bob", "charlie"], "m")
    rng = np.random.default_rng(0)
    k1 = KeyedSchedule({"bob": b"k" * 32})
    k2 = KeyedSchedule({"bob": b"k" * 32})
    k3 = KeyedSchedule({"bob": b"j" * 32})
    seq = lambda s: [s.basis(ctx, "bob", i, 0, rng) for i in range(64)]
    assert seq(k1) == seq(k2) and seq(k1) != seq(k3)
    assert 16 < sum(seq(k1)) < 48


def test_public_schedule_is_computable_from_the_context_alone():
    ctx = SignedContext.new("alice", ["bob", "charlie"], "m")
    rng = np.random.default_rng(0)
    a = [PublicHashSchedule().basis(ctx, "bob", i, 0, rng) for i in range(32)]
    b = [PublicHashSchedule().basis(ctx, "bob", i, 0, np.random.default_rng(9)) for i in range(32)]
    assert a == b


@pytest.mark.parametrize("basis", [0, 1])
def test_eve_measuring_in_the_verifier_basis_learns_the_outcome(basis):
    """Basis for the schedule experiment: outcome = eve_outcome XOR (m2 if Z else m1)."""
    rng = np.random.default_rng(1)
    backend = StatevectorTeleportationBackend()
    for _ in range(40):
        bit, prep = int(rng.integers(0, 2)), int(rng.integers(0, 2))
        out = backend.run([TeleportJob(bit, prep, basis, eve_basis=basis)], rng)[0]
        inferred = out.eve_outcome ^ (out.m2 if basis == 0 else out.m1)
        assert inferred == out.outcome
