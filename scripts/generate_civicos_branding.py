#!/usr/bin/env python3
"""Generate CivicOS branding assets (favicons, splash screens, logo PNGs).

Outputs directly to apps/civicos-openwebui-fork/static/static/.
Uses Pillow for rendering with supersampling for crisp anti-aliased strokes.

Requires: Pillow (pip install Pillow)
Font: Helvetica Neue Bold via /System/Library/Fonts/HelveticaNeue.ttc
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "apps" / "civicos-openwebui-fork" / "static" / "static"

# --- Solarized colors ---
LIGHT_CHEVRON = "#586e75"  # base01
LIGHT_TEXT = "#002b36"     # base03
DARK_CHEVRON = "#93a1a1"   # base1
DARK_TEXT = "#fdf6e3"      # base3

# --- Font ---
FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_INDEX = 1  # Bold variant in the TTC collection

# Supersampling factor
SS = 4


def draw_chevron(draw, cx, cy, size, color, stroke_width):
    """Draw a '<' chevron centered at (cx, cy) with given size.

    The chevron spans vertically from cy - size/2 to cy + size/2,
    and the tip is at cx - size*0.43 (left of center).
    """
    half = size / 2
    indent = size * 0.43  # horizontal depth of the chevron
    top = (cx + indent / 2, cy - half)
    tip = (cx - indent / 2, cy)
    bot = (cx + indent / 2, cy + half)
    draw.line([top, tip, bot], fill=color, width=int(stroke_width), joint="curve")
    # Round caps on endpoints
    r = stroke_width / 2
    for pt in [top, tip, bot]:
        draw.ellipse(
            [pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r],
            fill=color,
        )


def render_chevron_icon(size, color, ss=SS):
    """Render a chevron-only icon at the given final size."""
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    stroke = big * 0.104  # ~5/48 matching the SVG proportions
    draw_chevron(draw, big / 2, big / 2, big * 0.583, color, stroke)
    return img.resize((size, size), Image.LANCZOS)


def render_wordmark(size, chevron_color, text_color, ss=SS):
    """Render the full 'CivicOS' wordmark (chevron + 'ivicOS') centered in a square."""
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Layout: chevron on left, text on right, centered as a group
    chevron_h = big * 0.34
    stroke = big * 0.052

    # Load font - size relative to chevron
    font_size = int(chevron_h * 0.80)
    try:
        font = ImageFont.truetype(FONT_PATH, font_size, index=FONT_INDEX)
    except (OSError, IOError):
        print(f"Warning: Could not load {FONT_PATH}, falling back to default font")
        font = ImageFont.load_default()

    # Measure text
    text = "ivicOS"
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Chevron visual width including stroke
    chevron_indent = chevron_h * 0.43
    chevron_visual_w = chevron_indent + stroke  # account for rounded stroke caps
    gap = big * 0.01
    total_w = chevron_visual_w + gap + text_w

    # Center the group
    group_left = (big - total_w) / 2
    cy = big / 2

    # Draw chevron - position its center
    chev_cx = group_left + chevron_visual_w / 2
    draw_chevron(draw, chev_cx, cy, chevron_h, chevron_color, stroke)

    # Draw text - vertically centered, right of chevron
    text_x = group_left + chevron_visual_w + gap
    text_y = cy - text_h / 2 - bbox[1]  # adjust for font baseline offset
    draw.text((text_x, text_y), text, fill=text_color, font=font)

    return img.resize((size, size), Image.LANCZOS)


def save_ico(img, path, sizes=None):
    """Save an image as a multi-resolution ICO file."""
    if sizes is None:
        sizes = [48, 32, 16]
    ico_images = []
    for s in sizes:
        ico_images.append(img.resize((s, s), Image.LANCZOS))
    ico_images[0].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=ico_images[1:])


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Generating CivicOS branding assets...")

    # --- Chevron-only icons (light theme) ---
    print("  favicon.png (500x500, light)")
    render_chevron_icon(500, LIGHT_CHEVRON).save(OUTPUT_DIR / "favicon.png")

    print("  favicon-dark.png (500x500, dark)")
    render_chevron_icon(500, DARK_CHEVRON).save(OUTPUT_DIR / "favicon-dark.png")

    print("  favicon-96x96.png (96x96, light)")
    render_chevron_icon(96, LIGHT_CHEVRON).save(OUTPUT_DIR / "favicon-96x96.png")

    print("  apple-touch-icon.png (180x180, light)")
    render_chevron_icon(180, LIGHT_CHEVRON).save(OUTPUT_DIR / "apple-touch-icon.png")

    print("  web-app-manifest-192x192.png (192x192, light)")
    render_chevron_icon(192, LIGHT_CHEVRON).save(OUTPUT_DIR / "web-app-manifest-192x192.png")

    print("  web-app-manifest-512x512.png (512x512, light)")
    render_chevron_icon(512, LIGHT_CHEVRON).save(OUTPUT_DIR / "web-app-manifest-512x512.png")

    print("  favicon.ico (48/32/16, light)")
    icon_base = render_chevron_icon(48, LIGHT_CHEVRON, ss=8)  # Higher SS for small sizes
    save_ico(icon_base, OUTPUT_DIR / "favicon.ico")

    # --- Full wordmark images ---
    print("  splash.png (500x500, light)")
    render_wordmark(500, LIGHT_CHEVRON, LIGHT_TEXT).save(OUTPUT_DIR / "splash.png")

    print("  splash-dark.png (500x500, dark)")
    render_wordmark(500, DARK_CHEVRON, DARK_TEXT).save(OUTPUT_DIR / "splash-dark.png")

    print("  logo.png (500x500, light)")
    render_wordmark(500, LIGHT_CHEVRON, LIGHT_TEXT).save(OUTPUT_DIR / "logo.png")

    print(f"\nDone! {11} assets written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
