import os
from PIL import Image

src_path = r"C:\Users\SHIV\Downloads\Glossy Emerald Sunrise Ribbon Logo.png"
frontend_dir = r"d:\Projects\LLM (GenAI)\Whatsapp_budget_tracker\frontend"

im = Image.open(src_path)
print("Source image loaded:", im.size, im.mode)

# 1. Save full logo as frontend/logo_saarth.png
dst_logo = os.path.join(frontend_dir, "logo_saarth.png")
im.save(dst_logo, "PNG")
print("Saved:", dst_logo)

# Also replace Logo_ABT.png if it exists
dst_abt = os.path.join(frontend_dir, "Logo_ABT.png")
im.save(dst_abt, "PNG")
print("Replaced:", dst_abt)

# 2. Resize to 192x192 icon-192.png
im_192 = im.resize((192, 192), Image.Resampling.LANCZOS)
dst_192 = os.path.join(frontend_dir, "icon-192.png")
im_192.save(dst_192, "PNG")
print("Saved:", dst_192)

# 3. Resize to 512x512 icon-512.png
im_512 = im.resize((512, 512), Image.Resampling.LANCZOS)
dst_512 = os.path.join(frontend_dir, "icon-512.png")
im_512.save(dst_512, "PNG")
print("Saved:", dst_512)

# 4. Crop transparent borders for favicon if any, and resize to 64x64
bbox = im.getbbox()
if bbox:
    cropped = im.crop(bbox)
else:
    cropped = im
# Square pad cropped image
max_dim = max(cropped.size)
square = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
offset = ((max_dim - cropped.size[0]) // 2, (max_dim - cropped.size[1]) // 2)
square.paste(cropped, offset)

favicon = square.resize((64, 64), Image.Resampling.LANCZOS)
dst_fav = os.path.join(frontend_dir, "favicon.png")
favicon.save(dst_fav, "PNG")
print("Saved:", dst_fav)

# Also check if there is a favicon.ico or favicon in root
dst_fav_ico = os.path.join(frontend_dir, "favicon.ico")
favicon.save(dst_fav_ico, format="ICO", sizes=[(32, 32), (64, 64)])
print("Saved:", dst_fav_ico)
