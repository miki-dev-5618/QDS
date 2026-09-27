import pytest
import numpy as np
from qiskit_aer import AerSimulator

from quantum_sim.core.circuit import (
    create_bell_pair,
    build_teleportation_step_circuit
)
from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.protocols.teleportation_qds import (
    TeleportationQDSProtocol,
    TeleportationQDSResult
)
from quantum_sim.attacks.qds_threats import EveSignatureForgery


def test_teleportation_step_fidelity_z_basis():
    """Verify that teleporting |0> and |1> states preserves values deterministically under ideal circuit."""
    backend = AerSimulator()
    rng = np.random.default_rng(42)

    # Teleport |0> and measure in Z basis (0)
    qc_0 = build_teleportation_step_circuit(state_bit=0, state_basis=0, measure_basis=0)
    res_0 = backend.run(qc_0, shots=50).result().get_counts()
    for bitstring in res_0:
        clean = bitstring.replace(" ", "")
        assert clean[0] == '0' # Receiver measurement must be 0

    # Teleport |1> and measure in Z basis (0)
    qc_1 = build_teleportation_step_circuit(state_bit=1, state_basis=0, measure_basis=0)
    res_1 = backend.run(qc_1, shots=50).result().get_counts()
    for bitstring in res_1:
        clean = bitstring.replace(" ", "")
        assert clean[0] == '1' # Receiver measurement must be 1


def test_teleportation_qds_protocol_authentic_acceptance():
    """Verify end-to-end Teleportation QDS protocol accepts authentic signatures with 0 mismatches."""
    rng = np.random.default_rng(123)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    result = protocol.run(n_bits=16, rng=rng)

    assert isinstance(result, TeleportationQDSResult)
    assert not result.bob_aborted
    assert not result.charlie_aborted

    # Verify authentic signature
    sig_0 = result.alice_signatures[0]
    b_valid, b_mis, b_tot, b_cert = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mis, c_tot, c_cert = protocol.verify_signature(k=0, proposed_sig=sig_0, recipient='charlie')

    assert b_valid is True
    assert b_mis == 0
    assert c_valid is True
    assert c_mis == 0
    assert b_cert.is_securely_accepted is True


def test_teleportation_qds_detects_random_forgery():
    """Verify that an external forged signature causes high contradiction rates and rejection."""
    rng = np.random.default_rng(999)
    alice, bob, charlie = Node("Alice"), Node("Bob"), Node("Charlie")
    channel = QuantumChannel()

    protocol = TeleportationQDSProtocol(alice, bob, charlie, channel)
    result = protocol.run(n_bits=24, rng=rng)

    forged_sig = EveSignatureForgery.generate_random_forgery(n_bits=24, rng=rng)
    b_valid, b_mis, b_tot, b_cert = protocol.verify_signature(k=0, proposed_sig=forged_sig, recipient='bob')

    assert b_mis > 0
    assert b_mis / b_tot > 0.15 # Clear contradictions detected
