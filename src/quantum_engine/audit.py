"""
Q-Cert: signed, versioned, hash-chained audit records (``hedwig-audit/2``).

Three artifact kinds share one append-only chain:
  * ``transaction`` - issued automatically when each transmission is assessed;
  * ``incident``    - issued at the moment a link is quarantined;
  * ``link_reset``  - issued when an administrator resets a link (actor + reason).

Certificate layout:

    {
      "format": "hedwig-audit/2",
      "record": {...},             # signed: canonical_json(record) is the payload
      "payload_sha256": "...",     # sha256 of the exact signed bytes
      "signatures": [{"algorithm", "key_id", "post_quantum", "signature"}],
      "public_keys": {key_id: {"algorithm", "public_key"}},  # convenience copy only
      "evidence": {...}            # unsigned, bound by record.evidence_digests
    }

What a valid certificate proves: the holder of the listed key(s) signed
exactly these record bytes, and (when evidence is attached) the evidence
matches the signed digests. What it does not prove: that the simulator's
physical assumptions held, or that simulated measurements correspond to real
hardware. Ed25519 is classical; a certificate is "post-quantum signed" only
when it also carries a verifying ML-DSA-65 signature. The record is not
zero-knowledge: it discloses its evidence. Message plaintext is redacted by
default (only the domain-separated digest is recorded).
"""
import base64
import copy
import glob
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Union

from .binding import message_digest
from .canonical import CANONICAL_VERSION, canonical_json, digest_json, sha256_hex
from .security import ASSUMPTIONS
from .signers import ED25519, Ed25519Signer, MLDSA65Signer, key_id_for, verify_signature

AUDIT_VERSION = "hedwig-audit/2"
SIMULATOR_VERSION = "HEDWIG V2.2"
GENESIS = "0" * 64

DISCLAIMERS = [
    "Signed audit record of a SIMULATED quantum digital signature run; not evidence about physical hardware.",
    "Bounds are illustrative finite-sample Hoeffding/binomial bounds under the listed assumptions, not a "
    "composable security proof. Message binding relies on computational hash assumptions.",
    "Ed25519 is classical. Post-quantum protection applies only if an ML-DSA-65 signature is present and verifies.",
    "Not zero-knowledge: the attached evidence discloses verifier records.",
]


# ------------------------------------------------------------------ evidence
def _redact_verification(v: Dict[str, Any], alg: str) -> Dict[str, Any]:
    out = {k: val for k, val in v.items() if k != "received_message"}
    if "received_message" in v:
        out["received_message_digest"] = message_digest(v["received_message"] or "", alg)
    return out


def build_evidence(tx: Dict[str, Any]) -> Dict[str, Any]:
    alg = (tx.get("context") or {}).get("digest_alg", "sha256")
    return {
        "verifications": {k: _redact_verification(tx[k], alg) for k in ("bob", "charlie") if tx.get(k)},
        "additional_verifications": [_redact_verification(v, alg) for v in tx.get("additional_verifications", [])],
        "channel_test": tx.get("channel"),
        "symmetrisation": tx.get("symmetrisation"),
    }


def evidence_hash(evidence: Any) -> str:
    return sha256_hex(canonical_json(evidence))


def evidence_digests(evidence: Dict[str, Any]) -> Dict[str, Any]:
    per_verifier = {}
    for name, v in evidence.get("verifications", {}).items():
        per_verifier[f"{name}/{v.get('mode', 'direct')}"] = digest_json(v.get("eliminated_states", []), "sha3-256")
    for v in evidence.get("additional_verifications", []):
        per_verifier[f"{v.get('verifier')}/{v.get('mode')}"] = digest_json(v.get("eliminated_states", []),
                                                                         "sha3-256")
    sym = evidence.get("symmetrisation")
    return {
        "full_evidence_sha256": evidence_hash(evidence),
        "elimination_sha3_256": per_verifier,
        "symmetrisation_actions_sha3_256": digest_json(sym, "sha3-256") if sym else None,
        "channel_test_sha256": digest_json(evidence.get("channel_test")) if evidence.get("channel_test") else None,
    }


