import sys
sys.path.insert(0, ".")
from app.db import get_db_cursor

with get_db_cursor() as cur:
    cur.execute("SELECT id, route, message, created_at FROM errors ORDER BY created_at DESC LIMIT 30;")
    rows = cur.fetchall()
    print(f"Total error rows in errors table (up to 30): {len(rows)}")
    for r in rows:
        print(f"[{r['created_at']}] Route: {r.get('route')} | Message: {r.get('message')}")
