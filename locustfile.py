
"""
Locust load-test script for HEDWIG V2.2 QDS.

Tests the authentic sign-and-send scenario only to avoid triggering
the Quantum Circuit Breaker with adversarial threat types.

Run:
locust -f locustfile.py --headless -u 10 -r 2 --run-time 30s --host http://localhost:8000
"""

import os
import time
from locust import HttpUser, task, between, events

# Print the file name and full path.
FILE_NAME = os.path.basename(__file__)
FILE_PATH = os.path.abspath(__file__)

# Collect response times for the authentic scenario.
scenario_times = []
scenario_requests = 0
scenario_successes = 0
scenario_failures = 0
test_start_time = None


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize metrics and print file details."""
    global scenario_requests, scenario_successes, scenario_failures, test_start_time

    scenario_times.clear()
    scenario_requests = 0
    scenario_successes = 0
    scenario_failures = 0
    test_start_time = time.perf_counter()

    print("\nStarting HEDWIG authentic sign-and-send load test...")
    print(f"File name: {FILE_NAME}")
    print(f"Full file path: {FILE_PATH}")


@events.request.add_listener
def on_request(
    request_type,
    name,
    response_time,
    response_length,
    exception,
    **kwargs,
):
    """Collect response times for the selected scenario."""
    global scenario_requests, scenario_successes, scenario_failures

    if name == "api_sign_and_send_authentic":
        scenario_requests += 1
        if exception is None:
            scenario_successes += 1
            scenario_times.append(response_time)
        else:
            scenario_failures += 1


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print latency percentiles and overall request throughput."""
    print("\n=== HEDWIG Load Test Summary ===")

    times = sorted(scenario_times)

    if times:
        n = len(times)

        def percentile(values, p):
            # Nearest-rank percentile.
            index = max(0, int(p * len(values) + 0.999999) - 1)
            return values[min(index, len(values) - 1)]

        print(f"Successful responses: {n}")
        print(f"p50 latency: {percentile(times, 0.50):.2f} ms")
        print(f"p95 latency: {percentile(times, 0.95):.2f} ms")
        print(f"p99 latency: {percentile(times, 0.99):.2f} ms")
        print(f"Average latency: {sum(times) / n:.2f} ms")
    else:
        print("No successful matching requests were recorded; latency percentiles are unavailable.")

    elapsed = (
        time.perf_counter() - test_start_time
        if test_start_time is not None
        else 0
    )

    if elapsed > 0:
        print(f"Scenario requests: {scenario_requests}")
        print(f"Scenario failures: {scenario_failures}")
        print(f"Scenario throughput: {scenario_requests / elapsed:.2f} requests/sec")
        print(f"Successful scenario throughput: {scenario_successes / elapsed:.2f} requests/sec")

    print("================================\n")


class HedwigUser(HttpUser):
    """Simulated user for the authentic sign-and-send endpoint."""

    wait_time = between(0.5, 2)

    def on_start(self):
        """Create the admin session used by the protected endpoint."""
        username = os.environ.get("HEDWIG_LOCUST_USERNAME")
        password = os.environ.get("HEDWIG_LOCUST_PASSWORD")
        if not username or not password:
            raise RuntimeError(
                "Set HEDWIG_LOCUST_USERNAME and HEDWIG_LOCUST_PASSWORD before running Locust."
            )

        response = self.client.post(
            "/api/login",
            name="api_login",
            json={"username": username, "password": password},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Login failed with HTTP {response.status_code}")

    @task
    def api_sign_and_send_authentic(self):
        """Send an authentic message without adversarial threat types."""
        self.client.post(
            "/api/sign-and-send",
            name="api_sign_and_send_authentic",
            json={
                "message_text": "load test message",
                "n_bits": 32,
                "threat_type": "authentic",
            },
        )
