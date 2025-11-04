# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, Header
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import time

app = FastAPI(title="Sadad Control Server — Racetan")

# ==============================
# GLOBAL STATE
# ==============================
API_KEY = "RacetanSecret123"
JOBS: List[Dict] = []
AGENTS: Dict[str, Dict] = {}  # {agent_id: {last_seen, status, job_id}}

# ==============================
# PAYLOAD MODELS
# ==============================
class RunPayload(BaseModel):
    site: str
    amount: int
    count: int

class UpdatePayload(BaseModel):
    status: Optional[str] = None
    result: Optional[str] = None

class HeartbeatPayload(BaseModel):
    agent_id: str

# ==============================
# SECURITY
# ==============================
def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise Exception("Unauthorized")

# ==============================
# JOB CREATION (FROM PHONE / DASHBOARD)
# ==============================
@app.post("/run")
def run_job(payload: RunPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    job_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    job = {
        "id": job_id,
        "site": payload.site,
        "amount": payload.amount,
        "count": payload.count,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "queued",
    }
    JOBS.append(job)
    print(f"🆕 New job queued: {job}")
    return {"status": "queued", "job_id": job_id}

# ==============================
# AGENTS REQUEST JOBS
# ==============================
@app.get("/jobs/next")
def get_next_job(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    global JOBS
    if not JOBS:
        return {"job": None}
    job = JOBS.pop(0)
    print(f"📤 Dispatching job: {job}")
    return {"job": job}

# ==============================
# JOB STATUS UPDATE (from Agent)
# ==============================
@app.put("/jobs/{job_id}")
def jobs_update(job_id: str, payload: UpdatePayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    print(f"📝 Job {job_id} updated: {payload.dict()}")
    for j in JOBS:
        if j["id"] == job_id:
            j["status"] = payload.status or j.get("status", "unknown")
            j["result"] = payload.result or ""
    return {"ok": True}

# ==============================
# AGENT HEARTBEAT
# ==============================
@app.post("/heartbeat")
def heartbeat(payload: HeartbeatPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    AGENTS[payload.agent_id] = {
        "last_seen": time.time(),
        "status": "alive"
    }
    return {"ok": True}

# ==============================
# SERVER STATUS
# ==============================
@app.get("/status")
def status():
    running = any(a.get("status") == "alive" for a in AGENTS.values())
    return {
        "running": running,
        "queue_size": len(JOBS),
        "current_job": JOBS[0] if JOBS else None,
        "agents": list(AGENTS.keys())
    }

# ==============================
# SIMPLE DASHBOARD (HTML)
# ==============================
@app.get("/dashboard")
def dashboard():
    html = """
    <html><head><meta charset='utf-8'><title>Sadad Control Dashboard</title>
    <style>
    body {font-family:Arial, sans-serif; background:#111; color:#eee; padding:20px;}
    table {width:100%; border-collapse:collapse; margin-top:20px;}
    th, td {border:1px solid #333; padding:8px; text-align:center;}
    th {background:#222;}
    tr:nth-child(even){background:#1b1b1b;}
    .ok {color:lime;}
    .dead {color:red;}
    </style></head><body>
    <h2>🖥️ Sadad Control Dashboard</h2>
    <h3>Queued Jobs: """ + str(len(JOBS)) + """</h3>
    <table><tr><th>Agent ID</th><th>Status</th><th>Last Seen</th></tr>
    """

    now = time.time()
    for agent_id, info in AGENTS.items():
        alive = (now - info["last_seen"]) < 30
        color_class = "ok" if alive else "dead"
        html += f"<tr><td>{agent_id}</td><td class='{color_class}'>{'🟢 Alive' if alive else '🔴 Offline'}</td><td>{datetime.fromtimestamp(info['last_seen']).strftime('%H:%M:%S')}</td></tr>"

    html += "</table></body></html>"
    return html
