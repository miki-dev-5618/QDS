import sys
from pathlib import Path

# Add src/ to sys.path so demo can be run directly
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import numpy as np
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.protocols.qds import QDSProtocol


def main():
    print("=" * 60)
    print("      STAGE 3 QUANTUM DIGITAL SIGNATURE (QDS) DEMO      ")
    print("=" * 60)

    # Initialize Alice (Sender), Bob (Receiver), and Charlie (Receiver)
    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    rng = np.random.default_rng(42)

    print("\n--- Running Stage 1 & 2: Quantum Signature State Distribution & Symmetrisation ---")
    ideal_channel = QuantumChannel()
    protocol = QDSProtocol(
        alice, bob, charlie, ideal_channel, shots=1, abort_threshold_pct=50.0
    )
    
    # Run the QDS protocol simulation with signature length N = 10
    result = protocol.run(n_bits=10, rng=rng)

    print(f"Signature Length (N)       : {result.n_bits} elements")
    print(f"Bob Keep/Forward Actions   : {result.bob_actions}")
    print(f"Charlie Keep/Forward Actions : {result.charlie_actions}")
    print(f"Bob Received Elements Count: {result.bob_received_count}")
    print(f"Charlie Received Elements   : {result.charlie_received_count}")
    print(f"Protocol Aborted (Bob)      : {result.bob_aborted}")
    print(f"Protocol Aborted (Charlie)  : {result.charlie_aborted}")

    # Inspect the first 3 elements of Bob's and Charlie's eliminated states
    print("\n--- Eliminated States Stored (First 3 elements) ---")
    for i in range(3):
        print(f"Position {i + 1} | Alice Original: {result.alice_signatures[0][i]}")
        print(f"           | Bob Eliminated: {result.bob_eliminated[i]}")
        print(f"           | Charlie Eliminated: {result.charlie_eliminated[i]}")

    print("\n--- Stage 3: Messaging and Verification Stage ---")
    # Alice signs message k = 0
    k_message = 0
    proposed_sig_correct = result.alice_signatures[k_message]
    print(f"Alice signs and transmits message {k_message} with its signature.")
    
    # Receivers verify the signature matching k = 0
    bob_valid, bob_mismatch, bob_checked = protocol.verify_message(
        k_message, proposed_sig_correct, recipient='bob'
    )
    charlie_valid, charlie_mismatch, charlie_checked = protocol.verify_message(
        k_message, proposed_sig_correct, recipient='charlie'
    )
    print(f"Bob Verification     : {'VALID' if bob_valid else 'INVALID'} ({bob_mismatch} mismatches in {bob_checked} checked positions)")
    print(f"Charlie Verification : {'VALID' if charlie_valid else 'INVALID'} ({charlie_mismatch} mismatches in {charlie_checked} checked positions)")

    # Test forgery detection (Alice signs message 0 but sends signature for message 1)
    k_message_wrong = 1
    proposed_sig_wrong = result.alice_signatures[k_message_wrong]
    print(f"\nAlice signs message 0 but tries to send signature for message 1 (Forgery Attempt).")

    bob_valid_w, bob_mismatch_w, bob_checked_w = protocol.verify_message(
        0, proposed_sig_wrong, recipient='bob'
    )
    charlie_valid_w, charlie_mismatch_w, charlie_checked_w = protocol.verify_message(
        0, proposed_sig_wrong, recipient='charlie'
    )
    print(f"Bob Verification     : {'VALID' if bob_valid_w else 'INVALID'} ({bob_mismatch_w} mismatches in {bob_checked_w} checked positions)")
    print(f"Charlie Verification : {'VALID' if charlie_valid_w else 'INVALID'} ({charlie_mismatch_w} mismatches in {charlie_checked_w} checked positions)")

    print("\n" + "=" * 60)
    print("                      DEMO COMPLETED                     ")
    print("=" * 60)


if __name__ == "__main__":
    main()
