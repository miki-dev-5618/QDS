"""\
Persistent state — SQLite (default) or PostgreSQL via HEDWIG_DATABASE_URL.

What survives a restart:
  * link state of the circuit breaker and its full transition log;
  * consumed replay nonces per verifier;
  * every signed audit artifact (transaction records, incidents, resets), stored
    as the exact signed payload bytes plus the certificate JSON, in hash-chain order.

``Store(\":memory:\")`` gives the same behaviour without a file (tests, experiments).
Every write is a single transaction under one lock, so concurrent server
workers inside one process see consistent state. Multiple *processes* sharing
one file rely on SQLite's own locking.

Database driver selection:
  * No ``HEDWIG_DATABASE_URL`` env var  →  SQLite  (default, ``data/hedwig.db``).
  * ``HEDWIG_DATABASE_URL`` set to a ``postgresql://`` URI  →  PostgreSQL
    (requires ``psycopg[binary]``).  The public API is identical; only the
    underlying ``?`` vs ``%s`` placeholder style and a couple of DDL
    keywords differ.
"""
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

# ---- PostgreSQL support (optional, added when HEDWIG_DATABASE_URL is postgresql://) ----
try:
    import psycopg  # psycopg 3.x — synchronous, thread-friendly
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False

# ------------------------------------------------------------------ SQL schemas ----
# SQLite-compatible DDL.  PostgreSQL will use the same strings because
# SQLite since 3.24.0 and PostgreSQL both support ON CONFLICT ... DO UPDATE/DO NOTHING.
# The only difference is ``AUTOINCREMENT`` → plain ``INTEGER PRIMARY KEY``
# (PostgreSQL does not use that keyword; a plain primary key works fine because
# the code never relies on sequence-valued IDs).

_SCHEMA_SQLITE = """\
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transitions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
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
    payload        BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL,
    cert           TEXT NOT NULL
);
"""

_SCHEMA_PG = """\
CREATE TABLE IF NOT EXISTS kv (
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
);
"""

