"""C1 (exact finite-sample thresholds) and C2 (adaptive evidence allocation, bounded reserve)."""
import math
from itertools import product

import numpy as np
import pytest

from src.quantum_engine import (
    ChannelModel, DistributionRecord, SecurityParameters, SignedContext, SignedPackage, TeleportationQDS,
    ThreatClassification, ThreatScenarioConfig, ThreatType, VerifierNode, decide, ResponsePolicy,
    QDSDetectionEngine,
)
from src.quantum_engine.binding import ReserveOpening, commitment, new_blinding, reserve_commitment
from src.quantum_engine.channel import estimate_channel_qber
from src.quantum_engine.thresholds import (
    exact_rule, forgery_cap_limit, plan_test_tokens, reliability_limit, single_stage_rule, two_stage_rule,
    channel_test_power,
)

P = SecurityParameters()
MU, PF, FR, FA = P.mu_honest, P.forger_min_mismatch, P.fr_target, P.fa_target


def _pmf(n, p, k):
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


# ------------------------------------------------------------------ C1: single stage
@pytest.mark.parametrize("n", [57, 64, 96, 128, 200])
def test_sufficient_n_meets_both_targets_in_both_modes(n):
    d, f = (single_stage_rule(n, MU, PF, FR, FA, fw) for fw in (False, True))
    assert d.sufficient and f.sufficient
    assert d.false_reject <= FR and d.forgery_accept <= FA and f.false_reject <= FR and f.forgery_accept <= FA
    assert d.a1 <= f.a1                       # forwarded never stricter than direct (transfer margin)
    assert d.r1 == d.a1 and f.r1 == f.a1      # no inconclusive band when the evidence suffices


@pytest.mark.parametrize("n", [8, 16, 24, 32, 48])
def test_small_n_is_reported_below_target_with_an_inconclusive_band(n):
    r = single_stage_rule(n, MU, PF, FR, FA)
    assert not r.sufficient and r.r1 > r.a1 >= 0
    assert r.r1 == reliability_limit(n, MU, FR)
    cap = forgery_cap_limit(n, PF, FA)
    assert r.a1 == max(cap, 0)
    assert r.stage1(r.a1) == "pass" and r.stage1(r.a1 + 1) == "borderline" and r.stage1(r.r1 + 1) == "fail"


def test_minimum_sufficient_n_is_tight():
    n = P.n_required()
    assert single_stage_rule(n, MU, PF, FR, FA).sufficient
    assert not single_stage_rule(n - 1, MU, PF, FR, FA).sufficient


def test_legacy_policy_reproduces_the_original_limit():
    legacy = SecurityParameters(threshold_policy="legacy")
    for n in (16, 32, 64, 128):
        assert legacy.acceptance_limit(n) == math.floor(legacy.s_a * n + 1e-9)
        assert legacy.acceptance_limit(n, True) == math.floor(legacy.s_v * n + 1e-9)


# ------------------------------------------------------------------- C1: two stage
def _enumerate(rule, p):
    """Brute-force P(accept) of a two-stage rule under per-copy mismatch probability p."""
    acc = 0.0
    for m1 in range(rule.n1 + 1):
        w1 = _pmf(rule.n1, p, m1)
        o = rule.stage1(m1)
        if o == "pass":
            acc += w1
        elif o == "borderline":
            acc += w1 * sum(_pmf(rule.n2, p, m2) for m2 in range(rule.n2 + 1) if rule.stage2(m1, m2) == "pass")
    return acc


@pytest.mark.parametrize("n1,n2,fw", [(28, 28, False), (32, 24, True), (36, 32, False), (20, 20, False)])
def test_two_stage_errors_match_brute_force(n1, n2, fw):
    rule = exact_rule(n1, n2, MU, PF, FR, FA, fw)
    assert rule.two_stage
    assert 1 - _enumerate(rule, MU) == pytest.approx(rule.false_reject, rel=1e-9, abs=1e-15)
    assert _enumerate(rule, PF) == pytest.approx(rule.forgery_accept, rel=1e-9, abs=1e-15)


