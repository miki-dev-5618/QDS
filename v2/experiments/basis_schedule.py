"""
Exploratory experiment (roadmap step 7): does a message-derived basis schedule add security?

Three verifier basis schedules at EQUAL qubit budgets (same L, same test tokens):
  random       - private RNG (baseline)
  public_hash  - basis = H(context, verifier, position, copy); anyone can compute it
  keyed_hmac   - basis = HMAC(verifier secret, context, ...); Eve cannot compute it

Adversary (schedule-aware Eve). She taps a fraction f of the stream. For a
tapped signature copy she measures in the verifier's basis when she can
compute it (public schedule), otherwise in a random basis. Test tokens are
indistinguishable from signature copies, so she measures them in a basis
uncorrelated with their preparation. Measuring the Bell half in the
verifier's basis B is invisible to the verifier's measurement in B (it only
dephases in B), and from her outcome e and the public correction bits she
infers the verifier's outcome exactly: e XOR (m2 if B = Z else m1). She
therefore learns the verifier's eliminated state, and forges a signature
that avoids every eliminated state she learned (uniform guess elsewhere).

Reported separately, as the roadmap requires:
  (a) classical binding rejection of the forgery (the commitment check);
  (b) quantum contradictions of the forgery, i.e. whether the QUANTUM layer
      alone would have caught it;
  (c) Tier 1 channel alarms (what the tapping costs Eve on test tokens).

Modelling assumptions: Eve knows each signature copy's (verifier, position,
copy) stream slot; she reads the classical correction bits; noise on the
channel acts after her measurement. The keyed schedule is expected to match
the random baseline; if it shows no measurable gain it should stay off by
default.

    python experiments/basis_schedule.py --trials 200 --bits 32
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from src.quantum_engine import ChannelModel, TeleportationQDS  # noqa: E402
from src.quantum_engine.channel import wilson_interval  # noqa: E402
from src.quantum_engine.elimination import OrthogonalEliminationEngine, REV_SYMBOL_MAP  # noqa: E402
from src.quantum_engine.schedule import SCHEDULES  # noqa: E402

ALL_STATES = ['|0⟩', '|1⟩', '|+⟩', '|−⟩']


class ScheduleAwareEve:
    def __init__(self, tap_fraction: float, depolarizing: float):
        self.f = tap_fraction
        self.dep = depolarizing
        self.events = []
        self.learned = {}
        self.public = False

    def tap(self, stream, schedule_public, rng):
        self.public = schedule_public
        self.events = []
        for s in stream:
            noise = str(rng.choice(["X", "Y", "Z"])) if rng.random() < self.dep else None
            if rng.random() < self.f:
                basis = s.meas_basis if (schedule_public and s.kind == "sig") else int(rng.integers(0, 2))
                self.events.append((basis, noise))
            else:
                self.events.append((None, noise))
        return self.events

    def observe(self, sent, outcomes):
        self.learned = {}
        if not self.public:
            return  # without the schedule she cannot tell whether her basis matched the verifier's
        for s, (eb, _), out in zip(sent, self.events, outcomes):
            if s.kind == "sig" and eb is not None:
                inferred = out.eve_outcome ^ (out.m2 if eb == 0 else out.m1)
                elim = OrthogonalEliminationEngine.eliminate_state_symbol(eb, inferred)
                self.learned.setdefault(s.pos, set()).add(elim)

    def forge(self, n_bits, rng):
        sig = []
        for i in range(n_bits):
            candidates = [x for x in ALL_STATES if x not in self.learned.get(i, set())] or ALL_STATES
            sig.append(REV_SYMBOL_MAP[str(rng.choice(candidates))])
        return sig


def rate(k, n):
    lo, hi = wilson_interval(k, n)
    return f"{k / n:.3f} [{lo:.3f}, {hi:.3f}]" if n else "—"


def run(schedule_name, f, n_bits, trials, rng, dep):
    alarms = forged = binding_rej = quantum_rej = 0
    contradiction_rates = []
    for _ in range(trials):
        eng = TeleportationQDS(backend="statevector", channel=ChannelModel(depolarizing=dep),
                               schedule=SCHEDULES[schedule_name]())
        eve = ScheduleAwareEve(f, dep)
        session = eng.distribute("alice", "schedule experiment", n_bits, rng, adversary=eve)
        if session.aborted:
            alarms += 1
            continue  # Alice never reveals; nothing to forge against
        forged += 1
        pkg = eng.reveal(session).copy(message="forged by Eve", revealed_signature=eve.forge(n_bits, rng))
        results = eng.deliver(pkg)
        binding_rej += any(not r.binding_pass for r in results)
        quantum_rej += any(not r.elimination_pass for r in results)
        checked = sum(r.n_checked for r in results)
        contradiction_rates.append(sum(r.mismatches for r in results) / checked if checked else 0.0)
    return {
        "schedule": schedule_name, "tap_fraction": f, "L": n_bits, "trials": trials,
        "tier1_alarm": rate(alarms, trials),
        "forgeries_attempted": forged,
        "binding_rejects_forgery": rate(binding_rej, forged),
        "quantum_layer_rejects_forgery": rate(quantum_rej, forged),
        "quantum_layer_would_accept": rate(forged - quantum_rej, forged),
        "mean_contradiction_rate": round(float(np.mean(contradiction_rates)), 4) if contradiction_rates else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--bits", type=int, nargs="+", default=[32])
    ap.add_argument("--taps", type=float, nargs="+", default=[0.0, 0.25, 0.5, 1.0])
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--depolarizing", type=float, default=0.01)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    rows = []
    for n_bits in args.bits:
        for name in SCHEDULES:
            for f in args.taps:
                rows.append(run(name, f, n_bits, args.trials, rng, args.depolarizing))
                r = rows[-1]
                print(f"L={n_bits} {name:12s} tap={f:.2f}  alarm {r['tier1_alarm']}  quantum-only accept "
                      f"{r['quantum_layer_would_accept']}  contradictions {r['mean_contradiction_rate']}", flush=True)

    meta = {"trials": args.trials, "bits": args.bits, "taps": args.taps, "seed": args.seed,
            "depolarizing": args.depolarizing, "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(args.out, "basis_schedule.json"), "w", encoding="utf-8") as fjson:
        json.dump({"meta": meta, "rows": rows}, fjson, indent=2)
    lines = [
        "# Basis-schedule experiment (exploratory)", "",
        f"Seed {args.seed}, {args.trials} trials per cell, depolarising p={args.depolarizing}, equal qubit budgets. "
        f"Generated {meta['generated']}. See the module docstring of `experiments/basis_schedule.py` for the "
        f"adversary model.", "",
        "| L | schedule | Eve tap fraction | Tier 1 alarm | binding rejects forgery | quantum layer rejects "
        "| quantum layer alone would accept | mean contradiction rate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['L']} | {r['schedule']} | {r['tap_fraction']} | {r['tier1_alarm']} | "
                     f"{r['binding_rejects_forgery']} | {r['quantum_layer_rejects_forgery']} | "
                     f"{r['quantum_layer_would_accept']} | {r['mean_contradiction_rate']} |")
    lines += ["", "Rates for the forgery columns are over runs that were not aborted by Tier 1."]
    with open(os.path.join(args.out, "basis_schedule.md"), "w", encoding="utf-8") as fmd:
        fmd.write("\n".join(lines) + "\n")
    print(f"\nWrote {os.path.join(args.out, 'basis_schedule.md')}")


if __name__ == "__main__":
    main()
