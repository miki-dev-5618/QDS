import asyncio
import csv
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import Body, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
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
    ChannelModel,
    ChannelQuarantined,
    NoPackageToReplay,
    Store,
    TeleportationQDS,
    ThreatScenarioConfig,
    ThreatSuite,
    ThreatType,
    build_reset_record,
    make_readout_channel,
    pq_provider,
    verify_certificate_report,
    verify_chain,
)
from src.quantum_engine import noise_profiles
from src.quantum_engine.audit import strip_evidence
from src.quantum_engine.enforcement import LINK_FORWARD, LINK_SIGNER
from src.quantum_engine.roster import ConfigurationError, SessionConfig, limits as roster_limits
from src.quantum_engine.topology import Topology, TopologyError
from src.quantum_engine.enforcement import edge_scope, EMERGENCY
from src.quantum_engine.routing import freshness
from src.quantum_engine.monitoring import probe_edges
from src.quantum_engine.routing_demo import run_failover_demo

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
qds_engine = TeleportationQDS(backend=os.environ.get("HEDWIG_BACKEND", "qiskit"), store=store, audit=audit_authority,
                              topology=os.environ.get("HEDWIG_TOPOLOGY"))
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
        injected = (tx["ground_truth"].get("injected_scenario", "authentic") != "authentic" or
                    bool(tx["ground_truth"].get("traversed_injected_edges")))
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


_PRIVATE_EVIDENCE = ("eliminated_states", "held_tokens")


def _strip_private(v: Optional[Dict[str, Any]], role: str) -> Optional[Dict[str, Any]]:
    """Another participant's private distribution evidence is never shown to a verifier."""
    if not v or v.get("verifier") == role:
        return v
    return {k: val for k, val in v.items() if k not in _PRIVATE_EVIDENCE}


