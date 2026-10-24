"""
Generate Android app launcher icons from frontend/icon-512.png (or icon-192.png).
Outputs standard launcher icons, round icons, and adaptive foreground icons across all mipmap densities,
plus anydpi-v26 adaptive icon XML configs, and removes conflicting default Capacitor vector drawables.
"""
import os
from pathlib import Path
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ICON_192 = PROJECT_ROOT / "frontend" / "icon-192.png"
SOURCE_ICON_512 = PROJECT_ROOT / "frontend" / "icon-512.png"
RES_DIR = PROJECT_ROOT / "android-app" / "android" / "app" / "src" / "main" / "res"

# Density mapping: (folder_name, launcher_size, foreground_size)
DENSITIES = [
    ("mipmap-mdpi", 48, 108),
    ("mipmap-hdpi", 72, 162),
    ("mipmap-xhdpi", 96, 216),
    ("mipmap-xxhdpi", 144, 324),
    ("mipmap-xxxhdpi", 192, 432),
]


def make_round_icon(img: Image.Image, size: int) -> Image.Image:
    """Create a circular-masked icon variant."""
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    round_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    round_img.paste(resized, (0, 0), mask=mask)
    return round_img


def generate_icons():
    # Prefer highest-resolution source available
    src_path = SOURCE_ICON_512 if SOURCE_ICON_512.exists() else SOURCE_ICON_192
    if not src_path.exists():
        raise FileNotFoundError(f"Source icon not found at {src_path} or {SOURCE_ICON_192}")

    print(f"Loading source icon: {src_path}")
    base_img = Image.open(src_path).convert("RGBA")

    RES_DIR.mkdir(parents=True, exist_ok=True)

    for folder_name, size, fg_size in DENSITIES:
        target_dir = RES_DIR / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Standard square/rounded launcher icon (e.g. 72x72)
        resized_icon = base_img.resize((size, size), Image.Resampling.LANCZOS)
        resized_icon.save(target_dir / "ic_launcher.png", format="PNG")

        # 2. Circular round icon variant
        round_icon = make_round_icon(base_img, size)
        round_icon.save(target_dir / "ic_launcher_round.png", format="PNG")
        print(f"Generated {folder_name}/ic_launcher.png & ic_launcher_round.png ({size}x{size})")

        # 3. Adaptive launcher foreground icon (centered with safe margins, e.g. 162x162)
        # Android adaptive foreground spec: 108dp total, 72dp safe central area (ratio ~ 72/108 = 0.666)
        fg_canvas = Image.new("RGBA", (fg_size, fg_size), (0, 0, 0, 0))
        inner_size = int(fg_size * 0.72)
        inner_icon = base_img.resize((inner_size, inner_size), Image.Resampling.LANCZOS)
        offset = (fg_size - inner_size) // 2
        fg_canvas.paste(inner_icon, (offset, offset), inner_icon)
        fg_canvas.save(target_dir / "ic_launcher_foreground.png", format="PNG")
        print(f"Generated {folder_name}/ic_launcher_foreground.png ({fg_size}x{fg_size})")

    # Update ic_launcher_background to match SAARTH dark theme
    values_dir = RES_DIR / "values"
    values_dir.mkdir(parents=True, exist_ok=True)
    bg_xml = values_dir / "ic_launcher_background.xml"
    bg_xml.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#0a0a0f</color>\n</resources>\n',
        encoding="utf-8",
    )
    print("Updated values/ic_launcher_background.xml to #0a0a0f")

    # Ensure anydpi-v26 adaptive icon configs are present and reference @mipmap/ic_launcher_foreground
    anydpi_dir = RES_DIR / "mipmap-anydpi-v26"
    anydpi_dir.mkdir(parents=True, exist_ok=True)
    adaptive_xml_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>\n'
        '</adaptive-icon>\n'
    )
    (anydpi_dir / "ic_launcher.xml").write_text(adaptive_xml_content, encoding="utf-8")
    (anydpi_dir / "ic_launcher_round.xml").write_text(adaptive_xml_content, encoding="utf-8")
    print("Updated mipmap-anydpi-v26/ic_launcher.xml and ic_launcher_round.xml")

    # Remove conflicting default Capacitor vector drawables that override mipmaps on Android 8+
    stale_files = [
        RES_DIR / "drawable-v24" / "ic_launcher_foreground.xml",
        RES_DIR / "drawable" / "ic_launcher_background.xml",
    ]
    for stale in stale_files:
        if stale.exists():
            try:
                stale.unlink()
                print(f"Removed conflicting vector drawable: {stale.relative_to(RES_DIR)}")
            except Exception as e:
                print(f"Warning: could not remove {stale}: {e}")


if __name__ == "__main__":
    generate_icons()
    print("All icons successfully generated!")
