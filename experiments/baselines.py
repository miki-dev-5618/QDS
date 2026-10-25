"""
Baseline comparison: HEDWIG vs the simpler alternatives a judge might suggest.

Systems (same seeded trials: trial i uses the same seed under every system):

  qber_cutoff   fixed QKD-style abort rule: abort iff test-token QBER > 11% (no
                binomial Tier 1, no sequential early abort, no Tier 2, no
                circuit breaker); otherwise the verifiers' own elimination and
                commitment checks decide. Attribution: cutoff -> channel;
                commitment fail -> forgery; elimination fail -> signature.
  hedwig_no_cb  full HEDWIG detector (Tier 1 + Tier 2), circuit breaker disabled
                (reject only, links never WATCH or QUARANTINE).
  hedwig        full HEDWIG.

Per-transmission metrics (fresh engine per trial; hedwig_no_cb and hedwig are
identical here because the breaker only affects *later* traffic):
  attack caught (per scenario), honest false alarm, correct attribution,
  tokens sent per attacked transmission ("tokens wasted").

Sequence metrics (one engine, `--seq-length` transmissions, simulated clock):
  honest blocked after one forged package (DoS): the signer sends honest
      traffic; transmission `--attack-at` is replaced by an eve_forgery package.
      Share of the signer's later transmissions that are refused or rejected.
  accepted while tapped: every transmission is intercept-resent at f=0.2;
      share of the signer's transmissions accepted anyway (exposure).

All rates carry 95% Wilson intervals; token means carry normal-approximation CIs.

    python experiments/baselines.py                         # L = 16 32 64, 200 trials, 50 sequences
    python experiments/baselines.py --trials 500 --bits 16 32

Writes experiments/baselines.csv and baselines.md.
"""
import argparse
import csv
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import (ChannelGuard, ChannelModel, ChannelQuarantined, TeleportationQDS,  # noqa: E402
                                ThreatScenarioConfig, ThreatType)
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.security import SecurityParameters  # noqa: E402

SYSTEMS = ("qber_cutoff", "hedwig_no_cb", "hedwig")
SYSTEM_LABELS = {"qber_cutoff": "(a) fixed 11% QBER cutoff", "hedwig_no_cb": "(b) HEDWIG, no circuit breaker",
                 "hedwig": "(c) full HEDWIG"}
QBER_CUTOFF = 0.11
WEAK_RATE = 0.2
# name, threat, intercept rate, ground-truth cause
SCENARIOS = (
    ("honest", ThreatType.AUTHENTIC, None, "accepted"),
    ("eve_forgery", ThreatType.EVE_FORGERY, None, "forgery"),
    ("eve_intercept", ThreatType.EVE_INTERCEPT, 1.0, "channel"),
    ("weak_intercept_f0.2", ThreatType.EVE_INTERCEPT, WEAK_RATE, "channel"),
    ("repudiation", ThreatType.REPUDIATION, None, "signature"),
)
HEDWIG_LABEL = {"BENIGN_AUTHENTIC": "accepted", "CHANNEL_NOISE": "accepted", "EAVESDROPPING_TAMPERING": "channel",
                "REPUDIATION_ATTEMPT": "signature", "EXTERNAL_FORGERY": "forgery",
                "DISHONEST_VERIFIER_FORGERY": "forgery", "UNDETERMINED_DISTURBANCE": "undetermined"}
FIELDS = ("L", "metric", "scenario", "system", "direction", "k", "n", "value", "lo", "hi")


class SimClock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class NoBreakerGuard(ChannelGuard):
    """Circuit breaker disabled: decisions are recorded nowhere, links stay OPEN."""

    def apply(self, *args, **kwargs):
        return None


def make_engine(system, depolarizing, clock=None):
    clock = clock or SimClock()
    if system == "qber_cutoff":
        # No Tier 1 alarm and no early abort: the whole stream is sent and the 11% rule is applied afterwards.
        # Fixed allocation (max(16, L) test tokens, no reserve); the C2 fields exist only once C2 is merged.
        c2 = {"allocation_policy": "legacy", "reserve_policy": "off"}
        params = SecurityParameters(false_alarm_alpha=0.0, strong_alpha=0.0, abort_chunks=1,
                                    **{k: v for k, v in c2.items() if k in SecurityParameters.__dataclass_fields__})
    else:
        params = SecurityParameters()
    eng = TeleportationQDS(params=params, backend="statevector", channel=ChannelModel(depolarizing=depolarizing),
                           clock=clock)
    if system != "hedwig":
        eng.guard = NoBreakerGuard(eng.policy, eng.store, eng.router, clock)
    return eng


def cutoff_outcome(transcript):
    """(accepted, label) under the fixed-QBER-cutoff baseline."""
    ct = transcript.channel_test
    if ct is not None and ct.test_count and ct.error_count / ct.test_count > QBER_CUTOFF:
        return False, "channel"
    direct = [r for r in transcript.results if r.mode == "direct"]
    if direct and all(r.accepted for r in direct):
        return True, "accepted"
    if any(not r.binding_pass for r in direct):
        return False, "forgery"
    if any(not r.elimination_pass for r in direct):
        return False, "signature"
    return False, "other"


