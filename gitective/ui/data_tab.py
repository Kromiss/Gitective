"""Base class of the data views (Merge Requests, direct commits, Statistics)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.core.rules import Evaluation
from gitective.ui.grid import Column, DataGrid
from gitective.ui.widgets import MultiSelect

if TYPE_CHECKING:
    from gitective.ui.app import App


class DataTab(ttk.Frame):
    """Shared behaviour: lazy reload, sortable grid, repository and people selectors.

    Subclasses set `table` (key of the saved column widths), create
    `grid_view`, `repos` and `authors`, and implement reload() and _apply_view().
    """

    table = ""

    def __init__(self, master: tk.Misc, app: App, sort_key: str, ascending: bool) -> None:
        super().__init__(master)
        self.app = app
        self.dirty = True
        self._sort_key = sort_key
        self._ascending = ascending
        self.grid_view: DataGrid
        self.repos: MultiSelect
        self.authors: MultiSelect
        app.subscribe_people(self._people_changed)

    # ------------------------------------------------------------- Widgets

    def make_grid(self, columns: Sequence[Column], empty_text: str, links: bool = False,
                  master: tk.Misc | None = None, table: str | None = None,
                  on_link: Callable[[str], None] | None = None) -> DataGrid:
        """Sortable grid whose column widths are saved under `table` (the tab's own by default)."""
        name = table or self.table
        grid = DataGrid(master or self, columns, self.app.get_theme, on_sort=self._sort_by,
                        on_link=on_link or (self.app.open_url if links else None), empty_text=empty_text,
                        widths=self.app.column_widths(name),
                        on_widths_changed=lambda w: self.app.save_column_widths(name, w))
        grid.set_sort(self._sort_key, self._ascending)
        return grid

    def make_authors(self, parent: tk.Misc, label: str = "Auteurs") -> MultiSelect:
        """People selector bound to the shared author filter (FI-09)."""
        widget = MultiSelect(parent, label, self._authors_changed, self.app.get_theme, all_text="Toutes")
        widget.set_selected(self.app.filters.authors)
        return widget

    def refresh_button(self, parent: tk.Misc, compact: bool = False) -> ttk.Button:
        if compact:
            return ttk.Button(parent, text="⟳", width=3, style="Accent.TButton", command=self.app.refresh)
        return ttk.Button(parent, text="⟳  Rafraîchir (F5)", style="Accent.TButton", command=self.app.refresh)

    # ------------------------------------------------------------- Loading

    def request_reload(self) -> None:
        """Reload now when visible, otherwise on next display (CH-04)."""
        self.dirty = True
        if self.app.is_visible(self):
            self.reload()

    def reload(self) -> None:
        raise NotImplementedError

    def absorb(self, evaluations: Iterable[Evaluation], errors: Sequence[BaseException]) -> None:
        """Report load errors and record the users and people seen in the results."""
        if errors:
            self.app.report_error(errors[0], extra=len(errors) - 1)
        else:
            self.app.report_offline()
        evaluations = list(evaluations)
        self.app.remember_users(u for e in evaluations for u in (e.mr.author, e.mr.merged_by) if u)
        self.app.register_people((p.key, p.name) for e in evaluations for p in (e.author, e.merger) if p)

    # ---------------------------------------------------------------- View

    def _apply_view(self, reset_page: bool = False) -> None:
        raise NotImplementedError

    def _sort_by(self, key: str) -> None:
        """Sort the whole filtered list, then go back to page 1 (TA-02)."""
        self._ascending = not self._ascending if key == self._sort_key else True
        self._sort_key = key
        self.grid_view.set_sort(key, self._ascending)
        self._apply_view(reset_page=True)

    def _authors_changed(self, keys: list[str]) -> None:
        self.app.filters.authors = keys
        self.app.filters.changed("authors")

    def _people_changed(self, items: list[tuple[str, str]]) -> None:
        self.authors.set_items(items)

    def restyle(self) -> None:
        self.grid_view.redraw()

    def update_repo_items(self) -> None:
        self.repos.set_items([(str(p.id), p.path) for p in self.app.settings.projects])
