"""Text search used by the data tabs (FI-12)."""


def matches(needle: str, *fields: str | None) -> bool:
    """Case-insensitive substring search over several fields; an empty needle matches all."""
    return not needle or needle in " ".join(f for f in fields if f).casefold()
