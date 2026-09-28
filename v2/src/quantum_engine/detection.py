"""
Blind threat classifier.

Input: only what the verifiers observed (their VerificationResults) and the
channel test computed from disclosed test tokens. There is deliberately no
attack-label parameter: identical observations always produce the
identical verdict.

Decision order (first matching rule wins):
  1. Tier 1 channel alarm                             -> EAVESDROPPING_TAMPERING
  2. No distribution record / sender != record sender -> IMPERSONATION_ATTACK
  3. Nonce already consumed / timestamp out of window -> REPLAY_ATTACK
  4. Forwarded package fails elimination or binding   -> DISHONEST_VERIFIER_FORGERY
  5. Binding fails and elimination fails              -> EXTERNAL_FORGERY
  6. Binding fails, elimination passes                -> MESSAGE_INTEGRITY_VIOLATION
  7. Binding passes, elimination fails: Tier 2 attributes the contradictions
       signature_inconsistency                        -> REPUDIATION_ATTEMPT
       channel_disturbance                            -> EAVESDROPPING_TAMPERING (via Tier 2)
       undetermined                                   -> UNDETERMINED_DISTURBANCE
     (the signature is exactly what the authenticated signer committed to, yet
     it contradicts the distributed states; Tier 2 asks whether the channel
     disturbance measured on the test tokens explains the contradictions)
  8. All accepted, some mismatches / channel errors   -> CHANNEL_NOISE (benign)
  9. All accepted, no mismatches                      -> BENIGN_AUTHENTIC

Each report carries its supporting counts and an evidence strength
(``evidence_p``: the smallest p-value under the honest hypothesis among the
statistics that caused the rejection). The response policy uses it to choose
between watching and quarantining a link.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from .channel import ChannelTestResult
from .discriminator import TierTwoResult, tier_two
from .security import SecurityParameters
from .verifier import VerificationResult


class ThreatClassification(str, Enum):
    BENIGN_AUTHENTIC = "BENIGN_AUTHENTIC"
    CHANNEL_NOISE = "CHANNEL_NOISE"
    EXTERNAL_FORGERY = "EXTERNAL_FORGERY"
    DISHONEST_VERIFIER_FORGERY = "DISHONEST_VERIFIER_FORGERY"
    EAVESDROPPING_TAMPERING = "EAVESDROPPING_TAMPERING"
    REPUDIATION_ATTEMPT = "REPUDIATION_ATTEMPT"
    UNDETERMINED_DISTURBANCE = "UNDETERMINED_DISTURBANCE"
    REPLAY_ATTACK = "REPLAY_ATTACK"
    IMPERSONATION_ATTACK = "IMPERSONATION_ATTACK"
    MESSAGE_INTEGRITY_VIOLATION = "MESSAGE_INTEGRITY_VIOLATION"
    UNAUTHORIZED_VERIFICATION = "UNAUTHORIZED_VERIFICATION"


BENIGN = {ThreatClassification.BENIGN_AUTHENTIC, ThreatClassification.CHANNEL_NOISE}

_VERDICTS = {
    ThreatClassification.BENIGN_AUTHENTIC: "SIGNATURE ACCEPTED: ALL CHECKS PASSED",
    ThreatClassification.CHANNEL_NOISE: "SIGNATURE ACCEPTED: MISMATCHES WITHIN HONEST-NOISE LIMIT",
    ThreatClassification.EAVESDROPPING_TAMPERING: "CHANNEL ALARM: TEST-TOKEN QBER ABOVE HONEST LIMIT",
    ThreatClassification.IMPERSONATION_ATTACK: "REJECTED: NO AUTHENTICATED DISTRIBUTION FOR CLAIMED SENDER",
    ThreatClassification.REPLAY_ATTACK: "REJECTED: REPLAYED OR STALE PACKAGE",
    ThreatClassification.DISHONEST_VERIFIER_FORGERY: "REJECTED: FORWARDED SIGNATURE FAILS TRANSFER CHECK",
    ThreatClassification.EXTERNAL_FORGERY: "REJECTED: SIGNATURE CONTRADICTS QUANTUM RECORDS AND COMMITMENT",
    ThreatClassification.MESSAGE_INTEGRITY_VIOLATION: "REJECTED: MESSAGE/CONTEXT DOES NOT MATCH SIGNER COMMITMENT",
    ThreatClassification.REPUDIATION_ATTEMPT: "REJECTED: SIGNER'S OWN SIGNATURE CONTRADICTS DISTRIBUTED STATES",
    ThreatClassification.UNDETERMINED_DISTURBANCE:
        "REJECTED: SIGNATURE CONTRADICTS RECORDS; CAUSE UNDETERMINED (CHANNEL OR SIGNER)",
}
_TIER2_CHANNEL_VERDICT = "CHANNEL ANOMALY (TIER 2): CONTRADICTIONS EXPLAINED BY ELEVATED CHANNEL DISTURBANCE"


@dataclass
class ThreatReport:
    classification: ThreatClassification
    verdict: str
    details: str
    is_threat_detected: bool
    evidence: List[str] = field(default_factory=list)
    verifier_verdicts: Dict[str, bool] = field(default_factory=dict)
    verifiers_agree: bool = True
    decided_by: str = "all_checks"
    evidence_p: float = 1.0
    tier1: Optional[Dict[str, Any]] = None
    tier2: Optional[Dict[str, Any]] = None
    elimination_p: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification.value,
            "verdict": self.verdict,
            "details": self.details,
            "is_threat_detected": self.is_threat_detected,
            "evidence": self.evidence,
            "verifier_verdicts": self.verifier_verdicts,
            "verifiers_agree": self.verifiers_agree,
            "decided_by": self.decided_by,
            "evidence_p": float(f"{self.evidence_p:.4e}"),
            "tier1": self.tier1,
            "tier2": self.tier2,
            "elimination_p": {k: float(f"{v:.4e}") for k, v in self.elimination_p.items()},
        }


class QDSDetectionEngine:
    def __init__(self, params: Optional[SecurityParameters] = None):
        self.params = params or SecurityParameters()

    def classify(
        self,
        observations: Sequence[VerificationResult],
        channel_test: Optional[ChannelTestResult] = None,
    ) -> ThreatReport:
        p = self.params
        obs = list(observations)
        evidence: List[str] = []
        elim_p: Dict[str, float] = {}
        for o in obs:
            tag = f"{o.verifier}/{o.mode}" + (f" via {o.forwarded_by}" if o.forwarded_by else "")
            if o.record_found and o.n_checked:
                elim_p[tag] = p.elimination_p_value(o.n_checked, o.mismatches)
            evidence.append(
                f"{tag}: {'ACCEPT' if o.accepted else 'REJECT'}; mismatches {o.mismatches}/{o.n_checked} "
                f"(limit {o.acceptance_limit}); binding {'ok' if o.binding_pass else 'FAIL'}; "
                f"fresh={o.freshness_reason}; record={'yes' if o.record_found else 'no'}"
            )
        if channel_test is not None:
            abort = (f"; early abort after {channel_test.tokens_sent}/{channel_test.tokens_planned} tokens"
                     if channel_test.early_abort else "")
            evidence.append(
                f"Tier 1 channel test: {channel_test.error_count}/{channel_test.test_count} errors "
                f"(planned {channel_test.planned_test_count}), QBER^={channel_test.qber_estimate:.3f} "
                f"(95% CI {channel_test.qber_ci_low:.3f}-{channel_test.qber_ci_high:.3f}); alarm if errors > "
                f"{channel_test.alarm_threshold_errors}; p={channel_test.p_value:.2e}{abort}"
            )

        t2: TierTwoResult = tier_two(obs, channel_test, p.tier2_alpha, p.tier2_channel_beta)
        if t2.applicable:
            evidence.append(
                f"Tier 2: {t2.contradictions}/{t2.copies} contradictions vs {t2.test_errors}/{t2.test_tokens} "
                f"test errors; p_excess={t2.p_excess:.2e}, p_channel={t2.p_channel:.2e}, "
                f"KL={t2.kl_nats:.2f} nats -> {t2.attribution}"
            )

        direct = [o for o in obs if o.mode == "direct"]
        forwarded = [o for o in obs if o.mode == "forwarded"]
        verdicts = {f"{o.verifier}:{o.mode}": o.accepted for o in obs}
        agree = len({o.accepted for o in direct}) <= 1

        def min_elim_p(subset) -> float:
            vals = [p.elimination_p_value(o.n_checked, o.mismatches) for o in subset if o.n_checked]
            return min(vals) if vals else 1.0

        def report(cls: ThreatClassification, details: str, decided_by: str, evidence_p: float = 1.0,
                   verdict: Optional[str] = None) -> ThreatReport:
            return ThreatReport(
                classification=cls,
                verdict=verdict or _VERDICTS[cls],
                details=details,
                is_threat_detected=cls not in BENIGN,
                evidence=evidence,
                verifier_verdicts=verdicts,
                verifiers_agree=agree,
                decided_by=decided_by,
                evidence_p=evidence_p,
                tier1=channel_test.to_dict() if channel_test is not None else None,
                tier2=t2.to_dict(),
                elimination_p=elim_p,
            )

        if channel_test is not None and channel_test.alarm:
            early = (f" The stream was aborted after {channel_test.tokens_sent} of {channel_test.tokens_planned} "
                     f"tokens because the running error count was already decisive."
                     if channel_test.early_abort else " Session aborted.")
            return report(ThreatClassification.EAVESDROPPING_TAMPERING,
                          f"{channel_test.error_count} of {channel_test.test_count} disclosed test tokens were "
                          f"measured wrong (estimated QBER {channel_test.qber_estimate:.1%}); an honest channel "
                          f"with QBER <= {channel_test.honest_qber_assumption:.0%} exceeds "
                          f"{channel_test.alarm_threshold_errors} errors with probability <= "
                          f"{channel_test.false_alarm_alpha} (exact p = {channel_test.p_value:.2e})." + early,
                          "tier1", channel_test.p_value)

        if any(not o.record_found or not o.sender_matches for o in obs):
            return report(ThreatClassification.IMPERSONATION_ATTACK,
                          "The claimed sender has no authenticated distribution record at the verifiers "
                          "(no quantum tokens or commitment were received from that identity for this session).",
                          "identity")

        if any(not o.fresh for o in obs):
            reasons = sorted({o.freshness_reason for o in obs if not o.fresh})
            return report(ThreatClassification.REPLAY_ATTACK,
                          f"Replay protection rejected the package ({', '.join(reasons)}). The nonce/timestamp are "
                          f"covered by the signer's commitment, so they cannot be altered without failing binding.",
                          "replay")

        bad_forward = [o for o in forwarded if not (o.elimination_pass and o.binding_pass)]
        if bad_forward:
            o = bad_forward[0]
            return report(ThreatClassification.DISHONEST_VERIFIER_FORGERY,
                          f"Signature forwarded by {o.forwarded_by} to {o.verifier}: {o.mismatches}/{o.n_checked} "
                          f"copies contradict {o.verifier}'s own eliminations (limit {o.acceptance_limit}); "
                          f"commitment {'matches' if o.commitment_matches else 'does not match'} the signer's.",
                          "transfer_check", min(min_elim_p(bad_forward), 1.0 if o.commitment_matches else 0.0))

        bind_fail = [o for o in obs if not o.binding_pass]
        elim_fail = [o for o in obs if not o.elimination_pass]
        if bind_fail and elim_fail:
            return report(ThreatClassification.EXTERNAL_FORGERY,
                          "The revealed signature is not the one the signer committed to, and it contradicts the "
                          "verifiers' elimination records: " +
                          "; ".join(f"{o.verifier} {o.mismatches}/{o.n_checked}" for o in elim_fail) + ".",
                          "binding+elimination", min_elim_p(elim_fail))
        if bind_fail:
            digest = any(not o.digest_matches for o in bind_fail)
            return report(ThreatClassification.MESSAGE_INTEGRITY_VIOLATION,
                          ("The received message's digest differs from the signed context. "
                           if digest else "The received context/signature differs from the signer's commitment. ") +
                          "The quantum elimination check alone passed, which is expected when only classical "
                          "payload fields are changed.",
                          "binding")
        if elim_fail:
            counts = "; ".join(f"{o.verifier} {o.mismatches}/{o.n_checked} (limit {o.acceptance_limit})"
                               for o in elim_fail)
            ep = min_elim_p(elim_fail)
            if t2.attribution == "signature_inconsistency":
                return report(ThreatClassification.REPUDIATION_ATTEMPT,
                              f"The revealed signature matches the authenticated signer's commitment but contradicts "
                              f"the distributed states: {counts}. Tier 2: the contradictions exceed what the "
                              f"measured channel disturbance explains (p_excess = {t2.p_excess:.2e}).",
                              "elimination+tier2", ep)
            if t2.attribution == "channel_disturbance":
                return report(ThreatClassification.EAVESDROPPING_TAMPERING,
                              f"The elimination check failed ({counts}) and Tier 1 did not alarm, but Tier 2 finds "
                              f"the test-token error rate elevated (p_channel = {t2.p_channel:.2e}) and the "
                              f"contradictions consistent with that disturbance (p_excess = {t2.p_excess:.2e}). "
                              f"Attributed to the channel.",
                              "elimination+tier2", min(ep, t2.p_channel), verdict=_TIER2_CHANNEL_VERDICT)
            return report(ThreatClassification.UNDETERMINED_DISTURBANCE,
                          f"The revealed signature matches the signer's commitment but contradicts the distributed "
                          f"states: {counts}. Tier 2 cannot attribute the cause at this sample size "
                          f"(p_excess = {t2.p_excess:.2e}, p_channel = {t2.p_channel:.2e}): an honest-noise "
                          f"fluctuation, a weak channel attack and a repudiating signer are all consistent.",
                          "elimination+tier2", ep)

        noisy = any(o.mismatches for o in obs) or (channel_test is not None and channel_test.error_count > 0)
        if noisy:
            return report(ThreatClassification.CHANNEL_NOISE,
                          "All checks passed. Observed mismatches/test errors are within the honest-noise limits.",
                          "all_checks")
        return report(ThreatClassification.BENIGN_AUTHENTIC,
                      "All checks passed with zero elimination contradictions and zero test-token errors.",
                      "all_checks")
