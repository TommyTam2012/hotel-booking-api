# init_db.py
import sqlite3
from datetime import date, timedelta

DB_PATH = "hotel.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# --- tables ---
cur.executescript("""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hotels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  address TEXT
);

CREATE TABLE IF NOT EXISTS rooms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hotel_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  type TEXT,
  capacity INTEGER NOT NULL DEFAULT 2,
  base_price REAL NOT NULL DEFAULT 100.0,
  FOREIGN KEY (hotel_id) REFERENCES hotels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id INTEGER NOT NULL,
  day TEXT NOT NULL,               -- ISO date string YYYY-MM-DD
  total INTEGER NOT NULL,
  booked INTEGER NOT NULL DEFAULT 0,
  UNIQUE(room_id, day),
  FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reservations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id INTEGER NOT NULL,
  guest_name TEXT NOT NULL,
  check_in TEXT NOT NULL,          -- ISO date
  check_out TEXT NOT NULL,         -- ISO date (exclusive)
  nights INTEGER NOT NULL,
  total_price REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'confirmed',
  created_at TEXT NOT NULL,
  FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
);
""")

# --- seed (idempotent) ---
cur.execute("INSERT INTO hotels(name, address) VALUES (?, ?)", (
    "Harbor View Hotel", "88 Seaside Road, Kowloon"
))
hotel_id = cur.lastrowid

rooms = [
    (hotel_id, "Standard 1", "standard", 2, 680.0),
    (hotel_id, "Deluxe 1",   "deluxe",   3, 980.0),
    (hotel_id, "Suite 1",    "suite",    4, 1680.0),
]
cur.executemany(
    "INSERT INTO rooms(hotel_id, name, type, capacity, base_price) VALUES (?, ?, ?, ?, ?)",
    rooms
)

# build 7 days of inventory for each room (today -> today+6)
today = date.today()
cur.execute("SELECT id FROM rooms WHERE hotel_id = ?", (hotel_id,))
room_ids = [r[0] for r in cur.fetchall()]

inv_rows = []
for rid in room_ids:
    for i in range(7):
        d = today + timedelta(days=i)
        inv_rows.append((rid, d.isoformat(), 5, 0))  # total=5, booked=0

cur.executemany(
    "INSERT OR IGNORE INTO inventory(room_id, day, total, booked) VALUES (?, ?, ?, ?)",
    inv_rows
)

conn.commit()
conn.close()
print(f"Initialized {DB_PATH} with sample hotel/rooms/inventory.")
