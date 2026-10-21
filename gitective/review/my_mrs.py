"""Token owner, own open MRs, "new" flags and notifications (5.7, 5.8, 6.4, 6.5)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from gitective.forge.models import MergeRequest, User
from gitective.database.store import RoleKey, Store, decode, encode
from gitective.settings.config_file import TrackedProject
from gitective.shared.people import PersonDirectory

ASSIGNEE, REVIEWER, AUTHOR = "assignee", "reviewer", "author"
MyMr = tuple[MergeRequest, frozenset[str]]
Key = tuple[int, int]


def save_user(store: Store, user: User) -> None:
    """Last known token owner, used when the instance is unreachable (PR-07)."""
    store.set_meta("token_user", json.dumps(encode(user)))


def load_user(store: Store) -> User | None:
    text = store.get_meta("token_user")
    if text:
        return decode(User, json.loads(text))
    # Bases written before v1.15 kept the user inside the Developer / Merger profile.
    old = json.loads(store.get_meta("profile") or "{}").get("user")
    return decode(User, old) if old else None


def authored_open_mrs(store: Store, project_ids: Iterable[int], people: PersonDirectory,
                      me: User | None) -> list[MergeRequest]:
    """Open MRs of the tracked repositories written by the user, any of their accounts (AM-09)."""
    if me is None:
        return []
    mine = people.for_user(me).key
    return [mr for pid in project_ids for mr in store.merge_requests(pid, state="opened")
            if people.for_user(mr.author).key == mine]


# ---------------------------------------------------------------- Own open MRs


def role_keys(items: Iterable[MyMr]) -> set[RoleKey]:
    """(project, iid, role) of the MRs ready to merge; drafts are left out (FI-08)."""
    return {(mr.project_id, mr.iid, role) for mr, roles in items if not mr.draft for role in roles}


@dataclass(frozen=True)
class BadgeCounts:
    """Figures of one badge (BA-01)."""

    total: int
    new: int
    drafts: int


def badge_counts(items: Sequence[MyMr], seen: set[RoleKey], role: str) -> BadgeCounts:
    """Open MRs where the user has `role`, drafts apart; "new" = role not seen yet (AM-04)."""
    mine = [mr for mr, roles in items if role in roles]
    ready = [mr for mr in mine if not mr.draft]
    new = sum(1 for mr in ready if (mr.project_id, mr.iid, role) not in seen)
    return BadgeCounts(total=len(ready), new=new, drafts=len(mine) - len(ready))


def author_counts(mrs: Sequence[MergeRequest]) -> BadgeCounts:
    """Own open MRs, drafts apart; the author badge has no "new" dot (BA-01)."""
    ready = sum(1 for mr in mrs if not mr.draft)
    return BadgeCounts(total=ready, new=0, drafts=len(mrs) - ready)


def unseen_keys(items: Sequence[MyMr], seen: set[RoleKey]) -> set[RoleKey]:
    return role_keys(items) - seen


def badge_tip(counts: BadgeCounts, word: str) -> str:
    """Badge tooltip, e.g. "3 assignée(s), dont 1 nouvelle(s) ; 1 brouillon(s)" (BA-01)."""
    tip = f"{counts.total} {word}"
    if counts.new:
        tip += f", dont {counts.new} nouvelle(s)"
    if counts.drafts:
        tip += f" ; {counts.drafts} brouillon(s)"
    return tip + "\nClic : voir ces MR ouvertes"


def seen_on_click(items: Sequence[MyMr], seen: set[RoleKey], role: str) -> set[RoleKey]:
    """Role keys a badge click marks as seen: the unseen ones of that role only (AM-04)."""
    return {key for key in unseen_keys(items, seen) if key[2] == role}


def new_count(items: Sequence[MyMr], seen: set[RoleKey]) -> int:
    """MRs with at least one new role, counted once (BA-03)."""
    return len({(p, i) for p, i, _ in unseen_keys(items, seen)})


# ---------------------------------------------------------------- Desktop notifications


@dataclass(frozen=True)
class Notice:
    """One desktop notification (NO-03)."""

    kind: str  # "merge", "own" (my MR merged, NO-09), "role" or "new" (any new MR, NO-11)
    title: str
    mr: MergeRequest
    repo: str
    author: str
    merger: str = ""
    score: float | None = None  # process score of the MR, shown and used as the color (NO-03)
    roles: frozenset[str] = frozenset()  # assignee / reviewer, for a "role" notice


def role_title(roles: Iterable[str]) -> str:
    """Notification title naming the role (NO-08)."""
    roles = set(roles)
    if roles == {ASSIGNEE, REVIEWER}:
        return "MR assignée + relecture"
    return "MR assignée" if ASSIGNEE in roles else "Relecture demandée"


def merge_notices(
    before: set[tuple[int, int]],
    synced: Iterable[tuple[TrackedProject, MergeRequest]],
    me: User | None,
    people: PersonDirectory,
    others: bool = True,
    own: bool = True,
) -> list[Notice]:
    """MRs merged since the previous synchronisation, own merges excluded (NO-04).

    `others`: any new merge (NO-01); `own`: the user's own MRs merged by someone
    else (NO-09), which then get this notification only.
    """
    mine = people.for_user(me).key if me else None
    notices = []
    for project, mr in synced:
        if mr.state != "merged" or (mr.project_id, mr.iid) in before or mr.merged_by is None:
            continue
        merger = people.for_user(mr.merged_by)
        if merger.key == mine:
            continue
        author = people.for_user(mr.author)
        if mine is not None and author.key == mine:
            if own:
                notices.append(Notice("own", "Votre MR a été mergée", mr, project.path, author.name, merger.name))
        elif others:
            notices.append(Notice("merge", "Nouveau merge", mr, project.path, author.name, merger.name))
    return sorted(notices, key=lambda n: n.mr.merged_at or n.mr.created_at)


def role_notices(previous: set[RoleKey], items: Sequence[MyMr], people: PersonDirectory) -> list[Notice]:
    """MRs where the user just became assignee or reviewer, or that just left draft (NO-01, NO-08)."""
    added: dict[tuple[int, int], set[str]] = {}
    for project_id, iid, role in role_keys(items) - previous:
        added.setdefault((project_id, iid), set()).add(role)
    by_key = {(mr.project_id, mr.iid): mr for mr, _ in items}
    notices = [Notice("role", role_title(roles), by_key[key], by_key[key].project_path,
                      people.for_user(by_key[key].author).name, roles=frozenset(roles))
               for key, roles in added.items()]
    return sorted(notices, key=lambda n: n.mr.created_at)


def open_ready_keys(store: Store, project_ids: Iterable[int]) -> set[Key]:
    """Stored open MRs that are not drafts, before a synchronisation (NO-11)."""
    return {(mr.project_id, mr.iid) for pid in project_ids for mr in store.merge_requests(pid, state="opened")
            if not mr.draft}


def new_mr_notices(
    before: set[Key],
    synced: Iterable[tuple[TrackedProject, MergeRequest]],
    me: User | None,
    people: PersonDirectory,
    skip: set[Key],
) -> list[Notice]:
    """Open MRs ready to merge that were not before: just created, or just out of draft (NO-11).

    The user's own MRs are left out, and so are those in `skip` (already notified as
    assigned or in review).
    """
    mine = people.for_user(me).key if me else None
    notices = []
    for project, mr in synced:
        key = (mr.project_id, mr.iid)
        if mr.state != "opened" or mr.draft or key in before or key in skip:
            continue
        author = people.for_user(mr.author)
        if author.key != mine:
            notices.append(Notice("new", "Nouvelle MR", mr, project.path, author.name))
    return sorted(notices, key=lambda n: n.mr.created_at)
