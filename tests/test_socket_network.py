import pytest
import asyncio
import numpy as np

from quantum_sim.network.channel_proxy import ChannelProxyNode
from quantum_sim.network.alice_daemon import AliceDaemon
from quantum_sim.network.verifier_daemon import VerifierDaemon
from quantum_sim.network.detector_daemon import DetectorDaemon
from quantum_sim.detection.engine import ThreatClassification


def test_full_socket_qds_authentic():
    async def _runner():
        # Setup daemons on test ports (9400-9404)
        router = ChannelProxyNode(port=9400, routing_table={"Alice": 9401, "Bob": 9402, "Charlie": 9403, "Detector": 9404})
        alice = AliceDaemon(port=9401, router_port=9400)
        bob = VerifierDaemon(node_id="Bob", peer_id="Charlie", port=9402, router_port=9400, detector_port=9404)
        charlie = VerifierDaemon(node_id="Charlie", peer_id="Bob", port=9403, router_port=9400, detector_port=9404)
        detector = DetectorDaemon(port=9404)

        # Start servers
        await router.start_server()
        await alice.start_server()
        await bob.start_server()
        await charlie.start_server()
        await detector.start_server()

        try:
            # 1. Alice generates 16-bit keys
            rng = np.random.default_rng(42)
            alice.generate_signatures(n_bits=16, rng=rng)

            # 2. Alice distributes states over socket
            await alice.distribute_states_to_verifiers()
            await asyncio.sleep(0.05)

            # 3. Symmetrisation swap over sockets
            await bob.perform_symmetrisation_swap(rng=rng)
            await charlie.perform_symmetrisation_swap(rng=rng)
            await asyncio.sleep(0.05)

            # 4. Measure & eliminate
            bob.perform_measurements_and_elimination(rng=rng)
            charlie.perform_measurements_and_elimination(rng=rng)

            # 5. Broadcast legitimate signature
            await alice.broadcast_signature(k=0)
            await asyncio.sleep(0.1)

            # Verify detector report
            assert detector.last_report is not None
            assert detector.last_report.classification == ThreatClassification.BENIGN_AUTHENTIC
            assert detector.last_report.is_threat_detected is False
        finally:
            await router.stop()
            await alice.stop()
            await bob.stop()
            await charlie.stop()
            await detector.stop()

    asyncio.run(_runner())


def test_socket_qds_eve_intercept():
    async def _runner():
        router = ChannelProxyNode(port=9500, routing_table={"Alice": 9501, "Bob": 9502, "Charlie": 9503, "Detector": 9504})
        alice = AliceDaemon(port=9501, router_port=9500)
        bob = VerifierDaemon(node_id="Bob", peer_id="Charlie", port=9502, router_port=9500, detector_port=9504)
        charlie = VerifierDaemon(node_id="Charlie", peer_id="Bob", port=9503, router_port=9500, detector_port=9504)
        detector = DetectorDaemon(port=9504)

        # Enable Eve MITM on Router
        router.set_eve_attack(active=True, intercept_rate=1.0)

        await router.start_server()
        await alice.start_server()
        await bob.start_server()
        await charlie.start_server()
        await detector.start_server()

        try:
            rng = np.random.default_rng(42)
            alice.generate_signatures(n_bits=24, rng=rng)

            await alice.distribute_states_to_verifiers()
            await asyncio.sleep(0.05)

            await bob.perform_symmetrisation_swap(rng=rng)
            await charlie.perform_symmetrisation_swap(rng=rng)
            await asyncio.sleep(0.05)

            bob.perform_measurements_and_elimination(rng=rng)
            charlie.perform_measurements_and_elimination(rng=rng)

            await alice.broadcast_signature(k=0)
            await asyncio.sleep(0.1)

            assert detector.last_report is not None
            assert detector.last_report.is_threat_detected is True
        finally:
            await router.stop()
            await alice.stop()
            await bob.stop()
            await charlie.stop()
            await detector.stop()

    asyncio.run(_runner())
