import os
import time

now = time.time()
# The request arrived at 13:27:45 local time.
# Check from 13:20 to now
start_time = now - 3600

search_roots = [
    r'C:\Users\SHIV\AppData\Local',
    r'C:\Users\SHIV\AppData\Roaming',
    r'C:\Users\SHIV\.gemini',
    r'd:\Projects\LLM (GenAI)',
]

found = []
for base in search_roots:
    for root, dirs, files in os.walk(base):
        # skip git and node_modules
        if '.git' in root or 'node_modules' in root or 'venv' in root or '.venv' in root:
            continue
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.ico')):
                fp = os.path.join(root, f)
                try:
                    mt = os.path.getmtime(fp)
                    if mt >= start_time:
                        found.append((mt, os.path.getsize(fp), fp))
                except Exception:
                    pass

found.sort(reverse=True)
print(f"Total found: {len(found)}")
for mt, sz, fp in found[:30]:
    print(f"{time.ctime(mt)} | {sz} bytes | {fp}")
