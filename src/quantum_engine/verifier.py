"""
A verifier node (Bob, Charlie, or any enrolled roster member).

A verifier decides using only:
  * the classical package it received (message, context, revealed signature,
    blinding value, and which peer forwarded it, if any);
  * its own trusted local records from the distribution stage (eliminated
    states, the signer's commitment, the authenticated sender identity, the
    channel test outcome, the session roster, delivery mode and depth H);
  * the parent verification event a forwarder names, as resolved by the
    simulation's authenticated event ledger (who verified it, at what depth);
  * its own replay state and clock.
It is never told which attack scenario, if any, was injected.

Transfers (N-verifier extension). The depth whose rule applies is derived
from the verifier's own record and the authenticated sender, never taken from
the package: a claimed depth, sender or parent that disagrees makes the
transfer invalid, and an invalid transfer is evaluated under the strictest
(depth 0) rule and rejected. Each verifier evaluates at most one forwarded
delivery per session (any sender, any route); later ones are refused as
duplicates without opening the reserve. The reserve is opened at most
``max_reserve_openings`` times per session across all channels.
"""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
import uuid
from typing import Callable, Dict, Any, List, Optional

from .binding import SignedPackage, commitment, digest_matches, reserve_commitment
from .channel import ChannelTestResult
from .elimination import OrthogonalEliminationEngine
from .replay import ReplayGuard
from .roster import SessionConfig
from .security import SecurityParameters


