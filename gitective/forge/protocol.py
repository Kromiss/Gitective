"""ForgeClient: the forge-neutral operations the application needs (12.3, AR-01).

database, review, reporting and shared depend on this protocol only. GitLabClient implements it; another forge
(GitHub, Gitea...) only needs an adapter with the same methods, returning the
neutral objects of models.py and raising the errors of errors.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from gitective.forge.models import (
    Approvals,
    Branch,
    ChangedFile,
    Commit,
    CommitStatus,
    Discussion,
    Job,
    MergeRequest,
    MergeState,
    PipelineRef,
    Project,
    ProtectedBranch,
    Tag,
    User,
)


class ForgeClient(Protocol):
    """Read-only access to a code forge."""

    base_url: str

    def current_user(self) -> User:
        """Account owning the token (connection test)."""
        ...

    def get_user(self, user_id: int) -> User:
        ...

    def search_users(self, query: str) -> list[User]:
        ...

    def list_projects(self, membership: bool = True, workers: int = 1) -> list[Project]:
        """Projects visible to the token."""
        ...

    def branch_exists(self, project_id: int, branch: str) -> bool:
        ...

    def list_merge_requests(
        self,
        project_id: int,
        state: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
    ) -> list[MergeRequest]:
        """Merge requests of a project; state "opened", "closed", "merged" or None for all."""
        ...

    def list_merge_request_commits(self, project_id: int, mr_iid: int) -> list[Commit]:
        ...

    def list_commits(self, project_id: int, ref_name: str, since: datetime | None = None,
                     until: datetime | None = None) -> list[Commit]:
        """Commits reachable from a branch, by commit date."""
        ...

    def list_commit_merge_requests(self, project_id: int, sha: str) -> list[MergeRequest]:
        ...

    def list_commit_statuses(self, project_id: int, sha: str) -> list[CommitStatus]:
        """Every CI status published on a commit, older ones included."""
        ...

    def list_project_members(self, project_id: int) -> list[tuple[User, int]]:
        """Members with their access level, inherited memberships included."""
        ...

    def list_protected_branches(self, project_id: int) -> list[ProtectedBranch]:
        ...

    def list_branches(self, project_id: int) -> list[Branch]:
        """Every branch with its last commit, merged / protected / default flags (BR-10)."""
        ...

    def list_tags(self, project_id: int) -> list[Tag]:
        """Every tag with its message, pointed commit and release (TG-08)."""
        ...

    def latest_pipeline(self, project_id: int, ref: str) -> PipelineRef | None:
        """Most recent pipeline of a branch or tag (TG-09)."""
        ...

    def list_my_open_merge_requests(self, user_id: int, role: str) -> list[MergeRequest]:
        """Open MRs of every visible project where the user is "assignee" or "reviewer" (AM-02)."""
        ...

    def get_merge_state(self, project_id: int, mr_iid: int) -> MergeState:
        ...

    def get_approvals(self, project_id: int, mr_iid: int) -> Approvals:
        ...

    def list_discussions(self, project_id: int, mr_iid: int) -> list[Discussion]:
        """Resolvable discussion threads."""
        ...

    def list_changed_files(self, project_id: int, mr_iid: int) -> list[ChangedFile]:
        ...

    def list_pipeline_jobs(self, project_id: int, pipeline_id: int) -> list[Job]:
        ...

    def job_log(self, project_id: int, job_id: int) -> str:
        ...

    def download(self, url: str) -> bytes:
        """Raw file, such as an avatar."""
        ...
