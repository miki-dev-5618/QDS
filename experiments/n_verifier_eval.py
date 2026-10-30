"""
Evaluation of the optional N-verifier extension (plan §17, Phase 6).

Varies N (recipients), delivery mode (direct / chain with H = N - 1) and
signature length L separately, on the default depolarising channel and the
statevector backend, and records:

  * honest outcomes: per-event accept / reject / inconclusive and session outcome
  * a dishonest forwarder (message or signature altered): who rejected and why
  * resource cost: planned / sent tokens, reserve positions, copies per verifier
  * latency: distribution, delivery + forwarding, total
  * growth: transaction + transfer audit record bytes

Finite trials: zero accepted attacks is not a proof of zero forgery
probability. Exact per-event risks come from the applied rule; no aggregate
session-level bound is claimed (recipients' evidence comes from one
distribution and is not independent).

    python experiments/n_verifier_eval.py [--trials 40] [--seed 2026]
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.quantum_engine import (AuditAuthority, ChannelModel, SessionConfig, Store, TeleportationQDS,  # noqa: E402
                                ThreatScenarioConfig, ThreatType)
from src.quantum_engine.canonical import canonical_json  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (round(max(0.0, c - h), 4), round(min(1.0, c + h), 4))


def run_config(n: int, delivery: str, L: int, trials: int, seed: int, attack: str = None):
    store = Store(":memory:")
    eng = TeleportationQDS(backend="statevector", channel=ChannelModel(), store=store,
                           audit=AuditAuthority(store=store, pq=False))
    cfg = SessionConfig.build(n_verifiers=n, delivery=delivery)
    rng = np.random.default_rng(seed)
    ev = {"accepted": 0, "rejected": 0, "inconclusive": 0, "distribution_aborted": 0}
    sess, classes, causes = {}, {}, {}
    tokens_planned, tokens_sent, reserve_bits, copies, dist_ms, total_ms, rec_bytes = [], [], [], [], [], [], []
    attack_accepted_downstream = 0
    for _ in range(trials):
        eng.guard.reset()
        sc = None
        if attack:
            sc = ThreatScenarioConfig(ThreatType.DISHONEST_FORWARDER, dishonest_verifier=cfg.roster[0],
                                      forward_alteration=attack)
        t0 = time.perf_counter()
        res = eng.execute_protocol("regional instruction", L, rng=rng, config=cfg, scenario=sc)
        total_ms.append((time.perf_counter() - t0) * 1000)
        d = res.to_dict()
        s = res.transcript.session
        dist_ms.append(s.observation_ms)
        tokens_planned.append(s.tokens_planned)
        tokens_sent.append(s.tokens_sent)
        reserve_bits.append(len(s.reserve))
        for v in cfg.roster:
            rec = eng.verifiers[v].records.get(s.context.session_id)
            if rec:
                copies.append(sum(len(r) for r in rec.eliminated))
        for r in res.transcript.results:
            ev[r.status] = ev.get(r.status, 0) + 1
            if attack and r.mode == "forwarded" and r.forwarded_by == cfg.roster[0]:
                attack_accepted_downstream += int(r.accepted)
                cause = "+".join(c for c, bad in (("digest", not r.digest_matches),
                                                  ("commitment", not r.commitment_matches)) if bad)
                causes[cause or "elimination_only"] = causes.get(cause or "elimination_only", 0) + 1
        sess[d["session_outcome"]] = sess.get(d["session_outcome"], 0) + 1
        classes[d["threat_report"]["classification"]] = classes.get(d["threat_report"]["classification"], 0) + 1
        size = len(canonical_json(res.audit_cert["record"]))
        for t in res.transfer_records:
            size += len(canonical_json(store.get_audit(t["artifact_id"])["record"]))
        rec_bytes.append(size)
    n_events = sum(ev.values())
    out = {
        "N": n, "delivery": delivery, "H": cfg.max_depth, "L": L, "trials": trials,
        "scenario": f"dishonest_forwarder/{attack}" if attack else "authentic",
        "events": ev, "event_accept_rate": round(ev["accepted"] / n_events, 4) if n_events else None,
        "event_accept_ci95": wilson(ev["accepted"], n_events),
        "session_outcomes": sess, "classifications": classes,
        "tokens_planned_mean": round(float(np.mean(tokens_planned)), 1),
        "tokens_sent_mean": round(float(np.mean(tokens_sent)), 1),
        "reserve_positions_mean": round(float(np.mean(reserve_bits)), 1),
        "copies_per_verifier": {"mean": round(float(np.mean(copies)), 2), "min": int(np.min(copies)),
                                "max": int(np.max(copies))} if copies else None,
        "distribution_ms_p50": round(float(np.median(dist_ms)), 2),
        "total_ms_p50": round(float(np.median(total_ms)), 2),
        "audit_bytes_mean": int(np.mean(rec_bytes)),
    }
    if attack:
        out["altered_package_accepted_by_next_recipient"] = attack_accepted_downstream
        out["rejection_cause"] = causes
    return out


def rule_table(Ls=(32, 64, 128, 256), Hs=(1, 3, 9)):
    """Applied stage-1 limits per depth (exact policy, ~L checked copies, no reserve)."""
    from src.quantum_engine.security import SecurityParameters
    P = SecurityParameters()
    rows = []
    for L in Ls:
        for H in Hs:
            rules = [P.elimination_rule(L, depth=l, max_depth=H) for l in range(H + 1)]
            rows.append({"n_checked": L, "H": H, "limits_by_depth": [r.a1 for r in rules],
                         "all_meet_targets": all(r.sufficient for r in rules)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    results = []
    for L in (32, 64):
        for n in (2, 3, 5, 10):
            for delivery in ("direct", "chain"):
                results.append(run_config(n, delivery, L, args.trials, args.seed))
                print(json.dumps({k: results[-1][k] for k in ("N", "delivery", "L", "event_accept_rate",
                                                              "session_outcomes", "total_ms_p50")}))
    for n in (3, 10):
        for alt in ("message", "signature"):
            results.append(run_config(n, "chain", 64, args.trials, args.seed + 1, attack=alt))
            print(json.dumps({k: results[-1][k] for k in ("N", "scenario", "altered_package_accepted_by_next_recipient",
                                                          "rejection_cause")}))
    report = {"seed": args.seed, "trials_per_config": args.trials, "backend": "statevector",
              "channel": "ChannelModel() default depolarising", "results": results, "depth_rules": rule_table(),
              "notes": [
                  "Per-event statistics only; no session-level aggregate risk is claimed.",
                  "Zero accepted attacks in finite trials is not a proof of zero forgery probability.",
                  "Latency is simulator wall time on this host (statevector backend), not hardware timing.",
              ]}
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "n_verifier_eval.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(here, "n_verifier_eval.md"), "w", encoding="utf-8") as f:
        f.write(render_md(report))


def render_md(r):
    lines = ["# N-verifier extension: evaluation", "",
             f"Seed {r['seed']}, {r['trials_per_config']} trials per configuration, {r['backend']} backend, "
             f"{r['channel']}. Chain mode uses H = N - 1.", "",
             "## Honest sessions", "",
             "| L | N | delivery | events accepted (95% CI) | rejected | inconclusive | session outcomes | "
             "tokens planned | reserve | copies/verifier (min-max) | dist ms p50 | total ms p50 | audit bytes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in r["results"]:
        if x["scenario"] != "authentic":
            continue
        c = x["copies_per_verifier"]
        lines.append(f"| {x['L']} | {x['N']} | {x['delivery']} | {x['event_accept_rate']} {tuple(x['event_accept_ci95'])} | "
                     f"{x['events'].get('rejected', 0)} | {x['events'].get('inconclusive', 0)} | "
                     f"{', '.join(f'{k} {v}' for k, v in x['session_outcomes'].items())} | {x['tokens_planned_mean']} | "
                     f"{x['reserve_positions_mean']} | {c['mean']} ({c['min']}-{c['max']}) | {x['distribution_ms_p50']} | "
                     f"{x['total_ms_p50']} | {x['audit_bytes_mean']} |")
    lines += ["", "## Dishonest forwarder (first chain member alters, then forwards)", "",
              "| N | alteration | altered package accepted by next recipient | rejection cause | classifications |",
              "|---|---|---|---|---|"]
    for x in r["results"]:
        if x["scenario"] == "authentic":
            continue
        lines.append(f"| {x['N']} | {x['scenario'].split('/')[1]} | {x['altered_package_accepted_by_next_recipient']}"
                     f"/{x['trials']} | {x['rejection_cause']} | {x['classifications']} |")
    lines += ["", "## Applied stage-1 limits by depth (exact policy)", "",
              "| checked copies | H | limits for depth 0..H | all levels meet targets |", "|---|---|---|---|"]
    for d in r["depth_rules"]:
        lines.append(f"| {d['n_checked']} | {d['H']} | {d['limits_by_depth']} | {d['all_meet_targets']} |")
    lines += ["", "## Notes", ""] + [f"- {n}" for n in r["notes"]] + [""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