def test_reserve_turns_an_infeasible_sample_into_a_feasible_rule():
    assert not single_stage_rule(30, MU, PF, FR, FA).sufficient
    rule = two_stage_rule(30, 30, MU, PF, FR, FA)
    assert rule is not None and rule.sufficient and rule.false_reject <= FR and rule.forgery_accept <= FA


def test_stagewise_p_value_is_valid_under_the_stopping_rule():
    """P_h(p <= a) <= a for every a: looking at stage 1 first does not inflate the evidence."""
    rule = exact_rule(30, 30, MU, PF, FR, FA)
    outcomes = []
    for m1 in range(rule.n1 + 1):
        w1 = _pmf(rule.n1, MU, m1)
        if rule.stage1(m1) != "borderline":
            outcomes.append((rule.p_value(m1), w1))
        else:
            outcomes += [(rule.p_value(m1, m2), w1 * _pmf(rule.n2, MU, m2)) for m2 in range(rule.n2 + 1)]
    for a in (1e-4, 1e-3, 1e-2, 0.05, 0.2):
        assert sum(w for p, w in outcomes if p <= a) <= a + 1e-12


# ------------------------------------------------------------- C2: allocation plans
def test_test_budget_reaches_planned_decisive_power():
    plan = P.test_token_plan(64, suspicious=False)
    n = plan["test_tokens"]
    k, power = channel_test_power(n, P.honest_qber, P.strong_alpha, P.test_attack_qber)
    assert power >= P.test_power_target and plan["reached"]
    _, below = channel_test_power(n - 1, P.honest_qber, P.strong_alpha, P.test_attack_qber)
    assert below < P.test_power_target or n == P.min_test_tokens


def test_test_budget_does_not_grow_with_signature_length_and_inflates_for_loss():
    assert P.test_token_plan(16, False)["test_tokens"] == P.test_token_plan(256, False)["test_tokens"]
    lossy = P.test_token_plan(64, False, observed_loss=0.2)
    assert lossy["test_tokens"] == math.ceil(lossy["measured_tokens_needed"] / 0.8)


def test_reserve_is_length_aware():
    assert P.reserve_plan(128)["reserve_bits"] == 0
    assert P.reserve_plan(64)["reserve_bits"] == 0
    r32 = P.reserve_plan(32)
    assert 0 < r32["reserve_bits"] <= 32 and r32["reaches_target"]
    r16 = P.reserve_plan(16)
    assert r16["reserve_bits"] == 16 and not r16["reaches_target"]   # capped, reported honestly
    assert SecurityParameters(reserve_policy="off").reserve_plan(16)["reserve_bits"] == 0


def test_allocation_never_reads_the_injected_scenario():
    eng = TeleportationQDS(backend="statevector")
    before = eng.allocation_plan(32)
    eng.execute_protocol("m", 32, rng=np.random.default_rng(5),
                         scenario=ThreatScenarioConfig(threat_type=ThreatType.MESSAGE_TAMPERING))
    # A classical rejection leaves the link OPEN and loss at zero, so the plan is unchanged.
    assert eng.allocation_plan(32) == before


# ------------------------------------------------------- verifier: inconclusive path
def _verifier(n, mismatches, clock, reserve=None, reserve_mismatches=0):
    v = VerifierNode("bob", P, clock=clock)
    sig = [(0, 0)] * n
    ctx = SignedContext.new("alice", ["bob", "charlie"], "m", timestamp=clock())
    r = new_blinding()
    elim = [['|0⟩'] if i < mismatches else ['|1⟩'] for i in range(n)]
    rsv_elim, rsv_commit, opening = [], None, None
    if reserve:
        rsv = [(0, 0)] * reserve
        rb = new_blinding()
        rsv_elim = [['|0⟩'] if i < reserve_mismatches else ['|1⟩'] for i in range(reserve)]
        rsv_commit = reserve_commitment(ctx, rsv, rb)
        opening = ReserveOpening(tuple(rsv), rb)
    v.receive_distribution(DistributionRecord(ctx.session_id, "alice", commitment(ctx, sig, r), elim,
                                              [["kept"]] * n, estimate_channel_qber(16, 0, 0.02, 0.01), False,
                                              reserve_eliminated=rsv_elim, reserve_commitment=rsv_commit))
    return v, SignedPackage(ctx, "m", sig, r), opening


