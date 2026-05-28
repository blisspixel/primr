"""Icon generation for the Cowork plugin .zip.

Two PNGs required:
  - color.png   192x192  full-color app icon
  - outline.png  32x32   single-color outline

The Cowork docs say solid-color placeholders are acceptable for sideload but
must be replaced before store submission — we generate exactly that, with a
deterministic color derived from the company name so repeated runs produce
identical icons.

Two backends:
  1. Pillow when available — preferred, produces a clean filled square with
     the company's initials.
  2. Embedded static PNG fallback — single 192x192 / 32x32 solid-color PNGs
     generated at module import time using a minimal hand-rolled PNG writer
     (no external dep). Used when Pillow is not installed.

Either way the bytes are deterministic for a given (company_name, size).
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from typing import Any

Image: Any = None
ImageDraw: Any = None
ImageFont: Any = None

try:
    from PIL import Image as _Image  # type: ignore[import-not-found]
    from PIL import ImageDraw as _ImageDraw  # type: ignore[import-not-found]
    from PIL import ImageFont as _ImageFont  # type: ignore[import-not-found]

    Image = _Image
    ImageDraw = _ImageDraw
    ImageFont = _ImageFont
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False


def _deterministic_color(company_name: str) -> tuple[int, int, int]:
    """Pick a deterministic accent color from a company name.

    Hashes the name to 3 bytes for RGB, then clamps to a "saturated but not
    eye-watering" range. Same input always produces the same color.
    """
    digest = hashlib.sha256(company_name.encode("utf-8")).digest()
    # Clamp each channel to [40, 220] so we avoid pure black and pure white
    # — those render poorly in both light and dark mode UIs.
    r = 40 + (digest[0] % 181)
    g = 40 + (digest[1] % 181)
    b = 40 + (digest[2] % 181)
    return r, g, b


def _complement_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Pick a visually compatible accent for gradient/shape highlights.

    Rotates roughly 60 degrees in RGB space — not a true hue rotation but
    close enough for non-clashing gradients, and deterministic.
    """
    r, g, b = rgb
    return (
        min(255, int(r * 0.6) + 60),
        min(255, int(b * 0.6) + 60),
        min(255, int(g * 0.6) + 60),
    )


def _shape_id(company_name: str) -> int:
    """Pick one of N shape archetypes deterministically from the company name.

    Cheap visual diversity that's still readable as a brand mark.
    """
    digest = hashlib.sha256(company_name.encode("utf-8")).digest()
    return digest[3] % 4  # 4 shape variants


def _initials(company_name: str) -> str:
    """First-letter initials of up to 2 words, uppercase."""
    words = [w for w in company_name.split() if w and w[0].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


# ---------------------------------------------------------------------------
# Minimal PNG writer (used only when Pillow is unavailable)
# ---------------------------------------------------------------------------


def _write_png_solid(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Write a solid-color RGB PNG without any external dependency.

    Uses Python stdlib only (zlib + struct). Output is a fully valid PNG —
    smoke-tested by writing one and reading back with PIL when available.
    """
    r, g, b = rgb

    def chunk(tag: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return length + tag + data + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,  # bit depth
        2,  # color type: truecolor RGB
        0,  # compression: deflate
        0,  # filter: adaptive
        0,  # interlace: none
    )
    # Each scanline: 1 filter byte (0 = None) + width * 3 bytes of RGB
    scanline = bytes([0]) + (bytes([r, g, b]) * width)
    raw = scanline * height
    idat = zlib.compress(raw, level=9)
    iend = b""
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", iend)


# ---------------------------------------------------------------------------
# Pillow path
# ---------------------------------------------------------------------------


def _build_color_png_with_pillow(
    company_name: str, size: int, rgb: tuple[int, int, int]
) -> bytes:
    """Pillow-rendered icon: vertical gradient + geometric shape + initials.

    Looks like a real brand mark rather than a flat color block. The shape
    archetype, accent color, and initials are all deterministic on the
    company name so re-runs produce identical bytes (manifest stability).
    """
    import io

    assert Image is not None
    assert ImageDraw is not None
    assert ImageFont is not None
    accent = _complement_color(rgb)

    # Vertical gradient background.
    bg = Image.new("RGB", (size, size), rgb)
    pixels = bg.load()
    for y in range(size):
        t = y / max(1, size - 1)
        ir = int(rgb[0] * (1 - t) + accent[0] * t)
        ig = int(rgb[1] * (1 - t) + accent[1] * t)
        ib = int(rgb[2] * (1 - t) + accent[2] * t)
        for x in range(size):
            pixels[x, y] = (ir, ig, ib)

    draw = ImageDraw.Draw(bg, "RGBA")

    # Geometric mark — choose one of 4 archetypes per company name.
    shape_id = _shape_id(company_name)
    mark_color = (255, 255, 255, 60)  # subtle white overlay
    center = size // 2
    radius = int(size * 0.36)
    if shape_id == 0:
        # Soft circle
        draw.ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            fill=mark_color,
        )
    elif shape_id == 1:
        # Tilted square (diamond)
        draw.polygon(
            [
                (center, center - radius),
                (center + radius, center),
                (center, center + radius),
                (center - radius, center),
            ],
            fill=mark_color,
        )
    elif shape_id == 2:
        # Rounded triangle (upward)
        draw.polygon(
            [
                (center, center - radius),
                (center + radius, center + radius // 2),
                (center - radius, center + radius // 2),
            ],
            fill=mark_color,
        )
    else:
        # Hex
        import math

        pts = []
        for i in range(6):
            ang = math.pi / 6 + i * math.pi / 3
            pts.append((center + radius * math.cos(ang), center + radius * math.sin(ang)))
        draw.polygon(pts, fill=mark_color)

    # Initials on top.
    initials = _initials(company_name)
    font = None
    for candidate in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(candidate, size=int(size * 0.42))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((size - tw) // 2 - bbox[0], (size - th) // 2 - bbox[1])
    draw.text(pos, initials, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    bg.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _build_outline_png_with_pillow(rgb: tuple[int, int, int]) -> bytes:
    """32x32 single-color outline icon — a 3px-stroked rounded square."""
    import io

    assert Image is not None
    assert ImageDraw is not None
    size = 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (2, 2, size - 3, size - 3),
        radius=6,
        outline=rgb,
        width=3,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_color_icon(company_name: str) -> bytes:
    """Build the 192x192 color.png bytes for a company."""
    rgb = _deterministic_color(company_name)
    if _PIL_AVAILABLE:
        try:
            return _build_color_png_with_pillow(company_name, 192, rgb)
        except Exception:
            # Pillow installed but font load or draw failed — fall through.
            pass
    return _write_png_solid(192, 192, rgb)


def build_outline_icon(company_name: str) -> bytes:
    """Build the 32x32 outline.png bytes for a company."""
    rgb = _deterministic_color(company_name)
    if _PIL_AVAILABLE:
        try:
            return _build_outline_png_with_pillow(rgb)
        except Exception:
            pass
    # Static fallback: a solid 32x32 in the same accent color — Cowork accepts
    # this as a placeholder.
    return _write_png_solid(32, 32, rgb)


def pillow_available() -> bool:
    """Whether the Pillow-rendered (rather than solid-fill) path is in use."""
    return _PIL_AVAILABLE


__all__ = ["build_color_icon", "build_outline_icon", "pillow_available"]
