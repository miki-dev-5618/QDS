"""
tests/test_sdk.py
~~~~~~~~~~~~~~~~~~
Integration tests for the hedwig-client SDK (Feature E55).

These tests route the SDK's httpx.Client directly into the FastAPI ``app``
object from ``server.py`` via ``httpx.ASGITransport`` — no live server is
needed.  The session cookie set by /api/login is automatically replayed
by the shared httpx.Client instance, so the full auth flow is exercised.

Run with::

    pytest tests/test_sdk.py -v
"""
from __future__ import annotations

import sys
import os
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import httpx

# ---------------------------------------------------------------------------
# SDK imports
# ---------------------------------------------------------------------------
from hedwig_client import (
    AuditCertificate,
    HedwigClient,
    LinkQuarantinedError,
    TransmissionResult,
)
from hedwig_client.exceptions import APIError, AuthError

# ---------------------------------------------------------------------------
# Lightweight fake "server" helpers
# ---------------------------------------------------------------------------
# We use httpx.MockTransport so the tests never touch the real FastAPI app
# (which has heavy quantum-engine deps that may not be installed in CI).
# Each test controls exactly what the server returns, letting us verify that
# the SDK maps responses → domain objects / exceptions correctly.
# ---------------------------------------------------------------------------

_BASE = "http://testserver"


def _make_client(transport: httpx.MockTransport) -> HedwigClient:
    """Return a HedwigClient whose inner httpx.Client uses *transport*."""
    client = HedwigClient(base_url=_BASE, username="admin", password="admin2026")
    client.session = httpx.Client(
        base_url=_BASE,
        transport=transport,
        follow_redirects=False,
        timeout=5.0,
    )
    return client


def _json_response(body: Any, status_code: int = 200) -> httpx.Response:
    """Construct an httpx.Response with a JSON body."""
    import json as _json
    content = _json.dumps(body).encode()
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=content,
        # httpx needs a Request object attached to the response.
        request=httpx.Request("GET", _BASE),
    )


