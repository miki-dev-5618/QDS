import numpy as np


def extract_bits_from_counts(counts: dict, n_qubits: int) -> np.ndarray:
    if not counts:
        return np.zeros(n_qubits, dtype=int)
    
    most_probable_bitstring = max(counts, key=counts.get)
    clean_bitstring = most_probable_bitstring.replace(" ", "")
    
    qubit_order_bits = clean_bitstring[::-1][:n_qubits]
    return np.array([int(b) for b in qubit_order_bits], dtype=int)


def sift_bases(alice_bases: np.ndarray, bob_bases: np.ndarray) -> np.ndarray:
    return np.where(alice_bases == bob_bases)[0]


def estimate_qber(
    alice_bits: np.ndarray,
    bob_bits: np.ndarray,
    sifted_indices: np.ndarray,
    sample_ratio: float = 0.5,
    rng: np.random.Generator = None
) -> float:
    if len(sifted_indices) == 0:
        return 0.0
    
    if rng is None:
        rng = np.random.default_rng()

    sample_size = max(1, int(len(sifted_indices) * sample_ratio))
    sampled_indices = rng.choice(sifted_indices, size=sample_size, replace=False)
    
    mismatches = np.sum(alice_bits[sampled_indices] != bob_bits[sampled_indices])
    return float(mismatches / sample_size)
