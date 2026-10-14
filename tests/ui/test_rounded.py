"""Tests of the rounded PNG generator used by the themes (standard library only)."""

import struct
import unittest
import zlib

from gitective.ui.rounded import blend, rounded_png


def pixels(png: bytes) -> tuple[int, list[list[tuple[int, int, int, int]]]]:
    """Decode the unfiltered RGBA PNG written by rounded_png."""
    size = struct.unpack(">I", png[16:20])[0]
    start = png.index(b"IDAT") + 4
    length = struct.unpack(">I", png[start - 8:start - 4])[0]
    raw = zlib.decompress(png[start:start + length])
    stride = size * 4 + 1
    rows = []
    for y in range(size):
        line = raw[y * stride + 1:(y + 1) * stride]
        rows.append([tuple(line[i:i + 4]) for i in range(0, len(line), 4)])
    return size, rows


class RoundedTests(unittest.TestCase):
    def test_png_signature_corners_and_center(self) -> None:
        png = rounded_png(20, 8, "#102030", "#FFFFFF")
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        size, rows = pixels(png)
        self.assertEqual(size, 20)
        self.assertEqual(rows[0][0][3], 0)  # transparent corner
        self.assertEqual(rows[10][10], (0x10, 0x20, 0x30, 255))  # opaque fill
        self.assertEqual(rows[10][0], (255, 255, 255, 255))  # border on the straight edge
        self.assertTrue(0 < rows[1][3][3] < 255)  # anti-aliased curve

    def test_underline_and_blend(self) -> None:
        _, rows = pixels(rounded_png(20, 6, "#000000", "#000000", underline="#00FF00"))
        self.assertEqual(rows[17][10][:3], (0, 255, 0))
        self.assertEqual(rows[10][10][:3], (0, 0, 0))
        self.assertEqual(blend("#000000", "#FFFFFF", 0.5), "#808080")


if __name__ == "__main__":
    unittest.main()
