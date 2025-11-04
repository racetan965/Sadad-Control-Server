# server.py
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from collections import deque

app = FastAPI(title="Sadad Control Server")

API_KEY = "CHANGE_ME"  # غيّرها وحافظ عليها سرّية
jobs = deque()         # صف طلبات بسيط بالذاكرة
running = False
current_job = None
logs_store = []        # آخر لوجات قصيرة (للعرض السريع)

class RunPayload(BaseModel):
    site: str              # storekuwaitkw | gamestoreskw | playstoreskw
    amount: int            # 5/10/15/20/30
    count: int

class Job(BaseModel):
    id: str
    site: str
    amount: int
    count: int
    created_at: str
    status: str  # queued|running|done|error
    message: Optional[str] = None

def require_api_key(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

@app.post("/run")
def run_job(payload: RunPayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    job_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    job = Job(
        id=job_id,
        site=payload.site,
        amount=payload.amount,
        count=payload.count,
        created_at=datetime.utcnow().isoformat()+"Z",
        status="queued"
    )
    jobs.append(job.dict())
    return {"status":"queued","job_id":job_id}

@app.get("/status")
def status():
    return {
        "running": running,
        "queue_size": len(jobs),
        "current_job": current_job
    }

@app.get("/jobs/next")
def jobs_next(x_api_key: Optional[str] = Header(None)):
    # يُستدعى من الــ Agent على ويندوز ليأخذ أول مهمة
    require_api_key(x_api_key)
    global running, current_job
    if running or not jobs:
        return {"job": None}
    job = jobs.popleft()
    job["status"] = "running"
    running = True
    current_job = job
    return {"job": job}

class UpdatePayload(BaseModel):
    status: str   # running|done|error
    message: Optional[str] = None
    log: Optional[str] = None

@app.post("/jobs/{job_id}/update")
def jobs_update(job_id: str, payload: UpdatePayload, x_api_key: Optional[str] = Header(None)):
    require_api_key(x_api_key)
    global running, current_job
    if current_job and current_job["id"] == job_id:
        current_job["status"] = payload.status
        if payload.message:
            current_job["message"] = payload.message
        if payload.log:
            logs_store.append(payload.log[-2000:])  # احتفظ بآخر نص قصير
        if payload.status in ("done","error"):
            running = False
            # نترك current_job مرجِعًا حتى يراه /status
    return {"ok": True}

@app.get("/logs")
def get_logs(limit: int = 50):
    # آخر 50 سطر لوج مثلاً
    return {"lines": logs_store[-limit:]}
