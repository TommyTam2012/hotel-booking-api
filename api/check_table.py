import sqlite3

c = sqlite3.connect("bcm.db")

print("DDL:", c.execute(
    "SELECT sql FROM sqlite_master WHERE name='enrollments'"
).fetchone()[0])

print("COLUMNS:", c.execute(
    "PRAGMA table_info(enrollments)"
).fetchall())

