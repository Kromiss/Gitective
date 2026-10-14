"""Avatars from the local store, and the initials badge fallback (AV-01..AV-07)."""

from __future__ import annotations

import hashlib

from gitective.forge.errors import ForgeError
from gitective.database.sync import ForgeData

# Colors for initials badges; chosen by a stable hash of the person key.
BADGE_COLORS = ("#B8542A", "#2B3A5C", "#5B4A8A", "#2F7A57", "#8A3D5C", "#2F8F8A", "#7A5A1F", "#3D6E9E")


def initials(name: str) -> str:
    """Up to two uppercase initials from a display name."""
    parts = [p for p in name.replace(".", " ").replace("-", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def badge_color(key: str) -> str:
    """Stable color for a person key (AV-04)."""
    digest = hashlib.md5(key.encode("utf-8")).digest()
    return BADGE_COLORS[digest[0] % len(BADGE_COLORS)]


def image_format(data: bytes) -> str | None:
    """'png' or 'gif' when Tk can display the bytes, else None (AV-03)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


class AvatarStore:
    """Avatars kept in the local store (AV-07), downloaded again once per session.

    Unsupported formats (JPEG...) are stored as empty content so the badge
    is shown without downloading them again until the next refresh.
    """

    def __init__(self, data: ForgeData) -> None:
        self.data = data

    def image_for(self, user_id: int, avatar_url: str | None = None) -> bytes | None:
        """PNG or GIF bytes of a user's avatar, or None when an initials badge is needed."""
        try:
            content = self.data.avatar(user_id, avatar_url)
        except (ForgeError, ValueError):
            return None  # Unreachable avatar: badge fallback, not an error.
        return content if content and image_format(content) else None
