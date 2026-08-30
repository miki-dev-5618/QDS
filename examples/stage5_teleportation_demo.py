"""
============================================================================
STAGE 5: TELEPORTATION-BASED QUANTUM DIGITAL SIGNATURE (QDS) DEMONSTRATION
============================================================================
Demonstrates:
1. Quantum Public Key Distribution via Bell Pairs (|Phi+>) & Quantum Teleportation.
2. Bell-State Measurement (BSM) & Classical Pauli feed-forward corrections (X^{m2} Z^{m1}).
3. Symmetrisation & Projective Measurement Verification.
4. Formal Information-Theoretic Security Bounds via Chernoff-Hoeffding inequalities.
"""

import sys
import os
import numpy as np

# Ensure src is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.protocols.teleportation_qds import TeleportationQDSProtocol
from quantum_sim.attacks.qds_threats import EveSignatureForgery, DishonestVerifierForgery
from quantum_sim.detection.engine import QDSDetectionEngine


def print_banner():
    print("=" * 85)
    print(" STAGE 5: TELEPORTATION-BASED QUANTUM DIGITAL SIGNATURE & SECURITY BOUNDS")
    print("=" * 85)
    print(" Protocol: Bell Entanglement -> Teleportation -> Pauli Corrections -> Chernoff Bounds\n")


def display_certificate(cert, title="SECURITY CERTIFICATE"):
    print("\n" + "-" * 85)
    print(f" [*] FORMAL INFORMATION-THEORETIC {title}")
    print("-" * 85)

    print(f" Signature Token Length (L)       : {cert.signature_length} qubits")
    print(f" Channel Baseline Noise (e0)      : {cert.channel_error_rate*100:.2f}%")
    print(f" Acceptance Threshold (sa)        : {cert.acceptance_threshold_sa*100:.2f}%")
    print(f" Verification Threshold (sv)      : {cert.verification_threshold_sv*100:.2f}%")
    print(f" Safety Margin (delta)            : {cert.safety_margin_delta:.4f}")
    print(f" Observed Mismatch Rate           : {cert.observed_mismatch_rate*100:.2f}%")
    print(f" Forgery Probability Bound (P_forg): {cert.forgery_probability_bound:.2e}")
    print(f" False Rejection Bound (P_FRR)    : {cert.false_rejection_probability_bound:.2e}")
    print(f" Repudiation Bound (P_rep)        : {cert.repudiation_probability_bound:.2e}")
    print(f" Equivalent Security Level        : {cert.security_level_bits:.1f} bits")
    print(f" Verification Status              : {'[ACCEPTED]' if cert.is_securely_accepted else '[REJECTED]'}")
    print("-" * 85 + "\n")


def run_authentic_teleportation_demo(n_bits=32, seed=42):
    print(">>> [TEST 1] AUTHENTIC TELEPORTATION-BASED SIGNATURE TRANSMISSION")
    print(f"    Generating {n_bits} signature tokens, Bell pairs, and teleportation circuits...")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    result = protocol.run(n_bits=n_bits, rng=rng)

    print(f" [OK] Teleportation distribution completed.")
    print(f"      - Bob received tokens: {result.bob_received_count}/{n_bits}")
    print(f"      - Charlie received tokens: {result.charlie_received_count}/{n_bits}")
    print(f"      - Sample Pauli BSM syndromes (m1, m2): {result.bob_teleportation_syndromes[:4]}...")

    sig_0 = result.alice_signatures[0]
    b_valid, b_mis, b_tot, b_cert = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mis, c_tot, c_cert = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='charlie')

    print(f"\n [VERIFICATION RESULT]")
    print(f"  Bob Verification     : Mismatches = {b_mis}/{b_tot} -> {'PASS' if b_valid else 'FAIL'}")
    print(f"  Charlie Verification : Mismatches = {c_mis}/{c_tot} -> {'PASS' if c_valid else 'FAIL'}")

    display_certificate(b_cert, title="BOB'S SECURITY CERTIFICATE")


def run_forgery_teleportation_demo(n_bits=32, seed=42):
    print(">>> [TEST 2] ADVERSARY SIGNATURE FORGERY ATTEMPT AGAINST TELEPORTED TOKENS")
    print(f"    Adversary attempts blind counterfeit signature without possessing teleported states...")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    result = protocol.run(n_bits=n_bits, rng=rng)

    forged_sig = EveSignatureForgery.generate_random_forgery(n_bits=n_bits, rng=rng)
    b_valid, b_mis, b_tot, b_cert = protocol.verify_signature(k=0, proposed_sig=forged_sig, recipient='bob')

    print(f"\n [VERIFICATION RESULT]")
    print(f"  Bob Verification : Mismatches = {b_mis}/{b_tot} ({b_mis/b_tot*100:.1f}%) -> {'PASS' if b_valid else 'REJECTED (ATTACK DETECTED)'}")

    display_certificate(b_cert, title="FORGERY DETECTION REPORT")


def main():
    print_banner()
    run_authentic_teleportation_demo(n_bits=32)
    print("\n" + "=" * 85 + "\n")
    run_forgery_teleportation_demo(n_bits=32)


if __name__ == "__main__":
    main()