# ------------------------------------------------------------------ records
def _fidelity(channel: Optional[Dict[str, Any]], tier2: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    model = ("Uniform Pauli (depolarising) channel acting on Pauli-eigenstate tokens: X and Y flip a Z-eigenstate, "
             "Z does not (and symmetrically for X), so average teleported-state fidelity F = 1 - QBER.")
    if not channel:
        return {"status": "not measured", "reason": "no channel test in this transmission"}
    if channel.get("alarm") or (tier2 or {}).get("attribution") == "channel_disturbance":
        return {"status": "not reported", "model": model,
                "reason": "the channel test rejected the honest depolarising model, so F = 1 - QBER does not apply"}
    return {"status": "model-based estimate (not a direct fidelity measurement)", "model": model,
            "estimate": round(1 - channel["qber_estimate"], 4),
            "ci95": [round(1 - channel["qber_ci_high"], 4), round(1 - channel["qber_ci_low"], 4)],
            "from": f"{channel['error_count']}/{channel['test_count']} test-token errors"}


def _assurance(accepted: bool, bounds: Dict[str, Any], target: str) -> Dict[str, Any]:
    if not accepted:
        return {"level": "REJECTED", "basis": "at least one verifier rejected the transmission"}
    meets = [b["meets_target"] for b in bounds.values()]
    need = max((b["n_required_for_target"] for b in bounds.values()), default=None)
    if meets and all(meets):
        return {"level": "ACCEPTED - BOUNDS MEET TARGET", "target": target,
                "basis": "every verifier's forgery / false-reject / repudiation bound is <= target"}
    return {"level": "ACCEPTED - DEMONSTRATION GRADE", "target": target,
            "basis": f"bounds above target at this signature length; about {need} checked copies per verifier "
                     f"would be needed"}


def build_record(tx: Dict[str, Any], params: Dict[str, Any], policy: Optional[Dict[str, Any]] = None,
                 evidence: Optional[Dict[str, Any]] = None, freshness_window_s: float = 120.0) -> Dict[str, Any]:
    """Versioned transaction record for one transmission dict (QDSExecutionResult.to_dict)."""
    evidence = evidence if evidence is not None else build_evidence(tx)
    ctx = tx.get("context") or {}
    report = tx["threat_report"]
    verifs = {f"{k}/{v['mode']}": v for k, v in evidence["verifications"].items()}
    for v in evidence["additional_verifications"]:
        verifs[f"{v['verifier']}/{v['mode']}"] = v

    summary, bounds = {}, {}
    for name, v in verifs.items():
        summary[name] = {"accepted": v["is_valid"], "mismatches": v["mismatches"], "checked": v["total_checked"],
                         "limit": v["acceptance_limit"], "checks": v["checks"],
                         "received_message_digest": v.get("received_message_digest")}
        b = v.get("bounds") or {}
        if b:
            bounds[name] = {"values": b["values"], "inputs": b["inputs"], "decision_rule": b["decision_rule"],
                            "formulas": b["formulas"], "n_required_for_target": b["n_required_for_target"],
                            "meets_target": b["meets_target"]}
    direct = [v for v in evidence["verifications"].values() if v.get("mode") == "direct"]
    accepted = bool(direct) and all(v["is_valid"] for v in direct) and not report["is_threat_detected"]
    ts = ctx.get("timestamp")

    return {
        "version": AUDIT_VERSION,
        "kind": "transaction",
        "canonicalization": CANONICAL_VERSION,
        "issued_at": time.time(),
        "transmission_id": tx["transmission_id"],
        "session_id": ctx.get("session_id"),
        "protocol_version": ctx.get("version"),
        "simulator": {"version": SIMULATOR_VERSION, "backend": tx.get("backend")},
        "signer": ctx.get("sender"),
        "verifiers": ctx.get("verifiers"),
        "nonce": ctx.get("nonce"),
        "created_at": ts,
        "expires_at": ts + freshness_window_s if ts is not None else None,
        "message": {"digest_alg": ctx.get("digest_alg"), "digest": ctx.get("message_digest"),
                    "plaintext_included": False},
        "outcome": {"accepted": accepted, "classification": report["classification"],
                    "verdict": report["verdict"], "decided_by": report.get("decided_by"),
                    "evidence_p": report.get("evidence_p")},
        "response": tx.get("response"),
        "enforcement": {k: v for k, v in (tx.get("enforcement") or {}).items() if k != "channel_state"},
        "verification_summary": summary,
        "channel_test": tx.get("channel"),
        "tier2": report.get("tier2"),
        "bounds": {"per_verifier": bounds, "assumptions": ASSUMPTIONS,
                   "status": "illustrative bound under stated assumptions (not a security proof)"},
        "fidelity": _fidelity(tx.get("channel"), report.get("tier2")),
        "assurance": _assurance(accepted, bounds, f"{params.get('target_failure', 1e-6):.0e}"),
        "parameters": params,
        "policy": policy,
        "evidence_digests": evidence_digests(evidence),
        "disclaimers": DISCLAIMERS,
    }


def build_incident_record(incident_id: str, transition: Dict[str, Any], tx: Dict[str, Any],
                          evidence_sha256: str, policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    report = tx["threat_report"]
    return {
        "version": AUDIT_VERSION,
        "kind": "incident",
        "canonicalization": CANONICAL_VERSION,
        "issued_at": time.time(),
        "incident_id": incident_id,
        "transmission_id": tx["transmission_id"],
        "link": transition["link"],
        "transition": transition,
        "trigger": {"classification": report["classification"], "decided_by": report.get("decided_by"),
                    "evidence_p": report.get("evidence_p"), "details": report["details"],
                    "response": tx.get("response")},
        "evidence_sha256": evidence_sha256,
        "purged_records": (tx.get("enforcement") or {}).get("purged_records", 0),
        "timing": {k: tx.get("latency", {}).get(k) for k in ("detection_us", "enforcement_us")},
        "policy": policy,
        "note": "Purged records are unaccepted software distribution records; no physical Bell pair is destroyed.",
    }


def build_reset_record(transitions: List[Dict[str, Any]], actor: str, reason: str) -> Dict[str, Any]:
    return {"version": AUDIT_VERSION, "kind": "link_reset", "canonicalization": CANONICAL_VERSION,
            "issued_at": time.time(), "actor": actor, "reason": reason, "transitions": transitions}


# --------------------------------------------------------------- authority
class AuditAuthority:
    """
    Verifier-side audit service. Keys persist next to ``key_path`` so records
    stay verifiable across restarts; ``rotate()`` retires the active Ed25519
    key (kept for verification) and creates a new one.

    pq: True = require ML-DSA-65 (error if no provider), False = Ed25519 only,
        None = hybrid when a provider is installed (default).
    """

    def __init__(self, key_path: Optional[str] = None, pq: Optional[bool] = None, store=None):
        self.key_path = key_path
        self.store = store
        self._lock = threading.Lock()
        self._chain_mem: Optional[tuple] = None
        self._ed = Ed25519Signer.load_or_create(key_path)
        self._pq = None
        if pq is not False:
            self._pq = MLDSA65Signer.load_or_create(key_path + ".mldsa65.json" if key_path else None)
            if pq is True and self._pq is None:
                raise RuntimeError("ML-DSA-65 requested but no provider is installed "
                                   "(pip install dilithium-py, or liboqs-python).")
        self._retired: Dict[str, Dict[str, str]] = {}
        if key_path:
            for p in sorted(glob.glob(os.path.join(self._retired_dir(), "*.pem"))):
                s = Ed25519Signer.load_or_create(p)
                self._retired[s.key_id] = {"algorithm": ED25519, "public_key": s.public_key}

    def _retired_dir(self) -> str:
        return (self.key_path or "") + ".retired"

    @property
    def signers(self):
        return [s for s in (self._ed, self._pq) if s is not None]

    @property
    def public_key_pem(self) -> str:
        return self._ed.public_key

    @property
    def post_quantum(self) -> bool:
        return self._pq is not None

    def trusted_keys(self) -> Dict[str, Dict[str, Any]]:
        keys = {s.key_id: {"algorithm": s.algorithm, "public_key": s.public_key, "status": "active",
                           "post_quantum": s.post_quantum, "provider": s.provider} for s in self.signers}
        for kid, k in self._retired.items():
            keys[kid] = {**k, "status": "retired", "post_quantum": False}
        return keys

    def rotate(self) -> Dict[str, Any]:
        if not self.key_path:
            raise RuntimeError("Key rotation needs a persistent key path.")
        with self._lock:
            old = self._ed
            os.makedirs(self._retired_dir(), exist_ok=True)
            shutil.move(self.key_path, os.path.join(self._retired_dir(), f"{old.key_id}.pem"))
            self._retired[old.key_id] = {"algorithm": ED25519, "public_key": old.public_key}
            self._ed = Ed25519Signer.load_or_create(self.key_path)
        return {"retired": old.key_id, "active": self._ed.key_id}

    def sign(self, record: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Sign a record (adds the signature suite to it first, so the suite itself is signed)."""
        record = dict(record)
        record["signature_suite"] = [{"algorithm": s.algorithm, "key_id": s.key_id, "post_quantum": s.post_quantum}
                                     for s in self.signers]
        payload = canonical_json(record)
        cert = {
            "format": AUDIT_VERSION,
            "record": record,
            "payload_sha256": sha256_hex(payload),
            "signatures": [{"algorithm": s.algorithm, "key_id": s.key_id, "post_quantum": s.post_quantum,
                            "signature": base64.b64encode(s.sign(payload)).decode("ascii")} for s in self.signers],
            "public_keys": {s.key_id: {"algorithm": s.algorithm, "public_key": s.public_key} for s in self.signers},
        }
        if evidence is not None:
            cert["evidence"] = evidence
        return cert

    def issue(self, record: Dict[str, Any], artifact_id: str, evidence: Optional[Dict[str, Any]] = None
              ) -> Dict[str, Any]:
        """Append to the hash chain, sign, and persist the exact signed bytes."""
        with self._lock:
            last = self.store.last_audit() if self.store is not None else self._chain_mem
            seq, prev = (last[0] + 1, last[1]) if last else (1, GENESIS)
            record = dict(record)
            record["chain"] = {"seq": seq, "prev_payload_sha256": prev}
            cert = self.sign(record, evidence)
            payload = canonical_json(cert["record"])
            if self.store is not None:
                self.store.append_audit(artifact_id, record["kind"], seq, record["issued_at"],
                                        record.get("transmission_id"), payload, cert["payload_sha256"], cert)
            self._chain_mem = (seq, cert["payload_sha256"])
        return cert


# -------------------------------------------------------------- verification
TrustedKeys = Union[None, str, Dict[str, Dict[str, Any]]]


def _trusted_map(trusted: TrustedKeys) -> Optional[Dict[str, Dict[str, Any]]]:
    if trusted is None:
        return None
    if isinstance(trusted, str):
        return {key_id_for(ED25519, trusted): {"algorithm": ED25519, "public_key": trusted}}
    return trusted


def verify_certificate_report(cert: Dict[str, Any], trusted: TrustedKeys = None,
                              require_pq: bool = False) -> Dict[str, Any]:
    """
    Check a certificate offline. ``trusted`` is the audit authority's key set
    obtained out-of-band (a PEM string or {key_id: {algorithm, public_key}}).
    Without it the embedded keys are used, which proves integrity, not origin.
    """
    checks: Dict[str, Any] = {}
    try:
        record = cert["record"]
        payload = canonical_json(record)
        checks["schema"] = cert.get("format") == AUDIT_VERSION and record.get("version") == AUDIT_VERSION
        checks["payload_hash"] = sha256_hex(payload) == cert.get("payload_sha256")
        suite = {(s["algorithm"], s["key_id"]) for s in record.get("signature_suite", [])}
        listed = {(s["algorithm"], s["key_id"]) for s in cert.get("signatures", [])}
        checks["signature_suite_matches"] = bool(listed) and suite == listed

        keys = _trusted_map(trusted)
        origin = "trusted keys" if keys is not None else "embedded keys (integrity only, origin not proven)"
        keys = keys if keys is not None else cert.get("public_keys", {})
        sig_results = []
        for s in cert.get("signatures", []):
            k = keys.get(s["key_id"])
            ok = bool(k) and k["algorithm"] == s["algorithm"] and \
                verify_signature(s["algorithm"], k["public_key"], s["signature"], payload)
            sig_results.append({"algorithm": s["algorithm"], "key_id": s["key_id"], "valid": ok,
                                "key_known": bool(k)})
        checks["signatures"] = sig_results
        checks["all_signatures_valid"] = bool(sig_results) and all(r["valid"] for r in sig_results)
        checks["post_quantum_signed"] = any(r["valid"] and s.get("post_quantum")
                                            for r, s in zip(sig_results, cert.get("signatures", [])))

        if "evidence" in cert and record.get("kind") == "transaction":
            checks["evidence_digests_match"] = evidence_digests(cert["evidence"]) == record.get("evidence_digests")
        checks["origin"] = origin
        required = ["schema", "payload_hash", "signature_suite_matches", "all_signatures_valid"]
        if "evidence_digests_match" in checks:
            required.append("evidence_digests_match")
        valid = all(checks[k] for k in required) and (checks["post_quantum_signed"] or not require_pq)
        return {"valid": valid, "checks": checks}
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        return {"valid": False, "checks": checks, "error": f"{type(e).__name__}: {e}"}


def verify_certificate(cert: Dict[str, Any], trusted_public_key_pem: TrustedKeys = None) -> bool:
    return verify_certificate_report(cert, trusted_public_key_pem)["valid"]


def verify_chain(certs: List[Dict[str, Any]], trusted: TrustedKeys = None) -> Dict[str, Any]:
    """Verify every certificate and the hash links between consecutive ones (oldest first)."""
    problems = []
    prev_hash, prev_seq = None, None
    for i, c in enumerate(certs):
        rep = verify_certificate_report(c, trusted)
        if not rep["valid"]:
            problems.append({"index": i, "problem": "certificate invalid", "checks": rep.get("checks")})
        chain = c.get("record", {}).get("chain", {})
        if prev_hash is not None:
            if chain.get("prev_payload_sha256") != prev_hash:
                problems.append({"index": i, "problem": "hash link broken (record removed, reordered or altered)"})
            if chain.get("seq") != prev_seq + 1:
                problems.append({"index": i, "problem": f"sequence gap: {prev_seq} -> {chain.get('seq')}"})
        prev_hash = sha256_hex(canonical_json(c.get("record", {})))
        prev_seq = chain.get("seq")
    return {"valid": not problems, "length": len(certs), "problems": problems}


def strip_evidence(cert: Dict[str, Any]) -> Dict[str, Any]:
    c = copy.deepcopy(cert)
    c.pop("evidence", None)
    return c
