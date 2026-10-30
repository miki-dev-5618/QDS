"""
hedwig_client.client
~~~~~~~~~~~~~~~~~~~~~
Synchronous HTTP client for the HEDWIG REST API.

Usage::

    from hedwig_client import HedwigClient

    client = HedwigClient("http://localhost:8000", "admin", "secret")
    client.login()
    result = client.sign_and_send("Hello, HEDWIG!")
    print(result.verdict, result.qber)
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .exceptions import APIError, AuthError, HedwigError, LinkQuarantinedError
from .models import AuditCertificate, TransmissionResult


class HedwigClient:
    """Synchronous client that wraps the HEDWIG REST API.

    Parameters
    ----------
    base_url:
        Root URL of the running HEDWIG server, e.g. ``"http://localhost:8000"``.
        Trailing slashes are stripped automatically.
    username:
        Login username (role ``admin`` is required for :meth:`sign_and_send`
        and :meth:`reset_link`).
    password:
        Corresponding password.

    The underlying :class:`httpx.Client` instance is available as
    :attr:`session` for advanced use-cases (e.g. injecting a custom
    transport for testing).

    Examples
    --------
    >>> client = HedwigClient("http://localhost:8000", "admin", "secret")
    >>> client.login()
    >>> result = client.sign_and_send("Transfer £1 000 to account #42")
    >>> print(result.verdict)
    authentic
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

        # A single httpx.Client is reused across calls so that cookies
        # (session tokens) set by /api/login are automatically replayed.
        self.session: httpx.Client = httpx.Client(
            base_url=self.base_url,
            timeout=30.0,
            follow_redirects=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        """Return the absolute URL for *path* (leading slash optional)."""
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Map HTTP error codes to SDK exceptions.

        ============  ========================
        Status code   Exception raised
        ============  ========================
        401           :class:`AuthError`
        403           :class:`AuthError`
        423           :class:`LinkQuarantinedError`
        other 4xx/5xx :class:`APIError`
        ============  ========================
        """
        if response.is_success:
            return

        status_code = response.status_code

        # Try to extract a human-readable message from the JSON body.
        try:
            body: dict[str, Any] = response.json()
        except Exception:
            body = {}

        detail: str = (
            body.get("detail")
            or body.get("message")
            or response.text
            or f"HTTP {status_code}"
        )

        if status_code in (401, 403):
            raise AuthError(status_code, detail)

        if status_code == 423:
            raise LinkQuarantinedError(body)

        raise APIError(status_code, detail, response.text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def login(self) -> dict[str, Any]:
        """Authenticate with the HEDWIG server.

        Sends a ``POST /api/login`` request with :attr:`username` and
        :attr:`password`.  On success the server sets an ``httpOnly`` session
        cookie which the underlying :class:`httpx.Client` stores and replays
        automatically for subsequent requests.

        Returns
        -------
        dict
            The parsed JSON body, e.g.
            ``{"status": "success", "username": "admin", "role": "admin", ...}``.

        Raises
        ------
        AuthError
            If the credentials are rejected (HTTP 401).
        APIError
            For any other non-2xx response.
        """
        if not self.username or not self.password:
            raise HedwigError(
                "username and password must be set before calling login()"
            )

        response = self.session.post(
            "/api/login",
            json={"username": self.username, "password": self.password},
        )
        self._raise_for_status(response)
        return response.json()

    def sign_and_send(
        self,
        message: str,
        L: int = 16,
        scenario: str = "authentic",
        noise_profile: dict[str, Any] | None = None,
    ) -> TransmissionResult:
        """Sign *message* and transmit it through the quantum channel.

        Calls ``POST /api/sign-and-send`` (requires the ``admin`` role).

        Parameters
        ----------
        message:
            Plaintext message to sign and send.
        L:
            Number of qubits per bit (``n_bits`` in the server model).
            Clamped to ``[8, 64]`` by the server; defaults to ``16``.
        scenario:
            Threat scenario to inject, e.g. ``"authentic"`` (default),
            ``"eavesdrop"``, ``"replay"``, ``"cloning"``, etc.
        noise_profile:
            Optional dict of extra noise parameters forwarded verbatim to the
            server.  Recognised keys include ``noise_profile`` (profile name),
            ``noise_param``, ``readout_p01``, ``readout_p10``, ``eta_loss``,
            etc.  See ``GET /api/noise-profiles`` for the full catalogue.

        Returns
        -------
        TransmissionResult
            Decoded summary of the transmission outcome.

        Raises
        ------
        LinkQuarantinedError
            If the circuit breaker is open (HTTP 423).
        AuthError
            If the session has expired or the user lacks the ``admin`` role.
        APIError
            For any other error response.
        """
        payload: dict[str, Any] = {
            "message_text": message,
            "n_bits": L,
            "threat_type": scenario,
        }
        if noise_profile:
            payload.update(noise_profile)

        response = self.session.post("/api/sign-and-send", json=payload)
        self._raise_for_status(response)
        return TransmissionResult.from_api(response.json())

    def get_audit(self, artifact_id: str) -> AuditCertificate:
        """Retrieve a stored audit certificate by its artifact ID.

        Calls ``GET /api/audit/{artifact_id}``.

        Parameters
        ----------
        artifact_id:
            The artifact / transmission ID assigned by the server.

        Returns
        -------
        AuditCertificate
            Decoded certificate including chain hashes and signatures.

        Raises
        ------
        APIError
            If no certificate exists (HTTP 404) or any other error occurs.
        """
        response = self.session.get(f"/api/audit/{artifact_id}")
        self._raise_for_status(response)
        return AuditCertificate.from_api(response.json())

    def reset_link(self, reason: str = "admin reset") -> dict[str, Any]:
        """Reset the quantum channel circuit breaker.

        Calls ``POST /api/channel/reset`` (requires the ``admin`` role).

        Parameters
        ----------
        reason:
            Human-readable justification for the reset, stored in the
            signed reset record on the audit chain.

        Returns
        -------
        dict
            The parsed server response, containing ``channel_state``,
            ``transitions``, and optionally a ``reset_record`` summary.

        Raises
        ------
        AuthError
            If the session lacks the ``admin`` role (HTTP 403).
        APIError
            For any other error response.
        """
        response = self.session.post(
            "/api/channel/reset",
            json={"reason": reason},
        )
        self._raise_for_status(response)
        return response.json()

    def topology(self) -> dict[str, Any]:
        """Return the current network topology and channel state.

        Calls ``GET /api/topology`` (requires any authenticated session).

        Returns
        -------
        dict
            Contains ``"router"`` (node/link topology) and
            ``"channel_state"`` (circuit-breaker status, counters, etc.).

        Raises
        ------
        AuthError
            If no valid session exists (HTTP 401).
        APIError
            For any other error response.
        """
        response = self.session.get("/api/topology")
        self._raise_for_status(response)
        return response.json()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self.session.close()

    def __enter__(self) -> "HedwigClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