def transmit(eng, system, n_bits, rng, threat, rate):
    """One transmission. Returns (accepted, label, tokens_sent), or None if the link refused it."""
    cfg = ThreatScenarioConfig(threat_type=threat)
    if rate is not None:
        cfg.channel_intercept_rate = rate
    try:
        r = eng.execute_protocol("baseline comparison", n_bits, rng=rng, scenario=cfg)
    except ChannelQuarantined:
        return None
    t = r.transcript
    tokens = t.session.tokens_sent if t.session else 0
    if system == "qber_cutoff":
        accepted, label = cutoff_outcome(t)
    else:
        label = HEDWIG_LABEL.get(r.threat_report.classification.value, "other")
        accepted = not r.threat_report.is_threat_detected
    return accepted, label, tokens


def per_transmission(system, n_bits, scen_idx, trials, seed, depolarizing):
    _, threat, rate, _ = SCENARIOS[scen_idx]
    out = []
    for i in range(trials):
        rng = np.random.default_rng([seed, n_bits, scen_idx, i])
        out.append(transmit(make_engine(system, depolarizing), system, n_bits, rng, threat, rate))
    return out


def sequence(system, n_bits, kind, run, length, attack_at, seed, depolarizing, interarrival):
    """
    kind = "forgery_injection": honest traffic, transmission `attack_at` is a forged package.
    kind = "tapped": every transmission intercept-resent at WEAK_RATE.
    Returns a list of (is_signer_tx, outcome) where outcome is None if refused.
    """
    rng = np.random.default_rng([seed, n_bits, 100 + (kind == "tapped"), run])
    clock = SimClock()
    eng = make_engine(system, depolarizing, clock)
    out = []
    for i in range(1, length + 1):
        clock.t += interarrival
        if kind == "tapped":
            out.append((True, transmit(eng, system, n_bits, rng, ThreatType.EVE_INTERCEPT, WEAK_RATE)))
        elif i == attack_at:
            out.append((False, transmit(eng, system, n_bits, rng, ThreatType.EVE_FORGERY, None)))
        else:
            out.append((True, transmit(eng, system, n_bits, rng, ThreatType.AUTHENTIC, None)))
    return out


def _rate_row(L, metric, scenario, system, direction, k, n):
    lo, hi = wilson_interval(k, n)
    return {"L": L, "metric": metric, "scenario": scenario, "system": system, "direction": direction,
            "k": k, "n": n, "value": round(k / n, 4) if n else None, "lo": round(lo, 4), "hi": round(hi, 4)}


def _mean_row(L, metric, scenario, system, values):
    m = float(np.mean(values))
    half = 1.96 * float(np.std(values, ddof=1)) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"L": L, "metric": metric, "scenario": scenario, "system": system, "direction": "lower",
            "k": None, "n": len(values), "value": round(m, 2), "lo": round(m - half, 2), "hi": round(m + half, 2)}


def run_baselines(bits, trials, seq_runs, seq_length, attack_at, seed, depolarizing=0.01, interarrival=60.0):
    rows = []
    for L in bits:
        # ---- per-transmission (hedwig_no_cb == hedwig here: fresh engine per trial)
        per = {}
        for s_idx in range(len(SCENARIOS)):
            per[("qber_cutoff", s_idx)] = per_transmission("qber_cutoff", L, s_idx, trials, seed, depolarizing)
            per[("hedwig", s_idx)] = per_transmission("hedwig", L, s_idx, trials, seed, depolarizing)
            per[("hedwig_no_cb", s_idx)] = per[("hedwig", s_idx)]
        for system in SYSTEMS:
            attr_k = attr_n = 0
            for s_idx, (name, _, _, truth) in enumerate(SCENARIOS):
                res = per[(system, s_idx)]
                if name == "honest":
                    rows.append(_rate_row(L, "honest false alarm", name, system, "lower",
                                          sum(not a for a, _, _ in res), len(res)))
                    continue
                rows.append(_rate_row(L, "attack caught", name, system, "higher",
                                      sum(not a for a, _, _ in res), len(res)))
                correct = sum(lab == truth for _, lab, _ in res)
                rows.append(_rate_row(L, "correct attribution", name, system, "higher", correct, len(res)))
                attr_k, attr_n = attr_k + correct, attr_n + len(res)
                if name in ("eve_intercept", "weak_intercept_f0.2"):
                    rows.append(_mean_row(L, "tokens sent per attacked tx", name, system, [t for *_, t in res]))
            rows.append(_rate_row(L, "correct attribution", "all attacks", system, "higher", attr_k, attr_n))

        # ---- sequences (the circuit breaker matters here)
        for system in SYSTEMS:
            blocked = n_after = 0
            accepted_tapped = n_tapped = 0
            for run in range(seq_runs):
                for i, (signer, o) in enumerate(sequence(system, L, "forgery_injection", run, seq_length,
                                                         attack_at, seed, depolarizing, interarrival), start=1):
                    if signer and i > attack_at:
                        n_after += 1
                        blocked += o is None or not o[0]
                for _, o in sequence(system, L, "tapped", run, seq_length, attack_at, seed, depolarizing,
                                     interarrival):
                    n_tapped += 1
                    accepted_tapped += o is not None and o[0]
            rows.append(_rate_row(L, "honest blocked after one forged package (DoS)", "forgery_injection", system,
                                  "lower", blocked, n_after))
            rows.append(_rate_row(L, "signer tx accepted while tapped (exposure)", f"tapped_f{WEAK_RATE:g}", system,
                                  "lower", accepted_tapped, n_tapped))
        for r in rows:
            if r["L"] == L:
                print(f"L={L:<3} {r['metric']:45s} {r['scenario']:22s} {r['system']:13s} "
                      f"{r['value']} [{r['lo']}, {r['hi']}]", flush=True)
    return rows


