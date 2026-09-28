"""
A verifier node (Bob or Charlie).

A verifier decides using only:
  * the classical package it received (message, context, revealed signature,
    blinding value, and which peer forwarded it, if any);
  * its own trusted local records from the distribution stage (eliminated
    states, the signer's commitment, the authenticated sender identity, the
    channel test outcome);
  * its own replay state and clock.
It is never told which attack scenario, if any, was injected.
"""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Optional

from .binding import SignedPackage, commitment, digest_matches
from .channel import ChannelTestResult
from .elimination import OrthogonalEliminationEngine
from .replay import ReplayGuard
from .security import SecurityParameters


@dataclass
class DistributionRecord:
    session_id: str
    sender: str
    commitment: str
    eliminated: List[List[str]]        # per position, one eliminated symbol per measured copy
    held_desc: List[List[str]]
    channel_test: ChannelTestResult
    aborted: bool                      # channel test raised an alarm
    created: float = field(default_factory=time.time)


@dataclass
class VerificationResult:
    verifier: str
    mode: str                          # "direct" or "forwarded"
    forwarded_by: Optional[str]
    session_id: str
    claimed_sender: str
    received_message: str
    revealed_signature: List[List[int]]
    # checks
    record_found: bool
    sender_matches: bool
    addressed_to_verifier: bool
    session_aborted: bool
    fresh: bool
    freshness_reason: str
    n_checked: int
    mismatches: int
    acceptance_limit: int
    elimination_pass: bool
    contradiction_indices: List[int]
    digest_matches: bool
    commitment_matches: bool
    binding_pass: bool
    accepted: bool
    reasons: List[str]
    # display
    eliminated_states: List[List[str]]
    held_tokens: List[List[str]]
    bounds: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verifier": self.verifier,
            "mode": self.mode,
            "forwarded_by": self.forwarded_by,
            "session_id": self.session_id,
            "claimed_sender": self.claimed_sender,
            "received_message": self.received_message,
            "revealed_signature": self.revealed_signature,
            "is_valid": self.accepted,
            "mismatches": self.mismatches,
            "total_checked": self.n_checked,
            "acceptance_limit": self.acceptance_limit,
            "contradiction_indices": self.contradiction_indices,
            "eliminated_states": self.eliminated_states,
            "held_tokens": self.held_tokens,
            "checks": {
                "distribution_record_found": self.record_found,
                "sender_matches_record": self.sender_matches,
                "addressed_to_verifier": self.addressed_to_verifier,
                "session_not_aborted": not self.session_aborted,
                "fresh": self.fresh,
                "freshness_reason": self.freshness_reason,
                "elimination_pass": self.elimination_pass,
                "message_digest_matches": self.digest_matches,
                "commitment_matches": self.commitment_matches,
                "binding_pass": self.binding_pass,
            },
            "reasons": self.reasons,
            "bounds": self.bounds,
        }


