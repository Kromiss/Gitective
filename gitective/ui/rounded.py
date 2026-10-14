"""Anti-aliased rounded rectangles as PNG bytes, for ttk image elements (standard library only)."""

from __future__ import annotations

import math
import struct
import zlib


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def blend(a: str, b: str, ratio: float) -> str:
    """Color between a (ratio 0) and b (ratio 1)."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * ratio):02X}" for x, y in zip(ra, rb))


def _coverage(px: float, py: float, width: float, height: float, radius: float) -> float:
    """Share of the pixel centred on (px, py) inside a rounded rectangle at the origin."""
    qx = abs(px - width / 2) - (width / 2 - radius)
    qy = abs(py - height / 2) - (height / 2 - radius)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - radius
    return max(0.0, min(1.0, 0.5 - outside))


def rounded_png(size: int, radius: int, fill: str, border: str, border_width: int = 1,
                underline: str | None = None) -> bytes:
    """Square PNG of a filled, outlined rounded rectangle with transparent corners.

    Used as a 9-slice ttk element: the corners stay intact and the middle
    stretches. `underline` draws a 2-pixel bar along the bottom edge
    (selected segment of a segmented control).
    """
    fill_rgb, border_rgb = _rgb(fill), _rgb(border)
    line_rgb = _rgb(underline) if underline else None
    inner = radius - border_width
    rows = []
    for y in range(size):
        row = bytearray(b"\x00")  # PNG filter type 0
        for x in range(size):
            cx, cy = x + 0.5, y + 0.5
            outer = _coverage(cx, cy, size, size, radius)
            body = _coverage(cx - border_width, cy - border_width, size - 2 * border_width,
                             size - 2 * border_width, max(0, inner))
            rgb = tuple(round(b + (f - b) * body) for f, b in zip(fill_rgb, border_rgb))
            if line_rgb and y >= size - border_width - 2 and body > 0:
                rgb = line_rgb
            row += bytes((*rgb, round(255 * outer)))
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows)))
            + chunk(b"IEND", b""))
