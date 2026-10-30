"""
Key providers for the audit authority: where signing keys live and how they rotate.

Interface (``KeyProvider``):
  active_keys()      keys that sign new records, in signing order (Ed25519 first)
  sign(key_id, data) signature bytes from one active key
  rotate()           retire the active keys (public halves stay in the keyring) and create new ones
  list_keys()        every key with its status ("active" / "retired")
  get_public_keys()  the verification keyring {key_id: {...}} - active and retired

Providers, chosen with HEDWIG_KEY_PROVIDER:
  software (default) PEM / JSON files next to the configured key path (the original behaviour).
  softhsm            the Ed25519 key is generated and used inside a PKCS#11 token (SoftHSM2, a
                     *software HSM emulator*) through python-pkcs11. ML-DSA-65 has no PKCS#11
                     mechanism in SoftHSM, so the post-quantum key stays in software in this mode.
                     Configure with HEDWIG_PKCS11_LIB (path to the softhsm2 library),
                     HEDWIG_PKCS11_TOKEN (token label, default "hedwig") and HEDWIG_PKCS11_PIN.

Public keys keep the formats the verifier already understands (Ed25519: SubjectPublicKeyInfo PEM;
ML-DSA-65: base64), so ``verify_certificate`` and tools/verify_audit.py need no changes.
"""
import glob
import json
import os
import shutil
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .signers import ED25519, ML_DSA_65, Ed25519Signer, MLDSA65Signer, key_id_for

PROVIDERS = ("software", "softhsm")


def _entry(key_id: str, algorithm: str, public_key: str, status: str, provider: str) -> Dict[str, Any]:
    return {"key_id": key_id, "algorithm": algorithm, "public_key": public_key, "status": status,
            "post_quantum": algorithm == ML_DSA_65, "provider": provider}


class KeyProvider(ABC):
    name = "abstract"

    @abstractmethod
    def active_keys(self) -> List[Dict[str, Any]]:
        """Signing keys for new records: [{key_id, algorithm, public_key, post_quantum, provider, status}]."""

    @abstractmethod
    def retired_keys(self) -> List[Dict[str, Any]]:
        """Keys that no longer sign but must still verify old records."""

    @abstractmethod
    def sign(self, key_id: str, data: bytes) -> bytes:
        """Sign with one active key."""

    @abstractmethod
    def rotate(self) -> Dict[str, Any]:
        """Retire the active keys and create new ones."""

    def list_keys(self) -> List[Dict[str, Any]]:
        return self.active_keys() + self.retired_keys()

    def get_public_keys(self) -> Dict[str, Dict[str, Any]]:
        return {k["key_id"]: {f: v for f, v in k.items() if f != "key_id"} for k in self.list_keys()}

    def _rotation_result(self, old: List[Dict[str, Any]]) -> Dict[str, Any]:
        new = self.active_keys()
        ed_old = next(k["key_id"] for k in old if k["algorithm"] == ED25519)
        ed_new = next(k["key_id"] for k in new if k["algorithm"] == ED25519)
        return {"retired": ed_old, "active": ed_new,
                "retired_keys": [k["key_id"] for k in old], "active_keys": [k["key_id"] for k in new]}


# ------------------------------------------------------------------ software
class SoftwareKeyProvider(KeyProvider):
    """Keys in files: Ed25519 PEM at ``key_path``, ML-DSA-65 JSON at ``key_path.mldsa65.json``;
    retired keys move to ``key_path.retired/``."""
    name = "software"

    def __init__(self, key_path: Optional[str] = None, pq: Optional[bool] = None):
        self.key_path = key_path
        self._ed = Ed25519Signer.load_or_create(key_path)
        self._pq = _load_pq(key_path, pq)
        self._retired: Dict[str, Dict[str, Any]] = {}
        if key_path:
            for p in sorted(glob.glob(os.path.join(self._retired_dir(), "*.pem"))):
                s = Ed25519Signer.load_or_create(p)
                self._retired[s.key_id] = _entry(s.key_id, ED25519, s.public_key, "retired", self.name)
            self._retired.update(_retired_pq(self._retired_dir(), self.name))

    def _retired_dir(self) -> str:
        return (self.key_path or "") + ".retired"

    def _signers(self):
        return [s for s in (self._ed, self._pq) if s is not None]

    def active_keys(self) -> List[Dict[str, Any]]:
        return [_entry(s.key_id, s.algorithm, s.public_key, "active", s.provider) for s in self._signers()]

    def retired_keys(self) -> List[Dict[str, Any]]:
        return list(self._retired.values())

    def sign(self, key_id: str, data: bytes) -> bytes:
        for s in self._signers():
            if s.key_id == key_id:
                return s.sign(data)
        raise KeyError(f"{key_id} is not an active signing key")

    def rotate(self) -> Dict[str, Any]:
        if not self.key_path:
            raise RuntimeError("Key rotation needs a persistent key path.")
        old = self.active_keys()
        os.makedirs(self._retired_dir(), exist_ok=True)
        shutil.move(self.key_path, os.path.join(self._retired_dir(), f"{self._ed.key_id}.pem"))
        self._retired[self._ed.key_id] = _entry(self._ed.key_id, ED25519, self._ed.public_key, "retired", self.name)
        self._ed = Ed25519Signer.load_or_create(self.key_path)
        if self._pq is not None:
            self._pq = _rotate_pq(self.key_path, self._pq, self._retired_dir(), self._retired, self.name)
        return self._rotation_result(old)


