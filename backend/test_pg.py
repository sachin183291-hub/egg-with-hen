import psycopg2
try:
    conn = psycopg2.connect(host='localhost', port=5432, dbname='giotag_db', user='giotag', password='giotag_secret')
    cur = conn.cursor()
    cur.execute("SELECT id, email, username, is_active FROM users WHERE email='admin@giotag.gov'")
    print("Before:", cur.fetchall())
    cur.execute("UPDATE users SET is_active=true WHERE email='admin@giotag.gov'")
    conn.commit()
    cur.execute("SELECT id, email, username, is_active FROM users WHERE email='admin@giotag.gov'")
    print("After:", cur.fetchall())
except Exception as e:
    print("Error:", e)
