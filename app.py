from fastapi import FastAPI, HTTPException, Query, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse, Response, FileResponse, JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import os
import sqlite3
import csv
import io
import time
import json

# =========================
# App setup & Constants
# =========================
APP_DIR = Path(__file__).parent.resolve()
DB_PATH = os.getenv("HOTEL_DB_FILE", str(APP_DIR / "bcm_demo.db"))
STATIC_DIR = APP_DIR / "api" / "static"

# NEW: import seeder
from contextlib import asynccontextmanager
from seed import seed_if_needed

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure DB seeded (idempotent, runs once at startup)
    os.makedirs(APP_DIR, exist_ok=True)
    seed_if_needed(DB_PATH)
    yield
    # optional teardown later if needed

app = FastAPI(
    title="BCM + Hotel API",
    version="2.0.0",
    description="Backend for BCM demo (courses, enrollments) and Hotel Booking (rooms, availability, bookings).",
    lifespan=lifespan
)

# Ensure static directory exists (won't crash if missing; some routes handle 404 gracefully)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# =========================
# CORS
# =========================
origins = [
    "https://bcmavatar.vercel.app",
    "https://bcm-demo.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Debug / Static helper routes
# =========================
def _file_or_404(path: Path) -> FileResponse:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path.name}")
    return FileResponse(str(path))

@app.get("/calendar", tags=["static"])
def serve_calendar():
    """Serve /api/static/index.html directly (bypass StaticFiles)"""
    return _file_or_404(STATIC_DIR / "index.html")

@app.get("/debug/static-list", tags=["static"])
def debug_static_list():
    """List files in the static directory"""
    p = STATIC_DIR
    return {
        "mounted_dir": str(p),
        "dir_exists": p.exists(),
        "files": sorted(os.listdir(p)) if p.exists() else [],
    }

@app.get("/admin", tags=["static"])
def serve_admin():
    return _file_or_404(STATIC_DIR / "admin.html")

@app.get("/enroll", tags=["static"])
def serve_enroll():
    return _file_or_404(STATIC_DIR / "enroll.html")

@app.get("/course_form", tags=["static"])
def serve_course_form():
    return _file_or_404(STATIC_DIR / "course_form.html")

# =========================
# DB helpers
# =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any((c[1] == column) for c in cols)
    except Exception:
        return False

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
                venue TEXT,
                seats INTEGER DEFAULT 0
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
        # Backfill seats column if the table existed without it
        if not _column_exists(conn, "courses", "seats"):
            conn.execute("ALTER TABLE courses ADD COLUMN seats INTEGER DEFAULT 0")
        conn.commit()

