"""Side panel with the details of the selected merge request (6.6)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.shared.i18n import t
from gitective.database.sync import MrDetailData
from gitective.reporting.statistics import format_days
from gitective.review.mr_detail import (
    WARN,
    discussion_place,
    failed_jobs,
    first_lines,
    log_tail,
    readiness,
    short_duration,
    top_files,
    unresolved_discussions,
)
from gitective.review.rules import KO, NA, OK, Evaluation, score_level
from gitective.shared.dates import business_days, format_datetime, now_local, to_local
from gitective.shared.people import PersonRef
from gitective.ui.components.side_panel import SidePanel
from gitective.ui.themes import Theme

if TYPE_CHECKING:
    from gitective.ui.app import App

ICONS = {OK: "✓", KO: "✕", WARN: "!", NA: "–"}


class MrDetailPanel(SidePanel):
    """Read-only summary of one MR; the forge data is loaded in the background (DE-12)."""

    def __init__(self, master: tk.Misc, app: App, on_close: Callable[[], None]) -> None:
        super().__init__(master)
        self.app = app
        self._on_close = on_close
        self._ev: Evaluation | None = None
        self._is_new = False
        self._detail: MrDetailData | None = None
        self._loading = False
        self._error = ""
        self._all_files = False

    @property
    def evaluation(self) -> Evaluation | None:
        return self._ev

    def show(self, ev: Evaluation, is_new: bool) -> None:
        """Show an MR at once from what is known, then complete it with the forge data."""
        same = self._ev is not None and (self._ev.mr.project_id, self._ev.mr.iid) == (ev.mr.project_id, ev.mr.iid)
        self._ev, self._is_new = ev, is_new
        if not same:
            self._all_files = False
            self._detail = self.app.data.stored_detail(ev.mr.project_id, ev.mr)
        self._error = ""
        self._loading = True
        self.render()
        data, mr = self.app.data, ev.mr

        def done(detail: MrDetailData) -> None:
            if self._ev is not None and self._ev.mr.iid == mr.iid and self._ev.mr.project_id == mr.project_id:
                self._detail, self._loading = detail, False
                self.render()
                self.app.report_offline()

        def failed(exc: BaseException) -> None:
            self._loading = False
            self._error = t("Détails indisponibles : instance injoignable ou droits insuffisants.")
            self.render()
            self.app.report_error(exc)

        self.app.runner.run("detail", lambda _p: data.mr_detail(mr.project_id, mr), done, failed)

    # ---------------------------------------------------------------- Drawing

    def render(self) -> None:
        theme = self.app.get_theme()
        inner = self._clear(theme)
        if self._ev is None:
            return
        self._header(inner, theme)
        detail = self._detail
        ready = readiness(self._ev.mr, detail) if detail else None
        if ready is not None:
            self._readiness(inner, theme, ready)
        elif self._ev.mr.state == "opened":
            self._placeholder(inner, theme, t("Prête à merger ?"))
        self._people(inner, theme)
        self._score(inner, theme)
        if detail is not None:
            self._pipeline(inner, theme, detail)
            self._discussions(inner, theme, detail)
            self._files(inner, theme, detail)
        elif self._loading or self._error:
            self._placeholder(inner, theme, t("Pipeline, discussions et fichiers"))
        footer = tk.Frame(inner, background=theme.bg)
        footer.pack(fill="x", padx=12, pady=(12, 16))
        ttk.Button(footer, text=t("↗  Ouvrir dans GitLab"), style="Accent.TButton",
                   command=lambda: self.app.open_url(self._ev.mr.web_url if self._ev else "")).pack(side="right")
        if detail is not None:
            when = format_datetime(to_local(detail.fetched_at))
            tk.Label(footer, text=t("Lu le {date}", date=when), background=theme.bg, foreground=theme.muted,
                     font=self._font(theme, -1)).pack(side="left")
        self._bind_wheel()

    def _header(self, parent: tk.Misc, theme: Theme) -> None:
        assert self._ev is not None
        ev, mr = self._ev, self._ev.mr
        head = tk.Frame(parent, background=theme.bg)
        head.pack(fill="x", padx=12, pady=(12, 0))
        self._close_button(head, theme, self._on_close)
        title = f"{t('BROUILLON')}  {mr.title}" if mr.draft else mr.title
        tk.Label(head, text=title, background=theme.bg, foreground=theme.text, font=self._font(theme, 3, "bold"),
                 wraplength=self._wrap - 30, justify="left", anchor="w").pack(fill="x")
        repo = (ev.project_path or mr.project_path).split("/")[-1]
        tk.Label(head, text=f"!{mr.iid} · {repo} · {mr.source_branch} → {mr.target_branch}", background=theme.bg,
                 foreground=theme.muted, font=(theme.mono[0], theme.mono[1] - 1), wraplength=self._wrap,
                 justify="left", anchor="w").pack(fill="x", pady=(2, 0))
        tags = tk.Frame(parent, background=theme.bg)
        tags.pack(fill="x", padx=12, pady=(8, 0))
        detail = self._detail
        ready = readiness(mr, detail) if detail else None
        if ready is not None:
            colors = theme.green if ready.ready else theme.red
            self._tag(tags, t("Prête à merger") if ready.ready else t("Pas prête à merger"), colors, theme)
        if mr.state == "opened":
            self._tag(tags, t("Ouverte depuis {days}", days=format_days(business_days(mr.created_at, now_local()))), theme.info,
                      theme)
        elif mr.state == "merged" and mr.merged_at:
            when = format_datetime(mr.merged_at)
            text = (t("Mergée le {date} par {merger}", date=when, merger=ev.merger.name) if ev.merger
                    else t("Mergée le {date}", date=when))
            self._tag(tags, text, theme.success, theme)
        elif mr.closed_at:
            self._tag(tags, t("Fermée le {date}", date=format_datetime(mr.closed_at)), theme.na, theme)
        if self._is_new:
            self._tag(tags, t("Nouvelle"), (theme.header, theme.second), theme)

    def _status_color(self, theme: Theme, status: str) -> str:
        return {OK: theme.ok[1], KO: theme.ko[1], WARN: theme.orange[1]}.get(status, theme.muted)

    def _readiness(self, parent: tk.Misc, theme: Theme, ready: object) -> None:
        body = self._card(parent, theme, t("Prête à merger ?"))
        for item in ready.items:  # type: ignore[attr-defined]
            color = self._status_color(theme, item.status)
            self._line(body, theme, item.text, item.note, icon=ICONS.get(item.status, "–"), icon_color=color)

    def _people(self, parent: tk.Misc, theme: Theme) -> None:
        assert self._ev is not None
        ev = self._ev
        body = self._card(parent, theme, t("Personnes"))
        me = self.app.me_key()
        for label, people in ((t("Auteur"), [ev.author]), (t("Assignés"), ev.assignees), (t("Relecteurs"), ev.reviewers)):
            mine = any(p.key == me for p in people)
            self._line(body, theme, label, self._names(people, me) or "—", color=theme.muted,
                       right_color=theme.accent if mine else theme.text)
        if ev.merger:
            warn = ev.merger_not_assignee
            self._line(body, theme, t("Mergeur"), ("≠ " if warn else "") + self._names([ev.merger], me),
                       color=theme.muted, right_color=theme.orange[1] if warn else theme.text)
            if warn:
                self._line(body, theme, warn, color=theme.orange[1])

    @staticmethod
    def _names(people: tuple[PersonRef, ...] | list[PersonRef], me: str | None) -> str:
        return ", ".join(t("Moi") if p.key == me else p.name for p in people)

    def _score(self, parent: tk.Misc, theme: Theme) -> None:
        assert self._ev is not None
        ev = self._ev
        settings = self.app.settings
        level = score_level(ev.score, settings.green_threshold, settings.orange_threshold)
        body = self._card(parent, theme, t("Score"), f"{ev.score:.0f} %", theme.level_colors(level))
        labels = {c.id: c.label for c in self.app.rules.criteria} if self.app.rules else {}
        not_applicable = []
        for cid, label in labels.items():
            result = ev.results.get(cid)
            if result is None:
                continue
            if result.status == NA:
                not_applicable.append(label)
                continue
            bg, fg = theme.status_colors(result.status)
            row = tk.Frame(body, background=theme.surface)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=t("OK") if result.status == OK else t("KO"), background=bg, foreground=fg, width=4,
                     font=self._font(theme, -1, "bold")).pack(side="right")
            # A long rule name wraps instead of hiding under its OK / KO label.
            tk.Label(row, text=label, background=theme.surface, foreground=theme.text, font=self._font(theme),
                     anchor="w", justify="left", wraplength=self._wrap - 90).pack(side="left")
            if result.status == KO and result.detail:
                tk.Label(body, text=result.detail, background=theme.surface, foreground=theme.muted,
                         font=self._font(theme, -1), wraplength=self._wrap - 30, justify="left",
                         anchor="w").pack(fill="x", padx=(10, 0))
        if not_applicable:
            row = tk.Frame(body, background=theme.surface)
            row.pack(fill="x", pady=1)
            bg, fg = theme.status_colors(NA)
            tk.Label(row, text=t("N/A"), background=bg, foreground=fg, width=4,
                     font=self._font(theme, -1, "bold")).pack(side="right")
            tk.Label(row, text=", ".join(not_applicable), background=theme.surface, foreground=theme.muted,
                     font=self._font(theme), anchor="w", justify="left",
                     wraplength=self._wrap - 80).pack(side="left")

    def _pipeline(self, parent: tk.Misc, theme: Theme, detail: MrDetailData) -> None:
        pipeline = detail.state.pipeline if detail.state else None
        if pipeline is None and not detail.statuses and not detail.jobs:
            return
        title = t("Pipeline")
        if pipeline is not None:
            title += f" · {pipeline.status}"
            if pipeline.updated_at:
                title += f" · {format_datetime(pipeline.updated_at)}"
        body = self._card(parent, theme, title)
        failed = failed_jobs(detail.jobs)
        for job in failed:
            self._line(body, theme, job.name, f"{job.status} · {short_duration(job.duration)}".rstrip(" ·"),
                       color=theme.ko[1])
        if pipeline is not None and not failed:
            self._line(body, theme, t("{count} job(s), aucun en échec", count=len(detail.jobs)), color=theme.muted)
        if pipeline is None:
            latest = {s.name: s for s in sorted(detail.statuses, key=lambda s: s.created_at)}
            for name, status in sorted(latest.items()):
                color = theme.ok[1] if status.status == "success" else theme.ko[1] if status.status in (
                    "failed", "canceled") else theme.orange[1]
                self._line(body, theme, name, status.status, right_color=color)
        tail = log_tail(detail.log)
        if tail:
            box = tk.Label(body, text=tail, background=theme.bg, foreground=theme.text, justify="left", anchor="w",
                           font=(theme.mono[0], theme.mono[1] - 1), padx=8, pady=6, wraplength=self._wrap - 30)
            box.pack(fill="x", pady=(6, 0))

    def _discussions(self, parent: tk.Misc, theme: Theme, detail: MrDetailData) -> None:
        open_threads = unresolved_discussions(detail.discussions)
        if not open_threads:
            return
        body = self._card(parent, theme, t("Discussions non résolues · {count}", count=len(open_threads)))
        me = self.app.me_key()
        for thread in open_threads:
            author = self.app.people.for_user(thread.author)
            name = t("Moi") if author.key == me else author.name
            tk.Label(body, text=f"{name} · {discussion_place(thread)}", background=theme.surface,
                     foreground=theme.muted, font=self._font(theme, -1), anchor="w").pack(fill="x", pady=(4, 0))
            tk.Label(body, text=first_lines(thread.body), background=theme.surface, foreground=theme.text,
                     font=self._font(theme), anchor="w", justify="left",
                     wraplength=self._wrap - 30).pack(fill="x")

    def _files(self, parent: tk.Misc, theme: Theme, detail: MrDetailData) -> None:
        if not detail.files:
            return
        body = self._card(parent, theme, t("Fichiers modifiés · {count}", count=len(detail.files)))
        shown, hidden = top_files(detail.files, len(detail.files) if self._all_files else 5)
        for changed in shown:
            row = tk.Frame(body, background=theme.surface)
            row.pack(fill="x", pady=1)
            mono = (theme.mono[0], theme.mono[1] - 1)
            tk.Label(row, text=f"−{changed.removed}", background=theme.surface, foreground=theme.ko[1],
                     font=mono).pack(side="right")
            tk.Label(row, text=f"+{changed.added}", background=theme.surface, foreground=theme.ok[1],
                     font=mono).pack(side="right", padx=(0, 6))
            tk.Label(row, text=changed.path.rsplit("/", 1)[-1], background=theme.surface, foreground=theme.text,
                     font=mono, anchor="w").pack(side="left")
        if hidden:
            more = tk.Label(body, text=t("+ {count} autres fichiers", count=hidden), background=theme.surface,
                            foreground=theme.link, cursor="hand2", font=self._font(theme, -1), anchor="w")
            more.pack(fill="x", pady=(2, 0))
            more.bind("<Button-1>", lambda e: self._show_all_files())

    def _show_all_files(self) -> None:
        self._all_files = True
        self.render()

