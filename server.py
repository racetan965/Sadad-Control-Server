# -*- coding: utf-8 -*-
from fastapi import FastAPI, Header
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import time

app = FastAPI(title="Sadad Control Server — Racetan")

API_KEY = "RacetanSecret123"
JOBS: List[Dict] = []
AGENTS: Dict[str, Dict] = {}
GLOBAL_PAUSE = False  # ⏸️ حالة التوقف العام

# ===================== MODELS =====================
class RunPayload(BaseModel):
    site: str
    amount: int
    count: int

class UpdatePayload(BaseModel):
    status: Optional[str] = None
    result: Optional[str] = None

class HeartbeatPayload(BaseModel):
    agent_id: str

def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise Exception("Unauthorized")

# ===================== JOB CREATION =====================
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
    print(f"🆕 Queued: {job}")
    return {"status": "queued", "job_id": job_id}

# ===================== JOB FETCH =====================
@app.get("/jobs/next")
def get_next_job(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    if GLOBAL_PAUSE:
        return {"job": None, "paused": True}

    global JOBS
    if not JOBS:
        return {"job": None}

    job = JOBS.pop(0)
    print(f"📤 Dispatching job: {job}")
    return {"job": job}

# ===================== JOB STATUS UPDATE =====================
@app.put("/jobs/{job_id}")
def jobs_update(job_id: str, payload: UpdatePayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    for agent_id, info in AGENTS.items():
        log_entry = f"{datetime.utcnow().isoformat()} → {payload.status or ''}: {payload.result or ''}"
        info.setdefault("logs", []).append(log_entry)

        if payload.status == "running":
            info["status"] = "busy"
            info["job"] = job_id
        elif payload.status == "done":
            info["status"] = "idle"
            info["job"] = None
        elif payload.status == "failed":
            info["status"] = "error"
        print(f"📝 {agent_id} → {log_entry}")
    return {"ok": True}

# ===================== HEARTBEAT =====================
@app.post("/heartbeat")
def heartbeat(payload: HeartbeatPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    agent_id = payload.agent_id
    if agent_id not in AGENTS:
        AGENTS[agent_id] = {"status": "idle", "job": None, "logs": [], "last_seen": time.time()}
    else:
        AGENTS[agent_id]["last_seen"] = time.time()
        if AGENTS[agent_id].get("job") is None:
            AGENTS[agent_id]["status"] = "idle"
    return {"ok": True, "paused": GLOBAL_PAUSE}

# ===================== AGENT STATUS =====================
@app.get("/agents")
def get_agents():
    now = time.time()
    data = []
    for agent_id, info in AGENTS.items():
        alive = (now - info["last_seen"]) < 30
        data.append({
            "agent_id": agent_id,
            "status": ("offline" if not alive else info.get("status", "idle")),
            "job": info.get("job"),
            "logs": info.get("logs", []),
            "last_seen": datetime.fromtimestamp(info["last_seen"]).isoformat(),
        })
    return {"agents": data, "paused": GLOBAL_PAUSE}

# ===================== GLOBAL CONTROL =====================
@app.post("/control/{action}")
def control_all(action: str, x_api_key: Optional[str] = Header(None)):
    global GLOBAL_PAUSE
    require_api_key(x_api_key)

    if action.lower() == "pause":
        GLOBAL_PAUSE = True
        print("⏸️ All agents paused.")
        return {"paused": True}
    elif action.lower() == "resume":
        GLOBAL_PAUSE = False
        print("▶️ All agents resumed.")
        return {"paused": False}
    else:
        return {"error": "invalid_action"}
