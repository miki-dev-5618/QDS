import numpy as np
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.channel.attacks import InterceptResendAttack
from quantum_sim.protocols.point_to_point import PointToPointProtocol


def test_protocol_ideal_channel():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    channel = QuantumChannel()
    protocol = PointToPointProtocol(alice, bob, channel, shots=1)
    
    result = protocol.run(n_bits=100, rng=rng)
    
    assert result.n_sent == 100
    assert result.n_sifted > 0
    assert result.qber == 0.0
    assert not result.eve_detected


def test_protocol_eavesdropped_channel():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    channel = QuantumChannel(attacks=[InterceptResendAttack(p_intercept=1.0)])
    protocol = PointToPointProtocol(alice, bob, channel, shots=1, qber_threshold=0.15)
    
    result = protocol.run(n_bits=400, sample_ratio=0.5, rng=rng)
    
    assert result.n_sent == 400
    assert result.n_sifted > 0
    assert 0.15 <= result.qber <= 0.35
    assert result.eve_detected

