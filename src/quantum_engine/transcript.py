from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .binding import SignedContext, SignedPackage
from .channel import ChannelModel, ChannelTestResult
from .roster import DEFAULT_CONFIG, SessionConfig
from .verifier import VerificationResult


@dataclass
class SigningSession:
    """Signer-private state for one distributed one-time signature."""
    context: SignedContext
    message: str
    signature: List[Tuple[int, int]]
    blinding: str
    commitment: str
    copies: Dict[str, List[Tuple[int, int]]]
    bob_actions: List[str]
    charlie_actions: List[str]
    channel_test: ChannelTestResult
    channel_model: ChannelModel
    observation_ms: float = 0.0        # wall time of the teleport/measure stream (simulator run)
    tokens_sent: int = 0
    tokens_planned: int = 0
    tokens_received: int = 0
    insufficient_tokens: bool = False
    reserve: List[Tuple[int, int]] = field(default_factory=list)   # precommitted reserve states (signer-private)
    reserve_blinding: Optional[str] = None
    reserve_commitment: Optional[str] = None
    allocation: Dict[str, Any] = field(default_factory=dict)       # evidence budget and its rationale
    config: SessionConfig = DEFAULT_CONFIG                          # fixed roster / delivery / depth H
    # Observer record of the recipients' private symmetrisation decisions, kept for display and audit.
    # The signer's own operations (reveal, open_reserve) never read it.
    actions: Dict[str, List[str]] = field(default_factory=dict)
    route_plan: Any = None
    route_execution: Dict[str, Any] = field(default_factory=dict)
    route_tests: Dict[str, Any] = field(default_factory=dict)
    route_abort: Optional[str] = None
    security_params: Any = None
    edge_ground_truth: Dict[str, Any] = field(default_factory=dict)  # simulator-private, never detector input

    @property
    def aborted(self) -> bool:
        return self.channel_test.alarm or self.insufficient_tokens or self.route_abort is not None


@dataclass
class Transcript:
    """What happened on the wire for one transmission (input to assessment)."""
    kind: str                                   # "direct", "chain" or "forward"
    link: str
    n_bits: int
    package: SignedPackage                      # primary package delivered
    results: List[VerificationResult]           # every verification performed
    display: Dict[str, VerificationResult]      # result shown on each verifier dashboard
    session: Optional[SigningSession] = None
    channel_test: Optional[ChannelTestResult] = None
    channel_model: Optional[ChannelModel] = None
    notes: List[str] = field(default_factory=list)
    config: Optional[SessionConfig] = None      # session configuration (None: default two-verifier)
