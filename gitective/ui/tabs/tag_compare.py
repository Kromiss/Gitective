"""Comparer sub-tab of the Tags tab: comparison lines, their detail panel and the Markdown copy (section 12.1)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.forge.models import Commit, MergeRequest
from gitective.repository.tag_compare import CompareError, Comparison, compare, copied_text, ref_choices
from gitective.review.rules import Evaluation, score_level
from gitective.settings.config_file import CompareLine, TrackedProject
from gitective.shared.dates import format_datetime
from gitective.ui.components.side_panel import SidePanel
from gitective.ui.themes import Theme

if TYPE_CHECKING:
    from gitective.ui.app import App

# (title, minimum width in characters) of the line columns; the ✕ column has no title.
HEADERS = (("Dépôt", 14), ("Current", 12), ("Référence", 12), ("Date current", 16), ("Date référence", 16),
           ("MR", 5), ("Hors MR", 8), ("Score", 7), ("Divergence", 10))
COMBO_COLUMNS = 3  # Dépôt, Current, Référence are combo boxes, the others labels
DATE_COLUMNS = (4, 5)  # hidden while the detail panel is open, which shows them (like DE-03)


class _Line:
    """Widgets and state of one comparison line."""

    def __init__(self, line: CompareLine) -> None:
        self.line = line
        self.result: Comparison | None = None
        self.error = ""
        self.progress = ""
        self.widgets: list[tk.Widget] = []
        self.labels: list[tk.Label] = []
        self.combos: list[ttk.Combobox] = []
        self.marker: tk.Frame | None = None
        self.choices: tuple[list[str], list[str]] = ([], [])  # (current choices, reference choices)

    @property
    def complete(self) -> bool:
        return bool(self.line.project_id and self.line.current and self.line.reference)


class TagCompareView(ttk.Frame):
    """Lines of (repository, current, reference); each one computed as soon as it is complete (TC-01..TC-09)."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.dirty = True
        self._lines: list[_Line] = []
        self._selected: str | None = None

        bar = ttk.Frame(self, style="Card.TFrame", padding=(14, 12))
        bar.pack(fill="x", padx=16, pady=(12, 0))
        ttk.Button(bar, text="+ Ajouter une ligne", command=self._add).pack(side="left")
        ttk.Label(bar, text="Les MR présentes dans Current et absentes de Référence, d'après l'historique Git",
                  style="BarMuted.TLabel").pack(side="left", padx=(16, 0))
        ttk.Button(bar, text="⟳  Rafraîchir (F5)", style="Accent.TButton", command=app.refresh).pack(side="right")
        ttk.Button(bar, text="⧉  Copier en Markdown", command=self._copy).pack(side="right", padx=(0, 8))

        self._split = ttk.PanedWindow(self, orient="horizontal")
        self._split.pack(fill="both", expand=True, padx=16, pady=(12, 12))
        card = ttk.Frame(self._split, style="Card.TFrame", padding=(10, 8, 10, 10))
        self._split.add(card, weight=1)
        self._table = tk.Frame(card, takefocus=True, highlightthickness=0)
        self._table.pack(anchor="nw")
        self._empty = ttk.Label(card, style="BarMuted.TLabel",
                                text="Aucune ligne : « + Ajouter une ligne », puis choisissez un dépôt, "
                                     "le tag ou la branche Current et le tag de Référence.")
        for key, step in (("<Up>", -1), ("<Down>", 1)):
            self._table.bind(key, lambda e, s=step: self._move(s))
        self._table.bind("<Escape>", lambda e: self.close_detail())
        self.panel = TagCompareDetail(self._split, app, self.close_detail)
        self._split.bind("<ButtonRelease-1>", lambda e: self._panel_resized())
        for line in app.settings.tag_compares:
            self._lines.append(_Line(line))
        self._render()

    # ------------------------------------------------------------- Lines

    def _projects(self) -> list[TrackedProject]:
        return list(self.app.settings.projects)

    def _project(self, project_id: int) -> TrackedProject | None:
        return next((p for p in self._projects() if p.id == project_id), None)

    def _save(self) -> None:
        """The lines are remembered in config.json (TC-02)."""
        self.app.settings.tag_compares = [item.line for item in self._lines]
        self.app.save_settings()

    def _add(self) -> None:
        projects = self._projects()
        if not projects:
            self.app.notify("info", "Aucun dépôt suivi : choisissez les dépôts dans l'onglet Config.")
            return
        # A new line starts on the repository of the last one, the usual case of a multi-repository delivery.
        last = self._lines[-1].line.project_id if self._lines else projects[0].id
        self._lines.append(_Line(CompareLine(project_id=last)))
        self._save()
        self._render()

    def _remove(self, item: _Line) -> None:
        self._lines.remove(item)
        if self._selected == item.line.id:
            self.close_detail()
        self._save()
        self._render()

    def _load_choices(self, item: _Line) -> None:
        """Current: tags then branches; Référence: tags; deleted ones left out (TC-03)."""
        tags, branches = ref_choices(self.app.store, item.line.project_id) if item.line.project_id else ([], [])
        names = [t.name for t in tags]
        item.choices = (names + [b.name for b in branches if b.name not in names], names)

    # ------------------------------------------------------------- Drawing

    def _render(self) -> None:
        theme = self.app.get_theme()
        for child in self._table.winfo_children():
            child.destroy()
        self._table.configure(background=theme.surface)
        if not self._lines:
            self._empty.pack(anchor="w", padx=6, pady=8)
        else:
            self._empty.pack_forget()
        bold = (theme.font[0], theme.font[1], "bold")
        for column, (title, _) in enumerate(HEADERS, start=1):
            if column in DATE_COLUMNS and self._panel_open:
                continue
            tk.Label(self._table, text=title, background=theme.surface, foreground=theme.muted, font=bold,
                     anchor="w", padx=6, pady=6).grid(row=0, column=column, sticky="ew")
        for row, item in enumerate(self._lines, start=1):
            self._load_choices(item)
            self._draw_line(item, row, theme)
            if item.complete and item.result is None and not item.error and not item.progress:
                self._compute(item)

    def _draw_line(self, item: _Line, row: int, theme: Theme) -> None:
        projects = self._projects()
        item.marker = tk.Frame(self._table, width=3, background=theme.surface)
        item.marker.grid(row=row, column=0, sticky="ns", pady=2)
        repo = ttk.Combobox(self._table, state="readonly", width=HEADERS[0][1],
                            values=[p.path.split("/")[-1] for p in projects])
        project = self._project(item.line.project_id)
        repo.set(project.path.split("/")[-1] if project else "")
        repo.bind("<<ComboboxSelected>>", lambda e: self._repo_chosen(item, projects[repo.current()].id))
        current = self._ref_combo(item, 0, HEADERS[1][1])
        reference = self._ref_combo(item, 1, HEADERS[2][1])
        item.combos = [repo, current, reference]
        for column, combo in enumerate(item.combos, start=1):
            combo.grid(row=row, column=column, sticky="ew", padx=4, pady=3)
        item.labels = []
        for column in range(COMBO_COLUMNS + 1, len(HEADERS) + 1):
            label = tk.Label(self._table, anchor="w", padx=8, pady=3, cursor="hand2")
            label.grid(row=row, column=column, sticky="nsew", pady=3)
            label.bind("<Button-1>", lambda e, i=item: self.open_detail(i))
            item.labels.append(label)
        remove = ttk.Button(self._table, text="✕", width=3, command=lambda: self._remove(item))
        remove.grid(row=row, column=len(HEADERS) + 1, padx=(6, 0), pady=3)
        self._fill(item, theme)

    def _ref_combo(self, item: _Line, which: int, width: int) -> ttk.Combobox:
        """Combo box with search: typing narrows the list, only a listed value is kept (TC-03)."""
        combo = ttk.Combobox(self._table, width=width, values=item.choices[which])
        combo.set(item.line.current if which == 0 else item.line.reference)

        def narrow(event: tk.Event) -> None:
            if event.keysym in ("Return", "Escape", "Tab", "Down", "Up"):
                return
            needle = combo.get().casefold()
            combo.configure(values=[c for c in item.choices[which] if needle in c.casefold()])

        def commit(_event: object = None) -> None:
            try:
                value = combo.get().strip()
            except tk.TclError:  # the line was redrawn meanwhile
                return
            old = item.line.current if which == 0 else item.line.reference
            if value not in item.choices[which]:
                combo.set(old)  # not a tag (or branch) of the repository: the previous choice stays
            elif value != old:
                self._ref_chosen(item, which, value)
            combo.configure(values=item.choices[which])

        combo.bind("<KeyRelease>", narrow)
        combo.bind("<<ComboboxSelected>>", commit)
        combo.bind("<Return>", commit)
        combo.bind("<FocusOut>", commit)
        return combo

    def _fill(self, item: _Line, theme: Theme) -> None:
        """Dates, counts, score and divergence of a line (TC-07)."""
        selected = item.line.id == self._selected
        bg = theme.selected_row if selected else theme.surface
        if item.marker is not None:
            item.marker.configure(background=theme.accent if selected else theme.surface)
        result = item.result
        texts = [""] * 6
        colors: list[tuple[str, str]] = [(bg, theme.text)] * 6
        if item.error:
            texts[0] = item.error
            colors[0] = (bg, theme.ko[1])
        elif item.progress:
            texts[0] = item.progress
            colors[0] = (bg, theme.muted)
        elif result is not None:
            texts[:3] = [format_datetime(result.current.date), format_datetime(result.reference.date),
                         str(len(result.ahead.mrs))]
            texts[3] = str(len(result.ahead.orphans))
            if result.average is not None:
                s = self.app.settings
                level = score_level(round(result.average, 6), s.green_threshold, s.orange_threshold)
                texts[4], colors[4] = f"{result.average:.0f} %", theme.level_colors(level)
            if not result.behind.empty:
                texts[5], colors[5] = f"⚠ {result.behind.commits}", theme.orange
        elif not item.complete:
            texts[0] = "Choisissez Current et Référence"
            colors[0] = (bg, theme.muted)
        mono = (theme.mono[0], theme.mono[1] - 1)
        for index, (label, text, (back, fore)) in enumerate(zip(item.labels, texts, colors)):
            font = mono if index < 2 and result is not None and not item.error else theme.font
            if index >= 4 and text:
                font = (theme.font[0], theme.font[1], "bold")
            label.configure(text=text, background=back, foreground=fore, font=font)
        dates = not self._panel_open
        if item.error or item.progress or not item.complete:
            # A message takes the width of the date and count columns.
            item.labels[0].grid_configure(column=COMBO_COLUMNS + 1, columnspan=4)
            for label in item.labels[1:4]:
                label.grid_remove()
        else:
            item.labels[0].grid_configure(columnspan=1)
            for label in item.labels[:4]:
                label.grid()
            for label in item.labels[:2]:
                if not dates:
                    label.grid_remove()

    # ------------------------------------------------------------- Choices

    def _repo_chosen(self, item: _Line, project_id: int) -> None:
        if project_id == item.line.project_id:
            return
        item.line.project_id, item.line.current, item.line.reference = project_id, "", ""
        item.result, item.error, item.progress = None, "", ""
        self._save()
        self._render()

    def _ref_chosen(self, item: _Line, which: int, value: str) -> None:
        if which == 0:
            item.line.current = value
        else:
            item.line.reference = value
        item.result, item.error, item.progress = None, "", ""
        self._save()
        if item.complete:
            self._compute(item)
        else:
            self._fill(item, self.app.get_theme())

    # ------------------------------------------------------------- Computing

    def _compute(self, item: _Line) -> None:
        """In the background, as soon as the line is complete (TC-04)."""
        project = self._project(item.line.project_id)
        if project is None:
            item.error = "Dépôt non suivi"
            self._fill(item, self.app.get_theme())
            return
        line = item.line
        data, rules, people = self.app.data, self.app.rules, self.app.people
        assert rules is not None
        workers = self.app.settings.parallel_requests
        item.progress = "Calcul…"
        self._fill(item, self.app.get_theme())

        def task(progress: Callable[[int, int], None]) -> Comparison:
            return compare(data, project, line.current, line.reference, rules, people, workers, progress)

        def still(current: _Line = item) -> bool:
            return current in self._lines and (current.line.current, current.line.reference) == (
                line.current, line.reference)

        def done(result: Comparison) -> None:
            if not still():
                return
            item.result, item.progress, item.error = result, "", ""
            self._fill(item, self.app.get_theme())
            if self._selected == line.id:
                self.panel.show(item.result, item.error)

        def failed(exc: BaseException) -> None:
            if not still():
                return
            item.progress = ""
            known = isinstance(exc, CompareError)
            item.error = str(exc) if known else "Calcul impossible : instance injoignable ou droits insuffisants"
            if not known:
                self.app.report_error(exc)
            self._fill(item, self.app.get_theme())
            if self._selected == line.id:
                self.panel.show(None, item.error)

        def progress(done_count: int, total: int) -> None:
            if still() and total:
                item.progress = f"Calcul… {done_count} / {total} commits"
                self._fill(item, self.app.get_theme())

        self.app.runner.run(f"compare:{line.id}", task, done, failed, on_progress=progress)

    def reload(self) -> None:
        """After a synchronisation: tags and branches may have moved; stored comparisons need no request (TC-10)."""
        self.dirty = False
        for item in self._lines:
            item.result, item.error, item.progress = None, "", ""
        self._render()

    # ------------------------------------------------------------- Detail panel

    @property
    def _panel_open(self) -> bool:
        return str(self.panel) in {str(p) for p in self._split.panes()}

    def open_detail(self, item: _Line) -> None:
        """Click on a line: its MRs in the side panel (TC-08, same mechanics as DE-01)."""
        self._selected = item.line.id
        if not self._panel_open:
            self._split.add(self.panel, weight=0)
            self._split.update_idletasks()
            total = self._split.winfo_width()
            if total > 1:
                self._split.sashpos(0, max(300, total - self.app.settings.detail_width))
        self._render()
        self._table.focus_set()
        self.panel.show(item.result, item.error or item.progress or ("" if item.complete else
                                                                     "Choisissez Current et Référence."))

    def close_detail(self) -> None:
        if self._panel_open:
            self._split.forget(self.panel)
        self._selected = None
        self._render()

    def _move(self, step: int) -> None:
        ids = [i.line.id for i in self._lines]
        if self._selected not in ids:
            return
        index = max(0, min(len(ids) - 1, ids.index(self._selected) + step))
        self.open_detail(self._lines[index])

    def _panel_resized(self) -> None:
        if self._panel_open:
            self.app.save_detail_width(self.panel.winfo_width())  # shared with the other panels

    # ------------------------------------------------------------- Copy and misc

    def _copy(self) -> None:
        """Every computed line as Markdown in the clipboard (TC-09)."""
        results = [i.result for i in self._lines if i.result is not None]
        if not results:
            self.app.notify("info", "Aucune comparaison calculée à copier.")
            return
        self.clipboard_clear()
        self.clipboard_append(copied_text(results, self.app.people))
        self.app.notify("success", f"{len(results)} comparaison(s) copiée(s) dans le presse-papiers.")

    def update_repo_items(self) -> None:
        self._render()

    def restyle(self) -> None:
        self._render()
        if self._panel_open:
            self.panel.render()


