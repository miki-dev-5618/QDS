from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import numpy as np

SYMBOL_MAP = {
    (0, 0): '|0⟩',
    (1, 0): '|1⟩',
    (0, 1): '|+⟩',
    (1, 1): '|−⟩'
}

REV_SYMBOL_MAP = {
    '|0⟩': (0, 0),
    '|1⟩': (1, 0),
    '|+⟩': (0, 1),
    '|−⟩': (1, 1),
}


class EveSignatureForgery:
    @staticmethod
    def generate_random_forgery(n_bits: int, rng: Optional[np.random.Generator] = None) -> List[Tuple[int, int]]:
        if rng is None:
            rng = np.random.default_rng()
        bits = rng.integers(0, 2, size=n_bits)
        bases = rng.integers(0, 2, size=n_bits)
        return [(int(b), int(ba)) for b, ba in zip(bits, bases)]


class DishonestVerifierForgery:
    @staticmethod
    def forge_to_verifier(
        n_bits: int,
        bob_eliminated: List[List[str]],
        bob_held: List[List[str]],
        rng: Optional[np.random.Generator] = None
    ) -> List[Tuple[int, int]]:
        if rng is None:
            rng = np.random.default_rng()

        forged_sig = []
        all_states = ['|0⟩', '|1⟩', '|+⟩', '|−⟩']

        for i in range(n_bits):
            elim = set(bob_eliminated[i])
            candidates = [s for s in all_states if s not in elim]
            
            if candidates:
                chosen_state = str(rng.choice(candidates))
            else:
                chosen_state = str(rng.choice(all_states))
                
            forged_sig.append(REV_SYMBOL_MAP[chosen_state])

        return forged_sig


@dataclass
class RepudiationScenario:
    alice_sigs: Dict[int, List[Tuple[int, int]]]
    bob_initial_sigs: Dict[int, List[Tuple[int, int]]]
    charlie_initial_sigs: Dict[int, List[Tuple[int, int]]]


class RepudiationSimulation:
    @staticmethod
    def create_asymmetric_signatures(
        n_bits: int,
        tamper_positions: List[int],
        rng: Optional[np.random.Generator] = None
    ) -> RepudiationScenario:
        if rng is None:
            rng = np.random.default_rng()

        alice_sigs = {
            0: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))],
            1: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
        }

        bob_sigs = {
            0: list(alice_sigs[0]),
            1: list(alice_sigs[1])
        }

        charlie_sigs_0 = list(alice_sigs[0])
        for pos in tamper_positions:
            if 0 <= pos < n_bits:
                b, ba = charlie_sigs_0[pos]
                charlie_sigs_0[pos] = (1 - b, ba)

        charlie_sigs = {
            0: charlie_sigs_0,
            1: list(alice_sigs[1])
        }

        return RepudiationScenario(
            alice_sigs=alice_sigs,
            bob_initial_sigs=bob_sigs,
            charlie_initial_sigs=charlie_sigs
        )
