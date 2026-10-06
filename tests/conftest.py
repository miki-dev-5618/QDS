import os
import sys

import numpy as np
import pytest

V2_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)

from src.quantum_engine import ChannelModel, TeleportationQDS  # noqa: E402


class FakeClock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float):
        self.t += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def rng():
    return np.random.default_rng(12345)


@pytest.fixture
def engine(clock):
    """Fast, noiseless engine with a controllable clock."""
    return TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=0.0), clock=clock)