class TagCompareDetail(SidePanel):
    """MRs of the gap, commits without MR and the divergence of one comparison line (TC-08)."""

    def __init__(self, master: tk.Misc, app: App, on_close: Callable[[], None]) -> None:
        super().__init__(master)
        self.app = app
        self._on_close = on_close
        self._result: Comparison | None = None
        self._message = ""

    def show(self, result: Comparison | None, message: str = "") -> None:
        self._result, self._message = result, message
        self.render()

    def render(self) -> None:
        theme = self.app.get_theme()
        inner = self._clear(theme)
        head = tk.Frame(inner, background=theme.bg)
        head.pack(fill="x", padx=12, pady=(12, 0))
        self._close_button(head, theme, self._on_close)
        result = self._result
        if result is None:
            tk.Label(head, text=self._message or "Calcul…", background=theme.bg, foreground=theme.muted,
                     font=self._font(theme), anchor="w", justify="left",
                     wraplength=self._wrap - 30).pack(fill="x")
            self._bind_wheel()
            return
        tk.Label(head, text=f"{result.reference.name} → {result.current.name}", background=theme.bg,
                 foreground=theme.text, font=(theme.mono[0], theme.mono[1] + 3, "bold"), anchor="w",
                 wraplength=self._wrap - 30, justify="left").pack(fill="x")
        kind = "branche" if result.current.is_branch else "tag"
        lines = (f"{result.project.path.split('/')[-1]} · current : {kind}",
                 f"{result.reference.name} : {format_datetime(result.reference.date)}",
                 f"{result.current.name} : {format_datetime(result.current.date)}")
        for text in lines:
            tk.Label(head, text=text, background=theme.bg, foreground=theme.muted,
                     font=(theme.mono[0], theme.mono[1] - 1), anchor="w").pack(fill="x")
        tags = tk.Frame(inner, background=theme.bg)
        tags.pack(fill="x", padx=12, pady=(8, 0))
        self._tag(tags, f"{len(result.ahead.mrs)} MR", theme.info, theme)
        self._tag(tags, f"{len(result.ahead.orphans)} commit(s) sans MR", theme.na, theme)
        if result.ahead.empty:
            body = self._card(inner, theme, "Résultat")
            self._line(body, theme, "Aucune différence : la référence contient déjà tout Current.",
                       color=theme.muted)
        scores = {(e.mr.project_id, e.mr.iid): e for e in result.evaluations}
        if result.ahead.mrs:
            body = self._card(inner, theme, f"Merge requests · {len(result.ahead.mrs)}")
            for mr in result.ahead.mrs:
                self._mr(body, theme, mr, scores.get((mr.project_id, mr.iid)))
        if result.ahead.orphans:
            body = self._card(inner, theme, f"Commits sans MR · {len(result.ahead.orphans)}")
            for commit in result.ahead.orphans:
                self._commit(body, theme, commit)
        if not result.behind.empty:
            body = self._card(inner, theme, f"Divergence · {result.behind.commits} commit(s)", "⚠", theme.orange)
            self._line(body, theme, "Présents dans la référence mais absents de current", color=theme.orange[1])
            for mr in result.behind.mrs:
                self._mr(body, theme, mr, None)
            for commit in result.behind.orphans:
                self._commit(body, theme, commit)
        tk.Frame(inner, background=theme.bg, height=16).pack(fill="x")
        self._bind_wheel()

    def _link(self, parent: tk.Misc, theme: Theme, text: str, url: str, mono: bool = False) -> tk.Label:
        font = (theme.mono[0], theme.mono[1] - 1, "underline") if mono else (theme.font[0], theme.font[1], "underline")
        label = tk.Label(parent, text=text, background=theme.surface, foreground=theme.link, cursor="hand2",
                         font=font, anchor="w", justify="left", wraplength=self._wrap - 110)
        label.bind("<Button-1>", lambda e: self.app.open_url(url))
        return label

    def _mr(self, parent: tk.Misc, theme: Theme, mr: MergeRequest, ev: Evaluation | None) -> None:
        row = tk.Frame(parent, background=theme.surface)
        row.pack(fill="x", pady=(4, 0))
        if ev is not None:
            s = self.app.settings
            bg, fg = theme.level_colors(score_level(ev.score, s.green_threshold, s.orange_threshold))
            tk.Label(row, text=f"{ev.score:.0f} %", background=bg, foreground=fg, padx=6,
                     font=self._font(theme, -1, "bold")).pack(side="right", anchor="n")
        self._link(row, theme, mr.title, mr.web_url).pack(side="left", fill="x")
        people = self.app.people
        who = people.for_user(mr.author).name
        if mr.merged_by:
            who += f" → {people.for_user(mr.merged_by).name}"
        self._line(parent, theme, f"!{mr.iid} · {who} · {format_datetime(mr.merged_at)}", color=theme.muted)

    def _commit(self, parent: tk.Misc, theme: Theme, commit: Commit) -> None:
        row = tk.Frame(parent, background=theme.surface)
        row.pack(fill="x", pady=(4, 0))
        self._link(row, theme, commit.short_id, commit.web_url, mono=True).pack(side="left")
        tk.Label(row, text=commit.title, background=theme.surface, foreground=theme.text, font=self._font(theme),
                 anchor="w", justify="left", wraplength=self._wrap - 130).pack(side="left", padx=(8, 0), fill="x")
        author = self.app.people.for_git(commit.author_name, commit.author_email).name
        self._line(parent, theme, f"{author} · {format_datetime(commit.committed_date)}", color=theme.muted)
