# ============================================================
# ✅ Sadad Control Server — (MODIFIED VERSION)
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
running_jobs: Dict[str, Dict] = {} # <-- MODIFIED: Track all running jobs by job_id
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
    # MODIFIED: Removed global 'running' flag. Just give a job if one exists.
    if not jobs:
        return {"job": None}
    job = jobs.popleft()
    job["status"] = "running"
    running_jobs[job["id"]] = job # <-- MODIFIED: Track this job as running
    print(f"🚀 Sending job {job['id']} to agent: {job['site']}")
    return {"job": job}


# ============================================================
# 🔸 Agent: report job status
# ============================================================
@app.post("/jobs/{job_id}/update")
def jobs_update(job_id: str, payload: UpdatePayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    # MODIFIED: Update the job in the 'running_jobs' dictionary
    if job_id in running_jobs:
        job = running_jobs[job_id]
        job["status"] = payload.status
        if payload.message:
            job["message"] = payload.message
        if payload.log:
            logs_store.append(payload.log[-2000:])
        
        # If job is finished, remove it from the running list
        if payload.status in ("done", "error"):
            running_jobs.pop(job_id, None) 
            
        print(f"📋 Job {job_id} updated → {payload.status}")
        return {"ok": True}
    else:
        print(f"⚠️ Received update for unknown/finished job: {job_id}")
        return {"ok": False, "detail": "Job not found or already finished"}


# ============================================================
# 🔸 Agent heartbeat + register
# ============================================================
@app.post("/update/{agent_id}")
def update_agent(agent_id: str, payload: Dict[str, Any] = None, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    payload_data = payload or {}
    agents_state.setdefault(agent_id, {"status": "idle", "logs": []})
    agents_state[agent_id]["status"] = payload_data.get("status", "idle")
    agents_state[agent_id]["last_seen"] = datetime.utcnow().isoformat()
    
    # MODIFIED: Store what job the agent is busy with
    if "job" in payload_data:
        agents_state[agent_id]["job"] = payload_data.get("job")
    elif payload_data.get("status", "idle") == "idle":
        agents_state[agent_id]["job"] = None # Clear job if agent is idle

    return {"ok": True}


@app.post("/register")
def register_agent(payload: Dict[str, Any], x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    agent_id = payload.get("agent_id")
    agents_state[agent_id] = {
        "status": payload.get("status", "idle"),
        "last_seen": datetime.utcnow().isoformat(),
        "logs": [],
        "job": None # <-- MODIFIED: Add job field on register
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
                "job": v.get("job"), # This will now be populated
                "logs": v.get("logs", []),
                "last_seen": v.get("last_seen")
            }
            for k, v in agents_state.items()
        ],
        "paused": False # Note: 'paused' logic is not implemented in server
    }


# ============================================================
# 🔸 Misc status / logs
# ============================================================
@app.get("/status")
def status():
    # MODIFIED: Report on the new 'running_jobs' dict
    return {
        "running_jobs_count": len(running_jobs),
        "queue_size": len(jobs),
        "running_jobs_list": list(running_jobs.values())
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