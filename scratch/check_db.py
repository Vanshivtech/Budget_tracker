from app.db import get_db_cursor, init_db

init_db()
with get_db_cursor() as cur:
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    rows = cur.fetchall()
    print("Tables in public schema:")
    for r in rows:
        print(" -", r["table_name"])
