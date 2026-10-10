"""Closable notification banner (ER-01) and user-facing error messages."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from gitective.api.errors import (
    AuthenticationError,
    GitLabError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SSLVerificationError,
)
from gitective.core.orphan_commits import BranchNotFoundError
from gitective.ui.themes import Theme


def describe_error(exc: BaseException) -> str:
    """Clear French message for an exception (ER-02)."""
    if isinstance(exc, AuthenticationError):
        return "Token invalide ou expiré : vérifiez le token dans l'onglet Config."
    if isinstance(exc, PermissionDeniedError):
        return "Droits insuffisants : le token doit avoir le droit read_api sur ce dépôt."
    if isinstance(exc, NotFoundError):
        return "Ressource introuvable : un dépôt suivi n'existe plus ou n'est plus visible avec ce token."
    if isinstance(exc, BranchNotFoundError):
        return f"Branche introuvable : « {exc.branch} » n'existe pas sur {exc.project_path}. Corrigez-la dans l'onglet Config."
    if isinstance(exc, RateLimitError):
        return "GitLab limite le nombre de requêtes (HTTP 429), même après 3 nouvelles tentatives. Réessayez plus tard."
    if isinstance(exc, SSLVerificationError):
        return "Certificat SSL non vérifiable. Vous pouvez désactiver la vérification SSL dans l'onglet Config."
    if isinstance(exc, NetworkError):
        return f"Instance GitLab injoignable (réseau coupé ou délai dépassé). Détail : {exc}"
    if isinstance(exc, GitLabError):
        return f"Erreur GitLab : {exc}"
    return f"Erreur inattendue : {exc}"


class Banner(tk.Frame):
    """Colored strip at the top of the window; hidden until a message arrives."""

    ICONS = {"error": "✖", "success": "✔", "info": "ℹ"}

    def __init__(self, master: tk.Misc, get_theme: Callable[[], Theme], before: tk.Widget) -> None:
        super().__init__(master, padx=16, pady=8)
        self._get_theme = get_theme
        self._before = before
        self._icon = tk.Label(self, font=("Segoe UI", 11, "bold"))
        self._icon.pack(side="left", padx=(0, 10))
        self._text = tk.Label(self, anchor="w", justify="left", wraplength=1000)
        self._text.pack(side="left", fill="x", expand=True)
        self._close = tk.Button(self, text="✕", relief="flat", borderwidth=0, cursor="hand2", command=self.hide)
        self._close.pack(side="right")
        self._kind = "info"
        self._visible = False

    def show(self, kind: str, message: str) -> None:
        """Display a message; kind is 'error', 'success' or 'info'."""
        self._kind = kind
        self._icon.configure(text=self.ICONS.get(kind, ""))
        self._text.configure(text=message)
        self.restyle()
        if not self._visible:
            self.pack(side="top", fill="x", before=self._before)
            self._visible = True

    def hide(self) -> None:
        if self._visible:
            self.pack_forget()
            self._visible = False

    def restyle(self) -> None:
        theme = self._get_theme()
        bg, fg = getattr(theme, self._kind, theme.info)
        self.configure(background=bg)
        for widget in (self._icon, self._text, self._close):
            widget.configure(background=bg, foreground=fg)
        self._close.configure(activebackground=bg, activeforeground=fg)
        self._text.configure(font=theme.font)
