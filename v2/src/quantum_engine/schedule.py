"""
Verifier measurement-basis schedules (exploratory, step 7 of the roadmap).

Default: each verifier draws every measurement basis from its private RNG.

Protocol chronology (all schedules):
  t0  Alice fixes the message and context (session_id, digest) and commits.
  t1  Tokens are teleported; each verifier measures copy j of position i in
      basis b(v, i, j). Alice's state preparation never depends on b.
  t2  Alice reveals message + signature; verifiers check eliminations.

  * RandomSchedule      b drawn from the verifier's RNG.            (baseline)
  * PublicHashSchedule  b = bit of SHA-256("basis-v1"|session|digest|v|i|j).
                        Anyone who knows the context can compute b before
                        t1 - including an eavesdropper. INSECURE BY DESIGN:
                        included only to measure the damage.
  * KeyedSchedule       b = bit of HMAC-SHA256(k_v, "basis-v1"|session|digest|v|i|j)
                        with k_v a secret held only by verifier v (never
                        shared with Alice or the other verifier). Without k_v
                        the schedule is pseudo-random, so it should perform
                        like RandomSchedule; its only gain is a reproducible,
                        auditable basis record derivable from (k_v, context).

``experiments/basis_schedule.py`` compares the three at equal qubit budgets.
"""
import hashlib
import hmac
import secrets
from typing import Dict, Optional

import numpy as np

_DOMAIN = b"HEDWIG-QDS-v2|basis-v1|"


def _label(session_id: str, digest: str, verifier: str, pos: int, copy: int) -> bytes:
    return _DOMAIN + f"{session_id}|{digest}|{verifier}|{pos}|{copy}".encode("utf-8")


class RandomSchedule:
    name = "random"
    public = False

    def basis(self, ctx, verifier: str, pos: int, copy: int, rng: np.random.Generator) -> int:
        return int(rng.integers(0, 2))


class PublicHashSchedule:
    name = "public_hash"
    public = True

    def basis(self, ctx, verifier: str, pos: int, copy: int, rng: np.random.Generator) -> int:
        return hashlib.sha256(_label(ctx.session_id, ctx.message_digest, verifier, pos, copy)).digest()[0] & 1


class KeyedSchedule:
    name = "keyed_hmac"
    public = False

    def __init__(self, keys: Optional[Dict[str, bytes]] = None):
        self.keys = keys or {}

    def _key(self, verifier: str) -> bytes:
        if verifier not in self.keys:
            self.keys[verifier] = secrets.token_bytes(32)
        return self.keys[verifier]

    def basis(self, ctx, verifier: str, pos: int, copy: int, rng: np.random.Generator) -> int:
        mac = hmac.new(self._key(verifier), _label(ctx.session_id, ctx.message_digest, verifier, pos, copy),
                       hashlib.sha256)
        return mac.digest()[0] & 1


SCHEDULES = {"random": RandomSchedule, "public_hash": PublicHashSchedule, "keyed_hmac": KeyedSchedule}
