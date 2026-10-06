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
from .channel import ChannelModel, ChannelTestResult, estimate_channel_qber
from .binding import SignedContext, SignedPackage, commitment, message_digest
from .verifier import VerifierNode, VerificationResult, DistributionRecord
from .policy import ResponsePolicy, ResponseDecision, decide
from .enforcement import ChannelGuard, ChannelQuarantined, LINK_SIGNER, LINK_FORWARD
from .router import SimulatedRouter
from .store import Store
from .audit import (AuditAuthority, build_record, build_evidence, build_reset_record, verify_certificate,
                    verify_certificate_report, verify_chain)
from .signers import pq_provider

__all__ = [
    "TeleportationQDS", "QDSExecutionResult", "VERIFIERS",
    "OrthogonalEliminationEngine", "SYMBOL_MAP", "REV_SYMBOL_MAP",
    "SymmetrisationManager",
    "ThreatSuite", "ThreatType", "ThreatScenarioConfig", "NoPackageToReplay",
    "QDSDetectionEngine", "ThreatReport", "ThreatClassification",
    "TierTwoResult", "tier_two",
    "SecurityParameters",
    "ChannelModel", "ChannelTestResult", "estimate_channel_qber",
    "SignedContext", "SignedPackage", "commitment", "message_digest",
    "VerifierNode", "VerificationResult", "DistributionRecord",
    "ResponsePolicy", "ResponseDecision", "decide",
    "ChannelGuard", "ChannelQuarantined", "LINK_SIGNER", "LINK_FORWARD",
    "SimulatedRouter", "Store",
    "AuditAuthority", "build_record", "build_evidence", "build_reset_record",
    "verify_certificate", "verify_certificate_report", "verify_chain",
    "pq_provider",
]
