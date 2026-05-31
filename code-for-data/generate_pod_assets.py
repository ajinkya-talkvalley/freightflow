"""
Generate 30 POD JPEG images and package them into freightflow-assets.zip.

Conforms to FreightFlow_Schema_Spec.md §3.7 (filename convention) and §5.4
(zip contents and size budget).
"""

import argparse
import io
import os
import random
import sys
import zipfile
from pathlib import Path

# Require Pillow 10+
try:
    import PIL
    _ver = tuple(int(x) for x in PIL.__version__.split(".")[:2])
    if _ver < (10, 0):
        sys.exit(f"Pillow 10+ required; found {PIL.__version__}")
except ImportError:
    sys.exit("Pillow is not installed. Run: pip install 'Pillow>=10'")

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 800, 600
JPEG_QUALITY_BASE = 87          # starting quality; raised if image < 50 KB
JPEG_QUALITY_MAX = 95
MIN_SIZE_BYTES = 50 * 1024      # 50 KB
MAX_SIZE_BYTES = 200 * 1024     # 200 KB
NUM_IMAGES = 30
FONT_SIZE_TRACKING = 64         # ≥ 60 px as required

# Cardboard-brown palette
COLOR_BG_TOP    = (180, 130,  80)
COLOR_BG_BOTTOM = (140,  95,  50)
COLOR_BOX_LINE  = (100,  68,  30)
COLOR_TAPE      = (230, 210, 160)
COLOR_BARCODE_DARK  = ( 60,  40,  15)
COLOR_BARCODE_LIGHT = (200, 175, 130)
COLOR_TEXT      = ( 20,  10,   5)
COLOR_TEXT_SHADOW = (220, 190, 120)

# Font search order
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
]

# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    # Download a fallback TTF (DejaVu subset from GitHub releases)
    import urllib.request
    fallback = Path(__file__).parent / "_fallback_DejaVuSans-Bold.ttf"
    if not fallback.exists():
        url = (
            "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/"
            "ttf/DejaVuSans-Bold.ttf"
        )
        print(f"Downloading fallback font from {url} …", flush=True)
        urllib.request.urlretrieve(url, fallback)
    return ImageFont.truetype(str(fallback), size)


# ---------------------------------------------------------------------------
# Image rendering
# ---------------------------------------------------------------------------

