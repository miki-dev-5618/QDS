"""
One threat model, one set of thresholds, and the probabilities that follow from them.

Per *measured copy* a verifier records one eliminated state. A copy is a
"mismatch" when the revealed state equals the eliminated state.

Model parameters
  e0     honest channel QBER assumption (channel test enforces it statistically)
  mu_h   = e0 / 2   honest per-copy mismatch probability (only matched-basis
                    measurements can eliminate the true state, and only via error)
  p_min  minimum per-copy mismatch probability of a forger who lacks the
         signer's states:
           - external forger guessing uniformly:                    1/4
           - dishonest verifier holding one copy of the same token: >= 1/6
             (Bob excludes his own eliminated state and guesses among the
             remaining three; Charlie's copy eliminates T-perp w.p. 1/2 and each
             other-basis state w.p. 1/4, giving 1/6 or 1/4 depending on which
             state Bob eliminated.)
  gap    = p_min - mu_h, split in thirds:
  s_a    = mu_h + gap/3     legacy acceptance rate for a directly received signature
  s_v    = mu_h + 2*gap/3   legacy acceptance rate for a forwarded signature (s_a < s_v)

Decision rule (``threshold_policy``; the displayed probabilities always refer to
the rule actually applied):
  "exact"  (default) integer limits chosen from the exact Bin(n, mu_h) and
           Bin(n, p_min) distributions at the observed n against the risk
           budget (fr_target, fa_target), with an INCONCLUSIVE band and an
           optional precommitted reserve stage when n is too small
           (see ``thresholds.py``).
  "legacy" accept iff mismatches <= floor(s * n), s = s_a (direct) or s_v
           (forwarded); kept as the reproducible baseline.

Hoeffding bounds (shown for reference next to the exact values; assume per-copy
outcomes independent, per-copy mismatch probability <= mu_h for honest runs and
>= p_min for forgers; symmetrisation assigns each copy independently and
uniformly to a verifier):
  P(false reject)      <= exp(-2 (s - mu_h)^2 n)
  P(forgery accepted)  <= exp(-2 (p_min - s)^2 n)
  P(repudiation)       <= 2 exp(-(s_v - s_a)^2 n / 2)
These are illustrative finite-sample statements under the stated assumptions,
not a composable security proof against general (coherent) attacks.
"""
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .channel import binomial_upper_tail
from .thresholds import EliminationRule, exact_rule, legacy_rule, min_sufficient_n, plan_reserve, plan_test_tokens

ASSUMPTIONS: List[str] = [
    "Per-copy measurement outcomes are independent.",
    "Honest per-copy mismatch probability <= e0/2 (e0 enforced by the channel test at level alpha).",
    "A forger without the signer's states mismatches each copy with probability >= p_min "
    "(1/4 for an outside guesser, >= 1/6 for a dishonest verifier holding one copy); "
    "coherent/collective attacks are not covered.",
    "Keep-or-forward assigns every copy to Bob or Charlie independently and uniformly.",
    "Exact values are binomial probabilities within this i.i.d. model; Hoeffding values are looser "
    "reference bounds. Neither is a composable security proof.",
    "Repudiation (Bob accepts, Charlie rejects) involves correlated counts under symmetrisation and is "
    "shown only as the Hoeffding reference, not as an exact probability.",
]


def _hoeffding(d: float, n: int) -> float:
    if n <= 0 or d <= 0:
        return 1.0
    return math.exp(-2.0 * d * d * n)


def _n_required(d: float, target: float, factor: float = 1.0) -> int:
    """Smallest n with factor * exp(-2 d^2 n) <= target."""
    if d <= 0:
        return -1
    return int(math.ceil(math.log(factor / target) / (2.0 * d * d)))


def _env_early_abort() -> bool:
    """EARLY_ABORT=on|off (default on). Ablation switch for the sequential early abort."""
    v = os.environ.get("EARLY_ABORT", "on").strip().lower()
    if v not in ("on", "off"):
        raise ValueError(f"EARLY_ABORT must be 'on' or 'off', got {v!r}")
    return v == "on"


def _env_detection_tiers() -> int:
    """DETECTION_TIERS=1|2 (default 2). Ablation switch: 1 disables Tier 2 attribution."""
    v = os.environ.get("DETECTION_TIERS", "2").strip()
    if v not in ("1", "2"):
        raise ValueError(f"DETECTION_TIERS must be 1 or 2, got {v!r}")
    return int(v)


