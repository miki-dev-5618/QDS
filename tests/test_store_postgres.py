"""\
Tests for :class:`src.quantum_engine.store.Store` under SQLite and PostgreSQL.

Run SQLite only:
    python -m pytest tests/test_store_postgres.py -v

Run PostgreSQL (requires psycopg):
    HEDWIG_DATABASE_URL="postgresql://hedwig:hedwig@localhost/hedwig" \
    python -m pytest tests/test_store_postgres.py -v
"""
import json
import os

import pytest

from src.quantum_engine.store import Store


# ------------------------------------------------------------------ pg fixture -


def _free_port():
    """Return a free TCP port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _make_pg_uri(port=None):
    if port is None:
        port = _free_port()
    return f"postgresql://hedwig:hedwig@localhost:{port}/hedwig_pg_test"


@pytest.fixture(scope="function")
def store_pg():
    """PostgreSQL Store using a temporary database.

    Skipped when psycopg is not installed.
    """
    try:
        import psycopg  # noqa: F401
    except ImportError:
        pytest.skip("psycopg not installed; skipping PostgreSQL tests")
        return  # unreachable

    uri = _make_pg_uri()
    conn = psycopg.connect(uri)
    conn.autocommit = True

    with conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS kv (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS transitions (
                id             INTEGER PRIMARY KEY,
                ts             REAL NOT NULL,
                link           TEXT NOT NULL,
                old_state      TEXT NOT NULL,
                new_state      TEXT NOT NULL,
                actor          TEXT NOT NULL,
                reason         TEXT,
                evidence_id    TEXT,
                policy_version TEXT,
                incident_id    TEXT
            );
            CREATE TABLE IF NOT EXISTS nonces (
                verifier    TEXT NOT NULL,
                channel     TEXT NOT NULL,
                nonce       TEXT NOT NULL,
                consumed_at REAL NOT NULL,
                PRIMARY KEY (verifier, channel, nonce)
            );
            CREATE TABLE IF NOT EXISTS audit (
                artifact_id    TEXT PRIMARY KEY,
                kind           TEXT NOT NULL,
                seq            INTEGER NOT NULL UNIQUE,
                issued_at      REAL NOT NULL,
                transmission_id TEXT,
                payload        BYTEA NOT NULL,
                payload_sha256 TEXT NOT NULL,
                cert           TEXT NOT NULL
            );""")

    yield Store(uri)
    # tables are left for next test; each test gets a fresh DB via a new URI


# ------------------------------------------------------------------ sqlite fixture -


@pytest.fixture(scope="function")
def store_sqlite():
    """SQLite in-memory Store (default driver)."""
    s = Store(":memory:")
    yield s
    s.close()


# ------------------------------------------------------------------ tests -


