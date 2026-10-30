# Audit key providers

The audit authority (`src/quantum_engine/audit.py`) gets its signing keys from a **key provider**
(`src/quantum_engine/key_provider.py`), chosen with `HEDWIG_KEY_PROVIDER`:

| Value | Ed25519 key | ML-DSA-65 key | Status |
|---|---|---|---|
| `software` (default) | PEM file at `HEDWIG_AUDIT_KEY` (default `data/audit_ed25519.pem`) | JSON file next to it (`.mldsa65.json`), when a PQ provider is installed | Implemented and tested |
| `softhsm` | Generated and used **inside a PKCS#11 token** (SoftHSM2, a software HSM emulator) | Still a software file: SoftHSM2 has no ML-DSA mechanism | Implemented; tested against a fake token, and against real SoftHSM2 only when you configure it (see below) |

Every audit signature carries the `key_id` of the key that made it, so a verifier picks the right public key from
the keyring (`GET /api/audit-public-key`).

## Interface

```python
class KeyProvider:
    active_keys()       # keys that sign new records (Ed25519 first, then ML-DSA-65 if enabled)
    sign(key_id, data)  # signature bytes from one active key
    rotate()            # retire the active keys, create new ones
    list_keys()         # every key with status "active" or "retired"
    get_public_keys()   # the verification keyring {key_id: {algorithm, public_key, status, post_quantum, provider}}
```

A new backend (a cloud KMS, a real HSM, a vault) only has to implement these methods; `AuditAuthority(...,
provider=MyProvider())` uses it without other changes. `tests/test_key_provider.py` shows a minimal in-memory one.

## Rotation

`POST /api/audit/rotate-key` (admin) or `AuditAuthority.rotate()`:

- **software**: the old Ed25519 PEM moves to `<key>.retired/<key_id>.pem`; the old ML-DSA-65 key is replaced and
  only its **public** half is written to `<key>.retired/<key_id>.mldsa65.json`.
- **softhsm**: a new Ed25519 key pair is generated in the token under a new label; the old private key stays in the
  token, unused, and its public half is recorded in `<key>.pkcs11.json` together with the active label.

Retired public keys stay in the keyring, so records signed before a rotation still verify, online and offline:

```bash
curl http://127.0.0.1:8000/api/audit-public-key -o keyring.json
python tools/verify_audit.py chain.json --chain --keys keyring.json
```

A keyring saved **before** a rotation does not contain the new key, so it cannot verify records signed after it.
Download the keyring again after rotating.

## Using SoftHSM2 (optional)

SoftHSM2 is a software emulator of an HSM. It does not give the physical protection of a real hardware security
module; it lets you exercise the PKCS#11 code path.

1. Install SoftHSM2. The upstream project is <https://github.com/opendnssec/SoftHSMv2>; on Windows you need a
   build of it from a source you trust (check where a binary comes from before installing it).
2. Install the Python binding into your virtual environment:
   ```bash
   pip install -r requirements-hsm.txt
   ```
3. Create a token (choose your own PINs; do not commit them):
   ```bash
   softhsm2-util --init-token --free --label hedwig
   ```
4. Point HEDWIG at it and start the server:
   ```bash
   export HEDWIG_KEY_PROVIDER=softhsm
   export HEDWIG_PKCS11_LIB=/path/to/softhsm2.dll      # libsofthsm2.so on Linux
   export HEDWIG_PKCS11_TOKEN=hedwig
   export HEDWIG_PKCS11_PIN=<your user PIN>
   python -m uvicorn server:app --host 127.0.0.1 --port 8000
   ```
   `GET /api/audit-public-key` then reports `"key_provider": "softhsm"`, and the Ed25519 key's `provider` is
   `pkcs11:softhsm`.
5. With the same variables set, `python -m pytest tests/test_key_provider.py -q` also runs
   `test_real_softhsm_token` against the real token (it is skipped otherwise).

Requirements: a SoftHSM2 build with EdDSA support (2.6 or later, built against OpenSSL 1.1.1+), because the
provider uses `CKM_EC_EDWARDS_KEY_PAIR_GEN` / `CKM_EDDSA` on curve Ed25519 (OID 1.3.101.112).
