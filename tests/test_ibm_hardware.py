"""
Tests for the IBM hardware teleportation benchmark scripts.

Everything here runs on the local simulator with fixed seeds: no IBM token, no
network access and no QPU time are used.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARDWARE_DIR = os.path.join(ROOT, "experiments", "hardware")
if HARDWARE_DIR not in sys.path:
    sys.path.insert(0, HARDWARE_DIR)

import compare_hw_vs_sim  # noqa: E402
import run_ibm_teleport as hw  # noqa: E402


class _FakeBackend:
    def __init__(self, name, num_qubits, pending_jobs):
        self.name = name
        self.num_qubits = num_qubits
        self.pending_jobs = pending_jobs


class _FakeService:
    def __init__(self, backends):
        self._backends = backends

    def backends(self, **kwargs):
        assert kwargs.get("min_num_qubits") == hw.MIN_QUBITS
        assert kwargs.get("operational") is True
        assert kwargs.get("simulator") is False
        return self._backends

    def backend(self, name):
        return next(b for b in self._backends if b.name == name)


def _result_files(directory):
    return sorted(n for n in os.listdir(directory) if n.startswith("result_") and n.endswith(".json"))


def _load_only_result(directory):
    files = _result_files(str(directory))
    assert len(files) == 1
    with open(os.path.join(str(directory), files[0]), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Initialisation: credentials, defaults, backend selection
# --------------------------------------------------------------------------
def test_token_is_read_from_the_environment_only(monkeypatch):
    monkeypatch.delenv(hw.TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match=hw.TOKEN_ENV):
        hw.get_token()
    monkeypatch.setenv(hw.TOKEN_ENV, "  secret-token  ")
    assert hw.get_token() == "secret-token"


def test_defaults_are_the_documented_contract():
    args = hw.parse_args([])
    assert args.shots == 2000
    assert args.dry_run is False
    assert args.backend is None
    assert args.output_dir == hw.DEFAULT_OUTPUT_DIR


@pytest.mark.parametrize("bad", ["0", "-5"])
def test_non_positive_shots_are_rejected(bad):
    with pytest.raises(SystemExit):
        hw.parse_args(["--shots", bad])


def test_least_busy_backend_with_enough_qubits_is_selected():
    service = _FakeService([
        _FakeBackend("busy", 3, 9),
        _FakeBackend("idle", 127, 2),
        _FakeBackend("unknown_queue", 5, None),
    ])
    assert hw.select_backend(service).name == "idle"


def test_explicit_backend_must_have_three_qubits():
    service = _FakeService([_FakeBackend("tiny", 2, 0)])
    with pytest.raises(RuntimeError, match="at least 3 qubits"):
        hw.select_backend(service, name="tiny")


# --------------------------------------------------------------------------
# Circuit construction
# --------------------------------------------------------------------------
def test_four_states_use_deferred_measurement_and_matched_bases():
    circuits = hw.build_state_circuits()
    assert len(circuits) == len(hw.STATES) == 4

    for index, ((_label, _bit, basis), circuit) in enumerate(zip(hw.STATES, circuits)):
        names = [instruction.operation.name for instruction in circuit.data]
        assert circuit.num_qubits == 3
        assert circuit.num_clbits == 3
        assert "if_else" not in names                     # no mid-circuit feed-forward
        assert names.count("measure") == 3
        assert "cx" in names and "cz" in names             # coherent corrections
        assert circuit.name == f"teleport_{index}"
        # Bob's qubit is measured last; the last gate applied to it is a
        # Hadamard exactly for the X-basis states |+> and |->.
        assert names[-1] == "measure"
        last_gate_on_bob = next(
            instruction.operation.name
            for instruction in reversed(circuit.data)
            if instruction.operation.name != "measure"
            and circuit.qubits[2] in instruction.qubits
        )
        assert (last_gate_on_bob == "h") is (basis == 1)


def test_counts_helpers_read_bobs_outcome_from_the_leftmost_bit():
    counts = {"000": 10, "010": 5, "100": 3, "110": 2}
    assert hw.outcome_bit("011") == 0
    assert hw.success_count(counts, 0) == 15
    assert hw.success_count(counts, 1) == 5
    assert hw.normalise_counts({"0 1 1": 4}) == {"011": 4}
    assert hw.normalise_counts({"0x3": 1}) == {"011": 1}
    with pytest.raises(ValueError):
        hw.normalise_counts({"01": 1})


# --------------------------------------------------------------------------
# Dry run and JSON serialisation
# --------------------------------------------------------------------------
def test_dry_run_writes_a_complete_result_file(tmp_path):
    assert hw.main(["--dry-run", "--shots", "200", "--seed", "7",
                    "--output-dir", str(tmp_path)]) == 0
    record = _load_only_result(tmp_path)

    assert record["schema_version"] == hw.SCHEMA_VERSION
    assert record["mode"] == "dry-run"
    assert record["job_id"] is None
    assert record["backend_name"] == "aer_simulator"
    assert record["timestamp"].endswith("Z")
    assert record["timestamp_compact"] in _result_files(str(tmp_path))[0]
    assert record["execution"]["shots"] == 200
    assert record["execution"]["optimization_level"] == 1
    assert record["execution"]["sampler"] == "SamplerV2"
    assert record["execution"]["transpile_backend"].startswith("generic_backend")
    assert [state["label"] for state in record["states"]] == ["0", "1", "+", "-"]
    assert record["total_shots"] == 800

    for state in record["states"]:
        assert sum(state["counts"].values()) == state["shots"] == 200
        assert state["success_rate"] == pytest.approx(state["success_count"] / state["shots"])
        assert 0.0 <= state["success_rate"] <= 1.0
        assert state["measurement_basis"] == state["basis"]
        assert state["circuit"]["num_qubits"] == 3
    # An ideal local run teleports every state correctly.
    assert all(state["success_rate"] >= 0.99 for state in record["states"])
    json.dumps(record)  # every field is plain JSON, no numpy scalars or dataclasses


def test_dry_run_is_deterministic_for_a_fixed_seed(tmp_path):
    for name in ("first", "second"):
        assert hw.main(["--dry-run", "--shots", "100", "--seed", "11",
                        "--output-dir", str(tmp_path / name)]) == 0
    first = _load_only_result(tmp_path / "first")
    second = _load_only_result(tmp_path / "second")
    assert [state["counts"] for state in first["states"]] == \
           [state["counts"] for state in second["states"]]


def test_result_files_are_never_overwritten(tmp_path):
    payload = {"timestamp_compact": "20260101T000000Z", "states": []}
    first = hw.write_result(payload, str(tmp_path))
    second = hw.write_result(payload, str(tmp_path))
    assert first != second
    assert os.path.exists(first) and os.path.exists(second)


def test_missing_token_fails_before_any_hardware_access(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(hw.TOKEN_ENV, raising=False)
    assert hw.main(["--shots", "10", "--output-dir", str(tmp_path)]) == 2
    assert hw.TOKEN_ENV in capsys.readouterr().err
    assert _result_files(str(tmp_path)) == []


# --------------------------------------------------------------------------
# Recovering a finished job (the submitting process may have died)
# --------------------------------------------------------------------------
class _FakeCounts:
    def __init__(self, counts):
        self._counts = counts

    def get_counts(self):
        return dict(self._counts)


class _FakeJob:
    def __init__(self, backend, pubs, status="DONE", creation_date=None):
        self._backend = backend
        self._pubs = pubs
        self._status = status
        self.creation_date = creation_date

    def status(self):
        return self._status

    def backend(self):
        return self._backend

    def result(self):
        return self._pubs


class _FakeJobService:
    def __init__(self, job):
        self._job = job

    def job(self, job_id):
        assert job_id == "fake-job"
        return self._job


def _pubs(*counts_per_state):
    """Minimal stand-ins for SamplerPubResult objects: only .data[field].get_counts()."""
    return [
        type("FakePub", (), {"data": {"c": _FakeCounts(counts)}})()
        for counts in counts_per_state
    ]


def test_finished_job_is_recovered_into_a_hardware_result_file(monkeypatch, tmp_path):
    backend = hw.local_reference_backend(seed=3)
    pubs = _pubs(
        {"000": 190, "100": 10},
        {"101": 195, "111": 5},
        {"000": 195, "101": 5},
        {"110": 194, "100": 6},
    )
    monkeypatch.setattr(hw, "connect", lambda token, channel=hw.DEFAULT_CHANNEL: _FakeJobService(
        _FakeJob(backend, pubs)))
    monkeypatch.setenv(hw.TOKEN_ENV, "token")

    assert hw.main(["--job-id", "fake-job", "--output-dir", str(tmp_path)]) == 0
    record = _load_only_result(tmp_path)

    assert record["mode"] == "hardware"           # never labelled as a simulation
    assert record["job_id"] == "fake-job"
    assert record["backend_name"] == backend.name
    assert record["execution"]["shots"] == 200     # taken from the job, not --shots
    assert record["total_shots"] == 800
    assert [state["counts"] for state in record["states"]] == [
        {"000": 190, "100": 10},
        {"101": 195, "111": 5},
        {"000": 195, "101": 5},
        {"100": 6, "110": 194},
    ]
    assert [state["success_count"] for state in record["states"]] == [190, 200, 195, 200]


def test_unfinished_job_is_refused_without_writing_a_result(monkeypatch, tmp_path, capsys):
    backend = hw.local_reference_backend(seed=3)
    monkeypatch.setattr(hw, "connect", lambda token, channel=hw.DEFAULT_CHANNEL: _FakeJobService(
        _FakeJob(backend, [], status="QUEUED")))
    monkeypatch.setenv(hw.TOKEN_ENV, "token")

    assert hw.main(["--job-id", "fake-job", "--output-dir", str(tmp_path)]) == 2
    assert "QUEUED" in capsys.readouterr().err
    assert _result_files(str(tmp_path)) == []


def test_job_id_cannot_be_combined_with_dry_run():
    with pytest.raises(SystemExit):
        hw.parse_args(["--job-id", "abc", "--dry-run"])


def test_a_hardware_device_name_resolves_to_its_own_fake_backend():
    """The simulated column must use the calibration of the device that ran."""
    pytest.importorskip("qiskit_ibm_runtime")
    from src.quantum_engine.teleportation import get_fake_backend

    resolved = get_fake_backend("ibm_fez").name
    assert resolved in ("fake_fez", "ibm_fez")
    assert compare_hw_vs_sim._device_stem("ibm_fez") == compare_hw_vs_sim._device_stem(resolved)


# --------------------------------------------------------------------------
# Comparison matrix
# --------------------------------------------------------------------------
def test_comparison_prints_the_matrix_for_a_saved_run(tmp_path, capsys):
    assert hw.main(["--dry-run", "--shots", "200", "--seed", "7",
                    "--output-dir", str(tmp_path)]) == 0
    path = os.path.join(str(tmp_path), _result_files(str(tmp_path))[0])

    assert compare_hw_vs_sim.main([path, "--shots", "200", "--seed", "7"]) == 0
    out = capsys.readouterr().out

    assert "Hardware Success Rate" in out
    assert "Simulated Success Rate" in out
    assert "Ideal Success Rate" in out
    for label in ("|0>", "|1>", "|+>", "|->"):
        assert label in out
    assert "dry-run" in out.lower()
    assert "noise model" in out.lower()


def test_comparison_rejects_missing_or_empty_files(tmp_path, capsys):
    missing = os.path.join(str(tmp_path), "result_missing.json")
    assert compare_hw_vs_sim.main([missing]) == 1
    assert "not found" in capsys.readouterr().out.lower()

    empty = tmp_path / "result_empty.json"
    empty.write_text(json.dumps({"states": []}), encoding="utf-8")
    assert compare_hw_vs_sim.main([str(empty)]) == 1
    assert "cannot read" in capsys.readouterr().out.lower()
