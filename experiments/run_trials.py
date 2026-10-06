"""
Seeded repeated-trial experiments for HEDWIG V2.

For every (scenario, signature length) it runs independent trials, keeps the
injected scenario as ground truth, and reports what the blind detector and the
verifiers actually concluded. Rates carry 95% Wilson intervals.

    python experiments/run_trials.py                       # default grid
    python experiments/run_trials.py --trials 500 --bits 16 32 64 128 --seed 7
    python experiments/run_trials.py --backend qiskit --trials 50 --bits 32

Writes experiments/results.md and experiments/results.json.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import ChannelModel, TeleportationQDS, ThreatScenarioConfig, ThreatType  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402

EXPECTED = {  # the eavesdropping label covers Tier 1 alarms and Tier 2 channel attributions
    ThreatType.AUTHENTIC: {"BENIGN_AUTHENTIC", "CHANNEL_NOISE"},
    ThreatType.EVE_FORGERY: {"EXTERNAL_FORGERY"},
    ThreatType.DISHONEST_BOB: {"DISHONEST_VERIFIER_FORGERY"},
    ThreatType.EVE_INTERCEPT: {"EAVESDROPPING_TAMPERING"},
    ThreatType.MESSAGE_TAMPERING: {"MESSAGE_INTEGRITY_VIOLATION"},
    ThreatType.REPUDIATION: {"REPUDIATION_ATTEMPT"},
    ThreatType.REPLAY: {"REPLAY_ATTACK"},
    ThreatType.IMPERSONATION: {"IMPERSONATION_ATTACK"},
}


def fmt_rate(k, n):
    lo, hi = wilson_interval(k, n)
    return f"{k / n:.3f} [{lo:.3f}, {hi:.3f}]"


def run_cell(threat, n_bits, trials, rng, backend, channel):
    flagged = correct = abstain = elim_reject = bob_acc = charlie_acc = 0
    watch = quarantine = early = 0
    tokens_saved = []
    qber_err, det_us, classes = [], [], Counter()
    start = time.perf_counter()
    for _ in range(trials):
        eng = TeleportationQDS(backend=backend, channel=channel)
        if threat == ThreatType.REPLAY:
            # Replay needs a package that was genuinely accepted; honest runs are occasionally rejected.
            while eng.last_accepted_package is None:
                eng.guard.reset()  # a falsely rejected preamble may have moved the link to watch/quarantine
                eng.execute_protocol("genuine", n_bits, rng=rng)
            eng.guard.reset()
        r = eng.execute_protocol("experiment message", n_bits, rng=rng,
                                 scenario=ThreatScenarioConfig(threat_type=threat))
        report, t = r.threat_report, r.transcript
        classes[report.classification.value] += 1
        flagged += report.is_threat_detected
        correct += report.classification.value in EXPECTED[threat]
        abstain += report.classification.value == "UNDETERMINED_DISTURBANCE"
        elim_reject += any(v.record_found and not v.elimination_pass for v in t.results)
        bob_acc += bool(t.display.get("bob") and t.display["bob"].accepted)
        charlie_acc += bool(t.display.get("charlie") and t.display["charlie"].accepted)
        watch += r.response.response_action == "watch"
        quarantine += r.response.response_action == "quarantine"
        ct = t.channel_test
        if ct is not None and ct.early_abort:
            early += 1
            tokens_saved.append(1 - ct.tokens_sent / ct.tokens_planned)
        if ct is not None and t.channel_model is not None:
            qber_err.append(abs(ct.qber_estimate - t.channel_model.expected_qber()))
        det_us.append(r.latency["detection_us"])
    elapsed = time.perf_counter() - start
    return {
        "scenario": threat.value,
        "n_bits": n_bits,
        "trials": trials,
        "flagged_as_threat": fmt_rate(flagged, trials),
        "correct_class": fmt_rate(correct, trials),
        "abstained_undetermined": fmt_rate(abstain, trials),
        "elimination_rejects": fmt_rate(elim_reject, trials),
        "bob_accepts": fmt_rate(bob_acc, trials),
        "charlie_accepts": fmt_rate(charlie_acc, trials),
        "response_watch": fmt_rate(watch, trials),
        "response_quarantine": fmt_rate(quarantine, trials),
        "early_abort": fmt_rate(early, trials),
        "mean_tokens_saved_when_aborted": round(float(np.mean(tokens_saved)), 3) if tokens_saved else None,
        "classes": dict(classes.most_common()),
        "mean_abs_qber_error": round(float(np.mean(qber_err)), 4) if qber_err else None,
        "detection_us_p50": round(float(np.median(det_us)), 1),
        "throughput_tx_per_s": round(trials / elapsed, 1),
    }


def lockout_sequence(n_bits, trials, runs, rng, backend, channel):
    """Honest-only sequences on one engine: how often does the link ever get quarantined?"""
    locked = 0
    for _ in range(trials):
        eng = TeleportationQDS(backend=backend, channel=channel)
        for _ in range(runs):
            r = eng.execute_protocol("honest", n_bits, rng=rng)
            if r.enforcement["link_state"] == "quarantined":
                locked += 1
                break
    return {"n_bits": n_bits, "trials": trials, "runs_per_trial": runs,
            "sequences_ever_quarantined": fmt_rate(locked, trials)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--bits", type=int, nargs="+", default=[16, 32, 64])
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--backend", default="statevector", choices=["statevector", "qiskit"])
    ap.add_argument("--depolarizing", type=float, default=ChannelModel().depolarizing)
    ap.add_argument("--lockout-trials", type=int, default=100)
    ap.add_argument("--lockout-runs", type=int, default=10)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    channel = ChannelModel(depolarizing=args.depolarizing)
    rows = []
    for n_bits in args.bits:
        for threat in ThreatType:
            rows.append(run_cell(threat, n_bits, args.trials, rng, args.backend, channel))
            print(f"L={n_bits:<4} {threat.value:18s} flagged {rows[-1]['flagged_as_threat']}  "
                  f"correct {rows[-1]['correct_class']}  quarantine {rows[-1]['response_quarantine']}", flush=True)
    lockouts = []
    for n_bits in args.bits:
        lockouts.append(lockout_sequence(n_bits, args.lockout_trials, args.lockout_runs, rng, args.backend, channel))
        print(f"L={n_bits:<4} honest x{args.lockout_runs}: ever quarantined "
              f"{lockouts[-1]['sequences_ever_quarantined']}", flush=True)

    meta = {"trials": args.trials, "bits": args.bits, "seed": args.seed, "backend": args.backend,
            "depolarizing": args.depolarizing, "expected_honest_qber": round(channel.expected_qber(), 4),
            "lockout_trials": args.lockout_trials, "lockout_runs": args.lockout_runs,
            "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rows": rows, "lockout": lockouts}, f, indent=2)

    lines = [
        "# HEDWIG V2.2 experiment results", "",
        f"Seed {args.seed}, {args.trials} trials per cell, backend `{args.backend}`, honest depolarising "
        f"p={args.depolarizing} (expected QBER {channel.expected_qber():.4f}). Generated {meta['generated']}.", "",
        "Rates are fractions with 95% Wilson intervals. *Injected* is the scenario the attack generator ran; "
        "*flagged* and *correct class* are what the blind detector concluded from observations. "
        "*Abstained* counts `UNDETERMINED_DISTURBANCE` (rejected, cause not attributable at this size). "
        "*Elimination rejects* counts runs where at least one verifier's quantum elimination check failed on its own "
        "(separate from the classical binding/replay checks). *Watch/quarantine* is the response policy's action "
        "for future traffic; the transmission itself is rejected whenever it is flagged.", "",
        "## Detection, attribution and response", "",
        "| L | injected | flagged as threat | correct class | abstained | elimination rejects | Bob accepts "
        "| Charlie accepts | watch | quarantine | early abort (tokens saved) | detect µs p50 | classes seen |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        classes = ", ".join(f"{k}: {v}" for k, v in r["classes"].items())
        saved = f" ({r['mean_tokens_saved_when_aborted']:.0%})" if r["mean_tokens_saved_when_aborted"] else ""
        lines.append(f"| {r['n_bits']} | {r['scenario']} | {r['flagged_as_threat']} | {r['correct_class']} | "
                     f"{r['abstained_undetermined']} | {r['elimination_rejects']} | {r['bob_accepts']} | "
                     f"{r['charlie_accepts']} | {r['response_watch']} | {r['response_quarantine']} | "
                     f"{r['early_abort']}{saved} | {r['detection_us_p50']} | {classes} |")
    lines += ["", "For `authentic`, *flagged as threat* is the false-rejection rate and *quarantine* the immediate "
              "false lock-out rate. For attacks, 1 − flagged is the miss rate.", "",
              "## False lock-out over honest sequences", "",
              f"Each trial sends {args.lockout_runs} honest transmissions in a row on one engine (so WATCH "
              f"escalation can occur). Reported: fraction of sequences in which the link was ever quarantined.", "",
              "| L | trials | runs per trial | ever quarantined |", "|---|---|---|---|"]
    for lo in lockouts:
        lines.append(f"| {lo['n_bits']} | {lo['trials']} | {lo['runs_per_trial']} | {lo['sequences_ever_quarantined']} |")
    lines += ["", "Zero observed events in N trials bounds the rate only to about 3/N (95%); these tables are "
              "empirical rates, not the 10⁻⁶ guarantees of the original innovation claims."]
    with open(os.path.join(args.out, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {os.path.join(args.out, 'results.md')}")


if __name__ == "__main__":
    main()
