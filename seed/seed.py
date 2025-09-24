# seed/seed.py
"""
Idempotent seeding for BCM demo data (courses, faq).
Safe to call at startup; inserts only when tables are empty.
"""

import sqlite3
from pathlib import Path

def _table_has_rows(conn: sqlite3.Connection, table: str) -> bool:
    try:
        cur = conn.execute(f"SELECT 1 FROM {table} LIMIT 1;")
        return cur.fetchone() is not None
    except Exception:
        return False

def seed_if_needed(db_path: str | Path) -> None:
    db_path = str(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # Ensure core tables exist (defensive)
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
            );
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
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                q TEXT,
                a TEXT
            );
        """)

        inserted = False

        # Seed demo courses if empty
        if not _table_has_rows(conn, "courses"):
            courses = [
                ("IELTS Intensive (Weekend)", 2980.0, "2025-10-05", "2025-11-30", "Sat–Sun 10:00–12:00", "TAEASLA HQ", 20),
                ("HKDSE English Skills Lab",   2380.0, "2025-10-08", "2025-12-10", "Wed 19:00–21:00",    "TAEASLA HQ", 18),
                ("Gaokao Reading AI Helper",   1880.0, "2025-10-10", "2025-12-05", "Fri 19:30–21:00",    "Online (Zoom)", 50),
            ]
            conn.executemany("""
                INSERT INTO courses (name, fee, start_date, end_date, time, venue, seats)
                VALUES (?,?,?,?,?,?,?)
            """, courses)
            inserted = True

        # Seed FAQs if empty
        if not _table_has_rows(conn, "faq"):
            faqs = [
                ("How do I enroll?", "Use /enroll (web form) or contact us on WeChat. A staff member will confirm your seat."),
                ("Do you offer online lessons?", "Yes. Many classes are hybrid with Zoom access."),
                ("Can I get a receipt for reimbursement?", "Absolutely. We issue official receipts on request."),
            ]
            conn.executemany("INSERT INTO faq (q, a) VALUES (?,?)", faqs)
            inserted = True

        if inserted:
            conn.commit()
            print("Seeded BCM demo data (courses/faq).")
        else:
            print("BCM demo data already present; skipping seed.")