def view_for(role: str, tx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifier dashboards never receive the injector's ground truth, the signer's private states,
    other participants' private distribution evidence, or the per-recipient symmetrisation decisions.
    Extra roster members are visible in the admin view only (initial release).
    """
    if role == "admin":
        return tx
    out = {k: v for k, v in tx.items() if k not in ("ground_truth", "alice", "symmetrisation")}
    for key in ("bob", "charlie"):
        out[key] = _strip_private(tx.get(key), role)
    out["additional_verifications"] = [_strip_private(v, role) for v in tx.get("additional_verifications", [])
                                       if v.get("verifier") in ("bob", "charlie")]
    if "participants" in tx:
        out["participants"] = [r for r in tx["participants"] if r.get("verifier") in ("bob", "charlie")]
    if "events" in tx:
        out["events"] = [e for e in tx["events"] if e.get("verifier") in ("bob", "charlie")]
    if tx.get("routing"):
        out["routing"] = route_view(role, tx["routing"])
    return out


def route_view(role, record):
    if role == "admin":
        return record
    import copy
    result = copy.deepcopy(record)
    plan = result["plan"]
    if role not in plan["roster"]:
        return None
    plan["roster"] = [role]
    plan["routes"] = {role: plan["routes"][role]}
    plan["candidates"] = {role: plan["candidates"][role]}
    plan.pop("scope_snapshot", None)
    execution = result.get("execution")
    if execution:
        stats = execution["recipients"][role]
        execution["recipients"] = {role: stats}
        execution["edges"] = stats["edges"]
        execution["route_tests"] = {role: execution["route_tests"][role]}
    return result


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
    noise_profile: Optional[str] = "depolarizing"
    readout_p01: Optional[float] = 0.0
    readout_p10: Optional[float] = 0.0
    readout_location: Optional[str] = "both"
    eta_loss: Optional[float] = 0.0
    # Optional N-verifier extension (defaults keep the original Bob + Charlie workflow)
    n_verifiers: Optional[int] = None
    roster: Optional[List[str]] = None
    delivery: str = "direct"
    max_depth: Optional[int] = None
    dishonest_verifier: Optional[str] = None
    forward_alteration: str = "message"
    cloner_type: Optional[str] = "universal"
    cloning_rate: Optional[float] = 1.0
    partial_intercept_fraction: Optional[float] = 0.05
    collective_theta: Optional[float] = None
    noise_param: Optional[float] = None   # the selected profile's main parameter (see /api/noise-profiles)


LEGACY_NOISE_PROFILES = (None, "depolarizing", "readout", "lossy")   # values the original fields already handled


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


# ------------------------------------------------------------- results page (D10)
RESULTS_DIR = os.path.join(CURRENT_DIR, "experiments", "results")   # written by run_experiments.py
RESULT_TABS = [  # (tab id, title, step folders under RESULTS_DIR)
    ("roc", "ROC", ["roc"]),
    ("ablations", "Ablations", ["ablate_adaptive", "ablate_early_abort", "ablate_escalation", "ablate_tiers"]),
    ("baselines", "Baselines", ["baselines"]),
    ("tightness", "Tightness", ["tightness", "sweep_collective"]),
    ("hardware", "Hardware run", ["hardware"]),
]
MAX_TABLE_ROWS = 50


def _results_section(step: str) -> Dict[str, Any]:
    folder = os.path.join(RESULTS_DIR, step)
    files = sorted(f for f in os.listdir(folder) if not f.startswith(".") and f != "run.log") \
        if os.path.isdir(folder) else []
    tables = []
    for name in (f for f in files if f.endswith(".csv")):
        with open(os.path.join(folder, name), newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        tables.append({"name": name, "header": rows[0] if rows else [], "rows": rows[1:MAX_TABLE_ROWS + 1],
                       "more": max(0, len(rows) - 1 - MAX_TABLE_ROWS)})
    return {"step": step, "files": files, "images": [f for f in files if f.endswith(".png")], "tables": tables}


def _results_context() -> Dict[str, Any]:
    try:
        with open(os.path.join(RESULTS_DIR, "manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        manifest = None
    tabs = [{"id": tid, "title": title, "sections": [_results_section(step) for step in steps]}
            for tid, title, steps in RESULT_TABS]
    return {"tabs": tabs, "manifest": manifest}


@app.get("/results", response_class=HTMLResponse)
async def results_page(request: Request):
    if not any_session(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "results.html", _results_context())


@app.get("/results/files/{step}/{name}")
async def results_file(step: str, name: str, session: Dict = Depends(require_any)):
    root = os.path.realpath(RESULTS_DIR)
    path = os.path.realpath(os.path.join(root, step, name))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        raise HTTPException(404, "Not generated yet")
    return FileResponse(path)


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
async def _run_and_publish(scenario: ThreatScenarioConfig, message: str, n_bits: int, sender: str,
                           channel: Optional[ChannelModel] = None, config: Optional[SessionConfig] = None):
    result = await asyncio.to_thread(qds_engine.execute_protocol, message_text=message, n_bits=n_bits,
                                     sender=sender, scenario=scenario, channel=channel, config=config)
    tx = result.to_dict()
    tx["noise"] = noise_profiles.describe_channel(channel or qds_engine.default_channel)
    state.record(tx)
    await manager.broadcast_transmission(tx)
    return tx


def _refused(q: ChannelQuarantined, started_ns: int, extra: Optional[Dict[str, Any]] = None) -> JSONResponse:
    refusal_us = round((time.perf_counter_ns() - started_ns) / 1000, 2)
    qds_engine.latency.add(refusal_us=refusal_us)
    state.stats["refused_sends"] += 1
    return JSONResponse(status_code=423, content={
        **q.payload(), "refusal_us": refusal_us, **(extra or {})})


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
                                    claimed_sender=sender, dishonest_verifier=req.dishonest_verifier,
                                    forward_alteration=req.forward_alteration)
    try:   # unsupported combinations are configuration errors, reported before any evidence is prepared
        config = SessionConfig.build(roster=req.roster, n_verifiers=req.n_verifiers, delivery=req.delivery,
                                     max_depth=req.max_depth)
        ThreatSuite.validate(scenario, config)
    except ConfigurationError as e:
        raise HTTPException(400, f"Configuration error: {e}")

    # Optional channel noise configuration
    channel = None
    try:
        profile = noise_profiles.canonical(req.noise_profile)
        if req.noise_param is not None or req.noise_profile not in LEGACY_NOISE_PROFILES:
            channel = noise_profiles.build_channel(profile, req.noise_param)
    except noise_profiles.NoiseProfileError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    if channel is None:
        if req.noise_profile == "readout" or (req.readout_p01 and req.readout_p01 > 0) or (req.readout_p10 and req.readout_p10 > 0):
            channel = make_readout_channel(
                p01=req.readout_p01 or 0.0,
                p10=req.readout_p10 or 0.0,
                location=req.readout_location or "both",
            )
        elif req.noise_profile == "lossy" or (req.eta_loss and req.eta_loss > 0):
            channel = make_lossy_channel(eta_loss=req.eta_loss or 0.1)

    published = []
    async with engine_lock:
        try:
            try:
                published.append(await _run_and_publish(scenario, req.message_text, n_bits, sender, channel=channel,
                                                        config=config))
            except NoPackageToReplay:
                # Replay needs a genuinely accepted earlier package: send one honestly, then replay it.
                published.append(await _run_and_publish(ThreatScenarioConfig(), req.message_text, n_bits, sender,
                                                        channel=channel, config=config))
                if qds_engine.last_accepted_package is None:
                    return JSONResponse(status_code=409, content={
                        "status": "no_package", "transmissions": published,
                        "message": "The honest preamble was rejected (channel noise), so there is no accepted "
                                   "package to replay yet. Try again."})
                published.append(await _run_and_publish(scenario, req.message_text, n_bits, sender, channel=channel,
                                                        config=config))
        except ChannelQuarantined as q:
            return _refused(q, started_ns, {"transmissions": published})
        except ConfigurationError as exc:
            raise HTTPException(400, str(exc))
    return {"status": "success", "transmission": published[-1], "transmissions": published, "stats": state.stats}


@app.get("/api/noise-profiles")
async def api_noise_profiles(session: Dict = Depends(require_any)):
    """Profiles for the admin noise selector: availability, parameter range, and the server's default channel."""
    return {"profiles": noise_profiles.catalogue(),
            "default": noise_profiles.describe_channel(qds_engine.default_channel)}


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
    """Authorised reset: needs the admin role; issues a signed reset record."""
    link = (payload or {}).get("link") or None
    reason = ((payload or {}).get("reason") or "").strip() or "admin reset"
    if link is not None and (link not in qds_engine.guard.to_dict() or link == EMERGENCY):
        raise HTTPException(400, "Unknown link")
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


@app.get("/api/roster")
async def api_roster(session: Dict = Depends(require_role("admin"))):
    """Enrolled identities and supported configuration limits of the N-verifier extension."""
    return {**roster_limits(), "default": SessionConfig().to_dict(),
            "scope": "Optional recipient-scaling extension: more pre-enrolled verifiers can independently "
                     "authenticate one signer's message. It adds no security by itself, is not universal "
                     "verification and is not multi-party approval; collusion is not covered."}


@app.get("/api/sessions/{session_id}/events")
async def api_session_events(session_id: str, session: Dict = Depends(require_role("admin"))):
    """Durable event history of one session (admin only): roster, every verification event, parent links."""
    stored = store.get_session(session_id)
    events = qds_engine.ledger.events(session_id)
    if stored is None and not events:
        raise HTTPException(404, "Unknown session")
    return {"session": stored, "events": events,
            "note": "Audit history only: one-time quantum evidence is not recoverable for new verification."}


@app.get("/api/channel")
async def api_channel(session: Dict = Depends(require_any)):
    return qds_engine.guard.to_dict()


@app.get("/api/channel/transitions")
async def api_channel_transitions(session: Dict = Depends(require_role("admin"))):
    return {"transitions": store.transitions(100), "policy": qds_engine.policy.to_dict()}


@app.get("/api/topology")
async def api_topology(session: Dict = Depends(require_any)):
    topology = qds_engine.topology
    probes = store.get_json("edge_probes", {})
    states = qds_engine.guard.to_dict()
    edges = [{**e.to_dict(), "scope": edge_scope(e.id, topology.digest),
        "state": states.get(edge_scope(e.id, topology.digest), {}).get("state", "open"),
        "monitoring": freshness(probes.get(edge_scope(e.id, topology.digest)), qds_engine.clock(), qds_engine.routing_policy),
        "probe": probes.get(edge_scope(e.id, topology.digest)) if session["role"] == "admin" else None}
        for e in topology.edges.values()]
    router = qds_engine.router.to_dict()
    if session["role"] != "admin":
        router = {"note": router["note"]}
    return {"router": router, "channel_state": states, "topology": topology.to_dict(),
        "digest": topology.digest, "edges": edges, "timestamp": qds_engine.clock(),
        "policy": qds_engine.routing_policy.__dict__,
        "injections": {k: v.__dict__ for k, v in qds_engine.edge_injections.items()} if session["role"] == "admin" else None}


@app.post("/api/topology")
async def api_activate_topology(payload: Dict[str, Any] = Body(...), session: Dict = Depends(require_role("admin"))):
    async with engine_lock:
        try:
            document = Topology.preset(payload["preset"]).to_dict() if isinstance(payload.get("preset"), str) else payload.get("topology", payload)
            topology = qds_engine.activate_topology(document, session["username"])
        except (TopologyError, ValueError) as exc:
            raise HTTPException(400, str(exc))
    return {"status": "success", "topology": topology.to_dict(), "digest": topology.digest}


@app.get("/api/routing/history")
async def api_route_history(session: Dict = Depends(require_any)):
    rows = [route_view(session["role"], row) for row in store.route_history()]
    return {"sessions": [r for r in rows if r is not None]}


@app.post("/api/routing/preview")
async def api_route_preview(payload: Dict[str, Any] = Body(default={}), session: Dict = Depends(require_role("admin"))):
    try:
        config = SessionConfig.build(roster=payload.get("roster"), n_verifiers=payload.get("n_verifiers"),
            delivery=payload.get("delivery", "direct"), max_depth=payload.get("max_depth"))
    except (ConfigurationError, ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))
    return qds_engine.preview_routes(config)


