# seed/seed_hotel.py
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "bcm_demo.db"

ROOM_TYPES = [
    "标准大床房",
    "标准双床房",
    "高级大床房",
    "豪华海景房",
    "家庭房",
    "行政套房",
    "总统套房",
    "无障碍客房"
]

def seed_hotel(db_path=DB_PATH, days=30):
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Ensure tables exist
    cur.execute("""
    CREATE TABLE IF NOT EXISTS room_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS room_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_type_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        price REAL NOT NULL,
        left INTEGER NOT NULL,
        UNIQUE(room_type_id, date)
    )
    """)

    # Insert room types
    for rt in ROOM_TYPES:
        cur.execute("INSERT OR IGNORE INTO room_types (name) VALUES (?)", (rt,))

    # Seed inventory for N days
    today = date.today()
    rows = cur.execute("SELECT id, name FROM room_types").fetchall()
    for rid, name in rows:
        for i in range(days):
            d = today + timedelta(days=i)
            price = base_price_for(name, d)
            left = 5  # default 5 rooms per night
            cur.execute("""
                INSERT OR IGNORE INTO room_inventory (room_type_id, date, price, left)
                VALUES (?,?,?,?)
            """, (rid, d.isoformat(), price, left))

    conn.commit()
    conn.close()
    print(f"Seeded {len(rows)} room types × {days} days.")

def base_price_for(name, d):
    # Simple price model: weekend +100, suites more expensive
    base = 600
    if "豪华" in name or "海景" in name: base = 880
    if "家庭" in name: base = 950
    if "行政" in name: base = 1200
    if "总统" in name: base = 2200
    if "无障碍" in name: base = 700
    # Weekend surcharge
    if d.weekday() >= 5: base += 100
    return float(base)

if __name__ == "__main__":
    seed_hotel()
