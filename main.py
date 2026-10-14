"""Gitective entry point: python main.py (or double-click main.pyw on Windows)."""

import sys
import tkinter as tk

if sys.version_info < (3, 11):
    sys.exit("Gitective requires Python 3.11 or newer.")

from gitective.settings.config_file import config_exists  # noqa: E402
from gitective.ui.app import App  # noqa: E402


def main() -> None:
    first_launch = not config_exists()
    # Sharp rendering on high-DPI Windows screens.
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    App(root, first_launch)
    root.mainloop()


if __name__ == "__main__":
    main()