# =========================
# Hotel schema & seed
# =========================
def init_hotel_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS room_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS room_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_type_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            price REAL NOT NULL,
            left INTEGER NOT NULL,
            UNIQUE(room_type_id, date),
            FOREIGN KEY(room_type_id) REFERENCES room_types(id)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_type_id INTEGER NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            name TEXT,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY(room_type_id) REFERENCES room_types(id)
        )
        """)
        # Ensure bookings.quantity exists if older DB
        if not _column_exists(conn, "bookings", "quantity"):
            conn.execute("ALTER TABLE bookings ADD COLUMN quantity INTEGER DEFAULT 1")

        conn.commit()

def seed_hotel_if_empty():
    from datetime import date, timedelta
    with get_db() as conn:
        room_types = [
            "标准大床房",
            "标准双床房",
            "高级大床房",
            "豪华海景房",
            "家庭房",
            "行政套房",
            "总统套房",
            "无障碍客房"
        ]
        # Always ensure all 8 exist (INSERT OR IGNORE keeps existing ones)
        for rt in room_types:
            conn.execute("INSERT OR IGNORE INTO room_types (name) VALUES (?)", (rt,))
        conn.commit()

        # Seed 14 days for Deluxe (only if found)
        rid_row = conn.execute("SELECT id FROM room_types WHERE name='Deluxe'").fetchone()
        if rid_row:
            rid = rid_row[0]
            today = date.today()
            for i in range(14):
                d = today + timedelta(days=i)
                key = d.isoformat()
                exists = conn.execute(
                    "SELECT 1 FROM room_inventory WHERE room_type_id=? AND date=?",
                    (rid, key)
                ).fetchone()
                if not exists:
                    price = 780 + (i % 5) * 35 + (150 if d.weekday() >= 5 else 0)
                    left = 5 if i % 9 != 0 else 0
                    conn.execute(
                        "INSERT INTO room_inventory (room_type_id, date, price, left) VALUES (?,?,?,?)",
                        (rid, key, float(price), int(left))
                    )
            conn.commit()

# Initialize DBs on import
init_db()
init_hotel_db()
seed_hotel_if_empty()

# =========================
# Admin Key Guard
# =========================
ADMIN_KEY = os.getenv("ADMIN_KEY") or os.getenv("VITE_BCM_ADMIN_KEY")
api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

def require_admin(x_admin_key: str = Security(api_key_header)):
    if not ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured on server")
    if not x_admin_key:
        raise HTTPException(status_code=403, detail="Forbidden (no X-Admin-Key header received)")
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden (bad X-Admin-Key)")
    return True

# =========================
# Basic routes
# =========================
@app.get("/")
def root():
    # If static exists, send to index.html; else show basic welcome JSON
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        return RedirectResponse(url="/static/index.html")
    return {"ok": True, "message": "BCM + Hotel API running", "docs": "/docs"}

@app.get("/health")
def health():
    return {"ok": True}

# =========================================================
# ============ HOTEL ENDPOINTS ============================
# =========================================================
from datetime import date as _date, timedelta as _timedelta

@app.get("/room_types", tags=["Hotel"])
def list_room_types():
    """Return all available room types"""
    with get_db() as conn:
        rows = conn.execute("SELECT id, name FROM room_types ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

@app.get("/availability", tags=["Hotel"])
def availability(room_type: int, start: str, end: str):
    """
    Return availability (inclusive of end date) for a room_type between start and end.
    Response: { "YYYY-MM-DD": { "price": float, "left": int }, ... }
    """
    with get_db() as c:
        rows = c.execute("""
            SELECT date, price, left
            FROM room_inventory
            WHERE room_type_id = ?
              AND date >= ?
              AND date <= ?
            ORDER BY date ASC
        """, (room_type, start, end)).fetchall()
        return { r["date"]: {"price": float(r["price"]), "left": int(r["left"])} for r in rows }

class BookIn(BaseModel):
    room_type: int
    check_in: str  # yyyy-mm-dd
    check_out: str # yyyy-mm-dd (exclusive)
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    quantity: int = Field(1, ge=1, le=10)  # rooms per night to book

@app.post("/book", tags=["Hotel"])
def book(payload: BookIn):
    """
    Create a booking (checkout exclusive) and decrement room_inventory.left per night.
    Returns: {"ok": True, "message": "..."}
    """
    qty = int(payload.quantity or 1)
    if qty < 1:
        raise HTTPException(400, "quantity must be >= 1")

    with get_db() as c:
        # Fetch the date range nights (checkout exclusive)
        nights = c.execute("""
            SELECT date, left FROM room_inventory
            WHERE room_type_id = ?
              AND date >= ?
              AND date <  ?
            ORDER BY date ASC
        """, (payload.room_type, payload.check_in, payload.check_out)).fetchall()

        if not nights:
            raise HTTPException(400, "No inventory for selected dates.")

        # Check all nights have enough inventory for the requested quantity
        if any(int(r["left"]) < qty for r in nights):
            raise HTTPException(409, "Range includes sold-out dates.")

        # Atomic decrement per night
        for r in nights:
            cur = c.execute("""
                UPDATE room_inventory
                   SET left = left - ?
                 WHERE room_type_id = ?
                   AND date = ?
                   AND left >= ?
            """, (qty, payload.room_type, r["date"], qty))
            if cur.rowcount == 0:
                raise HTTPException(409, "Just sold out while booking. Please try another range.")

        # Record booking with quantity
        c.execute("""
            INSERT INTO bookings (room_type_id, check_in, check_out, name, email, phone, notes, quantity)
            VALUES (?,?,?,?,?,?,?,?)
        """, (payload.room_type, payload.check_in, payload.check_out,
              payload.name, payload.email, payload.phone, payload.notes, qty))
        c.commit()

    return {"ok": True, "message": f"Booking confirmed. {qty} room(s) deducted per night."}

@app.get("/bookings", tags=["Hotel"])
def list_bookings(limit: int = Query(10, ge=1, le=100)):
    """Return recent hotel bookings"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, room_type_id, check_in, check_out, name, email, phone, notes, created_at, quantity "
            "FROM bookings ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# =========================================================
# ============ BCM DEMO ENDPOINTS =========================
# =========================================================

# --- FAQ ---
@app.get("/faq", tags=["BCM"])
def get_faq() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT id, q, a FROM faq ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

class FAQIn(BaseModel):
    q: str
    a: str

