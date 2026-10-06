"""
Canonical JSON encoding used for everything that is hashed or signed.

Rules (hedwig-canonical/1):
  * UTF-8 bytes, no BOM; object keys sorted by code point; no insignificant
    whitespace (separators "," and ":"); non-ASCII characters emitted as-is.
  * Integers as decimal; floats in Python's shortest round-trip repr;
    NaN and +/-Infinity are rejected.
  * Strings are hashed exactly as received: no Unicode normalisation. A
    message in NFC and the same text in NFD are different messages.
  * Tuples encode as arrays.
"""
import hashlib
import json
from typing import Any

CANONICAL_VERSION = "hedwig-canonical/1"


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha3_256_hex(data: bytes) -> str:
    return hashlib.sha3_256(data).hexdigest()


def digest_json(obj: Any, alg: str = "sha256") -> str:
    data = canonical_json(obj)
    return sha3_256_hex(data) if alg == "sha3-256" else sha256_hex(data)
