from typing import List, Tuple, Dict, Optional
import numpy as np


class SymmetrisationManager:
    """
    Manages classical/quantum symmetrisation (Keep-or-Forward) between verifiers.
    
    In 3-party QDS:
    - Alice distributes Copy 1 (bob_states) to Bob, and Copy 2 (charlie_states) to Charlie.
    - Bob randomly decides to Keep ('K') or Forward ('F') his copy to Charlie.
    - Charlie randomly decides to Keep ('K') or Forward ('F') his copy to Bob.
    
    Because Alice does not know which verifier kept or forwarded which token,
    any asymmetric state distribution by Alice (Repudiation Attack) is randomly
    dispersed across BOTH Bob and Charlie, causing BOTH verifiers to detect
    orthogonal state contradictions!
    """

    @staticmethod
    def perform_symmetrisation_swap(
        bob_initial_states: List[Tuple[int, int]],
        charlie_initial_states: List[Tuple[int, int]],
        rng: Optional[np.random.Generator] = None
    ) -> Tuple[
        List[str],                         # bob_actions
        List[str],                         # charlie_actions
        List[List[Tuple[int, int]]],       # bob_held_states (actual quantum states)
        List[List[Tuple[int, int]]],       # charlie_held_states (actual quantum states)
        List[List[str]],                   # bob_held_descriptions (UI labels)
        List[List[str]]                    # charlie_held_descriptions (UI labels)
    ]:
        if rng is None:
            rng = np.random.default_rng()

        n_bits = len(bob_initial_states)
        bob_actions = [str(rng.choice(['K', 'F'])) for _ in range(n_bits)]
        charlie_actions = [str(rng.choice(['K', 'F'])) for _ in range(n_bits)]

        bob_held_states: List[List[Tuple[int, int]]] = []
        charlie_held_states: List[List[Tuple[int, int]]] = []
        bob_held_desc: List[List[str]] = []
        charlie_held_desc: List[List[str]] = []

        for i in range(n_bits):
            b_states: List[Tuple[int, int]] = []
            c_states: List[Tuple[int, int]] = []
            b_desc: List[str] = []
            c_desc: List[str] = []

            # 1. Bob's Copy 1 handling
            if bob_actions[i] == 'K':
                b_states.append(bob_initial_states[i])
                b_desc.append("Bob Kept (Copy 1)")
            else:
                c_states.append(bob_initial_states[i])
                c_desc.append("Bob Forwarded -> Charlie (Copy 1)")

            # 2. Charlie's Copy 2 handling
            if charlie_actions[i] == 'K':
                c_states.append(charlie_initial_states[i])
                c_desc.append("Charlie Kept (Copy 2)")
            else:
                b_states.append(charlie_initial_states[i])
                b_desc.append("Charlie Forwarded -> Bob (Copy 2)")

            bob_held_states.append(b_states)
            charlie_held_states.append(c_states)
            bob_held_desc.append(b_desc)
            charlie_held_desc.append(c_desc)

        return bob_actions, charlie_actions, bob_held_states, charlie_held_states, bob_held_desc, charlie_held_desc
