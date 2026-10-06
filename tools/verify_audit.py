"""
Verify HEDWIG audit records offline, without trusting the server that produced them.

    # one certificate, against a keyring saved from GET /api/audit-public-key
    python tools/verify_audit.py hedwig-audit-TX-1234ABCD.json --keys keyring.json

    # a single Ed25519 PEM key
    python tools/verify_audit.py hedwig-audit-TX-1234ABCD.json --pubkey audit_pub.pem

    # the whole hash chain saved from GET /api/audit/chain
    python tools/verify_audit.py chain.json --chain --keys keyring.json

    # demand a post-quantum (ML-DSA-65) signature as well
    python tools/verify_audit.py cert.json --keys keyring.json --require-pq

Checks: schema version, canonical payload hash, every listed signature
(hybrid certificates need all of them), the attached evidence against the
signed digests, and - with --chain - the hash links and sequence numbers.
Without --keys/--pubkey the keys embedded in the file are used, which proves
the record was not altered after signing but not who signed it.
Exit code 0 = valid, 1 = invalid.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.quantum_engine.audit import verify_certificate_report, verify_chain  # noqa: E402


def load_trusted(args):
    if args.keys:
        with open(args.keys, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("keys", data)
    if args.pubkey:
        with open(args.pubkey, encoding="ascii") as f:
            return f.read()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("certificate", help="certificate JSON, or a chain export with --chain")
    ap.add_argument("--keys", help="keyring JSON (the response of /api/audit-public-key)")
    ap.add_argument("--pubkey", help="PEM file with a single Ed25519 public key")
    ap.add_argument("--chain", action="store_true", help="the file is a chain export (/api/audit/chain)")
    ap.add_argument("--require-pq", action="store_true", help="fail unless an ML-DSA-65 signature verifies")
    args = ap.parse_args()

    with open(args.certificate, encoding="utf-8") as f:
        data = json.load(f)
    trusted = load_trusted(args)
    origin = "trusted keys" if trusted is not None else "embedded keys only (integrity, not origin)"

    if args.chain:
        certs = data.get("certificates", data)
        res = verify_chain(certs, trusted)
        print(f"{'VALID' if res['valid'] else 'INVALID'} chain of {res['length']} record(s) ({origin})")
        for p in res["problems"]:
            print(f"  - #{p['index']}: {p['problem']}")
        sys.exit(0 if res["valid"] else 1)

    rep = verify_certificate_report(data, trusted, require_pq=args.require_pq)
    rec = data.get("record", {})
    ident = rec.get("transmission_id") or rec.get("incident_id") or rec.get("kind")
    outcome = (rec.get("outcome") or {}).get("classification") or (rec.get("trigger") or {}).get("classification")
    print(f"{'VALID' if rep['valid'] else 'INVALID'}: {rec.get('kind')} {ident} {outcome or ''} ({origin})")
    for k, v in rep.get("checks", {}).items():
        if k != "signatures":
            print(f"  {k}: {v}")
    for s in rep.get("checks", {}).get("signatures", []):
        print(f"  signature {s['algorithm']} key {s['key_id']}: {'ok' if s['valid'] else 'FAIL'}")
    if rep.get("error"):
        print(f"  error: {rep['error']}")
    sys.exit(0 if rep["valid"] else 1)


if __name__ == "__main__":
    main()
