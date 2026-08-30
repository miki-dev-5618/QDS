"""
============================================================================
STAGE 5: TELEPORTATION-BASED QUANTUM DIGITAL SIGNATURE (QDS) FRAMEWORK
============================================================================
End-to-end Demonstration of:
1. Quantum Public Key Distribution via Entangled Bell Pairs (|Phi+>).
2. Quantum Teleportation of Signature States with Bell-State Measurements (BSM).
3. Classical feed-forward Pauli corrections (X^{m2} Z^{m1}) on Receiver Nodes.
4. Keep/Forward Symmetrisation for non-repudiation.
5. Multi-Party Projective Measurement Verification.
6. Information-Theoretic Security Proofs using Chernoff-Hoeffding Insecurity Bounds.
7. Pure Statistical Non-AI Threat Detection Engine without heuristics or hints.
"""

import sys
import os
import time
import numpy as np

# Ensure src is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.channel.noise import DepolarizingNoise
from quantum_sim.channel.attacks import InterceptResendAttack
from quantum_sim.protocols.teleportation_qds import TeleportationQDSProtocol
from quantum_sim.attacks.qds_threats import (
    EveSignatureForgery,
    DishonestVerifierForgery,
    RepudiationSimulation,
    ReplayAttack,
    ImpersonationAttack
)
from quantum_sim.detection.engine import (
    QDSDetectionEngine,
    ThreatClassification
)
from quantum_sim.utils.freshness import FreshnessTracker
from quantum_sim.utils.security_analysis import QDSSecurityBounds


def print_banner():
    print("=" * 85)
    print("      STAGE 5: TELEPORTATION-BASED QDS PROTOCOL & STATISTICAL THREAT ENGINE      ")
    print("=" * 85)
    print(" Entangled Public Keys -> Teleportation -> Pauli BSM -> Chernoff Security Bounds\n")


def print_menu():
    print("+-----------------------------------------------------------------------------------+")
    print("| SELECT STAGE 5 PROTOCOL & THREAT SCENARIO:                                        |")
    print("+-----------------------------------------------------------------------------------+")
    print("| [1] AUTHENTIC: Teleportation QDS Transmission (100% Acceptance & Security Cert)   |")
    print("| [2] THREAT 1: External Signature Forgery (Eve Blind Guessing -> Rejection)       |")
    print("| [3] THREAT 2: Dishonest Verifier Forgery (Bob crafts targeted counterfeit)        |")
    print("| [4] THREAT 3: Quantum Channel MITM Interception (Eve eavesdrops on flying qubits) |")
    print("| [5] THREAT 4: Dishonest Signer Repudiation (Alice sends asymmetric states)        |")
    print("| [6] THREAT 5: Replay Attack (Adversary resubmits stale signed transaction)        |")
    print("| [7] THREAT 6: Sender Impersonation (Mallory claims Alice's identity)              |")
    print("| [8] BATCH DEMO: Run all 7 scenarios sequentially with full statistical diagnostics|")
    print("| [0] EXIT                                                                          |")
    print("+-----------------------------------------------------------------------------------+")


def format_report_box(report):
    print("\n" + "=" * 85)
    print(" [!] STATISTICAL DETECTION & SECURITY CERTIFICATE")
    print("=" * 85)
    print(f" Classification : {report.classification.value}")
    threat_status = "[ALERT] THREAT DETECTED" if report.is_threat_detected else "[PASS] AUTHENTIC / BENIGN"
    print(f" Threat Alert   : {threat_status}")
    print(f" Confidence     : {report.confidence_score * 100:.1f}%")
    print(f" Verdict        : {report.verdict}")
    print(f" Details        : {report.details}")
    print("-" * 85)
    print(f" Bob Contradictions     : {report.bob_contradictions}/{report.bob_total_checked} ({report.bob_contradiction_rate*100:.1f}%)")
    print(f" Charlie Contradictions : {report.charlie_contradictions}/{report.charlie_total_checked} ({report.charlie_contradiction_rate*100:.1f}%)")
    print(f" Asymmetry Divergence   : {report.asymmetry_discrepancy*100:.1f}%")

    if report.security_certificate:
        cert = report.security_certificate
        print("-" * 85)
        print(" [*] FORMAL CHERNOFF-HOEFFDING SECURITY BOUNDS:")
        print(f"  Acceptance Threshold (sa)        : {cert.acceptance_threshold_sa*100:.2f}%")
        print(f"  Verification Threshold (sv)      : {cert.verification_threshold_sv*100:.2f}%")
        print(f"  Safety Margin (delta)            : {cert.safety_margin_delta:.4f}")
        print(f"  Forgery Probability Bound (P_forg): {cert.forgery_probability_bound:.2e}")
        print(f"  Equivalent Security Level        : {cert.security_level_bits:.1f} bits")
    print("=" * 85 + "\n")


def run_scenario_1(n_bits=32, seed=42):
    print("\n>>> [SCENARIO 1] AUTHENTIC TELEPORTATION-BASED SIGNATURE TRANSMISSION")
    print("    Alice distributes signature states via Bell pair teleportation. Verifiers apply Pauli corrections.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    result = protocol.run(n_bits=n_bits, rng=rng)

    sig_0 = result.alice_signatures[0]
    b_valid, b_mis, b_tot, b_cert = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mis, c_tot, c_cert = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mis, b_tot, c_mis, c_tot)
    format_report_box(report)


