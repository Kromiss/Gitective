"""First-launch wizard: URL → token → connection test → repositories (AS-01..AS-03)."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from gitective.shared.i18n import t
from gitective.forge.gitlab_client import GitLabClient
from gitective.forge.models import Project, User
from gitective.settings.config_file import TrackedProject
from gitective.ui.alerts.error_banner import describe_error
from gitective.ui.components.widgets import ProjectPicker

if TYPE_CHECKING:
    from gitective.ui.app import App

STEPS = (t("Instance GitLab"), t("Token"), t("Test de connexion"), t("Dépôts"))


class Wizard(tk.Toplevel):
    """Modal four-step assistant; can be skipped at any time."""

    def __init__(self, app: App) -> None:
        super().__init__(app.root)
        self.app = app
        theme = app.get_theme()
        self.title(t("Gitective — Assistant de démarrage"))
        self.geometry("620x520")
        self.configure(background=theme.bg)
        self.transient(app.root)
        self.protocol("WM_DELETE_WINDOW", self._skip)
        self.settings = copy.deepcopy(app.settings)
        self.url = tk.StringVar(value=self.settings.gitlab_url)
        self.token = tk.StringVar(value=self.settings.token)
        self.verify_ssl = tk.BooleanVar(value=self.settings.verify_ssl)
        self._user: User | None = None
        self._projects: list[Project] = []
        self._step = 0

        header = ttk.Frame(self, padding=(20, 16, 20, 4))
        header.pack(fill="x")
        if app.logo_small is not None:
            ttk.Label(header, image=app.logo_small).pack(side="left", padx=(0, 10))
        ttk.Label(header, text=t("Bienvenue dans Gitective"), style="Title.TLabel").pack(side="left")
        self._steps_label = ttk.Label(self, style="Muted.TLabel", padding=(20, 0))
        self._steps_label.pack(fill="x")
        self._body = ttk.Frame(self, style="Surface.TFrame", padding=20)
        self._body.pack(fill="both", expand=True, padx=20, pady=12)
        self._message = ttk.Label(self, wraplength=560, padding=(20, 0))
        self._message.pack(fill="x")
        buttons = ttk.Frame(self, padding=20)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=t("Passer"), command=self._skip).pack(side="left")
        self._next = ttk.Button(buttons, text=t("Suivant"), style="Accent.TButton", command=self._forward)
        self._next.pack(side="right")
        self._back = ttk.Button(buttons, text=t("Précédent"), command=self._backward)
        self._back.pack(side="right", padx=8)
        self._show()
        self.grab_set()

    def _show(self) -> None:
        for child in self._body.winfo_children():
            child.destroy()
        self._message.configure(text="")
        self._steps_label.configure(text="   ›   ".join(
            f"[{s}]" if i == self._step else s for i, s in enumerate(STEPS)))
        self._back.state(["!disabled"] if self._step else ["disabled"])
        self._next.configure(text=t("Terminer") if self._step == len(STEPS) - 1 else t("Suivant"))
        getattr(self, f"_step_{self._step}")()

    def _step_0(self) -> None:
        ttk.Label(self._body, text=t("Adresse de votre instance GitLab"), style="Section.TLabel").pack(anchor="w")
        ttk.Label(self._body, text=t("Exemple : https://gitlab.mon-entreprise.fr"), style="BarMuted.TLabel").pack(anchor="w", pady=(2, 8))
        entry = ttk.Entry(self._body, textvariable=self.url)
        entry.pack(fill="x")
        entry.focus_set()
        ttk.Checkbutton(self._body, text=t("Vérifier le certificat SSL"), variable=self.verify_ssl).pack(anchor="w", pady=10)

    def _step_1(self) -> None:
        ttk.Label(self._body, text=t("Token d'accès personnel"), style="Section.TLabel").pack(anchor="w")
        ttk.Label(self._body, wraplength=520, style="BarMuted.TLabel",
                  text=t("Créez-le dans GitLab : Préférences › Jetons d'accès, avec uniquement le droit read_api. "
                       "Il sera stocké en clair dans config.json, à côté de l'application.")).pack(anchor="w", pady=(2, 8))
        entry = ttk.Entry(self._body, textvariable=self.token, show="•")
        entry.pack(fill="x")
        entry.focus_set()

    def _step_2(self) -> None:
        ttk.Label(self._body, text=t("Test de la connexion"), style="Section.TLabel").pack(anchor="w")
        self._test_result = ttk.Label(self._body, text=t("Test en cours…"), style="Bar.TLabel", wraplength=520)
        self._test_result.pack(anchor="w", pady=10)
        ttk.Button(self._body, text=t("Relancer le test"), command=self._run_test).pack(anchor="w")
        self._run_test()

    def _step_3(self) -> None:
        ttk.Label(self._body, text=t("Dépôts à contrôler"), style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        self._picker = ProjectPicker(self._body, self.app.get_theme)
        self._picker.pack(fill="both", expand=True)
        checked = [p.id for p in self.settings.projects]
        if self._projects:
            self._picker.set_projects([(p.id, p.path_with_namespace) for p in self._projects], checked)
            return

        def loaded(projects: list[Project]) -> None:
            if self.winfo_exists() and self._step == 3:
                self._projects = projects
                self._picker.set_projects([(p.id, p.path_with_namespace) for p in projects], checked)

        client, workers = self._client(), self.app.settings.parallel_requests

        def task(_progress: object) -> list[Project]:
            return client.list_projects(workers=workers)

        self.app.runner.run("wizard-projects", task, loaded, self._error)

    def _client(self) -> GitLabClient:
        return GitLabClient(self.url.get().strip(), self.token.get().strip(), verify_ssl=self.verify_ssl.get())

    def _run_test(self) -> None:
        self._user = None
        self._test_result.configure(text=t("Test en cours…"))

        def done(user: User) -> None:
            if self.winfo_exists() and self._step == 2:
                self._user = user
                self._test_result.configure(text="✔  " + t("Connecté en tant que {name} ({username})", name=user.name,
                                                                       username=user.username) + ".")

        def failed(exc: BaseException) -> None:
            if self.winfo_exists() and self._step == 2:
                self._test_result.configure(text=f"✖  {describe_error(exc)}")

        self.app.runner.run("wizard-test", lambda _p: self._client().current_user(), done, failed)

    def _error(self, exc: BaseException) -> None:
        if self.winfo_exists():
            self._message.configure(text=describe_error(exc))

    def _forward(self) -> None:
        if self._step == 0 and not self.url.get().strip().startswith(("http://", "https://")):
            self._message.configure(text=t("L'URL doit commencer par http:// ou https://"))
            return
        if self._step == 1 and not self.token.get().strip():
            self._message.configure(text=t("Le token est obligatoire."))
            return
        if self._step == 2 and self._user is None:
            self._message.configure(text=t("La connexion doit réussir avant de continuer (ou passez l'assistant)."))
            return
        if self._step == len(STEPS) - 1:
            self._finish()
            return
        self._step += 1
        self._show()

    def _backward(self) -> None:
        self._step = max(0, self._step - 1)
        self._show()

    def _finish(self) -> None:
        current = {p.id: p for p in self.settings.projects}
        chosen = set(self._picker.checked())
        self.settings.gitlab_url = self.url.get().strip()
        self.settings.token = self.token.get().strip()
        self.settings.verify_ssl = self.verify_ssl.get()
        self.settings.projects = [
            current.get(p.id) or TrackedProject(id=p.id, path=p.path_with_namespace, web_url=p.web_url,
                                               branch=p.default_branch or "")
            for p in self._projects if p.id in chosen
        ]
        self.grab_release()
        self.destroy()
        self.app.apply_settings(self.settings)
        self.app.notify("success", t("Configuration enregistrée. Complétez les règles du process dans l'onglet Config."))

    def _skip(self) -> None:
        """Skip: save what was typed so the wizard does not reappear (AS-03)."""
        self.settings.gitlab_url = self.url.get().strip()
        self.settings.token = self.token.get().strip()
        self.settings.verify_ssl = self.verify_ssl.get()
        self.grab_release()
        self.destroy()
        self.app.apply_settings(self.settings)
