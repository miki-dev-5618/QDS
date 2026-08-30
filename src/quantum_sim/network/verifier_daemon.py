import asyncio
from typing import Dict, List, Tuple, Optional
import numpy as np

from quantum_sim.network.socket_node import AsyncSocketNode
from quantum_sim.network.messages import NetworkMessage, MessageType
from quantum_sim.core.circuit import prepare_bb84_state, add_bb84_measurement
from qiskit_aer import AerSimulator


class VerifierDaemon(AsyncSocketNode):
    """
    Verifier Node Daemon for Bob (Port 8002) and Charlie (Port 8003).
    - Receives quantum state copies from Alice via Channel Router
    - Symmetrises states by randomly forwarding/keeping upon trigger or automatically
    - Measures in random/dual bases to eliminate orthogonal quantum states
    - Independently validates incoming classical signatures against local eliminated state tables
    - Pushes live verification telemetry to Detection Monitor (Port 8004)
    """
    def __init__(
        self,
        node_id: str,
        peer_id: str,
        host: str = "127.0.0.1",
        port: int = 8002,
        router_port: int = 8000,
        detector_port: int = 8004
    ):
        super().__init__(node_id=node_id, host=host, port=port)
        self.peer_id = peer_id
        self.router_port = router_port
        self.detector_port = detector_port

        self.initial_states: List[Tuple[int, int]] = []
        self.held_states: List[List[Tuple[int, int]]] = []
        self.eliminated_states: List[List[str]] = []
        self.n_bits = 0
        self.backend = AerSimulator()

        self.register_handler(MessageType.DISTRIBUTE_STATES, self._handle_distribution)
        self.register_handler(MessageType.TRIGGER_SYMMETRISATION, self._handle_trigger_symmetrisation)
        self.register_handler(MessageType.SYMMETRISE_FORWARD, self._handle_symmetrise_forward)
        self.register_handler(MessageType.BROADCAST_SIGNATURE, self._handle_signature)

    async def _handle_distribution(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        payload = msg.payload
        raw_states = payload.get("states", [])
        self.n_bits = len(raw_states)
        self.initial_states = [tuple(s) for s in raw_states]
        self.held_states = [[] for _ in range(self.n_bits)]
        self.eliminated_states = [[] for _ in range(self.n_bits)]

        print(f"[{self.node_id}] Received {self.n_bits} quantum states from {msg.sender}.")
        return None

    async def _handle_trigger_symmetrisation(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        seed = msg.payload.get("seed", None)
        rng = np.random.default_rng(seed) if seed else np.random.default_rng()
        await self.perform_symmetrisation_swap(rng=rng)
        return None

    async def perform_symmetrisation_swap(self, rng: Optional[np.random.Generator] = None):
        if rng is None:
            rng = np.random.default_rng()

        forward_payload = []
        for i in range(self.n_bits):
            decision = rng.choice(['K', 'F'])
            b, ba = self.initial_states[i]
            if decision == 'K':
                self.held_states[i].append((b, ba))
            else:
                forward_payload.append([i, b, ba])

        print(f"[{self.node_id}] Symmetrisation: Keeping {len(self.initial_states) - len(forward_payload)} states, Forwarding {len(forward_payload)} to {self.peer_id}.")
        
        # Send forward packet through router
        if forward_payload:
            msg = NetworkMessage(
                msg_type=MessageType.SYMMETRISE_FORWARD,
                sender=self.node_id,
                recipient=self.peer_id,
                payload={"states": forward_payload}
            )
            await self.send_message("127.0.0.1", self.router_port, msg)

    async def _handle_symmetrise_forward(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        payload = msg.payload
        forwarded = payload.get("states", [])
        for pos, b, ba in forwarded:
            if 0 <= pos < self.n_bits:
                self.held_states[pos].append((b, ba))
        print(f"[{self.node_id}] Received {len(forwarded)} forwarded states from {msg.sender}.")

        # Trigger measurements automatically once forwarded states arrive
        self.perform_measurements_and_elimination()
        return None

    def perform_measurements_and_elimination(self, rng: Optional[np.random.Generator] = None):
        if rng is None:
            rng = np.random.default_rng()

        for i in range(self.n_bits):
            copies = len(self.held_states[i])
            if copies == 1:
                # 1 measurement in random basis
                b, ba = self.held_states[i][0]
                chosen_basis = int(rng.integers(0, 2))
                elim = self._measure_single(b, ba, chosen_basis, rng)
                self.eliminated_states[i].append(elim)
            elif copies >= 2:
                # Dual basis measurement
                b1, ba1 = self.held_states[i][0]
                b2, ba2 = self.held_states[i][1]
                elim1 = self._measure_single(b1, ba1, 0, rng) # Z
                elim2 = self._measure_single(b2, ba2, 1, rng) # X
                self.eliminated_states[i].extend([elim1, elim2])

        total_elim = sum(len(el) for el in self.eliminated_states)
        print(f"[{self.node_id}] Completed measurements. Eliminated {total_elim} orthogonal states across {self.n_bits} positions.")

    def _measure_single(self, src_bit: int, src_basis: int, meas_basis: int, rng: np.random.Generator) -> str:
        qc = prepare_bb84_state(np.array([src_bit]), np.array([src_basis]))
        meas_qc = add_bb84_measurement(qc, np.array([meas_basis]))
        result = self.backend.run(meas_qc, shots=1).result()
        counts = result.get_counts()
        out_bit = int(max(counts, key=counts.get).strip()[-1])

        if meas_basis == 0:
            return '|1⟩' if out_bit == 0 else '|0⟩'
        else:
            return '|−⟩' if out_bit == 0 else '|+⟩'

    async def _handle_signature(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        payload = msg.payload
        k = payload.get("k", 0)
        proposed_sig = payload.get("signature", [])

        mismatches = 0
        total_checked = 0

        for i in range(min(self.n_bits, len(proposed_sig))):
            if len(self.held_states[i]) > 0:
                total_checked += 1
                b, ba = proposed_sig[i]
                if ba == 0:
                    state_sym = '|0⟩' if b == 0 else '|1⟩'
                else:
                    state_sym = '|+⟩' if b == 0 else '|−⟩'

                if state_sym in self.eliminated_states[i]:
                    mismatches += 1

        is_valid = (mismatches == 0)
        print(f"[{self.node_id}] Signature verification for k={k}: {'PASS' if is_valid else 'FAIL'} (Mismatches: {mismatches}/{total_checked})")

        # Push telemetry to Detection Engine
        telemetry = NetworkMessage(
            msg_type=MessageType.VERIFICATION_REPORT,
            sender=self.node_id,
            recipient="Detector",
            payload={
                "k": k,
                "verifier": self.node_id,
                "is_valid": is_valid,
                "mismatches": mismatches,
                "total_checked": total_checked
            }
        )
        await self.send_message("127.0.0.1", self.detector_port, telemetry)
        return None
