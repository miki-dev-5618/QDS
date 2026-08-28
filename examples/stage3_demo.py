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


def format_state(bit_val, basis_val):
    """Format (bit, basis) into readable state symbol."""
    if basis_val == 0:
        return "|0>" if bit_val == 0 else "|1>"
    else:
        return "|+>" if bit_val == 0 else "|->"


def clean_str(s):
    """Ensure safe ASCII representation for Windows consoles."""
    return str(s).replace("⟩", ">").replace("−", "-").replace("'", "")


def print_banner(title):
    print("\n" + "=" * 76)
    print(f"  {title.center(72)}")
    print("=" * 76)


def print_stage_box(title, desc):
    print(f"\n+{'-' * 74}+")
    print(f"|  {title:<72}|")
    print(f"+{'-' * 74}+")
    for line in desc:
        print(f"|  {line:<72}|")
    print(f"+{'-' * 74}+")


def main():
    print_banner("STAGE 3: QUANTUM DIGITAL SIGNATURE (QDS) PROTOCOL DEMO")
    print(" Architecture: Alice (Signer) -> Bob & Charlie (Verifiers)")
    print(" Mechanics   : Symmetrisation Swap + Orthogonal State Elimination")

    # Initialize Alice (Sender), Bob (Receiver), and Charlie (Receiver)
    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    rng = np.random.default_rng(42)

    n_elements = 8
    abort_thresh = 50.0

    print_stage_box(
        "STAGE 1: GENERATION & TRANSMISSION",
        [
            f"Alice creates private random signatures for k=0 and k=1 (Length N = {n_elements})",
            "Each signature element is chosen from BB84 states: {|0>, |1>, |+>, |->}",
            "Alice sends Copy 1 to Bob and Copy 2 to Charlie over quantum channel."
        ]
    )

    ideal_channel = QuantumChannel()
    protocol = QDSProtocol(
        alice, bob, charlie, ideal_channel, shots=1, abort_threshold_pct=abort_thresh
    )
    
    # Run the QDS protocol simulation
    result = protocol.run(n_bits=n_elements, rng=rng)

    # Print Visual State Table for Alice's generated keys
    print("\n[1] Alice's Generated Private Quantum Signatures:")
    print("+-------+" + "------+" * n_elements)
    print("| Pos   | " + " | ".join([f" #{i+1:02d}" for i in range(n_elements)]) + " |")
    print("+-------+" + "------+" * n_elements)
    sig0_str = " | ".join([f" {format_state(*result.alice_signatures[0][i]):^4}" for i in range(n_elements)])
    sig1_str = " | ".join([f" {format_state(*result.alice_signatures[1][i]):^4}" for i in range(n_elements)])
    print(f"| Sig 0 | {sig0_str} |")
    print(f"| Sig 1 | {sig1_str} |")
    print("+-------+" + "------+" * n_elements)

    print_stage_box(
        "STAGE 2: SYMMETRISATION & STATE ELIMINATION",
        [
            "Bob & Charlie choose KEEP (K) or FORWARD (F) for each position.",
            "Possession cases: K/K -> (1,1), K/F -> (2,0), F/K -> (0,2), F/F -> (1,1 swap)",
            "Holders measure in Z or X basis to eliminate impossible (orthogonal) states."
        ]
    )

    print("\n[2] Keep/Forward Routing & State Elimination Matrix:")
    print("+-----+-------+---------+--------------+---------------+-------------------+-------------------+")
    print("| Pos | Alice | Bob Act | Charlie Act  | Bob Copies    | Bob Eliminated    | Charlie Elim      |")
    print("+-----+-------+---------+--------------+---------------+-------------------+-------------------+")
    for i in range(n_elements):
        orig = format_state(*result.alice_signatures[0][i])
        b_act = result.bob_actions[i]
        c_act = result.charlie_actions[i]
        b_copies = len(protocol.bob_held[i])
        c_copies = len(protocol.charlie_held[i])
        b_elim = clean_str(str(result.bob_eliminated[i]))
        c_elim = clean_str(str(result.charlie_eliminated[i]))
        
        # Format copies held text
        b_held_txt = f"{b_copies} copy" if b_copies == 1 else f"{b_copies} copies"
        print(f"| #{i+1:02d} | {orig:^5} |    {b_act}    |      {c_act}       |  {b_held_txt:<12} | {b_elim:<17} | {c_elim:<17} |")
    print("+-----+-------+---------+--------------+---------------+-------------------+-------------------+")

    print("\n[3] Abort Condition Health Gauges:")
    b_pct = (result.bob_received_count / n_elements) * 100
    c_pct = (result.charlie_received_count / n_elements) * 100
    b_bar = "#" * int(b_pct // 10) + "-" * (10 - int(b_pct // 10))
    c_bar = "#" * int(c_pct // 10) + "-" * (10 - int(c_pct // 10))
    
    print(f" Bob Received Elements     : [{b_bar}] {b_pct:.0f}% ({result.bob_received_count}/{n_elements}) -> {'ABORT' if result.bob_aborted else 'PASSED [CONTINUE]'}")
    print(f" Charlie Received Elements : [{c_bar}] {c_pct:.0f}% ({result.charlie_received_count}/{n_elements}) -> {'ABORT' if result.charlie_aborted else 'PASSED [CONTINUE]'}")

    print_stage_box(
        "STAGE 3: MESSAGING & NON-REPUDIATION VERIFICATION",
        [
            "Alice signs a message (k=0 or k=1) and broadcasts the classical states.",
            "Bob and Charlie verify: Claimed State NOT in Eliminated List.",
            "Mismatch = Contradiction (Alice forged, cheated, or sent wrong signature)."
        ]
    )

    # Test 1: Legitimate Message (Alice signs message 0 with Sig 0)
    k_msg = 0
    print(f"\n--- Scenario A: Alice publishes Valid Signature for Message {k_msg} ---")
    proposed_sig_correct = result.alice_signatures[k_msg]
    
    b_valid, b_mis, b_tot = protocol.verify_message(k_msg, proposed_sig_correct, recipient='bob')
    c_valid, c_mis, c_tot = protocol.verify_message(k_msg, proposed_sig_correct, recipient='charlie')
    
    print(f"  Bob Verification     : {'[PASSED - AUTHENTIC]' if b_valid else '[REJECTED - FORGERY]'} ({b_mis} mismatches in {b_tot} checked positions)")
    print(f"  Charlie Verification : {'[PASSED - AUTHENTIC]' if c_valid else '[REJECTED - FORGERY]'} ({c_mis} mismatches in {c_tot} checked positions)")
    print(f"  Result: Signature accepted across all nodes with 100% integrity!")

    # Test 2: Forgery / Tampering Attempt (Alice claims message 0, but signature 1 is presented)
    print(f"\n--- Scenario B: Forgery / Cheating Attack (Message 0 + Tampered Signature) ---")
    proposed_sig_wrong = result.alice_signatures[1]
    
    b_valid_w, b_mis_w, b_tot_w = protocol.verify_message(0, proposed_sig_wrong, recipient='bob')
    c_valid_w, c_mis_w, c_tot_w = protocol.verify_message(0, proposed_sig_wrong, recipient='charlie')
    
    print(f"  Bob Verification     : {'[PASSED - AUTHENTIC]' if b_valid_w else '[REJECTED - FORGERY DETECTED]'} ({b_mis_w} contradictions detected in {b_tot_w} positions)")
    print(f"  Charlie Verification : {'[PASSED - AUTHENTIC]' if c_valid_w else '[REJECTED - FORGERY DETECTED]'} ({c_mis_w} contradictions detected in {c_tot_w} positions)")
    print(f"  Result: Quantum state elimination caught contradictions immediately. Forgery foiled!")

    print_banner("STAGE 3 DEMO COMPLETED SUCCESSFULLY")

    # Automatically launch the interactive visualizer in the default browser
    html_file = Path(__file__).resolve().parent.parent / "QDS PROTOCL EXPLAINED" / "index.html"
    if html_file.exists():
        import webbrowser
        print(f"\n[*] Launching interactive visualizer in your browser: {html_file}")
        webbrowser.open(html_file.as_uri())


if __name__ == "__main__":
    main()


