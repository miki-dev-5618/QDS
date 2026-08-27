import sys
from pathlib import Path

# Add src/ to sys.path so demo can be run directly
src_path = Path(__file__).resolve().parent.parent / "src"
if str(str(src_path)) not in sys.path:
    sys.path.insert(0, str(src_path))

import numpy as np
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.channel.attacks import InterceptResendAttack
from quantum_sim.protocols.point_to_point import PointToPointProtocol


def main():
    print("=" * 60)
    print("      STAGE 1 QUANTUM COMMUNICATION SIMULATOR DEMO      ")
    print("=" * 60)

    alice = Node("Alice")
    bob = Node("Bob")
    rng = np.random.default_rng(12345)

    print("\n--- Scenario 1: Ideal Channel (No Eavesdropper) ---")
    ideal_channel = QuantumChannel()
    ideal_protocol = PointToPointProtocol(alice, bob, ideal_channel, batch_size=20)
    res_ideal = ideal_protocol.run(n_bits=200, sample_ratio=0.5, rng=rng)

    print(f"Total Qubits Transmitted: {res_ideal.n_sent}")
    print(f"Sifted Key Length       : {res_ideal.n_sifted} bits")
    print(f"Estimated QBER          : {res_ideal.qber * 100:.2f}%")
    print(f"Eve Detected Status     : {res_ideal.eve_detected}")
    print(f"Alice Sifted Bits (First 15): {res_ideal.sifted_bits_alice[:15]}")
    print(f"Bob Sifted Bits   (First 15): {res_ideal.sifted_bits_bob[:15]}")

    print("\n--- Scenario 2: Intercept-Resend Attack (Full Eavesdropping) ---")
    attack = InterceptResendAttack(p_intercept=1.0)
    eavesdropped_channel = QuantumChannel(attacks=[attack])
    eavesdropped_protocol = PointToPointProtocol(
        alice, bob, eavesdropped_channel, qber_threshold=0.15, batch_size=20
    )
    res_attack = eavesdropped_protocol.run(n_bits=200, sample_ratio=0.5, rng=rng)

    print(f"Total Qubits Transmitted: {res_attack.n_sent}")
    print(f"Sifted Key Length       : {res_attack.n_sifted} bits")
    print(f"Estimated QBER          : {res_attack.qber * 100:.2f}%")
    print(f"Eve Detected Status     : {res_attack.eve_detected}")
    print(f"Alice Sifted Bits (First 15): {res_attack.sifted_bits_alice[:15]}")
    print(f"Bob Sifted Bits   (First 15): {res_attack.sifted_bits_bob[:15]}")

    print("\n" + "=" * 60)
    print("                      DEMO COMPLETED                     ")
    print("=" * 60)


if __name__ == "__main__":
    main()
