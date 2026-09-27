from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict, Optional
import json


class MessageType(str, Enum):
    # Setup & Distribution
    DISTRIBUTE_STATES = "DISTRIBUTE_STATES"
    DISTRIBUTE_STATES_ACK = "DISTRIBUTE_STATES_ACK"

    # Symmetrisation Swap
    TRIGGER_SYMMETRISATION = "TRIGGER_SYMMETRISATION"
    SYMMETRISE_FORWARD = "SYMMETRISE_FORWARD"
    SYMMETRISE_ACK = "SYMMETRISE_ACK"

    # Signing & Revelation
    BROADCAST_SIGNATURE = "BROADCAST_SIGNATURE"

    # Telemetry & Threat Reporting
    VERIFICATION_REPORT = "VERIFICATION_REPORT"
    THREAT_ALERT = "THREAT_ALERT"

    # Control commands
    SET_ATTACK = "SET_ATTACK"
    RESET = "RESET"
    PING = "PING"
    PONG = "PONG"


@dataclass
class NetworkMessage:
    msg_type: MessageType
    sender: str
    recipient: str
    payload: Dict[str, Any]
    timestamp: Optional[float] = None

    def serialize(self) -> bytes:
        data = asdict(self)
        data["msg_type"] = self.msg_type.value
        return (json.dumps(data) + "\n").encode("utf-8")

    @classmethod
    def deserialize(cls, raw_bytes: bytes) -> "NetworkMessage":
        data = json.loads(raw_bytes.decode("utf-8").strip())
        data["msg_type"] = MessageType(data["msg_type"])
        return cls(**data)
