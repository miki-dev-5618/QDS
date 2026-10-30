"""
Exact finite-sample decision rules for the elimination check (C1) and the
two-stage reserve design used for borderline evidence (C2).

Model (same assumptions as ``security.py``): a verifier checks n measured
copies; under the honest hypothesis the mismatch count is M ~ Bin(n, mu_h),
under the forger hypothesis M ~ Bin(n, p_f) with p_f the minimum per-copy
mismatch probability of the stated adversary. The probabilities below are
exact *within that i.i.d. model*; they are not a proof against coherent,
adaptive or loss-selecting adversaries.

Single-stage rule at n copies, risk budget (fr_target, fa_target):
  k_fr = min k with P_h(M > k)  <= fr_target    (honest reliability)
  k_fa = max k with P_f(M <= k) <= fa_target    (forgery resistance)
  feasible iff k_fr <= k_fa. Then
    direct    accept iff M <= k_fr   (strictest limit meeting reliability)
    forwarded accept iff M <= k_fa   (most permissive limit meeting forgery
                                      risk; k_fr <= k_fa keeps a transfer margin)
  infeasible (too little evidence): accept iff M <= max(k_fa, 0), decisive
  reject iff M > k_fr, and the counts in between are INCONCLUSIVE. Forgery
  risk stays capped wherever a capping limit exists; zero contradictions is
  always accepted, with the achieved (above-target) forgery risk reported.

Two-stage rule (n1 main copies, n2 precommitted reserve copies):
  stage 1:  M1 <= a1 accept;  M1 > r1 reject;  otherwise open the reserve
  stage 2:  accept iff M1 + M2 <= a2
  P(reject | honest)  = P_h(M1 > r1) + sum_{a1<m<=r1} P_h(M1=m) P_h(M2 > a2-m)
  P(accept | forger)  = P_f(M1 <= a1) + sum_{a1<m<=r1} P_f(M1=m) P_f(M2 <= a2-m)
  Both are the operating characteristics of the whole stopping rule, so
  looking at stage 1 first does not inflate either error. Among feasible
  designs the one opening the reserve least often under the honest model is
  chosen. Stage-2 p-values use the stagewise ordering (stage-1 rejections are
  more extreme than any stage-2 outcome), which is valid under the stopping.
"""
import math
from dataclasses import dataclass, asdict, replace
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple


