# app.py
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import sqlite3
from typing import Optional, List, Dict, Any
from fastapi.middleware.cors import CORSMiddleware  # <-- CORS import

DB_PATH = "bcm.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

app = FastAPI(title="BCM Demo API")

# ---- CORS Middleware ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, change to ["https://yourdomain.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Health check ----
@app.get("/health")
def health():
    return {"ok": True}

# ---- Get FAQ by intent ----
@app.get("/faq/{intent}")
def get_faq(intent: str):
    with get_db() as conn:
        cur = conn.execute(
            "SELECT question, answer FROM faq WHERE intent = ?",
            (intent,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="FAQ not found")
        return {
            "intent": intent,
            "question": row["question"],
            "answer": row["answer"],
        }

# ---- Enrollment model ----
class EnrollmentIn(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    program_code: Optional[str] = None
    cohort_code: Optional[str] = None
    timezone: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "avatar"

# ---- Add new enrollment ----
@app.post("/enroll")
def enroll(data: EnrollmentIn):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO enrollments
              (full_name, email, phone, program_code, cohort_code, timezone, notes, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.full_name,
                data.email,
                data.phone,
                data.program_code,
                data.cohort_code,
                data.timezone,
                data.notes,
                data.source,
            ),
        )
        conn.commit()
    return {"status": "ok"}

# ---- Recent enrollments (for LangChain/HeyGen reads) ----
@app.get("/enrollments/recent")
def recent_enrollments(
    limit: int = Query(10, ge=1, le=100),
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Returns the most recent enrollments.
    - limit: 1..100 (default 10)
    - source: optional filter, e.g. 'avatar', 'docs', 'agent', 'form'
    """
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
# ---- Chat endpoint for LangChain/HeyGen ----
class ChatIn(BaseModel):
    message: str
@app.post("/chat")
def chat(in_: ChatIn):
    # For now, just echo the message — replace with LangChain call later
    return {"reply": f"Echo: {in_.message}"}
