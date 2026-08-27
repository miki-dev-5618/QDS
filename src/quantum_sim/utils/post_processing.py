from typing import Tuple, List
import numpy as np


def _find_single_error(
    alice_bits: np.ndarray,
    bob_bits: np.ndarray,
    start: int,
    end: int
) -> int:
    """Recursively locates a single bit mismatch in Bob's bits using binary search parity comparison."""
    if start == end:
        return start

    mid = (start + end) // 2

    # Left parity comparison
    alice_left_parity = int(np.sum(alice_bits[start:mid + 1]) % 2)
    bob_left_parity = int(np.sum(bob_bits[start:mid + 1]) % 2)

    if alice_left_parity != bob_left_parity:
        return _find_single_error(alice_bits, bob_bits, start, mid)
    else:
        return _find_single_error(alice_bits, bob_bits, mid + 1, end)


def reconcile_keys(
    alice_bits: np.ndarray,
    bob_bits: np.ndarray,
    block_size: int = 8
) -> Tuple[np.ndarray, int]:
    """
    Performs block-parity error correction (simplified Cascade protocol).
    Divides bits into blocks, checks parity, and runs a binary search to find
    and correct single-bit errors in mismatched blocks.
    
    Returns:
        corrected_bob_bits: NumPy array of Bob's corrected bits
        errors_corrected: Total count of corrected bits
    """
    corrected_bob = bob_bits.copy()
    n = len(alice_bits)
    errors_corrected = 0

    if n == 0:
        return corrected_bob, 0

    for start in range(0, n, block_size):
        end = min(start + block_size - 1, n - 1)
        
        # Compare overall block parity
        alice_parity = int(np.sum(alice_bits[start:end + 1]) % 2)
        bob_parity = int(np.sum(corrected_bob[start:end + 1]) % 2)

        if alice_parity != bob_parity:
            # Odd number of errors in this block, find and correct one
            err_idx = _find_single_error(alice_bits, corrected_bob, start, end)
            corrected_bob[err_idx] = 1 - corrected_bob[err_idx]
            errors_corrected += 1

    return corrected_bob, errors_corrected


def amplify_privacy(
    bits: np.ndarray,
    qber: float,
    min_ratio: float = 0.1,
    rng: np.random.Generator = None
) -> np.ndarray:
    """
    Performs privacy amplification using a random binary matrix multiplier (Universal Hashing).
    
    The compression ratio is dynamically adjusted based on the QBER to discard information
    that could have leaked to Eve.
    
    Args:
        bits: The input bit string (NumPy array of 0s and 1s)
        qber: Estimated Quantum Bit Error Rate
        min_ratio: Minimum ratio of key to keep (default 0.1)
        rng: Optional random number generator
    """
    if len(bits) == 0:
        return bits.copy()

    if rng is None:
        rng = np.random.default_rng()

    # Dynamic compression ratio: more errors -> more compression
    # Under no errors, we might keep ~80% or 90% to account for general security margin.
    ratio = max(min_ratio, 1.0 - 2.5 * qber)
    n_out = max(1, int(np.floor(len(bits) * ratio)))

    n_in = len(bits)
    
    # Generate a random binary matrix (M x N)
    h_matrix = rng.integers(0, 2, size=(n_out, n_in))

    # Multiply H * bits modulo 2
    amplified_bits = np.dot(h_matrix, bits) % 2
    return amplified_bits
