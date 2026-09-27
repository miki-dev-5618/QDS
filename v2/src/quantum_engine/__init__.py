"""
Quantum Digital Signature (QDS) Engine & Cyber Threat Detection Suite.
Implements:
- Teleportation-based and Direct BB84 QDS Protocols
- Orthogonal State Elimination using Pauli eigenstates
- Keep-or-Forward Symmetrisation for Non-Repudiation
- Deterministic Threat Suite (Eve Forgery, Dishonest Bob, Eve MITM, Repudiation, Replay, Impersonation)
- Chernoff-Hoeffding Statistical Verification Engine
"""

from .protocol import TeleportationQDS, QDSExecutionResult
from .elimination import OrthogonalEliminationEngine, SYMBOL_MAP, REV_SYMBOL_MAP
from .symmetrisation import SymmetrisationManager
from .threats import ThreatSuite, ThreatType, ThreatScenarioConfig
from .detection import QDSDetectionEngine, ThreatReport, ThreatClassification, QDSSecurityBounds

__all__ = [
    "TeleportationQDS",
    "QDSExecutionResult",
    "OrthogonalEliminationEngine",
    "SYMBOL_MAP",
    "REV_SYMBOL_MAP",
    "SymmetrisationManager",
    "ThreatSuite",
    "ThreatType",
    "ThreatScenarioConfig",
    "QDSDetectionEngine",
    "ThreatReport",
    "ThreatClassification",
    "QDSSecurityBounds",
]
