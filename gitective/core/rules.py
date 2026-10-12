"""Process rules: custom regex rules, RC-03, RC-04, RC-05 and the weighted score."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from gitective.api.models import Commit, CommitStatus, MergeRequest
from gitective.config.settings import RULE_FIELDS, CustomRule, Settings
from gitective.core.people import PersonDirectory, PersonRef

OK, KO, NA = "ok", "ko", "na"

TICKET, SELF_MERGE, PIPELINE = "ticket", "self_merge", "pipeline"
FIXED_LABELS = {TICKET: "N° ticket", SELF_MERGE: "Mergeur ≠ auteur", PIPELINE: "Pipeline vert"}
SUCCESS = "success"
RUNNING_STATES = {"running", "pending", "created", "waiting_for_resource", "preparing", "scheduled", "manual"}
MAX_LISTED_COMMITS = 5


@dataclass(frozen=True)
class CheckResult:
    """Outcome of one criterion; detail explains a KO (tooltip text)."""

    status: str
    detail: str = ""


@dataclass(frozen=True)
class MrFields:
    """Everything a rule can inspect. commits is None when not loaded."""

    title: str
    description: str
    source_branch: str = ""
    target_branch: str = ""
    commits: tuple[tuple[str, str], ...] | None = None  # (short sha, message)

    @classmethod
    def from_mr(cls, mr: MergeRequest, commits: Sequence[Commit] | None) -> MrFields:
        return cls(
            title=mr.title,
            description=mr.description,
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            commits=tuple((c.short_id, c.message) for c in commits) if commits is not None else None,
        )


@dataclass(frozen=True)
class Criterion:
    """A column of the grid: a custom rule or a fixed criterion."""

    id: str
    label: str


@dataclass
class Evaluation:
    """Every check of one merge request plus its score."""

    mr: MergeRequest
    project_path: str
    author: PersonRef
    merger: PersonRef | None
    results: dict[str, CheckResult] = field(default_factory=dict)
    score: float = 0.0
    last_commit_at: datetime | None = None  # known only when the MR commits were loaded


def validate_regex(pattern: str) -> str | None:
    """Return an error message when the pattern does not compile, else None."""
    try:
        re.compile(pattern)
    except re.error as exc:
        return str(exc)
    return None


def _extract(pattern: re.Pattern[str], text: str) -> str | None:
    """First ticket number found: named group 'ticket', else group 1, else whole match."""
    match = pattern.search(text)
    if not match:
        return None
    if "ticket" in pattern.groupindex:
        return match.group("ticket")
    return match.group(1) if pattern.groups else match.group(0)


class RuleSet:
    """Compiled active rules built from the settings."""

    def __init__(
        self,
        rules: Sequence[CustomRule],
        link_regex: str,
        ticket_regex: str,
        fixed_weights: dict[str, float],
    ) -> None:
        self.rules = [r for r in rules if r.active]
        self._compiled = {r.id: re.compile(r.pattern) for r in self.rules if r.pattern}
        self.link = re.compile(link_regex) if link_regex else None
        self.ticket = re.compile(ticket_regex) if ticket_regex else None
        self.weights = {r.id: float(r.weight) for r in self.rules}
        self.weights[TICKET] = float(fixed_weights.get(TICKET, 0.0))
        self.weights[SELF_MERGE] = float(fixed_weights.get(SELF_MERGE, 0.0))
        self.weights[PIPELINE] = float(fixed_weights.get(PIPELINE, 0.0))

    @classmethod
    def from_settings(cls, settings: Settings) -> RuleSet:
        return cls(settings.rules, settings.link_regex, settings.ticket_regex, settings.weights)

    @property
    def criteria(self) -> list[Criterion]:
        """Grid columns, in display order."""
        return [Criterion(r.id, r.name) for r in self.rules] + [Criterion(k, v) for k, v in FIXED_LABELS.items()]

    @property
    def needs_commits(self) -> bool:
        """True when a rule inspects commit messages (one extra request per MR)."""
        return any(r.field == "commits" for r in self.rules)

    # -------------------------------------------------------------- Checks

    def _check_rule(self, rule: CustomRule, fields: MrFields) -> CheckResult:
        pattern = self._compiled.get(rule.id)
        if pattern is None:
            return CheckResult(KO, "Regex non configurée")
        expected = rule.mode == "match"
        if rule.field == "commits":
            if fields.commits is None:
                return CheckResult(NA, "Commits non chargés")
            bad = [sha for sha, message in fields.commits if bool(pattern.search(message)) != expected]
            if not bad:
                return CheckResult(OK)
            listed = ", ".join(bad[:MAX_LISTED_COMMITS]) + ("…" if len(bad) > MAX_LISTED_COMMITS else "")
            verb = "ne respecte(nt) pas" if expected else "contien(nen)t le motif interdit"
            return CheckResult(KO, f"{len(bad)} commit(s) {verb} : {listed}")
        value = getattr(fields, rule.field, "")
        if bool(pattern.search(value)) == expected:
            return CheckResult(OK)
        label = RULE_FIELDS.get(rule.field, rule.field)
        if expected:
            return CheckResult(KO, f"{label} : motif attendu absent")
        return CheckResult(KO, f"{label} : motif interdit trouvé")

    def _check_ticket(self, fields: MrFields) -> CheckResult:
        """RC-03: ticket number in the title equals the one in the description link."""
        if self.link is None or self.ticket is None:
            return CheckResult(KO, "Regex du lien ou du n° de ticket non configurée")
        link_match = self.link.search(fields.description)
        in_title = _extract(self.ticket, fields.title)
        in_link = _extract(self.ticket, link_match.group(0)) if link_match else None
        if in_title and in_link and in_title == in_link:
            return CheckResult(OK, in_title)
        if not in_title and not in_link:
            return CheckResult(KO, "N° absent du titre et du lien")
        if not in_title:
            return CheckResult(KO, f"N° absent du titre (lien : {in_link})")
        if not in_link:
            return CheckResult(KO, f"N° absent du lien (titre : {in_title})")
        return CheckResult(KO, f"{in_title} (titre) ≠ {in_link} (lien)")

    def check_fields(self, fields: MrFields) -> dict[str, CheckResult]:
        """Run every custom rule and RC-03 (everything but RC-04)."""
        results = {rule.id: self._check_rule(rule, fields) for rule in self.rules}
        results[TICKET] = self._check_ticket(fields)
        return results

    def score(self, results: dict[str, CheckResult]) -> float:
        """Weighted share of OK criteria among applicable ones, in percent."""
        applicable = [c for c, r in results.items() if r.status != NA]
        total = sum(self.weights.get(c, 0.0) for c in applicable)
        if total <= 0:
            return 0.0
        ok = sum(self.weights.get(c, 0.0) for c in applicable if results[c].status == OK)
        # Rounded to avoid float noise such as 99.9999 with weights like 33.33.
        return round(100.0 * ok / total, 6)

    def evaluate(
        self,
        mr: MergeRequest,
        project_path: str,
        people: PersonDirectory,
        commits: Sequence[Commit] | None = None,
        statuses: Sequence[CommitStatus] | None = None,
        ci_expected: bool = False,
    ) -> Evaluation:
        """Run every rule on a merge request and compute its score."""
        author = people.for_user(mr.author)
        merger = people.for_user(mr.merged_by) if mr.merged_by else None
        results = self.check_fields(MrFields.from_mr(mr, commits))
        if mr.state != "merged" or merger is None:
            results[SELF_MERGE] = CheckResult(NA, "MR non mergée")
        elif merger.key == author.key:
            account = mr.merged_by.username if mr.merged_by else ""
            results[SELF_MERGE] = CheckResult(KO, f"Mergée par son auteur (compte {account})")
        else:
            results[SELF_MERGE] = CheckResult(OK)
        results[PIPELINE] = check_pipeline(mr.merged_at, statuses, ci_expected)
        last_commit = max((c.committed_date for c in commits), default=None) if commits else None
        return Evaluation(mr=mr, project_path=project_path, author=author, merger=merger,
                          results=results, score=self.score(results), last_commit_at=last_commit)


def score_level(score: float, green: float, orange: float) -> str:
    """Color level of a score: 'green', 'orange' or 'red'."""
    if score >= green:
        return "green"
    if score >= orange:
        return "orange"
    return "red"


def check_pipeline(
    merged_at: datetime | None,
    statuses: Sequence[CommitStatus] | None,
    ci_expected: bool,
) -> CheckResult:
    """RC-05: every CI status of the head commit had succeeded when the MR was merged (PI-01..PI-04)."""
    if merged_at is None:
        return CheckResult(NA, "MR non mergée")
    if not ci_expected:
        return CheckResult(NA, "CI non attendue sur ce dépôt")
    if statuses is None:
        return CheckResult(NA, "Statuts CI non chargés")
    # Latest status of each name created before the merge; allow_failure ones do not count (PI-02, PI-03).
    latest: dict[str, CommitStatus] = {}
    for status in sorted((s for s in statuses if not s.allow_failure), key=lambda s: s.created_at):
        if status.created_at <= merged_at:
            latest[status.name] = status
    if not latest:
        return CheckResult(KO, "Aucun statut CI")
    problems = []
    for name, status in sorted(latest.items()):
        finished = status.finished_at is None or status.finished_at <= merged_at
        if status.status == SUCCESS and finished:
            continue
        if status.status in RUNNING_STATES or (status.status == SUCCESS and not finished):
            problems.append(f"{name} : en cours au merge")
        elif status.status == "canceled":
            problems.append(f"{name} : annulé")
        else:
            problems.append(f"{name} : {status.status}")
    return CheckResult(KO, "\n".join(problems)) if problems else CheckResult(OK)
