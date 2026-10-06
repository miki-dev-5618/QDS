"""
Quantum channel model and *observable* channel testing (Tier 1).

``ChannelModel`` holds hidden physical parameters (noise, interception,
bursts). They drive the simulation only; verifiers and the detector never
read them.

``estimate_channel_qber`` is what the verifiers can actually compute: Alice
discloses the prepared states of a secret, random set of sacrificed test
tokens interleaved with the signature copies, the verifiers measure those
tokens in the disclosed basis, and the error count is compared with an exact
binomial hypothesis test.

Sequential early abort. The alarm rule is "errors > k" over the *planned*
number of test tokens. Errors only accumulate, so once the running count
exceeds a threshold the final outcome is already decided and the rest of the
stream can be dropped without changing the test's false-alarm level. The
engine stops early only on a *decisive* count (errors > k_strong, computed at
the stricter quarantine level) so that an early abort always carries
quarantine-grade evidence. The reported p-value is P(X >= e) for X ~
Bin(planned, p0), which stays valid under this optional stopping because the
full-sample count can only be >= the count observed at the stop.
"""
import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from .teleportation import sample_channel_events


@dataclass(frozen=True)
class ChannelModel:
    """Hidden channel parameters. Ground truth for experiments only."""
    depolarizing: float = 0.01    # probability of a random Pauli on the travelling qubit
    intercept_rate: float = 0.0   # fraction of tokens Eve intercepts and resends
    burst_rate: float = 0.0       # per-token probability that a noise burst starts
    burst_depolarizing: float = 0.5
    burst_length: int = 8         # tokens per burst

    def expected_qber(self) -> float:
        """Matched-basis error probability implied by these parameters (bursts averaged)."""
        f = self.burst_fraction()
        dep = (1 - f) * self.depolarizing + f * self.burst_depolarizing
        a = 0.25 * self.intercept_rate       # intercept-resend in a random basis
        b = 2.0 * dep / 3.0                  # two of the three Paulis flip a given basis
        return a + b - 2 * a * b

    def burst_fraction(self) -> float:
        if self.burst_rate <= 0:
            return 0.0
        x = self.burst_rate * self.burst_length
        return x / (1.0 + x)

    def sample_events(self, n: int, rng: np.random.Generator) -> List[Tuple[Optional[int], Optional[str]]]:
        """Per-token (eve_basis, noise_pauli) in transmission order."""
        if self.burst_rate <= 0:
            return sample_channel_events(n, rng, self.depolarizing, self.intercept_rate)
        events, left = [], 0
        for _ in range(n):
            if left == 0 and rng.random() < self.burst_rate:
                left = self.burst_length
            dep = self.burst_depolarizing if left > 0 else self.depolarizing
            left = max(0, left - 1)
            events.extend(sample_channel_events(1, rng, dep, self.intercept_rate))
        return events


def binomial_upper_tail(n: int, p: float, k: int) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def bernoulli_kl(a: float, p: float) -> float:
    """D(a || p) in nats for Bernoulli distributions."""
    def term(x, y):
        return 0.0 if x <= 0 else x * math.log(x / y)
    if p <= 0 or p >= 1:
        return math.inf
    return term(a, p) + term(1 - a, 1 - p)


def chernoff_kl_tail_bound(n: int, p: float, k: int) -> float:
    """Chernoff bound P(X >= k) <= exp(-n D(k/n || p)) for k/n > p (else 1)."""
    if n <= 0 or k <= n * p:
        return 1.0
    if k > n:
        return 0.0
    return math.exp(-n * bernoulli_kl(k / n, p))


def critical_error_count(n: int, honest_qber: float, alpha: float) -> int:
    """
    Largest error count still consistent with an honest channel.

    Returns the smallest k with P(X > k | n, honest_qber) <= alpha; an alarm is
    raised when observed errors exceed k. alpha is therefore an upper bound on
    the false-alarm probability *if* the honest QBER is at most honest_qber.
    """
    for k in range(0, n + 1):
        if binomial_upper_tail(n, honest_qber, k + 1) <= alpha:
            return k
    return n


def wilson_interval(successes: int, n: int, z: float = 1.96):
    """Wilson score interval for a binomial proportion (default 95%)."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass
class ChannelTestResult:
    test_count: int                  # test tokens actually measured
    error_count: int
    qber_estimate: float
    qber_ci_low: float
    qber_ci_high: float
    honest_qber_assumption: float
    false_alarm_alpha: float
    alarm_threshold_errors: int      # alarm iff error_count > this
    detection_power_at_25pct: float  # P(alarm) if an intercept-resend attack gives QBER = 0.25
    alarm: bool
    planned_test_count: int = 0      # test tokens scheduled for this session
    p_value: float = 1.0             # P(X >= errors | planned, p0)
    chernoff_kl_bound: float = 1.0   # exp(-n D((k+1)/n || p0)) >= the exact false-alarm level
    strong_alpha: float = 1e-3
    strong_threshold_errors: int = 0  # decisive count (early abort / quarantine grade)
    early_abort: bool = False
    tokens_sent: int = 0
    tokens_planned: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for key in ("qber_estimate", "qber_ci_low", "qber_ci_high", "detection_power_at_25pct"):
            d[key] = round(d[key], 4)
        for key in ("p_value", "chernoff_kl_bound"):
            d[key] = float(f"{d[key]:.4e}")
        exact = binomial_upper_tail(self.planned_test_count or self.test_count, self.honest_qber_assumption,
                                    self.alarm_threshold_errors + 1)
        d["exact_false_alarm_level"] = float(f"{exact:.4e}")
        return d


def estimate_channel_qber(
    test_count: int,
    error_count: int,
    honest_qber: float,
    alpha: float,
    planned_count: Optional[int] = None,
    strong_alpha: float = 1e-3,
    tokens_sent: int = 0,
    tokens_planned: int = 0,
) -> ChannelTestResult:
    planned = planned_count or test_count
    k = critical_error_count(planned, honest_qber, alpha)
    k_strong = critical_error_count(planned, honest_qber, strong_alpha)
    lo, hi = wilson_interval(error_count, test_count)
    early = test_count < planned
    return ChannelTestResult(
        test_count=test_count,
        error_count=error_count,
        qber_estimate=(error_count / test_count) if test_count else 0.0,
        qber_ci_low=lo,
        qber_ci_high=hi,
        honest_qber_assumption=honest_qber,
        false_alarm_alpha=alpha,
        alarm_threshold_errors=k,
        detection_power_at_25pct=binomial_upper_tail(planned, 0.25, k + 1),
        alarm=error_count > k,
        planned_test_count=planned,
        p_value=binomial_upper_tail(planned, honest_qber, error_count),
        chernoff_kl_bound=chernoff_kl_tail_bound(planned, honest_qber, k + 1),
        strong_alpha=strong_alpha,
        strong_threshold_errors=k_strong,
        early_abort=early,
        tokens_sent=tokens_sent,
        tokens_planned=tokens_planned,
    )
