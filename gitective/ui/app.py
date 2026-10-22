"""Main window: tabs, banner, badges, busy indicator, synchronisation loop and shared state."""

from __future__ import annotations

import base64
import math
import sys
import tkinter as tk
import webbrowser
from tkinter import messagebox
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk

from gitective.shared.i18n import t
from gitective import APP_NAME, __version__
from gitective.forge.gitlab_client import GitLabClient
from gitective.forge.models import MergeRequest, User
from gitective.settings import config_file as config
from gitective.settings.config_file import Settings, TrackedProject
from gitective.shared.avatars import AvatarStore
from gitective.shared.dates import format_datetime, now_local, to_local
from gitective.shared.people import PersonDirectory
from gitective.shared.repo_names import short_name
from gitective.review.auto_sync import SyncOutcome, synchronise
from gitective.review.my_mrs import (
    ASSIGNEE,
    AUTHOR,
    REVIEWER,
    MyMr,
    author_counts,
    authored_open_mrs,
    badge_counts,
    badge_tip,
    load_user,
    new_count,
    seen_on_click,
    unseen_keys,
)
from gitective.review.rules import Evaluation, RuleSet, score_level
from gitective.database.store import Store, StoreError
from gitective.database.sync import ForgeData
from gitective.settings.filter_state import FilterState
from gitective.ui.tabs.branches import BranchesTab
from gitective.ui.tabs.merge_requests import MrTab
from gitective.ui.tabs.tags import TagsTab
from gitective.ui.components.dialogs import ask_unsaved
from gitective.ui.components.tab_bar import TabBar
from gitective.ui.alerts.badges import Badge
from gitective.ui.alerts.desktop_toast import Toasts, flash_taskbar
from gitective.ui.alerts.error_banner import Banner, describe_error
from gitective.ui.tabs.overview import OverviewTab
from gitective.ui.tabs.config import SettingsTab
from gitective.ui.tabs.statistics import StatsTab
from gitective.ui.themes import Theme, apply_theme, get_theme
from gitective.ui.background import BackgroundRunner

ASSETS = Path(__file__).resolve().parents[1] / "assets"
WINDOW_TITLE = t("{app} — contrôle des merge requests", app=APP_NAME)


def monitor_area(root: tk.Misc) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the monitor holding most of the window; None outside Windows (VE-13).

    Same DPI awareness as Tk (set in main.py), so both use the same coordinates.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        hwnd = user32.GetParent(root.winfo_id())  # the Tk wrapper window
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        rect = info.rcMonitor
        return rect.left, rect.top, rect.right, rect.bottom
    except (AttributeError, OSError):
        return None


