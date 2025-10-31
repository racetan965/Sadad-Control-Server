# control-server/main.py
import os, io, csv, time, uuid, json, random, threading
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

# ===== Optional Redis (Upstash/Render) =====
USE_REDIS = bool(os.environ.get("REDIS_URL"))
if USE_REDIS:
    import redis
    r = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
else:
    # In-memory fallback (MVP)
    r_store = {
        "agents": {},      # agent_id -> dict
        "jobs": {},        # job_id -> dict
        "queues": {},      # job_id -> [task_id,...]
        "tasks": {},       # task_id -> dict
    }

def _hset(key, mapping):
    if USE_REDIS:
        r.hset(key, mapping=mapping)
    else:
        prefix, _, kid = key.partition(":")
        if prefix == "agent":
            r_store["agents"][kid] = {**r_store["agents"].get(kid, {}), **mapping}
        elif prefix == "job":
            r_store["jobs"][kid] = {**r_store["jobs"].get(kid, {}), **mapping}
        elif prefix == "task":
            r_store["tasks"][kid] = {**r_store["tasks"].get(kid, {}), **mapping}

def _hgetall(key):
    if USE_REDIS:
        return r.hgetall(key)
    else:
        prefix, _, kid = key.partition(":")
        if prefix == "agent": return r_store["agents"].get(kid, {})
        if prefix == "job":   return r_store["jobs"].get(kid, {})
        if prefix == "task":  return r_store["tasks"].get(kid, {})
        return {}

def _lpop(qkey):
    if USE_REDIS:
        return r.lpop(qkey)
    else:
        job_id = qkey.split(":")[1]
        q = r_store["queues"].get(job_id, [])
        return q.pop(0) if q else None

def _rpush(qkey, val):
    if USE_REDIS:
        r.rpush(qkey, val)
    else:
        job_id = qkey.split(":")[1]
        r_store["queues"].setdefault(job_id, []).append(val)

def _keys(pattern):
    if USE_REDIS:
        return r.keys(pattern)
    else:
        if pattern.startswith("task:"):
            return [f"task:{k}" for k in r_store["tasks"].keys()]
        if pattern.startswith("job:") and not pattern.endswith(":queue"):
            return [f"job:{k}" for k in r_store["jobs"].keys()]
        return []

app = FastAPI(title="Distributed Sadad Controller")

# ======== Google Sheets =========
import gspread
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_JSON = os.environ.get("SERVICE_ACCOUNT_JSON", "")
SHEET_ID = os.environ.get("SHEET_ID", "")  # spreadsheet id
SHEET_MAP = {5:"Links-5",10:"Links-10",15:"Links-15",20:"Links-20",30:"Links-30"}

