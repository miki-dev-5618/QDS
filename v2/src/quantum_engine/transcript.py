from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .binding import SignedContext, SignedPackage
from .channel import ChannelModel, ChannelTestResult
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

    @property
    def aborted(self) -> bool:
        return self.channel_test.alarm


@dataclass
class Transcript:
    """What happened on the wire for one transmission (input to assessment)."""
    kind: str                                   # "direct" or "forward"
    link: str
    n_bits: int
    package: SignedPackage                      # primary package delivered
    results: List[VerificationResult]           # every verification performed
    display: Dict[str, VerificationResult]      # result shown on each verifier dashboard
    session: Optional[SigningSession] = None
    channel_test: Optional[ChannelTestResult] = None
    channel_model: Optional[ChannelModel] = None
    notes: List[str] = field(default_factory=list)