@app.post("/api/routing/demo")
async def api_route_demo(session: Dict = Depends(require_role("admin"))):
    try:
        report = await asyncio.to_thread(run_failover_demo, qds_engine.backend.name, qds_engine.params)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    artifact = "FAILOVER-" + __import__("uuid").uuid4().hex
    report["test_id"] = artifact
    store.put_json(artifact, report)
    audit_authority.issue({"version": "hedwig-audit/3", "kind": "routing_self_test", "issued_at": qds_engine.clock(),
        "report": report}, artifact)
    return report


@app.get("/api/routing/refusals")
async def api_route_refusals(session: Dict = Depends(require_role("admin"))):
    return {"refusals": store.route_refusals()}


@app.get("/api/sessions/{session_id}/routes")
async def api_session_routes(session_id: str, session: Dict = Depends(require_any)):
    row = store.route_session(session_id)
    result = route_view(session["role"], row) if row else None
    if result is None:
        raise HTTPException(404, "No authorized route history for this session")
    return result


@app.post("/api/routing/fault")
async def api_route_fault(payload: Dict[str, Any] = Body(...), session: Dict = Depends(require_role("admin"))):
    """Experimental ground truth is separate from observed detector evidence."""
    eid, action = payload.get("edge"), payload.get("action", "manual")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise HTTPException(400, "A reason is required")
    if not isinstance(eid, str) or eid not in qds_engine.topology.edges:
        raise HTTPException(400, "Unknown edge")
    scope = edge_scope(eid, qds_engine.topology.digest)
    if action == "manual":
        try:
            transition = await asyncio.to_thread(qds_engine.guard.manual, scope,
                payload.get("state", "quarantined"), session["username"], reason)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    elif action in ("attack", "clear_attack"):
        async with engine_lock:
            if eid not in qds_engine.topology.edges:
                raise HTTPException(400, "Topology changed; select a current edge")
            if action == "attack":
                qds_engine.edge_injections[eid] = ChannelModel(depolarizing=0, intercept_rate=1.0)
            else:
                qds_engine.edge_injections.pop(eid, None)
        transition = None
    else:
        raise HTTPException(400, "Unknown action")
    event = {"edge": eid, "scope": scope, "action": action, "actor": session["username"], "reason": reason,
                 "timestamp": qds_engine.clock(), "experimental_ground_truth": True, "transition": transition}
    artifact = "FAULT-" + __import__("uuid").uuid4().hex
    store.put_json(artifact, event)
    audit_authority.issue({"version": "hedwig-audit/3", "kind": "manual_fault", "issued_at": qds_engine.clock(),
                               "event": event}, artifact)
    if transition and transition.get("incident_id"):
        audit_authority.issue({"version": "hedwig-audit/3", "kind": "incident", "issued_at": qds_engine.clock(),
            "incident_id": transition["incident_id"], "link": scope, "scope_label": eid,
            "experimental_ground_truth": True,
            "trigger": {"classification": "MANUAL_FAULT_INJECTION", "evidence_p": None},
            "event": event}, transition["incident_id"])
    return {"status": "success", "event": event}


