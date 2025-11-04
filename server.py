# server.py
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from collections import deque

app = FastAPI(title="Sadad Control Server")

API_KEY = "bigboss999"  # غيّرها وحافظ عليها سرّية
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

JOB_QUEUE = []

@app.post("/run")
async def run_job(request: Request):
    global JOB_QUEUE  # 👈 ضروري جدًا حتى يعدّل القائمة العامة
    data = await request.json()
    job_id = str(int(time.time()))
    data["job_id"] = job_id
    JOB_QUEUE.append(data)
    print(f"🆕 New job queued: {data}")
    return {"status": "queued", "job_id": job_id}

@app.get("/status")
def status():
    return {
        "running": running,
        "queue_size": len(jobs),
        "current_job": current_job
    }

@app.get("/jobs/next")
async def get_next_job(request: Request):
    key = request.headers.get("X-API-Key")
    if key != "RacetanSecret123":
        return {"error": "unauthorized"}

    global JOB_QUEUE
    if not JOB_QUEUE:
        return {"job": None}

    job = JOB_QUEUE.pop(0)
    print(f"📤 Dispatching job: {job}")
    return {"job": job}

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
