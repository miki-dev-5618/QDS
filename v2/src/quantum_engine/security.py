"""
One threat model, one set of thresholds, and the bounds that follow from them.

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
  s_a    = mu_h + gap/3     acceptance limit for a directly received signature
  s_v    = mu_h + 2*gap/3   acceptance limit for a forwarded signature (s_a < s_v)

Decision rule (the same one whose bounds are displayed):
  accept  iff  mismatches <= floor(s * n)   with s = s_a (direct) or s_v (forwarded)

Hoeffding bounds (assume per-copy outcomes independent, per-copy mismatch
probability <= mu_h for honest runs and >= p_min for forgers; symmetrisation
assigns each copy independently and uniformly to a verifier):
  P(false reject)      <= exp(-2 (s - mu_h)^2 n)
  P(forgery accepted)  <= exp(-2 (p_min - s)^2 n)
  P(repudiation)       <= 2 exp(-(s_v - s_a)^2 n / 2)
These are illustrative finite-sample bounds under the stated assumptions, not
a composable security proof against general (coherent) attacks.
"""
import math
from dataclasses import dataclass
from typing import Dict, Any, List

from .channel import binomial_upper_tail

ASSUMPTIONS: List[str] = [
    "Per-copy measurement outcomes are independent.",
    "Honest per-copy mismatch probability <= e0/2 (e0 enforced by the channel test at level alpha).",
    "A forger without the signer's states mismatches each copy with probability >= p_min "
    "(1/4 for an outside guesser, >= 1/6 for a dishonest verifier holding one copy); "
    "coherent/collective attacks are not covered.",
    "Keep-or-forward assigns every copy to Bob or Charlie independently and uniformly.",
    "Bounds are Hoeffding tail bounds; they are illustrative, not a composable security proof.",
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


@dataclass(frozen=True)
class SecurityParameters:
    honest_qber: float = 0.02
    forger_min_mismatch: float = 1.0 / 6.0
    false_alarm_alpha: float = 0.01
    freshness_window_s: float = 120.0
    target_failure: float = 1e-6
    min_test_tokens: int = 16
    digest_alg: str = "sha256"            # or "sha3-512"
    strong_alpha: float = 1e-3            # evidence level for immediate quarantine / early abort
    tier2_alpha: float = 0.05             # excess-mismatch test (signature inconsistency)
    tier2_channel_beta: float = 0.10      # channel-elevation level for Tier 2 attribution
    abort_chunks: int = 4                 # stream blocks between early-abort checks
    watch_test_multiplier: int = 2        # adaptive test allocation while a link is on WATCH

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

    def acceptance_limit(self, n: int, forwarded: bool = False) -> int:
        """Maximum number of mismatches accepted out of n checked copies."""
        return int(math.floor(self.limit_rate(forwarded) * n + 1e-9))

    def bounds(self, n: int, mismatches: int, forwarded: bool = False) -> Dict[str, Any]:
        s = self.limit_rate(forwarded)
        limit = self.acceptance_limit(n, forwarded)
        p_fr = _hoeffding(s - self.mu_honest, n)
        p_forge = _hoeffding(self.forger_min_mismatch - s, n)
        rep_gap = self.s_v - self.s_a
        p_rep = min(1.0, 2.0 * math.exp(-(rep_gap ** 2) * n / 2.0)) if n > 0 else 1.0
        n_req = max(
            _n_required(s - self.mu_honest, self.target_failure),
            _n_required(self.forger_min_mismatch - s, self.target_failure),
            _n_required(rep_gap / 2.0, self.target_failure, factor=2.0),
        )
        return {
            "mode": "forwarded" if forwarded else "direct",
            "inputs": {
                "n_checked_copies": n,
                "observed_mismatches": mismatches,
                "observed_rate": round(mismatches / n, 4) if n else None,
                "e0_honest_qber": self.honest_qber,
                "mu_honest": round(self.mu_honest, 4),
                "p_min_forger": round(self.forger_min_mismatch, 4),
                "s_a": round(self.s_a, 4),
                "s_v": round(self.s_v, 4),
                "limit_rate_used": round(s, 4),
            },
            "decision_rule": f"accept iff mismatches <= floor({s:.4f} * {n}) = {limit}",
            "acceptance_limit": limit,
            "formulas": {
                "false_reject": "exp(-2 (s - mu_h)^2 n)",
                "forgery_accept": "exp(-2 (p_min - s)^2 n)",
                "repudiation": "2 exp(-(s_v - s_a)^2 n / 2)",
            },
            "values": {
                "false_reject": f"{p_fr:.3e}",
                "forgery_accept": f"{p_forge:.3e}",
                "repudiation": f"{p_rep:.3e}",
            },
            "target_failure": f"{self.target_failure:.0e}",
            "n_required_for_target": n_req,
            "meets_target": n >= n_req,
            "assumptions": ASSUMPTIONS,
            "status": "illustrative bound under stated assumptions (not a security proof)",
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
        }
