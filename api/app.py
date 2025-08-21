from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import os
import sqlite3
from openai import OpenAI
import csv
import io

# --- Paths ---
APP_DIR = Path(__file__).parent.resolve()
DB_PATH = str(APP_DIR / "bcm.db")

# --- App ---
app = FastAPI(title="BCM Demo API")

# Static files
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB helpers ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # FAQ
        c.execute("""
        CREATE TABLE IF NOT EXISTS faq(
          intent TEXT PRIMARY KEY,
          question TEXT,
          answer TEXT
        );
        """)
        # Enrollments
        c.execute("""
        CREATE TABLE IF NOT EXISTS enrollments(
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
        );
        """)
        # Courses
        c.execute("""
        CREATE TABLE IF NOT EXISTS courses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          fee TEXT,
          start_date TEXT,
          end_date TEXT,
          time TEXT,
          venue TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Fees
        c.execute("""
        CREATE TABLE IF NOT EXISTS fees(
          plan TEXT PRIMARY KEY,
          amount INTEGER,
          currency TEXT DEFAULT 'HKD',
          fee_text TEXT,
          note TEXT,
          effective_from TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Schedules
        c.execute("""
        CREATE TABLE IF NOT EXISTS schedules(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          season TEXT DEFAULT 'summer',
          day TEXT NOT NULL,
          start_time TEXT NOT NULL,
          end_time TEXT NOT NULL,
          label TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        c.execute("""
        INSERT OR IGNORE INTO faq(intent, question, answer)
        VALUES ('TEST_INTENT','Test Q?','Test A.');
        """)
        conn.commit()

@app.on_event("startup")
def on_startup():
    init_db()

# --- Admin key ---
ADMIN_KEY = os.getenv("ADMIN_KEY")
API_KEY_NAME = "X-Admin-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def require_admin(x_admin_key: str = Security(api_key_header)):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured on server")
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return True

# --- Root ---
@app.get("/")
def root():
    return RedirectResponse(url="/static/enroll.html")

@app.get("/health")
def health():
    return {"ok": True}

# --- FAQ ---
@app.get("/faq/{intent}")
def get_faq(intent: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT question, answer FROM faq WHERE intent = ?",
            (intent,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="FAQ not found")
        return {"intent": intent, "question": row["question"], "answer": row["answer"]}

# --- Models ---
class EnrollmentIn(BaseModel):
    full_name: Optional[str] = None
    name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    program_code: Optional[str] = None
    cohort_code: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "avatar"

class ChatIn(BaseModel):
    message: str

class CourseIn(BaseModel):
    name: str
    fee: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time: Optional[str] = None
    venue: Optional[str] = None

class FeeIn(BaseModel):
    plan: str = Field(examples=["GI"])
    amount: Optional[int] = Field(default=None, example=128000)
    currency: str = "HKD"
    fee_text: Optional[str] = Field(default=None, example="HK$1,280")
    note: Optional[str] = None

class FeeOut(FeeIn):
    effective_from: Optional[str] = None

class ScheduleIn(BaseModel):
    season: str = "summer"
    day: str
    start_time: str
    end_time: str
    label: Optional[str] = None

class ScheduleOut(ScheduleIn):
    id: int
    created_at: Optional[str] = None

class CourseOut(BaseModel):
    id: int
    name: str
    fee: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time: Optional[str] = None
    venue: Optional[str] = None
    created_at: Optional[str] = None

# --- Enrollments ---
@app.post("/enroll")
def enroll(data: EnrollmentIn):
    full_name_val = data.full_name or data.name
    if not full_name_val:
        raise HTTPException(status_code=422, detail="full_name or name is required")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO enrollments
              (full_name, email, phone, program_code, cohort_code, timezone, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            full_name_val, data.email, data.phone, data.program_code,
            data.cohort_code, data.timezone, data.notes, data.source
        ))
        conn.commit()
    return {"status": "ok", "message": "Thank you!", "full_name": full_name_val, "email": data.email}

@app.get("/enrollments/recent", dependencies=[Security(require_admin)], tags=["admin"])
def recent_enrollments(limit: int = Query(10, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM enrollments ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]

@app.get("/admin/health", dependencies=[Security(require_admin)], tags=["admin"])
def admin_health():
    return {"ok": True, "msg": "Admin access confirmed."}

# --- Courses ---
@app.post("/admin/courses", dependencies=[Security(require_admin)], tags=["admin"])
def admin_add_course(course: CourseIn):
    return add_course(course)

@app.post("/courses", dependencies=[Security(require_admin)], tags=["courses"])
def add_course(course: CourseIn):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO courses (name, fee, start_date, end_date, time, venue)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (course.name, course.fee, course.start_date, course.end_date, course.time, course.venue))
        conn.commit()
    return {"status": "ok", "message": "Course added", "course": course}

@app.get("/courses", tags=["courses"], response_model=List[CourseOut])
def list_courses():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

# --- Helpers & Exports (must come BEFORE /{course_id}) ---
def course_to_sentence(row: dict) -> str:
    parts = [row.get("name") or "The course"]
    if row.get("fee"): parts.append(f"costs {row['fee']}")
    if row.get("time"): parts.append(f"{row['time']}")
    if row.get("venue"): parts.append(f"at {row['venue']}")
    return ", ".join(parts) + "."

@app.get("/courses/export.csv", tags=["courses"])
def export_courses_csv():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM courses ORDER BY created_at DESC").fetchall()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows else [])
    writer.writeheader()
    for r in rows: writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=courses.csv"})

@app.get("/courses/latest", response_model=CourseOut, tags=["courses"])
def get_latest_course():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM courses ORDER BY datetime(created_at) DESC, id DESC LIMIT 1").fetchone()
    if not row: raise HTTPException(404, "No courses")
    return dict(row)

@app.get("/courses/search", response_model=List[CourseOut], tags=["courses"])
def search_courses(name: str = Query(...)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM courses WHERE name LIKE ? ORDER BY name ASC LIMIT 20", (f"%{name}%",)).fetchall()
    return [dict(r) for r in rows]

@app.get("/courses/summary", tags=["courses"])
def course_summary(name: Optional[str] = None):
    with get_db() as conn:
        if name:
            row = conn.execute("SELECT * FROM courses WHERE name LIKE ? ORDER BY id DESC LIMIT 1", (f"%{name}%",)).fetchone()
        else:
            row = conn.execute("SELECT * FROM courses ORDER BY datetime(created_at) DESC, id DESC LIMIT 1").fetchone()
    if not row: raise HTTPException(404, "No course found")
    return {"message": course_to_sentence(dict(row)), "data": dict(row)}

# --- ID route LAST ---
@app.get("/courses/{course_id}", tags=["courses"], response_model=CourseOut)
def get_course(course_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    if not row: raise HTTPException(404, "Not found")
    return dict(row)

# --- Fees ---
@app.post("/admin/fees", dependencies=[Security(require_admin)], response_model=FeeOut, tags=["admin"])
def upsert_fee(data: FeeIn):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO fees(plan, amount, currency, fee_text, note, effective_from)
            VALUES(?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(plan) DO UPDATE SET
              amount=excluded.amount,
              currency=excluded.currency,
              fee_text=excluded.fee_text,
              note=excluded.note,
              effective_from=CURRENT_TIMESTAMP
        """, (data.plan, data.amount, data.currency, data.fee_text, data.note))
        row = conn.execute("SELECT * FROM fees WHERE plan=?", (data.plan,)).fetchone()
    return dict(row)

@app.get("/fees", response_model=List[FeeOut], tags=["public"])
def list_fees():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM fees ORDER BY plan").fetchall()
    return [dict(r) for r in rows]

@app.get("/fees/{plan}", response_model=FeeOut, tags=["public"])
def get_fee(plan: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fees WHERE plan=?", (plan,)).fetchone()
    if not row: raise HTTPException(404, "Not found")
    return dict(row)

@app.get("/fees/export.csv", tags=["public"])
def export_fees_csv():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM fees ORDER BY plan").fetchall()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows else [])
    writer.writeheader()
    for r in rows: writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fees.csv"})

# --- Schedule ---
@app.post("/admin/schedule", dependencies=[Security(require_admin)], response_model=ScheduleOut, tags=["admin"])
def add_schedule(data: ScheduleIn):
    with get_db() as conn:
        cur = conn.execute("INSERT INTO schedules(season,day,start_time,end_time,label) VALUES(?,?,?,?,?)",
                           (data.season, data.day, data.start_time, data.end_time, data.label))
        sid = cur.lastrowid
        row = conn.execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone()
    return dict(row)

@app.get("/schedule", response_model=List[ScheduleOut], tags=["public"])
def list_schedule(season: Optional[str] = None, day: Optional[str] = None):
    q = "SELECT * FROM schedules WHERE 1=1"
    args = []
    if season: q += " AND season=?"; args.append(season)
    if day: q += " AND day=?"; args.append(day)
    q += " ORDER BY day, start_time"
    with get_db() as conn:
        rows = conn.execute(q, args).fetchall()
    return [dict(r) for r in rows]

@app.get("/schedule/export.csv", tags=["public"])
def export_schedule_csv():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM schedules ORDER BY season, day, start_time").fetchall()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys() if rows else [])
    writer.writeheader()
    for r in rows: writer.writerow(dict(r))
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=schedule.csv"})

# --- OpenAI Chat ---
@app.post("/chat")
def chat(in_: ChatIn):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "Missing OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a concise, helpful assistant."},
                      {"role": "user", "content": in_.message}],
            max_tokens=300,
            temperature=0.7,
        )
        return {"reply": resp.choices[0].message.content}
    except Exception as e:
        raise HTTPException(500, f"OpenAI error: {e}")
