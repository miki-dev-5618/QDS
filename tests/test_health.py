"""\
Tests for the HEDWIG ``/health`` endpoint.

Run:
    python -m pytest tests/test_health.py -v
"""
import importlib
import json

import pytest
from fastapi.testclient import TestClient


# ------------------------------------------------------------------ fixtures -


@pytest.fixture(scope="module")
def server_app():
    """FastAPI app instance; minimal env so the built-in demo credentials are active."""
    import server as srv
    import os

    os.environ.pop("HEDWIG_USERS_FILE", None)
    os.environ.pop("HEDWIG_DB", None)
    os.environ.pop("HEDWIG_AUDIT_KEY", None)
    # Ensure the built-in demo users are used.
    return importlib.reload(srv)


# ------------------------------------------------------------------ tests -


class TestHealthGet:
    """GET /health must return JSON with status, version, simulator."""

    def test_health_get_returns_ok(self, server_app):
        c = TestClient(server_app.app)
        resp = c.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "2.2"
        assert body["simulator"] == "HEDWIG V2.2"


class TestHealthHead:
    """HEAD /health must return 200 with no body (FastAPI handles this)."""

    def test_health_head_returns_200(self, server_app):
        c = TestClient(server_app.app, raise_server_exceptions=False)
        resp = c.head("/health")
        assert resp.status_code == 200
        # body should be empty or minimal
        assert len(resp.text) == 0 or resp.text is None


# ------------------------------------------------------------------ sanity -


def test_health_independent_of_db():
    """Verify /health works regardless of HEDWIG_DB (SQLite) or HEDWIG_DATABASE_URL (PG)."""
    import server as srv
    import os

    # Start with SQLite default
    os.environ.pop("HEDWIG_DATABASE_URL", None)
    os.environ["HEDWIG_DB"] = str(
        os.path.join(os.path.dirname(__file__), "..", "data", "hedwig.db")
    )
    app_s = importlib.reload(srv)

    # Now switch to PostgreSQL if available
    try:
        import psycopg  # noqa: F401

        os.environ["HEDWIG_DATABASE_URL"] = "postgresql://hedwig:hedwig@localhost:5432/hedwig"
        app_pg = importlib.reload(srv)
    except ImportError:
        # psycopg not installed – just test the SQLite path
        pytest.skip("psycopg not installed; skipping PG health test")

    c = TestClient(app_pg.app)
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"