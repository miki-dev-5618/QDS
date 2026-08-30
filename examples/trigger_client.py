"""
============================================================================
CLIENT CONTROLLER FOR RUNNING DISTRIBUTED QUANTUM NETWORK SIMULATIONS
============================================================================
Connects to already-running daemons on ports 8000-8004 and triggers protocol
cycles, signature verification, and real-time attack injections.
"""

import sys
import os
import asyncio
import numpy as np

# Ensure src is discoverable
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from quantum_sim.network.messages import NetworkMessage, MessageType
from quantum_sim.network.socket_node import AsyncSocketNode
from quantum_sim.attacks.qds_threats import EveSignatureForgery, DishonestVerifierForgery


class NetworkClientController(AsyncSocketNode):
    def __init__(self, host: str = "127.0.0.1"):
        super().__init__(node_id="SimulationController", host=host, port=8099)
        self.router_port = 8000
        self.alice_port = 8001
        self.bob_port = 8002
        self.charlie_port = 8003
        self.detector_port = 8004

    async def trigger_cycle(self, n_bits: int = 16, attack_type: str = "none", rng: np.random.Generator = None):
        if rng is None:
            rng = np.random.default_rng(42)

        print("\n" + "=" * 80)
        print(f" [COMMAND SENT] Triggering QDS Protocol Cycle: {attack_type.upper()}")
        print("=" * 80)

        # 0. Configure Router Attack state if needed
        is_eve = (attack_type == "eve_intercept")
        msg_att = NetworkMessage(
            msg_type=MessageType.SET_ATTACK,
            sender="Controller",
            recipient="QuantumChannelRouter",
            payload={"active": is_eve, "rate": 1.0}
        )
        await self.send_message("127.0.0.1", self.router_port, msg_att)

        # 1. Alice generates private signature states
        alice_sigs = {
            0: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))],
            1: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
        }

        # 2. Check for Alice repudiation asymmetry
        charlie_states = list(alice_sigs[0])
        if attack_type == "repudiation":
            for pos in range(n_bits // 2):
                b, ba = charlie_states[pos]
                charlie_states[pos] = (1 - b, ba)

        # 3. Distribute to Bob and Charlie via Channel Router
        msg_b = NetworkMessage(
            msg_type=MessageType.DISTRIBUTE_STATES,
            sender="Alice",
            recipient="Bob",
            payload={"k": 0, "copy_num": 1, "states": alice_sigs[0]}
        )
        msg_c = NetworkMessage(
            msg_type=MessageType.DISTRIBUTE_STATES,
            sender="Alice",
            recipient="Charlie",
            payload={"k": 0, "copy_num": 2, "states": charlie_states}
        )
        await self.send_message("127.0.0.1", self.router_port, msg_b)
        await self.send_message("127.0.0.1", self.router_port, msg_c)
        await asyncio.sleep(0.1)

        # 4. Trigger Symmetrisation Swap on Bob and Charlie
        msg_sym_b = NetworkMessage(
            msg_type=MessageType.TRIGGER_SYMMETRISATION,
            sender="Controller",
            recipient="Bob",
            payload={"seed": 42}
        )
        msg_sym_c = NetworkMessage(
            msg_type=MessageType.TRIGGER_SYMMETRISATION,
            sender="Controller",
            recipient="Charlie",
            payload={"seed": 43}
        )
        await self.send_message("127.0.0.1", self.bob_port, msg_sym_b)
        await self.send_message("127.0.0.1", self.charlie_port, msg_sym_c)
        await asyncio.sleep(0.15)

        # 5. Broadcast classical signature
        if attack_type == "eve_forgery":
            sig = EveSignatureForgery.generate_random_forgery(n_bits=n_bits, rng=rng)
        elif attack_type == "dishonest_verifier":
            sig = EveSignatureForgery.generate_random_forgery(n_bits=n_bits, rng=rng)
        else:
            sig = alice_sigs[0]

        msg_bc = NetworkMessage(
            msg_type=MessageType.BROADCAST_SIGNATURE,
            sender="Alice",
            recipient="ALL",
            payload={"k": 0, "signature": sig}
        )
        await self.send_message("127.0.0.1", self.router_port, msg_bc)
        print(" [COMPLETED] Packets sent over socket cluster. Check the node terminal windows to see live logs!\n")


async def main():
    controller = NetworkClientController()
    
    print("=" * 80)
    print("      QUANTUM NETWORK LIVE SIMULATION TRIGGER (CONTROLLER CLI)                ")
    print("=" * 80)
    print(" Assumes 5 node daemons are running via launch_cluster.bat\n")

    while True:
        print("+------------------------------------------------------------------------------+")
        print("| SELECT PROTOCOL SCENARIO TO FIRE ACROSS CLUSTER:                             |")
        print("+------------------------------------------------------------------------------+")
        print("| [1] AUTHENTIC SIGNATURE (Alice sends valid signature -> Bob & Charlie verify)|")
        print("| [2] EVE FORGERY (External attacker sends counterfeit signature string)       |")
        print("| [3] DISHONEST VERIFIER FORGERY (Bob sends forged signature to frame Charlie) |")
        print("| [4] EVE MITM (Channel Router intercepts & collapses qubits in transit)       |")
        print("| [5] DISHONEST SIGNER REPUDIATION (Alice sends asymmetric states)             |")
        print("| [0] EXIT                                                                     |")
        print("+------------------------------------------------------------------------------+")

        try:
            choice = input("Enter choice [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice == "0":
            break
        elif choice == "1":
            await controller.trigger_cycle(n_bits=16, attack_type="none")
        elif choice == "2":
            await controller.trigger_cycle(n_bits=16, attack_type="eve_forgery")
        elif choice == "3":
            await controller.trigger_cycle(n_bits=16, attack_type="dishonest_verifier")
        elif choice == "4":
            await controller.trigger_cycle(n_bits=16, attack_type="eve_intercept")
        elif choice == "5":
            await controller.trigger_cycle(n_bits=16, attack_type="repudiation")
        else:
            print("Invalid selection.")

        try:
            input("Press Enter to send another scenario...")
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    asyncio.run(main())
