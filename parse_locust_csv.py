
"""Parse a Locust 2.x ``*_stats.csv`` aggregate report."""

import csv
import os
import sys


def parse_locust_csv(csv_path):
    """Read Locust request statistics from a CSV file."""
    if not os.path.isfile(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        return None

    stats = {}

    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            if not reader.fieldnames:
                print("ERROR: CSV is empty or has no header.", file=sys.stderr)
                return None

            headers = {
                header.strip().lower().replace(" ", "_")
                for header in reader.fieldnames
            }
            required = {"name", "request_count", "failure_count", "average_response_time"}
            missing = required - headers

            if missing:
                print(
                    f"ERROR: Missing columns {missing}. "
                    f"Found: {reader.fieldnames}",
                    file=sys.stderr,
                )
                return None

            for row in reader:
                try:
                    normalized = {
                        (key or "").strip().lower().replace(" ", "_"): (value or "").strip()
                        for key, value in row.items()
                    }
                    name = normalized.get("name", "")
                    if not name:
                        continue

                    stats[name] = {
                        "p50": float(normalized.get("50%", "0")),
                        "p95": float(normalized.get("95%", "0")),
                        "p99": float(normalized.get("99%", "0")),
                        "avg": float(normalized["average_response_time"]),
                        "total": int(normalized["request_count"]),
                        "failures": int(normalized["failure_count"]),
                    }

                except (ValueError, TypeError):
                    continue

    except OSError as exc:
        print(f"ERROR: Could not read CSV: {exc}", file=sys.stderr)
        return None

    result = {}

    return stats


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python parse_locust_csv.py <path-to-locust-csv>",
            file=sys.stderr,
        )
        sys.exit(1)

    csv_path = sys.argv[1]
    data = parse_locust_csv(csv_path)

    if data is None:
        sys.exit(1)

    print(f"\nLocust CSV analysis: {csv_path}\n")
    print(
        f"{'Scenario':40s} {'p50(ms)':>9} {'p95(ms)':>9} "
        f"{'p99(ms)':>9} {'avg(ms)':>9} {'requests':>9} {'failures':>9}"
    )
    print("-" * 100)

    expected = [
        "api_login",
        "api_topology",
        "api_sign_and_send_authentic",
    ]

    for key in expected:
        if key not in data:
            print(f"{key:40s} {'not found in CSV':>30s}")
            continue

        d = data[key]
        print(
            f"{key:40s} {d['p50']:9.1f} {d['p95']:9.1f} "
            f"{d['p99']:9.1f} {d['avg']:9.1f} "
            f"{d['total']:9d} {d['failures']:9d}"
        )

    print("\nNote: Percentiles and averages are read from Locust's aggregate *_stats.csv report.")
    print("Throughput should be taken from Locust's console summary for the full run interval.")


if __name__ == "__main__":
    main()
