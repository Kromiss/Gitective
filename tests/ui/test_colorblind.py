"""Color-blind theme (TH-05): score levels distinct for deuteranopes and protanopes, gauges and patterns."""

from __future__ import annotations

import importlib.util
import unittest
from typing import Any

from gitective.ui.components.gauge import BARS, draw_dotted, draw_gauge, draw_hatched, label_text

# Machado, Oliveira and Fernandes (2009), full severity, on linear RGB.
DEUTERANOPIA = ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881))
PROTANOPIA = ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998))


def linear(hex_color: str) -> tuple[float, ...]:
    def channel(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return tuple(channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))


def simulate(rgb: tuple[float, ...], matrix: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    return tuple(max(0.0, min(1.0, sum(m * c for m, c in zip(row, rgb)))) for row in matrix)


def lab(rgb: tuple[float, ...]) -> tuple[float, float, float]:
    r, g, b = rgb
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(v: float) -> float:
        return v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum((p - q) ** 2 for p, q in zip(lab(a), lab(b))) ** 0.5


def contrast(fg: str, bg: str) -> float:
    def luminance(color: str) -> float:
        r, g, b = linear(color)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    high, low = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@unittest.skipUnless(importlib.util.find_spec("tkinter"), "Tk not installed")
class PaletteTests(unittest.TestCase):
    def setUp(self) -> None:
        from gitective.ui.themes import THEMES
        self.theme = THEMES["daltonien"]

    def test_levels_stay_distinct_for_deuteranopes_and_protanopes(self) -> None:
        levels = [self.theme.green[1], self.theme.orange[1], self.theme.red[1]]
        for matrix in (DEUTERANOPIA, PROTANOPIA):
            seen = [simulate(linear(c), matrix) for c in levels]
            for i in range(3):
                for j in range(i + 1, 3):
                    self.assertGreater(distance(seen[i], seen[j]), 20, (levels[i], levels[j]))

    def test_text_readable_on_every_level_and_status(self) -> None:
        t = self.theme
        for bg, fg in (t.green, t.orange, t.red, t.ok, t.ko, t.na):
            self.assertGreaterEqual(contrast(fg, bg), 4.5, (fg, bg))
        self.assertGreaterEqual(contrast(t.muted, t.surface), 4.5)

    def test_every_theme_draws_shapes(self) -> None:
        from gitective.ui.themes import THEMES
        self.assertEqual([k for k, theme in THEMES.items() if not theme.shapes], [])


@unittest.skipUnless(importlib.util.find_spec("tkinter"), "Tk not installed")
class AllThemesTests(unittest.TestCase):
    """Gauges and patterns in every theme; Windows 95 and Matrix made readable (TH-03, TH-04)."""

    def setUp(self) -> None:
        from gitective.ui.themes import THEMES
        self.themes = THEMES

    def test_text_readable_on_levels_and_statuses_in_every_theme(self) -> None:
        for key, t in self.themes.items():
            for bg, fg in (t.green, t.orange, t.red, t.ok, t.ko, t.na):
                self.assertGreaterEqual(contrast(fg, bg), 4.5, (key, fg, bg))
            self.assertGreaterEqual(contrast(t.text, t.surface), 4.5, key)
            self.assertGreaterEqual(contrast(t.muted, t.surface), 4.5, key)

    def test_matrix_levels_differ_by_brightness(self) -> None:
        m = self.themes["matrix"]
        def luminance(color: str) -> float:
            r, g, b = linear(color)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b
        # Good is bright, medium dimmed, low in inverse video (light background).
        self.assertGreater(luminance(m.green[1]), luminance(m.orange[1]))
        self.assertGreater(luminance(m.red[0]), luminance(m.green[0]) * 5)
        self.assertNotEqual(m.fill("red"), m.red[1])  # bars stay visible on the dark card
        self.assertEqual(m.heading_prefix, "> ")

    def test_fill_defaults_to_the_level_text_color(self) -> None:
        d = self.themes["default"]
        self.assertEqual((d.fill("green"), d.fill("orange"), d.fill("red")), (d.green[1], d.orange[1], d.red[1]))


class FakeCanvas:
    def __init__(self) -> None:
        self.items: list[tuple[str, tuple[float, ...], dict[str, Any]]] = []

    def create_rectangle(self, *coords: float, **options: Any) -> None:
        self.items.append(("rect", coords, options))

    def create_line(self, *coords: float, **options: Any) -> None:
        self.items.append(("line", coords, options))


class GaugeTests(unittest.TestCase):
    def test_filled_bars_follow_the_level_and_rise(self) -> None:
        for level, filled in BARS.items():
            canvas = FakeCanvas()
            draw_gauge(canvas, 0, 10, level, "#fff", "#333", 12)  # type: ignore[arg-type]
            fills = [o["fill"] for _, _, o in canvas.items]
            self.assertEqual(fills, ["#fff"] * filled + ["#333"] * (3 - filled))
            tops = [c[1] for _, c, _ in canvas.items]
            self.assertEqual(tops, sorted(tops, reverse=True))  # each bar taller than the previous

    def test_label_text(self) -> None:
        self.assertEqual(label_text("75 %", "orange", True), "▮▮▯ 75 %")
        self.assertEqual(label_text("75 %", "orange", False), "75 %")

    def test_stripes_are_vertical_on_whole_pixels_and_evenly_spaced(self) -> None:
        canvas = FakeCanvas()
        draw_hatched(canvas, 10.4, 20.6, 40.3, 80.2, "#f00", "#000")  # type: ignore[arg-type]
        stripes = [c for _, c, o in canvas.items if o["fill"] == "#f00"]
        self.assertTrue(stripes)
        for x0, y0, x1, y1 in stripes:
            self.assertTrue(all(v == int(v) for v in (x0, y0, x1, y1)))  # no fraction: nothing to round
            self.assertTrue(10 <= x0 < x1 <= 40 and (y0, y1) == (21, 80))
        self.assertEqual({b[0] - a[0] for a, b in zip(stripes, stripes[1:])}, {5})

    def test_dots_cover_the_box_on_whole_pixels(self) -> None:
        canvas = FakeCanvas()
        draw_dotted(canvas, 0, 0, 20.4, 10.4, "#ff0", "#000")  # type: ignore[arg-type]
        dots = [c for _, c, o in canvas.items if o["fill"] == "#000"]
        self.assertEqual(len(dots), 8)
        self.assertTrue(all(v == int(v) for c in dots for v in c))


if __name__ == "__main__":
    unittest.main()
