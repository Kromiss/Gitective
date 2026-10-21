"""Branches tab: active, dead and merged-but-not-deleted branches of the tracked repositories (section 11)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from gitective.database.store import LinkedMr
from gitective.forge.models import Branch
from gitective.repository.branches import (
    ACTIVE,
    DEAD,
    DELETED,
    MERGED,
    STATE_LABELS,
    STATE_ORDER,
    BranchRow,
    build_rows,
    copied_list,
    last_commit_text,
)
from gitective.shared.dates import now_local
from gitective.shared.search import matches
from gitective.ui.components.grid import Column, sort_rows
from gitective.ui.components.pagination import Pager
from gitective.ui.components.widgets import MultiSelect
from gitective.ui.tabs.data_tab import DataTab
from gitective.ui.themes import Theme

if TYPE_CHECKING:
    from gitective.ui.app import App

COLUMNS = [
    Column("repo", "Dépôt", 130),
    Column("branch", "Branche", 240, kind="link", stretch=True),
    Column("last", "Dernier commit", 190, kind="mono"),
    Column("author", "Auteur du dernier commit", 170),
    Column("mrs", "MR liées", 150, kind="links"),
    Column("state", "État", 190, kind="pill"),
]
SORT_KEYS: dict[str, Callable[[BranchRow], Any]] = {
    "repo": lambda r: r.project.path.casefold(),
    "branch": lambda r: r.branch.name.casefold(),
    "last": lambda r: r.branch.committed_date,
    "author": lambda r: r.author.name.casefold(),
    "mrs": lambda r: r.related[0].iid if r.related else None,
    "state": lambda r: STATE_ORDER[r.state],
}
STATE_WORDS = {ACTIVE: "active(s)", DEAD: "morte(s)", MERGED: "mergée(s) non supprimée(s)", DELETED: "supprimée(s)"}
MR_STATES = {"opened": "ouverte", "merged": "mergée", "closed": "fermée", "locked": "verrouillée"}

Stored = tuple[list[tuple[int, Branch, float | None]], list[LinkedMr]]


def state_colors(theme: Theme, state: str) -> tuple[str, str]:
    """Dead in the "red score" color of the theme (BR-04)."""
    return {ACTIVE: theme.info, DEAD: theme.red, MERGED: theme.orange}.get(state, theme.na)


class BranchesTab(DataTab):
    """Lists the branches to follow up: open a MR or delete them in GitLab (BR-01..BR-09)."""

    table = "branches"

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master, app, sort_key="last", ascending=True)
        self._rows: list[BranchRow] = []
        self._visible: list[BranchRow] = []
        saved = app.settings.branch_filters

        bar = ttk.Frame(self, style="Card.TFrame", padding=(14, 12))
        bar.pack(fill="x", padx=16, pady=(12, 0))
        top = ttk.Frame(bar, style="Bar.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Nom", style="BarMuted.TLabel").pack(side="left", padx=(0, 6))
        self._name_filter = tk.StringVar()
        self._name_filter.trace_add("write", lambda *_: self._apply_view(reset_page=True))
        ttk.Entry(top, textvariable=self._name_filter, width=26).pack(side="left")
        self.authors = MultiSelect(top, "Auteurs", self._authors_changed, app.get_theme, all_text="Toutes")
        self.authors.set_selected(saved.authors)
        self.authors.pack(side="left", padx=(12, 0))
        self.repos = MultiSelect(top, "Dépôts", self._repos_changed, app.get_theme)
        self.repos.set_selected([str(r) for r in saved.repos])
        self.repos.pack(side="left", padx=(8, 0))
        self.states = MultiSelect(top, "États", self._states_changed, app.get_theme)
        self.states.set_items([(key, STATE_LABELS[key]) for key in (ACTIVE, DEAD, MERGED, DELETED)], keep_order=True)
        self.states.set_selected(saved.states)
        self.states.pack(side="left", padx=(8, 0))
        self.refresh_button(top).pack(side="right")
        ttk.Button(top, text="⧉  Copier la liste", command=self._copy).pack(side="right", padx=(0, 8))
        self._rules = ttk.Label(bar, style="BarMuted.TLabel")
        self._rules.pack(anchor="w", pady=(10, 0))

        card = ttk.Frame(self, style="Card.TFrame", padding=(10, 8, 10, 10))
        card.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        summary = ttk.Frame(card, style="Bar.TFrame", padding=(6, 2, 6, 8))
        summary.pack(fill="x")
        self._count = ttk.Label(summary, style="Section.TLabel")
        self._count.pack(side="left")
        self._by_state = ttk.Label(summary, style="BarMuted.TLabel")
        self._by_state.pack(side="left", padx=(18, 0))
        ttk.Label(summary, text="Clic sur une branche ou une MR : ouvre GitLab",
                  style="BarMuted.TLabel").pack(side="right")
        self.grid_view = self.make_grid(COLUMNS, "Aucune branche pour ces filtres", links=True, master=card)
        self.grid_view.pack(fill="both", expand=True)
        self.pager = Pager(self, lambda _p, _s: self._render_page(), page_size=app.filters.page_size)
        self.pager.pack(fill="x", padx=16, pady=10)
        self._show_rules()

    # ------------------------------------------------------------- Filters

    def _save_filters(self) -> None:
        """Authors, repositories and states are remembered (BR-06)."""
        saved = self.app.settings.branch_filters
        saved.authors, saved.repos = self.authors.selected, [int(k) for k in self.repos.selected]
        saved.states = self.states.selected
        self.app.save_settings()
        self._apply_view(reset_page=True)

    def _authors_changed(self, _keys: list[str]) -> None:
        self._save_filters()

    def _repos_changed(self, _keys: list[str]) -> None:
        self._save_filters()

    def _states_changed(self, _keys: list[str]) -> None:
        self._save_filters()

    def _people_changed(self, items: list[tuple[str, str]]) -> None:
        self.authors.set_items(items, keep_order=True)

    def _show_rules(self) -> None:
        s = self.app.settings
        regex = f" et les noms correspondant à {s.branch_exclude_regex}" if s.branch_exclude_regex.strip() else ""
        self._rules.configure(text=f"Masquées : branche par défaut, branches protégées{regex} · branche morte "
                                   f"après {s.dead_branch_days} jours sans commit · réglages dans l'onglet Config")

    # ------------------------------------------------------------- Loading

    def reload(self) -> None:
        """Read the stored branches; the synchronisation keeps them up to date (BR-10, CH-07)."""
        self.dirty = False
        self._show_rules()
        if not self.app.ensure_connection():
            return
        store = self.app.store
        ids = [p.id for p in self.app.settings.projects]

        def task(_progress: Callable[[int, int], None]) -> Stored:
            return store.branches(ids), store.linked_mrs(ids)

        self.app.runner.run("branches", task, self._loaded, self.app.report_error)

    def _loaded(self, stored: Stored) -> None:
        branches, mrs = stored
        s = self.app.settings
        self._rows = build_rows(branches, s.projects, mrs, self.app.people, s.branch_exclude_regex,
                                s.dead_branch_days, now_local())
        self.app.register_people((r.author.key, r.author.name) for r in self._rows)
        self._apply_view(reset_page=True)

    # ---------------------------------------------------------------- View

    def _filtered(self) -> list[BranchRow]:
        authors, repos = set(self.authors.selected), {int(k) for k in self.repos.selected}
        states = set(self.states.selected)
        needle = self._name_filter.get().strip().casefold()
        return [r for r in self._rows
                if (not authors or r.author.key in authors) and (not repos or r.project.id in repos)
                and (not states or r.state in states) and matches(needle, r.branch.name)]

    def _apply_view(self, reset_page: bool = False) -> None:
        rows = self._filtered()
        self._visible = sort_rows(rows, SORT_KEYS[self._sort_key], self._ascending)
        self._count.configure(text=f"{len(rows)} branche(s)")
        counts = {state: sum(r.state == state for r in rows) for state in (ACTIVE, DEAD, MERGED, DELETED)}
        self._by_state.configure(text=" · ".join(f"{n} {STATE_WORDS[s]}" for s, n in counts.items() if n))
        self.pager.update_total(len(self._visible), reset=reset_page)
        self._render_page()

    def _render_page(self) -> None:
        theme = self.app.get_theme()
        rows = []
        for r in self._visible[self.pager.slice()]:
            rows.append({
                "repo": r.project.path.split("/")[-1],
                "branch": (r.branch.name, r.branch.web_url or self._branch_url(r)),
                "last": last_commit_text(r),
                "author": r.author.name,
                "mrs": [(f"!{m.iid}", m.web_url, f"{m.title} — {MR_STATES.get(m.state, m.state)}")
                        for m in r.related],
                "state": (STATE_LABELS[r.state], state_colors(theme, r.state)),
                "_muted": r.state == DELETED,
            })
        self.grid_view.set_rows(rows)

    @staticmethod
    def _branch_url(row: BranchRow) -> str:
        base = row.project.web_url.rstrip("/")
        return f"{base}/-/tree/{row.branch.name}" if base else ""

    def _copy(self) -> None:
        """Filtered branches, grouped by author, as Markdown in the clipboard (BR-08)."""
        text = copied_list(self._visible)
        if not text:
            self.app.notify("info", "Aucune branche à copier pour ces filtres.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.notify("success", f"{len(self._visible)} branche(s) copiée(s) dans le presse-papiers.")

    def restyle(self) -> None:
        self._render_page()
