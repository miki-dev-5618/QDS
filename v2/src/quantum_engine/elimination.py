from typing import List, Tuple, Dict, Optional, Set
import numpy as np

SYMBOL_MAP: Dict[Tuple[int, int], str] = {
    (0, 0): '|0⟩',
    (1, 0): '|1⟩',
    (0, 1): '|+⟩',
    (1, 1): '|−⟩'
}

REV_SYMBOL_MAP: Dict[str, Tuple[int, int]] = {
    '|0⟩': (0, 0),
    '|1⟩': (1, 0),
    '|+⟩': (0, 1),
    '|−⟩': (1, 1),
}


class OrthogonalEliminationEngine:
    """
    Implements Orthogonal State Elimination for Quantum Digital Signatures.
    
    Verifiers perform projective measurements on incoming quantum tokens.
    Based on the measurement outcome, the orthogonal quantum state is provably
    ruled out. The verifier maintains an 'eliminated states list' for each token
    position. To verify an Alice signature, the verifier simply checks whether
    the claimed state exists in their eliminated set.
    """

    @staticmethod
    def eliminate_state_symbol(meas_basis: int, outcome_bit: int) -> str:
        """
        Computes the eliminated state string based on measurement basis and outcome.
        - Basis 0 (Z basis):
            Outcome 0 (|0>) eliminates |1>
            Outcome 1 (|1>) eliminates |0>
        - Basis 1 (X basis):
            Outcome 0 (|+) eliminates |->
            Outcome 1 (|->) eliminates |+>
        """
        if meas_basis == 0:
            return '|1⟩' if outcome_bit == 0 else '|0⟩'
        else:
            return '|−⟩' if outcome_bit == 0 else '|+⟩'

    @staticmethod
    def verify_against_eliminations(
        revealed_signature: List[Tuple[int, int]],
        eliminated_table: List[List[str]],
        held_tokens: List[List[str]]
    ) -> Tuple[bool, int, int, List[int]]:
        """
        Verifies a revealed signature against the verifier's eliminated state table.
        
        Returns:
            is_valid (bool): True if 0 contradictions found.
            mismatch_count (int): Total number of states contradicting the elimination table.
            total_checked (int): Number of positions the verifier had quantum tokens for.
            contradiction_indices (List[int]): Positions where contradictions occurred.
        """
        mismatches = 0
        total_checked = 0
        contradiction_indices: List[int] = []

        n_bits = min(len(revealed_signature), len(eliminated_table))
        for i in range(n_bits):
            # Only verify positions where this verifier holds at least one measurement
            if held_tokens and len(held_tokens[i]) > 0:
                total_checked += 1
                bit, basis = revealed_signature[i]
                state_symbol = SYMBOL_MAP.get((int(bit), int(basis)), '|?⟩')

                if state_symbol in eliminated_table[i]:
                    mismatches += 1
                    contradiction_indices.append(i)

        is_valid = (mismatches == 0)
        return is_valid, mismatches, total_checked, contradiction_indices
