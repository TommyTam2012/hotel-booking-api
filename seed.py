# seed.py
import sqlite3, os
from datetime import date, timedelta

def seed_if_needed(db_file: str):
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.cursor()

    # Tables
    cur.execute("""CREATE TABLE IF NOT EXISTS room_types(
      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);""")
    cur.execute("""CREATE TABLE IF NOT EXISTS availability(
      day TEXT NOT NULL, room_type_id INTEGER NOT NULL,
      price INTEGER NOT NULL, left INTEGER NOT NULL,
      PRIMARY KEY(day, room_type_id),
      FOREIGN KEY(room_type_id) REFERENCES room_types(id));""")

    # If already seeded, exit quick
    cur.execute("SELECT COUNT(1) FROM room_types;")
    if cur.fetchone()[0] > 0:
        conn.close(); return  # already seeded

    # Seed 8 room types
    room_types = [
      (1,"标准大床房"),(2,"标准双床房"),(3,"高级大床房"),(4,"豪华海景房"),
      (5,"家庭房"),(6,"行政套房"),(7,"总统套房"),(8,"无障碍客房")
    ]
    cur.executemany("INSERT OR IGNORE INTO room_types(id,name) VALUES(?,?)", room_types)

    # Seed 120 days
    BASE_PRICE = {1:580,2:620,3:720,4:880,5:980,6:1280,7:2880,8:650}
    BASE_STOCK = {1:10,2:10,3:8,4:6,5:5,6:4,7:2,8:2}
    start = date.today()
    rows = []
    for d in range(120):
      day = (start).fromordinal(start.toordinal()+d)
      is_weekend = day.weekday() in (4,5)
      for rt in BASE_PRICE:
        price = BASE_PRICE[rt] + (80 if is_weekend else 0)
        rows.append((day.isoformat(), rt, price, BASE_STOCK[rt]))

    cur.executemany("""
      INSERT INTO availability(day,room_type_id,price,left)
      VALUES(?,?,?,?)
      ON CONFLICT(day,room_type_id) DO UPDATE SET
        price=excluded.price, left=excluded.left;
    """, rows)

    conn.commit(); conn.close()
