"""
hedwig_client.models
~~~~~~~~~~~~~~~~~~~~~
Dataclasses that represent the core domain objects returned by the HEDWIG
REST API.  All fields use ``None`` as the default so that partial server
responses (e.g. early-abort transmissions) can still be decoded safely.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# TransmissionResult
# ---------------------------------------------------------------------------

@dataclass
class TransmissionResult:
    """Summary of a single quantum-digital-signature transmission.

    Attributes
    ----------
    transmission_id:
        Unique identifier assigned by the server (e.g. ``"tx-<uuid>"``).
    status:
        High-level outcome string, e.g. ``"success"`` or ``"quarantined"``.
    qber:
        Quantum Bit Error Rate estimate for the channel used during this
        transmission, or ``None`` if unavailable (e.g. early abort).
    message:
        The plaintext message that was signed and sent.
    verdict:
        The threat-detection verdict, e.g. ``"authentic"``, ``"eavesdrop"``,
        ``"replay"``, etc.  ``None`` if the transmission was refused before
        assessment.
    circuit_breaker_state:
        The state of the circuit breaker *after* this transmission, e.g.
        ``"closed"``, ``"link_watch"``, or ``"link_quarantined"``.
    raw:
        The complete server JSON payload as a plain ``dict``, preserved for
        callers that need fields beyond the summarised attributes.
    """

    transmission_id: str | None = None
    status: str | None = None
    qber: float | None = None
    message: str | None = None
    verdict: str | None = None
    circuit_breaker_state: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "TransmissionResult":
        """Build a :class:`TransmissionResult` from the ``/api/sign-and-send``
        response body.

        The server wraps the transmission object inside a ``"transmission"``
        key.  This method handles both the outer envelope and a bare
        transmission dict.
        """
        tx: dict[str, Any] = payload.get("transmission", payload)

        # QBER lives inside the optional "channel" sub-object.
        channel: dict[str, Any] = tx.get("channel") or {}
        qber: float | None = channel.get("qber_estimate")

        # Verdict is inside "threat_report".
        threat: dict[str, Any] = tx.get("threat_report") or {}
        verdict: str | None = threat.get("verdict") or threat.get("decision")

        # Circuit-breaker state.
        enforcement: dict[str, Any] = tx.get("enforcement") or {}
        cb_state: str | None = enforcement.get("action") or enforcement.get("circuit_breaker_state")

        # The signed message text lives under "context".
        context: dict[str, Any] = tx.get("context") or {}
        message_text: str | None = context.get("message_text")

        return cls(
            transmission_id=tx.get("transmission_id"),
            status=payload.get("status", tx.get("status")),
            qber=qber,
            message=message_text,
            verdict=verdict,
            circuit_breaker_state=cb_state,
            raw=payload,
        )


# ---------------------------------------------------------------------------
# AuditCertificate
# ---------------------------------------------------------------------------

@dataclass
class AuditCertificate:
    """A single entry from the HEDWIG tamper-evident audit chain.

    Attributes
    ----------
    artifact_id:
        The opaque ID used to retrieve this certificate (e.g. a transmission
        ID or a ``"RST-…"`` reset record ID).
    transmission_id:
        Transmission ID embedded inside the certificate payload, if present.
    previous_hash:
        SHA-256 hex digest of the preceding chain entry (``None`` for the
        genesis record).
    hash:
        SHA-256 hex digest of *this* record's payload.
    ed25519_signature:
        Base-64-encoded classical Ed25519 signature over the payload, or
        ``None`` if the field is absent.
    mldsa_signature:
        Base-64-encoded post-quantum ML-DSA-65 signature, or ``None`` when
        the server is running in classical-only mode.
    raw_json:
        The full certificate JSON string, suitable for archiving or sending
        to ``POST /api/audit/verify``.
    """

    artifact_id: str | None = None
    transmission_id: str | None = None
    previous_hash: str | None = None
    hash: str | None = None
    ed25519_signature: str | None = None
    mldsa_signature: str | None = None
    raw_json: str = ""

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "AuditCertificate":
        """Build an :class:`AuditCertificate` from the ``/api/audit/{id}``
        response body.

        The server returns the raw certificate JSON directly (no outer
        envelope), so *payload* is the certificate itself.
        """
        record: dict[str, Any] = payload.get("record") or {}
        chain: dict[str, Any] = record.get("chain") or {}
        sig_block: dict[str, Any] = payload.get("signatures") or {}

        # Attempt to find transmission_id in nested structures.
        tx_id: str | None = (
            record.get("transmission_id")
            or (record.get("evidence") or {}).get("transmission_id")
            or payload.get("transmission_id")
        )

        return cls(
            artifact_id=payload.get("artifact_id") or payload.get("payload_sha256"),
            transmission_id=tx_id,
            previous_hash=chain.get("previous_hash"),
            hash=chain.get("hash") or payload.get("payload_sha256"),
            ed25519_signature=(
                sig_block.get("ed25519")
                or payload.get("ed25519_signature")
            ),
            mldsa_signature=(
                sig_block.get("mldsa")
                or payload.get("mldsa_signature")
            ),
            raw_json=json.dumps(payload),
        )

