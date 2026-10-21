"""
Sweep amplitude damping parameter gamma in [0, 0.15] across signature lengths
L = 16, 32, 64 with 200 trials per cell.

Measures:
- Honest accept rate (both verifiers accept and no threat reported)
- Effective honest mismatch rate (observed error on test tokens)
- Early abort rate

Outputs results to experiments/sweep_damping.csv and prints calibration table.
"""
import argparse
import csv
import os
import sys
import numpy as np

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quantum_engine import TeleportationQDS, make_amplitude_damping_channel


def run_damping_sweep(
    gammas=None,
    lengths=None,
    trials_per_cell=200,
    seed=2026,
    output_csv="experiments/sweep_damping.csv",
):
    if gammas is None:
        gammas = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.07, 0.10, 0.12, 0.15]
    if lengths is None:
        lengths = [16, 32, 64]

    rng = np.random.default_rng(seed)
    results = []

    print(f"Starting Amplitude Damping sweep: {len(gammas)} gammas x {len(lengths)} lengths, {trials_per_cell} trials/cell...")
    print(f"{'gamma':<8} | {'L':<4} | {'Accept Rate':<12} | {'Eff Mismatch Rate':<18} | {'Early Aborts':<12}")
    print("-" * 65)

    for gamma in gammas:
        for L in lengths:
            chan = make_amplitude_damping_channel(gamma=gamma)

            accepted_count = 0
            early_abort_count = 0
            mismatch_rates = []

            for i in range(trials_per_cell):
                # Fresh engine per trial to avoid circuit-breaker state leaking across trials
                engine = TeleportationQDS(backend="statevector", channel=chan)
                try:
                    res = engine.execute_protocol(
                        message_text=f"PAYLOAD_{gamma}_{L}_{i}",
                        n_bits=L,
                        rng=rng,
                    )
                except Exception:
                    # Quarantine or other enforcement error: count as rejected
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

            results.append({
                "gamma": gamma,
                "L": L,
                "trials": trials_per_cell,
                "accept_rate": round(accept_rate, 4),
                "effective_mismatch_rate": round(mean_mismatch, 4),
                "early_abort_rate": round(abort_rate, 4),
            })

            print(f"{gamma:<8.3f} | {L:<4} | {accept_rate:<12.3f} | {mean_mismatch:<18.4f} | {abort_rate:<12.3f}")

    # Write CSV
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["gamma", "L", "trials", "accept_rate", "effective_mismatch_rate", "early_abort_rate"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved CSV to: {output_csv}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sweep amplitude damping noise parameter gamma.")
    parser.add_argument("--trials", type=int, default=200, help="Number of trials per (gamma, L) cell")
    parser.add_argument("--seed", type=int, default=2026, help="Random seed")
    parser.add_argument("--out", type=str, default="experiments/sweep_damping.csv", help="Output CSV path")
    args = parser.parse_args()

    run_damping_sweep(trials_per_cell=args.trials, seed=args.seed, output_csv=args.out)
