"""Generic GitLab REST API client, independent from the application."""

from gitective.api.client import GitLabClient
from gitective.api.errors import (
    AuthenticationError,
    GitLabError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    SSLVerificationError,
)
from gitective.api.models import Commit, MergeRequest, Project, User

__all__ = [
    "GitLabClient",
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
    "User",
]
