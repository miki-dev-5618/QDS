"""
Tier 2: disturbance-pattern attribution (channel vs. signature source).

Tier 1 (``channel.py``) asks "is the test-token error count too high for an
honest channel?". Tier 2 asks a different question, using only observable
counts: *are the elimination contradictions explained by the channel
disturbance that the test tokens measured, or are there more contradictions
than the channel can explain?*

Model. Under any Pauli-type channel disturbance with matched-basis error q
(depolarising noise gives q = 2p/3; full intercept-resend gives q = 1/4):
  * each test token is measured in its preparation basis, so it errs with
    probability q;
  * a signature copy can only contradict the revealed state when the
    verifier measured in the preparation basis (probability 1/2) and the
    outcome flipped, so it contradicts with probability q/2.
With t test tokens (e errors) and n signature copies (m contradictions),
and q small, the two counts are thinned Poisson streams of one disturbance
process. Conditional on D = e + m,

        m | D  ~  Binomial(D, pi),   pi = (n/2) / (t + n/2),

whatever the unknown q is. This gives an exact, parameter-free test:
  p_excess  = P(Bin(D, pi) >= m)     small -> more contradictions than the
                                             channel explains (signature
                                             inconsistency: signer/forger)
  p_channel = P(Bin(t, p0) >= e)     small -> the channel itself is elevated
                                             above the calibrated baseline p0

Attribution rule (prespecified; applied only when binding passed, the
elimination check failed and Tier 1 did not alarm):
  p_excess  <= alpha2                -> "signature_inconsistency"
  else p_channel <= beta             -> "channel_disturbance"
  else                               -> "undetermined"

Tier 2 never rejects on its own. It only attributes a rejection that the
elimination check already made and selects the response (watch vs.
quarantine). Hence the rejection false-alarm rate is unchanged by Tier 2;
its cost is mislabelling, which the experiments measure.

KL diagnostic. ``kl_nats`` is the log-likelihood-ratio scale divergence of
the observed rates from the honest reference (p0 for tests, p0/2 for
copies), with add-1/2 (Jeffreys) smoothing for zero counts. It describes
separation; it is not a detector and carries no false-alarm guarantee.
"""
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Sequence

from .channel import ChannelTestResult, bernoulli_kl, binomial_upper_tail

TIER2_VERSION = "hedwig-tier2/1"


@dataclass
class TierTwoResult:
    applicable: bool
    test_tokens: int = 0
    test_errors: int = 0
    copies: int = 0
    contradictions: int = 0
    pi_contradiction_share: float = 0.0
    p_excess: float = 1.0
    p_channel: float = 1.0
    kl_nats: float = 0.0
    kl_per_token: float = 0.0
    attribution: str = "not_applicable"
    alpha2: float = 0.05
    beta: float = 0.10
    version: str = TIER2_VERSION

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("pi_contradiction_share", "kl_nats", "kl_per_token"):
            d[k] = round(d[k], 4)
        for k in ("p_excess", "p_channel"):
            d[k] = float(f"{d[k]:.4e}")
        d["rule"] = (f"p_excess <= {self.alpha2} -> signature_inconsistency; else p_channel <= {self.beta} "
                     f"-> channel_disturbance; else undetermined")
        return d


def _smoothed(k: int, n: int) -> float:
    return (k + 0.5) / (n + 1.0)


def tier_two(observations: Sequence[Any], channel_test: Optional[ChannelTestResult],
             alpha2: float = 0.05, beta: float = 0.10) -> TierTwoResult:
    """Compute the Tier 2 statistics from direct verifications with a distribution record."""
    obs = [o for o in observations if o.mode == "direct" and o.record_found]
    if channel_test is None or channel_test.test_count == 0 or not obs:
        return TierTwoResult(applicable=False, alpha2=alpha2, beta=beta)

    t, e = channel_test.test_count, channel_test.error_count
    n = sum(o.n_checked for o in obs)
    m = sum(o.mismatches for o in obs)
    p0 = channel_test.honest_qber_assumption

    share = (n / 2.0) / (t + n / 2.0) if (t + n) else 0.0
    d = e + m
    p_excess = binomial_upper_tail(d, share, m) if d > 0 else 1.0
    p_channel = binomial_upper_tail(t, p0, e)

    kl = t * bernoulli_kl(_smoothed(e, t), p0) + (n * bernoulli_kl(_smoothed(m, n), p0 / 2.0) if n else 0.0)

    if p_excess <= alpha2:
        attribution = "signature_inconsistency"
    elif p_channel <= beta:
        attribution = "channel_disturbance"
    else:
        attribution = "undetermined"

    return TierTwoResult(
        applicable=True, test_tokens=t, test_errors=e, copies=n, contradictions=m,
        pi_contradiction_share=share, p_excess=p_excess, p_channel=p_channel,
        kl_nats=kl, kl_per_token=kl / (t + n) if (t + n) else 0.0,
        attribution=attribution, alpha2=alpha2, beta=beta,
    )
