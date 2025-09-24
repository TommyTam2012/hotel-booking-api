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
from seed.seed import seed_if_needed
from seed.seed_hotel import seed_hotel   # <-- added

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure DB seeded (idempotent, runs once at startup)
    os.makedirs(APP_DIR, exist_ok=True)
    seed_if_needed(DB_PATH)
    seed_hotel(DB_PATH)   # <-- added
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
# DEMO MODE FLAG
# =========================
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

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

# Initialize DBs on import
init_db()
init_hotel_db()

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
    if DEMO_MODE:
        from datetime import datetime, timedelta
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        out = {}
        d = s
        while d <= e:
            out[d.date().isoformat()] = {"price": 0.0, "left": 99}
            d += timedelta(days=1)
        return out
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
    if DEMO_MODE:
        return {"ok": True, "message": f"[DEMO] Booking confirmed for {payload.check_in} → {payload.check_out} ({payload.quantity} room(s))."}
    qty = int(payload.quantity or 1)
    if qty < 1:
        raise HTTPException(400, "quantity must be >= 1")
    with get_db() as c:
        nights = c.execute("""
            SELECT date, left FROM room_inventory
            WHERE room_type_id = ?
              AND date >= ?
              AND date <  ?
            ORDER BY date ASC
        """, (payload.room_type, payload.check_in, payload.check_out)).fetchall()
        if not nights:
            raise HTTPException(400, "No inventory for selected dates.")
        if any(int(r["left"]) < qty for r in nights):
            raise HTTPException(409, "Range includes sold-out dates.")
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
# (BCM-related endpoints unchanged — kept fully intact in your file)

# Optional: local dev entrypoint
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
