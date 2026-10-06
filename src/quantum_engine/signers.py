"""
Audit signature algorithms.

  * Ed25519   - classical (NOT post-quantum). Always available (``cryptography``).
  * ML-DSA-65 - FIPS 204 post-quantum signature. Optional: used only when a
                provider is installed, tried in this order:
                  1. ``liboqs-python`` (import ``oqs``)  - C implementation
                  2. ``dilithium-py`` (import ``dilithium_py``) - pure-Python
                     reference implementation, not side-channel hardened;
                     suitable for this demonstration only.

A certificate lists every signature with its algorithm and key id. Hybrid
certificates (Ed25519 + ML-DSA-65) verify only if *every* listed signature
verifies, so the record stays secure if either algorithm holds. Existing
Ed25519-only records are never relabelled as post-quantum.
"""
import base64
import hashlib
import json
import os
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ED25519 = "Ed25519"
ML_DSA_65 = "ML-DSA-65"


def key_id_for(algorithm: str, public_key: str) -> str:
    return hashlib.sha256(f"{algorithm}|{public_key}".encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ Ed25519
class Ed25519Signer:
    algorithm = ED25519
    post_quantum = False
    provider = "cryptography"

    def __init__(self, key: Ed25519PrivateKey):
        self._key = key
        self.public_key = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        self.key_id = key_id_for(self.algorithm, self.public_key)

    @classmethod
    def load_or_create(cls, path: Optional[str]) -> "Ed25519Signer":
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return cls(serialization.load_pem_private_key(f.read(), password=None))
        key = Ed25519PrivateKey.generate()
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "wb") as f:
                f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
        return cls(key)

    def sign(self, data: bytes) -> bytes:
        return self._key.sign(data)


def _ed25519_verify(public_key: str, signature: bytes, data: bytes) -> bool:
    try:
        pub = serialization.load_pem_public_key(public_key.encode("ascii"))
        if not isinstance(pub, Ed25519PublicKey):
            return False
        pub.verify(signature, data)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ---------------------------------------------------------------- ML-DSA-65
def pq_provider() -> Optional[str]:
    """Name of an installed ML-DSA provider, or None."""
    try:
        import oqs  # noqa: F401
        return "liboqs"
    except Exception:
        pass
    try:
        from dilithium_py.ml_dsa import ML_DSA_65 as _  # noqa: F401
        return "dilithium-py"
    except Exception:
        return None


class _Provider:
    def __init__(self, name: str):
        self.name = name

    def keygen(self):
        if self.name == "liboqs":
            import oqs
            with oqs.Signature(ML_DSA_65) as s:
                pk = s.generate_keypair()
                return pk, s.export_secret_key()
        from dilithium_py.ml_dsa import ML_DSA_65 as M
        return M.keygen()

    def sign(self, sk: bytes, data: bytes) -> bytes:
        if self.name == "liboqs":
            import oqs
            with oqs.Signature(ML_DSA_65, secret_key=sk) as s:
                return s.sign(data)
        from dilithium_py.ml_dsa import ML_DSA_65 as M
        return M.sign(sk, data)

    def verify(self, pk: bytes, data: bytes, sig: bytes) -> bool:
        try:
            if self.name == "liboqs":
                import oqs
                with oqs.Signature(ML_DSA_65) as s:
                    return bool(s.verify(data, sig, pk))
            from dilithium_py.ml_dsa import ML_DSA_65 as M
            return bool(M.verify(pk, data, sig))
        except Exception:
            return False


class MLDSA65Signer:
    algorithm = ML_DSA_65
    post_quantum = True

    def __init__(self, pk: bytes, sk: bytes, provider: str):
        self._sk = sk
        self._provider = _Provider(provider)
        self.provider = provider
        self.public_key = base64.b64encode(pk).decode("ascii")
        self.key_id = key_id_for(self.algorithm, self.public_key)

    @classmethod
    def load_or_create(cls, path: Optional[str]) -> Optional["MLDSA65Signer"]:
        provider = pq_provider()
        if provider is None:
            return None
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return cls(base64.b64decode(d["pk"]), base64.b64decode(d["sk"]), provider)
        pk, sk = _Provider(provider).keygen()
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"algorithm": ML_DSA_65, "pk": base64.b64encode(pk).decode("ascii"),
                           "sk": base64.b64encode(sk).decode("ascii")}, f)
        return cls(pk, sk, provider)

    def sign(self, data: bytes) -> bytes:
        return self._provider.sign(self._sk, data)


# ------------------------------------------------------------------ verify
def verify_signature(algorithm: str, public_key: str, signature_b64: str, data: bytes) -> bool:
    try:
        sig = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False
    if algorithm == ED25519:
        return _ed25519_verify(public_key, sig, data)
    if algorithm == ML_DSA_65:
        provider = pq_provider()
        if provider is None:
            return False  # cannot check: treated as a failure, never as a pass
        try:
            pk = base64.b64decode(public_key)
        except (ValueError, TypeError):
            return False
        return _Provider(provider).verify(pk, data, sig)
    return False
