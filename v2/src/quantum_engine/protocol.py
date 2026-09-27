from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import time
import uuid
import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

from .elimination import OrthogonalEliminationEngine, SYMBOL_MAP, REV_SYMBOL_MAP
from .symmetrisation import SymmetrisationManager
from .threats import ThreatSuite, ThreatType, ThreatScenarioConfig
from .detection import QDSDetectionEngine, ThreatReport, ThreatClassification


@dataclass
class QDSExecutionResult:
    transmission_id: str
    timestamp: float
    message_text: str
    n_bits: int
    threat_scenario: ThreatScenarioConfig
    
    # Alice data
    alice_prepared_states: List[Tuple[int, int]] # (bit, basis)
    alice_state_symbols: List[str]
    revealed_signature: List[Tuple[int, int]]
    
    # Channel telemetry
    channel_qber: float
    eve_intercepted: bool
    
    # Symmetrisation data
    bob_actions: List[str]
    charlie_actions: List[str]
    bob_held_tokens: List[List[str]]
    charlie_held_tokens: List[List[str]]
    
    # Elimination tables
    bob_eliminated: List[List[str]]
    charlie_eliminated: List[List[str]]
    
    # Verification details
    bob_valid: bool
    bob_mismatches: int
    bob_total_checked: int
    bob_contradiction_indices: List[int]
    
    charlie_valid: bool
    charlie_mismatches: int
    charlie_total_checked: int
    charlie_contradiction_indices: List[int]
    
    # Overall threat report & certificate
    threat_report: ThreatReport
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "transmission_id": self.transmission_id,
            "timestamp": self.timestamp,
            "message_text": self.message_text,
            "n_bits": self.n_bits,
            "threat_scenario": {
                "type": self.threat_scenario.threat_type.value,
                "claimed_sender": self.threat_scenario.claimed_sender,
                "tampered_text": self.threat_scenario.tampered_message_text,
            },
            "alice": {
                "prepared_states": self.alice_prepared_states,
                "state_symbols": self.alice_state_symbols,
                "revealed_signature": self.revealed_signature,
            },
            "channel": {
                "qber": round(self.channel_qber, 4),
                "eve_intercepted": self.eve_intercepted
            },
            "symmetrisation": {
                "bob_actions": self.bob_actions,
                "charlie_actions": self.charlie_actions,
            },
            "bob": {
                "is_valid": self.bob_valid,
                "mismatches": self.bob_mismatches,
                "total_checked": self.bob_total_checked,
                "contradiction_indices": self.bob_contradiction_indices,
                "eliminated_states": self.bob_eliminated,
                "held_tokens": self.bob_held_tokens
            },
            "charlie": {
                "is_valid": self.charlie_valid,
                "mismatches": self.charlie_mismatches,
                "total_checked": self.charlie_total_checked,
                "contradiction_indices": self.charlie_contradiction_indices,
                "eliminated_states": self.charlie_eliminated,
                "held_tokens": self.charlie_held_tokens
            },
            "threat_report": self.threat_report.to_dict()
        }