class App:
    """Owns the settings, the GitLab client and every tab."""

    def __init__(self, root: tk.Tk, first_launch: bool) -> None:
        self.root = root
        self.settings: Settings = config.load()
        self.theme: Theme = get_theme(self.settings.theme)
        self.filters = FilterState(self.settings.filters)
        self.store = self._open_store()
        self.client: GitLabClient | None = None
        self.data = ForgeData(None, self.store)
        self.rules: RuleSet | None = None
        self.people = PersonDirectory(self.settings.people)
        self.avatars = AvatarStore(self.data)
        self.known_users: dict[int, User] = {}
        self._known_people: dict[str, str] = {}
        self._people_listeners: list[Callable[[list[tuple[str, str]]], None]] = []
        # Last known token owner and own open MRs, so the interface is right even offline (PR-07).
        self.user: User | None = load_user(self.store)
        self.my_mrs: list[MyMr] = self.store.my_mrs()
        self.authored: list[MergeRequest] = []  # own open MRs of the tracked repositories (AM-09)
        self._seen = self.store.seen_roles()
        self._new_at_click: set[tuple[int, int]] = set()  # MRs that were new when a badge was clicked
        self.last_sync: datetime | None = None
        self.next_sync: datetime | None = None
        self._sync_timer: str | None = None
        self._syncing = False
        self._windowed: tuple[str, str] | None = None  # geometry and state before full screen (VE-13)
        self._build_services()

        root.title(WINDOW_TITLE)
        root.geometry("1440x880")
        root.minsize(1000, 600)
        self.logo_small = self._load_logo(48)
        self._set_icon()
        apply_theme(root, self.theme)

        self.runner = BackgroundRunner(root, self._set_busy)
        self._build_layout()
        apply_theme(root, self.theme)  # again, for the plain Tk widgets the tabs just created
        root.bind_all("<F5>", lambda e: self.refresh())
        root.bind_all("<F11>", lambda e: self.toggle_fullscreen())
        self.root.after(50, lambda: self._start(first_launch))

    # -------------------------------------------------------------- Setup

    def _open_store(self) -> Store:
        """Open gitective.db; offer to recreate it when unreadable (ER-06)."""
        try:
            store = Store(config.DB_PATH)
        except StoreError as exc:
            recreate = messagebox.askyesno(
                t("Base locale illisible"),
                t("La base locale gitective.db est illisible, corrompue ou verrouillée ({error}).\n\n"
                  "La recréer ? Les données seront relues depuis GitLab.", error=exc))
            if not recreate:
                raise SystemExit(1) from exc
            for suffix in ("", "-wal", "-shm"):
                config.DB_PATH.with_name(config.DB_PATH.name + suffix).unlink(missing_ok=True)
            store = Store(config.DB_PATH)
        # The base belongs to one instance (CH-10): data of another one is dropped.
        url = self.settings.gitlab_url.rstrip("/")
        if url and store.get_meta("instance_url") not in (None, url):
            store.clear()
        if url:
            store.set_meta("instance_url", url)
        return store

    def _build_services(self) -> None:
        """(Re)create the client, rules and directories from the settings."""
        s = self.settings
        self.client = GitLabClient(s.gitlab_url, s.token, verify_ssl=s.verify_ssl) if s.is_configured else None
        self.data = ForgeData(self.client, self.store)
        self.rules = RuleSet.from_settings(s)
        self.people = PersonDirectory(s.people)
        self.avatars = AvatarStore(self.data)

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
        # Header: logo, name, the main tabs, then the loading indicator and the Merger badges.
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(16, 0))
        header.pack(side="top", fill="x")
        if self.logo_small is not None:
            self._logo_header = self.load_avatar_image(ASSETS / "logo.png", 30)
            ttk.Label(header, image=self._logo_header, style="Header.TLabel").pack(side="left", padx=(0, 8), pady=8)
        ttk.Label(header, text=APP_NAME, style="Header.TLabel",
                  font=(self.theme.font[0], self.theme.font[1] + 4, "bold")).pack(side="left")
        ttk.Label(header, text=f"v{__version__}", style="HeaderMuted.TLabel").pack(side="left", padx=(6, 0))
        self.tab_bar = TabBar(header, self.get_theme, lambda i: self.notebook.select(i))
        self.tab_bar.pack(side="left", fill="y", padx=(24, 0))
        # Assignee, reviewer and author badges, top right of every tab (BA-01).
        self._badges = ttk.Frame(header, style="Header.TFrame")
        self._badges.pack(side="right", padx=(12, 0))
        self._badge_list = [Badge(self._badges, role, label, self.get_theme, lambda r=role: self.show_mine(r))
                            for role, label in ((ASSIGNEE, t("Assigné")), (REVIEWER, t("Relecteur")),
                                                (AUTHOR, t("Auteur")))]
        for badge in self._badge_list:
            badge.pack(side="left", padx=(0, 10))
        self._busy = ttk.Progressbar(header, mode="indeterminate", length=120)
        self._busy_label = ttk.Label(header, text=t("Chargement…"), style="HeaderMuted.TLabel")
        ttk.Separator(self.root, orient="horizontal").pack(side="top", fill="x")
        logo = ASSETS / "logo.png"
        self._toast_logo = self.load_avatar_image(logo, 40) if logo.exists() else None
        self.toasts = Toasts(self.root, self.get_theme, self.open_url, self._open_merge_requests,
                             self._open_notification_settings, self._score_colors, self._toast_logo,
                             repo_label=self.repo_label, score_level=self._score_level)

        self.notebook = ttk.Notebook(self.root, style="Pages.TNotebook")
        self.banner = Banner(self.root, lambda: self.theme, before=self.notebook)
        self.notebook.pack(side="top", fill="both", expand=True)
        self.overview_tab = OverviewTab(self.notebook, self)
        self.mr_tab = MrTab(self.notebook, self)
        self.branches_tab = BranchesTab(self.notebook, self)
        self.tags_tab = TagsTab(self.notebook, self)
        self.stats_tab = StatsTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self)
        self._current_tab: int | None = None
        # The overview is the first tab, shown at launch (VE-01); Branches and Tags follow the MRs (BR-01, TG-01).
        for tab, text in ((self.overview_tab, t("Vue d'ensemble")), (self.mr_tab, t("Merge Requests")),
                          (self.branches_tab, t("Branches")), (self.tags_tab, t("Tags")),
                          (self.stats_tab, t("Statistiques")), (self.settings_tab, t("Config"))):
            self.notebook.add(tab, text=text)
            self.tab_bar.add(text)
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        self._update_repo_items()
        self._update_badges()
        self.mr_tab.update_columns()

    def _start(self, first_launch: bool) -> None:
        if first_launch:
            self.open_wizard()
        elif not self.settings.is_configured:
            self.notebook.select(self.settings_tab)
            self.notify("info", t("Renseignez l'URL de l'instance GitLab et le token dans l'onglet Config."))
        else:
            self._tab_changed()
            self.sync()

    # ------------------------------------------------------- Shared state

    def get_theme(self) -> Theme:
        return self.theme

    def me_key(self) -> str | None:
        """Person key of the token owner, to show "Moi" (AM-07)."""
        return self.people.for_user(self.user).key if self.user else None

    def repo_label(self, path: str) -> str:
        """Short name of a repository, its whole path when another known repository has the same name."""
        paths = [p.path for p in self.settings.projects] + [mr.project_path for mr, _ in self.my_mrs]
        return short_name(path, paths)

    def me_name(self) -> str:
        return self.people.for_user(self.user).name if self.user else ""

    def new_mr_keys(self) -> set[tuple[int, int]]:
        """Own open MRs to flag as new: unseen roles, and those that were new at the last badge click."""
        return {(p, i) for p, i, _ in unseen_keys(self.my_mrs, self._seen)} | self._new_at_click

    def notify(self, kind: str, message: str) -> None:
        """Show the banner (every error goes through it, ER-04)."""
        self.banner.show(kind, message)

    def report_offline(self) -> None:
        """Banner of the offline mode: stored data is shown (CH-08)."""
        since = self.data.offline_since
        if since is not None:
            self.notify("info", t("Instance GitLab injoignable : affichage des données locales "
                                  "(dernière synchronisation le {date}).", date=format_datetime(since)))

    def report_error(self, exc: BaseException, extra: int = 0) -> None:
        message = describe_error(exc)
        if extra > 0:
            message += t(" (+{count} autre(s) erreur(s) similaire(s))", count=extra)
        self.notify("error", message)

    def ensure_connection(self) -> bool:
        """True when a client exists; otherwise point the user to Config."""
        if self.client is None:
            self.notify("info", t("Renseignez l'URL de l'instance GitLab et le token dans l'onglet Config."))
            return False
        if not self.settings.projects:
            self.notify("info", t("Aucun dépôt suivi : choisissez les dépôts à contrôler dans l'onglet Config."))
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

    def save_settings(self) -> None:
        """Write config.json after a tab changed its remembered filters (BR-06, TG-04)."""
        self._save()

    def save_config_view(self, view: str) -> None:
        """Remember the last Config sub-tab (OC-14)."""
        self.settings.config_view = view
        self._save()

    def save_stats_view(self, view: str) -> None:
        """Remember the Statistics view, per person or per repository (ST-01)."""
        self.settings.stats_view = view
        self._save()

    def save_detail_width(self, width: int) -> None:
        """Remember the width of the MR detail panel (DE-02)."""
        if width > 1 and abs(width - self.settings.detail_width) > 4:
            self.settings.detail_width = max(280, min(900, width))
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
            self._people_changed()

    def _people_changed(self) -> None:
        """Author filter entries: the user first as "Moi (nom)", then everyone by name (FI-09)."""
        me = self.me_key()
        items = sorted(((k, n) for k, n in self._known_people.items() if k != me), key=lambda i: i[1].casefold())
        if me is not None:
            items.insert(0, (me, t("Moi ({name})", name=self.me_name())))
        for listener in self._people_listeners:
            listener(items)

    def load_avatar_image(self, source: Path | bytes, size: int) -> tk.PhotoImage | None:
        """Load a PNG/GIF file or bytes and shrink it by an integer factor (AV-06)."""
        try:
            if isinstance(source, bytes):
                image = tk.PhotoImage(master=self.root, data=base64.b64encode(source))
            else:
                image = tk.PhotoImage(master=self.root, file=str(source))
        except tk.TclError:
            return None
        factor = max(1, math.ceil(max(image.width(), image.height()) / size))
        return image.subsample(factor) if factor > 1 else image

    # ------------------------------------------------------------ Actions

    def refresh(self) -> None:
        """Bring the stored data up to date and reload the current tab (CH-05, AV-07)."""
        self.stats_tab.forget_avatars()
        self.banner.hide()
        self.sync(manual=True)

    # ------------------------------------------------------- Synchronisation

    def _schedule_sync(self) -> None:
        """Next automatic synchronisation in N minutes, even when the window is minimized (CH-13)."""
        if self._sync_timer is not None:
            self.root.after_cancel(self._sync_timer)
        minutes = self.settings.sync_minutes
        self.next_sync = now_local() + timedelta(minutes=minutes)
        self._sync_timer = self.root.after(minutes * 60_000, lambda: self.sync())

    def sync(self, manual: bool = False) -> None:
        """Update the base incrementally, the token owner and the own MRs, then the display (CH-05, CH-13)."""
        self._schedule_sync()
        if self.client is None or self._syncing:
            if manual and self.client is None:
                self._tab_changed()
            return
        self._syncing = True
        data, store, people = self.data, self.store, self.people
        settings = self.settings
        projects = list(settings.projects)
        previous = self.user

        def task(_progress: Callable[[int, int], None]) -> SyncOutcome:
            return synchronise(data, store, projects, settings, people, previous)

        def done(outcome: SyncOutcome) -> None:
            self._syncing = False
            self.last_sync = now_local()
            self._synced(outcome, manual)

        def failed(exc: BaseException) -> None:
            self._syncing = False
            self.report_error(exc)  # banner only, never a desktop notification (ER-04)

        self.runner.run("sync", task, done, failed)

    def _synced(self, outcome: SyncOutcome, manual: bool) -> None:
        if outcome.user != self.user:
            self.user = outcome.user
            self._people_changed()
        self.my_mrs = outcome.my_mrs
        self._seen = self.store.seen_roles()
        self._update_badges()
        self.mr_tab.update_repo_items()
        if outcome.errors:
            self.report_error(outcome.errors[0], extra=len(outcome.errors) - 1)
        elif manual:
            self.report_offline()
        if outcome.notices:
            self.toasts.show(outcome.notices)
            if any(n.kind == "role" for n in outcome.notices):
                flash_taskbar(self.root)
        self.settings_tab.show_user()
        for tab in (self.overview_tab, self.mr_tab, self.branches_tab, self.tags_tab, self.stats_tab):
            tab.dirty = True
        current = self.notebook.nametowidget(self.notebook.select())
        if current is self.mr_tab:
            self.mr_tab.soft_reload()
        else:
            self._tab_changed()

    # ------------------------------------------------------- Badges (6.5)

    def _update_badges(self) -> None:
        """Counts, tooltips and the window title (BA-01, BA-03, BA-04)."""
        self.authored = authored_open_mrs(self.store, [p.id for p in self.settings.projects], self.people, self.user)
        counts = (badge_counts(self.my_mrs, self._seen, ASSIGNEE), badge_counts(self.my_mrs, self._seen, REVIEWER),
                  author_counts(self.authored))
        for badge, count, word in zip(self._badge_list, counts, (t("assignée(s)"), t("en relecture"), t("MR ouverte(s)"))):
            badge.update_counts(count, badge_tip(count, word))
        new = new_count(self.my_mrs, self._seen)
        self.root.title(f"{APP_NAME} ({new})" if new else WINDOW_TITLE)

    def show_mine(self, role: str) -> None:
        """Badge click: open MRs where the user has this role, which become seen (BA-02, AM-04)."""
        me = self.me_key()
        if me is None:
            return
        if role != AUTHOR:
            keys = seen_on_click(self.my_mrs, self._seen, role)
            self._new_at_click = {(p, i) for p, i, _ in keys}
            self.store.mark_seen(keys)
            self._seen |= keys
            self._update_badges()
        self.notebook.select(self.mr_tab)
        self.filters.show_mine(role, me)

    def show_merge_request(self, ev: Evaluation) -> None:
        """A merge clicked on the overview: that MR selected in the Merge Requests tab (VE-14)."""
        merged = to_local(ev.mr.merged_at) if ev.mr.merged_at else now_local()
        self.mr_tab.focus_mr(ev.mr.project_id, ev.mr.iid, merged.date())
        self.notebook.select(self.mr_tab)

    def _open_merge_requests(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.notebook.select(self.mr_tab)

    def _score_level(self, score: float) -> str:
        s = self.settings
        return score_level(round(score, 6), s.green_threshold, s.orange_threshold)

    def _score_colors(self, score: float) -> tuple[str, str]:
        """(background, foreground) of a score's level, with the configured thresholds."""
        s = self.settings
        return self.get_theme().level_colors(score_level(round(score, 6), s.green_threshold, s.orange_threshold))

    def _open_notification_settings(self) -> None:
        """Gear of a desktop notification: Config tab, notification switches highlighted (NO-10)."""
        self.root.deiconify()
        self.root.lift()
        self.notebook.select(self.settings_tab)
        self.settings_tab.highlight_notifications()

    def apply_settings(self, new: Settings) -> None:
        """Save new settings and rebuild whatever depends on them."""
        connection_changed = (new.gitlab_url, new.token, new.verify_ssl) != (
            self.settings.gitlab_url, self.settings.token, self.settings.verify_ssl)
        theme_changed = new.theme != self.settings.theme
        new.filters = self.filters.to_settings()
        new.column_widths = self.settings.column_widths
        # Filters remembered by the tabs since the Config form was loaded.
        new.branch_filters, new.tag_filters = self.settings.branch_filters, self.settings.tag_filters
        new.tags_view, new.tag_compares = self.settings.tags_view, self.settings.tag_compares
        new.stats_view, new.config_view = self.settings.stats_view, self.settings.config_view
        url_changed = new.gitlab_url.rstrip("/") != self.settings.gitlab_url.rstrip("/")
        self.settings = new
        self._save()
        if url_changed:  # the base belongs to one instance (CH-10)
            self.store.clear()
            if new.gitlab_url:
                self.store.set_meta("instance_url", new.gitlab_url.rstrip("/"))
        self._build_services()
        if connection_changed:
            self.data.new_session()
            self._new_at_click.clear()
        valid = {p.id for p in new.projects}
        self.filters.repos = [r for r in self.filters.repos if r in valid]
        if theme_changed:
            self.theme = get_theme(new.theme)
            apply_theme(self.root, self.theme)
            self.banner.restyle()
            for badge in self._badge_list:
                badge.redraw()
            self.tab_bar.restyle()
            for tab in (self.overview_tab, self.mr_tab, self.branches_tab, self.tags_tab, self.stats_tab):
                tab.restyle()
        self.mr_tab.update_columns()
        self.stats_tab.update_columns()
        self._update_repo_items()
        self.settings_tab.reset()
        for tab in (self.mr_tab, self.branches_tab, self.tags_tab, self.stats_tab):
            tab.dirty = True
        self.overview_tab.settings_changed()
        self._update_badges()
        # Token, repositories or period may have changed: token owner and own MRs again.
        self.sync()

    def clear_store(self) -> None:
        """Delete every stored row and reload from GitLab (OC-09)."""
        self.store.clear()
        if self.settings.gitlab_url:
            self.store.set_meta("instance_url", self.settings.gitlab_url.rstrip("/"))
        self.my_mrs, self._seen = [], set()
        self.stats_tab.forget_avatars()
        self.refresh()

    def toggle_fullscreen(self) -> None:
        """F11: full screen on / off, on the monitor holding the window (VE-02, VE-13)."""
        root = self.root
        if self._windowed is not None:  # leave full screen: borderless window back to its place
            geometry, state = self._windowed
            self._windowed = None
            root.overrideredirect(False)
            root.geometry(geometry)
            root.state(state)
            return
        area = monitor_area(root)
        if area is None:  # not Windows: Tk's own full screen
            root.attributes("-fullscreen", not bool(root.attributes("-fullscreen")))
            return
        self._windowed = (root.geometry(), root.state())
        left, top, right, bottom = area
        root.state("normal")
        root.overrideredirect(True)
        root.geometry(f"{right - left}x{bottom - top}+{left}+{top}")
        root.lift()
        root.focus_force()

    def open_wizard(self) -> None:
        from gitective.ui.first_launch_wizard import Wizard  # local import: wizard imports App types

        Wizard(self)

    # ------------------------------------------------------------ Internal

    def _save(self) -> None:
        try:
            config.save(self.settings)
        except OSError as exc:
            self.notify("error", t("Impossible d'écrire config.json : {error}", error=exc))

    def _update_repo_items(self) -> None:
        for tab in (self.mr_tab, self.branches_tab, self.tags_tab, self.stats_tab):
            tab.update_repo_items()

    def select_tab(self, tab: tk.Widget) -> None:
        self.notebook.select(tab)

    def _tab_changed(self) -> None:
        index = self.notebook.index("current")
        settings_index = self.notebook.index(self.settings_tab)
        leaving = self._current_tab == settings_index and index != settings_index
        if leaving and self.settings_tab.has_changes():  # OC-17
            choice = ask_unsaved(self.root, self, self.settings_tab.change_count(), self.settings_tab.changed_pages())
            if choice == "stay" or (choice == "save" and not self.settings_tab.save()):
                self.notebook.select(self.settings_tab)
                return
            if choice == "discard":
                self.settings_tab.reset()
        self._current_tab = index
        self.tab_bar.select(index)
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
