import os
import time

for folder in [r'C:\Users\SHIV\Downloads', r'C:\Users\SHIV\Desktop', r'C:\Users\SHIV\Pictures']:
    if not os.path.exists(folder):
        continue
    for f in os.listdir(folder):
        fp = os.path.join(folder, f)
        if os.path.isfile(fp):
            if any(k in f.lower() for k in ['saarth', 'logo', 'abt', 'budget', 'icon', 's_']):
                print(f"{fp} | {os.path.getsize(fp)} | {time.ctime(os.path.getmtime(fp))}")
            elif f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and (time.time() - os.path.getmtime(fp) < 86400 * 3):
                print(f"RECENT: {fp} | {os.path.getsize(fp)} | {time.ctime(os.path.getmtime(fp))}")
