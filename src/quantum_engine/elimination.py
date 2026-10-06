from typing import List, Tuple, Dict

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
    Orthogonal state elimination for Pauli-eigenstate signatures.

    A verifier measures each copy it holds in a randomly chosen Pauli basis.
    The outcome rules out the orthogonal state, so the verifier records one
    eliminated state per measured copy. A revealed signature state that equals
    an eliminated state is a contradiction (mismatch) for that copy.
    """

    @staticmethod
    def eliminate_state_symbol(meas_basis: int, outcome_bit: int) -> str:
        """
        - Z basis: outcome 0 eliminates |1>, outcome 1 eliminates |0>
        - X basis: outcome 0 eliminates |->, outcome 1 eliminates |+>
        """
        if meas_basis == 0:
            return '|1⟩' if outcome_bit == 0 else '|0⟩'
        return '|−⟩' if outcome_bit == 0 else '|+⟩'

    @staticmethod
    def count_mismatches(
        revealed_signature: List[Tuple[int, int]],
        eliminated_table: List[List[str]],
    ) -> Tuple[int, int, List[int]]:
        """
        Count contradictions per measured copy.

        Returns (mismatches, copies_checked, positions_with_a_contradiction).
        Positions beyond the shorter of the two inputs are ignored.
        """
        mismatches = 0
        checked = 0
        positions: List[int] = []
        for i in range(min(len(revealed_signature), len(eliminated_table))):
            bit, basis = revealed_signature[i]
            symbol = SYMBOL_MAP.get((int(bit), int(basis)), '|?⟩')
            hit = False
            for eliminated in eliminated_table[i]:
                checked += 1
                if eliminated == symbol:
                    mismatches += 1
                    hit = True
            if hit:
                positions.append(i)
        return mismatches, checked, positions
