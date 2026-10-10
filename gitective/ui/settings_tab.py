"""Config tab: connection, theme, rules, regex tester, repositories, people (OC-01..OC-08)."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.api.client import GitLabClient
from gitective.api.models import Project, User
from gitective.config.settings import (
    FIXED_CRITERIA,
    PARALLEL_RANGE,
    RULE_FIELDS,
    CustomRule,
    Person,
    Settings,
    TrackedProject,
)
from gitective.core.avatars import badge_color, initials
from gitective.core.rules import FIXED_LABELS, MrFields, RuleSet, validate_regex
from gitective.ui.themes import THEMES
from gitective.ui.dialogs import PersonDialog, ProjectsDialog, RuleDialog
from gitective.ui.widgets import ScrollableFrame

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
        self.parallel = tk.StringVar()
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text=f"Requêtes simultanées ({PARALLEL_RANGE[0]}–{PARALLEL_RANGE[1]})",
                  style="Bar.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=PARALLEL_RANGE[0], to=PARALLEL_RANGE[1], textvariable=self.parallel,
                    width=4).pack(side="left", padx=8)
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
        self.parallel.set(str(d.parallel_requests))
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
        low, high = PARALLEL_RANGE
        if not self.parallel.get().strip().isdigit() or not low <= int(self.parallel.get()) <= high:
            return None, f"Requêtes simultanées : un nombre entier entre {low} et {high}."
        d.parallel_requests = int(self.parallel.get())
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
        ProjectsDialog(self, self.app, client, self.draft.projects, self._projects_chosen)

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
