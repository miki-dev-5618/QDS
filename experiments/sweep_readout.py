"""
Sweep asymmetric readout (measurement) noise parameter p in {0.0, 0.01, 0.03, 0.05}
across locations (verifier_measurement, bell_measurement, both) and signature lengths
L = 16, 32, 64 with 200 trials per cell.

Measures:
- Honest accept rate (both verifiers accept and no threat reported)
- Effective honest mismatch rate (observed error on test tokens)
- Early abort rate

Outputs results to experiments/sweep_readout.csv and prints calibration table.
"""
import argparse
import csv
import os
import sys
import numpy as np

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quantum_engine import TeleportationQDS, make_readout_channel


def run_readout_sweep(
    p_values=None,
    locations=None,
    lengths=None,
    trials_per_cell=200,
    seed=2026,
    output_csv="experiments/sweep_readout.csv",
):
    if p_values is None:
        p_values = [0.0, 0.01, 0.03, 0.05]
    if locations is None:
        locations = ["verifier_measurement", "bell_measurement", "both"]
    if lengths is None:
        lengths = [16, 32, 64]

    rng = np.random.default_rng(seed)
    results = []

    total_cells = len(locations) * len(p_values) * len(lengths)
    print(f"Starting Readout Error sweep: {len(locations)} locations x {len(p_values)} p-values x {len(lengths)} lengths ({total_cells} cells), {trials_per_cell} trials/cell...")
    print(f"{'Location':<22} | {'p (p01/p10)':<14} | {'L':<4} | {'Accept Rate':<12} | {'Eff Mismatch':<14} | {'Early Aborts':<12}")
    print("-" * 88)

    for loc in locations:
        for p in p_values:
            p01 = float(p)
            p10 = float(min(1.0, 3.0 * p))  # asymmetric 1:3 ratio (e.g. 0.01 / 0.03)
            for L in lengths:
                chan = make_readout_channel(p01=p01, p10=p10, location=loc)

                accepted_count = 0
                early_abort_count = 0
                mismatch_rates = []

                for i in range(trials_per_cell):
                    # Fresh engine per trial to avoid circuit breaker state leaking across trials
                    engine = TeleportationQDS(backend="statevector", channel=chan)
                    try:
                        res = engine.execute_protocol(
                            message_text=f"READOUT_{loc}_{p}_{L}_{i}",
                            n_bits=L,
                            rng=rng,
                        )
                    except Exception:
                        continue

                    t = res.transcript
                    bob_ok = bool(t.display.get("bob") and t.display["bob"].accepted)
                    charlie_ok = bool(t.display.get("charlie") and t.display["charlie"].accepted)
                    no_threat = not res.threat_report.is_threat_detected

                    if bob_ok and charlie_ok and no_threat:
                        accepted_count += 1

                    if t.channel_test and t.channel_test.early_abort:
                        early_abort_count += 1

                    if t.channel_test:
                        mismatch_rates.append(t.channel_test.qber_estimate)

                accept_rate = accepted_count / trials_per_cell
                abort_rate = early_abort_count / trials_per_cell
                mean_mismatch = float(np.mean(mismatch_rates)) if mismatch_rates else 0.0

                p_str = f"{p01:.2f}/{p10:.2f}"
                results.append({
                    "location": loc,
                    "p": p,
                    "p01": p01,
                    "p10": p10,
                    "L": L,
                    "trials": trials_per_cell,
                    "accept_rate": round(accept_rate, 4),
                    "effective_mismatch_rate": round(mean_mismatch, 4),
                    "early_abort_rate": round(abort_rate, 4),
                })

                print(f"{loc:<22} | {p_str:<14} | {L:<4} | {accept_rate:<12.3f} | {mean_mismatch:<14.4f} | {abort_rate:<12.3f}")

    # Write CSV
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "location",
                "p",
                "p01",
                "p10",
                "L",
                "trials",
                "accept_rate",
                "effective_mismatch_rate",
                "early_abort_rate",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved CSV to: {output_csv}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sweep readout (measurement) noise parameter across locations.")
    parser.add_argument("--trials", type=int, default=200, help="Number of trials per (location, p, L) cell")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed")
    parser.add_argument("--out", type=str, default="experiments/sweep_readout.csv", help="Output CSV path")
    args = parser.parse_args()

    run_readout_sweep(trials_per_cell=args.trials, seed=args.seed, output_csv=args.out)