@app.post("/api/routing/probe")
async def api_route_probe(payload: Dict[str, Any] = Body(...), session: Dict = Depends(require_role("admin"))):
    async with engine_lock:
        try:
            ids = payload.get("edges", list(qds_engine.topology.edges))
            if not isinstance(ids, list) or any(not isinstance(e, str) for e in ids):
                raise ValueError("edges must be an array of edge IDs")
            observations = await asyncio.to_thread(probe_edges, qds_engine, ids, np.random.default_rng(), payload.get("count", 512))
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    return {"status": "success", "observations": observations}


@app.post("/api/routing/emergency")
async def api_route_emergency(payload: Dict[str, Any] = Body(...), session: Dict = Depends(require_role("admin"))):
    if type(payload.get("enabled")) is not bool or not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
        raise HTTPException(400, "enabled boolean and reason are required")
    change = await asyncio.to_thread(qds_engine.guard.emergency, payload["enabled"], session["username"], payload["reason"])
    audit_authority.issue({"version": "hedwig-audit/3", "kind": "emergency_stop", "issued_at": qds_engine.clock(),
        "transition": change}, "STOP-" + __import__("uuid").uuid4().hex)
    return {"status": "success", "transition": change}


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
    if session["role"] != "admin" and (cert["record"].get("kind") in ("manual_fault", "edge_probe", "topology_activation", "emergency_stop", "routing_self_test") or cert["record"].get("experimental_ground_truth")):
        raise HTTPException(403, "This audit record is admin-only")
    return JSONResponse(cert if evidence and session["role"] == "admin" else strip_evidence(cert),
                        headers={"Content-Disposition": f'attachment; filename="hedwig-audit-{artifact_id}.json"'})


@app.post("/api/audit/verify")
async def api_audit_verify(cert: Dict[str, Any]):
    report = verify_certificate_report(cert, audit_authority.trusted_keys())
    return {**report, "checked_against": "this server's audit keyring (active and retired keys)"}


@app.get("/api/audit-public-key")
async def api_audit_public_key():
    return {"keys": audit_authority.trusted_keys(), "public_key_pem": audit_authority.public_key_pem,
            "post_quantum": audit_authority.post_quantum, "pq_provider": pq_provider(),
            "key_provider": audit_authority.provider.name,
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
            "audit": {"post_quantum": audit_authority.post_quantum, "pq_provider": pq_provider(),
                      "key_provider": audit_authority.provider.name}}


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