@app.post("/faq", dependencies=[Security(require_admin)], tags=["BCM Admin"])
def add_faq(item: FAQIn):
    with get_db() as conn:
        cur = conn.execute("INSERT INTO faq (q, a) VALUES (?, ?)", (item.q, item.a))
        fid = cur.lastrowid
        row = conn.execute("SELECT id, q, a FROM faq WHERE id = ?", (fid,)).fetchone()
        conn.commit()
        return dict(row)

# --- Fees ---
@app.get("/fees/{program_code}", tags=["BCM"])
def get_fees(program_code: str):
    code = (program_code or "").upper()
    mapping = {
        "GI":    {"program": "BCM General English (GI)", "fee": 8800, "currency": "HKD"},
        "HKDSE": {"program": "BCM HKDSE English",        "fee": 7600, "currency": "HKD"},
    }
    if code not in mapping:
        raise HTTPException(status_code=404, detail="Program not found")
    return mapping[code]

# --- Schedule ---
@app.get("/schedule", tags=["BCM"])
def schedule(season: Optional[str] = None):
    if (season or "").lower() == "summer":
        return [{
            "course": "BCM Summer Intensive",
            "weeks": 6,
            "days": ["Monday", "Wednesday", "Friday"],
            "time": "Mon/Wed/Fri 7–9pm",
        }]
    return []

# --- Courses model ---
class CourseIn(BaseModel):
    name: str
    fee: float
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time: Optional[str] = None
    venue: Optional[str] = None
    seats: Optional[int] = Field(0, ge=0)

# --- Courses CRUD ---
@app.post("/courses", dependencies=[Security(require_admin)], tags=["BCM Admin"])
def add_course(course: CourseIn):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO courses (name, fee, start_date, end_date, time, venue, seats) VALUES (?,?,?,?,?,?,?)",
            (course.name, course.fee, course.start_date, course.end_date, course.time, course.venue, course.seats),
        )
        course_id = cur.lastrowid
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        conn.commit()
        return dict(row)

@app.get("/courses", tags=["BCM"])
def list_courses() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

@app.get("/courses/{course_id}", tags=["BCM"])
def get_course(course_id: int) -> Dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Course not found")
        return dict(row)

@app.delete("/courses/{course_id}", dependencies=[Security(require_admin)], tags=["BCM Admin"])
def delete_course(course_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Course not found")
        return {"ok": True, "deleted": course_id}

@app.get("/courses/export.csv", tags=["BCM"])
def export_courses_csv():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([c for c in rows[0].keys()] if rows else [])
    for r in rows:
        writer.writerow([r[c] for c in r.keys()])
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
    source: Optional[str] = "web"

@app.post("/enroll", tags=["BCM"])
def enroll(data: EnrollmentIn):
    full_name_val = (data.full_name or data.name or "").strip()
    if not full_name_val:
        raise HTTPException(status_code=422, detail="full_name or name is required")
    with get_db() as conn:
        row = conn.execute("SELECT id, seats FROM courses ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No course available")
        current_seats = int(row["seats"] or 0)
        if current_seats <= 0:
            return {"ok": False, "message": "Sorry, this course is full."}
        conn.execute("UPDATE courses SET seats = seats - 1 WHERE id = ? AND seats > 0", (row["id"],))
        conn.execute(
            "INSERT INTO enrollments (full_name, email, phone, program_code, cohort_code, timezone, notes, source) VALUES (?,?,?,?,?,?,?,?)",
            (full_name_val, data.email, data.phone, data.program_code, data.cohort_code, data.timezone, data.notes, data.source),
        )
        conn.commit()
    return {"ok": True, "message": "Enrollment confirmed. Seat deducted."}

@app.get("/enrollments/recent", dependencies=[Security(require_admin)], tags=["BCM Admin"])
def recent_enrollments(limit: int = Query(10, ge=1, le=100)) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM enrollments ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

# --- Assistant ---
class UserQuery(BaseModel):
    text: str

@app.post("/assistant/answer", tags=["BCM"])
def assistant_answer(payload: UserQuery):
    q = (payload.text or "").lower().strip()
    if "fee" in q or "學費" in q:
        return {"reply": "BCM General English (GI) costs HKD 8800. Would you like to enroll?"}
    if "schedule" in q or "時間" in q:
        return {"reply": "BCM Summer Intensive runs Mon/Wed/Fri 7–9pm. Would you like to enroll?"}
    if "course" in q or "課程" in q:
        return {"reply": "Latest BCM course is available. Would you like to enroll?"}
    if "enroll" in q or "報名" in q:
        return {"reply": "You can enroll online. Would you like to enroll?"}
    return {"reply": "I can only answer BCM-related questions. Would you like to enroll?"}

# Optional: local dev entrypoint
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