class VerifierNode:
    def __init__(self, name: str, params: SecurityParameters,
                 clock: Callable[[], float] = time.time, max_records: int = 1000, store=None):
        self.name = name
        self.params = params
        self.records: "OrderedDict[str, DistributionRecord]" = OrderedDict()
        self.replay_guard = ReplayGuard(window_seconds=params.freshness_window_s, clock=clock,
                                        store=store, owner=name)
        self.max_records = max_records
        self._accepted_sessions: set = set()
        self._lock = threading.RLock()

    # -- distribution stage ------------------------------------------------
    def receive_distribution(self, record: DistributionRecord):
        with self._lock:
            self.records[record.session_id] = record
            while len(self.records) > self.max_records:
                self.records.popitem(last=False)

    def purge_pending(self, sender: str) -> int:
        """Drop distribution records from `sender` that were never accepted (transient buffers)."""
        with self._lock:
            pending = [sid for sid, rec in self.records.items()
                       if rec.sender == sender and sid not in self._accepted_sessions]
            for sid in pending:
                del self.records[sid]
            return len(pending)

    # -- verification stage ------------------------------------------------
    def verify(self, package: SignedPackage, mode: str = "direct") -> VerificationResult:
        forwarded = mode == "forwarded"
        channel_key = f"forwarded:{package.forwarded_by}" if forwarded else "direct"
        ctx = package.context
        reasons: List[str] = []

        with self._lock:
            record = self.records.get(ctx.session_id)
            record_found = record is not None
            sender_matches = record_found and record.sender == ctx.sender
            addressed = self.name in ctx.verifiers
            if not record_found:
                reasons.append("No distribution record for this session: no quantum tokens were received "
                               "from the claimed sender.")
            elif not sender_matches:
                reasons.append(f"Claimed sender '{ctx.sender}' differs from authenticated distributor '{record.sender}'.")
            if not addressed:
                reasons.append("Package is not addressed to this verifier.")

            aborted = bool(record and record.aborted)
            if aborted:
                reasons.append("Session aborted at distribution: channel test alarm.")

            fresh, freshness_reason = self.replay_guard.freshness(ctx.nonce, ctx.timestamp, channel_key)
            if not fresh:
                reasons.append({
                    "duplicate_nonce": "Nonce already consumed by an accepted package (replay).",
                    "expired": "Timestamp outside the freshness window.",
                    "timestamp_in_future": "Timestamp is in the future beyond allowed clock skew.",
                }[freshness_reason])

            eliminated = record.eliminated if record else []
            mismatches, n_checked, positions = OrthogonalEliminationEngine.count_mismatches(
                package.revealed_signature, eliminated)
            if record and len(package.revealed_signature) != len(eliminated):
                reasons.append("Revealed signature length differs from distributed token count.")
            limit = self.params.acceptance_limit(n_checked, forwarded)
            elimination_pass = (record_found and n_checked > 0 and mismatches <= limit
                                and len(package.revealed_signature) == len(eliminated))
            if record_found and not elimination_pass:
                reasons.append(f"Elimination check failed: {mismatches} mismatches in {n_checked} copies "
                               f"(limit {limit}).")

            digest_ok = digest_matches(package.message, ctx)
            try:
                commit_ok = bool(record) and commitment(ctx, package.revealed_signature,
                                                        package.blinding) == record.commitment
            except (ValueError, TypeError):  # malformed blinding or non-canonical context
                commit_ok = False
            if not digest_ok:
                reasons.append(f"{ctx.digest_alg.upper()} digest of received message does not match the "
                               f"signed context digest.")
            if record and not commit_ok:
                reasons.append("Context/signature do not match the signer's distribution-stage commitment.")
            binding_pass = digest_ok and commit_ok

            accepted = (record_found and sender_matches and addressed and not aborted and fresh
                        and elimination_pass and binding_pass)
            if accepted and not self.replay_guard.consume(ctx.nonce, channel_key):
                # Lost a race with a concurrent identical package: the nonce is already spent.
                accepted, fresh, freshness_reason = False, False, "duplicate_nonce"
                reasons.append("Nonce already consumed by an accepted package (replay).")
            if accepted:
                self._accepted_sessions.add(ctx.session_id)

        return VerificationResult(
            verifier=self.name,
            mode=mode,
            forwarded_by=package.forwarded_by,
            session_id=ctx.session_id,
            claimed_sender=ctx.sender,
            received_message=package.message,
            revealed_signature=[list(s) for s in package.revealed_signature],
            record_found=record_found,
            sender_matches=sender_matches,
            addressed_to_verifier=addressed,
            session_aborted=aborted,
            fresh=fresh,
            freshness_reason=freshness_reason,
            n_checked=n_checked,
            mismatches=mismatches,
            acceptance_limit=limit,
            elimination_pass=elimination_pass,
            contradiction_indices=positions,
            digest_matches=digest_ok,
            commitment_matches=commit_ok,
            binding_pass=binding_pass,
            accepted=accepted,
            reasons=reasons,
            eliminated_states=eliminated,
            held_tokens=record.held_desc if record else [],
            bounds=self.params.bounds(n_checked, mismatches, forwarded),
        )