@dataclass(frozen=True)
class SecurityParameters:
    honest_qber: float = 0.02
    forger_min_mismatch: float = 1.0 / 6.0
    false_alarm_alpha: float = 0.01
    freshness_window_s: float = 120.0
    target_failure: float = 1e-6          # legacy (Hoeffding) target
    min_test_tokens: int = 16
    digest_alg: str = "sha256"            # or "sha3-512"
    strong_alpha: float = 1e-3            # evidence level for immediate quarantine / early abort
    tier2_alpha: float = 0.05             # excess-mismatch test (signature inconsistency)
    tier2_channel_beta: float = 0.10      # channel-elevation level for Tier 2 attribution
    abort_chunks: int = 4                 # stream blocks between early-abort checks
    watch_test_multiplier: int = 2        # legacy test allocation while a link is on WATCH
    min_surviving_ratio: float = 0.6      # abort with INSUFFICIENT_TOKENS if surviving < min_surviving_ratio * planned
    early_abort: bool = field(default_factory=_env_early_abort)          # False: always send the whole stream
    detection_tiers: int = field(default_factory=_env_detection_tiers)   # 1: Tier 1 only (no Tier 2 attribution)

    def __post_init__(self):
        if self.detection_tiers not in (1, 2):
            raise ValueError(f"detection_tiers must be 1 or 2, got {self.detection_tiers}")
    # C1: exact finite-sample elimination thresholds
    threshold_policy: str = "exact"       # "exact" | "legacy" (floor(s * n), the original rule)
    fr_target: float = 1e-2               # max P(honest signature not accepted) per verifier
    fa_target: float = 1e-2               # max P(forger accepted) per verifier, forger at p_min
    # C2: evidence allocation
    allocation_policy: str = "power"      # "power" | "legacy" (max(min, L), x watch_test_multiplier)
    test_power_target: float = 0.95       # Tier 1 decisive-alarm power on an OPEN link ...
    test_attack_qber: float = 0.25        # ... against this QBER (full intercept-resend)
    test_power_target_watch: float = 0.95  # on WATCH / probation ...
    test_attack_qber_watch: float = 0.125  # ... against a half-rate intercept-resend
    max_test_tokens: int = 512
    reserve_policy: str = "auto"          # "auto" (L-aware precommitted reserve) | "off"
    max_reserve_ratio: float = 1.0        # reserve positions <= ratio * L
    max_reserve_openings: int = 1         # per session and verifier channel (bounded borderline retry)

    def elimination_p_value(self, n: int, mismatches: int) -> float:
        """P(X >= mismatches) for X ~ Bin(n, mu_h): how surprising the count is for an honest run."""
        if n <= 0:
            return 1.0
        return binomial_upper_tail(n, self.mu_honest, mismatches)

    @property
    def mu_honest(self) -> float:
        return self.honest_qber / 2.0

    @property
    def gap(self) -> float:
        return self.forger_min_mismatch - self.mu_honest

    @property
    def s_a(self) -> float:
        return self.mu_honest + self.gap / 3.0

    @property
    def s_v(self) -> float:
        return self.mu_honest + 2.0 * self.gap / 3.0

    def limit_rate(self, forwarded: bool) -> float:
        return self.s_v if forwarded else self.s_a

    def elimination_rule(self, n: int, forwarded: bool = False, n_reserve: int = 0) -> EliminationRule:
        """The prespecified acceptance rule for n main copies (and n_reserve reserve copies, if any)."""
        if self.threshold_policy == "legacy":
            return legacy_rule(n, self.limit_rate(forwarded), self.mu_honest, self.forger_min_mismatch,
                               self.fr_target, self.fa_target, forwarded)
        return exact_rule(n, n_reserve, self.mu_honest, self.forger_min_mismatch, self.fr_target,
                          self.fa_target, forwarded)

    def acceptance_limit(self, n: int, forwarded: bool = False) -> int:
        """Maximum number of mismatches accepted at stage 1 out of n checked copies."""
        return self.elimination_rule(n, forwarded).a1

    def n_required(self) -> int:
        """Smallest checked-copy count for which a single-stage exact rule meets both risk targets."""
        return min_sufficient_n(self.mu_honest, self.forger_min_mismatch, self.fr_target, self.fa_target)

    # -------------------------------------------------------------- C2 planning
    def test_token_plan(self, n_bits: int, suspicious: bool, observed_loss: float = 0.0) -> Dict[str, Any]:
        """Tier 1 test-token budget for a session and the reason for it (observable inputs only)."""
        if self.allocation_policy == "legacy":
            n = max(self.min_test_tokens, n_bits) * (self.watch_test_multiplier if suspicious else 1)
            return {"policy": "legacy", "test_tokens": n, "suspicious": suspicious,
                    "reason": "max(min_test_tokens, L)" + (" x watch multiplier" if suspicious else "")}
        target = self.test_power_target_watch if suspicious else self.test_power_target
        q = self.test_attack_qber_watch if suspicious else self.test_attack_qber
        # Power is planned at the decisive (quarantine / early-abort) level, so a detected attack of the
        # target strength carries quarantine-grade evidence; the session alarm at alpha is then stronger still.
        n_meas, power, reached = plan_test_tokens(self.honest_qber, self.strong_alpha, q, target,
                                                  self.min_test_tokens, self.max_test_tokens)
        loss = min(max(observed_loss, 0.0), 0.5)
        n = min(self.max_test_tokens, int(math.ceil(n_meas / (1.0 - loss))))
        reason = f"smallest n with P(decisive alarm | QBER={q}) >= {target} at strong_alpha={self.strong_alpha}"
        if loss > 0:
            reason += f", inflated for observed loss {loss:.1%}"
        if not reached:
            reason += f" (capped at {self.max_test_tokens})"
        return {"policy": "power", "test_tokens": n, "measured_tokens_needed": n_meas, "suspicious": suspicious,
                "power_target": target, "attack_qber": q, "power": round(power, 4), "reached": reached,
                "loss_adjustment": round(loss, 4), "reason": reason}

    def reserve_plan(self, n_bits: int, observed_loss: float = 0.0) -> Dict[str, Any]:
        """L-aware reserve size: extra signature positions so short signatures can approach the risk budget."""
        if self.reserve_policy != "auto" or self.threshold_policy != "exact" or n_bits <= 0:
            return {"policy": "off", "reserve_bits": 0, "reason": "reserve disabled"}
        keep = 1.0 - min(max(observed_loss, 0.0), 0.5)
        # Copies per verifier ~ Bin(2L, 1/2): plan for one standard deviation below the mean.
        n_expected = int((n_bits - math.sqrt(n_bits / 2.0)) * keep)
        cap = int(self.max_reserve_ratio * n_bits)
        r_copies, reached = plan_reserve(n_expected, self.mu_honest, self.forger_min_mismatch,
                                         self.fr_target, self.fa_target, int(cap * keep))
        bits = min(cap, int(math.ceil(r_copies / keep))) if r_copies else 0
        if bits == 0:
            reason = f"stage 1 alone meets the risk budget at ~{n_expected} checked copies"
        elif reached:
            reason = f"{bits} reserve positions let a two-stage rule meet the risk budget at ~{n_expected} copies"
        else:
            reason = (f"risk budget unreachable within {cap} reserve positions at ~{n_expected} copies; "
                      f"reserve sized at the cap (best effort)")
        return {"policy": "auto", "reserve_bits": bits, "expected_copies": n_expected,
                "reaches_target": reached, "reason": reason}

    # ------------------------------------------------------------- reporting
    def bounds(self, n: int, mismatches: int, forwarded: bool = False,
               rule: Optional[EliminationRule] = None, reserve_mismatches: Optional[int] = None) -> Dict[str, Any]:
        rule = rule or self.elimination_rule(n, forwarded)
        s = self.limit_rate(forwarded)
        limit = rule.a1
        p_fr = _hoeffding(s - self.mu_honest, n)
        p_forge = _hoeffding(self.forger_min_mismatch - s, n)
        rep_gap = self.s_v - self.s_a
        p_rep = min(1.0, 2.0 * math.exp(-(rep_gap ** 2) * n / 2.0)) if n > 0 else 1.0
        if rule.policy == "legacy":
            n_req = max(
                _n_required(s - self.mu_honest, self.target_failure),
                _n_required(self.forger_min_mismatch - s, self.target_failure),
                _n_required(rep_gap / 2.0, self.target_failure, factor=2.0),
            )
            target, meets = f"{self.target_failure:.0e}", n >= n_req
            values = {"false_reject": f"{p_fr:.3e}", "forgery_accept": f"{p_forge:.3e}",
                      "repudiation": f"{p_rep:.3e}"}
            formulas = {"false_reject": "exp(-2 (s - mu_h)^2 n)", "forgery_accept": "exp(-2 (p_min - s)^2 n)",
                        "repudiation": "2 exp(-(s_v - s_a)^2 n / 2)"}
        else:
            n_req = self.n_required()
            target, meets = f"FR<={self.fr_target:.0e}, FA<={self.fa_target:.0e}", rule.sufficient
            values = {"false_reject": f"{rule.false_reject:.3e}", "forgery_accept": f"{rule.forgery_accept:.3e}",
                      "repudiation": f"{p_rep:.3e}"}
            formulas = {
                "false_reject": ("P_h(M > a1), M ~ Bin(n, mu_h)" if not rule.two_stage else
                                 "P_h(M1 > r1) + sum_band P_h(M1=m) P_h(M2 > a2-m)"),
                "forgery_accept": ("P_f(M <= a1), M ~ Bin(n, p_min)" if not rule.two_stage else
                                   "P_f(M1 <= a1) + sum_band P_f(M1=m) P_f(M2 <= a2-m)"),
                "repudiation": "2 exp(-(s_v - s_a)^2 n / 2)  [Hoeffding reference only]",
            }
        return {
            "mode": "forwarded" if forwarded else "direct",
            "policy": rule.policy,
            "inputs": {
                "n_checked_copies": n,
                "observed_mismatches": mismatches,
                "observed_rate": round(mismatches / n, 4) if n else None,
                "n_reserve_copies": rule.n2,
                "reserve_mismatches": reserve_mismatches,
                "e0_honest_qber": self.honest_qber,
                "mu_honest": round(self.mu_honest, 4),
                "p_min_forger": round(self.forger_min_mismatch, 4),
                "s_a": round(self.s_a, 4),
                "s_v": round(self.s_v, 4),
                "limit_rate_used": round(limit / n, 4) if (n and rule.policy == "exact") else round(s, 4),
            },
            "decision_rule": f"{rule.describe()}  (n = {n})",
            "acceptance_limit": limit,
            "rule": rule.to_dict(),
            "evidence_status": "sufficient" if meets else "below_target",
            "formulas": formulas,
            "values": values,
            "hoeffding_reference": {
                "limit_rate": round(s, 4),
                "false_reject": f"{p_fr:.3e}",
                "forgery_accept": f"{p_forge:.3e}",
                "repudiation": f"{p_rep:.3e}",
                "note": "exp(-2 d^2 n) bounds at the legacy rate s; conservative reference, not the applied rule",
            },
            "target_failure": target,
            "n_required_for_target": n_req,
            "meets_target": meets,
            "assumptions": ASSUMPTIONS,
            "status": ("exact probability within the stated i.i.d. model (not a security proof)"
                       if rule.policy == "exact" else
                       "illustrative bound under stated assumptions (not a security proof)"),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "honest_qber_e0": self.honest_qber,
            "forger_min_mismatch_p_min": round(self.forger_min_mismatch, 4),
            "false_alarm_alpha": self.false_alarm_alpha,
            "freshness_window_s": self.freshness_window_s,
            "s_a": round(self.s_a, 4),
            "s_v": round(self.s_v, 4),
            "min_test_tokens": self.min_test_tokens,
            "digest_alg": self.digest_alg,
            "strong_alpha": self.strong_alpha,
            "tier2_alpha": self.tier2_alpha,
            "tier2_channel_beta": self.tier2_channel_beta,
            "abort_chunks": self.abort_chunks,
            "watch_test_multiplier": self.watch_test_multiplier,
            "target_failure": self.target_failure,
            "min_surviving_ratio": self.min_surviving_ratio,
            "early_abort": self.early_abort,
            "detection_tiers": self.detection_tiers,
            "threshold_policy": self.threshold_policy,
            "fr_target": self.fr_target,
            "fa_target": self.fa_target,
            "allocation_policy": self.allocation_policy,
            "test_power_target": self.test_power_target,
            "test_attack_qber": self.test_attack_qber,
            "test_power_target_watch": self.test_power_target_watch,
            "test_attack_qber_watch": self.test_attack_qber_watch,
            "max_test_tokens": self.max_test_tokens,
            "reserve_policy": self.reserve_policy,
            "max_reserve_ratio": self.max_reserve_ratio,
            "max_reserve_openings": self.max_reserve_openings,
        }
