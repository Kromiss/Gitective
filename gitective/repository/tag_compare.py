"""Comparer sub-tab: the MRs and commits between two references of a repository (section 12.1).

The Git graph decides, never the dates: the commits of `reference..current`
are read once per couple of SHAs (TC-05, TC-10), then linked to their merged
MRs, from the base first and through one request per unknown commit (TC-06).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from gitective.shared.i18n import t
from gitective.database.store import Store
from gitective.database.sync import ForgeData
from gitective.forge.models import Commit, MergeRequest
from gitective.review.mr_evaluation import evaluate_all
from gitective.review.rules import Evaluation, RuleSet
from gitective.settings.config_file import TrackedProject
from gitective.shared.dates import format_datetime
from gitective.shared.parallel import run_parallel
from gitective.shared.people import PersonDirectory
from gitective.shared.repo_names import short_names

Progress = Callable[[int, int], None]
MrKey = tuple[int, int]


class CompareError(Exception):
    """A reference of the line no longer exists (TC-07)."""


@dataclass(frozen=True)
class Ref:
    """A tag or a branch of a repository, as stored by the synchronisation (BR-10, TG-08)."""

    name: str
    sha: str
    date: datetime | None
    is_branch: bool = False


def ref_choices(store: Store, project_id: int) -> tuple[list[Ref], list[Ref]]:
    """(tags newest first, branches newest first) of a repository, deleted ones left out (TC-03)."""
    def newest_first(refs: list[Ref]) -> list[Ref]:
        return sorted(refs, key=lambda r: r.date.timestamp() if r.date else 0.0, reverse=True)

    tags = [Ref(t.name, t.commit_sha, t.committed_date) for _, t, deleted in store.tags([project_id])
            if deleted is None and t.commit_sha]
    branches = [Ref(b.name, b.commit_sha, b.committed_date, True) for _, b, deleted in store.branches([project_id])
                if deleted is None and b.commit_sha]
    return newest_first(tags), newest_first(branches)


@dataclass(frozen=True)
class Side:
    """Merged MRs and commits without MR found in one direction of the comparison."""

    mrs: tuple[MergeRequest, ...] = ()
    orphans: tuple[Commit, ...] = ()
    commits: int = 0

    @property
    def empty(self) -> bool:
        return not self.commits


@dataclass(frozen=True)
class Comparison:
    """Result of a line: what `current` brings over `reference`, and the divergence (TC-07, TC-08)."""

    project: TrackedProject
    current: Ref
    reference: Ref
    ahead: Side
    behind: Side  # commits of the reference missing from current: divergence
    evaluations: tuple[Evaluation, ...] = field(default=())

    @property
    def average(self) -> float | None:
        scores = [e.score for e in self.evaluations]
        return sum(scores) / len(scores) if scores else None


def _merged_index(store: Store, project_id: int) -> tuple[dict[str, MergeRequest], dict[str, MergeRequest]]:
    """Merged MRs of the base by merge / squash / head SHA, and by the SHA of each stored MR commit."""
    by_own: dict[str, MergeRequest] = {}
    by_iid: dict[int, MergeRequest] = {}
    for mr in store.merge_requests(project_id, state="merged"):
        by_iid[mr.iid] = mr
        for sha in (mr.merge_commit_sha, mr.squash_commit_sha, mr.sha):
            if sha:
                by_own[sha] = mr
    by_commit = {sha: by_iid[iid] for (_, iid), shas in store.mr_commit_shas([project_id]).items()
                 if iid in by_iid for sha in shas}
    return by_own, by_commit


def link_commits(
    data: ForgeData,
    project_id: int,
    commits: Sequence[Commit],
    workers: int = 1,
    progress: Progress | None = None,
) -> dict[str, list[MergeRequest]]:
    """Merged MRs of each commit: from the base without request, else one stored request per commit (TC-06)."""
    by_own, by_commit = _merged_index(data.store, project_id)
    links: dict[str, list[MergeRequest]] = {}
    pending: list[str] = []
    for commit in commits:
        mr = by_own.get(commit.id) or by_commit.get(commit.id)
        if mr is not None:
            links[commit.id] = [mr]
        else:
            pending.append(commit.id)

    def ask(sha: str) -> list[MergeRequest]:
        # Open or closed MRs that also contain the commit did not deliver it.
        return [m for m in data.commit_mrs(project_id, sha) if m.state == "merged"]

    for sha, mrs in zip(pending, run_parallel(ask, pending, workers, progress)):
        links[sha] = mrs
    return links


def build_side(commits: Sequence[Commit], links: dict[str, list[MergeRequest]]) -> Side:
    """MRs counted once each, newest merge first; commits without merged MR apart."""
    mrs: dict[MrKey, MergeRequest] = {}
    orphans = []
    for commit in commits:
        found = links.get(commit.id, [])
        if not found:
            orphans.append(commit)
        for mr in found:
            mrs.setdefault((mr.project_id, mr.iid), mr)
    ordered = sorted(mrs.values(), key=lambda m: m.merged_at.timestamp() if m.merged_at else 0.0, reverse=True)
    return Side(mrs=tuple(ordered), orphans=tuple(orphans), commits=len(commits))


def resolve(store: Store, project_id: int, current: str, reference: str) -> tuple[Ref, Ref]:
    """Current: a tag, else a branch; reference: a tag (TC-02). Raises CompareError when one is gone."""
    tags, branches = ref_choices(store, project_id)
    by_tag = {r.name: r for r in tags}
    cur = by_tag.get(current) or next((b for b in branches if b.name == current), None)
    ref = by_tag.get(reference)
    for name, found in ((current, cur), (reference, ref)):
        if found is None:
            raise CompareError(f"{name} introuvable")
    assert cur is not None and ref is not None
    return cur, ref


def compare(
    data: ForgeData,
    project: TrackedProject,
    current: str,
    reference: str,
    rules: RuleSet,
    people: PersonDirectory,
    workers: int = 1,
    progress: Progress | None = None,
) -> Comparison:
    """Everything a comparison line shows (TC-05..TC-08); a moved tag or branch head gives new SHAs (TC-10)."""
    cur, ref = resolve(data.store, project.id, current, reference)
    ahead = data.commits_between(project.id, ref.sha, cur.sha)
    behind = data.commits_between(project.id, cur.sha, ref.sha)
    links = link_commits(data, project.id, [*ahead, *behind], workers, progress)
    ahead_side, behind_side = build_side(ahead, links), build_side(behind, links)
    evaluations = evaluate_all(data, [(project, mr) for mr in ahead_side.mrs], rules, people, workers=workers)
    return Comparison(project, cur, ref, ahead_side, behind_side, tuple(evaluations))


def copied_text(comparisons: Iterable[Comparison], people: PersonDirectory) -> str:
    """Markdown of every computed line: a title per line, its MRs, then its commits without MR (TC-09)."""
    comparisons = list(comparisons)
    names = short_names(c.project.path for c in comparisons)
    blocks = []
    for c in comparisons:
        lines = [t("## {repo} : {reference} → {current}", repo=names[c.project.path],
                   reference=c.reference.name, current=c.current.name), ""]
        lines += [f"- !{mr.iid} {mr.title} — {people.for_user(mr.author).name}" for mr in c.ahead.mrs]
        if c.ahead.orphans:
            lines += ["", t("Commits sans MR :")]
            lines += [f"- {o.short_id} {o.title} — {people.for_git(o.author_name, o.author_email).name}"
                      for o in c.ahead.orphans]
        if not c.ahead.commits:
            lines.append(t("Aucune différence."))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def ref_date(ref: Ref) -> str:
    return format_datetime(ref.date)