def test_borderline_without_reserve_is_inconclusive_and_never_quarantines(clock):
    v, pkg, _ = _verifier(16, 1, clock)
    res = v.verify(pkg)
    assert not res.accepted and res.elimination_outcome == "inconclusive" and res.evidence_status == "below_target"
    report = QDSDetectionEngine(P).classify([res], estimate_channel_qber(34, 0, 0.02, 0.01))
    assert report.classification == ThreatClassification.INCONCLUSIVE_EVIDENCE
    d = decide(report, ResponsePolicy())
    assert d.verdict == "reject" and d.response_action == "none"


def test_reserve_resolves_borderline_once(clock):
    v, pkg, opening = _verifier(30, 1, clock, reserve=30, reserve_mismatches=0)
    first = v.verify(pkg)
    assert first.reserve_requested and first.elimination_outcome == "inconclusive"
    second = v.verify(pkg.copy(reserve=opening))
    assert second.decision_stage == 2 and second.accepted and second.reserve_binding_ok
    third = v.verify(pkg.copy(reserve=opening))   # bounded: the reserve is not evaluated again
    assert third.decision_stage == 1 and not third.accepted


def test_forged_reserve_opening_fails_binding(clock):
    v, pkg, opening = _verifier(30, 1, clock, reserve=30)
    fake = ReserveOpening(tuple((1, 1) for _ in opening.states), opening.blinding)
    res = v.verify(pkg.copy(reserve=fake))
    assert not res.accepted and res.reserve_binding_ok is False and not res.binding_pass


def test_reserve_is_not_spent_on_a_package_failing_binding(clock):
    v, pkg, opening = _verifier(30, 1, clock, reserve=30)
    bad = v.verify(pkg.copy(message="tampered", reserve=opening))
    assert not bad.accepted and bad.decision_stage == 1
    assert v.verify(pkg.copy(reserve=opening)).accepted


# ----------------------------------------------------------------- protocol level
def test_signer_opens_reserve_only_for_her_own_package():
    eng = TeleportationQDS(backend="statevector")
    session = eng.distribute("alice", "m", 32, np.random.default_rng(1))
    pkg = eng.reveal(session)
    assert session.reserve and eng.open_reserve(session, pkg) is not None
    assert eng.open_reserve(session, pkg.copy(message="other")) is None
    forged = pkg.copy(revealed_signature=[(1 - b, ba) for b, ba in pkg.revealed_signature])
    assert eng.open_reserve(session, forged) is None


def test_long_signatures_carry_no_reserve():
    eng = TeleportationQDS(backend="statevector")
    session = eng.distribute("alice", "m", 64, np.random.default_rng(2))
    assert session.reserve == [] and session.allocation["reserve"]["reserve_bits"] == 0
    assert all(not v.records[session.context.session_id].reserve_eliminated for v in eng.verifiers.values())


def _rates(threat, n_bits, trials, seed, params=None):
    rng = np.random.default_rng(seed)
    acc = det = 0
    for _ in range(trials):
        eng = TeleportationQDS(params=params, backend="statevector", channel=ChannelModel(depolarizing=0.03))
        r = eng.execute_protocol("m", n_bits, rng=rng, scenario=ThreatScenarioConfig(threat_type=threat))
        acc += bool(r.transcript.results) and all(v.accepted for v in r.transcript.results)
        det += r.threat_report.is_threat_detected
    return acc / trials, det / trials


def test_honest_l32_acceptance_with_reserve_on_a_noisy_channel():
    acc, _ = _rates(ThreatType.AUTHENTIC, 32, 40, seed=31)
    assert acc >= 0.9


@pytest.mark.parametrize("threat", [ThreatType.EVE_FORGERY, ThreatType.DISHONEST_BOB, ThreatType.REPUDIATION])
def test_attacks_still_rejected_at_short_lengths(threat):
    acc, det = _rates(threat, 32, 30, seed=32)
    assert acc == 0.0 and det >= 0.9
