"""Start with Windows (OC-12), checked with a fake registry so it runs on any system."""

import tempfile
import unittest
from pathlib import Path

from gitective.shared import autostart


class FakeRegistry:
    def __init__(self) -> None:
        self.value: str | None = None

    def read(self) -> str | None:
        return self.value

    def write(self, command: str) -> None:
        self.value = command

    def delete(self) -> None:
        self.value = None


class AutostartTests(unittest.TestCase):
    def test_command_uses_pythonw_and_starts_minimized(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / "python.exe"
            python.touch()
            (Path(folder) / "pythonw.exe").touch()
            command = autostart.launch_command(Path("C:/Apps/gitective"), str(python))
            self.assertTrue(command.startswith(f'"{Path(folder) / "pythonw.exe"}"'))
            self.assertIn(str(Path("C:/Apps/gitective") / "main.pyw"), command)
            self.assertTrue(command.endswith(autostart.MINIMIZED))

    def test_without_pythonw_the_interpreter_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / "python.exe"
            command = autostart.launch_command(Path("/app"), str(python))
            self.assertTrue(command.startswith(f'"{python}"'))

    def test_enable_disable_round_trip(self) -> None:
        registry = FakeRegistry()
        self.assertFalse(autostart.is_enabled(registry))
        autostart.set_enabled(registry, True, Path("/app"), "/usr/bin/python3")
        self.assertTrue(autostart.is_enabled(registry))
        autostart.set_enabled(registry, False, Path("/app"))
        self.assertFalse(autostart.is_enabled(registry))

    def test_no_registry_outside_windows(self) -> None:
        self.assertFalse(autostart.is_enabled(None))
        autostart.set_enabled(None, True, Path("/app"))  # silently nothing
        self.assertEqual(autostart.default_registry() is None, not autostart.supported())


if __name__ == "__main__":
    unittest.main()
