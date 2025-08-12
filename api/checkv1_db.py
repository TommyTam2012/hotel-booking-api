import sqlite3

conn = sqlite3.connect("bcm.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cur.fetchall()
print("Tables in bcm.db:", [t[0] for t in tables])

cur.execute("SELECT intent, question, answer FROM faq LIMIT 1;")
row = cur.fetchone()
print("Example FAQ row:", row)

conn.close()
