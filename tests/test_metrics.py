import numpy as np
from quantum_sim.utils.metrics import extract_bits_from_counts, sift_bases, estimate_qber


def test_extract_bits_from_counts():
    counts = {"0101": 100}
    bits = extract_bits_from_counts(counts, n_qubits=4)
    np.testing.assert_array_equal(bits, np.array([1, 0, 1, 0]))


def test_sift_bases():
    alice_bases = np.array([0, 1, 0, 1])
    bob_bases = np.array([0, 0, 1, 1])
    sifted = sift_bases(alice_bases, bob_bases)
    np.testing.assert_array_equal(sifted, np.array([0, 3]))


def test_estimate_qber_zero_error():
    alice_bits = np.array([1, 0, 1, 0])
    bob_bits = np.array([1, 0, 1, 0])
    sifted = np.array([0, 1, 2, 3])
    qber = estimate_qber(alice_bits, bob_bits, sifted, sample_ratio=1.0)
    assert qber == 0.0


def test_estimate_qber_high_error():
    alice_bits = np.array([1, 1, 1, 1])
    bob_bits = np.array([0, 0, 0, 0])
    sifted = np.array([0, 1, 2, 3])
    qber = estimate_qber(alice_bits, bob_bits, sifted, sample_ratio=1.0)
    assert qber == 1.0
