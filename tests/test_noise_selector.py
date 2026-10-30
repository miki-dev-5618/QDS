"""A6: noise-profile selector - profile registry, API validation and what the verifier dashboards receive."""
import importlib
import os

import pytest
from fastapi.testclient import TestClient

from src.quantum_engine import ChannelModel, make_lossy_channel, make_readout_channel
from src.quantum_engine import noise_profiles as npf

ADMIN = ("admin", "admin2026")
BOB = ("bob", "quantum2026")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    d = tmp_path_factory.mktemp("noise")
    os.environ["HEDWIG_BACKEND"] = "statevector"
    os.environ["HEDWIG_AUDIT_KEY"] = str(d / "audit.pem")
    os.environ["HEDWIG_DB"] = str(d / "hedwig.db")
    os.environ["HEDWIG_AUDIT_PQ"] = "off"
    os.environ.pop("HEDWIG_USERS_FILE", None)
    os.environ.pop("HEDWIG_NOISE_PROFILE", None)
    import server as srv
    return importlib.reload(srv)


def client(server, *logins):
    c = TestClient(server.app)
    for user, pw in logins:
        assert c.post("/api/login", json={"username": user, "password": pw}).status_code == 200
    return c


def send(c, **extra):
    c.post("/api/channel/reset", json={"reason": "noise selector test"})
    return c.post("/api/sign-and-send", json={"message_text": "hello", "n_bits": 64, **extra})


# ------------------------------------------------------------------ registry
def test_six_profiles_and_legacy_alias():
    assert list(npf.PROFILES) == ["ideal", "depolarising_1pct", "ibm_fake", "amp_damping", "readout", "lossy"]
    assert npf.canonical("depolarizing") == "depolarising_1pct"
    assert npf.canonical(None) == "depolarising_1pct"
    with pytest.raises(npf.NoiseProfileError):
        npf.canonical("thermal")


def test_build_channel_uses_the_parameter_and_validates_its_range():
    assert npf.build_channel("ideal").depolarizing == 0.0
    assert npf.build_channel("depolarising_1pct").depolarizing == 0.01
    assert npf.build_channel("depolarising_1pct", 0.05).depolarizing == 0.05
    assert npf.build_channel("amp_damping", 0.2).amp_damping_gamma == 0.2
    assert npf.build_channel("lossy", 0.3).eta_loss == 0.3
    for name, bad in (("lossy", 0.9), ("amp_damping", -0.1), ("ideal", 0.1)):
        with pytest.raises(npf.NoiseProfileError):
            npf.build_channel(name, bad)


@pytest.mark.parametrize("channel,profile", [
    (ChannelModel(depolarizing=0.0), "ideal"),
    (ChannelModel(), "depolarising_1pct"),
    (make_readout_channel(0.01, 0.03), "readout"),
    (make_lossy_channel(0.2), "lossy"),
])
def test_describe_channel_round_trips(channel, profile):
    assert npf.describe_channel(channel)["profile"] == profile


def test_unavailable_profile_is_reported_and_refused(monkeypatch):
    monkeypatch.setattr(npf, "availability", lambda name: (name != "ibm_fake", "needs qiskit-aer"))
    entry = next(p for p in npf.catalogue() if p["name"] == "ibm_fake")
    assert entry["available"] is False and entry["reason"] == "needs qiskit-aer"
    with pytest.raises(npf.NoiseProfileError, match="not available"):
        npf.build_channel("ibm_fake")


# ------------------------------------------------------------------ API
def test_profiles_endpoint(server):
    data = client(server, ADMIN).get("/api/noise-profiles").json()
    assert [p["name"] for p in data["profiles"]] == list(npf.PROFILES)
    assert all({"available", "reason", "param", "label"} <= set(p) for p in data["profiles"])
    assert data["default"]["profile"] == "depolarising_1pct"
    assert TestClient(server.app).get("/api/noise-profiles").status_code == 401


def test_unknown_profile_or_bad_parameter_is_422_not_a_crash(server):
    c = client(server, ADMIN)
    assert send(c, noise_profile="thermal").status_code == 422
    assert send(c, noise_profile="lossy", noise_param=0.99).status_code == 422
    assert send(c, noise_profile="readout", noise_param=0.1).status_code == 422


def test_requests_without_noise_fields_keep_the_default_channel(server):
    r = send(client(server, ADMIN))
    assert r.status_code == 200
    assert r.json()["transmission"]["noise"] == npf.describe_channel(server.qds_engine.default_channel)
    legacy = send(client(server, ADMIN), noise_profile="depolarizing")     # what the old admin page sent
    assert legacy.status_code == 200 and legacy.json()["transmission"]["noise"]["profile"] == "depolarising_1pct"


@pytest.mark.parametrize("profile,param", [("ideal", None), ("depolarising_1pct", 0.02), ("amp_damping", 0.1),
                                           ("lossy", 0.2), ("ibm_fake", None)])
def test_each_profile_runs_and_is_reported(server, profile, param):
    if not npf.availability(profile)[0]:
        pytest.skip(f"{profile} unavailable here")
    extra = {"noise_profile": profile} | ({} if param is None else {"noise_param": param})
    r = send(client(server, ADMIN), **extra)
    assert r.status_code == 200, r.text
    assert r.json()["transmission"]["noise"]["profile"] == profile


def test_switching_profile_changes_what_verifiers_see(server):
    admin = client(server, ADMIN)
    quiet = send(admin, noise_profile="ideal").json()["transmission"]
    noisy = send(admin, noise_profile="depolarising_1pct", noise_param=0.3).json()["transmission"]
    assert quiet["channel"]["error_count"] == 0          # noiseless statevector: no test-token errors
    assert noisy["channel"]["error_count"] > 0           # QBER 0.2 over dozens of test tokens
    bob_view = {t["transmission_id"]: t for t in client(server, BOB).get("/api/history").json()["transmissions"]}
    for tx in (quiet, noisy):
        seen = bob_view[tx["transmission_id"]]
        assert seen["noise"] == tx["noise"]
        assert "ground_truth" not in seen


def test_noise_reaches_the_verifier_websocket(server):
    admin, bob = client(server, ADMIN), client(server, BOB)
    with bob.websocket_connect("/ws/bob") as ws:
        ws.receive_text()                                              # init_sync
        tx = send(admin, noise_profile="amp_damping", noise_param=0.2).json()["transmission"]
        while True:
            msg = ws.receive_json()
            if msg["event"] == "new_transmission" and msg["data"]["transmission"]["transmission_id"] == tx["transmission_id"]:
                break
    pushed = msg["data"]["transmission"]
    assert pushed["noise"] == {"profile": "amp_damping", "label": "Amplitude damping", "params": {"gamma": 0.2}}
    assert "ground_truth" not in pushed
