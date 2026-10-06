"""
Server-side authentication for HEDWIG V2.

* Credentials are stored as PBKDF2-SHA256 hashes. Load them from the JSON file
  named by HEDWIG_USERS_FILE; without it the built-in demo accounts are used
  and a warning is logged (replace them before any shared deployment).
* Sessions are random 256-bit tokens held server-side, delivered in one
  HttpOnly, SameSite=Strict cookie per role (hedwig_admin, hedwig_bob,
  hedwig_charlie) so one browser can run all three demo terminals.

Create a users file:
    python auth.py add-user users.json alice admin
    set HEDWIG_USERS_FILE=users.json
"""
import getpass
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
from typing import Dict, Optional, Tuple

log = logging.getLogger("hedwig.auth")

ROLES = ("admin", "bob", "charlie")
ROLE_HOME = {"admin": "/admin", "bob": "/bob", "charlie": "/charlie"}
SIGNER_IDENTITY = {"admin": "alice"}   # the admin console signs as Alice
PBKDF2_ITERATIONS = 200_000
SESSION_TTL_SECONDS = 8 * 3600

_DEMO_USERS = {
    "admin": ("admin2026", "admin"),
    "alice": ("quantum2026", "admin"),
    "bob": ("quantum2026", "bob"),
    "charlie": ("quantum2026", "charlie"),
}


def cookie_name(role: str) -> str:
    return f"hedwig_{role}"


def hash_password(password: str, salt: Optional[str] = None) -> Dict[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return {"salt": salt, "hash": digest.hex()}


def load_users() -> Tuple[Dict[str, Dict[str, str]], bool]:
    """Returns (users, using_demo_credentials)."""
    path = os.environ.get("HEDWIG_USERS_FILE")
    if path:
        with open(path, encoding="utf-8") as f:
            users = json.load(f)
        for name, u in users.items():
            if u.get("role") not in ROLES:
                raise ValueError(f"User {name} has invalid role {u.get('role')}")
        return users, False
    log.warning("HEDWIG_USERS_FILE not set: using built-in DEMO credentials. "
                "Do not expose this server beyond localhost.")
    users = {}
    for name, (pw, role) in _DEMO_USERS.items():
        users[name] = {"role": role, **hash_password(pw)}
    return users, True


class Authenticator:
    def __init__(self):
        self.users, self.using_demo_credentials = load_users()
        self._sessions: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def check_password(self, username: str, password: str) -> Optional[str]:
        user = self.users.get(username)
        # Hash even for unknown users so timing does not reveal which names exist.
        salt = user["salt"] if user else "00" * 16
        candidate = hash_password(password, salt)["hash"]
        if user and hmac.compare_digest(candidate, user["hash"]):
            return user["role"]
        return None

    def create_session(self, username: str, role: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {"username": username, "role": role, "created": time.time()}
        return token

    def get_session(self, token: Optional[str], role: str) -> Optional[Dict]:
        if not token:
            return None
        with self._lock:
            sess = self._sessions.get(token)
            if not sess:
                return None
            if time.time() - sess["created"] > SESSION_TTL_SECONDS:
                del self._sessions[token]
                return None
            return sess if sess["role"] == role else None

    def revoke(self, token: Optional[str]):
        if token:
            with self._lock:
                self._sessions.pop(token, None)


def _cli():
    if len(sys.argv) != 5 or sys.argv[1] != "add-user" or sys.argv[4] not in ROLES:
        print("usage: python auth.py add-user <users.json> <username> <admin|bob|charlie>")
        sys.exit(2)
    path, username, role = sys.argv[2], sys.argv[3], sys.argv[4]
    users = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            users = json.load(f)
    password = getpass.getpass(f"Password for {username}: ")
    users[username] = {"role": role, **hash_password(password)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    print(f"Saved {username} ({role}) to {path}")


if __name__ == "__main__":
    _cli()
