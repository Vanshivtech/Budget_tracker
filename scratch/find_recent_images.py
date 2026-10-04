import os
import time

now = time.time()
two_hours_ago = now - 7200

# Search common places for recent image files
paths_to_check = [
    r'd:\Projects\LLM (GenAI)\Whatsapp_budget_tracker',
    r'C:\Users\SHIV\Downloads',
    r'C:\Users\SHIV\Desktop',
    r'C:\Users\SHIV\AppData\Local\Temp',
    r'C:\Users\SHIV\.gemini\antigravity-ide',
]

for base in paths_to_check:
    if not os.path.exists(base):
        continue
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                fp = os.path.join(root, f)
                try:
                    mt = os.path.getmtime(fp)
                    if mt >= two_hours_ago:
                        print(f"{fp} | {os.path.getsize(fp)} bytes | {time.ctime(mt)}")
                except Exception:
                    pass
