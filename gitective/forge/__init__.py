"""Forge access: the forge-neutral ForgeClient interface and its GitLab implementation."""

from gitective.forge.gitlab_client import GitLabClient
from gitective.forge.errors import (
    AuthenticationError,
    ForgeError,
    GitLabError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SSLVerificationError,
)
from gitective.forge.protocol import ForgeClient
from gitective.forge.models import Commit, CommitStatus, MergeRequest, Project, ProtectedBranch, User

__all__ = [
    "ForgeClient",
    "GitLabClient",
    "ForgeError",
    "GitLabError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "NetworkError",
    "SSLVerificationError",
    "RateLimitError",
    "Project",
    "MergeRequest",
    "Commit",
    "CommitStatus",
    "User",
    "ProtectedBranch",
]
