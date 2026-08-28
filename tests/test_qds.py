import numpy as np
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.protocols.qds import QDSProtocol


def test_qds_protocol_ideal():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    channel = QuantumChannel()
    
    protocol = QDSProtocol(alice, bob, charlie, channel, shots=1, abort_threshold_pct=40.0)
    result = protocol.run(n_bits=8, rng=rng)
    
    assert result.n_bits == 8
    assert not result.bob_aborted
    assert not result.charlie_aborted
    
    # Alice proposes the correct signature for message 0
    correct_sig = result.alice_signatures[0]
    
    # Bob verifies it
    bob_valid, bob_mismatch, bob_checked = protocol.verify_message(0, correct_sig, recipient='bob')
    assert bob_valid
    assert bob_mismatch == 0
    assert bob_checked > 0

    # Charlie verifies it
    charlie_valid, charlie_mismatch, charlie_checked = protocol.verify_message(0, correct_sig, recipient='charlie')
    assert charlie_valid
    assert charlie_mismatch == 0
    assert charlie_checked > 0

    # Now verify with incorrect message signature (k=1)
    incorrect_sig = result.alice_signatures[1]
    
    # With 8 states and random distribution, checking mismatch rate for a wrong signature
    # will likely yield mismatch count > 0 (probability of matching 4 orthogonal states is very low)
    _, bob_mismatch_wrong, _ = protocol.verify_message(0, incorrect_sig, recipient='bob')
    # Since incorrect_sig is random with respect to k=0 signature, it has a high chance of mismatch
    # In noise-free environments, even a single mismatch validates it as forged.
