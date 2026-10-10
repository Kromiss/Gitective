"""Avatar download, disk cache and initials fallback."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from gitective.api.client import GitLabClient
from gitective.api.errors import GitLabError

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
    """Downloads avatars once and keeps them in the avatars/ folder.

    Unsupported formats (JPEG...) are remembered with an empty marker file
    so they are not downloaded again until the next refresh.
    """

    def __init__(self, folder: Path, client: GitLabClient | None) -> None:
        self.folder = folder
        self.client = client
        self._lock = threading.Lock()

    def _existing(self, user_id: int) -> Path | None:
        for ext in ("png", "gif", "none"):
            path = self.folder / f"{user_id}.{ext}"
            if path.exists():
                return path
        return None

    def path_for(self, user_id: int, avatar_url: str | None = None) -> Path | None:
        """Local image path for a user, or None when an initials badge is needed."""
        with self._lock:
            found = self._existing(user_id)
        if found is not None:
            return None if found.suffix == ".none" else found
        if self.client is None:
            return None
        try:
            url = avatar_url or self.client.get_user(user_id).avatar_url
            data = self.client.download(url) if url else b""
        except (GitLabError, ValueError):
            return None  # Unreachable avatar: badge fallback, not an error.
        fmt = image_format(data)
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            target = self.folder / f"{user_id}.{fmt or 'none'}"
            target.write_bytes(data if fmt else b"")
        return target if fmt else None

    def clear(self) -> None:
        """Forget cached avatars so they are downloaded again (AV-07)."""
        with self._lock:
            if self.folder.exists():
                for path in self.folder.iterdir():
                    if path.suffix in (".png", ".gif", ".none"):
                        path.unlink(missing_ok=True)
