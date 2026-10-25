"""Issue 6: the displayed bound and the decision use the same threshold."""
import math

import pytest

from src.quantum_engine import SecurityParameters, VerifierNode, DistributionRecord, SignedContext, SignedPackage
from src.quantum_engine.binding import commitment, new_blinding
from src.quantum_engine.channel import binomial_upper_tail, critical_error_count, estimate_channel_qber

P = SecurityParameters()
LEGACY = SecurityParameters(threshold_policy="legacy")


def test_threshold_ordering():
    assert P.mu_honest < P.s_a < P.s_v < P.forger_min_mismatch


def _verifier_with_mismatches(n_copies: int, mismatches: int, clock):
    v = VerifierNode("bob", P, clock=clock)
    sig = [(0, 0)] * n_copies
    ctx = SignedContext.new("alice", ["bob", "charlie"], "m", timestamp=clock())
    r = new_blinding()
    elim = [['|0⟩'] if i < mismatches else ['|1⟩'] for i in range(n_copies)]  # '|0⟩' eliminated => mismatch
    v.receive_distribution(DistributionRecord(ctx.session_id, "alice", commitment(ctx, sig, r), elim,
                                              [["kept"]] * n_copies, estimate_channel_qber(16, 0, 0.02, 0.01), False))
    return v, SignedPackage(ctx, "m", sig, r)


@pytest.mark.parametrize("n", [16, 32, 64, 128])
@pytest.mark.parametrize("forwarded", [False, True])
def test_decision_boundary_matches_displayed_rule(n, forwarded, clock):
    limit = P.acceptance_limit(n, forwarded)
    mode = "forwarded" if forwarded else "direct"
    v, pkg = _verifier_with_mismatches(n, limit, clock)
    at = v.verify(pkg.copy(forwarded_by="bob" if forwarded else None), mode)
    assert at.accepted and at.bounds["acceptance_limit"] == limit
    v, pkg = _verifier_with_mismatches(n, limit + 1, clock)
    above = v.verify(pkg.copy(forwarded_by="bob" if forwarded else None), mode)
    assert not above.accepted and not above.elimination_pass


def test_legacy_bound_values_follow_their_formulas():
    n = 64
    P = LEGACY
    b = P.bounds(n, 0)
    assert b["acceptance_limit"] == math.floor(P.s_a * n)
    assert float(b["values"]["false_reject"]) == pytest.approx(math.exp(-2 * (P.s_a - P.mu_honest) ** 2 * n), rel=1e-3)
    assert float(b["values"]["forgery_accept"]) == pytest.approx(
        math.exp(-2 * (P.forger_min_mismatch - P.s_a) ** 2 * n), rel=1e-3)
    assert float(b["values"]["repudiation"]) == pytest.approx(
        min(1, 2 * math.exp(-((P.s_v - P.s_a) ** 2) * n / 2)), rel=1e-3)


@pytest.mark.parametrize("forwarded", [False, True])
def test_exact_bound_values_are_the_probabilities_of_the_applied_limit(forwarded):
    n = 64
    b = P.bounds(n, 0, forwarded)
    k = b["acceptance_limit"]
    assert float(b["values"]["false_reject"]) == pytest.approx(binomial_upper_tail(n, P.mu_honest, k + 1), rel=1e-3)
    assert float(b["values"]["forgery_accept"]) == pytest.approx(
        1 - binomial_upper_tail(n, P.forger_min_mismatch, k + 1), rel=1e-3)


def test_legacy_small_signatures_do_not_claim_target_security():
    for n in (16, 32, 64, 128):
        b = LEGACY.bounds(n, 0)
        assert not b["meets_target"] and b["n_required_for_target"] > n
    assert LEGACY.bounds(LEGACY.bounds(16, 0)["n_required_for_target"], 0)["meets_target"]


def test_exact_small_signatures_do_not_claim_target_security():
    n_req = P.n_required()
    for n in (16, 32, n_req - 1):
        b = P.bounds(n, 0)
        assert not b["meets_target"] and b["evidence_status"] == "below_target" and b["n_required_for_target"] > n
    for n in (n_req, 128, 256):
        assert P.bounds(n, 0)["meets_target"] and P.bounds(n, 0, True)["meets_target"]


@pytest.mark.parametrize("n", [16, 32, 64, 200])
def test_channel_alarm_threshold_controls_false_alarm(n):
    k = critical_error_count(n, 0.02, 0.01)
    assert binomial_upper_tail(n, 0.02, k + 1) <= 0.01
    if k > 0:
        assert binomial_upper_tail(n, 0.02, k) > 0.01
    assert not estimate_channel_qber(n, k, 0.02, 0.01).alarm
    assert estimate_channel_qber(n, k + 1, 0.02, 0.01).alarm