class TestStoreSQLiteDefault:
    """Assertions against the SQLite driver (the default)."""

    def test_put_get_json(self, store_sqlite):
        s = store_sqlite
        s.put_json("k1", {"hello": "world", "n": 42})
        assert s.get_json("k1") == {"hello": "world", "n": 42}
        assert s.get_json("missing", default={"fallback": True}) == {"fallback": True}

    def test_put_json_update(self, store_sqlite):
        s = store_sqlite
        s.put_json("k1", {"v1": 1})
        s.put_json("k1", {"v2": 2})
        assert s.get_json("k1") == {"v2": 2}

    def test_save_and_list_transitions(self, store_sqlite):
        s = store_sqlite
        s.save_link_transition(
            links={"a": 1, "b": 2},
            transition={
                "ts": 1_000_000.0,
                "link": "link-123",
                "old_state": "probation",
                "new_state": "active",
                "actor": "admin",
                "reason": "test",
            },
        )
        txs = s.transitions(limit=5)
        assert len(txs) == 1
        assert txs[0]["link"] == "link-123"
        assert txs[0]["new_state"] == "active"

    def test_consume_nonce_idempotent(self, store_sqlite):
        s = store_sqlite
        ts = 1_000_000.0
        assert s.consume_nonce("v1", "c1", "nonce-1", ts) is True
        assert s.consume_nonce("v1", "c1", "nonce-1", ts) is False
        assert s.consume_nonce("v1", "c1", "nonce-2", ts) is True

    def test_nonce_consumed_check(self, store_sqlite):
        s = store_sqlite
        ts = 1_000_000.0
        s.consume_nonce("v2", "c2", "nonce-A", ts)
        assert s.nonce_consumed("v2", "c2", "nonce-A") is True
        assert s.nonce_consumed("v2", "c2", "nonce-B") is False

    def test_append_and_last_audit(self, store_sqlite):
        s = store_sqlite
        payload = b"\xde\xad\xbe\xef" * 8
        cert = {"issuer": "test", "seq": 1}
        s.append_audit(
            artifact_id="art-1",
            kind="transaction",
            seq=1,
            issued_at=1_000_000.0,
            transmission_id="tx-1",
            payload=payload,
            payload_sha256="aa" * 32,
            cert=cert,
        )
        last = s.last_audit()
        assert last is not None
        assert last == (1, "aa" * 32)

    def test_audit_chain(self, store_sqlite):
        s = store_sqlite
        for i in range(3):
            payload = f"payload-{i}".encode()
            cert = {"issuer": "test", "seq": i + 1}
            s.append_audit(
                artifact_id=f"art-{i}",
                kind="transaction",
                seq=i + 1,
                issued_at=1_000_000.0 + i,
                transmission_id=f"tx-{i}",
                payload=payload,
                payload_sha256="xx" * 32,
                cert=cert,
            )
        chain = s.audit_chain(limit=5)
        assert len(chain) == 3
        assert {c["issuer"] for c in chain} == {"test"}


# ------------------------------------------------------------------ PG tests -


class TestStorePG:
    """Identical assertions against the PostgreSQL driver."""

    def test_put_get_json(self, store_pg):
        s = store_pg
        s.put_json("k1", {"hello": "world", "n": 42})
        assert s.get_json("k1") == {"hello": "world", "n": 42}
        assert s.get_json("missing", default={"fallback": True}) == {"fallback": True}

    def test_put_json_update(self, store_pg):
        s = store_pg
        s.put_json("k1", {"v1": 1})
        s.put_json("k1", {"v2": 2})
        assert s.get_json("k1") == {"v2": 2}

    def test_save_and_list_transitions(self, store_pg):
        s = store_pg
        s.save_link_transition(
            links={"a": 1, "b": 2},
            transition={
                "ts": 1_000_000.0,
                "link": "link-123",
                "old_state": "probation",
                "new_state": "active",
                "actor": "admin",
                "reason": "test",
            },
        )
        txs = s.transitions(limit=5)
        assert len(txs) == 1
        assert txs[0]["link"] == "link-123"
        assert txs[0]["new_state"] == "active"

    def test_consume_nonce_idempotent(self, store_pg):
        s = store_pg
        ts = 1_000_000.0
        assert s.consume_nonce("v1", "c1", "nonce-1", ts) is True
        assert s.consume_nonce("v1", "c1", "nonce-1", ts) is False
        assert s.consume_nonce("v1", "c1", "nonce-2", ts) is True

    def test_nonce_consumed_check(self, store_pg):
        s = store_pg
        ts = 1_000_000.0
        s.consume_nonce("v2", "c2", "nonce-A", ts)
        assert s.nonce_consumed("v2", "c2", "nonce-A") is True
        assert s.nonce_consumed("v2", "c2", "nonce-B") is False

    def test_append_and_last_audit(self, store_pg):
        s = store_pg
        payload = b"\xde\xad\xbe\xef" * 8
        cert = {"issuer": "test", "seq": 1}
        s.append_audit(
            artifact_id="art-1",
            kind="transaction",
            seq=1,
            issued_at=1_000_000.0,
            transmission_id="tx-1",
            payload=payload,
            payload_sha256="aa" * 32,
            cert=cert,
        )
        last = s.last_audit()
        assert last is not None
        assert last == (1, "aa" * 32)

    def test_audit_chain(self, store_pg):
        s = store_pg
        for i in range(3):
            payload = f"payload-{i}".encode()
            cert = {"issuer": "test", "seq": i + 1}
            s.append_audit(
                artifact_id=f"art-{i}",
                kind="transaction",
                seq=i + 1,
                issued_at=1_000_000.0 + i,
                transmission_id=f"tx-{i}",
                payload=payload,
                payload_sha256="xx" * 32,
                cert=cert,
            )
        chain = s.audit_chain(limit=5)
        assert len(chain) == 3
        assert {c["issuer"] for c in chain} == {"test"}