def winners(group):
    """Systems tied with the best value: their CI overlaps the best system's CI."""
    best = (max if group[0]["direction"] == "higher" else min)(group, key=lambda r: r["value"])
    return [r["system"] for r in group if r["lo"] <= best["hi"] and r["hi"] >= best["lo"]]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _cell(r):
    if r["k"] is None:
        return f"{r['value']} [{r['lo']}, {r['hi']}]"
    return f"{r['value']:.3f} [{r['lo']:.3f}, {r['hi']:.3f}]"


def write_markdown(rows, path, meta):
    lines = [
        "# Baselines: HEDWIG vs simpler alternatives", "",
        f"Seed {meta['seed']}, statevector backend, depolarizing p={meta['depolarizing']}. "
        f"{meta['trials']} trials per per-transmission cell; {meta['seq_runs']} sequences of {meta['seq_length']} "
        f"transmissions ({meta['interarrival']:g} s apart) per sequence cell. Generated {meta['generated']}.", "",
        "Systems: " + "; ".join(SYSTEM_LABELS[s] for s in SYSTEMS) + ". "
        "Per-transmission rows are identical for (b) and (c): the breaker only changes later traffic.", "",
        "*Best* lists every system whose 95% CI overlaps the best system's CI (a tie is reported as a tie).", "",
    ]
    for L in sorted({r["L"] for r in rows}):
        lines += [f"## L = {L}", "",
                  "| metric | scenario | better | " + " | ".join(SYSTEM_LABELS[s] for s in SYSTEMS) + " | best |",
                  "|---|---|---|" + "---|" * len(SYSTEMS) + "---|"]
        keys = []
        for r in rows:
            if r["L"] == L and (r["metric"], r["scenario"]) not in keys:
                keys.append((r["metric"], r["scenario"]))
        for metric, scen in keys:
            group = [next(r for r in rows if r["L"] == L and r["metric"] == metric and r["scenario"] == scen
                          and r["system"] == s) for s in SYSTEMS]
            best = winners(group)
            best_txt = "all tied" if len(best) == len(SYSTEMS) else ", ".join(SYSTEM_LABELS[s][:3] for s in best)
            lines.append(f"| {metric} | {scen} | {group[0]['direction']} | "
                         + " | ".join(_cell(r) for r in group) + f" | {best_txt} |")
        lines.append("")
    lines += ["Where a baseline wins, the table says so: the circuit breaker trades availability "
              "(honest traffic blocked after an attack) for exposure (traffic accepted on a tapped link). "
              "No admin reset is modelled inside a sequence, so a quarantine blocks the rest of it."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, nargs="+", default=[16, 32, 64])
    ap.add_argument("--trials", type=int, default=200, help="trials per per-transmission cell")
    ap.add_argument("--seq-runs", type=int, default=50)
    ap.add_argument("--seq-length", type=int, default=40)
    ap.add_argument("--attack-at", type=int, default=5, help="position of the forged package in DoS sequences")
    ap.add_argument("--interarrival", type=float, default=60.0)
    ap.add_argument("--depolarizing", type=float, default=0.01)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args(argv)

    rows = run_baselines(args.bits, args.trials, args.seq_runs, args.seq_length, args.attack_at, args.seed,
                         args.depolarizing, args.interarrival)
    meta = {"seed": args.seed, "depolarizing": args.depolarizing, "trials": args.trials, "seq_runs": args.seq_runs,
            "seq_length": args.seq_length, "interarrival": args.interarrival,
            "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, "baselines")
    write_csv(rows, base + ".csv")
    write_markdown(rows, base + ".md", meta)
    print(f"\nWrote {base}.csv and {base}.md")
    return rows


if __name__ == "__main__":
    main()
