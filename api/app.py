# api/app.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel  # swap to EmailStr if desired
from typing import Optional, List, Dict, Any
from pathlib import Path
import os
import sqlite3
from openai import OpenAI

# --- Paths ---
APP_DIR = Path(__file__).parent.resolve()
DB_PATH = str(APP_DIR / "bcm.db")

# --- App ---
app = FastAPI(title="BCM Demo API")

# Static files (serve /static/enroll.html, etc.)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

# CORS (dev-safe defaults)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # set True only with explicit origins
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
        c.execute("""
        CREATE TABLE IF NOT EXISTS faq(
          intent TEXT PRIMARY KEY,
          question TEXT,
          answer TEXT
        );
        """)
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
        c.execute("""
        INSERT OR IGNORE INTO faq(intent, question, answer)
        VALUES ('TEST_INTENT','Test Q?','Test A.');
        """)
        conn.commit()

@app.on_event("startup")
def on_startup():
    init_db()

# --- Convenience: open the form by default ---
@app.get("/")
def root():
    return RedirectResponse(url="/static/enroll.html")

@app.get("/health")
def health():
    return {"ok": True}

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
    # Accept either 'full_name' or 'name' (from the simple HTML form)
    full_name: Optional[str] = None
    name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    program_code: Optional[str] = None
    cohort_code: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "avatar"

# --- Routes ---
@app.post("/enroll")
def enroll(data: EnrollmentIn):
    full_name_val = data.full_name or data.name
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
    return {"status": "ok"}

@app.get("/enrollments/recent")
def recent_enrollments(
    limit: int = Query(10, ge=1, le=100),
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = """
      SELECT id, full_name, email, program_code, source, created_at
      FROM enrollments
    """
    params: List[Any] = []
    if source:
        sql += " WHERE source = ?"
        params.append(source)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

class ChatIn(BaseModel):
    message: str

@app.post("/chat")
def chat(in_: ChatIn):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise, helpful assistant."},
                {"role": "user", "content": in_.message},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        return {"reply": resp.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")
