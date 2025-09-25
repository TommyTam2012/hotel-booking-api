from fastapi import FastAPI, HTTPException, Query, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse, Response, FileResponse, JSONResponse, HTMLResponse
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
import smtplib, ssl
from email.message import EmailMessage

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

# Optional switch to disable serving /openapi.json (Swagger needs it; only disable if you accept that /docs won't load)
DISABLE_OPENAPI_JSON = os.getenv("DISABLE_OPENAPI_JSON", "false").lower() == "true"

app = FastAPI(
    title="Hotel API",
    version="2.0.0",
    description="Backend for BCM demo (courses, enrollments) and Hotel Booking (rooms, availability, bookings).",
    lifespan=lifespan,
    docs_url=None,   # disable built-in Swagger UI (we serve our own bilingual /docs)
    redoc_url=None   # disable built-in ReDoc (we serve our own bilingual /redoc)
)

# If explicitly requested, block schema (NOTE: this breaks Swagger UI)
if DISABLE_OPENAPI_JSON:
    app.openapi_url = None  # removes /openapi.json route

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
# Email helper (supports GMAIL_* and legacy SMTP_* envs)
# =========================
def _send_booking_email(subject: str, html: str, to_addr: str):
    # Prefer the new names; fall back to legacy if present
    user = os.getenv("GMAIL_USER") or os.getenv("SMTP_USER")
    pwd  = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASS")

    if not user or not pwd:
        print("[notify] GMAIL_USER/GMAIL_APP_PASSWORD (or SMTP_USER/SMTP_PASS) not set; skipping email.")
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
    return {"ok": True, "message": "Hotel API running", "docs": "/docs"}

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

    # --- notify by email ---
    to_addr = os.getenv("NOTIFY_TO", "tommytam2012@gmail.com")
    subject = f"New Booking: RT#{payload.room_type} {payload.check_in} → {payload.check_out} (x{qty})"
    html = f"""
    <h2>New Booking Confirmed</h2>
    <ul>
      <li><b>Room Type ID:</b> {payload.room_type}</li>
      <li><b>Check-in:</b> {payload.check_in}</li>
      <li><b>Check-out:</b> {payload.check_out}</li>
      <li><b>Quantity:</b> {qty}</li>
      <li><b>Name:</b> {payload.name}</li>
      <li><b>Email:</b> {payload.email or '-'}</li>
      <li><b>Phone:</b> {payload.phone or '-'}</li>
      <li><b>Notes:</b> {payload.notes or '-'}</li>
    </ul>
    <p>Sent by Hotel API.</p>
    """
    try:
        _send_booking_email(subject, html, to_addr)
    except Exception as e:
        print(f"[notify] Failed to send email: {e}")

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
# If you need them added here, paste your existing BCM routes below.

