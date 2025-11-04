from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import uvicorn

app = FastAPI()

API_KEY = "RacetanSecret123"

agents: List[Dict] = []
jobs: List[Dict] = []
paused = False


# =========================================================
# 🔐 AUTH
# =========================================================
def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")


# =========================================================
# 📡 MODELS
# =========================================================
class RunPayload(BaseModel):
    site: str
    amount: int
    count: int


class UpdatePayload(BaseModel):
    status: Optional[str] = None
    job: Optional[str] = None
    log: Optional[str] = None


class RegisterPayload(BaseModel):
    agent_id: str


# =========================================================
# 🧠 ROUTES
# =========================================================

@app.get("/")
def home():
    return {"message": "✅ Sadad Control Server Running"}


@app.get("/status")
def status(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    return {
        "running": any(a["status"] == "busy" for a in agents),
        "queue_size": len(jobs),
        "current_job": next((a["job"] for a in agents if a["status"] == "busy"), None)
    }


@app.get("/agents")
def list_agents(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    return {"agents": agents, "paused": paused}


@app.post("/register")
def register_agent(payload: RegisterPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    existing = next((a for a in agents if a["agent_id"] == payload.agent_id), None)
    if existing:
        existing["last_seen"] = datetime.utcnow().isoformat()
        existing["status"] = "idle"
    else:
        agents.append({
            "agent_id": payload.agent_id,
            "status": "idle",
            "job": None,
            "logs": [],
            "last_seen": datetime.utcnow().isoformat()
        })
    return {"ok": True}


@app.post("/run")
def run_job(payload: RunPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    job_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    job = {
        "id": job_id,
        "site": payload.site,
        "amount": payload.amount,
        "count": payload.count,
        "created_at": datetime.utcnow().isoformat(),
        "status": "queued"
    }
    jobs.append(job)
    return {"status": "queued", "job_id": job_id}


@app.post("/next-job")
def get_next_job(x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    if paused or not jobs:
        return {"job": None}
    return {"job": jobs.pop(0)}


@app.post("/update/{agent_id}")
def jobs_update(agent_id: str, payload: UpdatePayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if payload.status:
        agent["status"] = payload.status
    if payload.job:
        agent["job"] = payload.job
    if payload.log:
        agent["logs"].append(payload.log)
        if len(agent["logs"]) > 50:
            agent["logs"].pop(0)

    agent["last_seen"] = datetime.utcnow().isoformat()
    return {"ok": True}


@app.post("/control/{action}")
def control(action: str, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    global paused
    if action == "pause":
        paused = True
    elif action == "resume":
        paused = False
    return {"paused": paused}


# =========================================================
# 🚀 START
# =========================================================
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=10000)
