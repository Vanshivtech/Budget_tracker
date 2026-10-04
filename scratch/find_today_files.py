import os
import datetime

today = datetime.date(2026, 10, 4)
base = r'C:\Users\SHIV\.gemini'

for root, dirs, files in os.walk(base):
    for f in files:
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            p = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(p)
                mdate = datetime.date.fromtimestamp(mtime)
                if mdate >= today:
                    print(f"{p} ({os.path.getsize(p)} bytes, mtime={mtime})")
            except Exception:
                pass
