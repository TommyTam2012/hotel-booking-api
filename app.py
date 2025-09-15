from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"hello": "hotel"}
@app.get("/health")
def health():
    return {"status": "ok"}
import sqlite3
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"hello": "hotel"}

# simple connection helper (per-request)
def get_conn():
    conn = sqlite3.connect("hotel.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/hotels")
def list_hotels():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, address FROM hotels ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
