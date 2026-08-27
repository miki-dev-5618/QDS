import numpy as np
from quantum_sim.core.circuit import prepare_bb84_state
from quantum_sim.channel.base import QuantumChannel
from quantum_sim.channel.attacks import InterceptResendAttack


def test_ideal_channel():
    bits = np.array([0, 1])
    bases = np.array([0, 1])
    qc = prepare_bb84_state(bits, bases)
    channel = QuantumChannel()
    transmitted_qc = channel.transmit(qc)
    assert transmitted_qc.num_qubits == 2


def test_intercept_resend_attack():
    bits = np.array([0, 1])
    bases = np.array([0, 1])
    qc = prepare_bb84_state(bits, bases)
    channel = QuantumChannel(attacks=[InterceptResendAttack(p_intercept=1.0)])
    attacked_qc = channel.transmit(qc)
    assert "eve" in [reg.name for reg in attacked_qc.cregs]
