"""
Quantum Digital Signature (QDS) Engine & Cyber Threat Detection Suite.
Features Team ATHENA's 4 Core Technical Innovations:
- Innovation 1: Quantum-Tethered Hash Binding (Q-THB)
- Innovation 2: Quantum Circuit Breaker (QCB) - Active Auto-Quenching
- Innovation 3: Dual-Tier Chernoff-Hoeffding Noise Discriminator
- Innovation 4: Real-time Downloadable Q-Cert (Zero-Knowledge Audit Trail)
"""

from .protocol import TeleportationQDS, QDSExecutionResult
from .elimination import OrthogonalEliminationEngine, SYMBOL_MAP, REV_SYMBOL_MAP
from .symmetrisation import SymmetrisationManager
from .threats import ThreatSuite, ThreatType, ThreatScenarioConfig
from .detection import (
    QDSDetectionEngine,
    ThreatReport,
    ThreatClassification,
    QDSSecurityBounds,
    DualTierDiscriminator,
    DualTierDiscriminatorResult,
    SecurityCertificate
)
from .qthb import QTHBEngine, QTHBResult
from .circuit_breaker import QuantumCircuitBreaker, CircuitBreakerStatus, IncidentCertificate
from .qcert import QCertGenerator, QCertDocument

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
    "DualTierDiscriminator",
    "DualTierDiscriminatorResult",
    "SecurityCertificate",
    "QTHBEngine",
    "QTHBResult",
    "QuantumCircuitBreaker",
    "CircuitBreakerStatus",
    "IncidentCertificate",
    "QCertGenerator",
    "QCertDocument",
]
