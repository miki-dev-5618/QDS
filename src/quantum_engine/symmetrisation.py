from typing import Dict, List, Optional, Tuple
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


class UniformHolderAssignment:
    """
    N-recipient symmetrisation (optional extension): *uniform final holder*.

    Alice prepares one copy of every signature position for each roster
    member. Each recipient privately sends each copy it was given to a
    holder drawn uniformly from the whole roster (itself included), so every
    copy ends with exactly one holder and P(holder = v) = 1/N for every v.

    N = 2 reproduces the holder probabilities of keep-or-forward (each copy
    stays with probability 1/2); the random trace is not identical, by design.
    Transfers here model quantum copies in transit before measurement, exactly
    like ``perform_symmetrisation_swap``. This is an assignment rule, not a
    multiparty security proof: with N > 2, each recipient checks about one
    copy per position on average, as with N = 2.
    """

    @staticmethod
    def assign(initial: Dict[str, List[Tuple[int, int]]], roster: List[str],
               rng: Optional[np.random.Generator] = None
               ) -> Tuple[Dict[str, List[str]], Dict[str, List[List[Tuple[int, int]]]], Dict[str, List[List[str]]],
                          Dict[str, List[List[str]]]]:
        """
        Returns (destinations, held, held_desc, held_source).
        destinations[src][i]: holder chosen by ``src`` for its copy of position i (private to src).
        held[v][i]: states held by v at position i; held_source[v][i]: the roster member each came from.
        """
        rng = rng if rng is not None else np.random.default_rng()
        roster = list(roster)
        n_bits = len(next(iter(initial.values()))) if initial else 0
        if any(len(initial[v]) != n_bits for v in roster):
            raise ValueError("Every recipient needs one initial copy per signature position.")
        destinations = {src: [roster[int(k)] for k in rng.integers(0, len(roster), n_bits)] for src in roster}
        held = {v: [[] for _ in range(n_bits)] for v in roster}
        desc = {v: [[] for _ in range(n_bits)] for v in roster}
        source = {v: [[] for _ in range(n_bits)] for v in roster}
        for i in range(n_bits):
            for src in roster:
                dst = destinations[src][i]
                held[dst][i].append(initial[src][i])
                source[dst][i].append(src)
                desc[dst][i].append(f"{src.capitalize()} Kept ({src} copy)" if dst == src
                                    else f"{src.capitalize()} Forwarded -> {dst.capitalize()} ({src} copy)")
        return destinations, held, desc, source

    @staticmethod
    def legacy_actions(destinations: Dict[str, List[str]], verifier: str) -> List[str]:
        """'K'/'F' per position, as reported for the two-verifier display."""
        return ["K" if d == verifier else "F" for d in destinations.get(verifier, [])]
