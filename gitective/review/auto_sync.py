"""One synchronisation round: base, profile, own MRs and desktop notifications (CH-05, CH-13, NO-04).

Runs in a background thread; the interface only shows its outcome.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from gitective.database.store import Store
from gitective.database.sync import MR_OVERLAP, ForgeData
from gitective.forge.errors import ForgeError
from gitective.forge.models import MergeRequest
from gitective.review.mr_evaluation import evaluate_all
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
from gitective.review.rules import RuleSet
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
    the Merger profile only ("my MR merged" for every profile, NO-09), never at
    the very first synchronisation, and new
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
        state = store.sync_state(f"mr:{project.id}")
        # A merge new to the base was read by this round, so it was updated after the previous one:
        # only those MRs are decoded, not the whole history.
        changed = datetime.fromtimestamp(state[1], timezone.utc) - MR_OVERLAP if state else None
        try:
            mrs = data.merge_requests(project.id, now_local(), state="merged", updated_after=changed)
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
    if not first:
        others = profile.merger and settings.notify_merges
        if others or settings.notify_own_merged:
            notices += merge_notices(before, fresh, profile.user, people, others, settings.notify_own_merged)
        if profile.merger and settings.notify_assigned and had_mine:
            notices += role_notices(previous_roles, mine, people)
    if notices:
        notices = _with_scores(data, notices, projects, settings, people, errors)
    store.set_meta(NOTIFIED_ONCE, "1")
    return SyncOutcome(profile, mine, notices, errors)


def _with_scores(
    data: ForgeData,
    notices: list[Notice],
    projects: Sequence[TrackedProject],
    settings: Settings,
    people: PersonDirectory,
    errors: list[ForgeError],
) -> list[Notice]:
    """Score of each notified MR (NO-03); without it a notification keeps its type color."""
    tracked = {p.id: p for p in projects}
    pairs = [(tracked.get(n.mr.project_id) or TrackedProject(id=n.mr.project_id, path=n.repo), n.mr) for n in notices]
    try:
        evaluations = evaluate_all(data, pairs, RuleSet.from_settings(settings), people,
                                   workers=settings.parallel_requests)
    except ForgeError as exc:
        errors.append(exc)
        return notices
    return [replace(n, score=e.score) for n, e in zip(notices, evaluations)]
