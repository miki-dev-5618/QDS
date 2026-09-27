import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional

from .threats import ThreatType


class ThreatClassification(str, Enum):
    BENIGN_AUTHENTIC = "BENIGN_AUTHENTIC"
    CHANNEL_NOISE = "CHANNEL_NOISE"
    EXTERNAL_FORGERY = "EXTERNAL_FORGERY"
    DISHONEST_VERIFIER_FORGERY = "DISHONEST_VERIFIER_FORGERY"
    EAVESDROPPING_TAMPERING = "EAVESDROPPING_TAMPERING"
    REPUDIATION_ATTEMPT = "REPUDIATION_ATTEMPT"
    REPLAY_ATTACK = "REPLAY_ATTACK"
    IMPERSONATION_ATTACK = "IMPERSONATION_ATTACK"
    MESSAGE_INTEGRITY_VIOLATION = "MESSAGE_INTEGRITY_VIOLATION"
    UNAUTHORIZED_VERIFICATION = "UNAUTHORIZED_VERIFICATION"


@dataclass
class SecurityCertificate:
    signature_length: int
    channel_error_rate: float
    observed_mismatch_rate: float
    acceptance_threshold_sa: float
    verification_threshold_sv: float
    safety_margin_delta: float
    forgery_probability_bound: float
    false_rejection_probability_bound: float
    repudiation_probability_bound: float
    is_securely_accepted: bool
    security_level_bits: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_length": self.signature_length,
            "channel_error_rate": round(self.channel_error_rate, 4),
            "observed_mismatch_rate": round(self.observed_mismatch_rate, 4),
            "acceptance_threshold_sa": round(self.acceptance_threshold_sa, 4),
            "verification_threshold_sv": round(self.verification_threshold_sv, 4),
            "safety_margin_delta": round(self.safety_margin_delta, 4),
            "forgery_probability_bound": f"{self.forgery_probability_bound:.2e}",
            "false_rejection_probability_bound": f"{self.false_rejection_probability_bound:.2e}",
            "repudiation_probability_bound": f"{self.repudiation_probability_bound:.2e}",
            "is_securely_accepted": self.is_securely_accepted,
            "security_level_bits": round(self.security_level_bits, 1)
        }


class QDSSecurityBounds:
    """
    Evaluates Information-Theoretic Security (ITS) bounds using Chernoff-Hoeffding inequalities.
    """
    @staticmethod
    def compute_thresholds(
        e0: float = 0.02,
        p_forg_min: float = 0.25,
        delta: Optional[float] = None
    ) -> Tuple[float, float, float]:
        max_delta = (p_forg_min - e0) / 3.0
        if delta is None or delta <= 0 or delta >= max_delta:
            delta = max_delta
        s_a = e0 + delta
        s_v = p_forg_min - delta
        return s_a, s_v, delta

    @staticmethod
    def chernoff_forgery_bound(L: int, delta: float) -> float:
        exponent = -2.0 * (delta ** 2) * L
        if exponent < -700:
            return 0.0
        return math.exp(exponent)

    @staticmethod
    def false_rejection_bound(L: int, delta: float) -> float:
        exponent = -2.0 * (delta ** 2) * L
        if exponent < -700:
            return 0.0
        return math.exp(exponent)

    @staticmethod
    def repudiation_bound(L: int, s_a: float, s_v: float) -> float:
        gap = s_v - s_a
        exponent = -0.5 * (gap ** 2) * L
        if exponent < -700:
            return 0.0
        return min(1.0, 2.0 * math.exp(exponent))

    @classmethod
    def generate_security_certificate(
        cls,
        signature_length: int,
        channel_error_rate: float,
        mismatches: int,
        total_checked: int
    ) -> SecurityCertificate:
        s_a, s_v, delta = cls.compute_thresholds(e0=channel_error_rate)
        obs_rate = (mismatches / total_checked) if total_checked > 0 else 0.0
        p_forge = cls.chernoff_forgery_bound(signature_length, delta)
        p_frr = cls.false_rejection_bound(signature_length, delta)
        p_rep = cls.repudiation_bound(signature_length, s_a, s_v)

        is_accepted = (obs_rate <= s_a) and (channel_error_rate < s_v)
        sec_bits = -math.log2(p_forge) if p_forge > 0 else 256.0
        sec_bits = min(256.0, max(0.0, sec_bits))

        return SecurityCertificate(
            signature_length=signature_length,
            channel_error_rate=channel_error_rate,
            observed_mismatch_rate=obs_rate,
            acceptance_threshold_sa=s_a,
            verification_threshold_sv=s_v,
            safety_margin_delta=delta,
            forgery_probability_bound=p_forge,
            false_rejection_probability_bound=p_frr,
            repudiation_probability_bound=p_rep,
            is_securely_accepted=is_accepted,
            security_level_bits=sec_bits
        )


@dataclass
class ThreatReport:
    classification: ThreatClassification
    confidence_score: float
    bob_contradictions: int
    bob_total_checked: int
    bob_contradiction_rate: float
    charlie_contradictions: int
    charlie_total_checked: int
    charlie_contradiction_rate: float
    asymmetry_discrepancy: float
    verdict: str
    details: str
    is_threat_detected: bool
    security_certificate: Optional[SecurityCertificate] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification.value,
            "confidence_score": round(self.confidence_score, 4),
            "bob_contradictions": self.bob_contradictions,
            "bob_total_checked": self.bob_total_checked,
            "bob_contradiction_rate": round(self.bob_contradiction_rate, 4),
            "charlie_contradictions": self.charlie_contradictions,
            "charlie_total_checked": self.charlie_total_checked,
            "charlie_contradiction_rate": round(self.charlie_contradiction_rate, 4),
            "asymmetry_discrepancy": round(self.asymmetry_discrepancy, 4),
            "verdict": self.verdict,
            "details": self.details,
            "is_threat_detected": self.is_threat_detected,
            "certificate": self.security_certificate.to_dict() if self.security_certificate else None
        }


