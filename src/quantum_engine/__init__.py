"""
Quantum Digital Signature (QDS) engine and blind threat detection.

- Bell-state teleportation of Pauli-eigenstate tokens (Qiskit or statevector backend)
- Keep-or-forward symmetrisation and orthogonal state elimination
- Tier 1: observable channel testing with sequential early abort
- Tier 2: disturbance-pattern attribution (channel vs. signature source)
- Message/context binding, persistent replay protection, per-verifier decisions
- Response policy and circuit breaker (OPEN / WATCH / QUARANTINED / RESET_PENDING)
- Simulated router, SQLite persistence, hash-chained signed audit records
- Attack injectors kept separate from detection (threats.py)
"""

from .protocol import TeleportationQDS, QDSExecutionResult, VERIFIERS
from .elimination import OrthogonalEliminationEngine, SYMBOL_MAP, REV_SYMBOL_MAP
from .symmetrisation import SymmetrisationManager
from .threats import ThreatSuite, ThreatType, ThreatScenarioConfig, NoPackageToReplay
from .detection import QDSDetectionEngine, ThreatReport, ThreatClassification
from .discriminator import TierTwoResult, tier_two
from .security import SecurityParameters
from .channel import ChannelModel, ChannelTestResult, estimate_channel_qber, make_amplitude_damping_channel, make_readout_channel, make_lossy_channel, make_cloning_channel
from .binding import SignedContext, SignedPackage, commitment, message_digest
from .verifier import VerifierNode, VerificationResult, DistributionRecord, estimate_readout_mismatch_overhead
from .policy import ResponsePolicy, ResponseDecision, decide
from .enforcement import ChannelGuard, ChannelQuarantined, LINK_SIGNER, LINK_FORWARD
from .router import SimulatedRouter
from .store import Store
from .audit import (AuditAuthority, build_record, build_evidence, build_reset_record, verify_certificate,
                    verify_certificate_report, verify_chain)
from .signers import pq_provider
from .cloning import (build_cloning_circuit, measure_cloner_fidelity, simulate_eve_cloning_step,
                      UNIVERSAL_FIDELITY, UNIVERSAL_ERROR, PHASE_COVARIANT_FIDELITY, PHASE_COVARIANT_ERROR)

__all__ = [
    "TeleportationQDS", "QDSExecutionResult", "VERIFIERS",
    "OrthogonalEliminationEngine", "SYMBOL_MAP", "REV_SYMBOL_MAP",
    "SymmetrisationManager",
    "ThreatSuite", "ThreatType", "ThreatScenarioConfig", "NoPackageToReplay",
    "QDSDetectionEngine", "ThreatReport", "ThreatClassification",
    "TierTwoResult", "tier_two",
    "SecurityParameters",
    "ChannelModel", "ChannelTestResult", "estimate_channel_qber", "make_amplitude_damping_channel", "make_readout_channel", "make_lossy_channel", "make_cloning_channel",
    "SignedContext", "SignedPackage", "commitment", "message_digest",
    "VerifierNode", "VerificationResult", "DistributionRecord", "estimate_readout_mismatch_overhead",
    "ResponsePolicy", "ResponseDecision", "decide",
    "ChannelGuard", "ChannelQuarantined", "LINK_SIGNER", "LINK_FORWARD",
    "SimulatedRouter", "Store",
    "AuditAuthority", "build_record", "build_evidence", "build_reset_record",
    "verify_certificate", "verify_certificate_report", "verify_chain",
    "pq_provider",
]
