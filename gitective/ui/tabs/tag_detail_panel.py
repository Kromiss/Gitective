"""Side panel with the details of the selected tag (TG-07)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.shared.i18n import t
from gitective.database.store import LinkedMr
from gitective.database.sync import TagPipelineData
from gitective.repository.tags import TagRow
from gitective.review.mr_detail import failed_jobs, log_tail, short_duration
from gitective.shared.dates import format_datetime, now_local, to_local
from gitective.ui.components.side_panel import SidePanel
from gitective.ui.themes import Theme

if TYPE_CHECKING:
    from gitective.ui.app import App

PIPELINE_WORDS = {"success": t("Réussi"), "failed": t("Échec"), "canceled": t("Annulé"), "skipped": t("Ignoré"),
                  "running": t("En cours"), "pending": t("En attente"), "created": t("Créé"), "manual": t("Manuel")}


def ago(value: datetime | None, now: datetime | None = None) -> str:
    """"il y a 2 h", "il y a 3 j" (DE-08)."""
    if value is None:
        return ""
    seconds = max(0.0, ((now or now_local()) - value).total_seconds())
    if seconds < 3600:
        return t("il y a {count} min", count=int(seconds // 60))
    if seconds < 86400:
        return t("il y a {count} h", count=int(seconds // 3600))
    return t("il y a {count} j", count=int(seconds // 86400))


class TagDetailPanel(SidePanel):
    """Read-only summary of one tag; its pipeline is read in the background (TG-09)."""

    def __init__(self, master: tk.Misc, app: App, on_close: Callable[[], None]) -> None:
        super().__init__(master)
        self.app = app
        self._on_close = on_close
        self._row: TagRow | None = None
        self._mr: LinkedMr | None = None
        self._pipeline: TagPipelineData | None = None

    def show(self, row: TagRow) -> None:
        """Show a tag at once from the base, then complete its pipeline from the forge."""
        same = self._row is not None and (self._row.project.id, self._row.tag.name) == (row.project.id, row.tag.name)
        self._row = row
        project_id, tag = row.project.id, row.tag
        if not same:
            self._pipeline = self.app.data.stored_tag_pipeline(project_id, tag)
        self._mr = self.app.store.mr_of_commit(project_id, tag.commit_sha)
        self._error, self._loading = "", True
        self.render()
        data = self.app.data

        def done(pipeline: TagPipelineData) -> None:
            if self._row is not None and (self._row.project.id, self._row.tag.name) == (project_id, tag.name):
                self._pipeline, self._loading = pipeline, False
                self.render()
                self.app.report_offline()

        def failed(exc: BaseException) -> None:
            self._loading = False
            self._error = t("Pipeline indisponible : instance injoignable ou droits insuffisants.")
            self.render()
            self.app.report_error(exc)

        self.app.runner.run("tag_detail", lambda _p: data.tag_pipeline(project_id, tag), done, failed)

    # ---------------------------------------------------------------- Drawing

    def render(self) -> None:
        theme = self.app.get_theme()
        inner = self._clear(theme)
        if self._row is None:
            return
        self._header(inner, theme)
        tag = self._row.tag
        if tag.message:
            body = self._card(inner, theme, t("Message"))
            self._text(body, theme, tag.message)
        self._commit(inner, theme)
        if tag.has_release:
            body = self._card(inner, theme, t("Release GitLab"))
            if tag.release_name:
                self._line(body, theme, tag.release_name, color=theme.text)
            self._text(body, theme, tag.release_notes or t("Pas de notes de release."))
        self._pipeline_card(inner, theme)
        footer = tk.Frame(inner, background=theme.bg)
        footer.pack(fill="x", padx=12, pady=(12, 16))
        ttk.Button(footer, text=t("↗  Ouvrir dans GitLab"), style="Accent.TButton",
                   command=lambda: self.app.open_url(self._row.web_url if self._row else "")).pack(side="right")
        if self._pipeline is not None:
            tk.Label(footer, text=t("Lu le {date}", date=format_datetime(to_local(self._pipeline.fetched_at))), background=theme.bg,
                     foreground=theme.muted, font=self._font(theme, -1)).pack(side="left")
        self._bind_wheel()

    def _header(self, parent: tk.Misc, theme: Theme) -> None:
        assert self._row is not None
        row, tag = self._row, self._row.tag
        head = tk.Frame(parent, background=theme.bg)
        head.pack(fill="x", padx=12, pady=(12, 0))
        self._close_button(head, theme, self._on_close)
        tk.Label(head, text=tag.name, background=theme.bg, foreground=theme.text, anchor="w",
                 font=(theme.mono[0], theme.mono[1] + 4, "bold")).pack(fill="x")
        kind = t("tag annoté") if tag.annotated else t("tag léger")
        tk.Label(head, text=f"{row.project.path.split('/')[-1]} · {kind} · {format_datetime(tag.committed_date)}",
                 background=theme.bg, foreground=theme.muted, font=(theme.mono[0], theme.mono[1] - 1),
                 anchor="w", wraplength=self._wrap, justify="left").pack(fill="x", pady=(2, 0))
        if row.deleted_at is not None:
            tags = tk.Frame(parent, background=theme.bg)
            tags.pack(fill="x", padx=12, pady=(8, 0))
            self._tag(tags, t("SUPPRIMÉ · constaté le {date}", date=format_datetime(row.deleted_at)), theme.na, theme)

    def _text(self, parent: tk.Misc, theme: Theme, text: str) -> None:
        tk.Label(parent, text=text, background=theme.surface, foreground=theme.text, font=self._font(theme),
                 justify="left", anchor="w", wraplength=self._wrap - 30).pack(fill="x")

    def _commit(self, parent: tk.Misc, theme: Theme) -> None:
        assert self._row is not None
        row, tag = self._row, self._row.tag
        body = self._card(parent, theme, t("Commit pointé"))
        sha = tk.Label(body, text=tag.commit_sha[:8], background=theme.surface, foreground=theme.link,
                       cursor="hand2", font=(theme.mono[0], theme.mono[1], "underline"), anchor="w")
        sha.pack(anchor="w")
        sha.bind("<Button-1>", lambda e: self.app.open_url(row.commit_url))
        if tag.commit_title:
            self._text(body, theme, tag.commit_title)
        self._line(body, theme, f"{row.author.name} · {format_datetime(tag.committed_date)}", color=theme.muted)
        mr = self._mr
        if mr is not None:
            link = tk.Label(body, text=f"!{mr.iid}  {mr.title}", background=theme.surface, foreground=theme.link,
                            cursor="hand2", font=(theme.font[0], theme.font[1], "underline"), anchor="w",
                            justify="left", wraplength=self._wrap - 30)
            link.pack(fill="x", pady=(6, 0))
            link.bind("<Button-1>", lambda e: self.app.open_url(mr.web_url))
            self._line(body, theme, t("MR dont c'est le commit de merge, de squash ou de tête"), color=theme.muted)

    def _pipeline_card(self, parent: tk.Misc, theme: Theme) -> None:
        data = self._pipeline
        if data is None:
            if self._loading or self._error:
                self._placeholder(parent, theme, t("Pipeline du tag"))
            return
        if data.pipeline is None:
            return  # no pipeline: section hidden (TG-07)
        status = data.pipeline.status
        colors = theme.ok if status == "success" else theme.ko if status in ("failed", "canceled") else theme.na
        body = self._card(parent, theme, t("Pipeline du tag"), PIPELINE_WORDS.get(status, status), colors)
        failed = failed_jobs(data.jobs)
        self._line(body, theme, t("{ago} · {count} job(s), {failed} en échec", ago=ago(data.pipeline.updated_at),
                                                   count=len(data.jobs), failed=len(failed)),
                   color=theme.muted)
        for job in failed:
            self._line(body, theme, job.name, f"{job.status} · {short_duration(job.duration)}".rstrip(" ·"),
                       color=theme.ko[1], mono=True)
        tail = log_tail(data.log)
        if tail:
            tk.Label(body, text=tail, background=theme.bg, foreground=theme.text, justify="left", anchor="w",
                     font=(theme.mono[0], theme.mono[1] - 1), padx=8, pady=6,
                     wraplength=self._wrap - 30).pack(fill="x", pady=(6, 0))
