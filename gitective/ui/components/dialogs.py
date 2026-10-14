"""Dialogs of the Config tab: custom rule, repository picker, person (RP-01, SD-02, PE-01)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.forge.gitlab_client import GitLabClient
from gitective.forge.models import Project, User
from gitective.settings.config_file import RULE_FIELDS, RULE_MODES, CustomRule, Person, TrackedProject
from gitective.shared.dates import format_datetime, now_local
from gitective.database.project_list import load_cached, save_cached
from gitective.review.rules import validate_regex
from gitective.ui.components.widgets import ProjectPicker

if TYPE_CHECKING:
    from gitective.ui.app import App


class RuleDialog(tk.Toplevel):
    """Create or edit a custom rule: name, field, regex, condition, weight (RP-01)."""

    def __init__(self, master: tk.Misc, app: App, rule: CustomRule, on_done: Callable[[CustomRule], None]) -> None:
        super().__init__(master)
        self.app = app
        self._rule = rule
        self._on_done = on_done
        self.title("Règle personnalisée")
        self.geometry("520x380")
        self.transient(master.winfo_toplevel())
        self.configure(background=app.get_theme().bg)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self.name = tk.StringVar(value=rule.name)
        self.field_label = tk.StringVar(value=RULE_FIELDS.get(rule.field, RULE_FIELDS["title"]))
        self.pattern = tk.StringVar(value=rule.pattern)
        self.mode_label = tk.StringVar(value=RULE_MODES.get(rule.mode, RULE_MODES["match"]))
        self.weight = tk.StringVar(value=f"{rule.weight:g}")
        self.active = tk.BooleanVar(value=rule.active)

        rows: list[tuple[str, tk.Widget]] = [
            ("Nom (titre de colonne)", ttk.Entry(frame, textvariable=self.name)),
            ("Champ inspecté", ttk.Combobox(frame, textvariable=self.field_label, state="readonly",
                                            values=list(RULE_FIELDS.values()))),
            ("Condition", ttk.Combobox(frame, textvariable=self.mode_label, state="readonly",
                                       values=list(RULE_MODES.values()))),
            ("Regex", ttk.Entry(frame, textvariable=self.pattern, font=app.get_theme().mono)),
            ("Pondération", ttk.Entry(frame, textvariable=self.weight, width=8)),
        ]
        for line, (label, widget) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=line, column=0, sticky="w", pady=6, padx=(0, 12))
            widget.grid(row=line, column=1, sticky="ew" if label != "Pondération" else "w", pady=6)
        ttk.Checkbutton(frame, text="Active", variable=self.active).grid(row=len(rows), column=1, sticky="w")
        self._hint = ttk.Label(frame, style="Muted.TLabel", wraplength=470)
        self._hint.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.field_label.trace_add("write", lambda *_: self._update_hint())
        self._update_hint()

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="se", pady=(16, 0))
        frame.rowconfigure(len(rows) + 2, weight=1)
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="left", padx=8)
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self._validate).pack(side="left")

    def _update_hint(self) -> None:
        if self.field_label.get() == RULE_FIELDS["commits"]:
            self._hint.configure(text="Tous les commits de la MR doivent respecter la condition. "
                                      "Coût : une requête GitLab de plus par MR.")
        else:
            self._hint.configure(text="La regex est cherchée n'importe où dans le champ "
                                      "(utilisez ^ et $ pour l'ancrer).")

    def _validate(self) -> None:
        name = self.name.get().strip()
        if not name:
            self.app.notify("error", "Le nom de la règle est obligatoire.")
            return
        error = validate_regex(self.pattern.get())
        if error:
            self.app.notify("error", f"Regex invalide : {error}")
            return
        try:
            weight = float(self.weight.get().replace(",", "."))
            if weight < 0:
                raise ValueError
        except ValueError:
            self.app.notify("error", "Pondération : saisissez un nombre positif.")
            return
        fields = {v: k for k, v in RULE_FIELDS.items()}
        modes = {v: k for k, v in RULE_MODES.items()}
        self._on_done(CustomRule(name=name, field=fields[self.field_label.get()], pattern=self.pattern.get(),
                                 mode=modes[self.mode_label.get()], weight=weight, active=self.active.get(),
                                 id=self._rule.id))
        self.destroy()


class ProjectsDialog(tk.Toplevel):
    """Lists the projects visible to the token so the user ticks those to track.

    The list comes from the local store when present (SD-04); "Recharger la
    liste" reads it again from GitLab and updates the store.
    """

    def __init__(self, master: tk.Misc, app: App, client: GitLabClient, tracked: list[TrackedProject],
                 on_done: Callable[[list[Project]], None]) -> None:
        super().__init__(master)
        self.title("Choisir les dépôts")
        self.geometry("520x560")
        self.transient(master.winfo_toplevel())
        self.configure(background=app.get_theme().bg)
        self._app, self._client = app, client
        self._projects: list[Project] = []
        self._on_done = on_done
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 4))
        self._status = ttk.Label(top)
        self._status.pack(side="left")
        self._reload_button = ttk.Button(top, text="⟳  Recharger la liste", command=self._reload)
        self._reload_button.pack(side="right")
        self.picker = ProjectPicker(self, app.get_theme)
        self.picker.pack(fill="both", expand=True, padx=12)
        buttons = ttk.Frame(self, padding=12)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Valider", style="Accent.TButton", command=self._validate).pack(side="right")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right", padx=8)
        self._checked = [p.id for p in tracked]

        # The store belongs to the configured instance: another URL typed in the form is read from GitLab.
        self._use_store = client.base_url.rstrip("/") == app.settings.gitlab_url.rstrip("/")
        cached = load_cached(app.store) if self._use_store else None
        if cached:
            self._show(*cached)
        else:
            self._reload()

    def _show(self, projects: list[Project], saved_at: str) -> None:
        self._projects = projects
        self._status.configure(text=f"{len(projects)} projet(s) accessible(s) — liste du {saved_at}")
        self.picker.set_projects([(p.id, p.path_with_namespace) for p in projects], self._checked)

    def _reload(self) -> None:
        if self._projects:
            self._checked = self.picker.checked()  # keep ticks made before reloading
        self._status.configure(text="Chargement des projets…")
        self._reload_button.state(["disabled"])
        client, workers, store = self._client, self._app.settings.parallel_requests, self._app.store
        use_store = self._use_store

        def task(_progress: object) -> tuple[list[Project], str]:
            projects = client.list_projects(workers=workers)
            if use_store:
                return projects, save_cached(store, projects)
            return projects, format_datetime(now_local())

        def loaded(result: tuple[list[Project], str]) -> None:
            if self.winfo_exists():
                self._reload_button.state(["!disabled"])
                self._show(*result)

        def failed(exc: BaseException) -> None:
            if self.winfo_exists():
                self.destroy()
            self._app.report_error(exc)

        self._app.runner.run("projects", task, loaded, failed)

    def _validate(self) -> None:
        chosen = set(self.picker.checked())
        self._on_done([p for p in self._projects if p.id in chosen])
        self.destroy()


class PersonDialog(tk.Toplevel):
    """Create or edit a person: name, GitLab accounts, Git identities (PE-01..PE-03)."""

    def __init__(self, master: tk.Misc, app: App, person: Person, on_done: Callable[[Person], None]) -> None:
        super().__init__(master)
        self.app = app
        self._on_done = on_done
        theme = app.get_theme()
        self.title("Personne")
        self.geometry("640x560")
        self.transient(master.winfo_toplevel())
        self.configure(background=theme.bg)
        self._accounts: list[int] = list(person.account_ids)
        self._available: list[User] = sorted(app.known_users.values(), key=lambda u: u.name.casefold())

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Nom affiché").pack(anchor="w")
        self.name = tk.StringVar(value=person.name)
        ttk.Entry(frame, textvariable=self.name).pack(fill="x", pady=(2, 10))

        ttk.Label(frame, text="Comptes GitLab").pack(anchor="w")
        search_row = ttk.Frame(frame)
        search_row.pack(fill="x", pady=(2, 4))
        self.query = tk.StringVar()
        search = ttk.Entry(search_row, textvariable=self.query)
        search.pack(side="left", fill="x", expand=True)
        search.bind("<Return>", lambda e: self._search())
        ttk.Button(search_row, text="Rechercher sur GitLab", command=self._search).pack(side="left", padx=(6, 0))
        lists = ttk.Frame(frame)
        lists.pack(fill="both", expand=True)
        lists.columnconfigure((0, 2), weight=1)
        lists.rowconfigure(1, weight=1)
        ttk.Label(lists, text="Disponibles", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(lists, text="Associés à la personne", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self.available_list = tk.Listbox(lists, selectmode="extended", height=8, exportselection=False)
        self.chosen_list = tk.Listbox(lists, selectmode="extended", height=8, exportselection=False)
        self.available_list.grid(row=1, column=0, sticky="nsew")
        self.chosen_list.grid(row=1, column=2, sticky="nsew")
        middle = ttk.Frame(lists)
        middle.grid(row=1, column=1, padx=8)
        ttk.Button(middle, text="Ajouter →", command=self._add).pack(pady=4)
        ttk.Button(middle, text="← Retirer", command=self._remove).pack(pady=4)

        ttk.Label(frame, text="Identités Git pour les commits (nom ou e-mail, une par ligne)").pack(anchor="w", pady=(10, 2))
        self.identities = tk.Text(frame, height=4, relief="solid", borderwidth=1)
        self.identities.insert("1.0", "\n".join(person.git_identities))
        self.identities.pack(fill="x")
        for widget in (self.available_list, self.chosen_list, self.identities):
            widget.configure(background=theme.surface, foreground=theme.text, selectbackground=theme.accent,
                             selectforeground=theme.accent_text, font=theme.font)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self._validate).pack(side="right")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right", padx=8)
        self._refresh_lists()

    def _label(self, user_id: int) -> str:
        user = self.app.known_users.get(user_id) or next((u for u in self._available if u.id == user_id), None)
        return f"#{user.id}  {user.username}  ({user.name})" if user else f"#{user_id}"

    def _refresh_lists(self) -> None:
        self.available_list.delete(0, "end")
        self._shown = [u for u in self._available if u.id not in self._accounts]
        for user in self._shown:
            self.available_list.insert("end", self._label(user.id))
        self.chosen_list.delete(0, "end")
        for account in self._accounts:
            self.chosen_list.insert("end", self._label(account))

    def _search(self) -> None:
        query = self.query.get().strip()
        client = self.app.client
        if not query or client is None:
            return

        def done(users: list[User]) -> None:
            if not self.winfo_exists():
                return
            self.app.remember_users(users)
            self._available = users
            self._refresh_lists()

        self.app.runner.run("user-search", lambda _p: client.search_users(query), done, self.app.report_error)

    def _add(self) -> None:
        for index in self.available_list.curselection():
            self._accounts.append(self._shown[index].id)
        self._refresh_lists()

    def _remove(self) -> None:
        for index in sorted(self.chosen_list.curselection(), reverse=True):
            del self._accounts[index]
        self._refresh_lists()

    def _validate(self) -> None:
        name = self.name.get().strip()
        if not name:
            self.app.notify("error", "Le nom de la personne est obligatoire.")
            return
        identities = [line.strip() for line in self.identities.get("1.0", "end").splitlines() if line.strip()]
        self._on_done(Person(name=name, account_ids=self._accounts, git_identities=identities))
        self.destroy()