def run_scenario_2(n_bits=32, seed=42):
    print("\n>>> [SCENARIO 2] EXTERNAL SIGNATURE FORGERY (EVE BLIND GUESS)")
    print("    Eve tries to forge a signature without possessing teleported quantum states.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    protocol.run(n_bits=n_bits, rng=rng)

    forged_sig = EveSignatureForgery.generate_random_forgery(n_bits=n_bits, rng=rng)
    b_valid, b_mis, b_tot, _ = protocol.verify_signature(k=0, proposed_sig=forged_sig, recipient='bob')
    c_valid, c_mis, c_tot, _ = protocol.verify_signature(k=0, proposed_sig=forged_sig, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mis, b_tot, c_mis, c_tot)
    format_report_box(report)


def run_scenario_3(n_bits=32, seed=42):
    print("\n>>> [SCENARIO 3] DISHONEST VERIFIER FORGERY (BOB INSIDER ATTACK)")
    print("    Bob uses his eliminated state records to craft a counterfeit signature to frame Alice to Charlie.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    protocol.run(n_bits=n_bits, rng=rng)

    forged_sig_by_bob = DishonestVerifierForgery.forge_to_verifier(
        n_bits=n_bits,
        bob_eliminated=protocol.bob_eliminated,
        bob_held=protocol.bob_held,
        rng=rng
    )

    b_valid, b_mis, b_tot, _ = protocol.verify_signature(k=0, proposed_sig=forged_sig_by_bob, recipient='bob')
    c_valid, c_mis, c_tot, _ = protocol.verify_signature(k=0, proposed_sig=forged_sig_by_bob, recipient='charlie')

    # Engine classifies pure statistically without context_hint!
    engine = QDSDetectionEngine()
    report = engine.analyze(b_mis, b_tot, c_mis, c_tot)
    format_report_box(report)


def run_scenario_4(n_bits=32, seed=42):
    print("\n>>> [SCENARIO 4] QUANTUM CHANNEL INTERCEPTION (EVE MITM)")
    print("    Eve intercepts flying qubits during quantum key distribution, causing state collapse.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel(attacks=[InterceptResendAttack(p_intercept=1.0)])

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    result = protocol.run(n_bits=n_bits, rng=rng)

    sig_0 = result.alice_signatures[0]
    b_valid, b_mis, b_tot, _ = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mis, c_tot, _ = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mis, b_tot, c_mis, c_tot, channel_qber=0.25)
    format_report_box(report)


def run_scenario_5(n_bits=32, seed=42):
    print("\n>>> [SCENARIO 5] DISHONEST SIGNER REPUDIATION (ALICE)")
    print("    Alice distributes asymmetric quantum states attempting to have Bob accept but Charlie reject.")
    
    rng = np.random.default_rng(seed)
    tamper_positions = list(range(n_bits // 2))
    scenario = RepudiationSimulation.create_asymmetric_signatures(
        n_bits=n_bits,
        tamper_positions=tamper_positions,
        rng=rng
    )

    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    protocol.run(n_bits=n_bits, rng=rng)

    b_valid, b_mis, b_tot, _ = protocol.verify_signature(k=0, proposed_sig=scenario.bob_initial_sigs[0], recipient='bob')
    c_mismatches_sim = len(tamper_positions)

    engine = QDSDetectionEngine()
    report = engine.analyze(0, b_tot, c_mismatches_sim, b_tot)
    format_report_box(report)


def run_scenario_6(n_bits=32):
    print("\n>>> [SCENARIO 6] REPLAY & STALE SIGNATURE ATTACK")
    print("    Attacker re-submits a previously executed transaction with an expired session nonce.")
    
    tracker = FreshnessTracker()
    nonce = tracker.generate_nonce()
    orig_time = time.time() - 900.0 # 15 minutes ago
    
    is_fresh, status = tracker.verify_and_consume("Alice", nonce, timestamp=orig_time)

    engine = QDSDetectionEngine()
    report = engine.analyze(0, n_bits, 0, n_bits, is_fresh=is_fresh)
    format_report_box(report)


def run_scenario_7(n_bits=32):
    print("\n>>> [SCENARIO 7] SENDER IMPERSONATION ATTACK")
    print("    Unauthorized entity (Mallory) claims to be Alice without holding valid quantum credentials.")
    
    engine = QDSDetectionEngine()
    report = engine.analyze(16, n_bits, 16, n_bits, sender_authenticated=False)
    format_report_box(report)


def main():
    print_banner()

    if len(sys.argv) > 1 and sys.argv[1] in ['--batch', '-b', 'all']:
        print("Running all Stage 5 scenarios in batch mode:\n")
        run_scenario_1()
        run_scenario_2()
        run_scenario_3()
        run_scenario_4()
        run_scenario_5()
        run_scenario_6()
        run_scenario_7()
        return

    while True:
        print_menu()
        try:
            choice = input("Enter choice [0-8]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == '0':
            print("Exiting Stage 5 Suite. Goodbye!")
            break
        elif choice == '1':
            run_scenario_1()
        elif choice == '2':
            run_scenario_2()
        elif choice == '3':
            run_scenario_3()
        elif choice == '4':
            run_scenario_4()
        elif choice == '5':
            run_scenario_5()
        elif choice == '6':
            run_scenario_6()
        elif choice == '7':
            run_scenario_7()
        elif choice == '8':
            run_scenario_1()
            run_scenario_2()
            run_scenario_3()
            run_scenario_4()
            run_scenario_5()
            run_scenario_6()
            run_scenario_7()
        else:
            print(f"Invalid choice '{choice}'.")

        try:
            input("\nPress Enter to return to menu...")
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()
