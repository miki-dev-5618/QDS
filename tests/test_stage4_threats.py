import pytest
import numpy as np

from quantum_sim.nodes.node import Node
from quantum_sim.channel.base import QuantumChannel
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


def test_benign_authentic_classification():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    channel = QuantumChannel()

    qds = QDSProtocol(alice, bob, charlie, channel)
    result = qds.run(n_bits=16, rng=rng)

    # Legitimate signature for k=0
    sig_0 = result.alice_signatures[0]
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=sig_0, recipient='charlie')

    assert b_valid is True
    assert c_valid is True
    assert b_mismatches == 0
    assert c_mismatches == 0

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mismatches, b_total, c_mismatches, c_total)

    assert report.classification == ThreatClassification.BENIGN_AUTHENTIC
    assert report.is_threat_detected is False
    assert report.confidence_score == 1.0


def test_external_forgery_detection():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    channel = QuantumChannel()

    qds = QDSProtocol(alice, bob, charlie, channel)
    qds.run(n_bits=32, rng=rng)

    # Eve forges a completely random signature
    forged_sig = EveSignatureForgery.generate_random_forgery(n_bits=32, rng=rng)

    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=forged_sig, recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=forged_sig, recipient='charlie')

    assert b_mismatches > 0
    assert c_mismatches > 0

    engine = QDSDetectionEngine()
    report = engine.analyze(b_mismatches, b_total, c_mismatches, c_total)

    assert report.classification == ThreatClassification.EXTERNAL_FORGERY
    assert report.is_threat_detected is True
    assert report.confidence_score >= 0.80


def test_dishonest_verifier_forgery_detection():
    rng = np.random.default_rng(42)
    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    channel = QuantumChannel()

    qds = QDSProtocol(alice, bob, charlie, channel)
    qds.run(n_bits=32, rng=rng)

    # Bob attempts to forge a signature to Charlie
    forged_sig_by_bob = DishonestVerifierForgery.forge_to_verifier(
        n_bits=32,
        bob_eliminated=qds.bob_eliminated,
        bob_held=qds.bob_held,
        rng=rng
    )

    # Bob checks his own forged signature (which matches his knowledge)
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=forged_sig_by_bob, recipient='bob')
    # Charlie checks Bob's forged signature
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=forged_sig_by_bob, recipient='charlie')

    assert c_mismatches > 0

    engine = QDSDetectionEngine()
    report = engine.analyze(
        bob_mismatches=b_mismatches,
        bob_total=b_total,
        charlie_mismatches=c_mismatches,
        charlie_total=c_total,
        context_hint="dishonest_verifier"
    )

    assert report.classification == ThreatClassification.DISHONEST_VERIFIER_FORGERY
    assert report.is_threat_detected is True


def test_repudiation_detection():
    rng = np.random.default_rng(42)
    tamper_positions = [0, 1, 2, 3, 4, 5, 6, 7]
    scenario = RepudiationSimulation.create_asymmetric_signatures(
        n_bits=16,
        tamper_positions=tamper_positions,
        rng=rng
    )

    alice = Node("Alice")
    bob = Node("Bob")
    charlie = Node("Charlie")
    channel = QuantumChannel()

    qds = QDSProtocol(alice, bob, charlie, channel)
    qds.run(n_bits=16, rng=rng)

    # Manually overwrite Alice's presented signature to test repudiation discrepancy
    b_valid, b_mismatches, b_total = qds.verify_message(k=0, proposed_sig=scenario.bob_initial_sigs[0], recipient='bob')
    c_valid, c_mismatches, c_total = qds.verify_message(k=0, proposed_sig=scenario.bob_initial_sigs[0], recipient='charlie')

    engine = QDSDetectionEngine()
    report = engine.analyze(
        bob_mismatches=b_mismatches,
        bob_total=b_total,
        charlie_mismatches=c_mismatches + 6, # simulate asymmetric failure
        charlie_total=c_total
    )

    assert report.classification == ThreatClassification.REPUDIATION_ATTEMPT
    assert report.is_threat_detected is True
