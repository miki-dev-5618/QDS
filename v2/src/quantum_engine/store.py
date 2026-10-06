"""
Persistent state (SQLite, standard library only).

What survives a restart:
  * link state of the circuit breaker and its full transition log;
  * consumed replay nonces per verifier;
  * every signed audit artifact (transaction records, incidents, resets), stored
    as the exact signed payload bytes plus the certificate JSON, in hash-chain order.

What does not: verifier distribution records (one-time quantum evidence) and
signer sessions. After a restart, sessions distributed before it cannot be
verified and must be re-sent; their audit records remain verifiable.

``Store(":memory:")`` gives the same behaviour without a file (tests, experiments).
Every write is a single transaction under one lock, so concurrent server
workers inside one process see consistent state. Multiple *processes* sharing
one file rely on SQLite's own locking.
"""
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA = """
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


class Store:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY")
        self._lock = threading.RLock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    def close(self):
        with self._lock:
            self._db.close()

    # -------------------------------------------------------------- key/value
    def get_json(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put_json(self, key: str, value: Any):
        with self._lock:
            self._db.execute("INSERT INTO kv(key, value) VALUES(?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))

    # ------------------------------------------------------------ transitions
    def save_link_transition(self, links: Dict[str, Any], transition: Dict[str, Any]):
        """Persist the new link table and its transition entry atomically."""
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.execute("INSERT INTO kv(key, value) VALUES('links', ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps(links),))
                self._db.execute(
                    "INSERT INTO transitions(ts, link, old_state, new_state, actor, reason, evidence_id, "
                    "policy_version, incident_id) VALUES(?,?,?,?,?,?,?,?,?)",
                    (transition["ts"], transition["link"], transition["old_state"], transition["new_state"],
                     transition["actor"], transition.get("reason"), transition.get("evidence_id"),
                     transition.get("policy_version"), transition.get("incident_id")))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def transitions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT ts, link, old_state, new_state, actor, reason, evidence_id, policy_version, incident_id "
                "FROM transitions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        keys = ("ts", "link", "old_state", "new_state", "actor", "reason", "evidence_id", "policy_version",
                "incident_id")
        return [dict(zip(keys, r)) for r in rows]

    # ----------------------------------------------------------------- nonces
    def consume_nonce(self, verifier: str, channel: str, nonce: str, ts: float) -> bool:
        """Atomically mark a nonce consumed. False if it was already consumed."""
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO nonces(verifier, channel, nonce, consumed_at) "
                                   "VALUES(?,?,?,?)", (verifier, channel, nonce, ts))
            return cur.rowcount == 1

    def nonce_consumed(self, verifier: str, channel: str, nonce: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM nonces WHERE verifier=? AND channel=? AND nonce=?",
                                    (verifier, channel, nonce)).fetchone() is not None

    # ------------------------------------------------------------------ audit
    def last_audit(self) -> Optional[Tuple[int, str]]:
        """(seq, payload_sha256) of the newest artifact, or None."""
        with self._lock:
            row = self._db.execute("SELECT seq, payload_sha256 FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        return (row[0], row[1]) if row else None

    def append_audit(self, artifact_id: str, kind: str, seq: int, issued_at: float,
                     transmission_id: Optional[str], payload: bytes, payload_sha256: str, cert: Dict[str, Any]):
        with self._lock:
            self._db.execute(
                "INSERT INTO audit(artifact_id, kind, seq, issued_at, transmission_id, payload, payload_sha256, cert) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (artifact_id, kind, seq, issued_at, transmission_id, payload, payload_sha256, json.dumps(cert)))

    def get_audit(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._db.execute("SELECT cert FROM audit WHERE artifact_id = ?", (artifact_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_payload(self, artifact_id: str) -> Optional[bytes]:
        with self._lock:
            row = self._db.execute("SELECT payload FROM audit WHERE artifact_id = ?", (artifact_id,)).fetchone()
        return bytes(row[0]) if row else None

    def audit_chain(self, kind: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        q = "SELECT cert FROM audit" + (" WHERE kind = ?" if kind else "") + " ORDER BY seq ASC LIMIT ?"
        args = (kind, limit) if kind else (limit,)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [json.loads(r[0]) for r in rows]
