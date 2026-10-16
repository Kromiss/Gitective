"""Text and SHA prefix search used by the data tabs (FI-12, FI-20)."""

from collections.abc import Iterable

HEX = frozenset("0123456789abcdef")


def matches(needle: str, *fields: str | None) -> bool:
    """Case-insensitive substring search over several fields; an empty needle matches all."""
    return not needle or needle in " ".join(f for f in fields if f).casefold()


def sha_hit(needle: str, shas: Iterable[tuple[str, str | None]]) -> str | None:
    """Label and short SHA ("merge 4f1a9c2e") of the first (label, sha) starting with needle (FI-20).

    The prefix search starts at the first character; a needle that is not
    hexadecimal never matches a SHA.
    """
    needle = needle.strip().casefold()
    if not needle or not set(needle) <= HEX:
        return None
    for label, sha in shas:
        if sha and sha.casefold().startswith(needle):
            return f"{label} {sha[:max(8, len(needle))]}"
    return None
