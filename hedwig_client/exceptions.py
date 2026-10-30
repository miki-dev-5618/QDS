"""
hedwig_client.exceptions
~~~~~~~~~~~~~~~~~~~~~~~~~
Custom exception hierarchy for the HEDWIG Python SDK.

All exceptions raised by :class:`~hedwig_client.client.HedwigClient` are
subclasses of :class:`HedwigError`, so callers can catch the base class
when they do not need to distinguish between error kinds.
"""
from __future__ import annotations

from typing import Any


class HedwigError(Exception):
    """Base exception for every error raised by the HEDWIG SDK."""


class AuthError(HedwigError):
    """Raised when the server returns HTTP 401 or 403.

    Parameters
    ----------
    status_code:
        The exact HTTP status code (401 or 403).
    message:
        Human-readable description supplied by the server.
    """

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class LinkQuarantinedError(HedwigError):
    """Raised when the server returns HTTP 423 (circuit breaker open).

    The server's full JSON body is captured in :attr:`detail` so callers
    can inspect ``link``, ``refusal_us``, and other diagnostic fields.

    Parameters
    ----------
    detail:
        The parsed JSON body returned by the server (contains at minimum
        ``status``, ``link``, and ``message``).
    """

    def __init__(self, detail: dict[str, Any]) -> None:
        self.detail = detail
        link = detail.get("link", "unknown")
        msg = detail.get("message", "Link is quarantined.")
        super().__init__(f"Link quarantined (link={link!r}): {msg}")


class APIError(HedwigError):
    """Raised for any HTTP error not covered by the more specific exceptions.

    Parameters
    ----------
    status_code:
        The HTTP status code returned by the server.
    message:
        Human-readable description (server detail or raw body text).
    response_body:
        The raw response body as a string, for debugging.
    """

    def __init__(self, status_code: int, message: str, response_body: str = "") -> None:
        self.status_code = status_code
        self.message = message
        self.response_body = response_body
        super().__init__(f"HTTP {status_code}: {message}")

