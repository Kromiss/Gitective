"""What the MR detail panel shows: merge readiness, pipeline, discussions, changed files (6.6)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from gitective.forge.models import ChangedFile, Discussion, Job, MergeRequest
from gitective.database.sync import MrDetailData
from gitective.review.rules import KO, NA, OK

WARN = "warn"
FAILED = {"failed", "canceled"}
RUNNING = {"running", "pending", "created", "waiting_for_resource", "preparing", "scheduled", "manual"}
LOG_LINES = 8
FILES_SHOWN = 5
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")
SECTION = re.compile(r"section_(start|end):\d+:\S+\r?")


@dataclass(frozen=True)
class ReadinessItem:
    """One line of the "Prête à merger ?" block: OK, WARN, KO or NA (no data)."""

    status: str
    text: str
    note: str = ""


@dataclass(frozen=True)
class Readiness:
    ready: bool
    items: tuple[ReadinessItem, ...]


def readiness(mr: MergeRequest, detail: MrDetailData, target_branch: str = "") -> Readiness | None:
    """Merge readiness of an open MR (DE-05); None for merged or closed MRs.

    "Prête" follows GitLab's own verdict (detailed merge status "mergeable"),
    so the project's merge settings decide; the lines explain why it is not.
    """
    state = detail.state
    if mr.state != "opened" or state is None:
        return None
    status = state.merge_status
    items = [ReadinessItem(KO, "Conflits à résoudre") if state.has_conflicts else ReadinessItem(OK, "Pas de conflit")]
    items.append(_pipeline_item(detail))
    unresolved = len(unresolved_discussions(detail.discussions))
    if unresolved:
        blocking = status == "discussions_not_resolved" or not state.blocking_discussions_resolved
        items.append(ReadinessItem(KO if blocking else WARN, f"{unresolved} discussion(s) non résolue(s)"))
    else:
        items.append(ReadinessItem(OK, "Discussions résolues"))
    items.append(_approval_item(detail, status))
    if state.behind_by:
        items.append(ReadinessItem(KO if status == "need_rebase" else WARN,
                                   f"{state.behind_by} commit(s) de retard sur {target_branch or mr.target_branch}"))
    if mr.draft:
        items.append(ReadinessItem(KO, "MR en brouillon"))
    return Readiness(ready=status == "mergeable" and not mr.draft, items=tuple(items))


def _pipeline_item(detail: MrDetailData) -> ReadinessItem:
    pipeline = detail.state.pipeline if detail.state else None
    if pipeline is not None:
        failed = [j.name for j in detail.jobs if j.status in FAILED]
        if pipeline.status == "success":
            return ReadinessItem(OK, "Pipeline vert")
        if pipeline.status in FAILED:
            return ReadinessItem(KO, "Pipeline en échec", ", ".join(failed[:3]))
        if pipeline.status in RUNNING:
            return ReadinessItem(WARN, "Pipeline en cours")
        return ReadinessItem(WARN, f"Pipeline : {pipeline.status}")
    # CIs that only publish commit statuses (e.g. Jenkins): latest status of each name.
    latest = {s.name: s for s in sorted(detail.statuses, key=lambda s: s.created_at) if not s.allow_failure}
    if not latest:
        return ReadinessItem(NA, "Aucun pipeline")
    bad = sorted(n for n, s in latest.items() if s.status in FAILED)
    if bad:
        return ReadinessItem(KO, "CI en échec", ", ".join(bad))
    if any(s.status != "success" for s in latest.values()):
        return ReadinessItem(WARN, "CI en cours")
    return ReadinessItem(OK, "CI verte", ", ".join(sorted(latest)))


def _approval_item(detail: MrDetailData, status: str) -> ReadinessItem:
    approvals = detail.approvals
    names = ", ".join(u.name for u in approvals.approved_by) if approvals else ""
    count = len(approvals.approved_by) if approvals else 0
    if approvals and approvals.required:
        missing = approvals.left if approvals.left is not None else max(0, approvals.required - count)
        text = f"Approuvée {approvals.required - missing} / {approvals.required}"
        return ReadinessItem(KO if missing else OK, text, names)
    if status == "not_approved":
        return ReadinessItem(KO, "Approbation manquante", names)
    # Without required approvals (or an edition that does not tell): who approved, no total (DE-13).
    return ReadinessItem(OK if count else NA, f"Approuvée par {count} personne(s)" if count else "Pas d'approbation", names)


def unresolved_discussions(discussions: Sequence[Discussion]) -> list[Discussion]:
    return [d for d in discussions if not d.resolved]


def discussion_place(discussion: Discussion) -> str:
    """"File.java:88", or "description" for a general comment (DE-09)."""
    if not discussion.path:
        return "description"
    name = discussion.path.rsplit("/", 1)[-1]
    return f"{name}:{discussion.line}" if discussion.line else name


def first_lines(text: str, count: int = 2, width: int = 160) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()][:count]
    return "\n".join(line if len(line) <= width else line[: width - 1] + "…" for line in lines)


def log_tail(log: str, lines: int = LOG_LINES) -> str:
    """Last meaningful lines of a CI log, without colors and GitLab section markers (DE-08)."""
    cleaned = [SECTION.sub("", ANSI.sub("", line)).rstrip() for line in log.replace("\r\n", "\n").split("\n")]
    meaningful = [line for line in cleaned if line.strip() and not line.startswith(("Cleaning up", "Uploading"))]
    return "\n".join(meaningful[-lines:])


def failed_jobs(jobs: Sequence[Job]) -> list[Job]:
    return [j for j in jobs if j.status in FAILED]


def top_files(files: Sequence[ChangedFile], count: int = FILES_SHOWN) -> tuple[list[ChangedFile], int]:
    """Files sorted by size of change, and how many more are hidden (DE-10)."""
    ordered = sorted(files, key=lambda f: (-(f.added + f.removed), f.path))
    return ordered[:count], max(0, len(ordered) - count)


def short_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{seconds:.0f} s"
    return f"{seconds / 60:.0f} min"
