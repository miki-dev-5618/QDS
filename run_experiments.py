"""\
HEDWIG experiment runner with a ``--quick`` mode for CI smoke tests.

Default mode (no --quick):
    python run_experiments.py

Quick smoke-test mode (CI):
    python run_experiments.py --quick --trials 2 --bits 32
"""
import argparse
import sys

# Re‑use the real runner but with reduced parameters for quick CI runs.
from experiments.run_trials import main as run_main


def _parse_args():
    ap = argparse.ArgumentParser(description="HEDWIG experiment runner")
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Run a quick smoke test (overrides --trials and --bits for CI).",
    )
    # Pass through all other args to the real runner, but we override them
    # when --quick is used.
    # Remaining args are captured by the real main() via argparse,
    # so we just need --quick here.
    return ap.parse_args()


def main():
    args = _parse_args()

    # When --quick is set, override the expensive defaults for CI.
    if args.quick:
        # Re‑invoke the real main with reduced parameters.
        # We construct a new namespace and patch sys.argv so the real main()
        # picks up the quick values.
        namespace = argparse.Namespace(
            trials=2,
            bits=[32],
            seed=2026,
            backend="statevector",
            depolarizing=0.0,
            lockout_trials=10,
            lockout_runs=1,
            out="experiments",
        )
        # Replace sys.argv so the real main() parses the quick args.
        sys.argv = [
            "run_experiments.py",
            "--trials",
            "2",
            "--bits",
            "32",
            "--seed",
            "2026",
            "--backend",
            "statevector",
            "--depolarizing",
            "0.0",
            "--lockout-trials",
            "10",
            "--lockout-runs",
            "1",
        ]
        # Now call the real main – it will parse sys.argv and run quick.
        run_main()
    else:
        run_main()


if __name__ == "__main__":
    main()