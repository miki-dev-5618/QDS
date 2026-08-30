import asyncio
from typing import Dict, Optional, Any
from quantum_sim.network.socket_node import AsyncSocketNode
from quantum_sim.network.messages import NetworkMessage, MessageType
from quantum_sim.detection.engine import QDSDetectionEngine, ThreatReport


class DetectorDaemon(AsyncSocketNode):
    """
    Threat Detection & Telemetry Monitoring Daemon (Default Port: 8004).
    - Collects asynchronous telemetry from Bob & Charlie socket verifiers
    - Correlates multi-verifier elimination contradictions & asymmetry
    - Emits live threat alerts and diagnosis verdicts
    """
    def __init__(self, node_id: str = "ThreatDetector", host: str = "127.0.0.1", port: int = 8004):
        super().__init__(node_id=node_id, host=host, port=port)
        self.engine = QDSDetectionEngine()
        self.pending_reports: Dict[int, Dict[str, Any]] = {} # k -> {verifier -> report}
        self.last_report: Optional[ThreatReport] = None

        self.register_handler(MessageType.VERIFICATION_REPORT, self._handle_telemetry)

    async def _handle_telemetry(self, msg: NetworkMessage) -> Optional[NetworkMessage]:
        payload = msg.payload
        k = payload["k"]
        verifier = payload["verifier"]

        if k not in self.pending_reports:
            self.pending_reports[k] = {}

        self.pending_reports[k][verifier] = payload
        print(f"[{self.node_id}] Telemetry from {verifier}: {payload['mismatches']}/{payload['total_checked']} contradictions.")

        # If both Bob and Charlie have reported, perform multi-party threat analysis
        if "Bob" in self.pending_reports[k] and "Charlie" in self.pending_reports[k]:
            b_data = self.pending_reports[k]["Bob"]
            c_data = self.pending_reports[k]["Charlie"]

            report = self.engine.analyze(
                bob_mismatches=b_data["mismatches"],
                bob_total=b_data["total_checked"],
                charlie_mismatches=c_data["mismatches"],
                charlie_total=c_data["total_checked"]
            )
            self.last_report = report
            self._print_verdict(k, report)

            # Clear session
            del self.pending_reports[k]

        return None

    def _print_verdict(self, k: int, report: ThreatReport):
        print("\n" + "=" * 70)
        print(f" [REPORT] LIVE TELEMETRY THREAT REPORT FOR MESSAGE k={k}")
        print("=" * 70)
        print(f" Classification : {report.classification.value}")
        threat_tag = "[ALERT] DETECTED" if report.is_threat_detected else "[PASS] BENIGN / PASS"
        print(f" Threat Alert   : {threat_tag}")
        print(f" Confidence     : {report.confidence_score * 100:.1f}%")
        print(f" Verdict        : {report.verdict}")
        print(f" Details        : {report.details}")
        print(f" Bob Contradictions     : {report.bob_contradictions}/{report.bob_total_checked} ({report.bob_contradiction_rate*100:.1f}%)")
        print(f" Charlie Contradictions : {report.charlie_contradictions}/{report.charlie_total_checked} ({report.charlie_contradiction_rate*100:.1f}%)")
        print("=" * 70 + "\n")
