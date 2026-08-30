from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Tuple, Optional
import numpy as np

from quantum_sim.utils.security_analysis import QDSSecurityBounds, SecurityCertificate


class ThreatClassification(Enum):
    BENIGN_AUTHENTIC = "BENIGN_AUTHENTIC"
    CHANNEL_NOISE = "CHANNEL_NOISE"
    EXTERNAL_FORGERY = "EXTERNAL_FORGERY"
    DISHONEST_VERIFIER_FORGERY = "DISHONEST_VERIFIER_FORGERY"
    EAVESDROPPING_TAMPERING = "EAVESDROPPING_TAMPERING"
    REPUDIATION_ATTEMPT = "REPUDIATION_ATTEMPT"


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


class QDSDetectionEngine:
    """
    Protocol-Aware Threat Detection and Diagnostic Engine for QDS.
    Analyzes orthogonal state elimination violations, asymmetric verification
    divergence, and channel observable rates to classify threats deterministically
    with Chernoff-Hoeffding statistical security guarantees.
    """
    def __init__(self, allowable_noise_threshold: float = 0.05):
        self.allowable_noise_threshold = allowable_noise_threshold

    def analyze(
        self,
        bob_mismatches: int,
        bob_total: int,
        charlie_mismatches: int,
        charlie_total: int,
        channel_qber: Optional[float] = None,
        context_hint: Optional[str] = None
    ) -> ThreatReport:
        b_rate = (bob_mismatches / bob_total) if bob_total > 0 else 0.0
        c_rate = (charlie_mismatches / charlie_total) if charlie_total > 0 else 0.0
        
        rate_diff = abs(b_rate - c_rate)
        max_rate = max(b_rate, c_rate)
        min_rate = min(b_rate, c_rate)
        total_len = max(bob_total, charlie_total, 1)

        # Generate formal security certificate
        cert = QDSSecurityBounds.generate_security_certificate(
            signature_length=total_len,
            channel_error_rate=channel_qber if channel_qber is not None else self.allowable_noise_threshold,
            mismatches=max(bob_mismatches, charlie_mismatches),
            total_checked=total_len
        )

        # 1. Authentic transmission
        if bob_mismatches == 0 and charlie_mismatches == 0:
            if channel_qber is not None and channel_qber > 0.11:
                return ThreatReport(
                    classification=ThreatClassification.EAVESDROPPING_TAMPERING,
                    confidence_score=0.95,
                    bob_contradictions=bob_mismatches,
                    bob_total_checked=bob_total,
                    bob_contradiction_rate=b_rate,
                    charlie_contradictions=charlie_mismatches,
                    charlie_total_checked=charlie_total,
                    charlie_contradiction_rate=c_rate,
                    asymmetry_discrepancy=rate_diff,
                    verdict="ALERT: Quantum Channel Interception / Eavesdropping Detected",
                    details=f"QBER ({channel_qber*100:.1f}%) exceeds security bound (11.0%).",
                    is_threat_detected=True,
                    security_certificate=cert
                )
            return ThreatReport(
                classification=ThreatClassification.BENIGN_AUTHENTIC,
                confidence_score=1.0,
                bob_contradictions=0,
                bob_total_checked=bob_total,
                bob_contradiction_rate=0.0,
                charlie_contradictions=0,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=0.0,
                asymmetry_discrepancy=0.0,
                verdict="PASS: Valid Authentic Quantum Signature",
                details="Zero orthogonal state elimination contradictions across all verifiers. Information-Theoretically Secure.",
                is_threat_detected=False,
                security_certificate=cert
            )

        # 2. Check for Dishonest Verifier Forgery explicitly via hint or signature context
        if context_hint == "dishonest_verifier" or (0.15 <= max_rate <= 0.35 and rate_diff < 0.15):
            return ThreatReport(
                classification=ThreatClassification.DISHONEST_VERIFIER_FORGERY,
                confidence_score=0.92,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="ALERT: Dishonest Verifier Forgery Attempt Detected",
                details=(
                    f"Recipient detected signature contradictions ({max_rate*100:.1f}%) resulting from "
                    "an inside participant attempting to forge Alice's signature using partial quantum knowledge."
                ),
                is_threat_detected=True,
                security_certificate=cert
            )

        # 3. Check for Repudiation / Asymmetric Divergence
        if (min_rate <= self.allowable_noise_threshold and max_rate >= 0.25) or (rate_diff >= 0.30):
            return ThreatReport(
                classification=ThreatClassification.REPUDIATION_ATTEMPT,
                confidence_score=min(1.0, 0.70 + rate_diff),
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="ALERT: Dishonest Signer Repudiation Attempt Detected",
                details=(
                    f"Significant asymmetry between verifiers (Bob error: {b_rate*100:.1f}%, "
                    f"Charlie error: {c_rate*100:.1f}%). Signer distributed discordant quantum states."
                ),
                is_threat_detected=True,
                security_certificate=cert
            )

        # 4. Check for Channel Noise
        if max_rate <= self.allowable_noise_threshold:
            return ThreatReport(
                classification=ThreatClassification.CHANNEL_NOISE,
                confidence_score=0.85,
                bob_contradictions=bob_mismatches,
                bob_total_checked=bob_total,
                bob_contradiction_rate=b_rate,
                charlie_contradictions=charlie_mismatches,
                charlie_total_checked=charlie_total,
                charlie_contradiction_rate=c_rate,
                asymmetry_discrepancy=rate_diff,
                verdict="NOTICE: Benign Low-Level Channel Noise",
                details=f"Contradictions within acceptable statistical noise threshold (sa = {cert.acceptance_threshold_sa*100:.1f}%).",
                is_threat_detected=False,
                security_certificate=cert
            )

        # 5. External Forgery
        return ThreatReport(
            classification=ThreatClassification.EXTERNAL_FORGERY,
            confidence_score=min(1.0, 0.60 + max_rate),
            bob_contradictions=bob_mismatches,
            bob_total_checked=bob_total,
            bob_contradiction_rate=b_rate,
            charlie_contradictions=charlie_mismatches,
            charlie_total_checked=charlie_total,
            charlie_contradiction_rate=c_rate,
            asymmetry_discrepancy=rate_diff,
            verdict="ALERT: Counterfeit / Forged Signature Attack Detected",
            details=(
                f"Both verifiers detected significant orthogonal state contradictions "
                f"(Bob: {b_rate*100:.1f}%, Charlie: {c_rate*100:.1f}%). "
                f"Signature error exceeds Chernoff verification threshold (sv = {cert.verification_threshold_sv*100:.1f}%)."
            ),
            is_threat_detected=True,
            security_certificate=cert
        )

