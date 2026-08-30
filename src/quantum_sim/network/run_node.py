"""
CLI entrypoint to run individual node daemons as standalone long-running processes.
Usage:
    python -m quantum_sim.network.run_node router --port 8000
    python -m quantum_sim.network.run_node alice --port 8001
    python -m quantum_sim.network.run_node bob --port 8002
    python -m quantum_sim.network.run_node charlie --port 8003
    python -m quantum_sim.network.run_node detector --port 8004
"""

import sys
import os
import argparse
import asyncio

# Ensure src is discoverable from repository root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from quantum_sim.network.channel_proxy import ChannelProxyNode
from quantum_sim.network.alice_daemon import AliceDaemon
from quantum_sim.network.verifier_daemon import VerifierDaemon
from quantum_sim.network.detector_daemon import DetectorDaemon


async def main():
    parser = argparse.ArgumentParser(description="Quantum Network Node Runner")
    parser.add_argument("role", choices=["router", "alice", "bob", "charlie", "detector"], help="Role of the node")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on")
    args = parser.parse_args()

    if args.role == "router":
        port = args.port or 8000
        node = ChannelProxyNode(port=port)
    elif args.role == "alice":
        port = args.port or 8001
        node = AliceDaemon(port=port)
    elif args.role == "bob":
        port = args.port or 8002
        node = VerifierDaemon(node_id="Bob", peer_id="Charlie", port=port)
    elif args.role == "charlie":
        port = args.port or 8003
        node = VerifierDaemon(node_id="Charlie", peer_id="Bob", port=port)
    elif args.role == "detector":
        port = args.port or 8004
        node = DetectorDaemon(port=port)
    else:
        print(f"Unknown role: {args.role}")
        return

    print("=" * 60)
    print(f" [NODE BOOT] Starting {node.node_id} on port {node.port}...")
    print("=" * 60)
    await node.start_server()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print(f"\n[{node.node_id}] Shutting down...")
        await node.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
