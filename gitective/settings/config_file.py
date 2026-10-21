"""Load and save config.json, with defaults for every parameter."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any

# Application root: the folder holding main.py, config.json and gitective.db.
APP_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "gitective.db"

# Fixed criteria (RC-03 to RC-06); custom rules are identified by their own id.
FIXED_CRITERIA = ("ticket", "self_merge", "pipeline", "assignee")
STATS_VIEWS = ("person", "repo")
THEMES = ("default", "light", "dark", "win95", "matrix")
REFRESH_RANGE = (1, 120)  # automatic synchronisation period, in minutes (CH-13)
DRAFT_MODES = ("all", "exclude", "only")  # drafts filter (FI-17)
PAGE_SIZES = (20, 50, 100)
# Branch states (BR-04), in priority order; the default filter hides deleted branches (BR-06).
BRANCH_STATES = ("deleted", "merged", "dead", "active")
DEFAULT_BRANCH_STATES = ["active", "dead", "merged"]
DEFAULT_BRANCH_EXCLUDE = r"^(main|master|develop.*)$"
PARALLEL_RANGE = (1, 16)

# Fields a custom rule can inspect (RP-02).
RULE_FIELDS = {
    "title": "Titre",
    "description": "Description",
    "source_branch": "Branche source",
    "target_branch": "Branche cible",
    "commits": "Messages des commits",
}
RULE_MODES = {"match": "Doit correspondre", "no_match": "Ne doit pas correspondre"}


def new_rule_id() -> str:
    return "r_" + uuid.uuid4().hex[:8]


@dataclass
class CustomRule:
    """User-defined regex check on one field of a merge request (RP-01)."""

    name: str
    field: str = "title"
    pattern: str = ""
    mode: str = "match"
    weight: float = 25.0
    active: bool = True
    id: str = dc_field(default_factory=new_rule_id)


def default_rules() -> list[CustomRule]:
    """Pre-filled rules replacing the former RC-01 and RC-02 (RP-07)."""
    return [
        CustomRule(name="Titre conforme", field="title", id="r_title"),
        CustomRule(name="Lien ticket", field="description", id="r_link"),
    ]


@dataclass
class TrackedProject:
    """A repository selected for inspection, with its watched branch."""

    id: int
    path: str
    web_url: str = ""
    branch: str = ""
    ci_expected: bool = False  # RC-05 applies only when the repository runs a CI (SD-08)


@dataclass
class Person:
    """A real person owning one or more GitLab accounts and Git identities."""

    name: str
    account_ids: list[int] = dc_field(default_factory=list)
    git_identities: list[str] = dc_field(default_factory=list)


@dataclass
class Filters:
    """Last filters used in the Merge Requests tab."""

    state: str = "merged"
    since_yesterday: bool = True
    date_from: str = ""
    date_to: str = ""
    total: bool = False  # "Total": no date limit (FI-19)
    authors: list[str] = dc_field(default_factory=list)
    mergers: list[str] = dc_field(default_factory=list)
    assignees: list[str] = dc_field(default_factory=list)
    reviewers: list[str] = dc_field(default_factory=list)
    drafts: str = "all"
    repos: list[int] = dc_field(default_factory=list)
    page_size: int = 20


@dataclass
class BranchFilters:
    """Last filters of the Branches tab (BR-06); the name search is not remembered."""

    authors: list[str] = dc_field(default_factory=list)
    repos: list[int] = dc_field(default_factory=list)
    states: list[str] = dc_field(default_factory=lambda: list(DEFAULT_BRANCH_STATES))


@dataclass
class TagFilters:
    """Last filters of the Tags tab (TG-04); "Total" (no date limit) by default."""

    repos: list[int] = dc_field(default_factory=list)
    total: bool = True
    date_from: str = ""
    date_to: str = ""


@dataclass
class CompareLine:
    """A line of the Comparer sub-tab: a repository, a "current" tag or branch and a reference tag (TC-02)."""

    project_id: int = 0
    current: str = ""
    reference: str = ""
    id: str = dc_field(default_factory=lambda: uuid.uuid4().hex[:8])


TAG_VIEWS = ("browse", "compare")


@dataclass
class Settings:
    """Every user-editable parameter of the application."""

    gitlab_url: str = ""
    token: str = ""
    verify_ssl: bool = True
    projects: list[TrackedProject] = dc_field(default_factory=list)
    rules: list[CustomRule] = dc_field(default_factory=default_rules)
    link_regex: str = ""
    ticket_regex: str = ""
    weights: dict[str, float] = dc_field(default_factory=lambda: {c: 25.0 for c in FIXED_CRITERIA})
    # RC-06 "merged by the assignee" counts only when checked in the Config tab.
    assignee_rule: bool = False
    green_threshold: float = 100.0
    orange_threshold: float = 50.0
    people: list[Person] = dc_field(default_factory=list)
    theme: str = "default"
    # Automatic synchronisation period of the local base, in minutes (CH-13).
    sync_minutes: int = 5
    # Desktop notifications (NO-01); every new MR of anyone (NO-11) is off unless checked.
    notify_merges: bool = True
    notify_assigned: bool = True
    notify_own_merged: bool = True
    notify_new_mrs: bool = False
    # Width of the MR detail panel, in pixels (DE-02).
    detail_width: int = 420
    # View of the Statistics tab: "person" or "repo" (ST-01).
    stats_view: str = "person"
    # Simultaneous GitLab requests for per-commit / per-MR lookups (P1).
    parallel_requests: int = 6
    filters: Filters = dc_field(default_factory=Filters)
    # Branches tab (BR-04, BR-05): exclusion regex and age of a dead branch, in calendar days.
    branch_exclude_regex: str = DEFAULT_BRANCH_EXCLUDE
    dead_branch_days: int = 30
    branch_filters: BranchFilters = dc_field(default_factory=BranchFilters)
    tag_filters: TagFilters = dc_field(default_factory=TagFilters)
    # Tags tab: shown sub-tab and the lines of the Comparer sub-tab (TG-01, TC-02).
    tags_view: str = "browse"
    tag_compares: list[CompareLine] = dc_field(default_factory=list)
    # Column widths set by dragging, per table ("mr", "commits", "stats", "stats_repo", "branches", "tags").
    column_widths: dict[str, dict[str, int]] = dc_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        """Build settings from JSON, ignoring unknown keys and filling defaults."""
        base = cls()
        weights = {k: float(v) for k, v in (data.get("weights") or {}).items() if k in FIXED_CRITERIA}
        theme = data.get("theme", base.theme)
        rules = data.get("rules")
        return cls(
            gitlab_url=str(data.get("gitlab_url", "")),
            token=str(data.get("token", "")),
            verify_ssl=bool(data.get("verify_ssl", True)),
            projects=[TrackedProject(**_pick(p, TrackedProject)) for p in data.get("projects") or []],
            rules=[CustomRule(**_pick(r, CustomRule)) for r in rules] if rules is not None else base.rules,
            link_regex=str(data.get("link_regex", "")),
            ticket_regex=str(data.get("ticket_regex", "")),
            weights={**base.weights, **weights},
            green_threshold=float(data.get("green_threshold", base.green_threshold)),
            orange_threshold=float(data.get("orange_threshold", base.orange_threshold)),
            people=[Person(**_pick(p, Person)) for p in data.get("people") or []],
            theme=theme if theme in THEMES else base.theme,
            assignee_rule=bool(data.get("assignee_rule", False)),
            filters=_filters(data.get("filters")),
            parallel_requests=clamp_parallel(data.get("parallel_requests", base.parallel_requests)),
            # "overview_refresh" is the name used before the synchronisation covered every tab.
            sync_minutes=clamp_refresh(data.get("sync_minutes", data.get("overview_refresh", base.sync_minutes))),
            notify_merges=bool(data.get("notify_merges", True)),
            notify_assigned=bool(data.get("notify_assigned", True)),
            notify_own_merged=bool(data.get("notify_own_merged", True)),
            notify_new_mrs=bool(data.get("notify_new_mrs", False)),
            detail_width=clamp_width(data.get("detail_width", base.detail_width)),
            stats_view=data.get("stats_view") if data.get("stats_view") in STATS_VIEWS else base.stats_view,
            column_widths=_column_widths(data.get("column_widths")),
            branch_exclude_regex=str(data.get("branch_exclude_regex", base.branch_exclude_regex)),
            dead_branch_days=clamp_dead_days(data.get("dead_branch_days", base.dead_branch_days)),
            branch_filters=_branch_filters(data.get("branch_filters")),
            tag_filters=TagFilters(**_pick(_dict(data.get("tag_filters")), TagFilters)),
            tags_view=data.get("tags_view") if data.get("tags_view") in TAG_VIEWS else base.tags_view,
            tag_compares=[CompareLine(**_pick(_dict(c), CompareLine)) for c in data.get("tag_compares") or []
                          if isinstance(c, dict)],
        )

    @property
    def is_configured(self) -> bool:
        """True once the connection parameters are filled in."""
        return bool(self.gitlab_url and self.token)

    @property
    def active_rules(self) -> list[CustomRule]:
        return [r for r in self.rules if r.active]


def clamp_parallel(value: Any) -> int:
    """Number of simultaneous requests, forced into PARALLEL_RANGE."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = Settings.parallel_requests
    return max(PARALLEL_RANGE[0], min(PARALLEL_RANGE[1], number))


