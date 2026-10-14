"""Forge-neutral error hierarchy (API-05): raised by every ForgeClient implementation."""


class ForgeError(Exception):
    """Base class for every error raised by a forge client."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# Former name, kept so existing callers and tests keep working.
GitLabError = ForgeError


class AuthenticationError(ForgeError):
    """Token missing, invalid or expired (HTTP 401)."""


class PermissionDeniedError(ForgeError):
    """Token valid but lacking rights on the resource (HTTP 403)."""


class NotFoundError(ForgeError):
    """Resource does not exist or is not visible (HTTP 404)."""


class RateLimitError(ForgeError):
    """The forge kept answering HTTP 429 after all retries."""


class NetworkError(ForgeError):
    """Instance unreachable, connection lost or timed out."""


class SSLVerificationError(NetworkError):
    """TLS certificate of the instance could not be verified."""
