from fastapi import FastAPI, HTTPException, Query, Security, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse, Response
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import os
import sqlite3
from openai import OpenAI
import csv
import io
import time
import httpx
import json

# --- App & basic setup ---
APP_DIR = Path(__file__).parent.resolve()
DB_PATH = str(APP_DIR / "bcm_demo.db")

app = FastAPI(
    title="BCM Demo API",
    version="1.0.0",
    description="Backend for BCM demo: courses, enrollments, fees, schedules, and HeyGen token/proxy.",
)

# Static files
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

# --- CORS ---
origins = [
    "https://bcmavatar.vercel.app",  # your Vercel frontend
    "http://localhost:3000",         # local dev
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB helpers ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            fee REAL NOT NULL,
            start_date TEXT,
            end_date TEXT,
            time TEXT,
            venue TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            program_code TEXT,
            cohort_code TEXT,
            timezone TEXT,
            notes TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            q TEXT,
            a TEXT
        )
        """)
        conn.commit()

init_db()

# --- Admin key guard ---
ADMIN_KEY = os.getenv("ADMIN_KEY") or os.getenv("VITE_BCM_ADMIN_KEY")
api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

def require_admin(x_admin_key: str = Security(api_key_header)):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured on server")
    if not x_admin_key:
        raise HTTPException(status_code=403, detail="Forbidden (no X-Admin-Key header received)")
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail=f"Forbidden (got {x_admin_key}, expected ADMIN_KEY)")
    return True

# --- Basic routes ---
@app.get("/")
def root():
    return RedirectResponse(url="/static/enroll.html")

@app.get("/health")
def health():
    return {"ok": True}

# --- FAQ ---
@app.get("/faq")
def get_faq() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT id, q, a FROM faq ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

class FAQIn(BaseModel):
    q: str
    a: str

@app.post("/faq", dependencies=[Security(require_admin)], tags=["admin"])
def add_faq(item: FAQIn):
    with get_db() as conn:
        cur = conn.execute("INSERT INTO faq (q, a) VALUES (?, ?)", (item.q, item.a))
        conn.commit()
        fid = cur.lastrowid
        row = conn.execute("SELECT id, q, a FROM faq WHERE id = ?", (fid,)).fetchone()
        return dict(row)

# --- Fees ---
@app.get("/fees/{program_code}")
def get_fees(program_code: str):
    mapping = {
        "GI": {"program": "General IELTS", "fee": 8800, "currency": "HKD"},
        "HKDSE": {"program": "HKDSE English", "fee": 7600, "currency": "HKD"},
    }
    if program_code not in mapping:
        raise HTTPException(status_code=404, detail="Program not found")
    return mapping[program_code]

# --- Schedule ---
@app.get("/schedule")
def schedule(season: Optional[str] = None):
    if season == "summer":
        return [{"course": "IELTS Summer Bootcamp", "weeks": 6, "days": ["Mon", "Wed", "Fri"]}]
    return []

# --- Admin check ---
@app.get("/admin/check", dependencies=[Security(require_admin)], tags=["admin"])
def admin_check():
    return {"ok": True, "message": "Admin access confirmed."}

# =========================================================
# === HeyGen CONFIG + TOKEN + PROXY =======================
# =========================================================

HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY") or os.getenv("ADMIN_KEY")
HEYGEN_BASE = "https://api.heygen.com/v1"

@app.post("/heygen/token")
async def heygen_token():
    if not HEYGEN_API_KEY:
        raise HTTPException(500, "HEYGEN_API_KEY missing")

    AVATAR_ID = os.getenv("HEYGEN_AVATAR_ID")

    url = f"{HEYGEN_BASE}/streaming.new"
    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "avatar_id": AVATAR_ID,   # must be interactive avatar
        "quality": "high",
        "version": "v2",          # LiveKit flow
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers=headers, json=payload)

    if r.status_code != 200:
        raise HTTPException(r.status_code, f"heygen error: {r.text}")

    try:
        data = r.json()
    except Exception:
        raise HTTPException(502, f"heygen ok but non-JSON body: {r.text[:500]}")

    return data

@app.api_route("/heygen/proxy/{subpath:path}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"], tags=["public"])
async def heygen_proxy(subpath: str, request: Request):
    if not HEYGEN_API_KEY:
        raise HTTPException(500, "HEYGEN_API_KEY missing")
    target_url = f"{HEYGEN_BASE}/{subpath}"
    if request.url.query:
        target_url += f"?{request.url.query}"
    body_bytes = await request.body()
    json_payload = None
    if body_bytes:
        try:
            json_payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            json_payload = None
    headers = {"X-Api-Key": HEYGEN_API_KEY, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.request(
            request.method,
            target_url,
            headers=headers,
            json=json_payload if json_payload is not None else None,
            content=None if json_payload is not None else (body_bytes or None),
        )
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))

# =========================================================

# --- Courses model ---
class CourseIn(BaseModel):
    name: str = Field(..., description="Course name (e.g., IELTS Foundation)")
    fee: float = Field(..., description="Fee amount (numeric)")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    time: Optional[str] = Field(None, description="e.g., Mon 7–9pm")
    venue: Optional[str] = Field(None, description="Room / Center")

# --- Courses CRUD ---
@app.post("/admin/courses", dependencies=[Security(require_admin)], tags=["admin"])
def admin_add_course(course: CourseIn):
    return add_course(course)

@app.post("/courses", dependencies=[Security(require_admin)], tags=["courses"])
def add_course(course: CourseIn):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO courses (name, fee, start_date, end_date, time, venue)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (course.name, course.fee, course.start_date, course.end_date, course.time, course.venue))
        course_id = cur.lastrowid
        row = conn.execute("""
            SELECT id, name, fee, start_date, end_date, time, venue
            FROM courses WHERE id = ?
        """, (course_id,)).fetchone()
        conn.commit()
        return dict(row)

@app.get("/courses")
def list_courses() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, name, fee, start_date, end_date, time, venue
            FROM courses ORDER BY id DESC
        """).fetchall()
        return [dict(r) for r in rows]

