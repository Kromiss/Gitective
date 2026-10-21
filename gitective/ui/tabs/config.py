"""Config tab: connection, theme, rules, regex tester, repositories, people (OC-01..OC-08)."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from gitective.shared.i18n import t
from gitective.forge.gitlab_client import GitLabClient
from gitective.forge.models import Project, User
from gitective.settings.config_file import (
    FIXED_CRITERIA,
    PARALLEL_RANGE,
    REFRESH_RANGE,
    RULE_FIELDS,
    CustomRule,
    Person,
    Settings,
    TrackedProject,
)
from gitective.settings import config_file as config
from gitective.shared import autostart
from gitective.shared.avatars import badge_color, initials
from gitective.review.rules import FIXED_LABELS, MrFields, RuleSet, validate_regex
from gitective.review.settings_form import NumberFields, apply_numbers
from gitective.ui.themes import THEMES
from gitective.shared.i18n import LANGUAGES
from gitective.ui.components.dialogs import PersonDialog, ProjectsDialog, RuleDialog
from gitective.ui.components.widgets import ScrollableFrame

if TYPE_CHECKING:
    from gitective.ui.app import App

AVATAR_PX = 30
HIGHLIGHT_MS = 6000  # how long the notification switches stay highlighted (NO-10)


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
        self._build_notifications(columns[0])
        self._build_theme(columns[0])
        self._build_rules(columns[1])
        self._build_tester(columns[1])
        self._build_projects(columns[2])
        self._build_branches(columns[2])
        self._build_people(columns[2])

        actions = ttk.Frame(self, padding=(16, 10))
        actions.pack(fill="x", side="bottom")
        ttk.Button(actions, text=t("Enregistrer"), style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(actions, text=t("Annuler"), command=self.reset).pack(side="right", padx=8)
        self.reset()

    # ------------------------------------------------------------ Sections

    def _section(self, parent: tk.Misc, title: str, pack: bool = True) -> ttk.Frame:
        """Rounded card with its title, like the filter cards of the data tabs."""
        frame = ttk.Frame(parent, style="Card.TFrame", padding=(14, 12))
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        if pack:
            frame.pack(fill="x", pady=(0, 12))
        return frame

    def _labeled_entry(self, parent: tk.Misc, label: str, var: tk.StringVar, **options: object) -> ttk.Entry:
        ttk.Label(parent, text=label, style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        entry = ttk.Entry(parent, textvariable=var, **options)  # type: ignore[arg-type]
        entry.pack(fill="x")
        return entry

    def _build_connection(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Connexion GitLab"))
        self.url = tk.StringVar()
        self.token = tk.StringVar()
        self.verify_ssl = tk.BooleanVar()
        self._labeled_entry(box, t("URL de l'instance"), self.url)
        ttk.Label(box, text=t("Token personnel (droit read_api)"), style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x")
        self._token_entry = ttk.Entry(row, textvariable=self.token, show="•")
        self._token_entry.pack(side="left", fill="x", expand=True)
        self._show_button = ttk.Button(row, text=t("Afficher"), command=self._toggle_token)
        self._show_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(box, text=t("Vérifier le certificat SSL"), variable=self.verify_ssl).pack(anchor="w", pady=8)
        self.parallel = tk.StringVar()
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text=t("Requêtes simultanées ({low}–{high})", low=PARALLEL_RANGE[0], high=PARALLEL_RANGE[1]),
                  style="Bar.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=PARALLEL_RANGE[0], to=PARALLEL_RANGE[1], textvariable=self.parallel,
                    width=4).pack(side="left", padx=8)
        ttk.Button(box, text=t("Tester la connexion"), command=self._test_connection).pack(anchor="w")
        # Read-only: read from GitLab, never edited (OC-11).
        self._user_text = ttk.Label(box, style="BarMuted.TLabel", wraplength=320, justify="left")
        self._user_text.pack(anchor="w", pady=(10, 0))
        self.sync_minutes = tk.StringVar()
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=t("Synchronisation automatique (min)"), style="Bar.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=REFRESH_RANGE[0], to=REFRESH_RANGE[1], textvariable=self.sync_minutes,
                    width=4).pack(side="left", padx=8)

    def _build_notifications(self, parent: tk.Misc) -> None:
        """Desktop notifications, four switches (NO-01, OC-11)."""
        self._notifications = self._section(parent, t("Notifications de bureau"))
        self._highlight_job: str | None = None
        self.notify_merges = tk.BooleanVar()
        self.notify_assigned = tk.BooleanVar()
        self.notify_own_merged = tk.BooleanVar()
        self.notify_new_mrs = tk.BooleanVar()
        self._checks = [
            ttk.Checkbutton(self._notifications, text=text, variable=var)
            for text, var in ((t("Nouveaux merges sur les dépôts suivis"), self.notify_merges),
                              (t("MR qui me sont assignées ou en relecture"), self.notify_assigned),
                              (t("Ma MR mergée"), self.notify_own_merged),
                              (t("Toutes les nouvelles MR des dépôts suivis"), self.notify_new_mrs))
        ]
        for check in self._checks:
            check.pack(anchor="w", pady=(4, 0))
        ttk.Label(self._notifications, text=t("Affichées même quand Gitective est réduit (pas quand il est fermé)."),
                  style="BarMuted.TLabel", wraplength=320).pack(anchor="w", pady=(6, 0))

    def highlight_notifications(self) -> None:
        """Scroll to the notification switches and highlight them for a few seconds (NO-10)."""
        self.update_idletasks()
        frame = self._notifications
        top = frame.winfo_rooty() - self._scroller.inner.winfo_rooty()
        height = max(1, self._scroller.inner.winfo_height())
        self._scroller.canvas.yview_moveto(max(0.0, (top - 12) / height))
        checks = self._checks
        title = frame.winfo_children()[0]  # the card title (see _section)
        frame.state(["alternate"])  # accent border of the card
        title.configure(style="Highlight.TLabel")  # type: ignore[call-arg]
        for check in checks:
            check.configure(style="Highlight.TCheckbutton")
        checks[0].focus_set()
        if self._highlight_job:
            self.after_cancel(self._highlight_job)

        def restore() -> None:
            self._highlight_job = None
            frame.state(["!alternate"])
            title.configure(style="Section.TLabel")  # type: ignore[call-arg]
            for check in checks:
                check.configure(style="TCheckbutton")

        self._highlight_job = self.after(HIGHLIGHT_MS, restore)

    def show_user(self) -> None:
        """Token owner, read only (OC-11)."""
        user = self.app.user
        if user is None:
            text = t("Utilisateur inconnu (testez la connexion ou rafraîchissez).")
        else:
            text = t("Connecté en tant que {name} ({username})", name=user.name, username=user.username)
        self._user_text.configure(text=text)

    def _build_theme(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Thème"))
        self.theme = tk.StringVar()
        for key, theme in THEMES.items():
            ttk.Radiobutton(box, text=theme.label, value=key, variable=self.theme).pack(anchor="w", pady=2)
        # Language (OC-13, 5.9): applied at the next start.
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=t("Langue"), style="Bar.TLabel").pack(side="left")
        self.language = tk.StringVar()
        ttk.Combobox(row, textvariable=self.language, values=list(LANGUAGES.values()), state="readonly",
                     width=12).pack(side="left", padx=8)
        # Start with Windows (OC-12): stored in the registry, not in config.json.
        self.autostart = tk.BooleanVar()
        self._autostart_box = ttk.Checkbutton(box, text=t("Lancer Gitective au démarrage de Windows (réduit)"),
                                              variable=self.autostart)
        self._autostart_box.pack(anchor="w", pady=(10, 0))
        if not autostart.supported():
            self._autostart_box.state(["disabled"])
        ttk.Button(box, text=t("Relancer l'assistant de démarrage"), command=self.app.open_wizard).pack(anchor="w", pady=(10, 0))
        ttk.Button(box, text=t("Vider la base locale"), command=self._clear_store).pack(anchor="w", pady=(6, 0))

    def _build_rules(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Règles personnalisées"))
        ttk.Button(box, text=t("+ Règle"), command=lambda: self._edit_rule(None)).pack(anchor="w")
        self._rules_frame = ttk.Frame(box, style="Surface.TFrame")
        self._rules_frame.pack(fill="x", pady=(8, 0))

        fixed = self._section(parent, t("Correspondance ticket et règles fixes"))
        self.link_regex = tk.StringVar()
        self.ticket_regex = tk.StringVar()
        mono = self.app.get_theme().mono
        self._labeled_entry(fixed, t("Regex du lien ticket (dans la description)"), self.link_regex, font=mono)
        self._labeled_entry(fixed, t("Regex du n° de ticket"), self.ticket_regex, font=mono)
        for var in (self.link_regex, self.ticket_regex):
            var.trace_add("write", lambda *_: self._run_tester())
        ttk.Label(fixed, text=t("Pondérations"), style="BarMuted.TLabel").pack(anchor="w", pady=(12, 2))
        weights = ttk.Frame(fixed, style="Surface.TFrame")
        weights.pack(fill="x")
        self.weights = {c: tk.StringVar() for c in FIXED_CRITERIA}
        for index, criterion in enumerate(FIXED_CRITERIA):
            cell = ttk.Frame(weights, style="Surface.TFrame")
            cell.grid(row=0, column=index, sticky="sew", padx=(0, 8))
            weights.columnconfigure(index, weight=1)
            ttk.Label(cell, text=FIXED_LABELS[criterion], style="BarMuted.TLabel", wraplength=90).pack(anchor="w")
            ttk.Entry(cell, textvariable=self.weights[criterion], width=6).pack(fill="x")
        self.assignee_rule = tk.BooleanVar()
        ttk.Checkbutton(fixed, text=t("Compter la règle « Mergée par l'assigné » (RC-06)"),
                        variable=self.assignee_rule).pack(anchor="w", pady=(8, 0))
        ttk.Label(fixed, text=t("Seuils du score (%)"), style="BarMuted.TLabel").pack(anchor="w", pady=(12, 2))
        thresholds = ttk.Frame(fixed, style="Surface.TFrame")
        thresholds.pack(fill="x")
        self.green = tk.StringVar()
        self.orange = tk.StringVar()
        ttk.Label(thresholds, text=t("Vert ≥"), style="Bar.TLabel").pack(side="left")
        ttk.Entry(thresholds, textvariable=self.green, width=6).pack(side="left", padx=(4, 14))
        ttk.Label(thresholds, text=t("Orange ≥"), style="Bar.TLabel").pack(side="left")
        ttk.Entry(thresholds, textvariable=self.orange, width=6).pack(side="left", padx=4)
        ttk.Label(thresholds, text=t("sinon rouge"), style="BarMuted.TLabel").pack(side="left", padx=6)

    def _build_tester(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Testeur de règles"))
        self.sample_title = tk.StringVar()
        self.sample_source = tk.StringVar()
        self.sample_target = tk.StringVar()
        self._labeled_entry(box, t("Titre"), self.sample_title)
        branches = ttk.Frame(box, style="Surface.TFrame")
        branches.pack(fill="x")
        branches.columnconfigure((0, 1), weight=1)
        for column, (label, var) in enumerate(((t("Branche source"), self.sample_source),
                                               (t("Branche cible"), self.sample_target))):
            cell = ttk.Frame(branches, style="Surface.TFrame")
            cell.grid(row=0, column=column, sticky="ew", padx=(0, 6) if column == 0 else 0)
            self._labeled_entry(cell, label, var)
        for var in (self.sample_title, self.sample_source, self.sample_target):
            var.trace_add("write", lambda *_: self._run_tester())
        self.sample_description = self._sample_text(box, t("Description"), 3)
        self.sample_commits = self._sample_text(box, t("Messages de commits (un par ligne)"), 3)
        self._results = ttk.Frame(box, style="Surface.TFrame")
        self._results.pack(fill="x", pady=(10, 0))

    def _sample_text(self, parent: tk.Misc, label: str, height: int) -> tk.Text:
        ttk.Label(parent, text=label, style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        text = tk.Text(parent, height=height, wrap="word", relief="solid", borderwidth=1)
        text.pack(fill="x")
        text.bind("<KeyRelease>", lambda e: self._run_tester())
        return text

    def _build_projects(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Dépôts suivis et branche contrôlée"))
        ttk.Button(box, text=t("Choisir les dépôts…"), command=self._choose_projects).pack(anchor="w")
        self._projects_frame = ttk.Frame(box, style="Surface.TFrame")
        self._projects_frame.pack(fill="x", pady=(8, 0))
        self._branch_vars: dict[int, tk.StringVar] = {}
        self._ci_vars: dict[int, tk.BooleanVar] = {}

    def _build_branches(self, parent: tk.Misc) -> None:
        """Exclusion regex and dead branch threshold of the Branches tab (OC-10)."""
        box = self._section(parent, t("Branches"))
        self.branch_regex = tk.StringVar()
        self.dead_days = tk.StringVar()
        self._labeled_entry(box, t("Regex d'exclusion (insensible à la casse)"), self.branch_regex)
        ttk.Label(box, text=t("La branche par défaut et les branches protégées sont toujours masquées."),
                  style="BarMuted.TLabel", wraplength=320).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text=t("Branche morte après"), style="Bar.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=1, to=3650, textvariable=self.dead_days, width=5).pack(side="left", padx=8)
        ttk.Label(row, text=t("jours calendaires sans commit"), style="Bar.TLabel").pack(side="left")

    def _build_people(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Personnes et comptes"))
        ttk.Button(box, text=t("+ Personne"), command=lambda: self._edit_person(None)).pack(anchor="w")
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
        self.language.set(LANGUAGES.get(d.language, LANGUAGES["fr"]))
        self.sync_minutes.set(str(d.sync_minutes))
        self.autostart.set(autostart.is_enabled(self._registry()))
        self.assignee_rule.set(d.assignee_rule)
        self.notify_merges.set(d.notify_merges)
        self.notify_assigned.set(d.notify_assigned)
        self.notify_own_merged.set(d.notify_own_merged)
        self.notify_new_mrs.set(d.notify_new_mrs)
        self.link_regex.set(d.link_regex)
        self.ticket_regex.set(d.ticket_regex)
        self.branch_regex.set(d.branch_exclude_regex)
        self.dead_days.set(str(d.dead_branch_days))
        for criterion, var in self.weights.items():
            var.set(_fmt(d.weights.get(criterion, 0)))
        self.green.set(_fmt(d.green_threshold))
        self.orange.set(_fmt(d.orange_threshold))
        self._render_rules()
        self._render_projects()
        self._render_people()
        self._run_tester()
        self.show_user()

    def _collect(self) -> tuple[Settings | None, str]:
        """Build settings from the form; return (None, error) when invalid."""
        d = copy.deepcopy(self.draft)
        d.gitlab_url = self.url.get().strip()
        d.token = self.token.get().strip()
        d.verify_ssl = self.verify_ssl.get()
        d.theme = self.theme.get()
        d.language = next((code for code, name in LANGUAGES.items() if name == self.language.get()), d.language)
        d.link_regex = self.link_regex.get()
        d.ticket_regex = self.ticket_regex.get()
        d.branch_exclude_regex = self.branch_regex.get().strip()
        d.assignee_rule = self.assignee_rule.get()
        d.notify_merges = self.notify_merges.get()
        d.notify_assigned = self.notify_assigned.get()
        d.notify_own_merged = self.notify_own_merged.get()
        d.notify_new_mrs = self.notify_new_mrs.get()
        error = apply_numbers(d, NumberFields(
            weights={c: v.get() for c, v in self.weights.items()}, green=self.green.get(),
            orange=self.orange.get(), parallel=self.parallel.get(), sync_minutes=self.sync_minutes.get(),
            dead_branch_days=self.dead_days.get()))
        if error:
            return None, error
        for project in d.projects:
            project.branch = self._branch_vars[project.id].get().strip() if project.id in self._branch_vars else project.branch
            project.ci_expected = self._ci_vars[project.id].get() if project.id in self._ci_vars else project.ci_expected
        return d, ""

    def _save(self) -> None:
        settings, error = self._collect()
        if settings is None:
            self.app.notify("error", error)
            return
        changed = settings.gitlab_url.rstrip("/") != self.app.settings.gitlab_url.rstrip("/")
        if changed and self.app.settings.gitlab_url and not self.app.store.is_empty():
            # The local base belongs to one instance (CH-10).
            if not messagebox.askyesno(t("Changement d'instance"),
                                       t("L'URL de l'instance change : la base locale va être vidée et les données "
                                         "seront relues depuis la nouvelle instance.\n\nContinuer ?"), parent=self):
                return
        registry = self._registry()
        if autostart.supported() and self.autostart.get() != autostart.is_enabled(registry):
            try:
                autostart.set_enabled(registry, self.autostart.get(), config.APP_DIR)
            except OSError as exc:
                self.app.notify("error", t("Démarrage avec Windows impossible à régler : {error}", error=exc))
                return
        restart = settings.language != self.app.settings.language
        self.app.apply_settings(settings)
        self.draft = copy.deepcopy(settings)
        if restart:  # in both languages: the interface still speaks the old one (LG-02)
            self.app.notify("info", "Redémarrez Gitective pour appliquer la langue. / "
                                    "Restart Gitective to apply the language.")
        else:
            self.app.notify("success", t("Configuration enregistrée."))

    @staticmethod
    def _registry() -> autostart.Registry | None:
        try:
            return autostart.default_registry()
        except OSError:
            return None

    def _clear_store(self) -> None:
        """OC-09: delete every stored row after confirmation."""
        if messagebox.askyesno(t("Vider la base locale"),
                               t("Supprimer toutes les données de gitective.db ? Elles seront relues depuis GitLab "
                                 "(la configuration est conservée)."), parent=self):
            self.app.clear_store()
            self.app.notify("success", t("Base locale vidée."))

    # --------------------------------------------------------- Connection

    def _toggle_token(self) -> None:
        hidden = self._token_entry.cget("show") != ""
        self._token_entry.configure(show="" if hidden else "•")
        self._show_button.configure(text=t("Masquer") if hidden else t("Afficher"))

    def _form_client(self) -> GitLabClient | None:
        if not self.url.get().strip() or not self.token.get().strip():
            self.app.notify("error", t("Renseignez l'URL de l'instance et le token."))
            return None
        return GitLabClient(self.url.get().strip(), self.token.get().strip(), verify_ssl=self.verify_ssl.get())

    def _test_connection(self) -> None:
        client = self._form_client()
        if client is None:
            return

        def done(user: User) -> None:
            self.app.notify("success", t("Connexion réussie : connecté en tant que {username} ({name}).", username=user.username,
                                           name=user.name))

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
            ttk.Label(self._results, text=t("Une regex est invalide."), style="Bar.TLabel").pack(anchor="w")
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
            tk.Label(row, text={"ok": t("OK"), "ko": t("KO")}.get(result.status, t("N/A")), background=bg, foreground=fg,
                     width=4, font=(theme.font[0], theme.font[1], "bold")).pack(side="left")
            text = labels.get(criterion_id, criterion_id)
            if result.detail:
                text += " — " + (t("n° extrait {number}", number=result.detail) if result.status == "ok" else result.detail)
            ttk.Label(row, text=text, style="Bar.TLabel", wraplength=300).pack(side="left", padx=8)

    # --------------------------------------------------------------- Rules

    def _render_rules(self) -> None:
        for child in self._rules_frame.winfo_children():
            child.destroy()
        if not self.draft.rules:
            ttk.Label(self._rules_frame, text=t("Aucune règle personnalisée."), style="BarMuted.TLabel").pack(anchor="w")
        theme = self.app.get_theme()
        for index, rule in enumerate(self.draft.rules):
            row = ttk.Frame(self._rules_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=3)
            active = tk.BooleanVar(value=rule.active)
            ttk.Checkbutton(row, variable=active,
                            command=lambda r=rule, v=active: self._toggle_rule(r, v.get())).pack(side="left")
            ttk.Button(row, text=t("Suppr."), width=6, command=lambda i=index: self._delete_rule(i)).pack(side="right")
            ttk.Button(row, text=t("Modifier"), command=lambda i=index: self._edit_rule(i)).pack(side="right", padx=4)
            text = ttk.Frame(row, style="Surface.TFrame")
            text.pack(side="left", fill="x", expand=True, padx=4)
            style = "Bar.TLabel" if rule.active else "BarMuted.TLabel"
            ttk.Label(text, text=rule.name, style=style, wraplength=220,
                      font=(theme.font[0], theme.font[1], "bold")).pack(anchor="w")
            mode = "≈" if rule.mode == "match" else "≠"
            detail = (f"{t(RULE_FIELDS.get(rule.field, rule.field))} {mode} {rule.pattern or t('(regex à compléter)')}"
                      + t("  ·  poids {weight}", weight=f"{rule.weight:g}"))
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
        previous_ci = {pid: var.get() for pid, var in self._ci_vars.items()}
        self._branch_vars = {}
        self._ci_vars = {}
        if not self.draft.projects:
            ttk.Label(self._projects_frame, text=t("Aucun dépôt suivi."), style="BarMuted.TLabel").pack(anchor="w")
        for project in self.draft.projects:
            row = ttk.Frame(self._projects_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=2)
            var = tk.StringVar(value=previous.get(project.id, project.branch))
            self._branch_vars[project.id] = var
            ci = tk.BooleanVar(value=previous_ci.get(project.id, project.ci_expected))
            self._ci_vars[project.id] = ci
            # The path on its own line, so a long one never pushes the branch and CI fields away.
            ttk.Label(row, text=project.path, style="Bar.TLabel", wraplength=380).pack(anchor="w")
            fields = ttk.Frame(row, style="Surface.TFrame")
            fields.pack(fill="x", pady=(2, 6))
            ttk.Label(fields, text=t("Branche"), style="BarMuted.TLabel").pack(side="left")
            ttk.Entry(fields, textvariable=var, width=18, font=self.app.get_theme().mono).pack(side="left", padx=(6, 0))
            # RC-05 is N/A for the MRs of a repository without CI (SD-08, PI-06).
            ttk.Checkbutton(fields, text=t("CI attendue"), variable=ci).pack(side="left", padx=(12, 0))

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
            ttk.Label(self._people_frame, text=t("Aucune personne : chaque compte compte pour une personne."),
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
            ttk.Button(row, text=t("Suppr."), width=6, command=lambda i=index: self._delete_person(i)).pack(side="right")
            ttk.Button(row, text=t("Modifier"), command=lambda i=index: self._edit_person(i)).pack(side="right", padx=4)
            text = ttk.Frame(row, style="Surface.TFrame")
            text.pack(side="left", fill="x", expand=True, padx=8)
            ttk.Label(text, text=person.name, style="Bar.TLabel", font=(theme.font[0], theme.font[1], "bold")).pack(anchor="w")
            accounts = ", ".join(self._account_label(a) for a in person.account_ids)
            identities = ", ".join(person.git_identities)
            details = " · ".join(x for x in (accounts, t("git : {identities}", identities=identities) if identities else "") if x)
            ttk.Label(text, text=details or t("Aucun compte"), style="BarMuted.TLabel", wraplength=200).pack(anchor="w")

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

        self.app.runner.run(f"avatar-{id(canvas)}", lambda _p: store.image_for(user_id, user.avatar_url if user else None),
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