# ------------------------------------------------------------------ cross-driver equality -


def _make_test_payloads():
    return {
        "json_obj": {"key": "value", "n": 3.14, "lst": [1, 2, 3]},
        "bytes_payload": b"\x01\x02\x03\x04",
        "sha256_32": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    }


class TestStoreCrossDriver:
    """Verify SQLite and PostgreSQL produce identical results."""

    def test_put_get_json_identical(self):
        data = _make_test_payloads()["json_obj"]

        # SQLite
        s_sqlite = Store(":memory:")
        s_sqlite.put_json("k", data)
        got_sqlite = s_sqlite.get_json("k")
        s_sqlite.close()

        # PostgreSQL (skip if psycopg not available)
        try:
            import psycopg  # noqa: F401
        except ImportError:
            pytest.skip("psycopg not installed; skipping PG cross-driver test")

        s_pg = Store(_make_pg_uri())
        s_pg.put_json("k", data)
        got_pg = s_pg.get_json("k")
        s_pg.close()

        assert got_sqlite == got_pg == data

    def test_nonce_consume_idempotent_identical(self):
        ts = 1_000_000.0

        # SQLite
        s = Store(":memory:")
        f1 = s.consume_nonce("v", "c", "n", ts)
        f2 = s.consume_nonce("v", "c", "n", ts)
        s.close()
        assert f1 is True
        assert f2 is False

        # PostgreSQL
        try:
            import psycopg  # noqa: F401
        except ImportError:
            pytest.skip("psycopg not installed; skipping PG cross-driver test")

        s2 = Store(_make_pg_uri())
        assert s2.consume_nonce("v", "c", "n", ts) is True
        assert s2.consume_nonce("v", "c", "n", ts) is False
        s2.close()

    def test_audit_chain_ordering_identical(self):
        data = _make_test_payloads()

        # SQLite
        s = Store(":memory:")
        for i in range(5):
            s.append_audit(
                artifact_id=f"art{i}",
                kind="transaction",
                seq=i + 1,
                issued_at=1_000_000.0 + i,
                transmission_id=f"tx{i}",
                payload=data["bytes_payload"],
                payload_sha256=data["sha256_32"],
                cert={"issuer": "test", "seq": i + 1},
            )
        chain_sqlite = s.audit_chain(limit=100)
        s.close()

        # PostgreSQL
        try:
            import psycopg  # noqa: F401
        except ImportError:
            pytest.skip("psycopg not installed; skipping PG cross-driver test")

        s2 = Store(_make_pg_uri())
        for i in range(5):
            s2.append_audit(
                artifact_id=f"art{i}",
                kind="transaction",
                seq=i + 1,
                issued_at=1_000_000.0 + i,
                transmission_id=f"tx{i}",
                payload=data["bytes_payload"],
                payload_sha256=data["sha256_32"],
                cert={"issuer": "test", "seq": i + 1},
            )
        chain_pg = s2.audit_chain(limit=100)
        s2.close()

        seq_sqlite = [c["seq"] for c in chain_sqlite]
        seq_pg = [c["seq"] for c in chain_pg]
        assert seq_sqlite == seq_pg == list(range(1, 6))