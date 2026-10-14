"""Start Gitective with Windows (OC-12): one value in the user's Run registry key, no admin rights needed."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Gitective"
MINIMIZED = "--minimized"


class Registry(Protocol):
    """The few winreg calls used here, so the tests can use a fake."""

    def read(self) -> str | None: ...

    def write(self, command: str) -> None: ...

    def delete(self) -> None: ...


class WindowsRegistry:
    """HKEY_CURRENT_USER Run key: programs started when this user logs in."""

    def __init__(self) -> None:
        import winreg  # Windows only; imported here so the module loads everywhere

        self._winreg: Any = winreg

    def read(self) -> str | None:
        reg = self._winreg
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
                return str(reg.QueryValueEx(key, VALUE_NAME)[0])
        except FileNotFoundError:
            return None

    def write(self, command: str) -> None:
        reg = self._winreg
        with reg.CreateKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command)

    def delete(self) -> None:
        reg = self._winreg
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                reg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass


def supported() -> bool:
    return sys.platform == "win32"


def default_registry() -> Registry | None:
    return WindowsRegistry() if supported() else None


def launch_command(app_dir: Path, python: str = sys.executable) -> str:
    """pythonw (no console window) running main.pyw, minimized to the taskbar."""
    interpreter = Path(python)
    windowed = interpreter.with_name("pythonw.exe")
    if interpreter.name.lower() == "python.exe" and windowed.exists():
        interpreter = windowed
    return f'"{interpreter}" "{app_dir / "main.pyw"}" {MINIMIZED}'


def is_enabled(registry: Registry | None) -> bool:
    return registry is not None and bool(registry.read())


def set_enabled(registry: Registry | None, enabled: bool, app_dir: Path, python: str = sys.executable) -> None:
    """Add or remove the Run entry; the command is rewritten so a moved folder keeps working."""
    if registry is None:
        return
    if enabled:
        registry.write(launch_command(app_dir, python))
    else:
        registry.delete()
