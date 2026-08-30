import pytest
import math
from quantum_sim.utils.security_analysis import QDSSecurityBounds, SecurityCertificate


def test_compute_thresholds_validity():
    e0 = 0.02
    p_forg_min = 0.25
    s_a, s_v, delta = QDSSecurityBounds.compute_thresholds(e0=e0, p_forg_min=p_forg_min)

    # Basic ordering constraints
    assert e0 < s_a < s_v < p_forg_min
    assert delta > 0
    assert math.isclose(s_a + 2 * delta, s_v, rel_tol=1e-5) or s_a < s_v


def test_chernoff_forgery_bound_monotonicity():
    delta = 0.07
    L_small = 32
    L_large = 128

    p_small = QDSSecurityBounds.chernoff_forgery_bound(L=L_small, delta=delta)
    p_large = QDSSecurityBounds.chernoff_forgery_bound(L=L_large, delta=delta)

    assert 0.0 <= p_small <= 1.0
    assert 0.0 <= p_large <= 1.0
    assert p_large < p_small


def test_min_signature_length():
    eps1 = 1e-3
    eps2 = 1e-6
    delta = 0.07

    l1 = QDSSecurityBounds.min_signature_length(target_epsilon=eps1, delta=delta)
    l2 = QDSSecurityBounds.min_signature_length(target_epsilon=eps2, delta=delta)

    assert l1 > 0
    assert l2 > l1


def test_security_certificate_generation():
    cert = QDSSecurityBounds.generate_security_certificate(
        signature_length=64,
        channel_error_rate=0.02,
        mismatches=0,
        total_checked=64
    )

    assert isinstance(cert, SecurityCertificate)
    assert cert.is_securely_accepted is True
    assert cert.observed_mismatch_rate == 0.0
    assert cert.forgery_probability_bound < 1.0
    assert cert.security_level_bits > 0
