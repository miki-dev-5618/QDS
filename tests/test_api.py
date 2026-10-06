"""Issue 4: server-side sessions and authorisation, end to end through the API."""
import importlib
import os

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    d = tmp_path_factory.mktemp("state")
    os.environ["HEDWIG_BACKEND"] = "statevector"
    os.environ["HEDWIG_AUDIT_KEY"] = str(d / "audit.pem")
    os.environ["HEDWIG_DB"] = str(d / "hedwig.db")
    os.environ["HEDWIG_AUDIT_PQ"] = "off"
    os.environ.pop("HEDWIG_USERS_FILE", None)
    import server as srv
    return importlib.reload(srv)


def client(server, *logins):
    c = TestClient(server.app)
    for user, pw in logins:
        assert c.post("/api/login", json={"username": user, "password": pw}).status_code == 200
    return c


def reset(c, reason="test reset"):
    return c.post("/api/channel/reset", json={"reason": reason})


ADMIN = ("admin", "admin2026")
BOB = ("bob", "quantum2026")
CHARLIE = ("charlie", "quantum2026")


def send(c, threat="authentic", n_bits=32):
    return c.post("/api/sign-and-send", json={"message_text": "hello", "n_bits": n_bits, "threat_type": threat})


def test_unauthenticated_calls_fail(server):
    c = TestClient(server.app)
    assert send(c).status_code == 401
    assert c.get("/api/history").status_code == 401
    assert c.post("/api/arm-threat", json={"threat_type": "replay"}).status_code == 401
    r = c.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_bad_password_rejected(server):
    c = TestClient(server.app)
    assert c.post("/api/login", json={"username": "bob", "password": "nope"}).status_code == 401


def test_bob_cannot_act_as_alice_or_charlie(server):
    c = client(server, BOB)
    assert send(c).status_code == 403
    assert c.post("/api/channel/reset", json={}).status_code == 403
    assert c.get("/charlie", follow_redirects=False).status_code == 303


def test_websocket_requires_matching_session(server):
    c = client(server, BOB)
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws/admin") as ws:
            ws.receive_text()
    assert exc.value.code == 4401
    with c.websocket_connect("/ws/bob") as ws:
        assert '"init_sync"' in ws.receive_text()


def test_admin_can_sign_and_sender_comes_from_session(server):
    c = client(server, ADMIN)
    reset(c)
    r = send(c)
    assert r.status_code == 200
    tx = r.json()["transmission"]
    assert tx["context"]["sender"] == "alice"
    assert tx["ground_truth"]["injected_scenario"] == "authentic"


def test_verifier_views_hide_ground_truth(server):
    c = client(server, BOB)
    txs = c.get("/api/history").json()["transmissions"]
    assert txs and all("ground_truth" not in t and "alice" not in t for t in txs)


def test_replay_resends_real_package(server):
    c = client(server, ADMIN)
    reset(c)
    body = send(c, "replay").json()
    assert body["transmission"]["threat_report"]["classification"] == "REPLAY_ATTACK"
    assert body["transmission"]["response"]["response_action"] == "none"  # classical rejection never locks


def test_unauthorized_verification_is_recorded(server):
    admin = client(server, ADMIN)
    reset(admin)
    tx_id = send(admin).json()["transmission"]["transmission_id"]
    assert admin.get(f"/api/verification/{tx_id}/bob").status_code == 403
    events = admin.get("/api/security-events").json()["events"]
    assert any(e["type"] == "UNAUTHORIZED_VERIFICATION" and tx_id in e["detail"] for e in events)
    bob = client(server, BOB)
    assert bob.get(f"/api/verification/{tx_id}/bob").status_code == 200
    assert bob.get(f"/api/verification/{tx_id}/charlie").status_code == 403


