"""B3: EVE_COLLECTIVE ancilla-probe attack and experiments/sweep_collective.py."""
import csv
import math
import os
import sys

import numpy as np
import pytest

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatSuite, ThreatType
from src.quantum_engine.threats import EveCollectiveAdversary, probe_flip_probability, probe_guess_probability

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))
import sweep_collective  # noqa: E402


def _probe_statevector(theta, bit, basis):
    """Explicit 2-qubit simulation: token (q0) in |bit>_basis, ancilla (q1) |0>, controlled-Ry(theta) q0 -> q1."""
    token = np.array([1, 0] if bit == 0 else [0, 1], dtype=complex)
    if basis == 1:
        token = np.array([1, 1] if bit == 0 else [1, -1], dtype=complex) / math.sqrt(2)
    psi = np.kron(np.array([1, 0], dtype=complex), token)        # index = q0 + 2*q1
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    cry = np.eye(4, dtype=complex)
    cry[np.ix_([1, 3], [1, 3])] = [[c, -s], [s, c]]               # acts on q1 when q0 = 1
    return (cry @ psi).reshape(2, 2)                              # [q1, q0]


@pytest.mark.parametrize("theta", [0.0, 0.4, math.pi / 4, math.pi / 2, math.pi])
def test_closed_forms_match_statevector(theta):
    for basis in (0, 1):
        # Token disturbance: probability of finding the orthogonal state in the preparation basis.
        state = _probe_statevector(theta, 0, basis)
        flip = np.array([0, 1], dtype=complex) if basis == 0 else np.array([1, -1], dtype=complex) / math.sqrt(2)
        p_flip = float(np.sum(np.abs(state @ flip.conj()) ** 2))
        assert p_flip == pytest.approx(probe_flip_probability(theta, basis), abs=1e-12)
        # Eve's Helstrom success between her ancilla states for bit 0 and bit 1 (equal priors).
        rho = [np.einsum("ai,bi->ab", s_, s_.conj()) for s_ in (_probe_statevector(theta, b, basis) for b in (0, 1))]
        helstrom = 0.5 + 0.25 * np.sum(np.abs(np.linalg.eigvalsh(rho[0] - rho[1])))
        assert helstrom == pytest.approx(probe_guess_probability(theta, basis), abs=1e-12)


def test_theta_validated():
    with pytest.raises(ValueError):
        EveCollectiveAdversary(-0.1, ChannelModel())
    with pytest.raises(ValueError):
        EveCollectiveAdversary(3.2, ChannelModel())


def test_scenario_runs_through_execute_protocol(rng):
    eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0))
    r = eng.execute_protocol("m", 16, rng=rng, scenario=ThreatScenarioConfig(
        threat_type=ThreatType.EVE_COLLECTIVE, collective_theta=math.pi / 2))
    assert r.ground_truth["injected_scenario"] == "eve_collective"


def test_no_probe_no_information_and_no_disturbance():
    channel = ChannelModel(depolarizing=0.0)
    eng = TeleportationQDS(backend="statevector", channel=channel)
    tr, eve = ThreatSuite.eve_collective(eng, 0.0, "m", 64, "alice", np.random.default_rng(1), channel)
    assert sweep_collective.copy_mismatches(eng, tr.session)[0] == 0
    assert 0.35 < eve.guess_accuracy < 0.65


def test_strong_probe_trades_disturbance_for_information():
    weak = sweep_collective.run_cell(0.0, 32, 20, seed=3, depolarizing=0.0)
    strong = sweep_collective.run_cell(math.pi / 2, 32, 20, seed=3, depolarizing=0.0)
    assert weak["mismatches"] == 0 and strong["mismatch_rate"] > 0.02
    assert strong["eve_accuracy"] > 0.6 > weak["eve_accuracy"]


def test_sweep_is_seeded_and_writes_outputs(tmp_path):
    assert sweep_collective.run_cell(0.5, 16, 3, seed=9) == sweep_collective.run_cell(0.5, 16, 3, seed=9)
    rows = sweep_collective.main(["--trials", "2", "--bits", "16", "--thetas", "0", "1.5708",
                                  "--seed", "1", "--out", str(tmp_path)])
    with open(tmp_path / "sweep_collective.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(rows) == 2
    assert "not a proof of security" in (tmp_path / "sweep_collective.md").read_text()
