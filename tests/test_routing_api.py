"""Admin demo controls and participant-filtered durable routing APIs."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def routing_server(tmp_path, monkeypatch):
    monkeypatch.setenv("HEDWIG_BACKEND", "statevector")
    monkeypatch.setenv("HEDWIG_DB", str(tmp_path / "routing.db"))
    monkeypatch.setenv("HEDWIG_AUDIT_KEY", str(tmp_path / "audit.pem"))
    monkeypatch.setenv("HEDWIG_AUDIT_PQ", "off")
    monkeypatch.setenv("HEDWIG_TOPOLOGY", "demo-multihop")
    monkeypatch.delenv("HEDWIG_USERS_FILE", raising=False)
    import server
    return importlib.reload(server)


def login(server, role):
    client = TestClient(server.app)
    password = "admin2026" if role == "admin" else "quantum2026"
    assert client.post("/api/login", json={"username": role, "password": password}).status_code == 200
    return client


def test_api_probe_driven_reroute_history_privacy_and_refusal(routing_server):
    server = routing_server
    admin = login(server, "admin")
    bob = login(server, "bob")
    payload = {"message_text": "routing demonstration", "n_bits": 32}
    first_response = admin.post("/api/sign-and-send", json=payload)
    assert first_response.status_code == 200
    first = first_response.json()["transmission"]
    sid = first["context"]["session_id"]
    original = admin.get(f"/api/sessions/{sid}/routes").json()
    assert original["plan"]["routes"]["bob"]["nodes"] == ["alice", "R1", "R2", "bob"]
    fault = {"edge": "R1->R2", "action": "attack", "reason": "controlled intercept"}
    assert bob.post("/api/routing/fault", json=fault).status_code == 403
    assert admin.post("/api/routing/fault", json=fault).status_code == 200
    topo = admin.get("/api/topology").json()
    assert next(e for e in topo["edges"] if e["id"] == "R1->R2")["state"] == "open"
    probe = admin.post("/api/routing/probe", json={"edges": ["R1->R2"], "count": 512})
    assert probe.status_code == 200
    assert probe.json()["observations"][0]["decision"]["response_action"] == "quarantine"
    next_response = admin.post("/api/sign-and-send", json=payload)
    assert next_response.status_code == 200
    next_tx = next_response.json()["transmission"]
    assert next_tx["routing"]["plan"]["routes"]["bob"]["nodes"] == ["alice", "R3", "bob"]
    assert next_tx["routing"]["plan"]["routes"]["bob"]["rerouted"]
    assert admin.get(f"/api/sessions/{sid}/routes").json() == original
    private_view = bob.get("/api/routing/history").json()["sessions"][0]
    assert list(private_view["plan"]["routes"]) == ["bob"]
    assert list(private_view["execution"]["recipients"]) == ["bob"]
    assert bob.get("/api/topology").json()["injections"] is None
    assert "latest_plan" not in bob.get("/api/topology").json()["router"]
    assert bob.get("/api/history").json()["transmissions"][-1]["routing"]["plan"]["roster"] == ["bob"]
    cert = bob.get(f"/api/audit/{next_tx['transmission_id']}").json()
    assert "evidence" not in cert and "plan" not in cert["record"]["routing"]
    assert bob.post("/api/audit/verify", json=cert).json()["valid"]
    assert admin.post("/api/routing/fault", json={"edge": "alice->R3", "action": "manual", "reason": "block alternative"}).status_code == 200
    refused = admin.post("/api/sign-and-send", json=payload)
    assert refused.status_code == 423
    assert refused.json()["detail"]["reason"] == "no_eligible_route"
    assert refused.json()["detail"]["search_complete"]
    assert admin.get("/api/routing/refusals").json()["refusals"][0]["detail"]["reason"] == "no_eligible_route"
    assert bob.get("/api/routing/refusals").status_code == 403
    assert len(admin.get("/api/routing/history").json()["sessions"]) == 2
    assert admin.get("/api/audit/chain").json()["verification"]["valid"]


def test_topology_validation_and_emergency_endpoints(routing_server):
    admin = login(routing_server, "admin")
    for document in ({"nodes": {}}, {"preset": "missing"}):
        assert admin.post("/api/topology", json=document).status_code == 400
    assert admin.post("/api/routing/probe", json={"edges": ["unknown"]}).status_code == 400
    assert admin.post("/api/routing/probe", json={"count": True}).status_code == 400
    assert admin.post("/api/routing/fault", json={"edge": "R1->R2", "reason": ""}).status_code == 400
    assert admin.post("/api/routing/emergency", json={"enabled": True, "reason": "maintenance"}).status_code == 200
    request = {"message_text": "stop check", "n_bits": 32}
    assert admin.post("/api/sign-and-send", json=request).json()["status"] == "emergency_stop"
    admin.post("/api/channel/reset", json={})
    assert admin.post("/api/sign-and-send", json=request).status_code == 423
    admin.post("/api/routing/emergency", json={"enabled": False, "reason": "restored"})
    assert admin.post("/api/topology", json={"preset": "star"}).status_code == 200
    assert admin.post("/api/sign-and-send", json=request).status_code == 200