@app.get("/courses/{course_id}")
def get_course(course_id: int) -> Dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("""
            SELECT id, name, fee, start_date, end_date, time, venue
            FROM courses WHERE id = ?
        """, (course_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Course not found")
        return dict(row)

@app.delete("/courses/{course_id}", dependencies=[Security(require_admin)], tags=["admin"])
def delete_course(course_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Course not found")
        return {"ok": True, "deleted": course_id}

# --- CSV export for courses ---
@app.get("/courses/export.csv")
def export_courses_csv():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, name, fee, start_date, end_date, time, venue
            FROM courses ORDER BY id DESC
        """).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "fee", "start_date", "end_date", "time", "venue"])
    for r in rows:
        writer.writerow([r["id"], r["name"], r["fee"], r["start_date"], r["end_date"], r["time"], r["venue"]])
    return Response(content=output.getvalue(), media_type="text/csv")

# --- Enrollment ---
class EnrollmentIn(BaseModel):
    full_name: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    program_code: Optional[str] = None
    cohort_code: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = Field(default="web", description="Where this came from (web/journal/etc)")

@app.post("/enroll", tags=["enroll"])
def enroll(data: EnrollmentIn):
    full_name_val = (data.full_name or data.name or "").strip()
    if not full_name_val:
        raise HTTPException(status_code=422, detail="full_name or name is required")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO enrollments
              (full_name, email, phone, program_code, cohort_code, timezone, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name_val, data.email, data.phone, data.program_code,
                data.cohort_code, data.timezone, data.notes, data.source
            ),
        )
        conn.commit()
        return {"ok": True, "message": "Enrollment saved."}

@app.get("/enrollments/recent", dependencies=[Security(require_admin)], tags=["admin"])
def recent_enrollments(
    limit: int = Query(10, ge=1, le=100),
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = """
      SELECT id, full_name, email, phone, program_code, cohort_code, timezone, notes, source, created_at
      FROM enrollments
    """
    params: List[Any] = []
    if source:
        sql += " WHERE source = ?"
        params.append(source)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

# --- OpenAI passthrough example (optional) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None

class EchoIn(BaseModel):
    text: str

@app.post("/echo")
def echo(item: EchoIn):
    return {"echo": item.text}

# --- Simple SSE/streaming example (placeholder) ---
@app.get("/stream")
def stream():
    async def gen():
        yield b"data: hello\n\n"
        time.sleep(0.5)
        yield b"data: world\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
