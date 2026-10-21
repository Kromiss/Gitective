"""Overview tab: dashboard of every tracked repository, drawn on a Canvas (VE-01..VE-14)."""

from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.shared.i18n import t
from gitective.forge.errors import ForgeError
from gitective.shared.dates import now_local, to_local
from gitective.review.mr_evaluation import evaluate_all, load_all_states, load_merge_requests, load_pairs
from gitective.reporting.overview_figures import (
    GROUP_H,
    SCORE_DAYS,
    WEEKS,
    OverviewData,
    build_overview,
    feed_row_height,
    load_start,
    short_title,
)
from gitective.review.rules import Evaluation, score_level

if TYPE_CHECKING:
    from gitective.ui.app import App

PAD, GAP, INNER = 20, 16, 22
STATUS_H, DAILY_H = 26, 150
TICK_MS = 30_000

DAY_NAMES = (t("Lun"), t("Mar"), t("Mer"), t("Jeu"), t("Ven"), t("Sam"), t("Dim"))
WEEKDAYS = (t("Lundi"), t("Mardi"), t("Mercredi"), t("Jeudi"), t("Vendredi"), t("Samedi"), t("Dimanche"))
MONTHS = (t("janvier"), t("février"), t("mars"), t("avril"), t("mai"), t("juin"), t("juillet"), t("août"),
          t("septembre"), t("octobre"), t("novembre"), t("décembre"))

Loaded = tuple[OverviewData, list[Evaluation], list[ForgeError]]


def blend(a: str, b: str, ratio: float) -> str:
    """Mix two #RRGGBB colors; ratio 0 gives a, 1 gives b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * ratio):02X}" for x, y in zip(ca, cb))


def day_label(day: date, today: date) -> str:
    """Group title of the latest merges: 'Aujourd'hui', 'Hier' or 'Vendredi 9 octobre'."""
    if day == today:
        return t("Aujourd'hui")
    if day == today - timedelta(days=1):
        return t("Hier")
    return t("{weekday} {day} {month}", weekday=WEEKDAYS[day.weekday()], day=day.day, month=MONTHS[day.month - 1])


def nice_step(maximum: float, ticks: int = 4) -> int:
    """Round axis step so that about `ticks` gridlines cover maximum."""
    raw = max(maximum, 1) / ticks
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 5, 10):
        if raw <= factor * magnitude:
            return max(1, int(factor * magnitude))
    return max(1, int(10 * magnitude))