def estimate_readout_mismatch_overhead(n_tokens: int, p01: float, p10: float, location: str = "both") -> float:
    """
    Theoretical extra mismatch rate introduced by asymmetric detector readout error.
    - 'verifier_measurement': verifier detector flip rate p_m = (p01 + p10)/2.
    - 'bell_measurement': Alice Bell measurement bit flips trigger erroneous feed-forward Pauli corrections.
    - 'both': combined Bell-measurement corruption and verifier detector flips.
    """
    p_m = 0.5 * (float(p01) + float(p10))
    loc = location.lower()
    if loc in ("verifier_measurement", "verifier"):
        return p_m
    elif loc in ("bell_measurement", "bell"):
        return p_m
    return p_m * (1.0 - p_m) + (1.0 - p_m) * p_m


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
    insufficient_tokens: bool = False  # n_surviving < n_min
    tokens_received: int = 0
    tokens_planned: int = 0
    # Precommitted reserve (C2): measured at distribution like any copy, opened only for a borderline count.
    reserve_eliminated: List[List[str]] = field(default_factory=list)
    reserve_commitment: Optional[str] = None
    # Session configuration received from the signer at distribution (authenticated, pre-reveal).
    # None: a record built outside the engine; transfers are then not route-checked (legacy unit use).
    config: Optional[SessionConfig] = None
    security_params: Optional[SecurityParameters] = None

    @property
    def n_reserve(self) -> int:
        return sum(len(row) for row in self.reserve_eliminated)


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
    insufficient_tokens: bool = False
    tokens_received: int = 0
    tokens_planned: int = 0
    # Staged decision (C1/C2)
    elimination_outcome: str = "fail"      # "pass" | "fail" | "inconclusive"
    decision_stage: int = 1                # 1 = main copies only, 2 = reserve opened
    evidence_status: str = "sufficient"    # "sufficient" | "below_target" (risk budget not met at this n)
    reserve_available: int = 0             # reserve copies held for this session
    reserve_requested: bool = False        # borderline at stage 1 and the package carried no reserve opening
    reserve_checked: int = 0
    reserve_mismatches: int = 0
    reserve_binding_ok: Optional[bool] = None
    elimination_p: float = 1.0             # honest-hypothesis p-value, valid under the staged stopping rule
    # Transfer lifecycle (N-verifier extension)
    event_id: str = ""
    depth: int = 0                         # validated depth whose rule was applied
    max_depth: int = 1
    claimed_depth: Optional[int] = None
    parent_event_id: Optional[str] = None
    transfer_valid: bool = True
    transfer_reasons: List[str] = field(default_factory=list)
    duplicate: bool = False

    @property
    def inconclusive(self) -> bool:
        return self.elimination_outcome == "inconclusive"

    @property
    def status(self) -> str:
        """accepted | rejected | inconclusive | distribution_aborted (not_reached is a session-level status)."""
        if self.accepted:
            return "accepted"
        if self.session_aborted or self.insufficient_tokens:
            return "distribution_aborted"
        if (self.inconclusive and self.binding_pass and self.fresh and self.transfer_valid
                and self.record_found and self.sender_matches):
            return "inconclusive"
        return "rejected"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "verifier": self.verifier,
            "mode": self.mode,
            "status": self.status,
            "depth": self.depth,
            "max_depth": self.max_depth,
            "transfer": {
                "valid": self.transfer_valid,
                "claimed_depth": self.claimed_depth,
                "parent_event_id": self.parent_event_id,
                "duplicate": self.duplicate,
                "reasons": self.transfer_reasons,
            },
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
            "insufficient_tokens": self.insufficient_tokens,
            "tokens_received": self.tokens_received,
            "tokens_planned": self.tokens_planned,
            "tokens_received_str": f"{self.tokens_received}/{self.tokens_planned}" if self.tokens_planned else "—",
            "elimination_outcome": self.elimination_outcome,
            "decision_stage": self.decision_stage,
            "evidence_status": self.evidence_status,
            "reserve": {
                "available": self.reserve_available,
                "requested": self.reserve_requested,
                "opened": self.decision_stage == 2,
                "checked": self.reserve_checked,
                "mismatches": self.reserve_mismatches,
                "binding_ok": self.reserve_binding_ok,
            },
            "elimination_p": float(f"{self.elimination_p:.4e}"),
            "checks": {
                "distribution_record_found": self.record_found,
                "sender_matches_record": self.sender_matches,
                "addressed_to_verifier": self.addressed_to_verifier,
                "session_not_aborted": not self.session_aborted,
                "fresh": self.fresh,
                "freshness_reason": self.freshness_reason,
                "transfer_valid": self.transfer_valid,
                "elimination_pass": self.elimination_pass,
                "message_digest_matches": self.digest_matches,
                "commitment_matches": self.commitment_matches,
                "binding_pass": self.binding_pass,
                "sufficient_tokens": not self.insufficient_tokens,
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
        self._reserve_openings: Dict[str, int] = {}     # per session, across direct and forwarded channels
        self._forwarded_sessions: set = set()            # sessions with a final forwarded verification
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

    # -- transfer validation ---------------------------------------------------
    def _check_transfer(self, record: Optional[DistributionRecord], package: SignedPackage, forwarded: bool,
                        parent: Optional[Dict[str, Any]]) -> tuple:
        """(valid, depth, max_depth, reasons) from this verifier's own record and the resolved parent event."""
        cfg = record.config if record is not None else None
        if cfg is None:      # no route information: original two-level semantics
            return True, (1 if forwarded else 0), 1, []
        reasons: List[str] = []
        if not forwarded:
            if self.name not in cfg.first_recipients():
                reasons.append(f"Chain session: {self.name} may only receive this package by transfer, "
                               f"not directly from the signer.")
            return not reasons, 0, cfg.max_depth, reasons
        sender = package.forwarded_by
        depth = cfg.expected_depth(sender, self.name) if sender else None
        if sender not in cfg.roster:
            reasons.append(f"Forwarder '{sender}' is not a member of this session's roster.")
        elif depth is None:
            reasons.append(f"Transfer {sender} -> {self.name} is not a permitted edge of this session's route "
                           f"(delivery {cfg.delivery}, H = {cfg.max_depth}).")
        if package.depth is not None and depth is not None and package.depth != depth:
            reasons.append(f"Claimed depth {package.depth} differs from the validated depth {depth} of this edge.")
        if parent is None:
            reasons.append("No verification event of the forwarder is on record for the named parent; "
                           "the transfer has no valid parent.")
        else:
            if parent.get("session_id") != package.context.session_id:
                reasons.append("Named parent event belongs to a different session (substituted parent).")
            if parent.get("verifier") != sender:
                reasons.append(f"Named parent event was recorded by '{parent.get('verifier')}', not by the "
                               f"forwarder '{sender}' (substituted parent).")
            if depth is not None and parent.get("depth") != depth - 1:
                reasons.append(f"Parent event depth {parent.get('depth')} is inconsistent with transfer "
                               f"depth {depth}.")
        valid = not reasons
        return valid, (depth if valid else 0), cfg.max_depth, reasons

    # -- verification stage ------------------------------------------------
    def verify(self, package: SignedPackage, mode: str = "direct",
               parent: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """
        ``parent``: for a forwarded package, the ledger's summary of the event named by
        ``package.parent_event_id`` (None if no such event exists).
        """
        forwarded = mode == "forwarded"
        channel_key = f"forwarded:{package.forwarded_by}" if forwarded else "direct"
        ctx = package.context
        reasons: List[str] = []

        with self._lock:
            record = self.records.get(ctx.session_id)
            params = record.security_params if record and record.security_params else self.params
            transfer_valid, depth, max_depth, transfer_reasons = self._check_transfer(
                record, package, forwarded, parent)
            reasons.extend(transfer_reasons)
            duplicate = (forwarded and record is not None and record.config is not None
                         and ctx.session_id in self._forwarded_sessions)
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

            insufficient_tokens = bool(record and record.insufficient_tokens)
            if insufficient_tokens:
                reasons.append("Session aborted at distribution: INSUFFICIENT_TOKENS (photon loss exceeded tolerance).")

            fresh, freshness_reason = self.replay_guard.freshness(ctx.nonce, ctx.timestamp, channel_key)
            if fresh and duplicate:
                fresh, freshness_reason = False, "duplicate_delivery"
            if not fresh:
                reasons.append({
                    "duplicate_delivery": "This verifier already evaluated a forwarded delivery of this session; "
                                          "repeated deliveries (any sender or route) are refused and never open "
                                          "the reserve.",
                    "duplicate_nonce": "Nonce already consumed by an accepted package (replay).",
                    "expired": "Timestamp outside the freshness window.",
                    "timestamp_in_future": "Timestamp is in the future beyond allowed clock skew.",
                }[freshness_reason])

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

            eliminated = record.eliminated if record else []
            mismatches, n_checked, positions = OrthogonalEliminationEngine.count_mismatches(
                package.revealed_signature, eliminated)
            length_ok = bool(record) and len(package.revealed_signature) == len(eliminated)
            if record and not length_ok:
                reasons.append("Revealed signature length differs from distributed token count.")
            n_reserve = record.n_reserve if record else 0
            # An invalid transfer never obtains a more permissive rule: it is evaluated at depth 0.
            rule = params.elimination_rule(n_checked, forwarded and transfer_valid, n_reserve,
                                                depth=depth, max_depth=max_depth)
            limit = rule.a1
            stage, outcome = 1, "fail"
            reserve_requested, reserve_binding_ok = False, None
            r_mis = r_checked = 0
            elim_p = rule.p_value(mismatches) if n_checked else 1.0
            if record_found and n_checked > 0 and length_ok:
                outcome = rule.stage1(mismatches)
                if outcome == "borderline":
                    outcome = "inconclusive"
                    # The reserve is only worth (and only spent on) a package that is exactly what the signer
                    # committed to; anything else is rejected on binding regardless of the count.
                    if rule.two_stage and not (digest_ok and commit_ok and transfer_valid and not duplicate):
                        pass
                    elif rule.two_stage and package.reserve is None:
                        reserve_requested = True
                    elif rule.two_stage:
                        key = ctx.session_id
                        opened = self._reserve_openings.get(key, 0)
                        if opened >= self.params.max_reserve_openings:
                            reasons.append("Reserve already opened for this session (on any channel); "
                                           "no further evidence is accepted (bounded retry).")
                        else:
                            self._reserve_openings[key] = opened + 1
                            stage = 2
                            states = [tuple(x) for x in package.reserve.states]
                            try:
                                reserve_binding_ok = (len(states) == len(record.reserve_eliminated) and
                                                      reserve_commitment(ctx, states, package.reserve.blinding)
                                                      == record.reserve_commitment)
                            except (ValueError, TypeError):
                                reserve_binding_ok = False
                            r_mis, r_checked, _ = OrthogonalEliminationEngine.count_mismatches(
                                states, record.reserve_eliminated)
                            if reserve_binding_ok:
                                outcome = rule.stage2(mismatches, r_mis)
                                elim_p = rule.p_value(mismatches, r_mis)
                            else:
                                outcome = "fail"
                                reasons.append("Reserve opening does not match the signer's distribution-stage "
                                               "reserve commitment.")
            elimination_pass = outcome == "pass"
            if record_found and outcome == "fail" and reserve_binding_ok is not False:
                if stage == 2:
                    reasons.append(f"Elimination check failed at stage 2: {mismatches} + {r_mis} mismatches in "
                                   f"{n_checked} + {r_checked} copies (limit {rule.a2}).")
                else:
                    reasons.append(f"Elimination check failed: {mismatches} mismatches in {n_checked} copies "
                                   f"(limit {limit}).")
            elif outcome == "inconclusive":
                more = (" Reserve opening requested from the signer." if reserve_requested else
                        "" if rule.two_stage else " No reserve evidence is available for this session.")
                reasons.append(f"Elimination evidence inconclusive: {mismatches} mismatches in {n_checked} copies "
                               f"lies between the accept limit {rule.a1} and the decisive-reject limit {rule.r1} "
                               f"at this sample size.{more}")

            binding_pass = digest_ok and commit_ok and reserve_binding_ok is not False

            accepted = (record_found and sender_matches and addressed and not aborted and not insufficient_tokens and fresh
                        and elimination_pass and binding_pass and transfer_valid)
            if accepted and not self.replay_guard.consume(ctx.nonce, channel_key):
                # Lost a race with a concurrent identical package: the nonce is already spent.
                accepted, fresh, freshness_reason = False, False, "duplicate_nonce"
                reasons.append("Nonce already consumed by an accepted package (replay).")
            if accepted:
                self._accepted_sessions.add(ctx.session_id)
            if forwarded and record_found and not reserve_requested:
                self._forwarded_sessions.add(ctx.session_id)

        tokens_received = record.tokens_received if record else 0
        tokens_planned = record.tokens_planned if record else 0

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
            bounds=params.bounds(n_checked, mismatches, forwarded and transfer_valid, rule=rule,
                                      reserve_mismatches=r_mis if stage == 2 else None),
            insufficient_tokens=insufficient_tokens,
            tokens_received=tokens_received,
            tokens_planned=tokens_planned,
            elimination_outcome=outcome,
            decision_stage=stage,
            evidence_status="sufficient" if rule.sufficient else "below_target",
            reserve_available=n_reserve,
            reserve_requested=reserve_requested,
            reserve_checked=r_checked,
            reserve_mismatches=r_mis,
            reserve_binding_ok=reserve_binding_ok,
            elimination_p=elim_p,
            event_id=f"EV-{uuid.uuid4().hex[:10].upper()}",
            depth=depth,
            max_depth=max_depth,
            claimed_depth=package.depth,
            parent_event_id=package.parent_event_id,
            transfer_valid=transfer_valid,
            transfer_reasons=transfer_reasons,
            duplicate=duplicate,
        )
