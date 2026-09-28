import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import Body, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import numpy as np
from pydantic import BaseModel

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from auth import ROLE_HOME, ROLES, SIGNER_IDENTITY, Authenticator, cookie_name
from src.quantum_engine import (
    AuditAuthority,
    ChannelQuarantined,
    NoPackageToReplay,
    Store,
    TeleportationQDS,
    ThreatScenarioConfig,
    ThreatSuite,
    ThreatType,
    build_reset_record,
    pq_provider,
    verify_certificate_report,
    verify_chain,
)
from src.quantum_engine.audit import strip_evidence
from src.quantum_engine.enforcement import LINK_FORWARD, LINK_SIGNER

app = FastAPI(title="HEDWIG V2.2 - Teleportation QDS & Threat Detection System")

templates = Jinja2Templates(directory=os.path.join(CURRENT_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(CURRENT_DIR, "static")), name="static")


def _pq_setting() -> Optional[bool]:
    v = os.environ.get("HEDWIG_AUDIT_PQ", "auto").lower()
    return True if v in ("1", "on", "true", "require") else False if v in ("0", "off", "false") else None


auth = Authenticator()
store = Store(os.environ.get("HEDWIG_DB", os.path.join(CURRENT_DIR, "data", "hedwig.db")))
audit_authority = AuditAuthority(os.environ.get(
    "HEDWIG_AUDIT_KEY", os.path.join(CURRENT_DIR, "data", "audit_ed25519.pem")), pq=_pq_setting(), store=store)
qds_engine = TeleportationQDS(backend=os.environ.get("HEDWIG_BACKEND", "qiskit"), store=store, audit=audit_authority)
engine_lock = asyncio.Lock()


class SystemState:
    def __init__(self):
        self.transmissions: List[Dict[str, Any]] = []
        self.by_id: Dict[str, Dict[str, Any]] = {}
        self.security_events: List[Dict[str, Any]] = []
        self.active_threat_setting: str = "authentic"
        self.stats = {
            "total_sent": 0,
            "verified_authentic": 0,
            "threats_detected": 0,
            "attacks_injected": 0,
            "attacks_missed": 0,
            "false_alarms": 0,
            "last_qber": 0.0,
            "watch_events": 0,
            "quarantines": 0,
            "early_aborts": 0,
            "refused_sends": 0,
        }

    def record(self, tx: Dict[str, Any]):
        self.transmissions.append(tx)
        del self.transmissions[:-500]
        self.by_id[tx["transmission_id"]] = tx
        s = self.stats
        s["total_sent"] += 1
        detected = tx["threat_report"]["is_threat_detected"]
        injected = tx["ground_truth"].get("injected_scenario", "authentic") != "authentic"
        s["threats_detected" if detected else "verified_authentic"] += 1
        s["attacks_injected"] += int(injected)
        s["attacks_missed"] += int(injected and not detected)
        s["false_alarms"] += int(detected and not injected)
        action = tx["enforcement"]["action"]
        s["watch_events"] += int(action == "link_watch")
        s["quarantines"] += int(action == "link_quarantined")
        s["early_aborts"] += int(bool(tx["latency"].get("early_abort")))
        if tx.get("channel"):
            s["last_qber"] = tx["channel"]["qber_estimate"]


