# ============================================================
# ✅ Sadad Control Server — Unified version (for Flutter + Agent)
# ============================================================

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from collections import deque

app = FastAPI(title="Sadad Control Server")

# 🔐 Global config
API_KEY = "bigboss999"  # same key for Flutter app + agent
jobs = deque()           # job queue
running = False
current_job = None
logs_store = []
agents_state: Dict[str, Dict[str, Any]] = {}  # agent_id -> status info


# ============================================================
# 🔸 Models
# ============================================================
class RunPayload(BaseModel):
    site: str
    amount: int
    count: int


class Job(BaseModel):
    id: str
    site: str
    amount: int
    count: int
    created_at: str
    status: str  # queued|running|done|error
    message: Optional[str] = None


class UpdatePayload(BaseModel):
    status: str   # running|done|error
    message: Optional[str] = None
    log: Optional[str] = None


# ============================================================
# 🔸 Auth helper
# ============================================================
def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ============================================================
# 🔸 Flutter: Run new job
# ============================================================
@app.post("/run")
def run_job(payload: RunPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    job_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    job = Job(
        id=job_id,
        site=payload.site,
        amount=payload.amount,
        count=payload.count,
        created_at=datetime.utcnow().isoformat() + "Z",
        status="queued"
    )
    jobs.append(job.dict())
    print(f"🆕 Job queued: {payload.site} / {payload.amount} / count={payload.count}")
    return {"status": "queued", "job_id": job_id}


# ============================================================
# 🔸 Agent: get next job
# ============================================================
@app.get("/jobs/next")
def jobs_next(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    global running, current_job
    if running or not jobs:
        return {"job": None}
    job = jobs.popleft()
    job["status"] = "running"
    running = True
    current_job = job
    print(f"🚀 Sending job to agent: {job['site']} / {job['amount']} / {job['count']}")
    return {"job": job}


# ============================================================
# 🔸 Agent: report job status
# ============================================================
@app.post("/jobs/{job_id}/update")
def jobs_update(job_id: str, payload: UpdatePayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    global running, current_job
    if current_job and current_job["id"] == job_id:
        current_job["status"] = payload.status
        if payload.message:
            current_job["message"] = payload.message
        if payload.log:
            logs_store.append(payload.log[-2000:])
        if payload.status in ("done", "error"):
            running = False
    print(f"📋 Job {job_id} updated → {payload.status}")
    return {"ok": True}


# ============================================================
# 🔸 Agent heartbeat + register
# ============================================================
@app.post("/update/{agent_id}")
def update_agent(agent_id: str, payload: Dict[str, Any] = None, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    agents_state.setdefault(agent_id, {"status": "idle", "logs": []})
    agents_state[agent_id]["status"] = (payload or {}).get("status", "idle")
    agents_state[agent_id]["last_seen"] = datetime.utcnow().isoformat()
    return {"ok": True}


@app.post("/register")
def register_agent(payload: Dict[str, Any], x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    agent_id = payload.get("agent_id")
    agents_state[agent_id] = {
        "status": payload.get("status", "idle"),
        "last_seen": datetime.utcnow().isoformat(),
        "logs": []
    }
    print(f"🖥️ Registered agent: {agent_id}")
    return {"ok": True}


# ============================================================
# 🔸 Flutter dashboard: agents grid + control
# ============================================================
@app.get("/agents")
def list_agents(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    return {
        "agents": [
            {
                "agent_id": k,
                "status": v.get("status", "idle"),
                "job": v.get("job"),
                "logs": v.get("logs", []),
                "last_seen": v.get("last_seen")
            }
            for k, v in agents_state.items()
        ],
        "paused": False
    }


@app.post("/control/{action}")
def control_all(action: str, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    print(f"⚙️ Control action: {action}")
    # optional: pause/resume logic
    return {"ok": True}


# ============================================================
# 🔸 Misc status / logs
# ============================================================
@app.get("/status")
def status():
    return {
        "running": running,
        "queue_size": len(jobs),
        "current_job": current_job
    }


@app.get("/logs")
def get_logs(limit: int = 50):
    return {"lines": logs_store[-limit:]}


# ============================================================
# 🔸 Root
# ============================================================
@app.get("/")
def home():
    return {"status": "ok", "agents": len(agents_state), "jobs_in_queue": len(jobs)}

# ============================================================
# 🔸 Run locally
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
