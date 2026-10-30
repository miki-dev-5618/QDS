"""
Session roster and delivery configuration (optional N-verifier extension).

One signer serves a fixed, ordered roster of pre-enrolled verifiers. The
roster, delivery mode and maximum forwarding depth are fixed before any
evidence is distributed and are bound into the signer's commitment (through
``SignedContext``), so they cannot be reinterpreted later.

Delivery modes
  direct  Alice reveals to every roster member; each verifies independently.
          A recipient may pass the unchanged package to another roster member
          once (depth 1, H = 1): the original Bob -> Charlie transfer.
  chain   Alice reveals to the first roster member (depth 0); each recipient
          that accepts forwards the unchanged package to the next roster
          member (depth + 1). Forwarding stops at a rejection, an
          inconclusive result or depth H; later members are "not reached".

N (roster size) and H (maximum forwarding depth) are separate settings:
visiting all N recipients of a chain needs H = N - 1; a smaller H stops the
chain early and reports the rest as not reached.

What this does not provide: universal verification, multi-signer or
threshold approval, or any security gain from adding participants. One
dishonest verifier per scenario is modelled; collusion is not.
"""
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Stable verifier identities. Display labels may change; these ids never do.
VERIFIER_POOL: Tuple[str, ...] = ("bob", "charlie", "dave", "erin", "frank",
                                  "grace", "heidi", "ivan", "judy", "kim")
DEFAULT_ROSTER: Tuple[str, ...] = ("bob", "charlie")
MIN_VERIFIERS, MAX_VERIFIERS = 2, 10
DELIVERY_MODES = ("direct", "chain")
CONFIG_VERSION = "hedwig-roster/1"


class ConfigurationError(ValueError):
    """An unsupported or inconsistent session configuration (rejected before any evidence is prepared)."""


@dataclass(frozen=True)
class SessionConfig:
    roster: Tuple[str, ...] = DEFAULT_ROSTER
    delivery: str = "direct"
    max_depth: int = 1
    version: str = CONFIG_VERSION

    @classmethod
    def build(cls, roster: Optional[Sequence[str]] = None, n_verifiers: Optional[int] = None,
              delivery: str = "direct", max_depth: Optional[int] = None) -> "SessionConfig":
        """Roster from an explicit list, else the first ``n_verifiers`` pool members; H defaults to the full chain."""
        if roster is None:
            n = len(DEFAULT_ROSTER) if n_verifiers is None else int(n_verifiers)
            if not MIN_VERIFIERS <= n <= MAX_VERIFIERS:
                raise ConfigurationError(f"Verifier count must be between {MIN_VERIFIERS} and {MAX_VERIFIERS}.")
            roster = VERIFIER_POOL[:n]
        roster = tuple(str(v).strip().lower() for v in roster)
        if max_depth is None:
            max_depth = 1 if delivery == "direct" else len(roster) - 1
        cfg = cls(roster=roster, delivery=delivery, max_depth=int(max_depth))
        cfg.validate()
        return cfg

    def validate(self) -> None:
        n = len(self.roster)
        if not MIN_VERIFIERS <= n <= MAX_VERIFIERS:
            raise ConfigurationError(f"Roster must hold {MIN_VERIFIERS}-{MAX_VERIFIERS} verifiers (got {n}).")
        if len(set(self.roster)) != n:
            raise ConfigurationError("Roster contains duplicate verifier identities.")
        unknown = [v for v in self.roster if v not in VERIFIER_POOL]
        if unknown:
            raise ConfigurationError(f"Unknown (not enrolled) verifier(s): {', '.join(unknown)}.")
        if self.delivery not in DELIVERY_MODES:
            raise ConfigurationError(f"Unknown delivery mode {self.delivery!r}.")
        if self.delivery == "direct" and self.max_depth != 1:
            raise ConfigurationError("Direct delivery supports exactly one forwarding hop (H = 1).")
        if self.delivery == "chain" and not 1 <= self.max_depth <= n - 1:
            raise ConfigurationError(f"Chain depth H must be between 1 and N - 1 = {n - 1}.")

    # ------------------------------------------------------------ route rules
    @property
    def n(self) -> int:
        return len(self.roster)

    @property
    def is_default(self) -> bool:
        return self.roster == DEFAULT_ROSTER and self.delivery == "direct" and self.max_depth == 1

    def first_recipients(self) -> List[str]:
        """Recipients of Alice's reveal (depth 0)."""
        return list(self.roster) if self.delivery == "direct" else [self.roster[0]]

    def chain_route(self) -> List[str]:
        """Recipients a chain can reach, in order (depth = index)."""
        return list(self.roster[:self.max_depth + 1])

    def expected_depth(self, sender: str, recipient: str) -> Optional[int]:
        """
        The depth a transfer sender -> recipient has under this configuration, or None if the
        edge is not permitted. Derived from the configuration only, never from the package.
        """
        if sender not in self.roster or recipient not in self.roster or sender == recipient:
            return None
        if self.delivery == "direct":
            return 1
        i, j = self.roster.index(sender), self.roster.index(recipient)
        if j != i + 1 or j > self.max_depth:
            return None
        return j

    def next_hop(self, verifier: str) -> Optional[str]:
        if self.delivery != "chain" or verifier not in self.roster:
            return None
        j = self.roster.index(verifier) + 1
        return self.roster[j] if j < self.n and j <= self.max_depth else None

    def downstream_of(self, verifier: str) -> List[str]:
        if self.delivery != "chain" or verifier not in self.roster:
            return []
        return [v for v in self.roster[self.roster.index(verifier) + 1:]]

    def validate_dishonest(self, verifier: Optional[str]) -> None:
        """A dishonest-forwarder scenario needs a forwarder that has a permitted downstream recipient."""
        if verifier is None:
            raise ConfigurationError("Select the dishonest forwarder.")
        if verifier not in self.roster:
            raise ConfigurationError(f"Dishonest forwarder {verifier!r} is not in the session roster.")
        if self.delivery == "chain" and self.next_hop(verifier) is None:
            raise ConfigurationError(f"{verifier} has no downstream recipient within depth H = {self.max_depth}.")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["roster"] = list(self.roster)
        d["n_verifiers"] = self.n
        d["route"] = self.chain_route() if self.delivery == "chain" else list(self.roster)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionConfig":
        return cls(roster=tuple(d["roster"]), delivery=d.get("delivery", "direct"),
                   max_depth=int(d.get("max_depth", 1)), version=d.get("version", CONFIG_VERSION))


DEFAULT_CONFIG = SessionConfig()


def limits() -> Dict[str, Any]:
    return {"pool": list(VERIFIER_POOL), "default_roster": list(DEFAULT_ROSTER), "min_verifiers": MIN_VERIFIERS,
            "max_verifiers": MAX_VERIFIERS, "delivery_modes": list(DELIVERY_MODES), "version": CONFIG_VERSION}
