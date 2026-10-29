"""Tests of the user edition build: admin blocks removed, every file still valid Python."""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from tools.make_edition import ROOT, make_edition, strip_admin


class StripAdminTests(unittest.TestCase):
    def test_blocks_and_markers_removed(self) -> None:
        text = "a = 1\n# admin:begin\nb = 2\n    # admin:end\nc = 3\n"
        self.assertEqual(strip_admin(text), "a = 1\nc = 3\n")

    def test_unbalanced_markers_rejected(self) -> None:
        for text in ("# admin:begin\n", "# admin:end\n", "# admin:begin\n# admin:begin\n# admin:end\n"):
            with self.assertRaises(ValueError):
                strip_admin(text)

    def test_every_source_file_stays_valid(self) -> None:
        for path in [*ROOT.glob("gitective/**/*.py"), *ROOT.glob("tests/**/*.py"), ROOT / "main.py"]:
            ast.parse(strip_admin(path.read_text(encoding="utf-8"), str(path)), str(path))


class MakeEditionTests(unittest.TestCase):
    def test_user_edition(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "user"
            make_edition("user", out, "2026.10.29-1")
            init = (out / "gitective" / "__init__.py").read_text(encoding="utf-8")
            self.assertIn('EDITION = "user"', init)
            self.assertNotIn('EDITION = "admin"', init)
            self.assertIn('BUILD = "2026.10.29-1"', init)
            code = "".join(p.read_text(encoding="utf-8") for p in (out / "gitective").rglob("*.py"))
            self.assertNotIn("admin:begin", code)
            self.assertNotIn("def per_person", code)
            self.assertFalse((out / "tests" / "tools").exists())
            self.assertTrue((out / "README.md").read_text(encoding="utf-8").startswith("# Gitective — getting a GitLab token"))

    def test_admin_edition_keeps_everything(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "admin"
            make_edition("admin", out)
            self.assertIn("def per_person", (out / "gitective" / "reporting" / "statistics.py").read_text(encoding="utf-8"))
            self.assertFalse((out / "docs" / "README_user.md").exists())


if __name__ == "__main__":
    unittest.main()
