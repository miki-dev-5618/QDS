import numpy as np
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.channel.noise import BitFlipNoise, DepolarizingNoise
from quantum_sim.channel.attacks import InterceptResendAttack
from quantum_sim.protocols.secure_point_to_point import SecurePointToPointProtocol
from quantum_sim.utils.post_processing import reconcile_keys, amplify_privacy


def test_noise_models():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    circuit = alice.prepare_bb84_transmission(20, rng=rng)
    
    noise = BitFlipNoise(p_error=1.0) # Always flip
    noisy_circuit = noise.apply(circuit, rng=rng)
    assert noisy_circuit.num_qubits == 20


def test_reconciliation():
    # Setup two bit strings with 2 mismatches in different blocks of size 8
    alice_bits = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 0, 1])
    bob_bits   = np.array([0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1]) # Errors at index 3 and 14
    
    corrected_bob, errors_corrected = reconcile_keys(alice_bits, bob_bits, block_size=8)
    assert np.array_equal(alice_bits, corrected_bob)
    assert errors_corrected == 2


def test_privacy_amplification():
    rng = np.random.default_rng(42)
    bits = np.array([1, 0, 1, 1, 0, 1, 1, 0, 0, 1] * 5) # 50 bits
    qber = 0.1
    
    amplified = amplify_privacy(bits, qber, rng=rng)
    assert len(amplified) < len(bits)
    assert len(amplified) == int(np.floor(50 * (1.0 - 2.5 * qber))) # 50 * 0.75 = 37 bits


def test_secure_protocol_clean_channel():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    channel = QuantumChannel() # No noise, no attacks
    
    protocol = SecurePointToPointProtocol(alice, bob, channel, shots=1, qber_threshold=0.15)
    result = protocol.run(n_bits=100, rng=rng)
    
    assert result.n_sent == 100
    assert result.qber == 0.0
    assert np.array_equal(result.final_key_alice, result.final_key_bob)
    assert not result.eve_detected


def test_secure_protocol_noisy_channel():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    
    channel = QuantumChannel(noises=[BitFlipNoise(p_error=0.03)])
    protocol = SecurePointToPointProtocol(alice, bob, channel, shots=1, qber_threshold=0.15)
    
    result = protocol.run(n_bits=500, rng=rng)

    
    # QBER should be positive due to noise
    assert result.qber > 0.0

    # Bob's corrected bits should match Alice's
    assert np.array_equal(result.reconciled_bits_alice, result.reconciled_bits_bob)
    # Final amplified keys should match
    assert np.array_equal(result.final_key_alice, result.final_key_bob)
