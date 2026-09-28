"""Measurement and symmetrisation invariants."""
from src.quantum_engine import OrthogonalEliminationEngine, SYMBOL_MAP, SymmetrisationManager


def test_every_copy_ends_up_with_exactly_one_verifier(rng):
    states = [(i % 2, (i // 2) % 2) for i in range(64)]
    other = [(1 - b, ba) for b, ba in states]
    _, _, bob, charlie, _, _ = SymmetrisationManager.perform_symmetrisation_swap(states, other, rng)
    for i in range(64):
        held = bob[i] + charlie[i]
        assert sorted(held) == sorted([states[i], other[i]])


def test_eliminated_state_is_never_the_true_state_without_noise(engine, rng):
    session = engine.distribute("alice", "m", 64, rng)
    for name in ("bob", "charlie"):
        rec = engine.verifiers[name].records[session.context.session_id]
        for i, elims in enumerate(rec.eliminated):
            assert SYMBOL_MAP[session.signature[i]] not in elims


def test_count_mismatches_is_per_copy():
    sig = [(0, 0), (0, 1)]
    table = [['|0⟩', '|0⟩'], ['|1⟩']]
    mism, checked, pos = OrthogonalEliminationEngine.count_mismatches(sig, table)
    assert (mism, checked, pos) == (2, 3, [0])


def test_elimination_rules():
    e = OrthogonalEliminationEngine.eliminate_state_symbol
    assert [e(0, 0), e(0, 1), e(1, 0), e(1, 1)] == ['|1⟩', '|0⟩', '|−⟩', '|+⟩']
