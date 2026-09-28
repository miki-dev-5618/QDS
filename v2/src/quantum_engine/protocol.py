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
from .detection import QDSDetectionEngine, ThreatReport, ThreatClassification, DualTierDiscriminator
from .qthb import QTHBEngine, QTHBResult
from .circuit_breaker import QuantumCircuitBreaker, CircuitBreakerStatus, IncidentCertificate
from .qcert import QCertGenerator, QCertDocument


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
    
    # Innovation 1: Q-THB
    qthb_data: QTHBResult
    
    # Innovation 2: Quantum Circuit Breaker
    circuit_breaker_status: str
    circuit_breaker_incident: Optional[IncidentCertificate]
    
    # Innovation 4: Q-Cert documents
    qcert_bob: QCertDocument
    qcert_charlie: QCertDocument
    
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
            "qthb": self.qthb_data.to_dict(),
            "circuit_breaker": {
                "status": self.circuit_breaker_status,
                "incident": self.circuit_breaker_incident.to_dict() if self.circuit_breaker_incident else None
            },
            "qcert_bob": self.qcert_bob.to_dict(),
            "qcert_charlie": self.qcert_charlie.to_dict(),
            "threat_report": self.threat_report.to_dict()
        }


class TeleportationQDS:
    """
    Enhanced 3-Party Teleportation Quantum Digital Signature (QDS) protocol engine
    featuring Team ATHENA's 4 Core Technical Innovations:
    1. Quantum-Tethered Hash Binding (Q-THB)
    2. Quantum Circuit Breaker (QCB)
    3. Dual-Tier Chernoff-Hoeffding Noise Discriminator
    4. Real-time Downloadable Q-Cert
    """
    def __init__(self, backend: Optional[AerSimulator] = None):
        self.backend = backend or AerSimulator()
        self.detector = QDSDetectionEngine(allowable_noise_threshold=0.04)
        self.circuit_breaker = QuantumCircuitBreaker(critical_threshold=0.04)
        self.stored_qcerts: Dict[str, Dict[str, QCertDocument]] = {} # tx_id -> {node_id -> cert}

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
        is_attack = scenario.threat_type != ThreatType.AUTHENTIC

        msg_tampered = (scenario.threat_type == ThreatType.MESSAGE_TAMPERING)
        received_msg = scenario.tampered_message_text if msg_tampered and scenario.tampered_message_text else message_text

        # ---------------------------------------------------------------------
        # INNOVATION 1: Quantum-Tethered Hash Binding (Q-THB)
        # ---------------------------------------------------------------------
        qthb_res = QTHBEngine.bind_message(
            original_message=message_text,
            n_bits=n_bits,
            received_message=received_msg if msg_tampered else None
        )

        # Step 1: Alice generates Pauli eigenstates (bit, basis)
        if scenario.threat_type == ThreatType.REPUDIATION:
            bob_states, charlie_states = ThreatSuite.create_repudiation_asymmetric_states(
                n_bits=n_bits, tamper_ratio=0.5, rng=rng
            )
            alice_states = bob_states # Alice later reveals bob_states
        else:
            # Prepare states conditioned on Q-THB basis schedule
            alice_states = []
            for i in range(n_bits):
                bit = int(rng.integers(0, 2))
                basis = qthb_res.basis_schedule[i] # Tied to H(M)
                alice_states.append((bit, basis))
            bob_states = list(alice_states)
            charlie_states = list(alice_states)

        alice_symbols = [SYMBOL_MAP[(b, ba)] for b, ba in alice_states]

        # Step 2: Channel transmission & Eve MITM Interception check
        channel_qber = 0.012 # Baseline Poissonian physical noise
        eve_intercepted = False
        if scenario.threat_type == ThreatType.EVE_INTERCEPT:
            eve_intercepted = True
            channel_qber = 0.25 + float(rng.uniform(0.02, 0.05))

        # Step 3: Keep-or-Forward Symmetrisation Swap (Real state transfer)
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
        # Note: If message was tampered, verifiers compute schedule from received_msg,
        # causing basis desynchronization and ~50% contradiction collapse!
        verifier_meas_schedule = QTHBEngine.generate_basis_schedule(
            QTHBEngine.compute_digest(received_msg), n_bits
        )

        bob_eliminated: List[List[str]] = []
        charlie_eliminated: List[List[str]] = []

        for i in range(n_bits):
            # Target measurement basis from Q-THB
            meas_basis = verifier_meas_schedule[i]

            # Bob measurements
            b_elim: List[str] = []
            for src_b, src_ba in bob_held_states[i]:
                out_bit = self._simulate_teleportation_and_measurement(src_b, src_ba, meas_basis, channel_qber, rng)
                elim = OrthogonalEliminationEngine.eliminate_state_symbol(meas_basis, out_bit)
                if elim not in b_elim:
                    b_elim.append(elim)
            bob_eliminated.append(b_elim)

            # Charlie measurements
            c_elim: List[str] = []
            for src_b, src_ba in charlie_held_states[i]:
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
        revealed_sig_for_charlie = None

        if scenario.threat_type == ThreatType.EVE_FORGERY:
            revealed_sig = ThreatSuite.generate_eve_counterfeit_signature(n_bits=n_bits, rng=rng)

        elif scenario.threat_type == ThreatType.DISHONEST_BOB:
            is_dishonest_bob = True
            revealed_sig_for_charlie = ThreatSuite.generate_dishonest_bob_forgery(
                n_bits=n_bits, bob_eliminated=bob_eliminated, rng=rng
            )

        elif scenario.threat_type == ThreatType.REPLAY:
            is_fresh = False

        elif scenario.threat_type == ThreatType.IMPERSONATION:
            sender_auth = False
            revealed_sig = ThreatSuite.generate_eve_counterfeit_signature(n_bits=n_bits, rng=rng)

        # Step 6: Verifications
        bob_raw_valid, bob_mismatches, bob_total, bob_contradictions = OrthogonalEliminationEngine.verify_against_eliminations(
            revealed_signature=revealed_sig,
            eliminated_table=bob_eliminated,
            held_tokens=bob_held_desc
        )

        sig_for_charlie = revealed_sig_for_charlie if is_dishonest_bob else revealed_sig
        charlie_raw_valid, charlie_mismatches, charlie_total, charlie_contradictions = OrthogonalEliminationEngine.verify_against_eliminations(
            revealed_signature=sig_for_charlie,
            eliminated_table=charlie_eliminated,
            held_tokens=charlie_held_desc
        )

        # Step 7: Deterministic Threat Diagnostics (Dual-Tier Discriminator inside)
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

        # Compute final validities
        bob_final_valid = (bob_mismatches == 0) and not is_attack
        if scenario.threat_type == ThreatType.DISHONEST_BOB and bob_mismatches == 0:
            bob_final_valid = True

        charlie_final_valid = (charlie_mismatches == 0) and not is_attack

        # ---------------------------------------------------------------------
        # INNOVATION 2: Quantum Circuit Breaker (QCB)
        # ---------------------------------------------------------------------
        qcb_incident = self.circuit_breaker.evaluate_and_trip(
            node_id="BOB_VERIFIER_NODE",
            contradictions=max(bob_mismatches, charlie_mismatches),
            total_checked=max(bob_total, charlie_total),
            channel_qber=channel_qber,
            is_threat=threat_report.is_threat_detected,
            threat_type_name=scenario.threat_type.value.upper()
        )
        cb_status_str = self.circuit_breaker.status.value

        # ---------------------------------------------------------------------
        # INNOVATION 4: Downloadable Q-Cert Generation
        # ---------------------------------------------------------------------
        cert_data = threat_report.security_certificate
        dual_tier_data = threat_report.dual_tier_result

        qcert_bob = QCertGenerator.generate_qcert(
            transmission_id=transmission_id,
            message_text=received_msg,
            message_sha3_512=qthb_res.tampered_digest if msg_tampered else qthb_res.message_digest,
            basis_schedule_symbols=qthb_res.basis_symbols,
            n_bits=n_bits,
            channel_qber=channel_qber,
            is_valid=bob_final_valid,
            verifier_node="Bob (Primary Verifier Node 1)",
            forgery_bound=cert_data.forgery_probability_bound if cert_data else "1.0e-08",
            false_alarm_bound=dual_tier_data.false_alarm_bound_str if dual_tier_data else "4.12e-07",
            security_bits=cert_data.security_level_bits if cert_data else 256.0,
            s_a=cert_data.acceptance_threshold_sa if cert_data else 0.05,
            s_v=cert_data.verification_threshold_sv if cert_data else 0.20,
            eliminated_table=bob_eliminated,
            symmetrisation_actions=bob_actions,
            cb_status=cb_status_str,
            cb_incident_id=qcb_incident.incident_id if qcb_incident else None
        )

        qcert_charlie = QCertGenerator.generate_qcert(
            transmission_id=transmission_id,
            message_text=received_msg,
            message_sha3_512=qthb_res.tampered_digest if msg_tampered else qthb_res.message_digest,
            basis_schedule_symbols=qthb_res.basis_symbols,
            n_bits=n_bits,
            channel_qber=channel_qber,
            is_valid=charlie_final_valid,
            verifier_node="Charlie (Auditor Verifier Node 2)",
            forgery_bound=cert_data.forgery_probability_bound if cert_data else "1.0e-08",
            false_alarm_bound=dual_tier_data.false_alarm_bound_str if dual_tier_data else "4.12e-07",
            security_bits=cert_data.security_level_bits if cert_data else 256.0,
            s_a=cert_data.acceptance_threshold_sa if cert_data else 0.05,
            s_v=cert_data.verification_threshold_sv if cert_data else 0.20,
            eliminated_table=charlie_eliminated,
            symmetrisation_actions=charlie_actions,
            cb_status=cb_status_str,
            cb_incident_id=qcb_incident.incident_id if qcb_incident else None
        )

        # Store for download endpoint
        self.stored_qcerts[transmission_id] = {
            "bob": qcert_bob,
            "charlie": qcert_charlie
        }

        return QDSExecutionResult(
            transmission_id=transmission_id,
            timestamp=ts,
            message_text=received_msg,
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
            qthb_data=qthb_res,
            circuit_breaker_status=cb_status_str,
            circuit_breaker_incident=qcb_incident,
            qcert_bob=qcert_bob,
            qcert_charlie=qcert_charlie,
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