# ------------------------------------------------------------------- Store class ----
class Store:
    """Persistent state backed by SQLite or PostgreSQL.

    The *public API* is identical regardless of driver.  Internally the
    correct SQL placeholder style and DDL are chosen at instantiation time.
    """

    def __init__(self, path: str = ":memory:"):
        """*path* is either a SQLite file path or a ``postgresql://`` URI.

        If *path* does not start with ``postgresql://`` the SQLite driver is
        used (default, falling back to ``data/hedwig.db`` when called from
        ``server.py``).
        """
        # ------------------------------------------------------------------ driver detection
        if isinstance(path, str) and path.startswith("postgresql://"):
            self.driver = "postgresql"
            if not HAS_PSYCOPG:
                raise ImportError(
                    "psycopg (with binary support) is required for PostgreSQL support. "
                    "Install with: pip install psycopg[binary]"
                )
            self._conn = psycopg.connect(path)
            self._conn.autocommit = True
            self._lock = threading.RLock()
            with self._lock:
                self._conn.execute(_SCHEMA_PG)
        else:
            self.driver = "sqlite"
            self.path = path
            if path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            import sqlite3 as sqlmod

            self._db = sqlmod.connect(
                path, check_same_thread=False, isolation_level=None
            )
            self._db.execute(
                "PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY"
            )
            self._lock = threading.RLock()
            with self._lock:
                self._db.executescript(_SCHEMA_SQLITE)

    # --------------------------------------------------------------- close / reset
    def close(self):
        with self._lock:
            if self.driver == "postgresql":
                self._conn.close()
            else:
                self._db.close()

    # -------------------------------------------------------------- key/value
    def get_json(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if self.driver == "postgresql":
                row = self._conn.execute(
                    "SELECT value FROM kv WHERE key = %s", (key,)
                ).fetchone()
            else:
                row = self._db.execute(
                    "SELECT value FROM kv WHERE key = ?", (key,)
                ).fetchone()
        return json.loads(row[0]) if row else default

    def put_json(self, key: str, value: Any):
        with self._lock:
            if self.driver == "postgresql":
                self._conn.execute(
                    "INSERT INTO kv(key, value) VALUES(%s, %s) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )
            else:
                self._db.execute(
                    "INSERT INTO kv(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )

    # ------------------------------------------------------------ transitions
    def save_link_transition(self, links: Dict[str, Any], transition: Dict[str, Any]):
        """Persist the new link table and its transition entry atomically."""
        with self._lock:
            if self.driver == "postgresql":
                self._conn.execute("BEGIN")
                try:
                    self._conn.execute(
                        "INSERT INTO kv(key, value) VALUES(%s, %s) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        ("links", json.dumps(links)),
                    )
                    self._conn.execute(
                        """INSERT INTO transitions
                           (ts, link, old_state, new_state, actor, reason, evidence_id,
                            policy_version, incident_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            transition["ts"],
                            transition["link"],
                            transition["old_state"],
                            transition["new_state"],
                            transition["actor"],
                            transition.get("reason"),
                            transition.get("evidence_id"),
                            transition.get("policy_version"),
                            transition.get("incident_id"),
                        ),
                    )
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
            else:
                self._db.execute("BEGIN")
                try:
                    self._db.execute(
                        "INSERT INTO kv(key, value) VALUES(?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        ("links", json.dumps(links)),
                    )
                    self._db.execute(
                        """INSERT INTO transitions
                           (ts, link, old_state, new_state, actor, reason, evidence_id,
                            policy_version, incident_id)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            transition["ts"],
                            transition["link"],
                            transition["old_state"],
                            transition["new_state"],
                            transition["actor"],
                            transition.get("reason"),
                            transition.get("evidence_id"),
                            transition.get("policy_version"),
                            transition.get("incident_id"),
                        ),
                    )
                    self._db.execute("COMMIT")
                except Exception:
                    self._db.rollback()
                    raise

    def transitions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            if self.driver == "postgresql":
                rows = self._conn.execute(
                    "SELECT ts, link, old_state, new_state, actor, reason, evidence_id, "
                    "policy_version, incident_id "
                    "FROM transitions ORDER BY id DESC LIMIT %s",
                    (limit,),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT ts, link, old_state, new_state, actor, reason, evidence_id, "
                    "policy_version, incident_id "
                    "FROM transitions ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        keys = (
            "ts",
            "link",
            "old_state",
            "new_state",
            "actor",
            "reason",
            "evidence_id",
            "policy_version",
            "incident_id",
        )
        return [dict(zip(keys, r)) for r in rows]

    # ----------------------------------------------------------------- nonces
    def consume_nonce(self, verifier: str, channel: str, nonce: str, ts: float) -> bool:
        """Atomically mark a nonce consumed. False if it was already consumed."""
        with self._lock:
            if self.driver == "postgresql":
                cur = self._conn.execute(
                    """INSERT INTO nonces (verifier, channel, nonce, consumed_at)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (verifier, channel, nonce) DO NOTHING""",
                    (verifier, channel, nonce, ts),
                )
                return cur.rowcount == 1
            else:
                cur = self._db.execute(
                    "INSERT OR IGNORE INTO nonces(verifier, channel, nonce, consumed_at) "
                    "VALUES(?,?,?,?)",
                    (verifier, channel, nonce, ts),
                )
                return cur.rowcount == 1

    def nonce_consumed(self, verifier: str, channel: str, nonce: str) -> bool:
        with self._lock:
            if self.driver == "postgresql":
                return self._conn.execute(
                    "SELECT 1 FROM nonces WHERE verifier=%s AND channel=%s AND nonce=%s",
                    (verifier, channel, nonce),
                ).fetchone() is not None
            else:
                return self._db.execute(
                    "SELECT 1 FROM nonces WHERE verifier=? AND channel=? AND nonce=?",
                    (verifier, channel, nonce),
                ).fetchone() is not None

    # ------------------------------------------------------------------ audit
    def last_audit(self) -> Optional[Tuple[int, str]]:
        """(seq, payload_sha256) of the newest artifact, or None."""
        with self._lock:
            if self.driver == "postgresql":
                row = self._conn.execute(
                    "SELECT seq, payload_sha256 FROM audit ORDER BY seq DESC LIMIT 1"
                ).fetchone()
            else:
                row = self._db.execute(
                    "SELECT seq, payload_sha256 FROM audit ORDER BY seq DESC LIMIT 1"
                ).fetchone()
        return (row[0], row[1]) if row else None

    def append_audit(self, artifact_id: str, kind: str, seq: int, issued_at: float,
                     transmission_id: Optional[str], payload: bytes, payload_sha256: str, cert: Dict[str, Any]):
        with self._lock:
            if self.driver == "postgresql":
                self._conn.execute(
                    "INSERT INTO audit(artifact_id, kind, seq, issued_at, transmission_id, "
                    "payload, payload_sha256, cert) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        artifact_id,
                        kind,
                        seq,
                        issued_at,
                        transmission_id,
                        psycopg.Binary(payload) if self.driver == "postgresql" else payload,
                        payload_sha256,
                        json.dumps(cert),
                    ),
                )
            else:
                self._db.execute(
                    "INSERT INTO audit(artifact_id, kind, seq, issued_at, transmission_id, "
                    "payload, payload_sha256, cert) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        artifact_id,
                        kind,
                        seq,
                        issued_at,
                        transmission_id,
                        payload,
                        payload_sha256,
                        json.dumps(cert),
                    ),
                )

    def get_audit(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self.driver == "postgresql":
                row = self._conn.execute(
                    "SELECT cert FROM audit WHERE artifact_id = %s", (artifact_id,)
                ).fetchone()
            else:
                row = self._db.execute(
                    "SELECT cert FROM audit WHERE artifact_id = ?", (artifact_id,)
                ).fetchone()
        return json.loads(row[0]) if row else None

    def get_payload(self, artifact_id: str) -> Optional[bytes]:
        with self._lock:
            if self.driver == "postgresql":
                row = self._conn.execute(
                    "SELECT payload FROM audit WHERE artifact_id = %s", (artifact_id,)
                ).fetchone()
                return bytes(row[0]) if row else None
            else:
                row = self._db.execute(
                    "SELECT payload FROM audit WHERE artifact_id = ?", (artifact_id,)
                ).fetchone()
                return bytes(row[0]) if row else None

    def audit_chain(self, kind: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        if self.driver == "postgresql":
            w = "WHERE kind = %s" if kind else ""
            q = f"SELECT cert FROM audit {w} ORDER BY seq ASC LIMIT %s"
            args = (kind, limit) if kind else (limit,)
        else:
            w = "WHERE kind = ?" if kind else ""
            q = f"SELECT cert FROM audit {w} ORDER BY seq ASC LIMIT ?"
            args = (kind, limit) if kind else (limit,)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [json.loads(r[0]) for r in rows]
