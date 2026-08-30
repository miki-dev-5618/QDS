"""
============================================================================
MULTI-PROCESS DISTRIBUTED QUANTUM NETWORK LAUNCHER & INTERACTIVE RUNNER
============================================================================
Spawns & Orchestrates:
- Port 8000: Quantum Channel Router & Eve Man-in-the-Middle Proxy
- Port 8001: Alice Signer Node Daemon
- Port 8002: Bob Verifier Node Daemon
- Port 8003: Charlie Verifier Node Daemon
- Port 8004: Threat Detection & Telemetry Monitoring Daemon
"""

import sys
import os
import asyncio
import numpy as np

# Ensure src is discoverable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from quantum_sim.network.channel_proxy import ChannelProxyNode
from quantum_sim.network.alice_daemon import AliceDaemon
from quantum_sim.network.verifier_daemon import VerifierDaemon
from quantum_sim.network.detector_daemon import DetectorDaemon
from quantum_sim.attacks.qds_threats import EveSignatureForgery, DishonestVerifierForgery


class DistributedNetworkRunner:
    def __init__(self):
        self.router = ChannelProxyNode(port=8000)
        self.alice = AliceDaemon(port=8001, router_port=8000)
        self.bob = VerifierDaemon(node_id="Bob", peer_id="Charlie", port=8002, router_port=8000, detector_port=8004)
        self.charlie = VerifierDaemon(node_id="Charlie", peer_id="Bob", port=8003, router_port=8000, detector_port=8004)
        self.detector = DetectorDaemon(port=8004)

    async def start(self):
        print("\n" + "=" * 80)
        print(" [BOOT] STARTING DISTRIBUTED QUANTUM SOCKET NETWORK DAEMONS")
        print("=" * 80)
        await self.router.start_server()
        await self.alice.start_server()
        await self.bob.start_server()
        await self.charlie.start_server()
        await self.detector.start_server()
        print(" [READY] All 5 Network Daemons active on localhost:8000-8004\n")

    async def stop(self):
        await self.router.stop()
        await self.alice.stop()
        await self.bob.stop()
        await self.charlie.stop()
        await self.detector.stop()

    async def run_protocol_cycle(
        self,
        n_bits: int = 16,
        attack_type: str = "none",
        rng: np.random.Generator = None
    ):
        if rng is None:
            rng = np.random.default_rng(42)

        print("-" * 80)
        print(f" >>> EXECUTING QDS PROTOCOL OVER SOCKETS [Scenario: {attack_type.upper()}]")
        print("-" * 80)

        # 1. Configure Channel Attack if requested
        if attack_type == "eve_intercept":
            self.router.set_eve_attack(active=True, intercept_rate=1.0)
        else:
            self.router.set_eve_attack(active=False)

        # 2. Step 1: Alice generates private signatures
        self.alice.generate_signatures(n_bits=n_bits, rng=rng)

        # 3. Step 2: Distribution over sockets
        asym_positions = list(range(n_bits // 2)) if attack_type == "repudiation" else None
        await self.alice.distribute_states_to_verifiers(asymmetric_charlie_positions=asym_positions)
        await asyncio.sleep(0.05)

        # 4. Step 3: Symmetrisation swap over peer sockets
        await self.bob.perform_symmetrisation_swap(rng=rng)
        await self.charlie.perform_symmetrisation_swap(rng=rng)
        await asyncio.sleep(0.05)

        # 5. Step 4: Orthogonal state elimination
        self.bob.perform_measurements_and_elimination(rng=rng)
        self.charlie.perform_measurements_and_elimination(rng=rng)

        # 6. Step 5: Classical Signature Revelation
        if attack_type == "eve_forgery":
            print("[ATTACK] Eve injecting counterfeit classical signature over socket...")
            forged_sig = EveSignatureForgery.generate_random_forgery(n_bits=n_bits, rng=rng)
            await self.alice.broadcast_signature(k=0, counterfeit_sig=forged_sig)
        elif attack_type == "dishonest_verifier":
            print("[ATTACK] Bob constructing targeted counterfeit signature to Charlie...")
            forged_sig_by_bob = DishonestVerifierForgery.forge_to_verifier(
                n_bits=n_bits,
                bob_eliminated=self.bob.eliminated_states,
                bob_held=[[f"H{j}" for j in range(len(h))] for h in self.bob.held_states],
                rng=rng
            )
            await self.alice.broadcast_signature(k=0, counterfeit_sig=forged_sig_by_bob)
        else:
            # Authentic Alice broadcast
            await self.alice.broadcast_signature(k=0)

        # Allow time for verifier socket telemetry to arrive at Detector
        await asyncio.sleep(0.1)


async def main():
    runner = DistributedNetworkRunner()
    await runner.start()

    if len(sys.argv) > 1 and sys.argv[1] in ["--batch", "-b", "all"]:
        print("Running full automated socket network test suite:\n")
        await runner.run_protocol_cycle(n_bits=16, attack_type="none")
        await runner.run_protocol_cycle(n_bits=16, attack_type="eve_forgery")
        await runner.run_protocol_cycle(n_bits=16, attack_type="dishonest_verifier")
        await runner.run_protocol_cycle(n_bits=16, attack_type="eve_intercept")
        await runner.run_protocol_cycle(n_bits=16, attack_type="repudiation")
        await runner.stop()
        return

    try:
        while True:
            print("+------------------------------------------------------------------------------+")
            print("| DISTRIBUTED QUANTUM SOCKET NETWORK (MULTI-PORT PROCESS CONTROLLER):          |")
            print("+------------------------------------------------------------------------------+")
            print("| [1] AUTHENTIC: Alice signs message k=0 -> Bob & Charlie verify via Sockets  |")
            print("| [2] EVE FORGERY: External attacker sends forged signature over network       |")
            print("| [3] DISHONEST BOB: Bob crafts targeted forged signature to frame Charlie    |")
            print("| [4] EVE MITM: Channel Router intercepts & collapses qubits in transit        |")
            print("| [5] REPUDIATION: Alice transmits asymmetric states to verifiers              |")
            print("| [6] BATCH TEST: Run all socket cycles sequentially                           |")
            print("| [0] EXIT & SHUTDOWN DAEMONS                                                  |")
            print("+------------------------------------------------------------------------------+")
            
            try:
                choice = input("Enter choice [0-6]: ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if choice == "0":
                break
            elif choice == "1":
                await runner.run_protocol_cycle(attack_type="none")
            elif choice == "2":
                await runner.run_protocol_cycle(attack_type="eve_forgery")
            elif choice == "3":
                await runner.run_protocol_cycle(attack_type="dishonest_verifier")
            elif choice == "4":
                await runner.run_protocol_cycle(attack_type="eve_intercept")
            elif choice == "5":
                await runner.run_protocol_cycle(attack_type="repudiation")
            elif choice == "6":
                for att in ["none", "eve_forgery", "dishonest_verifier", "eve_intercept", "repudiation"]:
                    await runner.run_protocol_cycle(attack_type=att)
            else:
                print(f"Invalid option '{choice}'.")

            try:
                input("\nPress Enter to return to socket network controller...")
            except (KeyboardInterrupt, EOFError):
                break
    finally:
        await runner.stop()
        print("Distributed Network Daemons shutdown cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
