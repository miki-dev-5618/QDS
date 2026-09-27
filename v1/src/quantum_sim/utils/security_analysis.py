import math
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional


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


class QDSSecurityBounds:
    """
    Mathematical modeling of Information-Theoretic Security (ITS) bounds
    for Quantum Digital Signature protocols using Chernoff-Hoeffding inequalities.
    
    References:
    - Wallden et al., PRA 91, 042304 (2015)
    - Amiri et al., PRA 93, 032325 (2016)
    - Hoeffding's Inequality for Bounded Random Variables
    """

    @staticmethod
    def compute_thresholds(
        e0: float = 0.02,
        p_forg_min: float = 0.25,
        delta: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """
        Computes the acceptance threshold s_a, verification threshold s_v, and safety margin delta.
        
        Requirements for information-theoretic security:
          e0 < s_a < s_v < p_forg_min
          delta = (s_v - s_a) / 2
        """
        max_delta = (p_forg_min - e0) / 3.0
        if delta is None or delta <= 0 or delta >= max_delta:
            delta = max_delta

        s_a = e0 + delta
        s_v = p_forg_min - delta
        return s_a, s_v, delta

    @staticmethod
    def chernoff_forgery_bound(L: int, delta: float) -> float:
        """
        Calculates upper bound on probability of successful forgery:
        P_forge <= exp(-2 * delta^2 * L)
        """
        exponent = -2.0 * (delta ** 2) * L
        # Protect against underflow
        if exponent < -700:
            return 0.0
        return math.exp(exponent)

    @staticmethod
    def false_rejection_bound(L: int, delta: float) -> float:
        """
        Calculates upper bound on probability of an honest signature being falsely rejected (FRR):
        P_FRR <= exp(-2 * delta^2 * L)
        """
        exponent = -2.0 * (delta ** 2) * L
        if exponent < -700:
            return 0.0
        return math.exp(exponent)

    @staticmethod
    def repudiation_bound(L: int, s_a: float, s_v: float) -> float:
        """
        Calculates upper bound on dishonest signer repudiation probability:
        P_rep <= 2 * exp(-0.5 * (s_v - s_a)^2 * L)
        """
        gap = s_v - s_a
        exponent = -0.5 * (gap ** 2) * L
        if exponent < -700:
            return 0.0
        return min(1.0, 2.0 * math.exp(exponent))

    @staticmethod
    def standard_error(p: float, L: int) -> float:
        """
        Calculates standard error for a Bernoulli parameter p over sample size L:
        sigma = sqrt(p * (1 - p) / L)
        """
        if L <= 0:
            return 0.5
        p_clamped = max(0.0, min(1.0, p))
        return math.sqrt((p_clamped * (1.0 - p_clamped)) / L)

    @staticmethod
    def min_signature_length(
        target_epsilon: float = 1e-6,
        delta: float = 0.07,
        gap: Optional[float] = None
    ) -> int:
        """
        Calculates minimum signature length L required to achieve target security parameter epsilon
        against both forgery and dishonest signer repudiation:
        L_forge >= ln(1 / target_epsilon) / (2 * delta^2)
        L_rep   >= ln(2 / target_epsilon) / (0.5 * gap^2)
        L_min   = max(L_forge, L_rep)
        """
        if target_epsilon <= 0:
            raise ValueError("target_epsilon must be positive.")
        if delta <= 0:
            raise ValueError("delta must be positive.")
        
        effective_gap = gap if (gap is not None and gap > 0) else delta
        
        required_L_forge = math.ceil(math.log(1.0 / target_epsilon) / (2.0 * (delta ** 2)))
        required_L_rep = math.ceil(math.log(2.0 / target_epsilon) / (0.5 * (effective_gap ** 2)))
        
        return max(1, required_L_forge, required_L_rep)

    @classmethod
    def generate_security_certificate(
        cls,
        signature_length: int,
        channel_error_rate: float,
        mismatches: int,
        total_checked: int,
        p_forg_min: float = 0.25
    ) -> SecurityCertificate:
        """
        Generates a formal Information-Theoretic Security Certificate for a verified signature.
        """
        obs_rate = (mismatches / total_checked) if total_checked > 0 else 0.0
        s_a, s_v, delta = cls.compute_thresholds(e0=channel_error_rate, p_forg_min=p_forg_min)

        p_forge = cls.chernoff_forgery_bound(signature_length, delta)
        p_frr = cls.false_rejection_bound(signature_length, delta)
        p_rep = cls.repudiation_bound(signature_length, s_a, s_v)

        # Secure acceptance condition
        is_accepted = (obs_rate <= s_a)

        # Security level in equivalent cryptographic bits: -log2(P_forge)
        sec_bits = -math.log2(p_forge) if p_forge > 0 else 256.0

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
            security_level_bits=round(min(sec_bits, 256.0), 2)
        )