@lru_cache(maxsize=4096)
def _dist(n: int, p: float) -> Tuple[Tuple[float, ...], Tuple[float, ...], Tuple[float, ...]]:
    """(pmf, cdf, sf) of Bin(n, p); sf[k] = P(X > k), summed from the tail to keep small values exact."""
    if n <= 0:
        return (1.0,), (1.0,), (0.0,)
    if p <= 0.0 or p >= 1.0:
        pmf = [0.0] * (n + 1)
        pmf[0 if p <= 0.0 else n] = 1.0
    else:  # log space: math.comb(n, i) overflows a float for large n
        lp, lq, lgn = math.log(p), math.log1p(-p), math.lgamma(n + 1)
        pmf = [math.exp(lgn - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
               for i in range(n + 1)]
    cdf, acc = [], 0.0
    for x in pmf:
        acc += x
        cdf.append(min(1.0, acc))
    sf, acc = [0.0] * (n + 1), 0.0
    for i in range(n, 0, -1):
        acc += pmf[i]
        sf[i - 1] = min(1.0, acc)
    return tuple(pmf), tuple(cdf), tuple(sf)


def _cdf(n: int, p: float, k: int) -> float:
    """P(X <= k)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return _dist(n, p)[1][k]


def _sf(n: int, p: float, k: int) -> float:
    """P(X > k)."""
    if k < 0:
        return 1.0
    if k >= n:
        return 0.0
    return _dist(n, p)[2][k]


def reliability_limit(n: int, mu_h: float, fr_target: float) -> int:
    """Smallest k with P_h(M > k) <= fr_target."""
    for k in range(0, n + 1):
        if _sf(n, mu_h, k) <= fr_target:
            return k
    return n


def forgery_cap_limit(n: int, p_f: float, fa_target: float) -> int:
    """Largest k with P_f(M <= k) <= fa_target (-1 if even zero contradictions exceeds the budget)."""
    best = -1
    for k in range(0, n + 1):
        if _cdf(n, p_f, k) <= fa_target:
            best = k
        else:
            break
    return best


@dataclass(frozen=True)
class EliminationRule:
    """A prespecified acceptance rule for one verification mode and sample size."""
    mode: str                 # "direct" | "forwarded"
    policy: str               # "exact" | "legacy"
    n1: int                   # main checked copies
    n2: int                   # reserve copies available (0 = single stage)
    a1: int                   # accept at stage 1 iff M1 <= a1
    r1: int                   # decisive reject at stage 1 iff M1 > r1 (a1 < M1 <= r1 is borderline)
    a2: Optional[int]         # stage-2 total limit (None: no reserve stage)
    mu_h: float
    p_f: float
    fr_target: float
    fa_target: float
    false_reject: float       # P(not accepted | honest), whole rule
    forgery_accept: float     # P(accepted | forger), whole rule
    p_borderline_honest: float  # P(a1 < M1 <= r1 | honest): reserve-opening / inconclusive rate
    p_borderline_forger: float
    sufficient: bool          # both targets met by this rule
    depth: int = 0            # forwarding depth this rule applies to (0 = received from the signer)
    max_depth: int = 1        # the session's maximum depth H

    @property
    def two_stage(self) -> bool:
        return self.a2 is not None

    def stage1(self, m1: int) -> str:
        if m1 <= self.a1:
            return "pass"
        if m1 > self.r1:
            return "fail"
        return "borderline"

    def stage2(self, m1: int, m2: int) -> str:
        assert self.a2 is not None
        return "pass" if m1 + m2 <= self.a2 else "fail"

    def p_value(self, m1: int, m2: Optional[int] = None) -> float:
        """Honest-hypothesis p-value of the observed outcome, valid under this stopping rule."""
        if m2 is None or self.a2 is None:
            return _sf(self.n1, self.mu_h, m1 - 1)              # P(M1 >= m1)
        total = m1 + m2
        p = _sf(self.n1, self.mu_h, self.r1)
        pmf1 = _dist(self.n1, self.mu_h)[0]
        for m in range(self.a1 + 1, self.r1 + 1):
            p += pmf1[m] * _sf(self.n2, self.mu_h, total - m - 1)
        return min(1.0, p)

    def describe(self) -> str:
        s = f"accept iff M1 <= {self.a1}"
        if self.r1 > self.a1:
            if self.two_stage:
                s += (f"; reject iff M1 > {self.r1}; {self.a1} < M1 <= {self.r1} opens the {self.n2}-copy "
                      f"reserve, then accept iff M1 + M2 <= {self.a2}")
            else:
                s += f"; reject iff M1 > {self.r1}; {self.a1} < M1 <= {self.r1} is INCONCLUSIVE"
        else:
            s += " (otherwise reject)"
        if self.max_depth > 1:
            s += f" [depth {self.depth} of H = {self.max_depth}]"
        return s

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("false_reject", "forgery_accept", "p_borderline_honest", "p_borderline_forger"):
            d[k] = float(f"{d[k]:.4e}")
        d["two_stage"] = self.two_stage
        d["rule"] = self.describe()
        return d


def _single(mode: str, policy: str, n: int, a: int, r: int, mu_h: float, p_f: float,
            fr_t: float, fa_t: float) -> EliminationRule:
    fr = _sf(n, mu_h, a)
    fa = _cdf(n, p_f, a)
    return EliminationRule(mode, policy, n, 0, a, r, None, mu_h, p_f, fr_t, fa_t, fr, fa,
                           _cdf(n, mu_h, r) - _cdf(n, mu_h, a), _cdf(n, p_f, r) - _cdf(n, p_f, a),
                           fr <= fr_t and fa <= fa_t)


def single_stage_rule(n: int, mu_h: float, p_f: float, fr_target: float, fa_target: float,
                      forwarded: bool = False) -> EliminationRule:
    mode = "forwarded" if forwarded else "direct"
    if n <= 0:
        return _single(mode, "exact", 0, -1, -1, mu_h, p_f, fr_target, fa_target)
    k_fr = reliability_limit(n, mu_h, fr_target)
    k_fa = forgery_cap_limit(n, p_f, fa_target)
    if k_fr <= k_fa:
        k = k_fa if forwarded else k_fr
        return _single(mode, "exact", n, k, k, mu_h, p_f, fr_target, fa_target)
    return _single(mode, "exact", n, max(k_fa, 0), k_fr, mu_h, p_f, fr_target, fa_target)


def _two_stage_errors(n1, n2, a1, r1, a2, mu_h, p_f) -> Tuple[float, float]:
    pmf_h, pmf_f = _dist(n1, mu_h)[0], _dist(n1, p_f)[0]
    fr = _sf(n1, mu_h, r1)
    fa = _cdf(n1, p_f, a1)
    for m in range(a1 + 1, r1 + 1):
        fr += pmf_h[m] * _sf(n2, mu_h, a2 - m)
        fa += pmf_f[m] * _cdf(n2, p_f, a2 - m)
    return min(1.0, fr), min(1.0, fa)


@lru_cache(maxsize=8192)
def two_stage_rule(n1: int, n2: int, mu_h: float, p_f: float, fr_target: float, fa_target: float,
                   forwarded: bool = False) -> Optional[EliminationRule]:
    """Feasible two-stage design opening the reserve least often under the honest model, or None."""
    if n1 <= 0 or n2 <= 0:
        return None
    mode = "forwarded" if forwarded else "direct"
    k_fr1 = reliability_limit(n1, mu_h, fr_target)
    k_fa1 = forgery_cap_limit(n1, p_f, fa_target)
    # Rejecting beyond this point no longer changes the honest error measurably.
    r_max = min(n1, reliability_limit(n1, mu_h, fr_target * 1e-6))
    best, best_key = None, None
    for a1 in range(-1, k_fa1 + 1):
        for r1 in range(max(a1 + 1, k_fr1), r_max + 1):
            a2_found = None
            if forwarded:   # most permissive total limit within the forgery budget
                for a2 in range(n1 + n2, a1, -1):
                    fr, fa = _two_stage_errors(n1, n2, a1, r1, a2, mu_h, p_f)
                    if fa <= fa_target:
                        a2_found = (a2, fr, fa) if fr <= fr_target else None
                        break
            else:           # strictest total limit meeting the reliability budget
                for a2 in range(a1 + 1, n1 + n2 + 1):
                    fr, fa = _two_stage_errors(n1, n2, a1, r1, a2, mu_h, p_f)
                    if fr <= fr_target:
                        a2_found = (a2, fr, fa) if fa <= fa_target else None
                        break
            if a2_found is None:
                continue
            a2, fr, fa = a2_found
            cost = _cdf(n1, mu_h, r1) - _cdf(n1, mu_h, a1)
            key = (round(cost, 12), fa if not forwarded else fr)
            if best_key is None or key < best_key:
                best_key = key
                best = EliminationRule(mode, "exact", n1, n2, a1, r1, a2, mu_h, p_f, fr_target, fa_target,
                                       fr, fa, cost, _cdf(n1, p_f, r1) - _cdf(n1, p_f, a1), True)
    return best


def exact_rule(n1: int, n2: int, mu_h: float, p_f: float, fr_target: float, fa_target: float,
               forwarded: bool = False) -> EliminationRule:
    """Single stage when it suffices; else the best feasible two-stage design; else a capped fallback."""
    single = single_stage_rule(n1, mu_h, p_f, fr_target, fa_target, forwarded)
    if single.sufficient or n2 <= 0 or single.r1 == single.a1:
        return single
    two = two_stage_rule(n1, n2, mu_h, p_f, fr_target, fa_target, forwarded)
    if two is not None:
        return two
    # Below target even with the reserve: keep stage 1 as in the single rule and pick the pooled
    # limit that meets the forgery budget if any does, else the one with the smallest worst-case
    # ratio to its target; report the achieved (above-target) errors.
    a1, r1 = single.a1, single.r1

    def key(a2):
        fr_, fa_ = _two_stage_errors(n1, n2, a1, r1, a2, mu_h, p_f)
        return (fa_ > fa_target, max(fr_ / fr_target, fa_ / fa_target))

    a2 = min(range(a1 + 1, n1 + n2 + 1), key=key)
    fr, fa = _two_stage_errors(n1, n2, a1, r1, a2, mu_h, p_f)
    return EliminationRule(single.mode, "exact", n1, n2, a1, r1, a2, mu_h, p_f, fr_target, fa_target, fr, fa,
                           single.p_borderline_honest, single.p_borderline_forger, False)


def depth_rule(n1: int, n2: int, mu_h: float, p_f: float, fr_target: float, fa_target: float,
               depth: int, max_depth: int) -> EliminationRule:
    """
    Exact rule at forwarding depth ``depth`` of a session with maximum depth H = ``max_depth``.

    Depth 0 uses the direct rule (k_fr, strictest limit meeting reliability) and depth H the
    forwarded rule (k_fa, most permissive limit meeting the forgery budget); H = 1 is exactly the
    original direct/forwarded pair. In between, limits are evenly spaced whole numbers in [k_fr, k_fa],
    non-decreasing in depth, so every level meets both risk targets whenever the endpoints do.
    Adjacent levels may share a limit at short sample sizes; no distinct thresholds are invented.
    When the evidence is too thin (inconclusive band, or a reserve fallback below target) the
    intermediate levels keep the direct rule: no transfer margin is granted that cannot be supported.
    Two-stage designs keep the direct stage-1 limits and widen only the pooled limit a2, clamped to
    the largest value still meeting the forgery budget.
    """
    h = max(1, int(max_depth))
    l = max(0, min(int(depth), h))
    if l == 0 or l == h:
        r = exact_rule(n1, n2, mu_h, p_f, fr_target, fa_target, forwarded=l > 0)
        return replace(r, depth=l, max_depth=h)
    d = exact_rule(n1, n2, mu_h, p_f, fr_target, fa_target, forwarded=False)
    f = exact_rule(n1, n2, mu_h, p_f, fr_target, fa_target, forwarded=True)
    rule = d
    if not d.two_stage and not f.two_stage and d.r1 == d.a1 and f.r1 == f.a1 and d.sufficient:
        a = d.a1 + (l * (f.a1 - d.a1)) // h
        rule = _single("forwarded", "exact", n1, a, a, mu_h, p_f, fr_target, fa_target)
    elif d.two_stage and f.two_stage and d.sufficient:
        target = d.a2 + (l * (f.a2 - d.a2)) // h
        a2, fr, fa = d.a2, d.false_reject, d.forgery_accept
        for cand in range(d.a2 + 1, target + 1):
            fr_c, fa_c = _two_stage_errors(n1, n2, d.a1, d.r1, cand, mu_h, p_f)
            if fa_c > fa_target:
                break
            a2, fr, fa = cand, fr_c, fa_c
        rule = replace(d, a2=a2, false_reject=fr, forgery_accept=fa,
                       sufficient=fr <= fr_target and fa <= fa_target)
    return replace(rule, mode="forwarded", depth=l, max_depth=h)


def legacy_rule(n: int, limit_rate: float, mu_h: float, p_f: float, fr_target: float, fa_target: float,
                forwarded: bool = False) -> EliminationRule:
    """The original fraction-based limit floor(s*n), with its exact operating characteristics."""
    k = int(math.floor(limit_rate * n + 1e-9)) if n > 0 else -1
    r = _single("forwarded" if forwarded else "direct", "legacy", max(n, 0), k, k, mu_h, p_f,
                fr_target, fa_target)
    return r


def min_sufficient_n(mu_h: float, p_f: float, fr_target: float, fa_target: float, n_max: int = 4096) -> int:
    """Smallest single-stage n meeting both targets (same n for both modes, since feasibility is k_fr <= k_fa)."""
    for n in range(1, n_max + 1):
        if reliability_limit(n, mu_h, fr_target) <= forgery_cap_limit(n, p_f, fa_target):
            return n
    return -1


# ----------------------------------------------------------------- C2 planning
@lru_cache(maxsize=1024)
def plan_reserve(n_expected: int, mu_h: float, p_f: float, fr_target: float, fa_target: float,
                 max_reserve: int) -> Tuple[int, bool]:
    """
    Smallest reserve (in copies per verifier) for which a two-stage design meets both targets in both
    modes at ``n_expected`` main copies. Returns (reserve, reaches_target). Zero when stage 1 alone
    suffices; ``max_reserve`` (best effort, reaches_target False) when nothing within the cap does.
    """
    if n_expected <= 0 or max_reserve <= 0:
        return 0, False
    if all(single_stage_rule(n_expected, mu_h, p_f, fr_target, fa_target, fw).sufficient for fw in (False, True)):
        return 0, True
    for r in range(1, max_reserve + 1):
        if all(two_stage_rule(n_expected, r, mu_h, p_f, fr_target, fa_target, fw) is not None
               for fw in (False, True)):
            return r, True
    return max_reserve, False


@lru_cache(maxsize=4096)
def channel_test_power(n: int, p0: float, alpha: float, q_attack: float) -> Tuple[int, float]:
    """(alarm threshold k, P(errors > k | QBER = q_attack)) for the exact Tier 1 test at n tokens."""
    k = reliability_limit(n, p0, alpha)
    return k, _sf(n, q_attack, k)


@lru_cache(maxsize=1024)
def plan_test_tokens(p0: float, alpha: float, q_attack: float, power_target: float,
                     n_min: int, n_max: int) -> Tuple[int, float, bool]:
    """Smallest n in [n_min, n_max] whose Tier 1 test reaches ``power_target`` against ``q_attack``."""
    for n in range(max(1, n_min), n_max + 1):
        _, power = channel_test_power(n, p0, alpha, q_attack)
        if power >= power_target:
            return n, power, True
    return n_max, channel_test_power(n_max, p0, alpha, q_attack)[1], False
