# app.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel  # or EmailStr if you want validation
from typing import Optional, List, Dict, Any
import os
import sqlite3
from openai import OpenAI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bcm.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

app = FastAPI(title="BCM Demo API")

# CORS (dev-safe defaults)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # set True only with explicit origins
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class EnrollmentIn(BaseModel):
    full_name: str
    email: str  # swap to EmailStr if desired
    phone: Optional[str] = None
    program_code: Optional[str] = None
    cohort_code: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "avatar"

@app.post("/enroll")
def enroll(data: EnrollmentIn):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO enrollments
              (full_name, email, phone, program_code, cohort_code, timezone, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.full_name, data.email, data.phone, data.program_code,
            data.cohort_code, data.timezone, data.notes, data.source
        ))
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
    params = []
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
