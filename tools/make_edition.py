"""Copy Gitective as the admin or user edition, ready to zip or to freeze with PyInstaller.

    python tools/make_edition.py admin|user <output folder> [--build 2026.10.29-1]

The user edition (GDPR) drops every block between "# admin:begin" and "# admin:end"
from the Python files, so the per-person code is absent rather than hidden, and ships
docs/README_user.md as its README.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BEGIN, END = "# admin:begin", "# admin:end"
COPIED = ["gitective", "tests", "main.py", "main.pyw", "README.md", "docs"]


def strip_admin(text: str, name: str = "<text>") -> str:
    """Remove the admin blocks, markers included; reject unbalanced or nested markers."""
    kept: list[str] = []
    inside = False
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        marker = line.strip()
        if marker == BEGIN:
            if inside:
                raise ValueError(f"{name}:{number}: nested {BEGIN}")
            inside = True
        elif marker == END:
            if not inside:
                raise ValueError(f"{name}:{number}: {END} without {BEGIN}")
            inside = False
        elif not inside:
            kept.append(line)
    if inside:
        raise ValueError(f"{name}: {BEGIN} not closed")
    return "".join(kept)


def _ignored(folder: str, names: list[str]) -> list[str]:
    """Caches, and tests/tools which checks this script (not shipped)."""
    skip_tools = Path(folder) == ROOT / "tests"
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc") or (skip_tools and n == "tools")]


def make_edition(edition: str, out: Path, build: str = "") -> None:
    """Write the chosen edition into `out` (replaced if it exists)."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in COPIED:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, out / name, ignore=_ignored)
        else:
            shutil.copy2(source, out / name)
    if edition == "user":
        for path in out.rglob("*.py"):
            path.write_text(strip_admin(path.read_text(encoding="utf-8"), str(path)), encoding="utf-8")
        (out / "docs" / "README_user.md").replace(out / "README.md")
    else:
        (out / "docs" / "README_user.md").unlink()
    init = out / "gitective" / "__init__.py"
    text, count = re.subn(r'^BUILD = ""', f'BUILD = "{build}"', init.read_text(encoding="utf-8"), flags=re.M)
    if count != 1:
        raise ValueError(f'{init}: line BUILD = "" not found')
    init.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("edition", choices=["admin", "user"])
    parser.add_argument("out", type=Path)
    parser.add_argument("--build", default="", help="release number shown in the header, e.g. 2026.10.29-1")
    args = parser.parse_args()
    make_edition(args.edition, args.out, args.build)


if __name__ == "__main__":
    main()
