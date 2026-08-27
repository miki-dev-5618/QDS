import sys
from pathlib import Path

# Add src/ to sys.path so demo can be run directly
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import numpy as np
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.channel.noise import BitFlipNoise
from quantum_sim.channel.attacks import InterceptResendAttack
from quantum_sim.protocols.secure_point_to_point import SecurePointToPointProtocol


def main():
    print("=" * 70)
    print("      STAGE 2 SECURE QUANTUM COMMUNICATION SIMULATOR DEMO      ")
    print("=" * 70)

    alice = Node("Alice")
    bob = Node("Bob")
    rng = np.random.default_rng(12345)

    print("\n--- Scenario 1: Clean Channel (No Noise, No Eavesdropper) ---")
    clean_channel = QuantumChannel()
    clean_protocol = SecurePointToPointProtocol(alice, bob, clean_channel)
    res_clean = clean_protocol.run(n_bits=200, sample_ratio=0.5, rng=rng)

    print(f"Total Qubits Transmitted: {res_clean.n_sent}")
    print(f"Sifted Key Length       : {res_clean.n_sifted} bits")
    print(f"Estimated QBER          : {res_clean.qber * 100:.2f}%")
    print(f"Errors Corrected        : {res_clean.errors_corrected}")
    print(f"Agreement on Final Key  : {np.array_equal(res_clean.final_key_alice, res_clean.final_key_bob)}")
    print(f"Final Key Length        : {len(res_clean.final_key_alice)} bits")
    print(f"Final Key (First 15)    : {res_clean.final_key_alice[:15]}")

    print("\n--- Scenario 2: Noisy Channel (3% BitFlip Noise, No Eavesdropper) ---")
    # 3% BitFlip noise
    noisy_channel = QuantumChannel(noises=[BitFlipNoise(p_error=0.03)])
    noisy_protocol = SecurePointToPointProtocol(alice, bob, noisy_channel, reconciliation_block_size=8)
    res_noisy = noisy_protocol.run(n_bits=300, sample_ratio=0.5, rng=rng)

    print(f"Total Qubits Transmitted: {res_noisy.n_sent}")
    print(f"Sifted Key Length       : {res_noisy.n_sifted} bits")
    print(f"Estimated QBER          : {res_noisy.qber * 100:.2f}%")
    print(f"Errors Corrected        : {res_noisy.errors_corrected}")
    print(f"Agreement on Final Key  : {np.array_equal(res_noisy.final_key_alice, res_noisy.final_key_bob)}")
    print(f"Final Key Length        : {len(res_clean.final_key_alice)} bits")
    print(f"Final Key (First 15)    : {res_noisy.final_key_alice[:15]}")

    print("\n--- Scenario 3: Eavesdropped Noisy Channel (3% Noise + Eavesdropper) ---")
    attack = InterceptResendAttack(p_intercept=1.0)
    eavesdropped_channel = QuantumChannel(noises=[BitFlipNoise(p_error=0.03)], attacks=[attack])
    eavesdropped_protocol = SecurePointToPointProtocol(
        alice, bob, eavesdropped_channel, qber_threshold=0.15, reconciliation_block_size=8
    )
    res_attack = eavesdropped_protocol.run(n_bits=300, sample_ratio=0.5, rng=rng)

    print(f"Total Qubits Transmitted: {res_attack.n_sent}")
    print(f"Sifted Key Length       : {res_attack.n_sifted} bits")
    print(f"Estimated QBER          : {res_attack.qber * 100:.2f}%")
    print(f"Errors Corrected        : {res_attack.errors_corrected}")
    print(f"Eve Detected Status     : {res_attack.eve_detected}")
    print(f"Agreement on Final Key  : {np.array_equal(res_attack.final_key_alice, res_attack.final_key_bob)}")

    print("\n" + "=" * 70)
    print("                           DEMO COMPLETED                        ")
    print("=" * 70)


if __name__ == "__main__":
    main()
