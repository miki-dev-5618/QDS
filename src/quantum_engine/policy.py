"""
Response policy: turn a blind detector report into two separate outputs.

  verdict          - what happens to *this* transmission (accept / reject);
                     decided by the verifiers and detector, never by policy.
  response_action  - what happens to *future* traffic on the link
                     (none / watch / quarantine).

Rules (policy version ``hedwig-qcb/2``):
  * Benign classifications                     -> none.
  * Classical rejections (replay, impersonation, message integrity,
    unauthorised verification)                 -> none. Anyone can produce
    them at will by sending garbage, so they must not lock out the honest
    signer (that would be a free denial-of-service); the package is simply
    rejected and logged.
  * Quantum-evidence rejections (Tier 1 alarm, Tier 2 channel attribution,
    repudiation, undetermined disturbance, external forgery, dishonest
    verifier): the evidence strength ``evidence_p`` (p-value under the honest
    hypothesis) decides:
        evidence_p <= strong_alpha           -> quarantine (strong)
        otherwise                            -> watch (weak)
  * Escalation (evidence accumulation): the p-values of the weak alerts
    received inside ``watch_window_s`` are combined with Fisher's method,
        X = -2 * sum(ln p_i) ~ chi^2 with 2k degrees of freedom under H0,
    and the link is quarantined when the combined p-value is <=
    ``escalate_alpha``, or when ``watch_strikes`` weak alerts accumulate.
    Two borderline honest-noise alerts (p ~ 0.15 each) combine to ~0.11 and
    do not lock the link; two moderately strong ones (p ~ 0.02) combine to
    ~0.004 and do.
  * A link on RESET_PENDING (probation after an admin reset) is quarantined
    again by any quantum-evidence alert, and returns to OPEN after one fully
    accepted transmission.

False lock-out bound for a single honest transmission: an immediate
quarantine needs a statistic with p <= strong_alpha under the honest
hypothesis; with at most three such statistics per run (Tier 1 and one per
verifier) the union bound gives P(immediate quarantine | honest) <= 3 *
strong_alpha, assuming the honest-noise model holds. Escalation from WATCH
is checked repeatedly over a sequence, so its honest rate is measured in
``experiments/run_trials.py`` (false lock-out over honest sequences), not bounded.
"""
import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, Sequence

from .detection import BENIGN, ThreatClassification, ThreatReport

POLICY_VERSION = "hedwig-qcb/2"

CLASSICAL_ONLY = {
    ThreatClassification.REPLAY_ATTACK,
    ThreatClassification.IMPERSONATION_ATTACK,
    ThreatClassification.MESSAGE_INTEGRITY_VIOLATION,
    ThreatClassification.UNAUTHORIZED_VERIFICATION,
}


@dataclass(frozen=True)
class ResponsePolicy:
    version: str = POLICY_VERSION
    strong_alpha: float = 1e-3
    watch_window_s: float = 900.0
    watch_strikes: int = 3
    escalate_alpha: float = 1e-2

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fisher_combined_p(p_values: Sequence[float]) -> float:
    """Fisher's method: P(chi^2_{2k} >= -2 sum ln p_i), closed form for even degrees of freedom."""
    ps = [min(1.0, max(p, 1e-300)) for p in p_values]
    if not ps:
        return 1.0
    half = -sum(math.log(p) for p in ps)          # X / 2
    term, total = 1.0, 1.0
    for i in range(1, len(ps)):
        term *= half / i
        total += term
    return min(1.0, math.exp(-half) * total)


@dataclass
class ResponseDecision:
    verdict: str            # "accept" | "reject"
    response_action: str    # "none" | "watch" | "quarantine"
    severity: str           # "none" | "classical" | "weak" | "strong"
    evidence_p: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence_p"] = float(f"{self.evidence_p:.4e}")
        return d


def decide(report: ThreatReport, policy: ResponsePolicy) -> ResponseDecision:
    cls = report.classification
    if cls in BENIGN:
        return ResponseDecision("accept", "none", "none", 1.0, "All checks passed.")
    if cls in CLASSICAL_ONLY:
        return ResponseDecision("reject", "none", "classical", report.evidence_p,
                                f"{cls.value}: classical check failed; package rejected, link stays as is "
                                f"(an outsider can trigger this at will).")
    if report.evidence_p <= policy.strong_alpha:
        return ResponseDecision("reject", "quarantine", "strong", report.evidence_p,
                                f"{cls.value}: evidence p = {report.evidence_p:.2e} <= {policy.strong_alpha} "
                                f"(decided by {report.decided_by}).")
    return ResponseDecision("reject", "watch", "weak", report.evidence_p,
                            f"{cls.value}: evidence p = {report.evidence_p:.2e} > {policy.strong_alpha}; "
                            f"single weak observation - link placed on WATCH.")