class OverviewTab(ttk.Frame):
    """Supervision screen computed from the loaded MRs; only the latest merges are clickable (VE-14)."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.dirty = True
        self._data: OverviewData | None = None
        self._message = t("Chargement…")
        self._synced_at: datetime | None = None
        self._fonts: dict[tuple[str, int, str], tkfont.Font] = {}
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.canvas.self_themed = True  # type: ignore[attr-defined]
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        # Rows of the latest merges: (top, bottom, left, right, hover rectangle, MR) (VE-14).
        self._feed_rows: list[tuple[float, float, float, float, int, Evaluation]] = []
        self._hovered: int | None = None
        self.canvas.bind("<Motion>", lambda e: self._hover(e.x, e.y))
        self.canvas.bind("<Leave>", lambda e: self._hover(-1, -1))
        self.canvas.bind("<Button-1>", lambda e: self._click(e.x, e.y))
        self.after(TICK_MS, self._tick)

    # ----------------------------------------------------------- Refresh
    # The application synchronises every N minutes and reloads this tab afterwards (VE-03, CH-13).

    def _tick(self) -> None:
        """Keep the 'next refresh in N min' line up to date."""
        if self.app.is_visible(self):
            self.redraw()
        self.after(TICK_MS, self._tick)

    def settings_changed(self) -> None:
        """Rules, thresholds, repositories or synchronisation period may have changed."""
        self.dirty = True
        if self.app.is_visible(self):
            self.reload()

    # ----------------------------------------------------------- Loading

    def reload(self) -> None:
        self.dirty = False
        if not self.app.ensure_connection():
            self._data, self._message = None, t("Configurez la connexion et les dépôts dans l'onglet Config.")
            self.redraw()
            return
        data_source, rules, people = self.app.data, self.app.rules, self.app.people
        assert rules is not None
        settings = self.app.settings
        projects = list(settings.projects)
        workers = settings.parallel_requests

        def task(progress: Callable[[int, int], None]) -> Loaded:
            now = now_local()
            period = (load_start(now), now)
            pairs, errors = load_pairs(projects, lambda p: load_merge_requests(data_source, p, "merged", period))
            evaluations = evaluate_all(data_source, pairs, rules, people, progress, workers)
            created, created_errors = load_pairs(projects, lambda p: load_all_states(data_source, p, period))
            data = build_overview(evaluations, [mr for _, mr in created], [p.path for p in projects],
                                  rules.criteria, settings.green_threshold, settings.orange_threshold, now)
            return data, evaluations, [*errors, *created_errors]

        self.app.runner.run("overview", task, self._loaded, self.app.report_error)

    def _loaded(self, result: Loaded) -> None:
        data, evaluations, errors = result
        if errors:
            self.app.report_error(errors[0], extra=len(errors) - 1)
        else:
            self.app.report_offline()
        self.app.remember_users(u for e in evaluations for u in (e.mr.author, e.mr.merged_by) if u)
        self.app.register_people((p.key, p.name) for e in evaluations for p in (e.author, e.merger) if p)
        self._data = data
        # Offline, the data dates from the last synchronisation, not from now (CH-08).
        offline = self.app.data.offline_since
        self._synced_at = to_local(offline) if offline else now_local()
        self.redraw()

    def restyle(self) -> None:
        self._fonts.clear()
        self.redraw()

    # ----------------------------------------------------------- Drawing helpers

    def _font(self, size: int, weight: str = "normal") -> tkfont.Font:
        """Theme font at a pixel size (negative Tk size = pixels)."""
        family = self.app.get_theme().font[0]
        key = (family, size, weight)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(root=self.canvas, family=family, size=-size, weight=weight)
        return self._fonts[key]

    def _text(self, x: float, y: float, text: str, size: int = 13, color: str | None = None,
              weight: str = "normal", anchor: str = "nw", width: float | None = None) -> None:
        font = self._font(size, weight)
        if width is not None:
            text = self._fit(font, text, width)
        self.canvas.create_text(x, y, text=text, anchor=anchor, font=font,
                                fill=color or self.app.get_theme().text)

    @staticmethod
    def _fit(font: tkfont.Font, text: str, width: float) -> str:
        """Shorten text with an ellipsis so it fits in width pixels."""
        if font.measure(text) <= width:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if font.measure(text[:middle] + "…") <= width:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip() + "…"

    def _box(self, x1: float, y1: float, x2: float, y2: float, radius: int, fill: str, outline: str = "") -> None:
        """Rectangle with rounded corners (radius 0 = sharp)."""
        radius = int(min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        if radius <= 0:
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline or fill)
            return
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius, x2, y2,
                  x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        self.canvas.create_polygon(points, smooth=True, splinesteps=16, fill=fill, outline=outline or fill)

    def _card(self, x: float, y: float, w: float, h: float, fill: str | None = None) -> None:
        theme = self.app.get_theme()
        if theme.relief == "raised":  # Windows 95 bevel
            self.canvas.create_rectangle(x, y, x + w, y + h, fill=fill or theme.bg, outline=theme.bg)
            self.canvas.create_line(x, y + h, x, y, x + w, y, fill="#FFFFFF", width=2)
            self.canvas.create_line(x + w, y, x + w, y + h, x, y + h, fill="#404040", width=2)
            return
        self._box(x, y, x + w, y + h, theme.radius, fill or theme.surface, theme.border)

    def _card_fill(self) -> str:
        theme = self.app.get_theme()
        return theme.bg if theme.relief == "raised" else theme.surface

    def _bar(self, x1: float, y1: float, x2: float, y2: float, ratio: float, color: str) -> None:
        """Horizontal gauge: track plus a filled share."""
        theme = self.app.get_theme()
        radius = 3 if theme.radius else 0
        track = theme.surface if theme.relief == "raised" else theme.header
        self._box(x1, y1, x2, y2, radius, track, theme.border if theme.relief == "raised" else "")
        if ratio > 0:
            self._box(x1, y1, x1 + max(radius * 2, (x2 - x1) * min(ratio, 1)), y2, radius, color)

    def _pill(self, x2: float, y: float, text: str, colors: tuple[str, str], size: int = 14,
              min_width: int = 0) -> float:
        """Badge right-aligned on x2, vertically centred on y; returns its left edge."""
        theme = self.app.get_theme()
        font = self._font(size, "bold")
        width = max(min_width, font.measure(text) + 18)
        height = size + 12
        self._box(x2 - width, y - height / 2, x2, y + height / 2, 6 if theme.radius else 0, colors[0])
        self.canvas.create_text(x2 - width / 2, y, text=text, font=font, fill=colors[1])
        return x2 - width

    def _header(self, x: float, y: float, w: float, title: str, subtitle: str = "") -> None:
        theme = self.app.get_theme()
        self._text(x + INNER, y + 18, title, 14, weight="bold")
        if subtitle:
            self._text(x + w - INNER, y + 20, subtitle, 12, theme.muted, anchor="ne")

    def _level(self, score: float) -> tuple[str, str]:
        settings = self.app.settings
        return self.app.get_theme().level_colors(
            score_level(round(score, 6), settings.green_threshold, settings.orange_threshold))

    # ----------------------------------------------------------- Drawing

    def redraw(self) -> None:
        theme = self.app.get_theme()
        canvas = self.canvas
        canvas.delete("all")
        self._feed_rows, self._hovered = [], None
        canvas.configure(background=theme.bg)
        width, height = max(canvas.winfo_width(), 960), max(canvas.winfo_height(), 600)
        self._draw_status(width)
        data = self._data
        if data is None:
            self._text(width / 2, height / 2, self._message, 16, theme.muted, anchor="center")
            return
        top = PAD + STATUS_H + 10
        left_w = max(440, round((width - 2 * PAD - GAP) * 0.32))
        feed_h = height - top - PAD - GAP - DAILY_H
        self._draw_feed(PAD, top, left_w, feed_h, data)
        self._draw_daily(PAD, top + feed_h + GAP, left_w, DAILY_H, data)

        x = PAD + left_w + GAP
        right_w = width - x - PAD
        available = height - top - PAD - 2 * GAP
        row1, row3 = round(available * 0.30), round(available * 0.28)
        row2 = available - row1 - row3
        score_w = max(300, round(right_w * 0.28))
        self._draw_score(x, top, score_w, row1, data)
        self._draw_quality(x + score_w + GAP, top, right_w - score_w - GAP, row1, data)
        self._draw_ranking(x, top + row1 + GAP, right_w, row2, data)
        ko_w = round((right_w - GAP) * 0.42)
        y3 = top + row1 + row2 + 2 * GAP
        self._draw_kos(x, y3, ko_w, row3, data)
        self._draw_flow(x + ko_w + GAP, y3, right_w - ko_w - GAP, row3, data)

    def _draw_status(self, width: int) -> None:
        """Top line: tracked repositories, last sync and next refresh (VE-03)."""
        theme = self.app.get_theme()
        y = PAD + STATUS_H / 2
        count = len(self.app.settings.projects)
        tracked = t("{count} dépôts suivis", count=count) if count > 1 else t("{count} dépôt suivi", count=count)
        self._text(PAD, y, tracked + t(" · MR mergées, brouillons exclus"), 13, theme.muted, anchor="w")
        chip = t("F11 · Plein écran")
        font = self._font(12)
        chip_w = font.measure(chip) + 18
        self._box(width - PAD - chip_w, y - 12, width - PAD, y + 12, 6 if theme.radius else 0,
                  theme.bg, theme.border)
        self._text(width - PAD - chip_w / 2, y, chip, 12, theme.muted, anchor="center")
        parts = []
        if self._synced_at:
            parts.append(t("Synchronisé à {time}", time=f"{self._synced_at:%H:%M}"))
        if self.app.next_sync:
            minutes = max(0, math.ceil((self.app.next_sync - now_local()).total_seconds() / 60))
            parts.append(t("prochaine synchronisation dans {minutes} min", minutes=minutes))
        status = " · ".join(parts)
        right = width - PAD - chip_w - 16
        self._text(right, y, status, 13, theme.muted, anchor="e")
        if self._synced_at:
            dot_x = right - self._font(13).measure(status) - 12
            self.canvas.create_oval(dot_x - 4, y - 4, dot_x + 4, y + 4, fill=theme.green[1], outline="")

    def _draw_feed(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """Latest merges, grouped by day; today's group is highlighted (VE-05)."""
        theme = self.app.get_theme()
        fill = theme.feature or self._card_fill()
        self._card(x, y, w, h, fill)
        self._text(x + INNER, y + 18, t("Derniers merges"), 22, weight="bold")
        self._text(x + INNER, y + 50, t("Tous les dépôts suivis · du plus récent au plus ancien"), 12, theme.muted)
        self._text(x + w - INNER, y + 12, str(data.today_count), 38, theme.accent, "bold", anchor="ne")
        self._text(x + w - INNER, y + 58, t("aujourd'hui"), 12, theme.muted, anchor="ne")
        line = blend(fill, theme.border, 0.8) if theme.relief != "raised" else "#808080"
        self.canvas.create_line(x + 1, y + 84, x + w - 1, y + 84, fill=line)
        if not data.feed:
            self._text(x + w / 2, y + h / 2, t("Aucun merge sur les {weeks} dernières semaines", weeks=WEEKS), 14,
                       theme.muted, anchor="center")
            return
        today = now_local().date()
        cursor, bottom = y + 86, y + h - 10
        current: date | None = None
        row_h = feed_row_height(data.today_count, bottom - cursor)
        compact = row_h < 58
        title_x, pill_w = x + INNER + (54 if compact else 62), 58 if compact else 70
        for ev in data.feed:
            merged = to_local(ev.mr.merged_at)  # type: ignore[arg-type]
            day = merged.date()
            is_today = day == today
            band = theme.info[0] if is_today else fill
            needed = row_h + (GROUP_H if day != current else 0)
            if cursor + needed > bottom:
                break
            if day != current:
                current = day
                if is_today:
                    self.canvas.create_rectangle(x + 1, cursor, x + w - 1, cursor + GROUP_H, fill=band, outline="")
                self._text(x + INNER, cursor + GROUP_H - 6, day_label(day, today).upper(), 11,
                           theme.accent if is_today else theme.muted, "bold", anchor="sw")
                cursor += GROUP_H
            if is_today:
                self.canvas.create_rectangle(x + 1, cursor, x + w - 1, cursor + row_h, fill=band, outline="")
            hover = self.canvas.create_rectangle(x + 1, cursor, x + w - 1, cursor + row_h, outline="",
                                                 fill=theme.selected_row, state="hidden")
            self._feed_rows.append((cursor, cursor + row_h, x, x + w, hover, ev))
            middle = cursor + row_h / 2
            text_w = w - (title_x - x) - INNER - pill_w - 14
            who = ev.author.name + (f" → {ev.merger.name}" if ev.merger else "")
            meta = f"{ev.project_path.split('/')[-1]} · {who}"
            if compact:
                # One line: time, title, then repository and people as far as room allows.
                # One line: time, title, then repository and people, which always keep their room.
                self._text(x + INNER, middle, f"{merged:%H:%M}", 12, theme.muted, "bold", anchor="w")
                title = short_title(ev.mr.title)
                meta_w = min(self._font(11).measure(meta), text_w * 0.55)
                title_w = min(self._font(13, "bold").measure(title), text_w - meta_w - 12)
                self._text(title_x, middle, title, 13, weight="bold", anchor="w", width=title_w)
                self._text(title_x + title_w + 12, middle, meta, 11, theme.muted, anchor="w", width=meta_w)
                self._pill(x + w - INNER, middle, f"{ev.score:.0f} %", self._level(ev.score), 12, pill_w)
            else:
                self._text(x + INNER, middle, f"{merged:%H:%M}", 14, theme.muted, "bold", anchor="w")
                self._text(title_x, middle - 10, short_title(ev.mr.title), 15, weight="bold", anchor="w",
                           width=text_w)
                self._text(title_x, middle + 11, meta, 12, theme.muted, anchor="w", width=text_w)
                self._pill(x + w - INNER, middle, f"{ev.score:.0f} %", self._level(ev.score), 15, pill_w)
            cursor += row_h
            self.canvas.create_line(x + INNER, cursor, x + w - INNER, cursor,
                                    fill=blend(band, theme.border, 0.6) if theme.relief != "raised" else "#A0A0A0")

    def _row_at(self, x: float, y: float) -> int | None:
        return next((i for i, (top, bottom, left, right, _, _) in enumerate(self._feed_rows)
                     if top <= y < bottom and left <= x < right), None)

    def _hover(self, x: float, y: float) -> None:
        """Hand cursor and hover background on a merge row (VE-14)."""
        row = self._row_at(x, y)
        if row == self._hovered:
            return
        if self._hovered is not None:
            self.canvas.itemconfigure(self._feed_rows[self._hovered][4], state="hidden")
        if row is not None:
            self.canvas.itemconfigure(self._feed_rows[row][4], state="normal")
        self._hovered = row
        self.canvas.configure(cursor="hand2" if row is not None else "")

    def _click(self, x: float, y: float) -> None:
        """A merge row opens that MR in the Merge Requests tab (VE-14)."""
        row = self._row_at(x, y)
        if row is not None:
            self.app.show_merge_request(self._feed_rows[row][5])

    def _draw_daily(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """Merges per day, this week and last week (VE-06)."""
        theme = self.app.get_theme()
        self._card(x, y, w, h)
        self._header(x, y, w, t("Merges par jour"), t("Total"))
        label_w, total_w, gap = 108, 44, 6
        cell_w = (w - 2 * INNER - label_w - total_w - 7 * gap) / 7
        left = x + INNER + label_w
        for index, name in enumerate(DAY_NAMES):
            self._text(left + index * (cell_w + gap) + cell_w / 2, y + 50, name, 11, theme.muted, anchor="center")
        rows = ((t("Cette semaine"), data.this_week, data.this_week_scores),
                (t("Sem. dernière"), data.last_week, data.last_week_scores))
        for number, (label, values, scores) in enumerate(rows):
            top = y + 62 + number * 38
            self._text(x + INNER, top + 15, label, 13, theme.muted, anchor="w")
            for index, value in enumerate(values):
                cx = left + index * (cell_w + gap)
                if value is None:
                    self.canvas.create_rectangle(cx, top, cx + cell_w, top + 30, outline=theme.border, dash=(3, 3))
                    continue
                # Background = level of the day's average score, like the score pills; no merge = neutral.
                score = scores[index]
                fill, color = self._level(score) if score is not None else (theme.header, theme.muted)
                self._box(cx, top, cx + cell_w, top + 30, 6 if theme.radius else 0, fill,
                          theme.border if theme.relief == "raised" or theme.radius == 0 else "")
                self._text(cx + cell_w / 2, top + 15, str(value), 14, color, "bold", anchor="center")
            total = sum(v for v in values if v)
            self._text(x + w - INNER, top + 15, str(total), 18, weight="bold", anchor="e")

    def _draw_score(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """Average score of the last 30 days and its trend (VE-07)."""
        theme = self.app.get_theme()
        self._card(x, y, w, h)
        subtitle = t("{days} derniers jours · {count} MR", days=SCORE_DAYS, count=data.merged_count)
        self._header(x, y, w, t("Score moyen"), subtitle)
        if data.score is None:
            self._text(x + w / 2, y + h / 2, t("Aucune MR mergée"), 14, theme.muted, anchor="center")
            return
        color = self._level(data.score)[1]
        # The number takes whatever height the header, trend and gauge leave (fits small windows).
        size = int(max(32, min(84, (h - 136) / 0.8)))
        big = self._font(size, "bold")
        number = f"{data.score:.0f}"
        base = y + 50 + big.metrics("ascent")
        self.canvas.create_text(x + INNER, base, text=number, font=big, fill=color, anchor="sw")
        self._text(x + INNER + big.measure(number) + 4, base - size * 0.12, "%", max(16, size * 2 // 5), color,
                   "bold", anchor="sw")
        bar_y = y + h - 38
        if data.previous_score is not None:
            line_y = (base + bar_y) / 2
            delta = round(data.score - data.previous_score)
            colors = theme.green if delta > 0 else theme.red if delta < 0 else theme.na
            sign = "▲ +" if delta > 0 else "▼ −" if delta < 0 else "= "
            text = sign + (t("{count} pts", count=abs(delta)) if abs(delta) > 1 else t("{count} pt", count=abs(delta)))
            right = x + INNER + self._font(14, "bold").measure(text) + 18
            self._pill(right, line_y, text, colors, 14)
            self._text(right + 10, line_y, t("vs {days} j précédents ({score} %)", days=SCORE_DAYS, score=f"{data.previous_score:.0f}"), 12,
                       theme.muted, anchor="w", width=x + w - INNER - right - 10)
        self._bar(x + INNER, bar_y, x + w - INNER, bar_y + 10, data.score / 100, color)
        orange = self.app.settings.orange_threshold
        mark = x + INNER + (w - 2 * INNER) * orange / 100
        self.canvas.create_line(mark, bar_y - 4, mark, bar_y + 14, fill=self._card_fill(), width=3)
        for value, anchor, position in ((0, "nw", x + INNER), (orange, "n", mark), (100, "ne", x + w - INNER)):
            self._text(position, bar_y + 16, f"{value:g}", 11, theme.muted, anchor=anchor)

    def _draw_quality(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """Merged MRs per week split by score level (VE-08)."""
        theme = self.app.get_theme()
        settings = self.app.settings
        self._card(x, y, w, h)
        self._text(x + INNER, y + 18, t("Qualité des MR mergées par semaine"), 14, weight="bold")
        legend = ((theme.green[1], f"≥ {settings.green_threshold:g} %"),
                  (theme.orange[1], f"≥ {settings.orange_threshold:g} %"),
                  (theme.red[1], f"< {settings.orange_threshold:g} %"))
        lx = x + w - INNER
        for color, label in reversed(legend):
            lx -= self._font(12).measure(label)
            self._text(lx, y + 26, label, 12, theme.muted, anchor="w")
            lx -= 16
            self.canvas.create_rectangle(lx, y + 21, lx + 10, y + 31, fill=color, outline="")
            lx -= 14
        top, bottom = y + 70, y + h - 32
        gap = 10
        count = max(len(data.quality), 1)
        bar_w = (w - 2 * INNER - gap * (count - 1)) / count
        peak = max((q.total for q in data.quality), default=0) or 1
        self.canvas.create_line(x + INNER, bottom, x + w - INNER, bottom, fill=theme.border)
        for index, week in enumerate(data.quality):
            bx = x + INNER + index * (bar_w + gap)
            cursor = bottom
            for value, color in ((week.green, theme.green[1]), (week.orange, theme.orange[1]),
                                 (week.red, theme.red[1])):
                if value:
                    height = (bottom - top) * value / peak
                    self.canvas.create_rectangle(bx, cursor - height, bx + bar_w, cursor - 1, fill=color, outline="")
                    cursor -= height
            if week.total:
                self._text(bx + bar_w / 2, cursor - 4, str(week.total), 11, theme.muted, anchor="s")
            self._text(bx + bar_w / 2, bottom + 8, week.label, 11, theme.muted, anchor="n")

    def _draw_ranking(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """Repositories ranked by average score, on two columns (VE-09)."""
        theme = self.app.get_theme()
        self._card(x, y, w, h)
        count = len(data.repos)
        self._header(x, y, w, t("Classement des dépôts"),
                     (t("{count} dépôts", count=count) if count > 1 else t("{count} dépôt", count=count))
                     + t(" · score moyen sur {days} jours", days=SCORE_DAYS))
        if not count:
            return
        columns = 2 if count > 6 else 1
        rows = math.ceil(count / columns)
        top = y + 58
        row_h = min(32, (y + h - 14 - top) / rows)
        col_gap = 48
        col_w = (w - 2 * INNER - col_gap * (columns - 1)) / columns
        name_w = min(190, col_w * 0.36)
        size = 14 if row_h >= 22 else 12
        for index, (path, score) in enumerate(data.repos):
            column, row = divmod(index, rows)
            cx = x + INNER + column * (col_w + col_gap)
            middle = top + row * row_h + row_h / 2
            self._text(cx + 20, middle, str(index + 1), 12, theme.muted, anchor="e")
            self._text(cx + 30, middle, path.split("/")[-1], size, anchor="w", width=name_w)
            bar_x = cx + 30 + name_w + 12
            if score is None:
                self._bar(bar_x, middle - 5, cx + col_w - 60, middle + 5, 0, theme.muted)
                self._text(cx + col_w, middle, "—", size, theme.muted, anchor="e")
                continue
            color = self._level(score)[1]
            self._bar(bar_x, middle - 5, cx + col_w - 60, middle + 5, score / 100, color)
            self._text(cx + col_w, middle, f"{score:.0f} %", size, color, "bold", anchor="e")

    def _draw_kos(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """KO count per active criterion over 30 days (VE-10)."""
        theme = self.app.get_theme()
        self._card(x, y, w, h)
        total = sum(c for _, c in data.kos)
        self._header(x, y, w, t("Règles enfreintes"), t("{count} KO · {days} jours", count=total, days=SCORE_DAYS))
        if not data.kos:
            self._text(x + w / 2, y + h / 2, t("Aucune règle active"), 13, theme.muted, anchor="center")
            return
        top = y + 58
        row_h = min(34, (y + h - 12 - top) / len(data.kos))
        peak = max(c for _, c in data.kos) or 1
        name_w = min(200, (w - 2 * INNER) * 0.45)
        for index, (label, count) in enumerate(data.kos):
            middle = top + index * row_h + row_h / 2
            self._text(x + INNER, middle, label, 14, anchor="w", width=name_w)
            self._bar(x + INNER + name_w + 12, middle - 5, x + w - INNER - 40, middle + 5, count / peak, theme.red[1])
            self._text(x + w - INNER, middle, str(count), 15, weight="bold", anchor="e")

    def _draw_flow(self, x: float, y: float, w: float, h: float, data: OverviewData) -> None:
        """Created and merged MRs per week, with an MR-count axis (VE-11)."""
        theme = self.app.get_theme()
        self._card(x, y, w, h)
        self._text(x + INNER, y + 18, t("MR créées / mergées par semaine"), 14, weight="bold")
        lx = x + w - INNER
        created_color = blend(theme.muted, self._card_fill(), 0.35) if theme.relief != "raised" else theme.muted
        for color, label in ((theme.accent, t("Mergées")), (created_color, t("Créées"))):
            lx -= self._font(12).measure(label)
            self._text(lx, y + 26, label, 12, theme.muted, anchor="w")
            lx -= 22
            self.canvas.create_line(lx, y + 26, lx + 16, y + 26, fill=color, width=3)
            lx -= 16
        left, right = x + INNER + 30, x + w - INNER
        top, bottom = y + 62, y + h - 56
        peak = max([*data.created, *data.merged, 1])
        step = nice_step(peak, ticks=int(max(2, min(4, (bottom - top) // 28))))
        ceiling = step * math.ceil(peak / step)

        def y_of(value: float) -> float:
            return bottom - (bottom - top) * value / ceiling

        for value in range(0, ceiling + 1, step):
            gy = y_of(value)
            self.canvas.create_line(left, gy, right, gy, fill=theme.border if value == 0 else theme.header)
            self._text(left - 8, gy, str(value), 11, theme.muted, anchor="e")
        count = len(data.week_labels)
        if count:
            span = (right - left) / max(count - 1, 1)

            def points(values: Sequence[int]) -> list[float]:
                return [c for i, v in enumerate(values) for c in (left + i * span, y_of(v))]

            if count > 1:
                self.canvas.create_line(*points(data.created), fill=created_color, width=2, joinstyle="round")
                self.canvas.create_line(*points(data.merged), fill=theme.accent, width=3, joinstyle="round")
            for index in range(count):
                px, py = left + index * span, y_of(data.merged[index])
                self.canvas.create_oval(px - 3, py - 3, px + 3, py + 3, fill=theme.accent, outline="")
                if index % 3 == 0 or index == count - 1:
                    self._text(px, bottom + 8, data.week_labels[index], 11, theme.muted, anchor="n")
            self._text(x + INNER, y + h - 18, t("Semaine dernière : {created} créées, {merged} mergées",
                                                 created=data.created[-1], merged=data.merged[-1]),
                       12, theme.muted, anchor="sw")
