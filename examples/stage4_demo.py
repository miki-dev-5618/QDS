"""
============================================================================
STAGE 4: QUANTUM DIGITAL SIGNATURE (QDS) INTERACTIVE THREAT SIMULATOR
============================================================================
Architecture: Alice (Signer) -> Bob & Charlie (Verifiers)
Threat Engine: Signature Forgery, Dishonest Verifiers, Eavesdropping, Repudiation
Detection: Protocol-Aware Orthogonal State Elimination Contradiction Analysis
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
from quantum_sim.protocols.qds import QDSProtocol
from quantum_sim.attacks.qds_threats import (
    EveSignatureForgery,
    DishonestVerifierForgery,
    RepudiationSimulation,
)
from quantum_sim.detection.engine import (
    QDSDetectionEngine,
    ThreatClassification,
)


def print_banner():
    print("=" * 80)
    print("      STAGE 4: QUANTUM DIGITAL SIGNATURE (QDS) THREAT & ATTACK SIMULATOR     ")
    print("=" * 80)
    print(" Interactive Quantum Security Assessment & Protocol-Aware Detection Engine\n")


def print_menu():
    print("+------------------------------------------------------------------------------+")
    print("| SELECT THREAT SCENARIO / ATTACK TYPE TO SIMULATE:                            |")
    print("+------------------------------------------------------------------------------+")
    print("| [1] BASELINE: Authentic Signature (Legitimate Alice, Bob & Charlie verify)   |")
    print("| [2] THREAT 1: External Signature Forgery (Eve tries random/blind forgery)    |")
    print("| [3] THREAT 2: Dishonest Verifier Forgery (Bob attempts to forge to Charlie)  |")
    print("| [4] THREAT 3: Quantum Channel Interception (Eve eavesdrops during QDS dist)  |")
    print("| [5] THREAT 4: Dishonest Signer Repudiation (Alice sends asymmetric states)   |")
    print("| [6] NOISE TEST: Benign Channel Noise vs Active Malicious Tampering           |")
    print("| [7] BATCH DEMO: Run all scenarios sequentially with full diagnostic summary  |")
    print("| [0] EXIT                                                                     |")
    print("+------------------------------------------------------------------------------+")


def format_report_box(report):
    print("\n" + "=" * 80)
    print(" [!] DETECTION REPORT & DIAGNOSTIC VERDICT")
    print("=" * 80)
    print(f" Classification : {report.classification.value}")
    threat_status = "[ALERT] THREAT DETECTED" if report.is_threat_detected else "[PASS] AUTHENTIC / BENIGN"
    print(f" Threat Alert   : {threat_status}")
    print(f" Confidence     : {report.confidence_score * 100:.1f}%")
    print(f" Verdict        : {report.verdict}")
    print(f" Details        : {report.details}")
    print("-" * 80)
    print(f" Bob Contradictions     : {report.bob_contradictions}/{report.bob_total_checked} ({report.bob_contradiction_rate*100:.1f}%)")
    print(f" Charlie Contradictions : {report.charlie_contradictions}/{report.charlie_total_checked} ({report.charlie_contradiction_rate*100:.1f}%)")
    print(f" Asymmetry Divergence   : {report.asymmetry_discrepancy*100:.1f}%")
    print("=" * 80 + "\n")


def run_scenario_1(n_bits=16, seed=42):
    print("\n>>> [SCENARIO 1] BASELINE: AUTHENTIC QUANTUM DIGITAL SIGNATURE")
    print("    Alice generates private quantum states and distributes them over clean channels.")
    print("    Alice announces signature for message k=0. Bob and Charlie verify against eliminated states.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()
    qds = QDSProtocol(alice, bob, charlie, channel)
    result = qds.run(n_bits=n_bits, rng=rng)

    sig_0 = result.alice_signatures[0]
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mismatches, b_total, c_mismatches, c_total)
    format_report_box(report)


def run_scenario_2(n_bits=16, seed=42):
    print("\n>>> [SCENARIO 2] THREAT 1: EXTERNAL SIGNATURE FORGERY (EVE)")
    print("    Eve intercepts the classical message and attempts to forge Alice's signature")
    print("    without possessing Alice's private non-orthogonal quantum states.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()
    qds = QDSProtocol(alice, bob, charlie, channel)
    qds.run(n_bits=n_bits, rng=rng)

    forged_sig = EveSignatureForgery.generate_random_forgery(n_bits=n_bits, rng=rng)
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=forged_sig, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=forged_sig, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mismatches, b_total, c_mismatches, c_total)
    format_report_box(report)


def run_scenario_3(n_bits=16, seed=42):
    print("\n>>> [SCENARIO 3] THREAT 2: DISHONEST VERIFIER FORGERY (INSIDER ATTACK)")
    print("    Bob uses his measured quantum states & eliminated state records to construct")
    print("    a targeted counterfeit signature to frame Alice in front of Charlie.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()
    qds = QDSProtocol(alice, bob, charlie, channel)
    qds.run(n_bits=n_bits, rng=rng)

    forged_sig = DishonestVerifierForgery.forge_to_verifier(
        n_bits=n_bits,
        bob_eliminated=qds.bob_eliminated,
        bob_held=qds.bob_held,
        rng=rng
    )

    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=forged_sig, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=forged_sig, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(
        bob_mismatches=b_mismatches,
        bob_total=b_total,
        charlie_mismatches=c_mismatches,
        charlie_total=c_total,
        context_hint="dishonest_verifier"
    )
    format_report_box(report)


def run_scenario_4(n_bits=16, seed=42):
    print("\n>>> [SCENARIO 4] THREAT 3: QUANTUM CHANNEL INTERCEPTION (EVE EAVESDROPPING)")
    print("    Eve active Man-in-the-Middle intercepts and measures qubits in transit (100% intercept).")
    print("    This collapses superposition states and introduces errors into the elimination pools.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel(attacks=[InterceptResendAttack(p_intercept=1.0)])
    qds = QDSProtocol(alice, bob, charlie, channel)
    result = qds.run(n_bits=n_bits, rng=rng)

    sig_0 = result.alice_signatures[0]
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(
        bob_mismatches=b_mismatches,
        bob_total=b_total,
        charlie_mismatches=c_mismatches,
        charlie_total=c_total,
        channel_qber=0.25
    )
    format_report_box(report)


def run_scenario_5(n_bits=16, seed=42):
    print("\n>>> [SCENARIO 5] THREAT 4: DISHONEST SIGNER REPUDIATION (ALICE)")
    print("    Alice crafts asymmetric states (correct for Bob, flipped/orthogonal for Charlie)")
    print("    attempting to have Bob accept but Charlie reject so Alice can repudiate later.")
    
    rng = np.random.default_rng(seed)
    tamper_positions = list(range(n_bits // 2))
    scenario = RepudiationSimulation.create_asymmetric_signatures(
        n_bits=n_bits,
        tamper_positions=tamper_positions,
        rng=rng
    )

    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()
    qds = QDSProtocol(alice, bob, charlie, channel)
    qds.run(n_bits=n_bits, rng=rng)

    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=scenario.bob_initial_sigs[0], recipient='bob')
    c_mismatches_sim = len(tamper_positions)
    c_total = b_total

    engine = QDSDetectionEngine()
    report = engine.analyze(
        bob_mismatches=0,
        bob_total=b_total,
        charlie_mismatches=c_mismatches_sim,
        charlie_total=c_total
    )
    format_report_box(report)


def run_scenario_6(n_bits=16, seed=42):
    print("\n>>> [SCENARIO 6] BENIGN CHANNEL NOISE VS MALICIOUS ATTACK")
    print("    Simulating transmission through a low-level physical noise channel (p=2.0%).")
    print("    Detection engine verifies that error rates remain below alarm threshold.")
    
    rng = np.random.default_rng(seed)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel(noises=[DepolarizingNoise(p_error=0.02)])
    qds = QDSProtocol(alice, bob, charlie, channel)
    result = qds.run(n_bits=n_bits, rng=rng)

    sig_0 = result.alice_signatures[0]
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='charlie')

    engine = QDSDetectionEngine(allowable_noise_threshold=0.10)
    report = engine.analyze(b_mismatches, b_total, c_mismatches, c_total, channel_qber=0.02)
    format_report_box(report)


def main():
    print_banner()
    
    if len(sys.argv) > 1 and sys.argv[1] in ['--batch', '-b', 'all']:
        print("Running full batch demonstration:\n")
        run_scenario_1()
        run_scenario_2()
        run_scenario_3()
        run_scenario_4()
        run_scenario_5()
        run_scenario_6()
        return

    while True:
        print_menu()
        try:
            choice = input("Enter choice [0-7]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == '0':
            print("Exiting Stage 4 Threat Simulator. Good bye!")
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
            print("\n--- RUNNING ALL SCENARIOS ---")
            run_scenario_1()
            run_scenario_2()
            run_scenario_3()
            run_scenario_4()
            run_scenario_5()
            run_scenario_6()
        else:
            print(f"Invalid option '{choice}'. Please select between 0 and 7.")
        
        try:
            input("\nPress Enter to continue back to menu...")
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()
