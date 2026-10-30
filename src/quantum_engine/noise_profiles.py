"""
Named channel noise profiles for the dashboard's noise selector.

Each profile maps to one ChannelModel factory and at most one tunable parameter:

  ideal              noiseless channel (depolarizing = 0)
  depolarising_1pct  depolarising noise, p = 0.01 by default (the engine's baseline)
  ibm_fake           IBM fake-backend noise, calibrated mode (A1); needs qiskit-aer
  amp_damping        amplitude damping on the travelling qubit, gamma
  readout            asymmetric readout error (the existing p01 / p10 / location fields)
  lossy              heralded photon loss, eta_loss (plus the 1% depolarising baseline)

``describe_channel`` turns whatever channel was actually used back into a profile
name and parameter, so the verifier dashboards can show it. The legacy request value
"depolarizing" is accepted as an alias of "depolarising_1pct".
"""
import functools
import importlib.util
from typing import Any, Dict, Optional, Tuple

from .channel import ChannelModel, make_amplitude_damping_channel, make_ibm_channel, make_lossy_channel

PROFILES: Dict[str, Dict[str, Any]] = {
    "ideal": {"label": "Ideal (noiseless)", "param": None},
    "depolarising_1pct": {"label": "Depolarising (1% baseline)",
                          "param": {"name": "depolarizing", "min": 0.0, "max": 0.3, "step": 0.005, "default": 0.01}},
    "ibm_fake": {"label": "IBM fake-backend noise (calibrated)", "param": None},
    "amp_damping": {"label": "Amplitude damping",
                    "param": {"name": "gamma", "min": 0.0, "max": 0.5, "step": 0.01, "default": 0.05}},
    "readout": {"label": "Readout (measurement) error", "param": None},
    "lossy": {"label": "Lossy channel (heralded photon loss)",
              "param": {"name": "eta_loss", "min": 0.0, "max": 0.5, "step": 0.01, "default": 0.1}},
}
ALIASES = {"depolarizing": "depolarising_1pct"}


class NoiseProfileError(ValueError):
    """Unknown profile, unavailable profile or parameter out of range (the API answers 422)."""


def canonical(name: Optional[str]) -> str:
    name = ALIASES.get(name or "depolarizing", name or "depolarizing")
    if name not in PROFILES:
        raise NoiseProfileError(f"Unknown noise_profile {name!r}; expected one of {sorted(PROFILES)}")
    return name


def availability(name: str) -> Tuple[bool, str]:
    if name == "ibm_fake":
        if importlib.util.find_spec("qiskit_aer") is None:
            return False, "needs qiskit-aer (pip install qiskit-aer)"
        try:
            _ibm_channel()
        except Exception as e:  # no fake backend provider, calibration failed, ...
            return False, f"IBM fake backend unavailable: {e}"
    return True, ""


def catalogue() -> list:
    out = []
    for name, spec in PROFILES.items():
        ok, why = availability(name)
        out.append({"name": name, "label": spec["label"], "available": ok, "reason": why, "param": spec["param"]})
    return out


@functools.lru_cache(maxsize=1)
def _ibm_channel() -> ChannelModel:
    return make_ibm_channel(mode="calibrated")


def build_channel(name: str, param: Optional[float] = None) -> ChannelModel:
    """Channel for a profile and its (optional) parameter. Readout is built by the caller from its own fields."""
    name = canonical(name)
    ok, why = availability(name)
    if not ok:
        raise NoiseProfileError(f"noise_profile {name!r} is not available here: {why}")
    spec = PROFILES[name]["param"]
    if param is not None:
        if spec is None:
            raise NoiseProfileError(f"noise_profile {name!r} takes no noise_param")
        if not spec["min"] <= param <= spec["max"]:
            raise NoiseProfileError(f"noise_param for {name!r} must be in [{spec['min']}, {spec['max']}], got {param}")
    value = spec["default"] if (spec is not None and param is None) else param
    if name == "ideal":
        return ChannelModel(depolarizing=0.0)
    if name == "depolarising_1pct":
        return ChannelModel(depolarizing=float(value))
    if name == "ibm_fake":
        return _ibm_channel()
    if name == "amp_damping":
        return make_amplitude_damping_channel(gamma=float(value))
    if name == "lossy":
        return make_lossy_channel(eta_loss=float(value))
    raise NoiseProfileError(f"noise_profile {name!r} is configured with its own fields")


def describe_channel(ch: ChannelModel) -> Dict[str, Any]:
    """Profile name, label and parameter of the channel that was actually used."""
    if ch.noise_profile == "ibm_fake":
        name, param = "ibm_fake", {"effective_error_rate": ch.effective_error_rate, "backend": ch.ibm_backend}
    elif ch.noise_profile == "amp_damping":
        name, param = "amp_damping", {"gamma": ch.amp_damping_gamma}
    elif ch.noise_profile == "readout":
        name, param = "readout", {"p01": ch.readout_p01, "p10": ch.readout_p10, "location": ch.readout_location}
    elif ch.noise_profile == "lossy":
        name, param = "lossy", {"eta_loss": ch.eta_loss}
    elif ch.depolarizing == 0.0:
        name, param = "ideal", {}
    else:
        name, param = "depolarising_1pct", {"depolarizing": ch.depolarizing}
    return {"profile": name, "label": PROFILES[name]["label"], "params": param}
