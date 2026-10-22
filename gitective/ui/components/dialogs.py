"""Dialogs of the Config tab: custom rule, repository picker, person (RP-01, SD-02, PE-01)."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.shared.i18n import t
from gitective.forge.gitlab_client import GitLabClient
from gitective.forge.models import Project, User
from gitective.settings.config_file import RULE_FIELDS, RULE_MODES, CustomRule, Person, TrackedProject
from gitective.shared.dates import format_datetime, now_local
from gitective.database.project_list import load_cached, save_cached
from gitective.review.rules import validate_regex
from gitective.review.settings_form import group_error
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
        self.title(t("Règle personnalisée"))
        self.geometry("560x430")
        self.transient(master.winfo_toplevel())
        self.configure(background=app.get_theme().bg)
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self.name = tk.StringVar(value=rule.name)
        # Labels in the interface language; the rule stores the keys (RP-02).
        self._fields = {key: t(label) for key, label in RULE_FIELDS.items()}
        self._modes = {key: t(label) for key, label in RULE_MODES.items()}
        self.field_label = tk.StringVar(value=self._fields.get(rule.field, self._fields["title"]))
        self.pattern = tk.StringVar(value=rule.pattern)
        self.mode_label = tk.StringVar(value=self._modes.get(rule.mode, self._modes["match"]))
        self.weight = tk.StringVar(value=f"{rule.weight:g}")
        self.group = tk.StringVar(value=str(rule.group))
        self.active = tk.BooleanVar(value=rule.active)

        rows: list[tuple[str, tk.Widget]] = [
            (t("Nom (titre de colonne)"), ttk.Entry(frame, textvariable=self.name)),
            (t("Champ inspecté"), ttk.Combobox(frame, textvariable=self.field_label, state="readonly",
                                               values=list(self._fields.values()))),
            (t("Condition"), ttk.Combobox(frame, textvariable=self.mode_label, state="readonly",
                                          values=list(self._modes.values()))),
            (t("Regex"), ttk.Entry(frame, textvariable=self.pattern, font=app.get_theme().mono)),
            (t("Groupe à récupérer"), ttk.Spinbox(frame, from_=0, to=99, textvariable=self.group, width=6)),
            (t("Pondération"), ttk.Entry(frame, textvariable=self.weight, width=8)),
        ]
        for line, (label, widget) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=line, column=0, sticky="w", pady=6, padx=(0, 12))
            widget.grid(row=line, column=1, sticky="w" if line >= len(rows) - 2 else "ew", pady=6)
        ttk.Checkbutton(frame, text=t("Active"), variable=self.active).grid(row=len(rows), column=1, sticky="w")
        self._hint = ttk.Label(frame, style="Muted.TLabel", wraplength=470)
        self._hint.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.field_label.trace_add("write", lambda *_: self._update_hint())
        self._update_hint()

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="se", pady=(16, 0))
        frame.rowconfigure(len(rows) + 2, weight=1)
        ttk.Button(buttons, text=t("Annuler"), command=self.destroy).pack(side="left", padx=8)
        ttk.Button(buttons, text=t("OK"), style="Accent.TButton", command=self._validate).pack(side="left")

    def _update_hint(self) -> None:
        if self.field_label.get() == self._fields["commits"]:
            self._hint.configure(text=t("Tous les commits de la MR doivent respecter la condition. "
                                      "Coût : une requête GitLab de plus par MR."))
        else:
            self._hint.configure(text=t("La regex est cherchée n'importe où dans le champ "
                                      "(utilisez ^ et $ pour l'ancrer). Groupe à récupérer : 0 = toute la "
                                      "correspondance, sinon le n° du groupe capturant ; la valeur s'affiche "
                                      "dans le testeur."))

    def _validate(self) -> None:
        name = self.name.get().strip()
        if not name:
            self.app.notify("error", t("Le nom de la règle est obligatoire."))
            return
        error = validate_regex(self.pattern.get())
        if error:
            self.app.notify("error", t("Regex invalide : {error}", error=error))
            return
        group = self.group.get().strip()
        error = group_error(self.pattern.get(), group)
        if error:
            self.app.notify("error", t("Regex : {error}", error=error))
            return
        try:
            weight = float(self.weight.get().replace(",", "."))
            if weight < 0:
                raise ValueError
        except ValueError:
            self.app.notify("error", t("Pondération : saisissez un nombre positif."))
            return
        fields = {v: k for k, v in self._fields.items()}
        modes = {v: k for k, v in self._modes.items()}
        self._on_done(CustomRule(name=name, field=fields[self.field_label.get()], pattern=self.pattern.get(),
                                 mode=modes[self.mode_label.get()], weight=weight, active=self.active.get(),
                                 id=self._rule.id, group=int(group)))
        self.destroy()


class ProjectsDialog(tk.Toplevel):
    """Lists the projects visible to the token so the user ticks those to track.

    The list comes from the local store when present (SD-04); "Recharger la
    liste" reads it again from GitLab and updates the store.
    """

    def __init__(self, master: tk.Misc, app: App, client: GitLabClient, tracked: list[TrackedProject],
                 on_done: Callable[[list[Project]], None]) -> None:
        super().__init__(master)
        self.title(t("Choisir les dépôts"))
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
        self._reload_button = ttk.Button(top, text=t("⟳  Recharger la liste"), command=self._reload)
        self._reload_button.pack(side="right")
        self.picker = ProjectPicker(self, app.get_theme)
        self.picker.pack(fill="both", expand=True, padx=12)
        buttons = ttk.Frame(self, padding=12)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=t("Valider"), style="Accent.TButton", command=self._validate).pack(side="right")
        ttk.Button(buttons, text=t("Annuler"), command=self.destroy).pack(side="right", padx=8)
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
        self._status.configure(text=t("{count} projet(s) accessible(s) — liste du {date}", count=len(projects), date=saved_at))
        self.picker.set_projects([(p.id, p.path_with_namespace) for p in projects], self._checked)

    def _reload(self) -> None:
        if self._projects:
            self._checked = self.picker.checked()  # keep ticks made before reloading
        self._status.configure(text=t("Chargement des projets…"))
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
        self.title(t("Personne"))
        self.geometry("640x560")
        self.transient(master.winfo_toplevel())
        self.configure(background=theme.bg)
        self._accounts: list[int] = list(person.account_ids)
        self._available: list[User] = sorted(app.known_users.values(), key=lambda u: u.name.casefold())

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=t("Nom affiché")).pack(anchor="w")
        self.name = tk.StringVar(value=person.name)
        ttk.Entry(frame, textvariable=self.name).pack(fill="x", pady=(2, 10))

        ttk.Label(frame, text=t("Comptes GitLab")).pack(anchor="w")
        search_row = ttk.Frame(frame)
        search_row.pack(fill="x", pady=(2, 4))
        self.query = tk.StringVar()
        search = ttk.Entry(search_row, textvariable=self.query)
        search.pack(side="left", fill="x", expand=True)
        search.bind("<Return>", lambda e: self._search())
        ttk.Button(search_row, text=t("Rechercher sur GitLab"), command=self._search).pack(side="left", padx=(6, 0))
        lists = ttk.Frame(frame)
        lists.pack(fill="both", expand=True)
        lists.columnconfigure((0, 2), weight=1)
        lists.rowconfigure(1, weight=1)
        ttk.Label(lists, text=t("Disponibles"), style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(lists, text=t("Associés à la personne"), style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self.available_list = tk.Listbox(lists, selectmode="extended", height=8, exportselection=False)
        self.chosen_list = tk.Listbox(lists, selectmode="extended", height=8, exportselection=False)
        self.available_list.grid(row=1, column=0, sticky="nsew")
        self.chosen_list.grid(row=1, column=2, sticky="nsew")
        middle = ttk.Frame(lists)
        middle.grid(row=1, column=1, padx=8)
        ttk.Button(middle, text=t("Ajouter →"), command=self._add).pack(pady=4)
        ttk.Button(middle, text=t("← Retirer"), command=self._remove).pack(pady=4)

        ttk.Label(frame, text=t("Identités Git pour les commits (nom ou e-mail, une par ligne)")).pack(anchor="w", pady=(10, 2))
        self.identities = tk.Text(frame, height=4, relief="solid", borderwidth=1)
        self.identities.insert("1.0", "\n".join(person.git_identities))
        self.identities.pack(fill="x")
        for widget in (self.available_list, self.chosen_list, self.identities):
            widget.configure(background=theme.surface, foreground=theme.text, selectbackground=theme.accent,
                             selectforeground=theme.accent_text, font=theme.font)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text=t("OK"), style="Accent.TButton", command=self._validate).pack(side="right")
        ttk.Button(buttons, text=t("Annuler"), command=self.destroy).pack(side="right", padx=8)
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
            self.app.notify("error", t("Le nom de la personne est obligatoire."))
            return
        identities = [line.strip() for line in self.identities.get("1.0", "end").splitlines() if line.strip()]
        self._on_done(Person(name=name, account_ids=self._accounts, git_identities=identities))
        self.destroy()


def ask_unsaved(master: tk.Misc, app: App, count: int, pages: str) -> str:
    """Leaving Config with pending changes (OC-17): "save", "discard" or "stay"."""
    theme = app.get_theme()
    window = tk.Toplevel(master)
    window.title(t("Modifications non enregistrées"))
    window.transient(master.winfo_toplevel())
    window.configure(background=theme.bg)
    window.resizable(False, False)
    answer = {"value": "stay"}
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=t("{count} modification(s) non enregistrée(s) dans Config", count=count),
              font=(theme.font[0], theme.font[1] + 2, "bold")).pack(anchor="w")
    ttk.Label(frame, text=t("Sous-onglets concernés : {pages}.", pages=pages), wraplength=420,
              justify="left").pack(anchor="w", pady=(8, 14))
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")

    def choose(value: str) -> None:
        answer["value"] = value
        window.destroy()

    ttk.Button(buttons, text=t("Enregistrer"), style="Accent.TButton", command=lambda: choose("save")).pack(side="right")
    ttk.Button(buttons, text=t("Ignorer les modifications"), command=lambda: choose("discard")).pack(side="right", padx=8)
    stay = ttk.Button(buttons, text=t("Rester dans Config"), command=lambda: choose("stay"))
    stay.pack(side="right")
    window.bind("<Escape>", lambda e: choose("stay"))
    window.protocol("WM_DELETE_WINDOW", lambda: choose("stay"))
    window.update_idletasks()
    top = master.winfo_toplevel()
    x = top.winfo_rootx() + (top.winfo_width() - window.winfo_reqwidth()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - window.winfo_reqheight()) // 3
    window.geometry(f"+{max(0, x)}+{max(0, y)}")
    stay.focus_set()
    window.grab_set()
    window.wait_window()
    return answer["value"]
