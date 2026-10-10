"""Config tab: connection, theme, rules, regex tester, repositories, people (OC-01..OC-08)."""

from __future__ import annotations

import copy
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.api.client import GitLabClient
from gitective.api.models import Project, User
from gitective.config.settings import (
    FIXED_CRITERIA,
    RULE_FIELDS,
    RULE_MODES,
    CustomRule,
    Person,
    Settings,
    TrackedProject,
)
from gitective.core.avatars import badge_color, initials
from gitective.core.rules import FIXED_LABELS, MrFields, RuleSet, validate_regex
from gitective.ui.themes import THEMES
from gitective.ui.widgets import ProjectPicker, ScrollableFrame

if TYPE_CHECKING:
    from gitective.ui.app import App

AVATAR_PX = 30


class SettingsTab(ttk.Frame):
    """Edits a draft copy of the settings; nothing is applied before Save."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.dirty = False
        self.draft: Settings = copy.deepcopy(app.settings)
        self._avatar_images: list[tk.PhotoImage] = []

        scroller = ScrollableFrame(self)
        scroller.pack(fill="both", expand=True)
        self._scroller = scroller
        body = scroller.inner
        body.columnconfigure((0, 1, 2), weight=1, uniform="col")
        columns = [ttk.Frame(body) for _ in range(3)]
        for index, column in enumerate(columns):
            column.grid(row=0, column=index, sticky="nsew", padx=8, pady=12)

        self._build_connection(columns[0])
        self._build_theme(columns[0])
        self._build_rules(columns[1])
        self._build_tester(columns[1])
        self._build_projects(columns[2])
        self._build_people(columns[2])

        actions = ttk.Frame(self, padding=(16, 10))
        actions.pack(fill="x", side="bottom")
        ttk.Button(actions, text="Enregistrer", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(actions, text="Annuler", command=self.reset).pack(side="right", padx=8)
        self.reset()

    # ------------------------------------------------------------ Sections

    def _section(self, parent: tk.Misc, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=12)
        frame.pack(fill="x", pady=(0, 12))
        return frame

    def _labeled_entry(self, parent: tk.Misc, label: str, var: tk.StringVar, **options: object) -> ttk.Entry:
        ttk.Label(parent, text=label, style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        entry = ttk.Entry(parent, textvariable=var, **options)  # type: ignore[arg-type]
        entry.pack(fill="x")
        return entry

    def _build_connection(self, parent: tk.Misc) -> None:
        box = self._section(parent, "Connexion GitLab")
        self.url = tk.StringVar()
        self.token = tk.StringVar()
        self.verify_ssl = tk.BooleanVar()
        self._labeled_entry(box, "URL de l'instance", self.url)
        ttk.Label(box, text="Token personnel (droit read_api)", style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x")
        self._token_entry = ttk.Entry(row, textvariable=self.token, show="•")
        self._token_entry.pack(side="left", fill="x", expand=True)
        self._show_button = ttk.Button(row, text="Afficher", command=self._toggle_token)
        self._show_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(box, text="Vérifier le certificat SSL", variable=self.verify_ssl).pack(anchor="w", pady=8)
        ttk.Button(box, text="Tester la connexion", command=self._test_connection).pack(anchor="w")

    def _build_theme(self, parent: tk.Misc) -> None:
        box = self._section(parent, "Thème")
        self.theme = tk.StringVar()
        for key, theme in THEMES.items():
            ttk.Radiobutton(box, text=theme.label, value=key, variable=self.theme).pack(anchor="w", pady=2)
        ttk.Button(box, text="Relancer l'assistant de démarrage", command=self.app.open_wizard).pack(anchor="w", pady=(10, 0))

    def _build_rules(self, parent: tk.Misc) -> None:
        box = self._section(parent, "Règles personnalisées")
        ttk.Button(box, text="+ Règle", command=lambda: self._edit_rule(None)).pack(anchor="w")
        self._rules_frame = ttk.Frame(box, style="Surface.TFrame")
        self._rules_frame.pack(fill="x", pady=(8, 0))

        fixed = self._section(parent, "Correspondance ticket et règles fixes")
        self.link_regex = tk.StringVar()
        self.ticket_regex = tk.StringVar()
        mono = self.app.get_theme().mono
        self._labeled_entry(fixed, "Regex du lien ticket (dans la description)", self.link_regex, font=mono)
        self._labeled_entry(fixed, "Regex du n° de ticket", self.ticket_regex, font=mono)
        for var in (self.link_regex, self.ticket_regex):
            var.trace_add("write", lambda *_: self._run_tester())
        ttk.Label(fixed, text="Pondérations", style="BarMuted.TLabel").pack(anchor="w", pady=(12, 2))
        weights = ttk.Frame(fixed, style="Surface.TFrame")
        weights.pack(fill="x")
        self.weights = {c: tk.StringVar() for c in FIXED_CRITERIA}
        for index, criterion in enumerate(FIXED_CRITERIA):
            cell = ttk.Frame(weights, style="Surface.TFrame")
            cell.grid(row=0, column=index, sticky="ew", padx=(0, 8))
            weights.columnconfigure(index, weight=1)
            ttk.Label(cell, text=FIXED_LABELS[criterion], style="BarMuted.TLabel").pack(anchor="w")
            ttk.Entry(cell, textvariable=self.weights[criterion], width=6).pack(fill="x")
        ttk.Label(fixed, text="Seuils du score (%)", style="BarMuted.TLabel").pack(anchor="w", pady=(12, 2))
        thresholds = ttk.Frame(fixed, style="Surface.TFrame")
        thresholds.pack(fill="x")
        self.green = tk.StringVar()
        self.orange = tk.StringVar()
        ttk.Label(thresholds, text="Vert ≥", style="Bar.TLabel").pack(side="left")
        ttk.Entry(thresholds, textvariable=self.green, width=6).pack(side="left", padx=(4, 14))
        ttk.Label(thresholds, text="Orange ≥", style="Bar.TLabel").pack(side="left")
        ttk.Entry(thresholds, textvariable=self.orange, width=6).pack(side="left", padx=4)
        ttk.Label(thresholds, text="sinon rouge", style="BarMuted.TLabel").pack(side="left", padx=6)

    def _build_tester(self, parent: tk.Misc) -> None:
        box = self._section(parent, "Testeur de règles")
        self.sample_title = tk.StringVar()
        self.sample_source = tk.StringVar()
        self.sample_target = tk.StringVar()
        self._labeled_entry(box, "Titre", self.sample_title)
        branches = ttk.Frame(box, style="Surface.TFrame")
        branches.pack(fill="x")
        branches.columnconfigure((0, 1), weight=1)
        for column, (label, var) in enumerate((("Branche source", self.sample_source),
                                               ("Branche cible", self.sample_target))):
            cell = ttk.Frame(branches, style="Surface.TFrame")
            cell.grid(row=0, column=column, sticky="ew", padx=(0, 6) if column == 0 else 0)
            self._labeled_entry(cell, label, var)
        for var in (self.sample_title, self.sample_source, self.sample_target):
            var.trace_add("write", lambda *_: self._run_tester())
        self.sample_description = self._sample_text(box, "Description", 3)
        self.sample_commits = self._sample_text(box, "Messages de commits (un par ligne)", 3)
        self._results = ttk.Frame(box, style="Surface.TFrame")
        self._results.pack(fill="x", pady=(10, 0))

    def _sample_text(self, parent: tk.Misc, label: str, height: int) -> tk.Text:
        ttk.Label(parent, text=label, style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        text = tk.Text(parent, height=height, wrap="word", relief="solid", borderwidth=1)
        text.pack(fill="x")
        text.bind("<KeyRelease>", lambda e: self._run_tester())
        return text

    def _build_projects(self, parent: tk.Misc) -> None:
        box = self._section(parent, "Dépôts suivis et branche contrôlée")
        ttk.Button(box, text="Choisir les dépôts…", command=self._choose_projects).pack(anchor="w")
        self._projects_frame = ttk.Frame(box, style="Surface.TFrame")
        self._projects_frame.pack(fill="x", pady=(8, 0))
        self._branch_vars: dict[int, tk.StringVar] = {}

    def _build_people(self, parent: tk.Misc) -> None:
        box = self._section(parent, "Personnes et comptes")
        ttk.Button(box, text="+ Personne", command=lambda: self._edit_person(None)).pack(anchor="w")
        self._people_frame = ttk.Frame(box, style="Surface.TFrame")
        self._people_frame.pack(fill="x", pady=(8, 0))

    # ---------------------------------------------------------- Draft I/O

    def reset(self) -> None:
        """Reload the form from the saved settings (Cancel)."""
        self.draft = copy.deepcopy(self.app.settings)
        d = self.draft
        self.url.set(d.gitlab_url)
        self.token.set(d.token)
        self.verify_ssl.set(d.verify_ssl)
        self.theme.set(d.theme)
        self.link_regex.set(d.link_regex)
        self.ticket_regex.set(d.ticket_regex)
        for criterion, var in self.weights.items():
            var.set(_fmt(d.weights.get(criterion, 0)))
        self.green.set(_fmt(d.green_threshold))
        self.orange.set(_fmt(d.orange_threshold))
        self._render_rules()
        self._render_projects()
        self._render_people()
        self._run_tester()

    def _collect(self) -> tuple[Settings | None, str]:
        """Build settings from the form; return (None, error) when invalid."""
        d = copy.deepcopy(self.draft)
        d.gitlab_url = self.url.get().strip()
        d.token = self.token.get().strip()
        d.verify_ssl = self.verify_ssl.get()
        d.theme = self.theme.get()
        d.link_regex = self.link_regex.get()
        d.ticket_regex = self.ticket_regex.get()
        checks = [(f"de la règle « {r.name} »", r.pattern) for r in d.rules]
        checks += [("du lien ticket", d.link_regex), ("du n° de ticket", d.ticket_regex)]
        for label, pattern in checks:
            error = validate_regex(pattern)
            if error:
                return None, f"Regex {label} invalide : {error}. Enregistrement annulé."
        try:
            d.weights = {c: float(v.get().replace(",", ".")) for c, v in self.weights.items()}
            d.green_threshold = float(self.green.get().replace(",", "."))
            d.orange_threshold = float(self.orange.get().replace(",", "."))
        except ValueError:
            return None, "Pondérations et seuils : saisissez des nombres."
        all_weights = [*d.weights.values(), *(r.weight for r in d.active_rules)]
        if any(w < 0 for w in all_weights) or sum(all_weights) <= 0:
            return None, "Pondérations : valeurs positives avec un total supérieur à 0."
        if not 0 <= d.orange_threshold <= d.green_threshold <= 100:
            return None, "Seuils : il faut 0 ≤ orange ≤ vert ≤ 100."
        for project in d.projects:
            project.branch = self._branch_vars[project.id].get().strip() if project.id in self._branch_vars else project.branch
        return d, ""

    def _save(self) -> None:
        settings, error = self._collect()
        if settings is None:
            self.app.notify("error", error)
            return
        self.app.apply_settings(settings)
        self.draft = copy.deepcopy(settings)
        self.app.notify("success", "Configuration enregistrée.")

    # --------------------------------------------------------- Connection

    def _toggle_token(self) -> None:
        hidden = self._token_entry.cget("show") != ""
        self._token_entry.configure(show="" if hidden else "•")
        self._show_button.configure(text="Masquer" if hidden else "Afficher")

    def _form_client(self) -> GitLabClient | None:
        if not self.url.get().strip() or not self.token.get().strip():
            self.app.notify("error", "Renseignez l'URL de l'instance et le token.")
            return None
        return GitLabClient(self.url.get().strip(), self.token.get().strip(), verify_ssl=self.verify_ssl.get())

    def _test_connection(self) -> None:
        client = self._form_client()
        if client is None:
            return

        def done(user: User) -> None:
            self.app.notify("success", f"Connexion réussie : connecté en tant que {user.username} ({user.name}).")

        self.app.runner.run("test", lambda _p: client.current_user(), done, self.app.report_error)

    # -------------------------------------------------------------- Tester

    def _run_tester(self) -> None:
        """Run the draft rules on the sample MR and show OK / KO (OC-06)."""
        if not hasattr(self, "_results"):
            return
        for child in self._results.winfo_children():
            child.destroy()
        patterns = [r.pattern for r in self.draft.rules] + [self.link_regex.get(), self.ticket_regex.get()]
        if any(validate_regex(p) for p in patterns):
            ttk.Label(self._results, text="Une regex est invalide.", style="Bar.TLabel").pack(anchor="w")
            return
        rules = RuleSet(self.draft.rules, self.link_regex.get(), self.ticket_regex.get(), {})
        commits = [line for line in self.sample_commits.get("1.0", "end").splitlines() if line.strip()]
        fields = MrFields(
            title=self.sample_title.get(),
            description=self.sample_description.get("1.0", "end"),
            source_branch=self.sample_source.get(),
            target_branch=self.sample_target.get(),
            commits=tuple((f"#{i}", message) for i, message in enumerate(commits, start=1)),
        )
        results = rules.check_fields(fields)
        theme = self.app.get_theme()
        labels = {c.id: c.label for c in rules.criteria}
        for criterion_id, result in results.items():
            row = ttk.Frame(self._results, style="Surface.TFrame")
            row.pack(fill="x", pady=1)
            bg, fg = theme.status_colors(result.status)
            tk.Label(row, text={"ok": "OK", "ko": "KO"}.get(result.status, "N/A"), background=bg, foreground=fg,
                     width=4, font=(theme.font[0], theme.font[1], "bold")).pack(side="left")
            text = labels.get(criterion_id, criterion_id)
            if result.detail:
                text += f" — {'n° extrait ' if result.status == 'ok' else ''}{result.detail}"
            ttk.Label(row, text=text, style="Bar.TLabel", wraplength=300).pack(side="left", padx=8)

    # --------------------------------------------------------------- Rules

    def _render_rules(self) -> None:
        for child in self._rules_frame.winfo_children():
            child.destroy()
        if not self.draft.rules:
            ttk.Label(self._rules_frame, text="Aucune règle personnalisée.", style="BarMuted.TLabel").pack(anchor="w")
        theme = self.app.get_theme()
        for index, rule in enumerate(self.draft.rules):
            row = ttk.Frame(self._rules_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=3)
            active = tk.BooleanVar(value=rule.active)
            ttk.Checkbutton(row, variable=active,
                            command=lambda r=rule, v=active: self._toggle_rule(r, v.get())).pack(side="left")
            ttk.Button(row, text="Suppr.", width=6, command=lambda i=index: self._delete_rule(i)).pack(side="right")
            ttk.Button(row, text="Modifier", command=lambda i=index: self._edit_rule(i)).pack(side="right", padx=4)
            text = ttk.Frame(row, style="Surface.TFrame")
            text.pack(side="left", fill="x", expand=True, padx=4)
            style = "Bar.TLabel" if rule.active else "BarMuted.TLabel"
            ttk.Label(text, text=rule.name, style=style, wraplength=220,
                      font=(theme.font[0], theme.font[1], "bold")).pack(anchor="w")
            mode = "≈" if rule.mode == "match" else "≠"
            detail = (f"{RULE_FIELDS.get(rule.field, rule.field)} {mode} {rule.pattern or '(regex à compléter)'}"
                      f"  ·  poids {rule.weight:g}")
            ttk.Label(text, text=detail, style="BarMuted.TLabel", font=theme.mono, wraplength=220).pack(anchor="w")

    def _toggle_rule(self, rule: CustomRule, active: bool) -> None:
        rule.active = active
        self._render_rules()
        self._run_tester()

    def _delete_rule(self, index: int) -> None:
        del self.draft.rules[index]
        self._render_rules()
        self._run_tester()

    def _edit_rule(self, index: int | None) -> None:
        rule = copy.deepcopy(self.draft.rules[index]) if index is not None else CustomRule(name="")

        def done(updated: CustomRule) -> None:
            if index is None:
                self.draft.rules.append(updated)
            else:
                self.draft.rules[index] = updated
            self._render_rules()
            self._run_tester()

        RuleDialog(self, self.app, rule, done)

    # ------------------------------------------------------------ Projects

    def _render_projects(self) -> None:
        for child in self._projects_frame.winfo_children():
            child.destroy()
        previous = {pid: var.get() for pid, var in self._branch_vars.items()}
        self._branch_vars = {}
        if not self.draft.projects:
            ttk.Label(self._projects_frame, text="Aucun dépôt suivi.", style="BarMuted.TLabel").pack(anchor="w")
        for project in self.draft.projects:
            row = ttk.Frame(self._projects_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=2)
            var = tk.StringVar(value=previous.get(project.id, project.branch))
            self._branch_vars[project.id] = var
            ttk.Label(row, text=project.path, style="Bar.TLabel").pack(side="left")
            ttk.Entry(row, textvariable=var, width=14, font=self.app.get_theme().mono).pack(side="right")

    def _choose_projects(self) -> None:
        client = self._form_client()
        if client is None:
            return
        ProjectsDialog(self, client, self.draft.projects, self._projects_chosen)

    def _projects_chosen(self, chosen: list[Project]) -> None:
        current = {p.id: p for p in self.draft.projects}
        for pid, var in self._branch_vars.items():
            if pid in current:
                current[pid].branch = var.get().strip()
        self.draft.projects = [
            current.get(p.id) or TrackedProject(id=p.id, path=p.path_with_namespace, web_url=p.web_url,
                                               branch=p.default_branch or "")
            for p in chosen
        ]
        self._render_projects()

    # -------------------------------------------------------------- People

    def _render_people(self) -> None:
        for child in self._people_frame.winfo_children():
            child.destroy()
        self._avatar_images.clear()
        theme = self.app.get_theme()
        if not self.draft.people:
            ttk.Label(self._people_frame, text="Aucune personne : chaque compte compte pour une personne.",
                      style="BarMuted.TLabel", wraplength=320).pack(anchor="w")
        for index, person in enumerate(self.draft.people):
            row = ttk.Frame(self._people_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=3)
            avatar = tk.Canvas(row, width=AVATAR_PX, height=AVATAR_PX, highlightthickness=0, background=theme.surface)
            avatar.self_themed = True  # type: ignore[attr-defined]
            avatar.pack(side="left")
            key = f"p:{person.name.casefold()}"
            avatar.create_oval(1, 1, AVATAR_PX - 1, AVATAR_PX - 1, fill=badge_color(key), outline="")
            avatar.create_text(AVATAR_PX / 2, AVATAR_PX / 2, text=initials(person.name), fill="#FFFFFF",
                               font=(theme.font[0], theme.font[1] - 1, "bold"))
            if person.account_ids:
                self._load_avatar(avatar, max(person.account_ids))
            ttk.Button(row, text="Suppr.", width=6, command=lambda i=index: self._delete_person(i)).pack(side="right")
            ttk.Button(row, text="Modifier", command=lambda i=index: self._edit_person(i)).pack(side="right", padx=4)
            text = ttk.Frame(row, style="Surface.TFrame")
            text.pack(side="left", fill="x", expand=True, padx=8)
            ttk.Label(text, text=person.name, style="Bar.TLabel", font=(theme.font[0], theme.font[1], "bold")).pack(anchor="w")
            accounts = ", ".join(self._account_label(a) for a in person.account_ids)
            identities = ", ".join(person.git_identities)
            details = " · ".join(x for x in (accounts, f"git : {identities}" if identities else "") if x)
            ttk.Label(text, text=details or "Aucun compte", style="BarMuted.TLabel", wraplength=200).pack(anchor="w")

    def _load_avatar(self, canvas: tk.Canvas, user_id: int) -> None:
        if self.app.client is None:
            return
        user = self.app.known_users.get(user_id)
        store = self.app.avatars

        def done(path: object) -> None:
            if path and canvas.winfo_exists():
                image = self.app.load_avatar_image(path, AVATAR_PX)  # type: ignore[arg-type]
                if image is not None:
                    self._avatar_images.append(image)
                    canvas.delete("all")
                    canvas.create_image(AVATAR_PX / 2, AVATAR_PX / 2, image=image)

        self.app.runner.run(f"avatar-{id(canvas)}", lambda _p: store.path_for(user_id, user.avatar_url if user else None),
                            done, lambda e: None)

    def _account_label(self, account_id: int) -> str:
        user = self.app.known_users.get(account_id)
        return f"#{account_id} {user.username}" if user else f"#{account_id}"

    def _delete_person(self, index: int) -> None:
        del self.draft.people[index]
        self._render_people()

    def _edit_person(self, index: int | None) -> None:
        person = self.draft.people[index] if index is not None else Person(name="")

        def done(updated: Person) -> None:
            if index is None:
                self.draft.people.append(updated)
            else:
                self.draft.people[index] = updated
            self._render_people()

        PersonDialog(self, self.app, person, done)


def _fmt(value: float) -> str:
    return f"{value:g}"


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
    """Lists the projects visible to the token so the user ticks those to track."""

    def __init__(self, master: SettingsTab, client: GitLabClient, tracked: list[TrackedProject],
                 on_done: Callable[[list[Project]], None]) -> None:
        super().__init__(master)
        app = master.app
        self.title("Choisir les dépôts")
        self.geometry("520x560")
        self.transient(master.winfo_toplevel())
        self.configure(background=app.get_theme().bg)
        self._projects: list[Project] = []
        self._on_done = on_done
        self._status = ttk.Label(self, text="Chargement des projets…")
        self._status.pack(anchor="w", padx=12, pady=(12, 4))
        self.picker = ProjectPicker(self, app.get_theme)
        self.picker.pack(fill="both", expand=True, padx=12)
        buttons = ttk.Frame(self, padding=12)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Valider", style="Accent.TButton", command=self._validate).pack(side="right")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right", padx=8)
        checked = [p.id for p in tracked]

        def loaded(projects: list[Project]) -> None:
            if not self.winfo_exists():
                return
            self._projects = projects
            self._status.configure(text=f"{len(projects)} projet(s) accessible(s)")
            self.picker.set_projects([(p.id, p.path_with_namespace) for p in projects], checked)

        def failed(exc: BaseException) -> None:
            if self.winfo_exists():
                self.destroy()
            app.report_error(exc)

        app.runner.run("projects", lambda _p: client.list_projects(), loaded, failed)

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