def _draw_gradient_bg(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    """Fill background with a cardboard-brown vertical gradient."""
    r0, g0, b0 = COLOR_BG_TOP
    r1, g1, b1 = COLOR_BG_BOTTOM
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        r = int(r0 + (r1 - r0) * t)
        g = int(g0 + (g1 - g0) * t)
        b = int(b0 + (b1 - b0) * t)
        # Add slight horizontal noise for texture
        noise = rng.randint(-6, 6)
        draw.line([(0, y), (WIDTH, y)],
                  fill=(max(0, min(255, r + noise)),
                        max(0, min(255, g + noise)),
                        max(0, min(255, b + noise))))


def _draw_box_outlines(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    """Draw 3–5 overlapping rectangle outlines suggesting cardboard boxes."""
    num_boxes = rng.randint(3, 5)
    for _ in range(num_boxes):
        x0 = rng.randint(20, 200)
        y0 = rng.randint(20, 150)
        x1 = rng.randint(550, 760)
        y1 = rng.randint(380, 560)
        lw = rng.randint(2, 5)
        draw.rectangle([x0, y0, x1, y1], outline=COLOR_BOX_LINE, width=lw)
        # Cross-hatch fold lines
        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2
        draw.line([(x0, y0), (x1, y1)], fill=COLOR_BOX_LINE, width=1)
        draw.line([(x0, cy), (x1, cy)], fill=COLOR_BOX_LINE, width=1)
        draw.line([(cx, y0), (cx, y1)], fill=COLOR_BOX_LINE, width=1)


def _draw_tape_stripes(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    """Draw 2–4 horizontal semi-transparent tape stripes."""
    num_stripes = rng.randint(2, 4)
    for _ in range(num_stripes):
        y = rng.randint(60, HEIGHT - 60)
        h = rng.randint(14, 28)
        alpha = rng.randint(130, 190)
        r, g, b = COLOR_TAPE
        draw.rectangle(
            [(0, y - h // 2), (WIDTH, y + h // 2)],
            fill=(r, g, b),
        )
        # Add subtle inner highlight
        draw.line(
            [(0, y - h // 2 + 2), (WIDTH, y - h // 2 + 2)],
            fill=(min(255, r + 20), min(255, g + 20), min(255, b + 20)),
        )


def _draw_barcode(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    """Draw a vertical-bar barcode-like pattern on the right margin."""
    bar_x_start = WIDTH - 120
    bar_height = 160
    bar_y_start = (HEIGHT - bar_height) // 2 + rng.randint(-30, 30)
    x = bar_x_start
    while x < WIDTH - 10:
        w = rng.randint(1, 5)
        color = COLOR_BARCODE_DARK if rng.random() > 0.4 else COLOR_BARCODE_LIGHT
        draw.rectangle(
            [(x, bar_y_start), (x + w - 1, bar_y_start + bar_height)],
            fill=color,
        )
        x += w + rng.randint(1, 3)


def _draw_label_box(draw: ImageDraw.ImageDraw) -> None:
    """Draw a white label area in the center for the tracking number."""
    pad_x, pad_y = 100, 200
    draw.rectangle(
        [(pad_x, pad_y), (WIDTH - pad_x, HEIGHT - pad_y)],
        fill=(255, 255, 255),
        outline=COLOR_BOX_LINE,
        width=3,
    )


def render_image(tracking_number: str, rng: random.Random,
                 quality: int, font: ImageFont.FreeTypeFont) -> bytes:
    """Render one POD image and return raw JPEG bytes."""
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG_TOP)
    draw = ImageDraw.Draw(img)

    _draw_gradient_bg(draw, rng)
    _draw_box_outlines(draw, rng)
    _draw_tape_stripes(draw, rng)
    _draw_barcode(draw, rng)
    _draw_label_box(draw)

    # Tracking number centred inside label box
    label_cx = WIDTH // 2
    label_cy = HEIGHT // 2
    bbox = draw.textbbox((0, 0), tracking_number, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = label_cx - tw // 2
    ty = label_cy - th // 2

    # Shadow
    draw.text((tx + 3, ty + 3), tracking_number, font=font,
              fill=COLOR_TEXT_SHADOW)
    # Main text
    draw.text((tx, ty), tracking_number, font=font, fill=COLOR_TEXT)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate 30 POD JPEG images and package into freightflow-assets.zip"
    )
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    zip_path = repo_root / "freightflow-assets.zip"

    if zip_path.exists():
        print(f"WARNING: {zip_path} already exists — overwriting.", flush=True)
        zip_path.unlink()

    font = _load_font(FONT_SIZE_TRACKING)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(1, NUM_IMAGES + 1):
            tracking_number = f"FF-{i:06d}"
            filename = f"pod_{tracking_number}.jpg"

            # Each image gets a deterministic sub-seed derived from master seed
            rng = random.Random(args.seed + i)
            quality = JPEG_QUALITY_BASE

            jpeg_bytes = render_image(tracking_number, rng, quality, font)

            # Re-render at higher quality if too small (more detail via noise)
            attempts = 0
            while len(jpeg_bytes) < MIN_SIZE_BYTES and quality < JPEG_QUALITY_MAX:
                quality = min(quality + 3, JPEG_QUALITY_MAX)
                # Reset rng to same state for reproducibility of detail pass
                rng = random.Random(args.seed + i)
                jpeg_bytes = render_image(tracking_number, rng, quality, font)
                attempts += 1
                if attempts > 5:
                    break

            size_kb = len(jpeg_bytes) / 1024
            if size_kb < 50:
                print(f"  WARNING: {filename} is {size_kb:.1f} KB (< 50 KB target)",
                      flush=True)
            elif size_kb > 200:
                print(f"  WARNING: {filename} is {size_kb:.1f} KB (> 200 KB target)",
                      flush=True)

            zf.writestr(filename, jpeg_bytes)
            print(f"  {filename}: {size_kb:.1f} KB (quality={quality})", flush=True)

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Generated freightflow-assets.zip: {NUM_IMAGES} POD images, "
          f"{zip_size_mb:.2f} MB", flush=True)


if __name__ == "__main__":
    main()
