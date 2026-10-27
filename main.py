"""Gitective entry point: python main.py (or double-click main.pyw on Windows)."""

import sys
import tkinter as tk

if sys.version_info < (3, 11):
    sys.exit("Gitective requires Python 3.11 or newer.")

from gitective.settings import config_file  # noqa: E402
from gitective.shared import i18n  # noqa: E402

# The interface modules translate their texts when imported: choose the language first (LG-02).
i18n.use(config_file.load().language)

from gitective.ui.app import App  # noqa: E402


def main() -> None:
    first_launch = not config_file.config_exists()
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
