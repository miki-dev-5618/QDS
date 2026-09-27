import asyncio
from typing import Optional, List, Dict
import numpy as np

from quantum_sim.network.socket_node import AsyncSocketNode
from quantum_sim.network.messages import NetworkMessage, MessageType
from quantum_sim.channel.noise import DepolarizingNoise, BaseNoise
from quantum_sim.channel.attacks import InterceptResendAttack, BaseAttack


class ChannelProxyNode(AsyncSocketNode):
    """
    Quantum Channel Router & Eve Proxy daemon (Default Port: 8000).
    Acts as the physical quantum transmission medium.
    - Simulates physical transmission noise
    - Intercepts and measures packets when active attack mode (Eve) is enabled
    - Forwards quantum payloads to the appropriate destination node
    """
    def __init__(
        self,
        node_id: str = "QuantumChannelRouter",
        host: str = "127.0.0.1",
        port: int = 8000,
        routing_table: Optional[Dict[str, int]] = None
    ):
        super().__init__(node_id=node_id, host=host, port=port)
        self.routing_table = routing_table or {
            "Alice": 8001,
            "Bob": 8002,
            "Charlie": 8003,
            "Detector": 8004
        }
        self.attacks: List[BaseAttack] = []
        self.noises: List[BaseNoise] = []
        self.eve_active = False
        self.intercept_rate = 1.0

        # Register message handlers
        self.register_handler(MessageType.DISTRIBUTE_STATES, self._handle_distribution)
        self.register_handler(MessageType.SYMMETRISE_FORWARD, self._handle_forwarding)
        self.register_handler(MessageType.BROADCAST_SIGNATURE, self._handle_broadcast)
        self.register_handler(MessageType.SET_ATTACK, self._handle_set_attack)

    async def _handle_set_attack(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        active = msg.payload.get("active", False)
        rate = msg.payload.get("rate", 1.0)
        self.set_eve_attack(active=active, intercept_rate=rate)
        return None

    def set_eve_attack(self, active: bool, intercept_rate: float = 1.0):
        self.eve_active = active
        self.intercept_rate = intercept_rate
        print(f"[{self.node_id}] Eve Intercept-Resend Attack set to: {active} (p={intercept_rate*100:.0f}%)")

    def set_channel_noise(self, p_error: float = 0.0):
        self.noises = [DepolarizingNoise(p_error=p_error)] if p_error > 0 else []
        print(f"[{self.node_id}] Channel Depolarizing Noise set to: p={p_error*100:.1f}%")

    async def _handle_distribution(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        dest = msg.recipient
        dest_port = self.routing_table.get(dest)
        if not dest_port:
            print(f"[{self.node_id}] Unknown destination: {dest}")
            return None

        payload = msg.payload
        states = payload.get("states", [])

        if self.eve_active:
            print(f"[{self.node_id}] [EVE] INTERCEPTING {len(states)} quantum states in transit to {dest}!")
            attacked_states = []
            rng = np.random.default_rng()
            for b, ba in states:
                if rng.random() <= self.intercept_rate:
                    eve_basis = int(rng.integers(0, 2))
                    measured_bit = b if eve_basis == ba else int(rng.integers(0, 2))
                    attacked_states.append([measured_bit, eve_basis])
                else:
                    attacked_states.append([b, ba])
            payload["states"] = attacked_states
            payload["tampered_by_eve"] = True

        print(f"[{self.node_id}] Routing {len(states)} quantum states from {msg.sender} -> {dest} (Port {dest_port})")
        forward_msg = NetworkMessage(
            msg_type=MessageType.DISTRIBUTE_STATES,
            sender=msg.sender,
            recipient=dest,
            payload=payload
        )
        return await self.send_message("127.0.0.1", dest_port, forward_msg)

    async def _handle_forwarding(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        dest = msg.recipient
        dest_port = self.routing_table.get(dest)
        if not dest_port:
            return None

        payload = msg.payload
        states = payload.get("states", [])
        if self.eve_active:
            print(f"[{self.node_id}] [EVE] INTERCEPTING {len(states)} forwarded symmetrisation states -> {dest}!")
            rng = np.random.default_rng()
            attacked_states = []
            for item in states:
                pos, b, ba = item[0], item[1], item[2]
                if rng.random() <= self.intercept_rate:
                    eve_basis = int(rng.integers(0, 2))
                    measured_bit = b if eve_basis == ba else int(rng.integers(0, 2))
                    attacked_states.append([pos, measured_bit, eve_basis])
                else:
                    attacked_states.append([pos, b, ba])
            payload["states"] = attacked_states

        print(f"[{self.node_id}] Routing symmetrisation swap from {msg.sender} -> {dest} (Port {dest_port})")
        forward_msg = NetworkMessage(
            msg_type=MessageType.SYMMETRISE_FORWARD,
            sender=msg.sender,
            recipient=dest,
            payload=payload
        )
        return await self.send_message("127.0.0.1", dest_port, forward_msg)

    async def _handle_broadcast(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        print(f"[{self.node_id}] Broadcasting signature from {msg.sender} to Bob & Charlie")
        bob_msg = NetworkMessage(
            msg_type=MessageType.BROADCAST_SIGNATURE,
            sender=msg.sender,
            recipient="Bob",
            payload=msg.payload
        )
        charlie_msg = NetworkMessage(
            msg_type=MessageType.BROADCAST_SIGNATURE,
            sender=msg.sender,
            recipient="Charlie",
            payload=msg.payload
        )
        await self.send_message("127.0.0.1", self.routing_table["Bob"], bob_msg)
        await self.send_message("127.0.0.1", self.routing_table["Charlie"], charlie_msg)
        return None
