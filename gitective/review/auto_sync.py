"""One synchronisation round: base, profile, own MRs and desktop notifications (CH-05, CH-13, NO-04).

Runs in a background thread; the interface only shows its outcome.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from gitective.database.store import Store
from gitective.database.sync import ForgeData
from gitective.forge.errors import ForgeError
from gitective.forge.models import MergeRequest
from gitective.review.profile import (
    MyMr,
    Notice,
    Profile,
    compute_profile,
    merge_notices,
    role_keys,
    role_notices,
    save_profile,
)
from gitective.settings.config_file import Settings, TrackedProject
from gitective.shared.dates import now_local
from gitective.shared.people import PersonDirectory

NOTIFIED_ONCE = "notified_once"  # meta key: a first synchronisation already happened (no notification before)


@dataclass
class SyncOutcome:
    """What a synchronisation brings back to the interface."""

    profile: Profile
    my_mrs: list[MyMr] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    errors: list[ForgeError] = field(default_factory=list)


def synchronise(
    data: ForgeData,
    store: Store,
    projects: Sequence[TrackedProject],
    settings: Settings,
    people: PersonDirectory,
    previous: Profile,
) -> SyncOutcome:
    """Bring the base up to date, recompute the profile, read the own MRs and list what to notify.

    A failing project, profile or MR list is reported in `errors`, never fatal
    (ER-03): the last known profile and MRs are kept. Notifications are for
    the Merger profile only, never at the very first synchronisation, and new
    merges only on repositories already in the base (otherwise their whole
    history would look new).
    """
    known = [p for p in projects if store.sync_state(f"mr:{p.id}") is not None]
    known_ids = {p.id for p in known}
    before = store.merged_keys(known_ids)
    first = store.get_meta(NOTIFIED_ONCE) is None
    had_mine = store.get_meta("my_mrs_synced") is not None
    previous_roles = role_keys(store.my_mrs())
    data.new_session()
    errors: list[ForgeError] = []
    fresh: list[tuple[TrackedProject, MergeRequest]] = []
    for project in projects:
        try:
            mrs = data.merge_requests(project.id, now_local())
        except ForgeError as exc:
            errors.append(exc)
            continue
        if project.id in known_ids:
            fresh += [(project, mr) for mr in mrs]
    profile = previous
    try:
        user = data.client.current_user() if data.client else None
        if user is not None:
            profile = compute_profile(data, user, projects, settings.parallel_requests)
            save_profile(store, profile)
    except ForgeError as exc:
        errors.append(exc)
    mine: list[MyMr] = []
    if profile.merger and profile.user is not None:
        try:
            mine = data.my_open_mrs(profile.user.id)
        except ForgeError as exc:
            errors.append(exc)
            mine = store.my_mrs()
    notices: list[Notice] = []
    if profile.merger and not first:
        if settings.notify_merges:
            notices += merge_notices(before, fresh, profile.user, people)
        if settings.notify_assigned and had_mine:
            notices += role_notices(previous_roles, mine, people)
    store.set_meta(NOTIFIED_ONCE, "1")
    return SyncOutcome(profile, mine, notices, errors)
