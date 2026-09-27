import os
import sys
import json
import time
from typing import Dict, List, Set, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Add current dir and parent dir to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from src.quantum_engine import (
    TeleportationQDS,
    ThreatScenarioConfig,
    ThreatType,
    QDSExecutionResult,
    QDSSecurityBounds
)

app = FastAPI(title="HEDWIG V2 - Teleportation QDS & Threat Detection System")

# Templates and static files
TEMPLATES_DIR = os.path.join(CURRENT_DIR, "templates")
STATIC_DIR = os.path.join(CURRENT_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Quantum Protocol Engine
qds_engine = TeleportationQDS()

# In-memory communication & telemetry state
class SystemState:
    def __init__(self):
        self.transmissions: List[Dict[str, Any]] = []
        self.active_threat_setting: str = "authentic"
        self.channel_healthy: bool = True
        self.stats = {
            "total_sent": 0,
            "verified_authentic": 0,
            "threats_quenched": 0,
            "last_qber": 0.0,
        }

state = SystemState()


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "admin": set(),
            "bob": set(),
            "charlie": set()
        }

    async def connect(self, role: str, websocket: WebSocket):
        await websocket.accept()
        if role in self.active_connections:
            self.active_connections[role].add(websocket)

    def disconnect(self, role: str, websocket: WebSocket):
        if role in self.active_connections:
            self.active_connections[role].discard(websocket)

    async def broadcast(self, event_type: str, data: Any):
        payload = json.dumps({"event": event_type, "data": data})
        for role, sockets in self.active_connections.items():
            for ws in list(sockets):
                try:
                    await ws.send_text(payload)
                except Exception:
                    self.disconnect(role, ws)

    async def send_to_role(self, role: str, event_type: str, data: Any):
        if role in self.active_connections:
            payload = json.dumps({"event": event_type, "data": data})
            for ws in list(self.active_connections[role]):
                try:
                    await ws.send_text(payload)
                except Exception:
                    self.disconnect(role, ws)

manager = ConnectionManager()


# Hardcoded credentials
VALID_CREDENTIALS = {
    "admin": {"password": "admin2026", "role": "admin", "redirect": "/admin"},
    "alice": {"password": "quantum2026", "role": "admin", "redirect": "/admin"},
    "bob": {"password": "quantum2026", "role": "bob", "redirect": "/bob"},
    "charlie": {"password": "quantum2026", "role": "charlie", "redirect": "/charlie"}
}


# Request Models
class LoginRequest(BaseModel):
    username: str
    password: str


class SignAndSendRequest(BaseModel):
    message_text: str
    n_bits: int = 16
    threat_type: str = "authentic"
    tampered_text: Optional[str] = None
    claimed_sender: str = "Alice"


# Routes - Health & Root
@app.head("/")
@app.head("/health")
@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")


@app.get("/admin", response_class=HTMLResponse)
@app.get("/alice", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"active_threat": state.active_threat_setting}
    )


@app.get("/bob", response_class=HTMLResponse)
async def bob_page(request: Request):
    return templates.TemplateResponse(request=request, name="bob.html")


@app.get("/charlie", response_class=HTMLResponse)
async def charlie_page(request: Request):
    return templates.TemplateResponse(request=request, name="charlie.html")


# Routes - REST API
@app.post("/api/login")
async def api_login(req: LoginRequest):
    user = req.username.strip().lower()
    pw = req.password.strip()

    if user in VALID_CREDENTIALS and VALID_CREDENTIALS[user]["password"] == pw:
        info = VALID_CREDENTIALS[user]
        return {
            "status": "success",
            "username": user,
            "role": info["role"],
            "redirect_url": info["redirect"]
        }
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")


@app.post("/api/sign-and-send")
async def api_sign_and_send(req: SignAndSendRequest):
    try:
        t_type = ThreatType(req.threat_type)
    except ValueError:
        t_type = ThreatType.AUTHENTIC

    scenario = ThreatScenarioConfig(
        threat_type=t_type,
        tampered_message_text=req.tampered_text,
        claimed_sender=req.claimed_sender
    )

    # Execute physical quantum protocol
    result = qds_engine.execute_protocol(
        message_text=req.message_text,
        n_bits=max(8, min(64, req.n_bits)),
        scenario=scenario
    )

    result_dict = result.to_dict()

    # Update state statistics
    state.stats["total_sent"] += 1
    state.stats["last_qber"] = result.channel_qber
    if result.threat_report.is_threat_detected:
        state.stats["threats_quenched"] += 1
    else:
        state.stats["verified_authentic"] += 1

    state.transmissions.append(result_dict)

    # Broadcast real-time results via WebSockets
    await manager.broadcast("new_transmission", {
        "transmission": result_dict,
        "stats": state.stats
    })

    return {
        "status": "success",
        "transmission": result_dict,
        "stats": state.stats
    }


@app.post("/api/dishonest-bob-forward")
async def api_dishonest_bob_forward():
    """Triggered by Bob's terminal to simulate Dishonest Bob forwarding counterfeit to Charlie."""
    scenario = ThreatScenarioConfig(
        threat_type=ThreatType.DISHONEST_BOB,
        claimed_sender="Alice (Forwarded by Bob)"
    )
    result = qds_engine.execute_protocol(
        message_text="[BOB FORWARDED] Critical Authorization token #9021",
        n_bits=16,
        scenario=scenario
    )
    result_dict = result.to_dict()

    state.stats["total_sent"] += 1
    state.stats["last_qber"] = result.channel_qber
    state.stats["threats_quenched"] += 1
    state.transmissions.append(result_dict)

    await manager.broadcast("new_transmission", {
        "transmission": result_dict,
        "stats": state.stats
    })

    return {"status": "success", "transmission": result_dict}


@app.get("/api/history")
async def api_history():
    return {
        "transmissions": state.transmissions,
        "stats": state.stats
    }


@app.post("/api/arm-threat")
async def api_arm_threat(payload: Dict[str, str]):
    new_threat = payload.get("threat_type", "authentic")
    state.active_threat_setting = new_threat
    await manager.broadcast("threat_armed", {"active_threat": new_threat})
    return {"status": "success", "active_threat": new_threat}


# WebSocket endpoint
@app.websocket("/ws/{role}")
async def websocket_endpoint(websocket: WebSocket, role: str):
    role = role.lower()
    if role not in ["admin", "bob", "charlie"]:
        await websocket.close()
        return

    await manager.connect(role, websocket)

    # Send initial state sync
    await websocket.send_text(json.dumps({
        "event": "init_sync",
        "data": {
            "role": role,
            "active_threat": state.active_threat_setting,
            "stats": state.stats,
            "transmissions": state.transmissions[-5:] if state.transmissions else []
        }
    }))

    try:
        while True:
            data = await websocket.receive_text()
            # Heartbeat or client ping
    except WebSocketDisconnect:
        manager.disconnect(role, websocket)
    except Exception:
        manager.disconnect(role, websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
