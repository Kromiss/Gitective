"""Which evaluated MRs the Merge Requests tab shows, for the current filters (FI-08..FI-17)."""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence

from gitective.review.rules import Evaluation
from gitective.settings.filter_state import DRAFT_STATES, PEOPLE_STATES, FilterState
from gitective.shared.people import PersonRef
from gitective.shared.search import matches

NOBODY = "none"  # filter entry for MRs without assignee / reviewer (FI-14, FI-15)
ROLE_LABELS = {"assignees": "Non assignée", "reviewers": "Sans relecteur"}


def names(people: Iterable[PersonRef]) -> str:
    return ", ".join(p.name for p in people)


def people_filter(people: Sequence[PersonRef], wanted: set[str]) -> bool:
    """Empty selection keeps everything; NOBODY keeps MRs without anyone in that role."""
    if not wanted:
        return True
    return any(p.key in wanted for p in people) or (NOBODY in wanted and not people)


def visible(evaluations: Iterable[Evaluation], filters: FilterState, needle: str = "") -> list[Evaluation]:
    """MRs kept by the author, merger, assignee, reviewer, draft and text filters.

    The merger filter applies to merged MRs only (FI-13), the assignee and
    reviewer filters to merged, open and closed MRs (FI-14, FI-15), the draft
    filter to open and closed MRs (FI-17). Every filter combines (AND).
    """
    state = filters.state
    authors = set(filters.authors)
    mergers = set(filters.mergers) if state == "merged" else set()
    assignees = set(filters.assignees) if state in PEOPLE_STATES else set()
    reviewers = set(filters.reviewers) if state in PEOPLE_STATES else set()
    drafts = filters.drafts if state in DRAFT_STATES else "all"
    needle = needle.strip().casefold()
    return [e for e in evaluations
            if (not authors or e.author.key in authors)
            and (not mergers or (e.merger is not None and e.merger.key in mergers))
            and people_filter(e.assignees, assignees) and people_filter(e.reviewers, reviewers)
            and (drafts == "all" or e.mr.draft == (drafts == "only"))
            and matches(needle, e.mr.title, e.mr.description, e.author.name, e.merger.name if e.merger else None,
                        e.project_path, e.mr.source_branch, e.mr.target_branch, names(e.assignees),
                        names(e.reviewers))]


def people_choices(evaluations: Iterable[Evaluation], role: str, me_key: str | None,
                   me_name: str) -> list[tuple[str, str]]:
    """Assignee or reviewer filter entries: the user first as "Moi", everyone seen, then nobody (AM-07)."""
    seen = {p.key: p.name for e in evaluations for p in getattr(e, role)}
    items = []
    if me_key:
        items.append((me_key, f"Moi ({me_name})"))
        seen.pop(me_key, None)
    items += sorted(seen.items(), key=lambda i: i[1].casefold())
    items.append((NOBODY, ROLE_LABELS[role]))
    return items


def people_cell(people: Sequence[PersonRef], me_key: str | None) -> tuple[bool, str] | str:
    """Grid value of the Assignés / Relecteurs columns: (includes the user, the other names)."""
    if not people:
        return ""
    return any(p.key == me_key for p in people), names(p for p in people if p.key != me_key)


def step_selection(keys: Sequence[Hashable], selected: Hashable, step: int, page_size: int) -> tuple[int, int] | None:
    """Arrow keys: (index in the filtered list, page number) of the neighbouring MR; None when not listed (DE-01).

    The selection stops at both ends of the list instead of wrapping around.
    """
    if selected not in keys:
        return None
    index = max(0, min(len(keys) - 1, list(keys).index(selected) + step))
    return index, index // page_size + 1
