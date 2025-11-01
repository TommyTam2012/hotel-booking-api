from fastapi import FastAPI, HTTPException, Query, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import os
import sqlite3
import smtplib, ssl
from email.message import EmailMessage
from contextlib import asynccontextmanager
from seed.seed import seed_if_needed
from seed.seed_hotel import seed_hotel

# =========================
# App setup & Constants
# =========================
APP_DIR = Path(__file__).parent.resolve()
DB_PATH = os.getenv("HOTEL_DB_FILE", str(APP_DIR / "bcm_demo.db"))
STATIC_DIR = APP_DIR / "api" / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(APP_DIR, exist_ok=True)
    seed_if_needed(DB_PATH)
    seed_hotel(DB_PATH)
    yield

DISABLE_OPENAPI_JSON = os.getenv("DISABLE_OPENAPI_JSON", "false").lower() == "true"

app = FastAPI(
    title="Hotel API",
    version="2.0.0",
    description="Backend for demo courses and Hotel Booking (rooms, availability, bookings).",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)

if DISABLE_OPENAPI_JSON:
    app.openapi_url = None

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
# Email helper
# =========================
def _send_booking_email(subject: str, html: str, to_addr: str):
    user = os.getenv("GMAIL_USER") or os.getenv("SMTP_USER")
    pwd = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASS")
    if not user or not pwd:
        print("[notify] Email skipped (no creds).")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content("HTML version required.")
    msg.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(user, pwd)
        smtp.send_message(msg)
    print(f"[notify] Email sent to {to_addr}")

# =========================
# DB helpers
# =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _column_exists(conn, table: str, column: str) -> bool:
    try:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any((c[1] == column) for c in cols)
    except Exception:
        return False

def init_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            fee REAL NOT NULL,
            start_date TEXT,
            end_date TEXT,
            time TEXT,
            venue TEXT,
            seats INTEGER DEFAULT 0
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS enrollments (
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
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            q TEXT,
            a TEXT
        )""")
        if not _column_exists(conn, "courses", "seats"):
            conn.execute("ALTER TABLE courses ADD COLUMN seats INTEGER DEFAULT 0")
        conn.commit()

def init_hotel_db():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS room_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS room_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_type_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            price REAL NOT NULL,
            left INTEGER NOT NULL,
            UNIQUE(room_type_id, date)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_type_id INTEGER NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            name TEXT,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quantity INTEGER DEFAULT 1
        )""")
        if not _column_exists(conn, "bookings", "quantity"):
            conn.execute("ALTER TABLE bookings ADD COLUMN quantity INTEGER DEFAULT 1")
        conn.commit()

init_db()
init_hotel_db()

# =========================
# Admin Key Guard
# =========================
ADMIN_KEY = os.getenv("ADMIN_KEY") or os.getenv("VITE_BCM_ADMIN_KEY")
api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)

def require_admin(x_admin_key: str = Security(api_key_header)):
    if not ADMIN_KEY:
        raise HTTPException(500, "ADMIN_KEY not configured")
    if not x_admin_key or x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "Forbidden")
    return True

# =========================
# Basic routes
# =========================
@app.get("/")
def root():
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        return RedirectResponse(url="/static/index.html")
    return {"ok": True, "message": "Hotel API running", "docs": "/docs"}

@app.get("/health")
def health():
    return {"ok": True}

# =========================
# Hotel Endpoints
# =========================
from datetime import datetime, timedelta

@app.get("/room_types", tags=["Hotel"])
def list_room_types():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name FROM room_types ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

