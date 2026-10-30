"""
Response policy: turn a blind detector report into two separate outputs.

  verdict          - what happens to *this* transmission (accept / reject);
                     decided by the verifiers and detector, never by policy.
  response_action  - what happens to *future* traffic on the link
                     (none / watch / quarantine).

Rules (policy version ``hedwig-qcb/3``):
  * Benign classifications                     -> none.
  * Inconclusive elimination evidence (count in the borderline band, no
    reserve able to resolve it)               -> none. The signature is not
    accepted, but a statistically weak, unattributed observation never
    escalates the link on its own.
  * Classical rejections (replay, impersonation, message integrity,
    unauthorised verification, invalid transfer route, external classical
    signature forgery) -> none. Anyone can produce
    them at will by sending garbage, so they must not lock out the honest
    signer (that would be a free denial-of-service); the package is simply
    rejected and logged.
  * Quantum-evidence rejections (Tier 1 alarm, Tier 2 channel attribution,
    repudiation, undetermined disturbance, dishonest
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
  * Escalation rule (``escalation``, env ESCALATION; for ablation only):
        fisher       (default) the rule above: Fisher OR watch_strikes alerts
        fisher_only  Fisher-combined p <= escalate_alpha only, no strike count
        counter      quarantine after watch_strikes weak alerts, p-values ignored
    Strong alerts quarantine immediately under every rule.
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
import os
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Sequence

from .detection import BENIGN, ThreatClassification, ThreatReport

POLICY_VERSION = "hedwig-qcb/2"
ESCALATION_RULES = ("fisher", "fisher_only", "counter")

CLASSICAL_ONLY = {
    ThreatClassification.REPLAY_ATTACK,
    ThreatClassification.IMPERSONATION_ATTACK,
    ThreatClassification.MESSAGE_INTEGRITY_VIOLATION,
    ThreatClassification.UNAUTHORIZED_VERIFICATION,
    ThreatClassification.INVALID_TRANSFER,
    ThreatClassification.EXTERNAL_FORGERY,
}


@dataclass(frozen=True)
class ResponsePolicy:
    version: str = POLICY_VERSION
    strong_alpha: float = 1e-3
    watch_window_s: float = 900.0
    watch_strikes: int = 3
    escalate_alpha: float = 1e-2
    escalation: str = field(default_factory=lambda: os.environ.get("ESCALATION", "").strip().lower() or "fisher")

    def __post_init__(self):
        if self.escalation not in ESCALATION_RULES:
            raise ValueError(f"escalation must be one of {ESCALATION_RULES}, got {self.escalation!r}")

    def should_escalate(self, combined_p: float, strikes: int) -> bool:
        """Weak-alert escalation from WATCH under the selected rule."""
        if self.escalation == "counter":
            return strikes >= self.watch_strikes
        if self.escalation == "fisher_only":
            return combined_p <= self.escalate_alpha
        return combined_p <= self.escalate_alpha or strikes >= self.watch_strikes

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.escalation == "fisher":  # default rule: keep the recorded policy identical to before
            del d["escalation"]
        return d


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
        if cls == ThreatClassification.EXTERNAL_FORGERY:
            return ResponseDecision("reject", "none", "classical", report.evidence_p,
                "EXTERNAL_FORGERY: the revealed classical signature differs from Alice's commitment. "
                "Reject this package. This does not prove a faulty quantum edge or a compromised signer; "
                "future quantum distribution remains available.")
        return ResponseDecision("reject", "none", "classical", report.evidence_p,
                                f"{cls.value}: classical check failed; package rejected, link stays as is "
                                f"(an outsider can trigger this at will).")
    if cls == ThreatClassification.INCONCLUSIVE_EVIDENCE:
        return ResponseDecision("reject", "none", "inconclusive", report.evidence_p,
                                "INCONCLUSIVE_EVIDENCE: too little elimination evidence to decide within the risk "
                                "budget; signature not accepted, link state unchanged.")
    if cls == ThreatClassification.INSUFFICIENT_TOKENS:
        return ResponseDecision("reject", "watch", "weak", 1.0,
                                "INSUFFICIENT_TOKENS: photon loss exceeded threshold; link placed on WATCH (not quarantined).")
    if report.evidence_p <= policy.strong_alpha:
        return ResponseDecision("reject", "quarantine", "strong", report.evidence_p,
                                f"{cls.value}: evidence p = {report.evidence_p:.2e} <= {policy.strong_alpha} "
                                f"(decided by {report.decided_by}).")
    return ResponseDecision("reject", "watch", "weak", report.evidence_p,
                            f"{cls.value}: evidence p = {report.evidence_p:.2e} > {policy.strong_alpha}; "
                            f"single weak observation - link placed on WATCH.")
