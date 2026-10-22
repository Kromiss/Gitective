"""Config tab in three sub-tabs: Général, Règles, Avancé (OC-01..OC-17)."""

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
from gitective.review.rules import FIXED_LABELS, TICKET, MrFields, RuleSet, validate_regex
from gitective.review.settings_form import NumberFields, apply_numbers, changes_by_page, group_error
from gitective.ui.themes import THEMES
from gitective.shared.i18n import LANGUAGES
from gitective.ui.components.dialogs import PersonDialog, ProjectsDialog, RuleDialog
from gitective.ui.components.widgets import ScrollableFrame, Tooltip

if TYPE_CHECKING:
    from gitective.ui.app import App

AVATAR_PX = 30
HIGHLIGHT_MS = 6000  # how long the notification switches stay highlighted (NO-10)
DEFAULTS = Settings()


def _pages() -> tuple[tuple[str, str], ...]:
    """Sub-tabs of the Config tab (OC-14)."""
    return (("general", t("Général")), ("rules", t("Règles")), ("advanced", t("Avancé")))


class SettingsTab(ttk.Frame):
    """Edits a draft copy of the settings; nothing is applied before Save."""

    def __init__(self, master: tk.Misc, app: App) -> None:
        super().__init__(master)
        self.app = app
        self.dirty = False  # App reloads "dirty" data tabs; the form tracks its own changes (has_changes)
        self.draft: Settings = copy.deepcopy(app.settings)
        self._avatar_images: list[tk.PhotoImage] = []
        self._tooltip = Tooltip(self, app.get_theme)
        self._loading = True
        self._baseline: dict[str, object] = {}
        self._changes: dict[str, int] = {}

        bar = ttk.Frame(self, style="Card.TFrame", padding=(14, 10))
        bar.pack(fill="x", padx=16, pady=(12, 0))
        self._view = tk.StringVar(value=app.settings.config_view)
        self._page_buttons: dict[str, ttk.Radiobutton] = {}
        for key, text in _pages():
            button = ttk.Radiobutton(bar, text=text, value=key, variable=self._view, style="Toolbutton",
                                     command=lambda: self.show_page(self._view.get()))
            button.pack(side="left")
            self._page_buttons[key] = button

        actions = ttk.Frame(self, padding=(16, 10))
        actions.pack(fill="x", side="bottom")
        self._status = ttk.Label(actions, style="Muted.TLabel")
        self._status.pack(side="left")
        self._save_button = ttk.Button(actions, style="Accent.TButton", command=self._save)
        self._save_button.pack(side="right")
        self._cancel_button = ttk.Button(actions, text=t("Annuler les modifications"), command=self.reset)
        self._cancel_button.pack(side="right", padx=8)

        self._pages: dict[str, ScrollableFrame] = {}
        columns: dict[str, list[ttk.Frame]] = {}
        for key, _text in _pages():
            scroller = ScrollableFrame(self)
            body = scroller.inner
            body.columnconfigure((0, 1), weight=1, uniform="col")
            columns[key] = [ttk.Frame(body) for _ in range(2)]
            for index, column in enumerate(columns[key]):
                column.grid(row=0, column=index, sticky="nsew", padx=8, pady=12)
            self._pages[key] = scroller
        self._scroller = self._pages["general"]

        general, rules, advanced = columns["general"], columns["rules"], columns["advanced"]
        self._build_connection(general[0])
        self._build_projects(general[0])
        self._build_appearance(general[1])
        self._build_notifications(general[1])
        self._build_people(general[1])
        self._build_rules(rules[0])
        self._build_tester(rules[1])
        self._build_network(advanced[0])
        self._build_branches(advanced[0])
        self._build_startup(advanced[1])
        self._build_store(advanced[1])

        for var in self._tracked_vars():
            var.trace_add("write", lambda *_: self._refresh_changes())
        self.show_page(self._view.get(), remember=False)
        self.reset()

    # ------------------------------------------------------------ Sub-tabs

    def show_page(self, key: str, remember: bool = True) -> None:
        """Show one sub-tab and remember it (OC-14)."""
        self._tooltip.hide()
        self._view.set(key)
        for page_key, page in self._pages.items():
            if page_key == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        if remember and key != self.app.settings.config_view:
            self.app.save_config_view(key)

    # ------------------------------------------------------------ Sections

    def _section(self, parent: tk.Misc, title: str, help_text: str = "", pack: bool = True) -> ttk.Frame:
        """Rounded card with its title, like the filter cards of the data tabs."""
        frame = ttk.Frame(parent, style="Card.TFrame", padding=(16, 14))
        head = ttk.Frame(frame, style="Surface.TFrame")
        head.pack(fill="x", pady=(0, 6))
        ttk.Label(head, text=title, style="Section.TLabel").pack(side="left")
        if help_text:
            self._help(head, help_text)
        if pack:
            frame.pack(fill="x", pady=(0, 14))
        return frame

    def _help(self, parent: tk.Misc, text: str) -> ttk.Label:
        """ⓘ icon showing what a setting does and its default value (OC-16)."""
        icon = ttk.Label(parent, text="ⓘ", style="BarMuted.TLabel", cursor="question_arrow")
        icon.pack(side="left", padx=(6, 0))
        icon.bind("<Enter>", lambda e: self._tooltip.show(e.x_root, e.y_root, text))
        icon.bind("<Leave>", lambda e: self._tooltip.hide())
        return icon

    def _field_label(self, parent: tk.Misc, label: str, help_text: str) -> None:
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill="x", pady=(8, 2))
        ttk.Label(row, text=label, style="BarMuted.TLabel").pack(side="left")
        self._help(row, help_text)

    def _labeled_entry(self, parent: tk.Misc, label: str, var: tk.StringVar, help_text: str,
                       **options: object) -> ttk.Entry:
        self._field_label(parent, label, help_text)
        entry = ttk.Entry(parent, textvariable=var, **options)  # type: ignore[arg-type]
        entry.pack(fill="x")
        return entry

    def _check(self, parent: tk.Misc, text: str, var: tk.BooleanVar, help_text: str) -> ttk.Checkbutton:
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill="x", pady=(6, 0))
        check = ttk.Checkbutton(row, text=text, variable=var)
        check.pack(side="left")
        self._help(row, help_text)
        return check

    def _spin(self, parent: tk.Misc, label: str, var: tk.StringVar, bounds: tuple[int, int], help_text: str,
              unit: str = "") -> None:
        row = ttk.Frame(parent, style="Surface.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text=label, style="Bar.TLabel").pack(side="left")
        ttk.Spinbox(row, from_=bounds[0], to=bounds[1], textvariable=var, width=5).pack(side="left", padx=8)
        if unit:
            ttk.Label(row, text=unit, style="Bar.TLabel").pack(side="left")
        self._help(row, help_text)

    # ------------------------------------------------------------- Général

    def _build_connection(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Connexion GitLab"))
        self.url = tk.StringVar()
        self.token = tk.StringVar()
        self._labeled_entry(box, t("URL de l'instance"), self.url,
                            t("Adresse de votre instance GitLab, par exemple https://gitlab.exemple.fr."))
        self._field_label(box, t("Token personnel (droit read_api)"),
                          t("Token d'accès personnel avec le droit read_api. Il reste sur ce poste, dans config.json."))
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x")
        self._token_entry = ttk.Entry(row, textvariable=self.token, show="•")
        self._token_entry.pack(side="left", fill="x", expand=True)
        self._show_button = ttk.Button(row, text=t("Afficher"), command=self._toggle_token)
        self._show_button.pack(side="left", padx=(6, 0))
        ttk.Button(box, text=t("Tester la connexion"), command=self._test_connection).pack(anchor="w", pady=(10, 0))
        # Read-only: read from GitLab, never edited (OC-11).
        self._user_text = ttk.Label(box, style="BarMuted.TLabel", wraplength=420, justify="left")
        self._user_text.pack(anchor="w", pady=(8, 0))

    def _build_projects(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Dépôts suivis et branche contrôlée"),
                            t("Dépôts dont les MR sont contrôlées. « Branche » est la branche cible contrôlée ; "
                              "décochez « CI attendue » pour un dépôt sans pipeline (critère N/A). "
                              "Par défaut : aucun dépôt."))
        ttk.Button(box, text=t("Choisir les dépôts…"), command=self._choose_projects).pack(anchor="w")
        self._projects_frame = ttk.Frame(box, style="Surface.TFrame")
        self._projects_frame.pack(fill="x", pady=(8, 0))
        self._branch_vars: dict[int, tk.StringVar] = {}
        self._ci_vars: dict[int, tk.BooleanVar] = {}

    def _build_appearance(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Apparence"))
        self._field_label(box, t("Thème"),
                          t("Couleurs de l'interface, appliquées dès l'enregistrement. Chaque thème double les "
                            "couleurs de jauges, hachures et pointillés. Par défaut : {value}.",
                            value=THEMES[DEFAULTS.theme].label))
        self.theme = tk.StringVar()
        themes = ttk.Frame(box, style="Surface.TFrame")
        themes.pack(fill="x")
        themes.columnconfigure((0, 1), weight=1)
        for index, (key, theme) in enumerate(THEMES.items()):
            ttk.Radiobutton(themes, text=theme.label, value=key, variable=self.theme).grid(
                row=index // 2, column=index % 2, sticky="w", pady=2)
        # Language (OC-13, 5.9): applied at the next start.
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(12, 0))
        ttk.Label(row, text=t("Langue"), style="Bar.TLabel").pack(side="left")
        self.language = tk.StringVar()
        ttk.Combobox(row, textvariable=self.language, values=list(LANGUAGES.values()), state="readonly",
                     width=12).pack(side="left", padx=8)
        self._help(row, t("Langue de l'interface, appliquée au prochain démarrage. Par défaut : Français."))

    def _build_notifications(self, parent: tk.Misc) -> None:
        """Desktop notifications, four switches (NO-01, OC-11)."""
        self._notifications = self._section(parent, t("Notifications de bureau"))
        self._highlight_job: str | None = None
        self.notify_merges = tk.BooleanVar()
        self.notify_assigned = tk.BooleanVar()
        self.notify_own_merged = tk.BooleanVar()
        self.notify_new_mrs = tk.BooleanVar()
        self._checks = [
            self._check(self._notifications, text, var, help_text)
            for text, var, help_text in (
                (t("Nouveaux merges sur les dépôts suivis"), self.notify_merges,
                 t("Une notification à chaque MR mergée sur un dépôt suivi. Par défaut : coché.")),
                (t("MR qui me sont assignées ou en relecture"), self.notify_assigned,
                 t("Quand une MR vous est assignée ou demandée en relecture. Par défaut : coché.")),
                (t("Ma MR mergée"), self.notify_own_merged,
                 t("Quand une MR dont vous êtes l'auteur est mergée. Par défaut : coché.")),
                (t("Toutes les nouvelles MR des dépôts suivis"), self.notify_new_mrs,
                 t("Chaque nouvelle MR créée sur un dépôt suivi, quel que soit l'auteur. Par défaut : décoché.")))
        ]
        ttk.Label(self._notifications, text=t("Affichées même quand Gitective est réduit (pas quand il est fermé)."),
                  style="BarMuted.TLabel", wraplength=420).pack(anchor="w", pady=(8, 0))

    def highlight_notifications(self) -> None:
        """Show the notification switches and highlight them for a few seconds (NO-10)."""
        self.show_page("general")
        self.update_idletasks()
        frame = self._notifications
        top = frame.winfo_rooty() - self._scroller.inner.winfo_rooty()
        height = max(1, self._scroller.inner.winfo_height())
        self._scroller.canvas.yview_moveto(max(0.0, (top - 12) / height))
        checks = self._checks
        title = frame.winfo_children()[0].winfo_children()[0]  # the card title (see _section)
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

    def _build_people(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Personnes et comptes"),
                            t("Regroupe plusieurs comptes GitLab et identités git sous une même personne pour les "
                              "statistiques. Sans personne déclarée, chaque compte compte pour une personne."))
        ttk.Button(box, text=t("+ Personne"), command=lambda: self._edit_person(None)).pack(anchor="w")
        self._people_frame = ttk.Frame(box, style="Surface.TFrame")
        self._people_frame.pack(fill="x", pady=(8, 0))

    # -------------------------------------------------------------- Règles

    def _build_rules(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Règles personnalisées"),
                            t("Critères ajoutés au score : une regex cherchée (≈) ou interdite (≠) dans un champ de "
                              "la MR, avec un poids. Par défaut : aucune règle."))
        ttk.Button(box, text=t("+ Règle"), command=lambda: self._edit_rule(None)).pack(anchor="w")
        self._rules_frame = ttk.Frame(box, style="Surface.TFrame")
        self._rules_frame.pack(fill="x", pady=(8, 0))

        fixed = self._section(parent, t("Correspondance ticket"))
        self.link_regex = tk.StringVar()
        self.ticket_regex = tk.StringVar()
        self.link_group = tk.StringVar()
        self.ticket_group = tk.StringVar()
        mono = self.app.get_theme().mono
        self._labeled_entry(fixed, t("Regex du lien ticket (dans la description)"), self.link_regex,
                            t("Regex qui trouve le lien du ticket dans la description de la MR. "
                              "Par défaut : {value}", value=DEFAULTS.link_regex), font=mono)
        self._group_spin(fixed, self.link_group)
        self._labeled_entry(fixed, t("Regex du n° de ticket"), self.ticket_regex,
                            t("Regex qui extrait le n° de ticket (premier groupe capturant). "
                              "Par défaut : {value}", value=DEFAULTS.ticket_regex), font=mono)
        self._group_spin(fixed, self.ticket_group)
        for var in (self.link_regex, self.ticket_regex, self.link_group, self.ticket_group):
            var.trace_add("write", lambda *_: self._run_tester())

        scoring = self._section(parent, t("Pondérations et seuils"))
        defaults = ", ".join(f"{FIXED_LABELS[c]} {_fmt(DEFAULTS.weights.get(c, 0))}" for c in FIXED_CRITERIA)
        self._field_label(scoring, t("Pondérations"),
                          t("Poids de chaque critère fixe dans le score ; 0 retire le critère. "
                            "Par défaut : {value}.", value=defaults))
        weights = ttk.Frame(scoring, style="Surface.TFrame")
        weights.pack(fill="x")
        self.weights = {c: tk.StringVar() for c in FIXED_CRITERIA}
        for index, criterion in enumerate(FIXED_CRITERIA):
            cell = ttk.Frame(weights, style="Surface.TFrame")
            cell.grid(row=0, column=index, sticky="sew", padx=(0, 8))
            weights.columnconfigure(index, weight=1)
            ttk.Label(cell, text=FIXED_LABELS[criterion], style="BarMuted.TLabel", wraplength=100).pack(anchor="w")
            ttk.Entry(cell, textvariable=self.weights[criterion], width=6).pack(fill="x")
        self.assignee_rule = tk.BooleanVar()
        self._check(scoring, t("Compter la règle « Mergée par l'assigné » (RC-06)"), self.assignee_rule,
                    t("Ajoute le critère « Mergée par l'assigné » au score. Par défaut : décoché."))
        self._field_label(scoring, t("Seuils du score (%)"),
                          t("Score minimal du vert et de l'orange ; en dessous, rouge. "
                            "Par défaut : vert ≥ {green} %, orange ≥ {orange} %.",
                            green=_fmt(DEFAULTS.green_threshold), orange=_fmt(DEFAULTS.orange_threshold)))
        thresholds = ttk.Frame(scoring, style="Surface.TFrame")
        thresholds.pack(fill="x")
        self.green = tk.StringVar()
        self.orange = tk.StringVar()
        ttk.Label(thresholds, text=t("Vert ≥"), style="Bar.TLabel").pack(side="left")
        ttk.Entry(thresholds, textvariable=self.green, width=6).pack(side="left", padx=(4, 14))
        ttk.Label(thresholds, text=t("Orange ≥"), style="Bar.TLabel").pack(side="left")
        ttk.Entry(thresholds, textvariable=self.orange, width=6).pack(side="left", padx=4)
        ttk.Label(thresholds, text=t("sinon rouge"), style="BarMuted.TLabel").pack(side="left", padx=6)

    def _build_tester(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Testeur de règles"),
                            t("Saisissez une MR fictive pour voir le résultat des règles du formulaire, "
                              "avant même d'enregistrer. Ces champs ne sont pas enregistrés."))
        self.sample_title = tk.StringVar()
        self.sample_source = tk.StringVar()
        self.sample_target = tk.StringVar()
        ttk.Label(box, text=t("Titre"), style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
        ttk.Entry(box, textvariable=self.sample_title).pack(fill="x")
        branches = ttk.Frame(box, style="Surface.TFrame")
        branches.pack(fill="x")
        branches.columnconfigure((0, 1), weight=1)
        for column, (label, var) in enumerate(((t("Branche source"), self.sample_source),
                                               (t("Branche cible"), self.sample_target))):
            cell = ttk.Frame(branches, style="Surface.TFrame")
            cell.grid(row=0, column=column, sticky="ew", padx=(0, 6) if column == 0 else 0)
            ttk.Label(cell, text=label, style="BarMuted.TLabel").pack(anchor="w", pady=(6, 2))
            ttk.Entry(cell, textvariable=var).pack(fill="x")
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

    def _group_spin(self, parent: tk.Misc, var: tk.StringVar) -> None:
        self._spin(parent, t("Groupe à récupérer"), var, (0, 99), group_help())

    # -------------------------------------------------------------- Avancé

    def _build_network(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Réseau et synchronisation"))
        self.verify_ssl = tk.BooleanVar()
        self._check(box, t("Vérifier le certificat SSL"), self.verify_ssl,
                    t("À ne décocher que pour une instance interne avec un certificat auto-signé. "
                      "Par défaut : coché."))
        self.parallel = tk.StringVar()
        self._spin(box, t("Requêtes simultanées ({low}–{high})", low=PARALLEL_RANGE[0], high=PARALLEL_RANGE[1]),
                   self.parallel, PARALLEL_RANGE,
                   t("Requêtes GitLab lancées en même temps pour lire commits et MR : plus rapide, mais plus de "
                     "charge sur le serveur. Par défaut : {value}.", value=DEFAULTS.parallel_requests))
        self.sync_minutes = tk.StringVar()
        self._spin(box, t("Synchronisation automatique (min)"), self.sync_minutes, REFRESH_RANGE,
                   t("Intervalle entre deux relectures automatiques de GitLab. Par défaut : {value} min.",
                     value=DEFAULTS.sync_minutes))

    def _build_branches(self, parent: tk.Misc) -> None:
        """Exclusion regex and dead branch threshold of the Branches tab (OC-10)."""
        box = self._section(parent, t("Onglet Branches"))
        self.branch_regex = tk.StringVar()
        self.dead_days = tk.StringVar()
        self._labeled_entry(box, t("Regex d'exclusion (insensible à la casse)"), self.branch_regex,
                            t("Branches masquées dans l'onglet Branches. La branche par défaut et les branches "
                              "protégées sont toujours masquées. Par défaut : {value}",
                              value=DEFAULTS.branch_exclude_regex))
        self._spin(box, t("Branche morte après"), self.dead_days, (1, 3650),
                   t("Une branche sans commit depuis ce nombre de jours calendaires est marquée morte. "
                     "Par défaut : {value} jours.", value=DEFAULTS.dead_branch_days),
                   unit=t("jours calendaires sans commit"))

    def _build_startup(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Démarrage"))
        # Start with Windows (OC-12): stored in the registry, not in config.json.
        self.autostart = tk.BooleanVar()
        self._autostart_box = self._check(box, t("Lancer Gitective au démarrage de Windows (réduit)"), self.autostart,
                                          t("Lance Gitective réduit à l'ouverture de session Windows. Réglé dans le "
                                            "registre, pas dans config.json. Par défaut : décoché."))
        if not autostart.supported():
            self._autostart_box.state(["disabled"])
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text=t("Relancer l'assistant de démarrage"), command=self.app.open_wizard).pack(side="left")
        self._help(row, t("Rouvre l'assistant du premier lancement : URL, token et dépôts."))

    def _build_store(self, parent: tk.Misc) -> None:
        box = self._section(parent, t("Base locale"))
        row = ttk.Frame(box, style="Surface.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text=t("Vider la base locale"), command=self._clear_store).pack(side="left")
        self._help(row, t("Supprime les données lues depuis GitLab ; elles sont relues à la synchronisation "
                          "suivante. La configuration est conservée."))

    # ---------------------------------------------------- Unsaved changes

    def _tracked_vars(self) -> list[tk.Variable]:
        return [self.url, self.token, self.theme, self.language, self.notify_merges, self.notify_assigned,
                self.notify_own_merged, self.notify_new_mrs, self.link_regex, self.ticket_regex,
                self.link_group, self.ticket_group, *self.weights.values(), self.assignee_rule, self.green, self.orange, self.verify_ssl,
                self.parallel, self.sync_minutes, self.branch_regex, self.dead_days, self.autostart]

    def _snapshot(self) -> dict[str, object]:
        """Current form values, keyed "<sub-tab>.<setting>" (OC-15)."""
        d = self.draft
        projects = [(p.id, self._branch_vars[p.id].get().strip() if p.id in self._branch_vars else p.branch,
                     self._ci_vars[p.id].get() if p.id in self._ci_vars else p.ci_expected) for p in d.projects]
        values: dict[str, object] = {
            "general.url": self.url.get().strip(), "general.token": self.token.get().strip(),
            "general.projects": projects, "general.theme": self.theme.get(), "general.language": self.language.get(),
            "general.notify_merges": self.notify_merges.get(), "general.notify_assigned": self.notify_assigned.get(),
            "general.notify_own_merged": self.notify_own_merged.get(), "general.notify_new_mrs": self.notify_new_mrs.get(),
            "general.people": repr(d.people),
            "rules.rules": repr(d.rules), "rules.link_regex": self.link_regex.get(),
            "rules.ticket_regex": self.ticket_regex.get(), "rules.link_group": self.link_group.get().strip(),
            "rules.ticket_group": self.ticket_group.get().strip(), "rules.assignee_rule": self.assignee_rule.get(),
            "rules.green": self.green.get().strip(), "rules.orange": self.orange.get().strip(),
            "advanced.verify_ssl": self.verify_ssl.get(), "advanced.parallel": self.parallel.get().strip(),
            "advanced.sync_minutes": self.sync_minutes.get().strip(),
            "advanced.branch_regex": self.branch_regex.get().strip(), "advanced.dead_days": self.dead_days.get().strip(),
            "advanced.autostart": self.autostart.get(),
        }
        for criterion, var in self.weights.items():
            values[f"rules.weight_{criterion}"] = var.get().strip()
        return values

    def _refresh_changes(self) -> None:
        """Dot on the changed sub-tabs, count on Save, summary in the status bar (OC-15)."""
        if self._loading:
            return
        self._changes = changes_by_page(self._baseline, self._snapshot())
        total = sum(self._changes.values())
        names = dict(_pages())
        for key, button in self._page_buttons.items():
            button.configure(text=names[key] + ("  •" if self._changes.get(key) else ""))
        if total:
            self._save_button.configure(text=t("Enregistrer ({count})", count=total))
            self._save_button.state(["!disabled"])
            self._cancel_button.state(["!disabled"])
            pages = ", ".join(names[k] for k, _ in _pages() if self._changes.get(k))
            self._status.configure(text=t("{count} modification(s) non enregistrée(s) · {pages}",
                                          count=total, pages=pages), style="Pending.TLabel")
        else:
            self._save_button.configure(text=t("Enregistrer"))
            self._save_button.state(["disabled"])
            self._cancel_button.state(["disabled"])
            self._status.configure(text=t("Aucune modification en attente."), style="Muted.TLabel")

    def change_count(self) -> int:
        return sum(self._changes.values())

    def has_changes(self) -> bool:
        return self.change_count() > 0

    def changed_pages(self) -> str:
        return ", ".join(text for key, text in _pages() if self._changes.get(key))

    # ---------------------------------------------------------- Draft I/O

    def reset(self) -> None:
        """Reload the form from the saved settings (Cancel)."""
        self._loading = True
        for page in self._pages.values():  # page background, also after a theme change
            page.canvas.self_themed = True  # type: ignore[attr-defined]
            page.set_background(self.app.get_theme().bg)
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
        self.link_group.set(str(d.link_group))
        self.ticket_group.set(str(d.ticket_group))
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
        self._baseline = self._snapshot()
        self._loading = False
        self._refresh_changes()

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
            dead_branch_days=self.dead_days.get(), link_group=self.link_group.get().strip(),
            ticket_group=self.ticket_group.get().strip()))
        if error:
            return None, error
        for project in d.projects:
            project.branch = self._branch_vars[project.id].get().strip() if project.id in self._branch_vars else project.branch
            project.ci_expected = self._ci_vars[project.id].get() if project.id in self._ci_vars else project.ci_expected
        return d, ""

    def save(self) -> bool:
        """Apply the form; False when it is invalid or the user backed out."""
        settings, error = self._collect()
        if settings is None:
            self.app.notify("error", error)
            return False
        changed = settings.gitlab_url.rstrip("/") != self.app.settings.gitlab_url.rstrip("/")
        if changed and self.app.settings.gitlab_url and not self.app.store.is_empty():
            # The local base belongs to one instance (CH-10).
            if not messagebox.askyesno(t("Changement d'instance"),
                                       t("L'URL de l'instance change : la base locale va être vidée et les données "
                                         "seront relues depuis la nouvelle instance.\n\nContinuer ?"), parent=self):
                return False
        registry = self._registry()
        if autostart.supported() and self.autostart.get() != autostart.is_enabled(registry):
            try:
                autostart.set_enabled(registry, self.autostart.get(), config.APP_DIR)
            except OSError as exc:
                self.app.notify("error", t("Démarrage avec Windows impossible à régler : {error}", error=exc))
                return False
        restart = settings.language != self.app.settings.language
        self.app.apply_settings(settings)
        self.draft = copy.deepcopy(settings)
        if restart:  # in both languages: the interface still speaks the old one (LG-02)
            self.app.notify("info", "Redémarrez Gitective pour appliquer la langue. / "
                                    "Restart Gitective to apply the language.")
        else:
            self.app.notify("success", t("Configuration enregistrée."))
        return True

    def _save(self) -> None:
        self.save()

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
        link_group, ticket_group = self.link_group.get().strip(), self.ticket_group.get().strip()
        error = group_error(self.link_regex.get(), link_group) or group_error(self.ticket_regex.get(), ticket_group)
        if error:
            ttk.Label(self._results, text=error, style="Bar.TLabel").pack(anchor="w")
            return
        rules = RuleSet(self.draft.rules, self.link_regex.get(), self.ticket_regex.get(), {},
                        link_group=int(link_group), ticket_group=int(ticket_group))
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
                if result.status != "ok":
                    text += " — " + result.detail
                elif criterion_id == TICKET:
                    text += " — " + t("n° extrait {number}", number=result.detail)
                else:
                    text += " — " + t("valeur récupérée : {value}", value=result.detail)
            ttk.Label(row, text=text, style="Bar.TLabel", wraplength=420).pack(side="left", padx=8)

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
            ttk.Label(text, text=rule.name, style=style, wraplength=300,
                      font=(theme.font[0], theme.font[1], "bold")).pack(anchor="w")
            mode = "≈" if rule.mode == "match" else "≠"
            detail = (f"{t(RULE_FIELDS.get(rule.field, rule.field))} {mode} {rule.pattern or t('(regex à compléter)')}"
                      + (t("  ·  groupe {group}", group=rule.group) if rule.group else "")
                      + t("  ·  poids {weight}", weight=f"{rule.weight:g}"))
            ttk.Label(text, text=detail, style="BarMuted.TLabel", font=theme.mono, wraplength=300).pack(anchor="w")
        self._refresh_changes()

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
            ttk.Label(row, text=project.path, style="Bar.TLabel", wraplength=440).pack(anchor="w")
            fields = ttk.Frame(row, style="Surface.TFrame")
            fields.pack(fill="x", pady=(2, 6))
            ttk.Label(fields, text=t("Branche"), style="BarMuted.TLabel").pack(side="left")
            ttk.Entry(fields, textvariable=var, width=18, font=self.app.get_theme().mono).pack(side="left", padx=(6, 0))
            # RC-05 is N/A for the MRs of a repository without CI (SD-08, PI-06).
            ttk.Checkbutton(fields, text=t("CI attendue"), variable=ci).pack(side="left", padx=(12, 0))
            for tracked in (var, ci):
                tracked.trace_add("write", lambda *_: self._refresh_changes())
        self._refresh_changes()

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
                      style="BarMuted.TLabel", wraplength=420).pack(anchor="w")
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
            ttk.Label(text, text=details or t("Aucun compte"), style="BarMuted.TLabel", wraplength=280).pack(anchor="w")
        self._refresh_changes()

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


def group_help() -> str:
    """ⓘ text of every "group to extract" field (RP-09)."""
    return t("N° du groupe capturant à récupérer. Exemple : avec (#)(\\d+) sur « #42 », le groupe 2 donne 42, "
             "le groupe 1 donne #. 0 = toute la correspondance. Par défaut : 0.")


def _fmt(value: float) -> str:
    return f"{value:g}"