state = SystemState()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {r: set() for r in ROLES}

    async def connect(self, role: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[role].add(websocket)

    def disconnect(self, role: str, websocket: WebSocket):
        self.active_connections[role].discard(websocket)

    async def send_to_role(self, role: str, event_type: str, data: Any):
        payload = json.dumps({"event": event_type, "data": data})
        for ws in list(self.active_connections[role]):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(role, ws)

    async def broadcast_transmission(self, tx: Dict[str, Any]):
        for role in ROLES:
            await self.send_to_role(role, "new_transmission", {"transmission": view_for(role, tx),
                                                               "stats": state.stats})


manager = ConnectionManager()


def view_for(role: str, tx: Dict[str, Any]) -> Dict[str, Any]:
    """Verifier dashboards never receive the injector's ground truth or the signer's private states."""
    if role == "admin":
        return tx
    return {k: v for k, v in tx.items() if k not in ("ground_truth", "alice")}


async def security_event(kind: str, detail: str, request_path: str = "", client: str = ""):
    event = {"timestamp": time.time(), "type": kind, "detail": detail, "path": request_path, "client": client}
    state.security_events.append(event)
    del state.security_events[:-500]
    await manager.send_to_role("admin", "security_event", event)


def _client(conn) -> str:
    return conn.client.host if conn.client else ""


def current_session(conn, role: str) -> Optional[Dict]:
    return auth.get_session(conn.cookies.get(cookie_name(role)), role)


def require_role(*roles: str):
    async def dependency(request: Request) -> Dict:
        for role in roles:
            sess = current_session(request, role)
            if sess:
                return sess
        held = [r for r in ROLES if current_session(request, r)]
        if not held:
            await security_event("UNAUTHENTICATED_REQUEST", f"No session for {request.method} {request.url.path}",
                                 request.url.path, _client(request))
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
        await security_event("FORBIDDEN_ROLE", f"Session role(s) {held} not permitted; requires {list(roles)}",
                             request.url.path, _client(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
    return dependency


def any_session(request: Request) -> Optional[Dict]:
    for role in ROLES:
        sess = current_session(request, role)
        if sess:
            return sess
    return None


async def require_any(request: Request) -> Dict:
    sess = any_session(request)
    if not sess:
        await security_event("UNAUTHENTICATED_REQUEST", f"No session for {request.method} {request.url.path}",
                             request.url.path, _client(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")
    return sess


# ----------------------------------------------------------------- models
class LoginRequest(BaseModel):
    username: str
    password: str


class SignAndSendRequest(BaseModel):
    message_text: str
    n_bits: int = 32
    threat_type: str = "authentic"
    tampered_text: Optional[str] = None


class ForwardRequest(BaseModel):
    message_text: Optional[str] = None


# ------------------------------------------------------------------ health & pages
@app.get("/health")
@app.head("/health")
@app.head("/")
async def health_check():
    return {"status": "ok", "version": "2.2", "simulator": "HEDWIG V2.2"}


@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/login")



@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"demo_credentials": auth.using_demo_credentials})


def _page(role: str, template: str):
    async def handler(request: Request):
        if not current_session(request, role):
            return RedirectResponse(url=f"/login?role={role}&next={ROLE_HOME[role]}", status_code=303)
        return templates.TemplateResponse(request, template, {"active_threat": state.active_threat_setting})
    return handler


app.add_api_route("/admin", _page("admin", "admin.html"), methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/alice", _page("admin", "admin.html"), methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/bob", _page("bob", "bob.html"), methods=["GET"], response_class=HTMLResponse)
app.add_api_route("/charlie", _page("charlie", "charlie.html"), methods=["GET"], response_class=HTMLResponse)


# ------------------------------------------------------------- auth API
@app.post("/api/login")
async def api_login(req: LoginRequest, request: Request):
    user = req.username.strip().lower()
    role = auth.check_password(user, req.password)
    if not role:
        await security_event("LOGIN_FAILED", f"Failed login for '{user}'", "/api/login", _client(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")
    token = auth.create_session(user, role)
    resp = JSONResponse({"status": "success", "username": user, "role": role, "redirect_url": ROLE_HOME[role]})
    resp.set_cookie(cookie_name(role), token, httponly=True, samesite="strict", path="/")
    return resp


@app.post("/api/logout")
async def api_logout(request: Request, role: str):
    if role not in ROLES:
        raise HTTPException(400, "Unknown role")
    auth.revoke(request.cookies.get(cookie_name(role)))
    resp = JSONResponse({"status": "success"})
    resp.delete_cookie(cookie_name(role), path="/")
    return resp


@app.get("/api/session")
async def api_session(request: Request):
    return {r: (current_session(request, r) or {}).get("username") for r in ROLES}


# ---------------------------------------------------------- protocol API
async def _run_and_publish(scenario: ThreatScenarioConfig, message: str, n_bits: int, sender: str):
    result = await asyncio.to_thread(qds_engine.execute_protocol, message_text=message, n_bits=n_bits,
                                     sender=sender, scenario=scenario)
    tx = result.to_dict()
    state.record(tx)
    await manager.broadcast_transmission(tx)
    return tx


def _refused(q: ChannelQuarantined, started_ns: int, extra: Optional[Dict[str, Any]] = None) -> JSONResponse:
    refusal_us = round((time.perf_counter_ns() - started_ns) / 1000, 2)
    qds_engine.latency.add(refusal_us=refusal_us)
    state.stats["refused_sends"] += 1
    return JSONResponse(status_code=423, content={
        "status": "quarantined", "link": q.link, "detail": q.info, "refusal_us": refusal_us,
        "message": "Link is quarantined after a qualifying alert. Reset it from the admin console "
                   "(a reason is required; the link then enters probation).", **(extra or {})})


@app.post("/api/sign-and-send")
async def api_sign_and_send(req: SignAndSendRequest, session: Dict = Depends(require_role("admin"))):
    started_ns = time.perf_counter_ns()
    try:
        t_type = ThreatType(req.threat_type)
    except ValueError:
        raise HTTPException(400, f"Unknown threat_type {req.threat_type}")
    sender = SIGNER_IDENTITY["admin"]   # from the authenticated session, never from the client
    n_bits = max(8, min(64, req.n_bits))
    scenario = ThreatScenarioConfig(threat_type=t_type, tampered_message_text=req.tampered_text,
                                    claimed_sender=sender)
    published = []
    async with engine_lock:
        try:
            try:
                published.append(await _run_and_publish(scenario, req.message_text, n_bits, sender))
            except NoPackageToReplay:
                # Replay needs a genuinely accepted earlier package: send one honestly, then replay it.
                published.append(await _run_and_publish(ThreatScenarioConfig(), req.message_text, n_bits, sender))
                if qds_engine.last_accepted_package is None:
                    return JSONResponse(status_code=409, content={
                        "status": "no_package", "transmissions": published,
                        "message": "The honest preamble was rejected (channel noise), so there is no accepted "
                                   "package to replay yet. Try again."})
                published.append(await _run_and_publish(scenario, req.message_text, n_bits, sender))
        except ChannelQuarantined as q:
            return _refused(q, started_ns, {"transmissions": published})
    return {"status": "success", "transmission": published[-1], "transmissions": published, "stats": state.stats}


@app.post("/api/dishonest-bob-forward")
async def api_dishonest_bob_forward(req: ForwardRequest = ForwardRequest(),
                                    session: Dict = Depends(require_role("bob"))):
    """Bob (a dishonest verifier) forwards a signature he built from his own records to Charlie."""
    bob = qds_engine.verifiers["bob"]
    if not bob.records:
        raise HTTPException(409, "Bob holds no distribution records yet; Alice must send first.")
    session_id = next(reversed(bob.records))
    message = req.message_text or "[FORWARDED BY BOB] Authorise transfer to account #9021"
    started = time.perf_counter_ns()
    async with engine_lock:
        try:
            transcript = ThreatSuite.dishonest_bob_forward(qds_engine, session_id, message, np.random.default_rng())
            result = await asyncio.to_thread(qds_engine.assess, transcript, None, started)
        except ChannelQuarantined as q:
            return _refused(q, started)
    result.ground_truth = {"injected_scenario": "dishonest_bob", "hidden_channel": None,
                           "note": "Triggered from Bob's terminal; attached after detection."}
    tx = result.to_dict()
    state.record(tx)
    await manager.broadcast_transmission(tx)
    return {"status": "success", "transmission": view_for("bob", tx)}


@app.post("/api/arm-threat")
async def api_arm_threat(payload: Dict[str, str], session: Dict = Depends(require_role("admin"))):
    new_threat = payload.get("threat_type", "authentic")
    try:
        ThreatType(new_threat)
    except ValueError:
        raise HTTPException(400, f"Unknown threat_type {new_threat}")
    state.active_threat_setting = new_threat
    await manager.send_to_role("admin", "threat_armed", {"active_threat": new_threat})
    return {"status": "success", "active_threat": new_threat}


@app.post("/api/channel/reset")
async def api_channel_reset(payload: Optional[Dict[str, str]] = Body(default=None),
                            session: Dict = Depends(require_role("admin"))):
    """Authorised reset: needs the admin role and a reason; issues a signed reset record."""
    link = (payload or {}).get("link") or None
    reason = ((payload or {}).get("reason") or "").strip()
    if link not in (None, LINK_SIGNER, LINK_FORWARD):
        raise HTTPException(400, "Unknown link")
    if len(reason) < 3:
        raise HTTPException(400, "A reset reason (at least 3 characters) is required; it is kept in the audit chain.")
    async with engine_lock:
        transitions = qds_engine.guard.request_reset(link, actor=session["username"], reason=reason)
        cert = None
        if transitions:
            record = build_reset_record(transitions, session["username"], reason)
            cert = audit_authority.issue(record, f"RST-{int(time.time() * 1000)}-{len(transitions)}")
    channel_state = qds_engine.guard.to_dict()
    for role in ROLES:
        await manager.send_to_role(role, "channel_state", channel_state)
    return {"status": "success", "channel_state": channel_state, "transitions": transitions,
            "reset_record": None if cert is None else {"payload_sha256": cert["payload_sha256"],
                                                        "chain_seq": cert["record"]["chain"]["seq"]}}


@app.get("/api/channel")
async def api_channel(session: Dict = Depends(require_any)):
    return qds_engine.guard.to_dict()


@app.get("/api/channel/transitions")
async def api_channel_transitions(session: Dict = Depends(require_role("admin"))):
    return {"transitions": store.transitions(100), "policy": qds_engine.policy.to_dict()}


@app.get("/api/topology")
async def api_topology(session: Dict = Depends(require_any)):
    return {"router": qds_engine.router.to_dict(), "channel_state": qds_engine.guard.to_dict()}


@app.get("/api/history")
async def api_history(request: Request, session: Dict = Depends(require_any)):
    role = session["role"]
    return {"transmissions": [view_for(role, t) for t in state.transmissions[-50:]],
            "stats": state.stats, "channel_state": qds_engine.guard.to_dict()}


@app.get("/api/verification/{tx_id}/{verifier}")
async def api_verification(tx_id: str, verifier: str, request: Request):
    """A verifier fetches its own verification of a transmission addressed to it."""
    tx = state.by_id.get(tx_id)
    if tx is None:
        raise HTTPException(404, "Unknown transmission")
    allowed = verifier in (tx.get("context") or {}).get("verifiers", [])
    if not allowed or verifier not in ROLES or not current_session(request, verifier):
        held = [r for r in ROLES if current_session(request, r)]
        await security_event("UNAUTHORIZED_VERIFICATION",
                             f"Verification of {tx_id} as '{verifier}' attempted by session(s) {held or 'none'}; "
                             f"addressed verifiers: {(tx.get('context') or {}).get('verifiers')}",
                             request.url.path, _client(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an authorised verifier for this transmission.")
    return {"transmission_id": tx_id, "verification": tx.get(verifier),
            "threat_report": tx["threat_report"]}


@app.get("/api/audit/chain")
async def api_audit_chain(session: Dict = Depends(require_role("admin"))):
    """The whole hash chain (evidence stripped) plus the server-side chain check."""
    certs = store.audit_chain()
    return {"verification": verify_chain(certs, audit_authority.trusted_keys()),
            "certificates": [strip_evidence(c) for c in certs]}


@app.get("/api/incidents")
async def api_incidents(session: Dict = Depends(require_any)):
    return {"incidents": [strip_evidence(c) for c in store.audit_chain(kind="incident")][-50:]}


@app.get("/api/audit/{artifact_id}")
async def api_audit(artifact_id: str, evidence: bool = True, session: Dict = Depends(require_any)):
    """Stored certificate (issued automatically at assessment / quarantine / reset time)."""
    cert = store.get_audit(artifact_id)
    if cert is None:
        raise HTTPException(404, "No audit record with that id")
    return JSONResponse(cert if evidence else strip_evidence(cert),
                        headers={"Content-Disposition": f'attachment; filename="hedwig-audit-{artifact_id}.json"'})


@app.post("/api/audit/verify")
async def api_audit_verify(cert: Dict[str, Any]):
    report = verify_certificate_report(cert, audit_authority.trusted_keys())
    return {**report, "checked_against": "this server's audit keyring (active and retired keys)"}


@app.get("/api/audit-public-key")
async def api_audit_public_key():
    return {"keys": audit_authority.trusted_keys(), "public_key_pem": audit_authority.public_key_pem,
            "post_quantum": audit_authority.post_quantum, "pq_provider": pq_provider(),
            "note": "Ed25519 is classical. Certificates are post-quantum signed only when they also carry a "
                    "verifying ML-DSA-65 signature."}


@app.post("/api/audit/rotate-key")
async def api_audit_rotate_key(session: Dict = Depends(require_role("admin"))):
    async with engine_lock:
        result = audit_authority.rotate()
    return {"status": "success", **result, "keys": audit_authority.trusted_keys()}


@app.get("/api/metrics")
async def api_metrics(session: Dict = Depends(require_role("admin"))):
    return {"latency": qds_engine.latency.to_dict(), "stats": state.stats,
            "channel_state": qds_engine.guard.to_dict(), "parameters": qds_engine.params.to_dict(),
            "policy": qds_engine.policy.to_dict(), "backend": qds_engine.backend.name,
            "audit": {"post_quantum": audit_authority.post_quantum, "pq_provider": pq_provider()}}


@app.get("/api/security-events")
async def api_security_events(session: Dict = Depends(require_role("admin"))):
    return {"events": state.security_events[-100:]}


# -------------------------------------------------------------- websocket
@app.websocket("/ws/{role}")
async def websocket_endpoint(websocket: WebSocket, role: str):
    role = role.lower()
    if role not in ROLES or not current_session(websocket, role):
        await security_event("WS_REJECTED", f"WebSocket /ws/{role} without a valid {role} session",
                             f"/ws/{role}", _client(websocket))
        await websocket.close(code=4401)
        return

    await manager.connect(role, websocket)
    await websocket.send_text(json.dumps({
        "event": "init_sync",
        "data": {
            "role": role,
            "active_threat": state.active_threat_setting if role == "admin" else None,
            "stats": state.stats,
            "channel_state": qds_engine.guard.to_dict(),
            "transmissions": [view_for(role, t) for t in state.transmissions[-5:]],
        },
    }))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(role, websocket)
    except Exception:
        manager.disconnect(role, websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("server:app", host=host, port=port)