def test_audit_is_issued_automatically_and_verifies(server):
    admin = client(server, ADMIN)
    reset(admin)
    tx = send(admin).json()["transmission"]
    assert tx["audit"]["chain_seq"] >= 1  # issued at assessment time, before any download
    cert = admin.get(f"/api/audit/{tx['transmission_id']}").json()
    assert cert["payload_sha256"] == tx["audit"]["payload_sha256"]
    assert admin.get(f"/api/audit/{tx['transmission_id']}").json() == cert  # stable, not re-signed
    assert admin.post("/api/audit/verify", json=cert).json()["valid"] is True
    cert["record"]["outcome"]["verdict"] = "edited"
    assert admin.post("/api/audit/verify", json=cert).json()["valid"] is False


def test_dishonest_bob_forward_checked_by_charlie(server):
    admin = client(server, ADMIN)
    reset(admin)
    send(admin)
    bob = client(server, BOB)
    tx = bob.post("/api/dishonest-bob-forward", json={}).json()["transmission"]
    assert tx["bob"] is None and tx["charlie"]["mode"] == "forwarded"
    assert tx["threat_report"]["classification"] == "DISHONEST_VERIFIER_FORGERY"


def test_reset_requires_admin_but_no_reason(server):
    admin = client(server, ADMIN)
    assert admin.post("/api/channel/reset", json={}).status_code == 200
    assert admin.post("/api/channel/reset", json={"reason": " "}).status_code == 200
    assert client(server, BOB).post("/api/channel/reset", json={"reason": "please"}).status_code == 403


def test_quarantine_blocks_until_reset(server):
    admin = client(server, ADMIN)
    reset(admin)
    r = send(admin, "eve_forgery", 64)
    tx = r.json()["transmission"]
    assert tx["enforcement"]["action"] == "link_quarantined"
    incident_id = tx["enforcement"]["incident_id"]
    inc = admin.get(f"/api/audit/{incident_id}").json()
    assert inc["record"]["kind"] == "incident" and admin.post("/api/audit/verify", json=inc).json()["valid"]
    assert any(c["record"]["incident_id"] == incident_id for c in admin.get("/api/incidents").json()["incidents"])
    blocked = send(admin)
    assert blocked.status_code == 423 and blocked.json()["status"] == "quarantined"
    assert blocked.json()["detail"]["incident_id"] == incident_id and blocked.json()["refusal_us"] >= 0
    topo = admin.get("/api/topology").json()["router"]["hops"]
    assert topo["alice->QR-1"]["state"] == "down" and topo["alice->QR-1"]["dropped"] >= 1
    body = reset(admin, "investigated test forgery").json()
    assert body["channel_state"]["alice->verifiers"]["state"] == "reset_pending"
    assert body["reset_record"]["chain_seq"] > inc["record"]["chain"]["seq"]
    ok = send(admin)
    assert ok.status_code == 200
    assert ok.json()["transmission"]["enforcement"]["action"] in ("probation_passed", "link_quarantined",
                                                                  "link_watch", "package_rejected")


def test_audit_chain_verifies(server):
    admin = client(server, ADMIN)
    body = admin.get("/api/audit/chain").json()
    assert body["verification"]["valid"] and body["verification"]["length"] >= 3
    kinds = {c["record"]["kind"] for c in body["certificates"]}
    assert {"transaction", "incident", "link_reset"} <= kinds
    assert client(server, BOB).get("/api/audit/chain").status_code == 403


def test_state_and_records_survive_restart(server):
    admin = client(server, ADMIN)
    reset(admin)
    tx_id = send(admin, "eve_forgery", 64).json()["transmission"]["transmission_id"]
    restarted = importlib.reload(server)  # same HEDWIG_DB and key file
    admin = client(restarted, ADMIN)
    assert send(admin).status_code == 423  # quarantine persisted
    cert = admin.get(f"/api/audit/{tx_id}").json()
    assert admin.post("/api/audit/verify", json=cert).json()["valid"] is True
    assert reset(admin).status_code == 200