def _pq_path(key_path: Optional[str]) -> Optional[str]:
    return key_path + ".mldsa65.json" if key_path else None


def _load_pq(key_path: Optional[str], pq: Optional[bool]) -> Optional[MLDSA65Signer]:
    """pq: True = require ML-DSA-65, False = Ed25519 only, None = hybrid when a provider is installed."""
    if pq is False:
        return None
    signer = MLDSA65Signer.load_or_create(_pq_path(key_path))
    if pq is True and signer is None:
        raise RuntimeError("ML-DSA-65 requested but no provider is installed "
                           "(pip install dilithium-py, or liboqs-python).")
    return signer


def _retired_pq(retired_dir: str, provider: str) -> Dict[str, Dict[str, Any]]:
    """Retired ML-DSA-65 public keys (read straight from JSON, so no PQ library is needed to list them)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(retired_dir, "*.mldsa65.json"))):
        with open(p, encoding="utf-8") as f:
            pk = json.load(f)["pk"]
        kid = key_id_for(ML_DSA_65, pk)
        out[kid] = _entry(kid, ML_DSA_65, pk, "retired", provider)
    return out


def _rotate_pq(key_path: str, signer: MLDSA65Signer, retired_dir: str, retired: Dict[str, Dict[str, Any]],
               provider: str) -> MLDSA65Signer:
    os.makedirs(retired_dir, exist_ok=True)
    with open(os.path.join(retired_dir, f"{signer.key_id}.mldsa65.json"), "w", encoding="utf-8") as f:
        json.dump({"algorithm": ML_DSA_65, "pk": signer.public_key}, f)   # public half only
    os.remove(_pq_path(key_path))
    retired[signer.key_id] = _entry(signer.key_id, ML_DSA_65, signer.public_key, "retired", provider)
    return MLDSA65Signer.load_or_create(_pq_path(key_path))


# ------------------------------------------------------------------ SoftHSM (PKCS#11)
ED25519_OID = "1.3.101.112"
_LABEL_PREFIX = "hedwig-audit-ed25519"


def _open_pkcs11_session():
    """A read-write user session on the configured PKCS#11 token (python-pkcs11)."""
    try:
        import pkcs11
    except ImportError as e:
        raise RuntimeError("HEDWIG_KEY_PROVIDER=softhsm needs python-pkcs11 "
                           "(pip install -r requirements-hsm.txt)") from e
    lib_path = os.environ.get("HEDWIG_PKCS11_LIB")
    pin = os.environ.get("HEDWIG_PKCS11_PIN")
    if not lib_path or not pin:
        raise RuntimeError("HEDWIG_KEY_PROVIDER=softhsm needs HEDWIG_PKCS11_LIB (softhsm2 library path) "
                           "and HEDWIG_PKCS11_PIN (token user PIN); see docs/KEY_PROVIDERS.md")
    token = pkcs11.lib(lib_path).get_token(token_label=os.environ.get("HEDWIG_PKCS11_TOKEN", "hedwig"))
    return token.open(user_pin=pin, rw=True)


def _ed25519_pem_from_ec_point(ec_point: bytes) -> str:
    raw = ec_point[2:] if (len(ec_point) == 34 and ec_point[:2] == b"\x04\x20") else ec_point  # DER OCTET STRING
    return Ed25519PublicKey.from_public_bytes(raw).public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


