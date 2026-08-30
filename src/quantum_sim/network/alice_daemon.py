import asyncio
from typing import Dict, List, Tuple, Optional
import numpy as np

from quantum_sim.network.socket_node import AsyncSocketNode
from quantum_sim.network.messages import NetworkMessage, MessageType


class AliceDaemon(AsyncSocketNode):
    """
    Alice Signer Node Daemon (Default Port: 8001).
    - Generates private quantum signature keys for messages k=0 and k=1
    - Sends quantum states to Bob and Charlie via the Channel Router (Port 8000)
    - Broadcasts chosen classical signatures upon request
    """
    def __init__(self, node_id: str = "Alice", host: str = "127.0.0.1", port: int = 8001, router_port: int = 8000):
        super().__init__(node_id=node_id, host=host, port=port)
        self.router_port = router_port
        self.signatures: Dict[int, List[Tuple[int, int]]] = {} # k -> list of (bit, basis)
        self.n_bits = 0

    def generate_signatures(self, n_bits: int, rng: Optional[np.random.Generator] = None):
        if rng is None:
            rng = np.random.default_rng()
        self.n_bits = n_bits
        self.signatures = {
            0: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))],
            1: [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
        }
        print(f"[{self.node_id}] Generated {n_bits}-length private signatures for k=0 and k=1.")

    async def distribute_states_to_verifiers(self, asymmetric_charlie_positions: Optional[List[int]] = None):
        """
        Sends copy 1 to Bob and copy 2 to Charlie via Channel Router.
        If asymmetric_charlie_positions is given, simulates Alice repudiation attempt.
        """
        # Distribute states for k=0 signature
        bob_states = list(self.signatures[0])
        charlie_states = list(self.signatures[0])

        if asymmetric_charlie_positions:
            print(f"[{self.node_id}] [ALERT] Dishonest Repudiation: Tampering Charlie's copy at positions {asymmetric_charlie_positions}")
            for pos in asymmetric_charlie_positions:
                if 0 <= pos < len(charlie_states):
                    b, ba = charlie_states[pos]
                    charlie_states[pos] = (1 - b, ba)

        # Send to Bob
        msg_bob = NetworkMessage(
            msg_type=MessageType.DISTRIBUTE_STATES,
            sender=self.node_id,
            recipient="Bob",
            payload={"k": 0, "copy_num": 1, "states": bob_states}
        )
        await self.send_message("127.0.0.1", self.router_port, msg_bob)

        # Send to Charlie
        msg_charlie = NetworkMessage(
            msg_type=MessageType.DISTRIBUTE_STATES,
            sender=self.node_id,
            recipient="Charlie",
            payload={"k": 0, "copy_num": 2, "states": charlie_states}
        )
        await self.send_message("127.0.0.1", self.router_port, msg_charlie)
        print(f"[{self.node_id}] Distributed quantum signature states to Bob and Charlie.")

    async def broadcast_signature(self, k: int, counterfeit_sig: Optional[List[Tuple[int, int]]] = None):
        sig = counterfeit_sig if counterfeit_sig is not None else self.signatures.get(k, [])
        msg = NetworkMessage(
            msg_type=MessageType.BROADCAST_SIGNATURE,
            sender=self.node_id,
            recipient="ALL",
            payload={"k": k, "signature": sig}
        )
        await self.send_message("127.0.0.1", self.router_port, msg)
        print(f"[{self.node_id}] Broadcasted classical signature for message k={k} to network.")