_gs_lock = threading.Lock()
_gs_client = None
def _gs():
    global _gs_client
    if _gs_client: return _gs_client
    if not SERVICE_ACCOUNT_JSON or not SHEET_ID:
        raise RuntimeError("Missing SERVICE_ACCOUNT_JSON or SHEET_ID")
    info = json.loads(SERVICE_ACCOUNT_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    _gs_client = gspread.authorize(creds)
    return _gs_client

def append_to_sheet(price:int, row:List[str]):
    ws_name = SHEET_MAP.get(price)
    if not ws_name: return
    with _gs_lock:
        sh = _gs().open_by_key(SHEET_ID)
        ws = sh.worksheet(ws_name)
        ws.append_row(row, value_input_option="USER_ENTERED")

# ======== Models & Product Map ========
class ClaimRequest(BaseModel):
    agent_id: str
    sites: List[str]

class ReportRequest(BaseModel):
    task_id: str
    agent_id: str
    status: str
    result_link: Optional[str] = None
    error: Optional[str] = None

PRODUCTS = {
    # بدّل الروابط حسب مواقعك
    "site-1": {
        5:  "https://playstoreskw.com/product/%d8%b4%d8%ad%d9%86-%d9%86%d9%82%d8%a7%d8%b7-brawl-stars-30-usdt/",
        10: "https://playstoreskw.com/product/%d8%a7%d9%88%d9%81%d8%b1%d9%88%d8%a7%d8%aa%d8%b4-%d8%b3%d9%83%d9%86-%d9%88%d9%8a%d8%af%d9%88-%d9%86%d9%88%d9%8a%d8%b1-%d8%a3%d9%86%d8%af%d8%b1-%d8%b3%d9%83%d9%86-%d8%a8%d8%a7%d9%84%d9%84%d8%b9/",
        15: "https://playstoreskw.com/product/%d8%a7%d8%b4%d8%aa%d8%b1%d8%a7%d9%83-%d9%88%d9%84%d9%83%d9%86-%d9%85%d9%88%d9%86-%d9%82%d9%86%d8%a8%d9%83%d8%aa/",
        20: "https://playstoreskw.com/product/725-%d8%b4%d8%ad%d9%86-%d9%84%d9%8a%d9%82-%d8%a2%d8%b1-%d8%a8%d9%8a-%d9%84%d9%88%d9%84/",
        30: "https://playstoreskw.com/product/660-%d8%b4%d8%af%d9%87-pubg-uc/",
    },
    "site-2": {},  # عبّي لاحقًا
    "site-3": {},  # عبّي لاحقًا
}
def qty_for_price(price:int)->int:
    return 3 if price==30 else 1

# ======== Agents ========
@app.post("/agents/register")
def register_agent(agent_id: str = Form(...), name: str = Form(...), sites: str = Form(...)):
    caps = [s.strip() for s in sites.split(",") if s.strip()]
    _hset(f"agent:{agent_id}", {"id":agent_id,"name":name,"sites":",".join(caps),
                                "status":"online","last_seen_ts":str(time.time())})
    return {"ok": True}

@app.post("/agents/heartbeat")
def heartbeat(info: Dict[str, Any]):
    agent_id = info.get("agent_id")
    if not agent_id: raise HTTPException(400,"agent_id required")
    ag = _hgetall(f"agent:{agent_id}")
    if not ag: _hset(f"agent:{agent_id}", {"id":agent_id})
    _hset(f"agent:{agent_id}", {"status": info.get("status","online"),
                                "last_seen_ts": str(time.time())})
    return {"ok": True}

@app.get("/agents/online")
def agents_online():
    out=[]
    for k in _keys("agent:*"):
        ag = _hgetall(k)
        if ag: out.append(ag)
    return out

# ======== Jobs / Tasks ========
@app.post("/jobs/create")
async def create_job(
    site: str = Form(...),
    price: int = Form(...),
    total: int = Form(...),
    csv_file: UploadFile = File(...),
    random_sample: bool = Form(True),
):
    if site not in PRODUCTS or price not in PRODUCTS[site] or not PRODUCTS[site][price]:
        raise HTTPException(400, "Unknown site/price or product link not set")
    blob = await csv_file.read()
    txt = blob.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(txt))
    rows = [{"first_name": (r.get("first_name") or "").strip(),
             "last_name":  (r.get("last_name") or "").strip()} for r in reader]
    rows = [r for r in rows if r["first_name"] or r["last_name"]]
    if not rows: raise HTTPException(400, "CSV empty or headers missing (first_name,last_name)")
    if random_sample and total < len(rows):
        rows = random.sample(rows, total)
    else:
        rows = rows[:total]

    job_id = uuid.uuid4().hex
    _hset(f"job:{job_id}", {"site":site,"price":price,"total":len(rows),
                            "created_at":str(time.time()),"status":"running"})
    qkey = f"job:{job_id}:queue"
    for person in rows:
        tid = uuid.uuid4().hex
        _hset(f"task:{tid}", {"job_id":job_id,
                              "first_name":person["first_name"],
                              "last_name":person["last_name"],
                              "product_link":PRODUCTS[site][price],
                              "qty":str(qty_for_price(price)),
                              "status":"pending",
                              "assigned_to":"",
                              "result_link":"",
                              "error":""})
        _rpush(qkey, tid)
    return {"job_id": job_id, "total_tasks": len(rows)}

@app.get("/jobs/{job_id}/status")
def job_status(job_id:str):
    meta = _hgetall(f"job:{job_id}")
    if not meta: raise HTTPException(404,"job not found")
    total=done=failed=running=pending=0
    for k in _keys("task:*"):
        t = _hgetall(k)
        if t.get("job_id")!=job_id: continue
        total += 1
        st = t.get("status")
        if st=="success": done+=1
        elif st=="failed": failed+=1
        elif st=="running": running+=1
        else: pending+=1
    return {"job":meta,"stats":{"total":total,"done":done,"failed":failed,"running":running,"pending":pending}}

@app.post("/tasks/claim-auto")
def claim_auto(req: ClaimRequest):
    # اتAssign أول مهمة متاحة لأي job running ومتوافقة مع قدرات الـ agent
    for jk in _keys("job:*"):
        job_id = jk.split(":")[1]
        meta = _hgetall(jk)
        if not meta or meta.get("status")!="running": continue
        site = meta["site"]
        if site not in req.sites: continue
        qkey = f"job:{job_id}:queue"
        tid = _lpop(qkey)
        if not tid: continue
        tkey = f"task:{tid}"
        task = _hgetall(tkey)
        task["task_id"] = tid
        task["status"] = "running"
        task["assigned_to"] = req.agent_id
        task["site"] = site
        _hset(tkey, task)
        return {"task": task}
    return {"task": None}

@app.post("/tasks/report")
def report_task(rep: ReportRequest):
    tkey = f"task:{rep.task_id}"
    task = _hgetall(tkey)
    if not task: raise HTTPException(404,"task not found")
    ok = (rep.status.lower()=="success")
    task["status"] = "success" if ok else "failed"
    task["result_link"] = rep.result_link or ""
    task["error"] = rep.error or ""
    _hset(tkey, task)

    # اكتب على Google Sheet لو Success
    if ok:
        price = int(_hgetall(f"job:{task['job_id']}")["price"])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, task.get("assigned_to",""), task.get("first_name",""), task.get("last_name",""), rep.result_link]
        try:
            append_to_sheet(price, row)
        except Exception as e:
            # ما نكسر الطلب حتى لو الSheet فشل
            task["error"] = f"Saved but sheet error: {e}"
            _hset(tkey, task)

    return {"ok": True}