class SoftHSMKeyProvider(KeyProvider):
    """Ed25519 inside a PKCS#11 token (SoftHSM2 emulator); ML-DSA-65, if enabled, in software.

    The token holds the private keys. A small state file (``key_path.pkcs11.json``) records which token
    label is active and the public halves of retired keys, so old records verify after rotation.
    """
    name = "softhsm"

    def __init__(self, key_path: Optional[str] = None, pq: Optional[bool] = None,
                 session_factory: Callable[[], Any] = _open_pkcs11_session):
        self.key_path = key_path
        self._session = session_factory()
        self._state_path = key_path + ".pkcs11.json" if key_path else None
        self._state = {"active_label": None, "retired": {}}
        if self._state_path and os.path.exists(self._state_path):
            with open(self._state_path, encoding="utf-8") as f:
                self._state = json.load(f)
        if not self._state["active_label"]:
            self._new_ed_key()
        self._pq = _load_pq(key_path, pq)
        if key_path:
            self._state["retired"].update(_retired_pq(key_path + ".retired", self.name))

    # token helpers
    def _keys(self, label: str):
        from pkcs11 import ObjectClass
        return (self._session.get_key(object_class=ObjectClass.PUBLIC_KEY, label=label),
                self._session.get_key(object_class=ObjectClass.PRIVATE_KEY, label=label))

    def _new_ed_key(self):
        from pkcs11 import Attribute, KeyType, Mechanism
        from pkcs11.util.ec import encode_named_curve_parameters
        label = f"{_LABEL_PREFIX}-{int(time.time() * 1000)}"
        self._session.generate_keypair(KeyType.EC_EDWARDS, mechanism=Mechanism.EC_EDWARDS_KEY_PAIR_GEN,
                                       store=True, label=label,
                                       public_template={Attribute.EC_PARAMS: encode_named_curve_parameters(ED25519_OID)})
        self._state["active_label"] = label
        self._save()

    def _save(self):
        if self._state_path:
            os.makedirs(os.path.dirname(os.path.abspath(self._state_path)), exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)

    def _ed_public(self) -> str:
        from pkcs11 import Attribute
        return _ed25519_pem_from_ec_point(self._keys(self._state["active_label"])[0][Attribute.EC_POINT])

    # interface
    def active_keys(self) -> List[Dict[str, Any]]:
        pem = self._ed_public()
        keys = [_entry(key_id_for(ED25519, pem), ED25519, pem, "active", "pkcs11:softhsm")]
        if self._pq is not None:
            keys.append(_entry(self._pq.key_id, ML_DSA_65, self._pq.public_key, "active", self._pq.provider))
        return keys

    def retired_keys(self) -> List[Dict[str, Any]]:
        return list(self._state["retired"].values())

    def sign(self, key_id: str, data: bytes) -> bytes:
        from pkcs11 import Mechanism
        if self._pq is not None and key_id == self._pq.key_id:
            return self._pq.sign(data)
        pem = self._ed_public()
        if key_id != key_id_for(ED25519, pem):
            raise KeyError(f"{key_id} is not an active signing key")
        return self._keys(self._state["active_label"])[1].sign(data, mechanism=Mechanism.EDDSA)

    def rotate(self) -> Dict[str, Any]:
        old = self.active_keys()
        ed = old[0]
        self._state["retired"][ed["key_id"]] = {**ed, "status": "retired"}
        self._new_ed_key()   # the old private key stays in the token, unused; its public half is in the keyring
        if self._pq is not None:
            if not self.key_path:
                raise RuntimeError("ML-DSA-65 rotation needs a persistent key path.")
            self._pq = _rotate_pq(self.key_path, self._pq, self.key_path + ".retired", self._state["retired"],
                                  self.name)
            self._save()
        return self._rotation_result(old)


def make_key_provider(key_path: Optional[str] = None, pq: Optional[bool] = None,
                      name: Optional[str] = None) -> KeyProvider:
    name = (name or os.environ.get("HEDWIG_KEY_PROVIDER", "software")).strip().lower()
    if name == "software":
        return SoftwareKeyProvider(key_path, pq)
    if name == "softhsm":
        return SoftHSMKeyProvider(key_path, pq)
    raise ValueError(f"HEDWIG_KEY_PROVIDER must be one of {PROVIDERS}, got {name!r}")