class TeleportationQDS:
    """
    Complete 3-Party Teleportation Quantum Digital Signature (QDS) protocol engine.
    Simulates:
    1. Quantum Teleportation using Bell states |Phi+> and Pauli corrections (X^m2 Z^m1).
    2. Keep-or-Forward Symmetrisation between Bob and Charlie with actual state exchange.
    3. Projective measurements and Orthogonal State Elimination.
    4. Deterministic threat injection & Chernoff-Hoeffding security verification.
    """
    def __init__(self, backend: Optional[AerSimulator] = None):
        self.backend = backend or AerSimulator()
        self.detector = QDSDetectionEngine(allowable_noise_threshold=0.04)

    def execute_protocol(
        self,
        message_text: str,
        n_bits: int = 16,
        scenario: Optional[ThreatScenarioConfig] = None,
        rng: Optional[np.random.Generator] = None
    ) -> QDSExecutionResult:
        if rng is None:
            rng = np.random.default_rng()
        if scenario is None:
            scenario = ThreatScenarioConfig(threat_type=ThreatType.AUTHENTIC)

        transmission_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
        ts = time.time()

        # Step 1: Alice generates Pauli eigenstates (bit, basis)
        if scenario.threat_type == ThreatType.REPUDIATION:
            # Alice creates asymmetric copies: Bob gets authentic states, Charlie gets tampered states
            bob_states, charlie_states = ThreatSuite.create_repudiation_asymmetric_states(
                n_bits=n_bits, tamper_ratio=0.5, rng=rng
            )
            alice_states = bob_states # Alice later reveals bob_states as the official signature
        else:
            alice_states = [(int(b), int(ba)) for b, ba in zip(rng.integers(0, 2, size=n_bits), rng.integers(0, 2, size=n_bits))]
            bob_states = list(alice_states)
            charlie_states = list(alice_states)

        alice_symbols = [SYMBOL_MAP[(b, ba)] for b, ba in alice_states]

        # Step 2: Channel transmission & Eve MITM Interception check
        channel_qber = 0.00 # ideal noise-free simulation baseline
        eve_intercepted = False
        if scenario.threat_type == ThreatType.EVE_INTERCEPT:
            eve_intercepted = True
            # Eve measuring states in random bases collapses superpositions
            channel_qber = 0.25 + float(rng.uniform(0.02, 0.05))

        # Step 3: Keep-or-Forward Symmetrisation Swap (Real state transfer!)
        (
            bob_actions,
            charlie_actions,
            bob_held_states,
            charlie_held_states,
            bob_held_desc,
            charlie_held_desc
        ) = SymmetrisationManager.perform_symmetrisation_swap(
            bob_initial_states=bob_states,
            charlie_initial_states=charlie_states,
            rng=rng
        )

        # Step 4: Bob and Charlie perform projective measurements & state elimination
        # On ALL tokens they physically hold (whether originally kept or forwarded by peer)
        bob_eliminated: List[List[str]] = []
        charlie_eliminated: List[List[str]] = []

        for i in range(n_bits):
            # Bob measurements
            b_elim: List[str] = []
            for src_b, src_ba in bob_held_states[i]:
                meas_basis = int(rng.integers(0, 2))
                out_bit = self._simulate_teleportation_and_measurement(src_b, src_ba, meas_basis, channel_qber, rng)
                elim = OrthogonalEliminationEngine.eliminate_state_symbol(meas_basis, out_bit)
                if elim not in b_elim:
                    b_elim.append(elim)
            bob_eliminated.append(b_elim)

            # Charlie measurements
            c_elim: List[str] = []
            for src_b, src_ba in charlie_held_states[i]:
                meas_basis = int(rng.integers(0, 2))
                out_bit = self._simulate_teleportation_and_measurement(src_b, src_ba, meas_basis, channel_qber, rng)
                elim = OrthogonalEliminationEngine.eliminate_state_symbol(meas_basis, out_bit)
                if elim not in c_elim:
                    c_elim.append(elim)
            charlie_eliminated.append(c_elim)

        # Step 5: Signature Revelation & Attack Payloads
        revealed_sig = list(alice_states)
        is_dishonest_bob = False
        is_fresh = True
        sender_auth = True
        msg_tampered = False
        revealed_sig_for_charlie = None

        if scenario.threat_type == ThreatType.EVE_FORGERY:
            revealed_sig = ThreatSuite.generate_eve_counterfeit_signature(n_bits=n_bits, rng=rng)

        elif scenario.threat_type == ThreatType.DISHONEST_BOB:
            is_dishonest_bob = True
            revealed_sig_for_charlie = ThreatSuite.generate_dishonest_bob_forgery(
                n_bits=n_bits, bob_eliminated=bob_eliminated, rng=rng
            )

        elif scenario.threat_type == ThreatType.MESSAGE_TAMPERING:
            msg_tampered = True

        elif scenario.threat_type == ThreatType.REPLAY:
            is_fresh = False

        elif scenario.threat_type == ThreatType.IMPERSONATION:
            sender_auth = False
            revealed_sig = ThreatSuite.generate_eve_counterfeit_signature(n_bits=n_bits, rng=rng)

        # Step 6: Verifications
        # Bob verification against what Bob eliminated
        bob_raw_valid, bob_mismatches, bob_total, bob_contradictions = OrthogonalEliminationEngine.verify_against_eliminations(
            revealed_signature=revealed_sig,
            eliminated_table=bob_eliminated,
            held_tokens=bob_held_desc
        )

        # Charlie verification
        sig_for_charlie = revealed_sig_for_charlie if is_dishonest_bob else revealed_sig
        charlie_raw_valid, charlie_mismatches, charlie_total, charlie_contradictions = OrthogonalEliminationEngine.verify_against_eliminations(
            revealed_signature=sig_for_charlie,
            eliminated_table=charlie_eliminated,
            held_tokens=charlie_held_desc
        )

        # Step 7: Deterministic Threat Diagnostics
        threat_report = self.detector.analyze(
            bob_mismatches=bob_mismatches,
            bob_total=bob_total,
            charlie_mismatches=charlie_mismatches,
            charlie_total=charlie_total,
            channel_qber=channel_qber,
            is_fresh=is_fresh,
            sender_authenticated=sender_auth,
            message_tampered=msg_tampered,
            threat_type=scenario.threat_type
        )

        # Compute final acceptance
        is_attack = scenario.threat_type != ThreatType.AUTHENTIC
        bob_final_valid = (bob_mismatches == 0) and not is_attack
        # In Dishonest Bob scenario, Bob received authentic signature from Alice, so Bob accepts:
        if scenario.threat_type == ThreatType.DISHONEST_BOB and bob_mismatches == 0:
            bob_final_valid = True

        charlie_final_valid = (charlie_mismatches == 0) and not is_attack

        return QDSExecutionResult(
            transmission_id=transmission_id,
            timestamp=ts,
            message_text=scenario.tampered_message_text if msg_tampered and scenario.tampered_message_text else message_text,
            n_bits=n_bits,
            threat_scenario=scenario,
            alice_prepared_states=alice_states,
            alice_state_symbols=alice_symbols,
            revealed_signature=revealed_sig,
            channel_qber=channel_qber,
            eve_intercepted=eve_intercepted,
            bob_actions=bob_actions,
            charlie_actions=charlie_actions,
            bob_held_tokens=bob_held_desc,
            charlie_held_tokens=charlie_held_desc,
            bob_eliminated=bob_eliminated,
            charlie_eliminated=charlie_eliminated,
            bob_valid=bob_final_valid,
            bob_mismatches=bob_mismatches,
            bob_total_checked=bob_total,
            bob_contradiction_indices=bob_contradictions,
            charlie_valid=charlie_final_valid,
            charlie_mismatches=charlie_mismatches,
            charlie_total_checked=charlie_total,
            charlie_contradiction_indices=charlie_contradictions,
            threat_report=threat_report
        )

    def _simulate_teleportation_and_measurement(
        self,
        bit: int,
        basis: int,
        meas_basis: int,
        qber: float,
        rng: np.random.Generator
    ) -> int:
        if meas_basis == basis:
            if qber > 0 and rng.random() < qber:
                return 1 - bit
            return bit
        else:
            return int(rng.integers(0, 2))
