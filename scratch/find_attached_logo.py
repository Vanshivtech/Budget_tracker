import json
import glob
import os
from PIL import Image

# Search all png files in tempmediaStorage
files = glob.glob(r'C:\Users\SHIV\.gemini\antigravity-ide\brain\862cf148-45ea-4691-ad47-7086ae924d06\.tempmediaStorage\*.*')
files.sort(key=os.path.getmtime, reverse=True)
print("Found files:")
for f in files[:20]:
    try:
        im = Image.open(f)
        print(f"{os.path.basename(f)}: size={im.size}, mode={im.mode}, mtime={os.path.getmtime(f)}")
    except Exception as e:
        print(f"{os.path.basename(f)}: {e}")
