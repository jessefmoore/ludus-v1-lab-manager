"""Typed exceptions for Ludus client errors.

These errors form a small hierarchy so callers can catch either a specific
condition (`LudusUserExists`, `LudusAuthError`, etc.) or the base
`LudusError` to handle anything the Ludus integration raises.
"""

from __future__ import annotations


class LudusError(Exception):
    """Base for all Ludus client errors.

    Attributes:
        status_code: The HTTP status that triggered the error, if any.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LudusAuthError(LudusError):
    """Raised when Ludus returns HTTP 401 or 403."""


class LudusUserExists(LudusError):  # noqa: N818 - spec-mandated name
    """Raised when Ludus returns HTTP 409 (typically on user creation)."""


class LudusNotFound(LudusError):  # noqa: N818 - spec-mandated name
    """Raised when Ludus returns HTTP 404 (user, range, or snapshot missing)."""


class LudusTimeout(LudusError):  # noqa: N818 - spec-mandated name
    """Raised when the underlying HTTP request times out."""


class LudusNotSupported(LudusError):  # noqa: N818 - spec-mandated name
    """Raised when an operation is not available on the target Ludus version.

    Ludus v1 (1.11.x) lacks several endpoints that newer releases added
    (groups, multi-range create/assign, blueprints, whoami, log history,
    subscription roles, role scope, per-VM delete). The client raises this
    instead of issuing a request that would 404, so callers and the UI can
    surface a clear "not supported on this Ludus version" message.
    """
