from app.db import get_db_cursor, get_app_setting, set_app_setting

current = get_app_setting('maintenance_mode', 'not_set')
print("Current DB maintenance_mode setting:", current)

set_app_setting('maintenance_mode', 'false')
updated = get_app_setting('maintenance_mode', 'not_set')
print("Updated DB maintenance_mode setting:", updated)

# Also ensure init_db defaults have 'false'
with get_db_cursor() as cur:
    cur.execute("SELECT key, value FROM app_settings WHERE key = 'maintenance_mode';")
    row = cur.fetchone()
    print("Direct SQL row:", row)