class QDSDetectionEngine:
    def __init__(self, allowable_noise_threshold: float = 0.05):
        self.allowable_noise_threshold = allowable_noise_threshold

    def analyze(
        self,
        bob_mismatches: int,
        bob_total: int,
        charlie_mismatches: int,
        charlie_total: int,
        channel_qber: Optional[float] = None,
        is_fresh: bool = True,
        sender_authenticated: bool = True,
        message_tampered: bool = False,
        threat_type: ThreatType = ThreatType.AUTHENTIC
    ) -> ThreatReport:
        b_rate = (bob_mismatches / bob_total) if bob_total > 0 else 0.0
        c_rate = (charlie_mismatches / charlie_total) if charlie_total > 0 else 0.0
        rate_diff = abs(b_rate - c_rate)
        max_rate = max(b_rate, c_rate)
        total_len = max(bob_total, charlie_total, 1)

        cert = QDSSecurityBounds.generate_security_certificate(
            signature_length=total_len,
            channel_error_rate=channel_qber if channel_qber is not None else self.allowable_noise_threshold,
            mismatches=max(bob_mismatches, charlie_mismatches),
            total_checked=total_len
        )

        # 1. Explicit threat type checks
        if threat_type == ThreatType.IMPERSONATION or not sender_authenticated:
            return ThreatReport(
                classification=ThreatClassification.IMPERSONATION_ATTACK,
                confidence_score=1.0,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="THREAT DETECTED: UNAUTHORIZED IMPERSONATION",
                details="Claimed sender lacks valid quantum entangled pair distribution and credentials.",
                is_threat_detected=True,
                security_certificate=cert
            )

        if threat_type == ThreatType.REPLAY or not is_fresh:
            return ThreatReport(
                classification=ThreatClassification.REPLAY_ATTACK,
                confidence_score=1.0,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="THREAT DETECTED: REPLAY ATTACK",
                details="Cryptographic nonce reused or timestamp expired outside coherence window.",
                is_threat_detected=True,
                security_certificate=cert
            )

        if threat_type == ThreatType.MESSAGE_TAMPERING or message_tampered:
            return ThreatReport(
                classification=ThreatClassification.MESSAGE_INTEGRITY_VIOLATION,
                confidence_score=1.0,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="INTEGRITY THREAT: MESSAGE PAYLOAD TAMPERED",
                details="Plaintext payload altered in transit; cryptographic hash context rejected.",
                is_threat_detected=True,
                security_certificate=cert
            )

        if threat_type == ThreatType.EVE_INTERCEPT or (channel_qber is not None and channel_qber > 0.20):
            return ThreatReport(
                classification=ThreatClassification.EAVESDROPPING_TAMPERING,
                confidence_score=min(1.0, (channel_qber or 0.25) / 0.25),
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="QUANTUM ALERT: EAVESDROPPING / CHANNEL MANIPULATION DETECTED",
                details=f"Quantum Bit Error Rate (QBER={(channel_qber or 0.25)*100:.1f}%) exceeds physical threshold. Superpositions collapsed in transit by MITM interceptor.",
                is_threat_detected=True,
                security_certificate=cert
            )

        if threat_type == ThreatType.REPUDIATION:
            return ThreatReport(
                classification=ThreatClassification.REPUDIATION_ATTEMPT,
                confidence_score=0.98,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="THREAT QUENCHED: SIGNER REPUDIATION DETECTED",
                details=f"Asymmetric states exposed through Keep-or-Forward cross-symmetrisation between Bob and Charlie.",
                is_threat_detected=True,
                security_certificate=cert
            )

        if threat_type == ThreatType.DISHONEST_BOB:
            return ThreatReport(
                classification=ThreatClassification.DISHONEST_VERIFIER_FORGERY,
                confidence_score=1.0,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="THREAT QUENCHED: DISHONEST VERIFIER FORGERY DETECTED",
                details=f"Bob verified authentic copy ({bob_mismatches} errors) but Charlie encountered {charlie_mismatches} state elimination collisions on Bob's forwarded counterfeit.",
                is_threat_detected=True,
                security_certificate=cert
            )

        if threat_type == ThreatType.EVE_FORGERY or max(bob_mismatches, charlie_mismatches) > 0:
            return ThreatReport(
                classification=ThreatClassification.EXTERNAL_FORGERY,
                confidence_score=min(1.0, max(0.85, max_rate / 0.25)),
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="THREAT QUENCHED: EXTERNAL SIGNATURE FORGERY DETECTED",
                details=f"Verifiers encountered state elimination violations (Bob: {bob_mismatches}, Charlie: {charlie_mismatches}). Random classical forgery detected.",
                is_threat_detected=True,
                security_certificate=cert
            )

        # Baseline Authentic
        return ThreatReport(
            classification=ThreatClassification.BENIGN_AUTHENTIC,
            confidence_score=1.0,
            bob_contradictions=bob_mismatches,
            bob_total_checked=bob_total,
            bob_contradiction_rate=b_rate,
            charlie_contradictions=charlie_mismatches,
            charlie_total_checked=charlie_total,
            charlie_contradiction_rate=c_rate,
            asymmetry_discrepancy=rate_diff,
            verdict="SIGNATURE VERIFIED: AUTHENTIC & UNTAMPERED",
            details="Zero state elimination contradictions. Information-theoretic security guaranteed.",
            is_threat_detected=False,
            security_certificate=cert
        )
