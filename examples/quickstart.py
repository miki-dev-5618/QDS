"""
examples/quickstart.py
~~~~~~~~~~~~~~~~~~~~~~~
Minimal 10-line demonstration of the hedwig-client SDK.

Run from the repo root after installing the package::

    pip install -e .
    python examples/quickstart.py
"""
from hedwig_client import HedwigClient, LinkQuarantinedError

client = HedwigClient("http://localhost:8000", "admin", "secret")
client.login()
print("Topology:", client.topology()["channel_state"])

try:
    result = client.sign_and_send("Transfer £1 000 to account #42")
    print(f"verdict={result.verdict}  qber={result.qber:.4f}")
except LinkQuarantinedError as exc:
    print("Link is quarantined – resetting:", exc.detail["link"])
    client.reset_link(reason="quickstart recovery")
    print("Reset complete – retry now.")

