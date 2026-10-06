"""Issues 2 and 3: real replay state and real message binding."""
from src.quantum_engine import ThreatClassification, ThreatScenarioConfig, ThreatType
from src.quantum_engine.binding import message_digest


def _send(engine, rng, msg="transfer 10"):
    session = engine.distribute("alice", msg, 32, rng)
    return engine.reveal(session)


def _verdicts(results):
    return [r.accepted for r in results]


def test_first_accepted_identical_second_rejected(engine, rng):
    pkg = _send(engine, rng)
    assert _verdicts(engine.deliver(pkg)) == [True, True]
    again = engine.deliver(pkg.copy())
    assert _verdicts(again) == [False, False]
    assert {r.freshness_reason for r in again} == {"duplicate_nonce"}


def test_new_nonce_accepted(engine, rng):
    assert _verdicts(engine.deliver(_send(engine, rng))) == [True, True]
    assert _verdicts(engine.deliver(_send(engine, rng))) == [True, True]


def test_expired_package_rejected(engine, rng, clock):
    pkg = _send(engine, rng)
    clock.advance(engine.params.freshness_window_s + 1)
    results = engine.deliver(pkg)
    assert _verdicts(results) == [False, False]
    assert {r.freshness_reason for r in results} == {"expired"}


def test_changed_nonce_without_matching_signature_rejected(engine, rng):
    pkg = _send(engine, rng)
    engine.deliver(pkg)
    forged = pkg.copy()
    forged.context.nonce = "00" * 16
    results = engine.deliver(forged)
    assert all(r.fresh for r in results)            # new nonce passes the replay set...
    assert all(not r.commitment_matches for r in results)  # ...but not the signer's commitment
    assert _verdicts(results) == [False, False]


def test_rejected_package_does_not_burn_the_nonce(engine, rng):
    pkg = _send(engine, rng)
    assert _verdicts(engine.deliver(pkg.copy(message="tampered"))) == [False, False]
    assert _verdicts(engine.deliver(pkg)) == [True, True]


def test_one_byte_change_rejected(engine, rng):
    pkg = _send(engine, rng, "pay 100 to acct 42")
    results = engine.deliver(pkg.copy(message="pay 100 to acct 43"))
    assert _verdicts(results) == [False, False]
    assert all(r.elimination_pass and not r.digest_matches for r in results)


def test_updating_metadata_cannot_validate_modified_payload(engine, rng):
    pkg = _send(engine, rng, "pay 100")
    bad = pkg.copy(message="pay 999")
    bad.context.message_digest = message_digest("pay 999")
    results = engine.deliver(bad)
    assert all(r.digest_matches and not r.commitment_matches for r in results)
    assert _verdicts(results) == [False, False]


def test_unchanged_payload_accepted(engine, rng):
    assert _verdicts(engine.deliver(_send(engine, rng))) == [True, True]


def test_replay_scenario_resends_a_real_package(engine, rng):
    first = engine.execute_protocol("hello", 32, rng=rng)
    assert not first.threat_report.is_threat_detected
    replay = engine.execute_protocol("ignored", 32, rng=rng,
                                     scenario=ThreatScenarioConfig(threat_type=ThreatType.REPLAY))
    assert replay.transcript.package.context.nonce == first.transcript.package.context.nonce
    assert replay.threat_report.classification == ThreatClassification.REPLAY_ATTACK
