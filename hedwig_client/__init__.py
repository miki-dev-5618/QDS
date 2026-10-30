"""
hedwig_client
~~~~~~~~~~~~~
Python SDK for the HEDWIG V2.2 Teleportation QDS REST API.

Quick start::

    from hedwig_client import HedwigClient, LinkQuarantinedError

    with HedwigClient("http://localhost:8000", "admin", "secret") as client:
        client.login()
        result = client.sign_and_send("Hello, HEDWIG!")
        print(result.verdict, result.qber)
"""
from __future__ import annotations

from .client import HedwigClient
from .exceptions import APIError, AuthError, HedwigError, LinkQuarantinedError
from .models import AuditCertificate, TransmissionResult

__all__: list[str] = [
    # Client
    "HedwigClient",
    # Models
    "TransmissionResult",
    "AuditCertificate",
    # Exceptions
    "HedwigError",
    "AuthError",
    "LinkQuarantinedError",
    "APIError",
]

__version__ = "0.1.0"

