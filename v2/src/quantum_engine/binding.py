"""
Message/context binding for a one-time quantum signature.

Security model (classical, computational - stated explicitly):
  * During distribution Alice sends each verifier, over the authenticated
    classical channel, a commitment
        C = SHA-256( "HEDWIG-QDS-v2|commitment|" || canonical(context) || "|" || sig || "|" || r )
    where ``sig`` is the one-time Pauli-state signature and ``r`` a 256-bit
    random blinding value. The verifier stores C as a trusted local record.
  * ``context`` holds protocol version, session id, sender, allowed verifiers,
    random nonce, timestamp, the digest algorithm and digest(message).
    Canonical encoding follows ``canonical.py`` (sorted keys, UTF-8, no
    Unicode normalisation, no NaN/Infinity).
  * The message digest is domain separated:
        digest = H( "HEDWIG-QDS-v2|message|" || UTF-8(message) )
    with H = SHA-256 (default) or SHA3-512 (selectable). The algorithm name is
    inside the committed context, so it cannot be downgraded after commitment.
  * At reveal time the verifier recomputes the digest of the *received*
    message and the commitment of the *received* context and signature.
    Any change to message, nonce, timestamp, sender, verifier set or
    signature makes the recomputation differ from C (assuming collision
    resistance of the hash).
  * The hash does not entangle the message with the quantum states and does
    not provide information-theoretic security; the quantum elimination check
    is what ties the revealed signature to the states that were distributed.
"""
import hashlib
import secrets
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Tuple, Optional

from .canonical import canonical_json

PROTOCOL_VERSION = "HEDWIG-QDS-v2.2"
_DOMAIN = b"HEDWIG-QDS-v2|commitment|"
_MESSAGE_DOMAIN = b"HEDWIG-QDS-v2|message|"
DIGEST_ALGORITHMS = {"sha256": hashlib.sha256, "sha3-512": hashlib.sha3_512}
DEFAULT_DIGEST = "sha256"


def message_digest(message: str, alg: str = DEFAULT_DIGEST) -> str:
    if alg not in DIGEST_ALGORITHMS:
        raise ValueError(f"Unsupported digest algorithm {alg!r}")
    return DIGEST_ALGORITHMS[alg](_MESSAGE_DOMAIN + message.encode("utf-8")).hexdigest()


def encode_signature(signature: List[Tuple[int, int]]) -> str:
    return "".join(f"{int(b)}{int(ba)}" for b, ba in signature)


@dataclass
class SignedContext:
    session_id: str
    sender: str
    verifiers: List[str]
    nonce: str
    timestamp: float
    message_digest: str
    digest_alg: str = DEFAULT_DIGEST
    version: str = PROTOCOL_VERSION

    def canonical_bytes(self) -> bytes:
        return canonical_json(asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SignedContext":
        return cls(**d)

    @classmethod
    def new(cls, sender: str, verifiers: List[str], message: str,
            session_id: Optional[str] = None, timestamp: Optional[float] = None,
            digest_alg: str = DEFAULT_DIGEST) -> "SignedContext":
        import time
        return cls(
            session_id=session_id or f"S-{secrets.token_hex(8)}",
            sender=sender,
            verifiers=list(verifiers),
            nonce=secrets.token_hex(16),
            timestamp=time.time() if timestamp is None else timestamp,
            message_digest=message_digest(message, digest_alg),
            digest_alg=digest_alg,
        )


def commitment(context: SignedContext, signature: List[Tuple[int, int]], blinding: str) -> str:
    h = hashlib.sha256()
    h.update(_DOMAIN)
    h.update(context.canonical_bytes())
    h.update(b"|")
    h.update(encode_signature(signature).encode("ascii"))
    h.update(b"|")
    h.update(bytes.fromhex(blinding))
    return h.hexdigest()


def new_blinding() -> str:
    return secrets.token_hex(32)


def digest_matches(message: str, context: SignedContext) -> bool:
    """Recompute the digest of a received message under the context's (committed) algorithm."""
    try:
        return message_digest(message, context.digest_alg) == context.message_digest
    except ValueError:
        return False


@dataclass
class SignedPackage:
    """Everything a verifier receives at reveal time (classical)."""
    context: SignedContext
    message: str
    revealed_signature: List[Tuple[int, int]]
    blinding: str
    forwarded_by: Optional[str] = None

    def copy(self, **changes) -> "SignedPackage":
        d = dict(
            context=SignedContext.from_dict(self.context.to_dict()),
            message=self.message,
            revealed_signature=list(self.revealed_signature),
            blinding=self.blinding,
            forwarded_by=self.forwarded_by,
        )
        d.update(changes)
        return SignedPackage(**d)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context": self.context.to_dict(),
            "message": self.message,
            "revealed_signature": [list(s) for s in self.revealed_signature],
            "forwarded_by": self.forwarded_by,
        }