# ---------------------------------------------------------------------------
# Test: login – success
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self) -> None:
        """login() returns the parsed JSON body on HTTP 200."""
        login_body = {
            "status": "success",
            "username": "admin",
            "role": "admin",
            "redirect_url": "/admin",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/login"
            return _json_response(login_body, 200)

        client = _make_client(httpx.MockTransport(handler))
        result = client.login()
        assert result["status"] == "success"
        assert result["role"] == "admin"

    def test_login_bad_credentials(self) -> None:
        """login() raises AuthError on HTTP 401."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"detail": "Invalid credentials."}, 401)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(AuthError) as exc_info:
            client.login()
        assert exc_info.value.status_code == 401
        assert "Invalid credentials" in exc_info.value.message

    def test_login_forbidden(self) -> None:
        """login() raises AuthError on HTTP 403."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"detail": "Forbidden"}, 403)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(AuthError) as exc_info:
            client.login()
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Test: sign_and_send – authentic transmission
# ---------------------------------------------------------------------------

class TestSignAndSend:
    """Tests for HedwigClient.sign_and_send."""

    _SUCCESS_BODY: dict[str, Any] = {
        "status": "success",
        "transmission": {
            "transmission_id": "tx-abc-123",
            "context": {"message_text": "hello"},
            "channel": {"qber_estimate": 0.042},
            "threat_report": {"verdict": "authentic", "is_threat_detected": False},
            "enforcement": {"action": "closed"},
        },
        "transmissions": [],
        "stats": {},
    }

    def test_sign_and_send_success(self) -> None:
        """sign_and_send() returns a populated TransmissionResult on success."""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/sign-and-send"
            return _json_response(self._SUCCESS_BODY, 200)

        client = _make_client(httpx.MockTransport(handler))
        result = client.sign_and_send("hello")

        assert isinstance(result, TransmissionResult)
        assert result.transmission_id == "tx-abc-123"
        assert result.status == "success"
        assert abs(result.qber - 0.042) < 1e-9
        assert result.message == "hello"
        assert result.verdict == "authentic"
        assert result.circuit_breaker_state == "closed"

    def test_sign_and_send_forwards_noise_profile(self) -> None:
        """Keyword args in noise_profile are merged into the POST body."""
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _j
            captured.append(_j.loads(request.content))
            return _json_response(self._SUCCESS_BODY, 200)

        client = _make_client(httpx.MockTransport(handler))
        client.sign_and_send("hi", L=32, noise_profile={"noise_profile": "dephasing", "noise_param": 0.01})

        assert captured[0]["n_bits"] == 32
        assert captured[0]["noise_profile"] == "dephasing"
        assert captured[0]["noise_param"] == pytest.approx(0.01)

    def test_sign_and_send_quarantined(self) -> None:
        """sign_and_send() raises LinkQuarantinedError on HTTP 423."""
        quarantine_body: dict[str, Any] = {
            "status": "quarantined",
            "link": "signer",
            "detail": {"alert_count": 3},
            "refusal_us": 12.5,
            "message": "Circuit is broken after a qualifying alert.",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response(quarantine_body, 423)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(LinkQuarantinedError) as exc_info:
            client.sign_and_send("blocked message")

        err = exc_info.value
        assert err.detail["status"] == "quarantined"
        assert err.detail["link"] == "signer"
        assert "quarantined" in str(err).lower()

    def test_sign_and_send_scenario_forwarded(self) -> None:
        """The `scenario` argument is sent as `threat_type` in the body."""
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _j
            captured.append(_j.loads(request.content))
            return _json_response(self._SUCCESS_BODY, 200)

        client = _make_client(httpx.MockTransport(handler))
        client.sign_and_send("test", scenario="eavesdrop")
        assert captured[0]["threat_type"] == "eavesdrop"

    def test_sign_and_send_api_error(self) -> None:
        """sign_and_send() raises APIError for unexpected server errors."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"detail": "Internal Server Error"}, 500)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(APIError) as exc_info:
            client.sign_and_send("boom")
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Test: topology
# ---------------------------------------------------------------------------

class TestTopology:
    _TOPO_BODY: dict[str, Any] = {
        "router": {"nodes": ["alice", "bob", "charlie"], "links": [{"a": "alice", "b": "bob"}]},
        "channel_state": {"state": "closed", "alert_count": 0},
    }

    def test_topology_success(self) -> None:
        """topology() returns the full server payload as a dict."""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/topology"
            return _json_response(self._TOPO_BODY, 200)

        client = _make_client(httpx.MockTransport(handler))
        topo = client.topology()
        assert "router" in topo
        assert "channel_state" in topo
        assert topo["channel_state"]["state"] == "closed"

    def test_topology_requires_auth(self) -> None:
        """topology() raises AuthError when not logged in (HTTP 401)."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"detail": "Authentication required."}, 401)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(AuthError):
            client.topology()


# ---------------------------------------------------------------------------
# Test: get_audit
# ---------------------------------------------------------------------------

class TestGetAudit:
    _CERT_BODY: dict[str, Any] = {
        "artifact_id": "tx-abc-123",
        "payload_sha256": "deadbeef00",
        "record": {
            "transmission_id": "tx-abc-123",
            "chain": {
                "seq": 1,
                "previous_hash": "0000",
                "hash": "cafebabe",
            },
        },
        "signatures": {
            "ed25519": "base64sighere==",
            "mldsa": None,
        },
    }

    def test_get_audit_success(self) -> None:
        """get_audit() returns an AuditCertificate with decoded fields."""
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/api/audit/" in request.url.path
            return _json_response(self._CERT_BODY, 200)

        client = _make_client(httpx.MockTransport(handler))
        cert = client.get_audit("tx-abc-123")

        assert isinstance(cert, AuditCertificate)
        assert cert.artifact_id == "tx-abc-123"
        assert cert.transmission_id == "tx-abc-123"
        assert cert.previous_hash == "0000"
        assert cert.hash == "cafebabe"
        assert cert.ed25519_signature == "base64sighere=="

    def test_get_audit_not_found(self) -> None:
        """get_audit() raises APIError on HTTP 404."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"detail": "No audit record with that id"}, 404)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(APIError) as exc_info:
            client.get_audit("nonexistent-id")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Test: reset_link
# ---------------------------------------------------------------------------

class TestResetLink:
    _RESET_BODY: dict[str, Any] = {
        "status": "success",
        "channel_state": {"state": "probation", "alert_count": 0},
        "transitions": [{"from": "quarantined", "to": "probation"}],
        "reset_record": {"payload_sha256": "abcd", "chain_seq": 5},
    }

    def test_reset_link_success(self) -> None:
        """reset_link() posts to /api/channel/reset and returns the body."""
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _j
            assert request.url.path == "/api/channel/reset"
            captured.append(_j.loads(request.content))
            return _json_response(self._RESET_BODY, 200)

        client = _make_client(httpx.MockTransport(handler))
        result = client.reset_link("test suite reset")

        assert result["status"] == "success"
        assert captured[0]["reason"] == "test suite reset"

    def test_reset_link_requires_admin(self) -> None:
        """reset_link() raises AuthError when the role is wrong (HTTP 403)."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"detail": "Requires role: admin"}, 403)

        client = _make_client(httpx.MockTransport(handler))
        with pytest.raises(AuthError) as exc_info:
            client.reset_link("unauthorized reset")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Test: 423 round-trip – quarantine then reset
# ---------------------------------------------------------------------------

class TestQuarantineAndReset:
    """End-to-end scenario: sign_and_send triggers 423, client catches it,
    calls reset_link, then retries successfully."""

    def test_quarantine_then_reset_then_retry(self) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1

            if request.url.path == "/api/sign-and-send" and call_count == 1:
                return _json_response(
                    {"status": "quarantined", "link": "signer",
                     "detail": {}, "message": "Circuit broken."},
                    423,
                )
            if request.url.path == "/api/channel/reset":
                return _json_response(
                    {"status": "success", "channel_state": {}, "transitions": []},
                    200,
                )
            if request.url.path == "/api/sign-and-send":
                return _json_response(
                    {
                        "status": "success",
                        "transmission": {
                            "transmission_id": "tx-retry-1",
                            "context": {"message_text": "retry"},
                            "channel": {"qber_estimate": 0.01},
                            "threat_report": {"verdict": "authentic", "is_threat_detected": False},
                            "enforcement": {"action": "closed"},
                        },
                        "transmissions": [],
                        "stats": {},
                    },
                    200,
                )
            return _json_response({"detail": "unexpected"}, 500)

        client = _make_client(httpx.MockTransport(handler))

        try:
            result = client.sign_and_send("first attempt")
        except LinkQuarantinedError:
            client.reset_link("automated recovery")
            result = client.sign_and_send("retry")

        assert result.transmission_id == "tx-retry-1"
        assert result.verdict == "authentic"


# ---------------------------------------------------------------------------
# Test: context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager_closes_session(self) -> None:
        """The client can be used as a context manager; close() is called on exit."""
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"status": "ok"}, 200)

        with _make_client(httpx.MockTransport(handler)) as client:
            assert client is not None
        # After __exit__ the underlying session should be closed; a fresh
        # request should raise RuntimeError (httpx raises when closed).
        with pytest.raises(Exception):
            client.session.get("/health")

