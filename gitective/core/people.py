"""Map GitLab accounts and Git identities to real people."""

from __future__ import annotations

from dataclasses import dataclass

from gitective.api.models import User
from gitective.config.settings import Person


@dataclass(frozen=True)
class PersonRef:
    """A resolved person: stable key used for filters and stats, display name."""

    key: str
    name: str
    avatar_user_id: int | None = None


class PersonDirectory:
    """Resolve accounts to people according to the configured mapping.

    An account without mapping is treated as a person of its own (PE-07).
    """

    def __init__(self, people: list[Person]) -> None:
        self._by_account: dict[int, PersonRef] = {}
        self._by_identity: dict[str, PersonRef] = {}
        for person in people:
            # Most recent account = highest GitLab user ID (AV-05).
            avatar_id = max(person.account_ids) if person.account_ids else None
            ref = PersonRef(key=f"p:{person.name.casefold()}", name=person.name, avatar_user_id=avatar_id)
            for account_id in person.account_ids:
                self._by_account[int(account_id)] = ref
            for identity in person.git_identities:
                self._by_identity[identity.strip().casefold()] = ref

    def for_user(self, user: User) -> PersonRef:
        """Person owning a GitLab account."""
        return self._by_account.get(user.id) or PersonRef(key=f"u:{user.id}", name=user.name, avatar_user_id=user.id)

    def for_git(self, name: str, email: str) -> PersonRef:
        """Person matching a Git author name or e-mail (case-insensitive)."""
        for identity in (email, name):
            ref = self._by_identity.get(identity.strip().casefold())
            if ref:
                return ref
        key = f"g:{(email or name).strip().casefold()}"
        return PersonRef(key=key, name=name or email)
