"""E4: KeyProvider interface, rotation that keeps old records verifiable offline, and the SoftHSM provider."""
import json
import os
import pathlib
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.quantum_engine.audit import (AuditAuthority, build_reset_record, verify_certificate,
                                      verify_certificate_report, verify_chain)
from src.quantum_engine.key_provider import (KeyProvider, SoftHSMKeyProvider, SoftwareKeyProvider,
                                             make_key_provider)
from src.quantum_engine.signers import ED25519, key_id_for, pq_provider

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERIFY = str(ROOT / "tools" / "verify_audit.py")


def issue(authority, i):
    """A real (schema-valid) audit record, appended to the authority's hash chain."""
    return authority.issue(build_reset_record([], "admin", f"key provider test {i}"), f"RST-{i}")


# ------------------------------------------------------------------ fake provider (interface contract)
class FakeKeyProvider(KeyProvider):
    """In-memory Ed25519 keys: the smallest provider that satisfies the interface."""
    name = "fake"

    def __init__(self):
        self.keys, self.retired = [], []
        self._new()

    def _new(self):
        sk = Ed25519PrivateKey.generate()
        pem = sk.public_key().public_bytes(serialization.Encoding.PEM,
                                           serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        self.keys = [(key_id_for(ED25519, pem), pem, sk)]

    def active_keys(self):
        return [{"key_id": k, "algorithm": ED25519, "public_key": p, "status": "active", "post_quantum": False,
                 "provider": self.name} for k, p, _ in self.keys]

    def retired_keys(self):
        return self.retired

    def sign(self, key_id, data):
        return next(sk for k, _, sk in self.keys if k == key_id).sign(data)

    def rotate(self):
        old = self.active_keys()
        self.retired += [{**k, "status": "retired"} for k in old]
        self._new()
        return self._rotation_result(old)


def test_audit_authority_works_with_any_provider():
    fake = FakeKeyProvider()
    authority = AuditAuthority(provider=fake)
    old = issue(authority, 1)
    assert old["signatures"][0]["key_id"] == fake.active_keys()[0]["key_id"]   # key_id on every signature
    result = authority.rotate()
    new = issue(authority, 2)
    assert result["retired"] != result["active"]
    keyring = authority.trusted_keys()
    assert {k["status"] for k in keyring.values()} == {"active", "retired"}
    assert verify_certificate(old, keyring) and verify_certificate(new, keyring)
    assert verify_chain([old, new], keyring)["valid"]
    assert [k["status"] for k in fake.list_keys()] == ["active", "retired"]


def test_provider_selection(monkeypatch, tmp_path):
    monkeypatch.delenv("HEDWIG_KEY_PROVIDER", raising=False)
    assert isinstance(make_key_provider(str(tmp_path / "a.pem"), pq=False), SoftwareKeyProvider)
    assert AuditAuthority(str(tmp_path / "b.pem"), pq=False).provider.name == "software"
    monkeypatch.setenv("HEDWIG_KEY_PROVIDER", "vault")
    with pytest.raises(ValueError, match="HEDWIG_KEY_PROVIDER"):
        make_key_provider(str(tmp_path / "c.pem"), pq=False)
    monkeypatch.setenv("HEDWIG_KEY_PROVIDER", "softhsm")
    monkeypatch.delenv("HEDWIG_PKCS11_LIB", raising=False)
    with pytest.raises(RuntimeError, match="HEDWIG_PKCS11_LIB|python-pkcs11"):
        make_key_provider(str(tmp_path / "d.pem"), pq=False)


# ------------------------------------------------------------------ software provider + offline tool
def _verify_offline(tmp_path, data, keyring, *flags):
    cert_file, keys_file = tmp_path / "in.json", tmp_path / "keyring.json"
    cert_file.write_text(json.dumps(data), encoding="utf-8")
    keys_file.write_text(json.dumps({"keys": keyring}), encoding="utf-8")   # same shape as /api/audit-public-key
    return subprocess.run([sys.executable, VERIFY, str(cert_file), "--keys", str(keys_file), *flags],
                          capture_output=True, text=True)


def test_rotation_mid_chain_verifies_offline(tmp_path):
    key = str(tmp_path / "audit.pem")
    authority = AuditAuthority(key, pq=False)
    before = [issue(authority, 1), issue(authority, 2)]
    keyring_before = authority.trusted_keys()
    authority.rotate()
    after = [issue(authority, 3), issue(authority, 4)]
    assert before[0]["signatures"][0]["key_id"] != after[0]["signatures"][0]["key_id"]

    keyring = AuditAuthority(key, pq=False).trusted_keys()          # reloaded from disk, like a restart
    for cert in before + after:
        res = _verify_offline(tmp_path, cert, keyring)
        assert res.returncode == 0, res.stdout + res.stderr
    chain = _verify_offline(tmp_path, {"certificates": before + after}, keyring, "--chain")
    assert chain.returncode == 0 and "VALID chain of 4" in chain.stdout
    # A keyring saved before the rotation does not know the new key: new records must fail.
    assert _verify_offline(tmp_path, after[0], keyring_before).returncode == 1


@pytest.mark.skipif(pq_provider() is None, reason="no ML-DSA provider installed (pip install dilithium-py)")
def test_rotation_also_retires_the_post_quantum_key(tmp_path):
    key = str(tmp_path / "audit.pem")
    authority = AuditAuthority(key, pq=True)
    old = issue(authority, 1)
    result = authority.rotate()
    new = issue(authority, 2)
    assert len(result["retired_keys"]) == 2 and len(result["active_keys"]) == 2
    keyring = AuditAuthority(key, pq=True).trusted_keys()
    retired_pq = [k for k in keyring.values() if k["algorithm"] == "ML-DSA-65" and k["status"] == "retired"]
    assert len(retired_pq) == 1 and retired_pq[0]["post_quantum"] is True
    retired_file = next((tmp_path / "audit.pem.retired").glob("*.mldsa65.json"))
    assert "sk" not in json.loads(retired_file.read_text(encoding="utf-8"))   # only the public half is kept
    for cert in (old, new):
        assert verify_certificate_report(cert, keyring, require_pq=True)["valid"]


def test_rotation_without_key_path_is_refused():
    with pytest.raises(RuntimeError, match="persistent key path"):
        AuditAuthority(pq=False).rotate()


# ------------------------------------------------------------------ SoftHSM provider on a fake PKCS#11 token
class _FakeKey:
    def __init__(self, label, sk, public):
        self.label, self._sk, self._public = label, sk, public

    def __getitem__(self, attribute):          # Attribute.EC_POINT: DER OCTET STRING of the raw key
        raw = self._sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return b"\x04\x20" + raw

    def sign(self, data, mechanism=None):
        assert not self._public and mechanism is not None
        return self._sk.sign(data)


class FakeToken:
    """Stands in for a python-pkcs11 session; keys survive across 'sessions' like a real token."""

    def __init__(self):
        self.objects = {}

    def generate_keypair(self, key_type, mechanism=None, store=True, label=None, public_template=None):
        sk = Ed25519PrivateKey.generate()
        self.objects[label] = (_FakeKey(label, sk, True), _FakeKey(label, sk, False))
        return self.objects[label]

    def get_key(self, object_class=None, label=None):
        from pkcs11 import ObjectClass
        pub, priv = self.objects[label]
        return pub if object_class == ObjectClass.PUBLIC_KEY else priv


def test_softhsm_provider_signs_rotates_and_survives_restart(tmp_path):
    pytest.importorskip("pkcs11", reason="python-pkcs11 not installed (pip install -r requirements-hsm.txt)")
    token, key = FakeToken(), str(tmp_path / "audit.pem")
    provider = SoftHSMKeyProvider(key, pq=False, session_factory=lambda: token)
    authority = AuditAuthority(key, provider=provider)
    old = issue(authority, 1)
    assert provider.active_keys()[0]["provider"] == "pkcs11:softhsm"
    assert not os.path.exists(key)                                     # no private key file in software
    authority.rotate()
    new = issue(authority, 2)

    restarted = SoftHSMKeyProvider(key, pq=False, session_factory=lambda: token)
    assert restarted.active_keys() == provider.active_keys()          # same active key after a restart
    keyring = restarted.get_public_keys()
    for cert in (old, new):
        res = _verify_offline(tmp_path, cert, keyring)
        assert res.returncode == 0, res.stdout
    assert len(token.objects) == 2


@pytest.mark.skipif(not os.environ.get("HEDWIG_PKCS11_LIB"),
                    reason="real SoftHSM2 not configured (set HEDWIG_PKCS11_LIB, HEDWIG_PKCS11_PIN, HEDWIG_PKCS11_TOKEN)")
def test_real_softhsm_token(tmp_path):
    key = str(tmp_path / "audit.pem")
    authority = AuditAuthority(key, pq=False, provider=SoftHSMKeyProvider(key, pq=False))
    old = issue(authority, 1)
    authority.rotate()
    new = issue(authority, 2)
    keyring = authority.trusted_keys()
    assert verify_certificate(old, keyring) and verify_certificate(new, keyring)