def clamp_dead_days(value: Any) -> int:
    """Age of a dead branch in calendar days, at least 1 (BR-04)."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return Settings.dead_branch_days


def clamp_width(value: Any) -> int:
    """Detail panel width in pixels, between 280 and 900; the default when unreadable."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = Settings.detail_width
    return max(280, min(900, number))


def clamp_refresh(value: Any) -> int:
    """Overview refresh period in minutes, forced into REFRESH_RANGE."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = Settings.sync_minutes
    return max(REFRESH_RANGE[0], min(REFRESH_RANGE[1], number))


def _filters(data: Any) -> Filters:
    filters = Filters(**_pick(data if isinstance(data, dict) else {}, Filters))
    if filters.drafts not in DRAFT_MODES:
        filters.drafts = "all"
    return filters


def _dict(data: Any) -> dict[str, Any]:
    return data if isinstance(data, dict) else {}


def _branch_filters(data: Any) -> BranchFilters:
    filters = BranchFilters(**_pick(_dict(data), BranchFilters))
    filters.states = [state for state in filters.states if state in BRANCH_STATES]
    return filters


def _column_widths(data: Any) -> dict[str, dict[str, int]]:
    """Saved column widths, ignoring malformed entries."""
    if not isinstance(data, dict):
        return {}
    return {str(t): {str(k): int(v) for k, v in w.items()} for t, w in data.items() if isinstance(w, dict)}


def _pick(data: dict[str, Any], cls: type) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k in cls.__dataclass_fields__}


def config_exists(path: Path = CONFIG_PATH) -> bool:
    """Tell whether config.json exists (absent means first launch)."""
    return path.exists()


def load(path: Path = CONFIG_PATH) -> Settings:
    """Read config.json; return defaults when the file is missing or unreadable."""
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return Settings()


def save(settings: Settings, path: Path = CONFIG_PATH) -> None:
    """Write config.json atomically (temporary file then rename)."""
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
