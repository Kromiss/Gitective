"""Exception hierarchy raised by the GitLab client."""


class GitLabError(Exception):
    """Base class for every error raised by GitLabClient."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AuthenticationError(GitLabError):
    """Token missing, invalid or expired (HTTP 401)."""


class PermissionDeniedError(GitLabError):
    """Token valid but lacking rights on the resource (HTTP 403)."""


class NotFoundError(GitLabError):
    """Resource does not exist or is not visible (HTTP 404)."""


class RateLimitError(GitLabError):
    """GitLab kept answering HTTP 429 after all retries."""


class NetworkError(GitLabError):
    """Instance unreachable, connection lost or timed out."""


class SSLVerificationError(NetworkError):
    """TLS certificate of the instance could not be verified."""