@app.get("/availability", tags=["Hotel"])
def availability(room_type: int, start: str, end: str):
    if DEMO_MODE:
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
            SELECT date, price, left FROM room_inventory
            WHERE room_type_id = ? AND date >= ? AND date <= ?
            ORDER BY date ASC
        """, (room_type, start, end)).fetchall()
        return {r["date"]: {"price": float(r["price"]), "left": int(r["left"])} for r in rows}

# =========================
# Compatibility / Demo endpoint
# =========================
@app.get("/rooms", tags=["Hotel"])
def get_demo_rooms():
    """Return demo room list with prices for backward compatibility."""
    return [
        {"id": 1, "name": "标准客房 / Standard Room", "price": 800},
        {"id": 2, "name": "豪华客房 / Deluxe Room", "price": 1200},
        {"id": 3, "name": "家庭套房 / Family Suite", "price": 1500},
        {"id": 4, "name": "总统套房 / Presidential Suite", "price": 2500},
    ]

class BookIn(BaseModel):
    room_type: int
    check_in: str
    check_out: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    quantity: int = Field(1, ge=1, le=10)

@app.post("/book", tags=["Hotel"])
def book(payload: BookIn):
    if DEMO_MODE:
        return {"ok": True, "message": f"[DEMO] Booking confirmed {payload.check_in}→{payload.check_out}"}
    qty = int(payload.quantity or 1)
    with get_db() as c:
        nights = c.execute("""
            SELECT date, left FROM room_inventory
            WHERE room_type_id=? AND date>=? AND date<?
            ORDER BY date ASC
        """, (payload.room_type, payload.check_in, payload.check_out)).fetchall()
        if not nights:
            raise HTTPException(400, "No inventory")
        if any(int(r["left"]) < qty for r in nights):
            raise HTTPException(409, "Sold out")
        for r in nights:
            c.execute("""UPDATE room_inventory
                         SET left=left-? WHERE room_type_id=? AND date=? AND left>=?""",
                      (qty, payload.room_type, r["date"], qty))
        c.execute("""INSERT INTO bookings (room_type_id, check_in, check_out, name, email, phone, notes, quantity)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (payload.room_type, payload.check_in, payload.check_out,
                   payload.name, payload.email, payload.phone, payload.notes, qty))
        c.commit()
    return {"ok": True, "message": f"Booking confirmed {qty} room(s)."}

@app.get("/bookings", tags=["Hotel"])
def list_bookings(limit: int = Query(10, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM bookings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

# =========================
# Bilingual Docs
# =========================
@app.get("/docs", include_in_schema=False)
async def custom_bilingual_docs(request: Request, lang: str = "zh"):
    lang = "zh" if str(lang).lower().startswith("zh") else "en"
    if DISABLE_OPENAPI_JSON:
        return HTMLResponse("<h2>OpenAPI disabled.</h2>", status_code=503)

    html = f"""
<!DOCTYPE html>
<html lang="{{ 'zh-CN' if lang=='zh' else 'en' }}">
<head>
  <meta charset="utf-8"/>
  <title>{{"酒店预订 API 文档" if lang=="zh" else "Hotel Booking API Docs"}}</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css"/>
  <style>
    body {{ margin:0; background:#ffffff; }}
    .topbar {{ display:flex; justify-content:space-between; align-items:center; padding:8px 16px; background:#f0f0f0; }}
    .topbar .title {{ font-weight:700; }}
    .lang-box select {{ padding:6px 10px; border-radius:8px; }}
    #swagger-ui {{ max-width:1400px; margin:0 auto; background:#ffffff; }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="title">{{'酒店预订 API 文档' if lang=='zh' else 'Hotel Booking API Docs'}}</div>
    <div class="lang-box">
      <select id="langSelect">
        <option value="en" {{"selected" if lang=="en" else ""}}>English</option>
        <option value="zh" {{"selected" if lang=="zh" else ""}}>中文</option>
      </select>
    </div>
  </div>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>
    const LANG="{lang}";
    window.ui=SwaggerUIBundle({{
      url:"{app.openapi_url or '/openapi.json'}",
      dom_id:'#swagger-ui',
      deepLinking:true,
      presets:[SwaggerUIBundle.presets.apis],
      layout:"BaseLayout"
    }});
    document.getElementById('langSelect').addEventListener('change',function(){{
      const u=new URL(window.location.href);u.searchParams.set('lang',this.value);window.location.href=u.toString();
    }});
  </script>
</body>
</html>
    """
    return HTMLResponse(html)

# Entry
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