# =========================================================
# ============ BILINGUAL DOCS (/docs & /redoc) ============
# =========================================================
@app.get("/docs", include_in_schema=False)
async def custom_bilingual_docs(request: Request, lang: str = "zh"):
    # default to Chinese; switch with ?lang=en
    lang = "zh" if str(lang).lower().startswith("zh") else "en"

    # If schema disabled, show a helpful message (Swagger can't render without it)
    if DISABLE_OPENAPI_JSON:
        warn = "已禁用 /openapi.json，因此无法显示 Swagger 文档。请取消环境变量 DISABLE_OPENAPI_JSON 再试。"
        return HTMLResponse(f"<html><body><h2>{warn}</h2></body></html>", status_code=503)

    html = f"""
<!DOCTYPE html>
<html lang="{ 'zh-CN' if lang=='zh' else 'en' }">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{"酒店预订 API 文档" if lang=="zh" else "Hotel Booking API Docs"}</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css"/>
  <style>
    body {{ margin:0; background:#0b1220; }}
    .topbar {{ display:flex; justify-content:space-between; align-items:center; padding:8px 16px; background:#0f172a; }}
    .topbar .title {{ color:#e5e7eb; font-weight:700; }}
    .lang-box select {{ background:#111827; color:#e5e7eb; border:1px solid #374151; padding:6px 10px; border-radius:8px; }}
    #swagger-ui {{ max-width: 1400px; margin: 0 auto; background:#0b1220; }}
    .swagger-ui .opblock-tag.no-desc span,
    .swagger-ui .opblock-tag small,
    .swagger-ui .model-title,
    .swagger-ui .info .title,
    .swagger-ui .info p,
    .swagger-ui .markdown p,
    .swagger-ui,
    .swagger-ui * {{ color: #e5e7eb !important; }}
    .swagger-ui .opblock {{ background:#0f172a; border-color:#1f2937; }}
    .swagger-ui .info .title small.version-stamp {{ color:#93c5fd !important; border-color:#1f2937; }}
    .swagger-ui .opblock .opblock-section-header {{ background:#111827; }}
    .swagger-ui .tab li, .swagger-ui .opblock-summary-method {{ color:#111827 !important; }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="title">{'酒店预订 API 文档' if lang=='zh' else 'Hotel Booking API Docs'}</div>
    <div class="lang-box">
      <select id="langSelect" aria-label="Language">
        <option value="en" {"selected" if lang=="en" else ""}>English</option>
        <option value="zh" {"selected" if lang=="zh" else ""}>中文</option>
      </select>
    </div>
  </div>
  <div id="swagger-ui"></div>

  <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>
    // --- Simple i18n dictionary for common Swagger UI labels ---
    const I18N = {{
      zh: {{
        "Authorize": "授权",
        "Try it out": "试一试",
        "Execute": "执行",
        "Cancel": "取消",
        "Clear": "清除",
        "Parameters": "参数",
        "Request body": "请求体",
        "Responses": "响应",
        "Response": "响应",
        "Example Value": "示例值",
        "Schema": "模式",
        "Curl": "Curl 命令",
        "Request URL": "请求 URL",
        "Server": "服务器",
        "Servers": "服务器",
        "Request samples": "请求示例",
        "Response samples": "响应示例",
        "Download": "下载",
        "Copy": "复制",
        "Hide": "隐藏",
        "Show": "显示",
        "No content": "无内容",
        "Model": "模型"
      }},
      en: {{}}
    }};
    const LANG = "{lang}";

    function translateUI() {{
      if (LANG !== "zh") return; // English default
      const map = I18N.zh;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
      const targets = [];
      while (walker.nextNode()) {{
        const node = walker.currentNode;
        const src = node.nodeValue && node.nodeValue.trim();
        if (!src) continue;
        const t = map[src];
        if (t) targets.push([node, t]);
      }}
      targets.forEach(([node, t]) => {{
        node.nodeValue = node.nodeValue.replace(node.nodeValue.trim(), t);
      }});
    }}

    const observer = new MutationObserver(() => translateUI());
    observer.observe(document.body, {{ childList:true, subtree:true }});

    // Init Swagger UI
    window.ui = SwaggerUIBundle({{
      url: "{app.openapi_url or '/openapi.json'}",
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [SwaggerUIBundle.presets.apis],
      layout: "BaseLayout"
    }});

    setTimeout(translateUI, 800);

    // Language switcher with URL persistence
    document.getElementById('langSelect').addEventListener('change', function() {{
      const v = this.value;
      const u = new URL(window.location.href);
      u.searchParams.set('lang', v);
      window.location.href = u.toString();
    }});
  </script>
</body>
</html>
    """
    return HTMLResponse(html)

@app.get("/redoc", include_in_schema=False)
async def custom_bilingual_redoc(request: Request, lang: str = "zh"):
    lang = "zh" if str(lang).lower().startswith("zh") else "en"

    if DISABLE_OPENAPI_JSON:
        warn = "已禁用 /openapi.json，因此无法显示 ReDoc 文档。请取消环境变量 DISABLE_OPENAPI_JSON 再试。"
        return HTMLResponse(f"<html><body><h2>{warn}</h2></body></html>", status_code=503)

    title = "酒店预订 API 文档 (ReDoc)" if lang == "zh" else "Hotel Booking API Docs (ReDoc)"
    html = f"""
<!DOCTYPE html>
<html lang="{ 'zh-CN' if lang=='zh' else 'en' }">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title}</title>
  <style>
    body {{ margin:0; background:#0b1220; color:#e5e7eb; }}
    .topbar {{ display:flex; justify-content:space-between; align-items:center; padding:8px 16px; background:#0f172a; }}
    .topbar .title {{ color:#e5e7eb; font-weight:700; }}
    .lang-box select {{ background:#111827; color:#e5e7eb; border:1px solid #374151; padding:6px 10px; border-radius:8px; }}
    redoc, .menu-content, .api-content {{ --text-color-primary:#e5e7eb; --bg-color:#0b1220; }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="title">{title}</div>
    <div class="lang-box">
      <select id="langSelect" aria-label="Language">
        <option value="en" {"selected" if lang=="en" else ""}>English</option>
        <option value="zh" {"selected" if lang=="zh" else ""}>中文</option>
      </select>
    </div>
  </div>
  <redoc spec-url="{app.openapi_url or '/openapi.json'}"></redoc>
  <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
  <script>
    document.getElementById('langSelect').addEventListener('change', function(){{
      const v = this.value;
      const u = new URL(window.location.href);
      u.searchParams.set('lang', v);
      window.location.href = u.toString();
    }});
  </script>
</body>
</html>
    """
    return HTMLResponse(html)

# Optional: local dev entrypoint
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
