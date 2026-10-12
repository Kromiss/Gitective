"""Main window: tabs, banner, busy indicator and shared application state."""

from __future__ import annotations

import math
import tkinter as tk
import webbrowser
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import ttk

from gitective import APP_NAME, __version__
from gitective.api.client import GitLabClient
from gitective.api.models import User
from gitective.config import settings as config
from gitective.config.settings import Settings, TrackedProject
from gitective.core.avatars import AvatarStore
from gitective.core.cache import SessionCache
from gitective.core.people import PersonDirectory
from gitective.core.rules import RuleSet
from gitective.ui.filters import FilterState
from gitective.ui.mr_tab import MrTab
from gitective.ui.notifications import Banner, describe_error
from gitective.ui.settings_tab import SettingsTab
from gitective.ui.stats_tab import StatsTab
from gitective.ui.themes import Theme, apply_theme, get_theme
from gitective.ui.worker import BackgroundRunner

ASSETS = Path(__file__).resolve().parents[1] / "assets"


class App:
    """Owns the settings, the GitLab client and every tab."""

    def __init__(self, root: tk.Tk, first_launch: bool) -> None:
        self.root = root
        self.settings: Settings = config.load()
        self.theme: Theme = get_theme(self.settings.theme)
        self.filters = FilterState(self.settings.filters)
        self.cache = SessionCache()
        self.client: GitLabClient | None = None
        self.rules: RuleSet | None = None
        self.people = PersonDirectory(self.settings.people)
        self.avatars = AvatarStore(config.AVATAR_DIR, None)
        self.known_users: dict[int, User] = {}
        self._known_people: dict[str, str] = {}
        self._people_listeners: list[Callable[[list[tuple[str, str]]], None]] = []
        self._build_services()

        root.title(f"{APP_NAME} — contrôle des merge requests")
        root.geometry("1360x820")
        root.minsize(1000, 600)
        self.logo_small = self._load_logo(48)
        self._set_icon()
        apply_theme(root, self.theme)

        self.runner = BackgroundRunner(root, self._set_busy)
        self._build_layout()
        root.bind_all("<F5>", lambda e: self.refresh())
        self.root.after(50, lambda: self._start(first_launch))

    # -------------------------------------------------------------- Setup

    def _build_services(self) -> None:
        """(Re)create the client, rules and directories from the settings."""
        s = self.settings
        self.client = GitLabClient(s.gitlab_url, s.token, verify_ssl=s.verify_ssl) if s.is_configured else None
        self.rules = RuleSet.from_settings(s)
        self.people = PersonDirectory(s.people)
        self.avatars = AvatarStore(config.AVATAR_DIR, self.client)

    def _load_logo(self, size: int) -> tk.PhotoImage | None:
        path = ASSETS / "logo.png"
        return self.load_avatar_image(path, size) if path.exists() else None

    def _set_icon(self) -> None:
        ico = ASSETS / "logo.ico"
        try:
            self.root.iconbitmap(default=str(ico))  # Windows
        except tk.TclError:
            if self.logo_small is not None:
                self.root.iconphoto(True, self.logo_small)

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Bar.TFrame", padding=(16, 8))
        header.pack(side="top", fill="x")
        if self.logo_small is not None:
            self._logo_header = self.load_avatar_image(ASSETS / "logo.png", 32)
            ttk.Label(header, image=self._logo_header, style="Bar.TLabel").pack(side="left", padx=(0, 8))
        ttk.Label(header, text=APP_NAME, style="Bar.TLabel",
                  font=(self.theme.font[0], self.theme.font[1] + 4, "bold")).pack(side="left")
        ttk.Label(header, text=f"v{__version__}", style="BarMuted.TLabel").pack(side="left", padx=8)
        self._busy = ttk.Progressbar(header, mode="indeterminate", length=140)
        self._busy_label = ttk.Label(header, text="Chargement…", style="BarMuted.TLabel")

        self.notebook = ttk.Notebook(self.root)
        self.banner = Banner(self.root, lambda: self.theme, before=self.notebook)
        self.notebook.pack(side="top", fill="both", expand=True)
        self.mr_tab = MrTab(self.notebook, self)
        self.stats_tab = StatsTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self)
        self.notebook.add(self.mr_tab, text="Merge Requests")
        self.notebook.add(self.stats_tab, text="Statistiques")
        self.notebook.add(self.settings_tab, text="Config")
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        self._update_repo_items()

    def _start(self, first_launch: bool) -> None:
        if first_launch:
            self.open_wizard()
        elif not self.settings.is_configured:
            self.notebook.select(self.settings_tab)
            self.notify("info", "Renseignez l'URL de l'instance GitLab et le token dans l'onglet Config.")
        else:
            self._tab_changed()

    # ------------------------------------------------------- Shared state

    def get_theme(self) -> Theme:
        return self.theme

    def notify(self, kind: str, message: str) -> None:
        """Show the banner (every error goes through it, ER-04)."""
        self.banner.show(kind, message)

    def report_error(self, exc: BaseException, extra: int = 0) -> None:
        message = describe_error(exc)
        if extra > 0:
            message += f" (+{extra} autre(s) erreur(s) similaire(s))"
        self.notify("error", message)

    def ensure_connection(self) -> bool:
        """True when a client exists; otherwise point the user to Config."""
        if self.client is None:
            self.notify("info", "Renseignez l'URL de l'instance GitLab et le token dans l'onglet Config.")
            return False
        if not self.settings.projects:
            self.notify("info", "Aucun dépôt suivi : choisissez les dépôts à contrôler dans l'onglet Config.")
            return False
        return True

    def selected_projects(self) -> list[TrackedProject]:
        """Tracked projects kept by the repository filter (FI-11)."""
        wanted = set(self.filters.repos)
        return [p for p in self.settings.projects if not wanted or p.id in wanted]

    def is_visible(self, tab: tk.Widget) -> bool:
        return str(self.notebook.select()) == str(tab)

    def open_url(self, url: str) -> None:
        webbrowser.open_new_tab(url)

    def persist_filters(self) -> None:
        """Remember the filters in config.json (FI-06)."""
        self.settings.filters = self.filters.to_settings()
        self._save()

    def column_widths(self, table: str) -> dict[str, int]:
        """Column widths the user set for a table."""
        return dict(self.settings.column_widths.get(table, {}))

    def save_column_widths(self, table: str, widths: dict[str, int]) -> None:
        """Remember dragged column widths in config.json."""
        if widths:
            self.settings.column_widths[table] = widths
        else:
            self.settings.column_widths.pop(table, None)
        self._save()

    def remember_users(self, users: Iterable[User]) -> None:
        for user in users:
            self.known_users[user.id] = user

    def subscribe_people(self, listener: Callable[[list[tuple[str, str]]], None]) -> None:
        """Be told the sorted (key, name) list of known people when it grows."""
        self._people_listeners.append(listener)

    def register_people(self, people: Iterable[tuple[str, str]]) -> None:
        """Record people seen in the data and notify the author filters."""
        before = len(self._known_people)
        for key, name in people:
            self._known_people[key] = name
        if len(self._known_people) != before:
            items = sorted(self._known_people.items(), key=lambda i: i[1].casefold())
            for listener in self._people_listeners:
                listener(items)

    def load_avatar_image(self, path: Path, size: int) -> tk.PhotoImage | None:
        """Load a PNG/GIF and shrink it by an integer factor (AV-06)."""
        try:
            image = tk.PhotoImage(master=self.root, file=str(path))
        except tk.TclError:
            return None
        factor = max(1, math.ceil(max(image.width(), image.height()) / size))
        return image.subsample(factor) if factor > 1 else image

    # ------------------------------------------------------------ Actions

    def refresh(self) -> None:
        """Empty the cache and reload the current tab (CH-05, AV-07)."""
        self.cache.clear()
        self.avatars.clear()
        self.stats_tab.forget_avatars()
        for tab in (self.mr_tab, self.stats_tab):
            tab.dirty = True
        self.banner.hide()
        self._tab_changed()

    def apply_settings(self, new: Settings) -> None:
        """Save new settings and rebuild whatever depends on them."""
        connection_changed = (new.gitlab_url, new.token, new.verify_ssl) != (
            self.settings.gitlab_url, self.settings.token, self.settings.verify_ssl)
        theme_changed = new.theme != self.settings.theme
        new.filters = self.filters.to_settings()
        new.column_widths = self.settings.column_widths
        self.settings = new
        self._save()
        self._build_services()
        if connection_changed:
            self.cache.clear()
        valid = {p.id for p in new.projects}
        self.filters.repos = [r for r in self.filters.repos if r in valid]
        if theme_changed:
            self.theme = get_theme(new.theme)
            apply_theme(self.root, self.theme)
            self.banner.restyle()
            for tab in (self.mr_tab, self.stats_tab):
                tab.restyle()
        self.mr_tab.update_columns()
        self.stats_tab.update_columns()
        self._update_repo_items()
        self.settings_tab.reset()
        for tab in (self.mr_tab, self.stats_tab):
            tab.dirty = True

    def open_wizard(self) -> None:
        from gitective.ui.wizard import Wizard  # local import: wizard imports App types

        Wizard(self)

    # ------------------------------------------------------------ Internal

    def _save(self) -> None:
        try:
            config.save(self.settings)
        except OSError as exc:
            self.notify("error", f"Impossible d'écrire config.json : {exc}")

    def _update_repo_items(self) -> None:
        for tab in (self.mr_tab, self.stats_tab):
            tab.update_repo_items()

    def _tab_changed(self) -> None:
        current = self.notebook.nametowidget(self.notebook.select())
        if getattr(current, "dirty", False):
            current.reload()  # type: ignore[attr-defined]

    def _set_busy(self, busy: bool) -> None:
        """Header loading indicator (CH-02)."""
        if busy:
            self._busy_label.pack(side="right")
            self._busy.pack(side="right", padx=8)
            self._busy.start(12)
        else:
            self._busy.stop()
            self._busy.pack_forget()
            self._busy_label.pack_forget()
