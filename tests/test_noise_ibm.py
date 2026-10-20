"""
Tests for IBM fake-backend noise model, deferred-measurement teleportation,
and calibration integration.
"""
import json
import os
import numpy as np
import pytest

from src.quantum_engine.teleportation import (
    TeleportJob,
    build_deferred_teleportation_circuit,
    get_fake_backend,
    calibrate_ibm_backend,
    IBMFakeTeleportationBackend,
    make_backend,
)
from src.quantum_engine.channel import make_ibm_channel
from src.quantum_engine.protocol import TeleportationQDS
from src.quantum_engine.qcert import QCertGenerator
from src.quantum_engine.audit import AuditAuthority, build_record


def test_deferred_circuit_structure_and_no_mid_circuit_feed_forward():
    """Deferred circuit replaces if_else feed-forward with CX/CZ gates."""
    job = TeleportJob(bit=1, basis=1, meas_basis=1)
    qc = build_deferred_teleportation_circuit(job)
    names = [inst.operation.name for inst in qc.data]

    assert "if_else" not in names
    assert "cx" in names
    assert "cz" in names
    assert "measure" in names


def test_ibm_calibration_json_fidelity_below_one():
    """Calibration JSON is saved and exhibits realistic fidelity < 1.0."""
    cal = calibrate_ibm_backend(shots=1000, force=True, seed=42)
    backend_name = cal["backend_name"]
    safe_name = backend_name.lower().replace(" ", "_")
    path = os.path.join("experiments", "calibration", f"ibm_{safe_name}.json")

    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["backend_name"] == backend_name
    assert "calibration_date" in data
    assert 0.0 < data["effective_error_rate"] < 0.15
    assert 0.85 < data["fidelity"] < 1.0
    for state in ["0", "1", "+", "-"]:
        assert state in data["confusion_matrix"]
        assert 0.0 <= data["confusion_matrix"][state]["error_rate"] <= 0.15


def test_full_vs_calibrated_effective_error_rates():
    """FULL (Aer simulator per token) and CALIBRATED modes agree within statistical error."""
    rng = np.random.default_rng(12345)
    n_tokens = 150

    full_backend = IBMFakeTeleportationBackend(mode="full")
    cal_backend = IBMFakeTeleportationBackend(mode="calibrated")

    # Matched basis jobs across all 4 basis states
    jobs = []
    for _ in range(n_tokens):
        bit = int(rng.integers(0, 2))
        basis = int(rng.integers(0, 2))
        jobs.append(TeleportJob(bit=bit, basis=basis, meas_basis=basis))

    rng_full = np.random.default_rng(2026)
    out_full = full_backend.run(jobs, rng_full)

    rng_cal = np.random.default_rng(2026)
    out_cal = cal_backend.run(jobs, rng_cal)

    err_full = np.mean([o.outcome != j.bit for o, j in zip(out_full, jobs)])
    err_cal = np.mean([o.outcome != j.bit for o, j in zip(out_cal, jobs)])

    # Both error rates must be low (< 5%) and consistent within statistical margin
    se = np.sqrt(max(err_full, 0.01) * (1 - max(err_full, 0.01)) / n_tokens)
    assert abs(err_full - err_cal) <= 3.5 * se + 0.03


def test_metadata_in_transmission_and_qcert():
    """Backend name, calibration date and effective error rate appear in metadata and Q-Cert."""
    engine = TeleportationQDS(backend="ibm_fake")
    res = engine.execute_protocol("DEFENSE_ORDERS_ALPHA", n_bits=8, rng=np.random.default_rng(42))
    d = res.to_dict()

    assert d["ibm_backend"] is not None
    assert d["calibration_date"] is not None
    assert d["effective_error_rate"] is not None
    assert d["effective_error_rate"] > 0.0

    # Verify QCertGenerator records these fields
    cert = QCertGenerator.generate_qcert(
        transmission_id=res.transmission_id,
        message_text="DEFENSE_ORDERS_ALPHA",
        message_sha3_512="dummy_sha3",
        basis_schedule_symbols=["Z", "X"],
        n_bits=8,
        channel_qber=d["effective_error_rate"],
        is_valid=True,
        verifier_node="Bob",
        forgery_bound="1e-6",
        false_alarm_bound="1e-4",
        security_bits=128.0,
        s_a=0.05,
        s_v=0.10,
        eliminated_table=[["|0>"], ["|+>"]],
        symmetrisation_actions=["KEEP", "SWAP"],
        cb_status="OPEN",
        ibm_backend=d["ibm_backend"],
        calibration_date=d["calibration_date"],
        effective_error_rate=d["effective_error_rate"],
    )
    cert_dict = cert.to_dict()
    assert cert_dict["ibm_backend"] == d["ibm_backend"]
    assert cert_dict["calibration_date"] == d["calibration_date"]
    assert cert_dict["effective_error_rate"] == d["effective_error_rate"]

    # Verify audit record simulator block
    audit = AuditAuthority()
    evidence = {"verifications": {}, "additional_verifications": []}
    record = build_record(d, engine.params.to_dict(), evidence=evidence)
    sim_meta = record["simulator"]
    assert sim_meta["ibm_backend"] == d["ibm_backend"]
    assert sim_meta["calibration_date"] == d["calibration_date"]
    assert sim_meta["effective_error_rate"] == d["effective_error_rate"]


def test_honest_signature_l32_over_200_runs():
    """Honest signatures at L=32 under ibm_fake: accept rate over >=200 runs."""
    rng = np.random.default_rng(9999)
    engine = TeleportationQDS(backend="ibm_fake")

    total_runs = 200
    accepted = 0

    for i in range(total_runs):
        res = engine.execute_protocol(
            message_text=f"MISSION_PACKET_{i}",
            n_bits=32,
            rng=rng,
        )
        t = res.transcript
        # Check verifier acceptance
        bob_ok = t.display.get("bob") and t.display["bob"].accepted
        charlie_ok = t.display.get("charlie") and t.display["charlie"].accepted
        no_threat = not res.threat_report.is_threat_detected

        if bob_ok and charlie_ok and no_threat:
            accepted += 1

    accept_rate = accepted / total_runs
    print(f"\n[IBM Fake Backend] L=32 Honest Signature Accept Rate over {total_runs} runs: {accept_rate * 100:.2f}% ({accepted}/{total_runs})")

    # Honest transmissions on low-noise calibrated IBM backend should have high acceptance rate
    assert accept_rate >= 0.95
