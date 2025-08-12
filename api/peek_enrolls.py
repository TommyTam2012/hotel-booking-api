import sqlite3, json

c = sqlite3.connect("bcm.db")
c.row_factory = sqlite3.Row

rows = c.execute("""
  SELECT id, full_name, email, program_code, source, created_at
  FROM enrollments
  ORDER BY id DESC
  LIMIT 5
""").fetchall()

print(json.dumps([dict(r) for r in rows], indent=2))

