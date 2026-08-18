import sqlite3

conn = sqlite3.connect('giotag.db')
cursor = conn.cursor()
cursor.execute("SELECT email, is_active, role FROM users")
for row in cursor.fetchall():
    print(row)
conn.close()
