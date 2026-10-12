"""Forge access: the forge-neutral ForgeClient interface and its GitLab implementation."""

from gitective.api.client import GitLabClient
from gitective.api.errors import (
    AuthenticationError,
    ForgeError,
    GitLabError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SSLVerificationError,
)
from gitective.api.forge import ForgeClient
from gitective.api.models import Commit, CommitStatus, MergeRequest, Project, ProtectedBranch, User

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
